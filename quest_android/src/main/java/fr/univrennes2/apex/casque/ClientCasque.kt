package fr.univrennes2.apex.casque

import android.content.Context
import com.flyfishxu.kadb.Kadb
import com.flyfishxu.kadb.cert.KadbCert
import java.io.Closeable
import java.io.File

/**
 * Connexion ADB au casque, sans binaire adb ni ordinateur intermédiaire.
 *
 * Le protocole ADB est du TCP : rien n'oblige le client à être un PC. Kadb en
 * fournit une implémentation Kotlin qui parle directement au démon `adbd` du
 * casque. La tablette peut donc jouer le rôle que tenait l'ordinateur.
 *
 * ## Les deux conditions à remplir
 *
 * **1. Le casque doit écouter sur le réseau.** Le démon n'accepte les
 * connexions TCP qu'après un `adb tcpip 5555`, donné une fois depuis un poste
 * relié en USB. Ce réglage **ne survit pas à un redémarrage du casque** : après
 * un arrêt complet, il faut le redonner. Une fois connecté, cette classe pose
 * `persist.adb.tcp.port`, ce qui le rétablit au démarrage sur une partie des
 * versions de firmware — sans garantie, le comportement varie.
 *
 * **2. La clé du client doit être reconnue.** À la première connexion d'une
 * clé inconnue, le casque affiche une demande d'autorisation *dans le casque* :
 * il faut donc que quelqu'un le porte, ce qu'on cherche précisément à éviter.
 *
 * La solution tient en une phrase : **réutiliser la clé du poste qui pilote
 * déjà le casque**. Elle est déjà autorisée, l'autorisation est liée à la clé
 * et non à la machine. Voir `outils/preparer_cle.py` et la section
 * « Provisionner la clé » du README.
 */
class ClientCasque private constructor(
    private val kadb: Kadb,
    val adresse: String,
) : Closeable {

    companion object {

        /** Port du démon ADB une fois le casque passé en mode réseau. */
        const val PORT_ADB = 5555

        /** Nom du fichier de clé attendu dans les ressources de l'application. */
        const val NOM_CLE = "adbkey"

        /**
         * Installe l'identité ADB de l'application.
         *
         * À appeler **une fois au démarrage**, avant toute connexion. Deux
         * chemins possibles :
         *
         * - une clé fournie dans `assets/adbkey`, recopiée depuis le poste qui
         *   pilote déjà le casque : aucune autorisation à donner dans le
         *   casque, la connexion passe du premier coup ;
         * - aucune clé fournie : Kadb en génère une, et la première connexion
         *   demandera une autorisation à porter le casque.
         *
         * @return vrai si une clé pré-autorisée a été chargée.
         */
        @JvmStatic
        fun preparerIdentite(context: Context): Boolean {
            val cleFournie = runCatching {
                context.assets.open(NOM_CLE).use { it.readBytes() }
            }.getOrNull()

            if (cleFournie != null && cleFournie.isNotEmpty()) {
                // `adbkey` est une clé privée PKCS#8 au format PEM : c'est
                // exactement ce qu'attend Kadb. Le certificat est régénéré à
                // partir d'elle, seule la clé compte pour l'autorisation.
                KadbCert.importPrivateKey(cleFournie)
                return true
            }
            KadbCert.ensureReady()
            return false
        }

        /**
         * Ouvre une connexion vers le casque.
         *
         * @param adresse adresse IP du casque sur le réseau local.
         * @throws CasqueInjoignable si la connexion n'aboutit pas.
         */
        @JvmStatic
        @JvmOverloads
        fun connecter(adresse: String, port: Int = PORT_ADB): ClientCasque {
            val kadb = try {
                Kadb.create(adresse, port)
            } catch (e: Exception) {
                throw CasqueInjoignable(
                    "Casque injoignable à $adresse:$port. Vérifiez qu'il est " +
                        "allumé, sur le même réseau, et qu'il a été passé en " +
                        "mode réseau (adb tcpip 5555) depuis un poste.",
                    e,
                )
            }
            return ClientCasque(kadb, adresse)
        }
    }

    /**
     * Exécute une commande shell sur le casque.
     *
     * Le code de retour ne suffit pas à juger du succès : `am` et `monkey`
     * signalent leurs échecs sur la sortie standard tout en rendant zéro. Le
     * texte est donc rendu tel quel, et c'est à l'appelant de le lire — ce que
     * fait [CasqueQuest].
     */
    fun shell(commande: String): ReponseShell {
        val reponse = try {
            kadb.shell(commande)
        } catch (e: Exception) {
            throw CasqueInjoignable("Connexion perdue pendant « $commande ».", e)
        }
        // Les trois champs attendus de la bibliothèque : `exitCode`, `output`,
        // `errorOutput`. Si une version future les renomme, c'est le seul
        // endroit à corriger.
        return ReponseShell(
            code = reponse.exitCode,
            sortie = reponse.output,
            erreur = reponse.errorOutput,
        )
    }

    /**
     * Demande au casque de continuer d'écouter après un redémarrage.
     *
     * Effet variable selon la version de firmware : à considérer comme un
     * bonus, jamais comme un acquis. Le README explique la marche à suivre
     * quand le casque revient d'un arrêt complet.
     */
    fun tenterPersistanceReseau() {
        runCatching { shell("setprop persist.adb.tcp.port $PORT_ADB") }
    }

    override fun close() {
        runCatching { kadb.close() }
    }
}

/** Résultat d'une commande shell. */
data class ReponseShell(
    val code: Int,
    val sortie: String,
    val erreur: String,
) {
    val texte: String get() = (sortie + " " + erreur).trim()
    val ok: Boolean get() = code == 0
}

/** Le casque n'a pas répondu. */
class CasqueInjoignable(message: String, cause: Throwable? = null) :
    Exception(message, cause)

/** Le casque a répondu, mais l'opération a échoué. */
class OperationRefusee(message: String) : Exception(message)
