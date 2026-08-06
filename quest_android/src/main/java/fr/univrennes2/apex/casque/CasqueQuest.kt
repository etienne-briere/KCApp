package fr.univrennes2.apex.casque

/**
 * Les commandes de séance, telles qu'elles sont données au casque.
 *
 * Transposition fidèle de `quest_control/quest.py`, l'outil Python utilisé
 * depuis le poste investigateur. Les commandes shell sont **identiques**, y
 * compris la détection des échecs : les deux implémentations doivent se
 * comporter pareil, sans quoi un incident survenu sur la tablette ne serait
 * pas reproductible depuis l'ordinateur, et inversement.
 *
 * ## Ce qui compte, et pourquoi
 *
 * **La limite de jeu est désactivée avant chaque séance.** Le participant est
 * assis au bord du lit ou dans un fauteuil, l'investigateur est présent,
 * l'amplitude du geste ne dépasse pas la longueur des bras : le risque dont la
 * limite protège — heurter un mur en se déplaçant — n'existe pas. En revanche,
 * une limite qui se déclenche en pleine séance affiche la grille, interrompt le
 * jeu, et la partie est perdue avec la mesure. Pour la qualité des données,
 * la supprimer est plus sûr que la maintenir.
 *
 * **Le capteur de proximité est leurré.** Le casque se met en veille dès qu'il
 * quitte la tête. Pendant la préparation — désinfection, réglage de la sangle,
 * lancement — il est posé sur la table : sans ce leurre, il s'endort et le jeu
 * ne démarre pas.
 *
 * **Un échec n'interrompt pas la suite.** Mieux vaut un casque partiellement
 * préparé et un message clair qu'un arrêt au premier obstacle, avec un
 * participant qui attend.
 */
class CasqueQuest(
    private val client: ClientCasque,
    private val paquetJeu: String = PAQUET_PAR_DEFAUT,
) {

    companion object {
        /**
         * Identifiant technique du jeu. Ce n'est **pas** le nom affiché dans le
         * casque : « APEX_experiment » à l'écran correspond à un identifiant de
         * la forme `com.VotreSociete.APEX`. C'est la confusion la plus fréquente
         * au premier lancement. [listerApplications] aide à le trouver.
         */
        const val PAQUET_PAR_DEFAUT = "com.DefaultCompany.APEX"

        /** Paquet système qui gère la limite de jeu. */
        const val PAQUET_LIMITE = "com.oculus.guardian"

        /** Fournisseur exposé par les services de test de Horizon OS v44+. */
        const val URI_SERVICES_TEST = "content://com.oculus.rc"

        /**
         * Motifs d'échec à chercher dans la sortie.
         *
         * `am start` et `monkey` rendent zéro tout en écrivant leur échec sur
         * la sortie standard. Se fier au seul code de retour laisserait croire
         * que le jeu tourne alors que rien n'a démarré — et l'investigateur
         * tendrait le casque à un participant devant un écran d'accueil.
         */
        private val MOTIFS_ECHEC = listOf(
            "error", "exception", "aborted", "no activities found",
            "events injected: 0", "does not exist",
        )

        /** Valeurs de propriété qui ne nomment rien. */
        private val MODELES_VIDES = setOf("", "unknown", "none", "null", "n/a")
    }

    // -- état ---------------------------------------------------------------

    /** Niveau de batterie, en pourcentage. */
    fun batterie(): Int? {
        val reponse = client.shell("dumpsys battery | grep level")
        return Regex("level:\\s*(\\d+)").find(reponse.texte)?.groupValues?.get(1)?.toIntOrNull()
    }

    /** Modèle du casque. */
    fun modele(): String =
        client.shell("getprop ro.product.model").sortie.trim()

    /** Application actuellement au premier plan. */
    fun applicationActive(): String {
        val reponse = client.shell(
            "dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity'"
        )
        return Regex("([A-Za-z0-9_.]+)/[A-Za-z0-9_.]+")
            .find(reponse.texte)?.groupValues?.get(1).orEmpty()
    }

    /** Applications installées, filtrées par un fragment de nom. */
    fun listerApplications(filtre: String = ""): List<String> {
        // « -3 » restreint aux applications installées par l'utilisateur : la
        // liste complète d'un casque compte plusieurs centaines de paquets
        // système, où le jeu se perd. Même filtre que côté Python.
        val reponse = client.shell("pm list packages -3")
        return reponse.sortie.lineSequence()
            .mapNotNull { it.trim().removePrefix("package:").ifBlank { null } }
            .filter { filtre.isBlank() || it.contains(filtre, ignoreCase = true) }
            .sorted()
            .toList()
    }

    /**
     * Cherche l'identifiant du jeu parmi les applications installées.
     *
     * Rend `null` si aucun candidat unique ne se dégage : choisir à la place de
     * l'investigateur reviendrait à lancer une autre application sans le dire.
     */
    fun devinerPaquetJeu(): String? {
        val candidats = listerApplications("apex")
        return candidats.singleOrNull()
    }

    // -- limite de jeu -------------------------------------------------------

    /**
     * La limite de jeu est-elle active ?
     *
     * Deux leviers coexistent et sont **indépendants** : la propriété système
     * `debug.oculus.guardian_pause`, et la propriété `disable_guardian` des
     * services de test. N'en interroger qu'un annoncerait une limite désactivée
     * alors qu'elle ne l'est pas — et la séance s'interromprait quand même.
     */
    fun limiteActive(): EtatLimite {
        val propriete = client.shell("getprop debug.oculus.guardian_pause")
            .sortie.trim() == "1"

        val officiel = client.shell(
            "content call --uri $URI_SERVICES_TEST --method GET_PROPERTY"
        ).texte.replace(" ", "")

        val servicesDisent = when {
            officiel.contains("disable_guardian=true") -> true
            officiel.contains("disable_guardian=false") -> false
            else -> null
        }

        return EtatLimite(
            active = !(propriete || servicesDisent == true),
            proprietePosee = propriete,
            servicesDisponibles = servicesDisent != null,
        )
    }

    /**
     * Active ou désactive la limite de jeu.
     *
     * Deux mécanismes tentés dans l'ordre :
     *
     * 1. les **services de test officiels** de Horizon OS v44+, voie documentée
     *    par Meta, qui exige un compte développeur connecté et son code PIN ;
     * 2. la propriété système `debug.oculus.guardian_pause`, qui fonctionne
     *    sans code PIN mais suspend aussi le passthrough — sans conséquence
     *    ici, le jeu s'affichant en environnement virtuel complet.
     *
     * Le second n'est pas un contournement du premier : un casque de
     * laboratoire n'est pas toujours provisionné avec un compte de test, et
     * c'est le cas courant.
     */
    fun definirLimite(active: Boolean, codePin: String = ""): List<String> {
        val journal = mutableListOf<String>()

        val valeur = if (active) "false" else "true"
        var commande = "content call --uri $URI_SERVICES_TEST --method SET_PROPERTY " +
            "--extra 'disable_guardian:b:$valeur'"
        if (codePin.isNotBlank()) commande += " --extra 'PIN:s:$codePin'"

        val officiel = client.shell(commande)
        val voieOfficielle = officiel.texte.contains("Success=true")
        journal += if (voieOfficielle) {
            "Services de test : appliqué"
        } else {
            "Services de test : indisponible" +
                if (codePin.isBlank()) " (aucun code PIN configuré)" else ""
        }

        val propriete = client.shell(
            "setprop debug.oculus.guardian_pause ${if (active) "0" else "1"}"
        )
        journal += if (propriete.ok) {
            "Propriété système : appliquée"
        } else {
            "Propriété système : refusée"
        }

        if (!voieOfficielle && !propriete.ok) {
            throw OperationRefusee(
                "La limite de jeu n'a pas pu être modifiée.\n" +
                    journal.joinToString("\n") +
                    "\n\nVérifiez que le mode développeur est actif sur le casque."
            )
        }
        return journal
    }

    /**
     * Efface la limite mémorisée : le casque en redemandera une au prochain port.
     *
     * Aucune commande ADB ne permet de *dessiner* une limite à distance — le
     * tracé est un geste, pas un réglage. Cette opération suppose donc que
     * quelqu'un mette le casque, ce qu'on cherche à éviter. À réserver aux cas
     * où l'on veut vraiment repartir de zéro.
     */
    fun effacerLimiteMemorisee() {
        val reponse = client.shell("pm clear $PAQUET_LIMITE")
        if (!reponse.texte.contains("Success")) {
            throw OperationRefusee(
                "Impossible d'effacer la limite mémorisée : ${reponse.texte}\n" +
                    "Passez par le casque : Paramètres > Limite > Effacer l'historique."
            )
        }
    }

    // -- veille et proximité --------------------------------------------------

    /** Sort le casque de veille. */
    fun reveiller() {
        client.shell("input keyevent KEYCODE_WAKEUP")
    }

    /**
     * Fait croire au casque qu'il est porté, ou qu'il ne l'est plus.
     *
     * @param porte vrai pour simuler le port, faux pour le retrait.
     */
    fun simulerPort(porte: Boolean) {
        val action = if (porte) "prox_close" else "prox_far"
        client.shell("am broadcast -a com.oculus.vrpowermanager.$action")
    }

    /** Neutralise la mise en veille automatique. */
    fun maintenirEveille(actif: Boolean): List<String> {
        val acceptees = mutableListOf<String>()
        val valeur = if (actif) "1" else "0"
        listOf(
            "settings put system screen_off_timeout ${if (actif) 1800000 else 60000}",
            "svc power stayon ${if (actif) "true" else "false"}",
            "setprop debug.oculus.suspendDisplay $valeur",
        ).forEach { commande ->
            val reponse = client.shell(commande)
            if (reponse.ok && !reponse.texte.contains("error", ignoreCase = true)) {
                acceptees += commande.substringBefore(" ")
            }
        }
        return acceptees
    }

    // -- jeu -----------------------------------------------------------------

    /** Démarre le jeu. */
    fun lancer(paquet: String = paquetJeu, activite: String = "") {
        val installees = listerApplications()
        if (installees.isNotEmpty() && paquet !in installees) {
            throw OperationRefusee(
                "L'application « $paquet » n'est pas installée sur ce casque.\n" +
                    "Applications trouvées :\n  " +
                    installees.take(15).joinToString("\n  ")
            )
        }

        val reponse = if (activite.isNotBlank()) {
            client.shell("am start -n $paquet/$activite")
        } else {
            client.shell("monkey -p $paquet -c android.intent.category.LAUNCHER 1")
        }

        val texte = reponse.texte.lowercase()
        if (!reponse.ok || MOTIFS_ECHEC.any { it in texte }) {
            throw OperationRefusee(
                "Lancement impossible : ${reponse.texte}\n" +
                    "Si l'application est bien installée, précisez son activité " +
                    "de lancement, par exemple com.unity3d.player.UnityPlayerActivity."
            )
        }
    }

    /** Arrête le jeu. */
    fun arreter(paquet: String = paquetJeu) {
        client.shell("am force-stop $paquet")
    }

    // -- enchaînement complet -------------------------------------------------

    /**
     * Prépare le casque pour une séance, dans l'ordre du soin.
     *
     * Chaque étape est rapportée, et son échec n'interrompt pas les suivantes.
     * Le résultat dit ce qui a marché et ce qui n'a pas marché : à
     * l'investigateur de juger si le casque est utilisable, plutôt qu'à
     * l'application de décider à sa place.
     */
    fun preparerSeance(
        codePin: String = "",
        desactiverLimite: Boolean = true,
        lancerLeJeu: Boolean = true,
        paquet: String = paquetJeu,
    ): List<EtapePreparation> {
        val etapes = mutableListOf<EtapePreparation>()

        fun etape(libelle: String, action: () -> Unit) {
            etapes += try {
                action()
                EtapePreparation(libelle, true)
            } catch (e: Exception) {
                EtapePreparation(libelle, false, e.message?.lineSequence()?.first().orEmpty())
            }
        }

        etape("Réveil de l'appareil") { reveiller() }
        etape("Capteur de proximité neutralisé") { simulerPort(true) }
        etape("Veille automatique neutralisée") { maintenirEveille(true) }
        if (desactiverLimite) {
            etape("Limite de jeu désactivée") { definirLimite(false, codePin) }
        }
        if (lancerLeJeu) {
            etape("Jeu lancé") { lancer(paquet) }
        }
        return etapes
    }
}

/** État de la limite de jeu, tel que les deux leviers le décrivent. */
data class EtatLimite(
    val active: Boolean,
    val proprietePosee: Boolean,
    val servicesDisponibles: Boolean,
)

/** Une étape de préparation et son issue. */
data class EtapePreparation(
    val libelle: String,
    val reussie: Boolean,
    val detail: String = "",
)
