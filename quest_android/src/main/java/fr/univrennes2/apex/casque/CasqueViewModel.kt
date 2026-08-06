package fr.univrennes2.apex.casque

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.time.LocalTime
import java.time.format.DateTimeFormatter

/**
 * État observable du pilotage, et point d'entrée depuis l'interface.
 *
 * Trois précautions valent d'être signalées, car elles ne se voient pas dans
 * la signature des méthodes.
 *
 * **Tout passe hors du fil principal.** Une commande ADB traverse le réseau et
 * attend la réponse du casque : quelques centaines de millisecondes en temps
 * normal, plusieurs secondes quand il dort. Sur le fil principal, l'interface
 * se figerait.
 *
 * **Une commande à la fois.** Un écran tactile invite aux appuis répétés, et
 * deux commandes simultanées sur le même casque produiraient des résultats
 * incohérents. Le verrou est ici, pas dans l'interface, pour qu'aucun appel
 * ne puisse s'y soustraire.
 *
 * **La connexion se rouvre à chaque action.** Ouvrir une connexion coûte peu ;
 * en garder une ouverte pendant qu'un soignant traverse le service avec la
 * tablette, beaucoup — elle meurt en silence et la commande suivante échoue
 * sans qu'on sache pourquoi.
 */
class CasqueViewModel(application: Application) : AndroidViewModel(application) {

    private val _etat = MutableStateFlow(EtatCasque())
    val etat: StateFlow<EtatCasque> = _etat.asStateFlow()

    private val verrou = Mutex()
    private val horloge = DateTimeFormatter.ofPattern("HH:mm:ss")

    /** Adresse du casque, à renseigner une fois et à conserver. */
    var adresse: String = ""
        set(valeur) {
            field = valeur.trim()
            _etat.update { it.copy(adresse = field) }
        }

    /** Code PIN Store, pour la voie officielle de la limite de jeu. */
    var codePin: String = ""

    /** Identifiant du jeu. */
    var paquetJeu: String = CasqueQuest.PAQUET_PAR_DEFAUT

    init {
        val cleFournie = ClientCasque.preparerIdentite(application)
        _etat.update { it.copy(clePreAutorisee = cleFournie) }
        journal(
            if (cleFournie) {
                "Clé ADB pré-autorisée chargée : aucune validation dans le casque."
            } else {
                "Aucune clé fournie : la première connexion demandera une " +
                    "autorisation à donner dans le casque."
            }
        )
    }

    // -- actions --------------------------------------------------------------

    fun rafraichirEtat() = lancer("État") { casque ->
        val limite = casque.limiteActive()
        _etat.update {
            it.copy(
                connecte = true,
                modele = casque.modele(),
                batterie = casque.batterie(),
                application = casque.applicationActive(),
                limiteActive = limite.active,
                servicesTestDisponibles = limite.servicesDisponibles,
            )
        }
        emptyList()
    }

    fun preparerSeance() = lancer("Préparation") { casque ->
        val etapes = casque.preparerSeance(codePin = codePin, paquet = paquetJeu)
        etapes.forEach { etape ->
            journal(
                (if (etape.reussie) "OK — " else "ÉCHEC — ") + etape.libelle +
                    if (etape.detail.isNotBlank()) " : ${etape.detail}" else "",
                erreur = !etape.reussie,
            )
        }
        val rates = etapes.count { !it.reussie }
        if (rates > 0) {
            throw OperationRefusee(
                "$rates étape(s) en échec. Le casque peut tout de même être " +
                    "utilisable — vérifiez avant de le tendre au participant."
            )
        }
        emptyList()
    }

    fun desactiverLimite() = lancer("Limite désactivée") { casque ->
        casque.definirLimite(active = false, codePin = codePin)
    }

    fun activerLimite() = lancer("Limite rétablie") { casque ->
        casque.definirLimite(active = true, codePin = codePin)
    }

    fun lancerJeu() = lancer("Jeu lancé") { casque ->
        casque.lancer(paquetJeu)
        emptyList()
    }

    fun arreterJeu() = lancer("Jeu arrêté") { casque ->
        casque.arreter(paquetJeu)
        emptyList()
    }

    fun chercherLeJeu() = lancer("Recherche du jeu") { casque ->
        val trouve = casque.devinerPaquetJeu()
        if (trouve == null) {
            val toutes = casque.listerApplications("apex")
            throw OperationRefusee(
                if (toutes.isEmpty()) {
                    "Aucune application dont le nom contienne « apex »."
                } else {
                    "Plusieurs candidats : ${toutes.joinToString(", ")}. " +
                        "Choisissez l'identifiant à la main."
                }
            )
        }
        paquetJeu = trouve
        listOf("Jeu configuré : $trouve")
    }

    // -- mécanique ------------------------------------------------------------

    private fun lancer(libelle: String, action: (CasqueQuest) -> List<String>) {
        viewModelScope.launch {
            // Un appui pendant qu'une commande tourne est ignoré plutôt que
            // mis en file : sur un écran tactile, la file se remplirait de
            // doublons sans que personne ne les ait voulus.
            if (verrou.isLocked) return@launch
            verrou.withLock {
                _etat.update { it.copy(occupe = true) }
                journal("→ $libelle…")
                try {
                    if (adresse.isBlank()) {
                        throw CasqueInjoignable(
                            "Renseignez l'adresse IP du casque " +
                                "(Paramètres du casque > Wi-Fi > réseau connecté)."
                        )
                    }
                    withContext(Dispatchers.IO) {
                        ClientCasque.connecter(adresse).use { client ->
                            client.tenterPersistanceReseau()
                            action(CasqueQuest(client, paquetJeu))
                        }
                    }.forEach { journal("   $it") }
                    journal("✓ $libelle")
                } catch (e: CasqueInjoignable) {
                    _etat.update { it.copy(connecte = false) }
                    journal("✗ ${e.message}", erreur = true)
                } catch (e: Exception) {
                    journal("✗ ${e.message ?: e.javaClass.simpleName}", erreur = true)
                } finally {
                    _etat.update { it.copy(occupe = false) }
                }
            }
        }
    }

    private fun journal(texte: String, erreur: Boolean = false) {
        val ligne = LigneJournal(LocalTime.now().format(horloge), texte, erreur)
        _etat.update { it.copy(journal = (listOf(ligne) + it.journal).take(60)) }
    }
}

/** Ce que l'interface affiche du casque. */
data class EtatCasque(
    val adresse: String = "",
    val connecte: Boolean = false,
    val occupe: Boolean = false,
    val modele: String = "",
    val batterie: Int? = null,
    val application: String = "",
    val limiteActive: Boolean? = null,
    val servicesTestDisponibles: Boolean = false,
    val clePreAutorisee: Boolean = false,
    val journal: List<LigneJournal> = emptyList(),
)

/** Une ligne du journal d'actions. */
data class LigneJournal(
    val heure: String,
    val texte: String,
    val erreur: Boolean = false,
)
