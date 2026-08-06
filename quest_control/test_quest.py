# -*- coding: utf-8 -*-
"""
Tests du pilotage du casque, sans casque.

Le module dialogue avec ADB, qui n'est pas disponible ici et ne le sera pas non
plus sur le poste tant qu'un casque n'est pas branché. Ces tests substituent à
`adb` un script qui reproduit ses sorties réelles — y compris les cas d'échec
que l'on rencontre le plus souvent sur le terrain : casque non autorisé,
application absente, dossier de données introuvable.

Les sorties simulées sont recopiées de sessions ADB réelles sur Meta Quest.

Exécution :  python quest_control/test_quest.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ICI = Path(__file__).resolve().parent
if str(ICI) not in sys.path:
    sys.path.insert(0, str(ICI))

from quest import ErreurAdb, Quest  # noqa: E402


# ---------------------------------------------------------------------------
# Faux adb — la fabrique vit dans quest_control/simulateur.py, parce qu'elle
# sert aussi hors des tests : `--simulateur` permet de parcourir l'interface
# sans matériel.
# ---------------------------------------------------------------------------

from simulateur import creer_faux_adb  # noqa: E402


class BaseQuest(unittest.TestCase):
    scenario = "normal"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="apex_quest_"))
        self.adb = creer_faux_adb(self.tmp, self.scenario)
        # Chaque test part d'un casque dans son état d'usine.
        (self.tmp / "_etat_casque.json").unlink(missing_ok=True)
        self.quest = Quest({
            "adb": str(self.adb),
            "package": "com.DefaultCompany.APEX",
            "activite": "",
            "dossiers_donnees": ["/sdcard/Android/data/{package}/files"],
            "destination_import": str(self.tmp / "recup"),
            "port_wifi": 5555,
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------

class TestDetection(BaseQuest):

    def test_casque_detecte(self):
        appareils = self.quest.appareils()
        self.assertEqual(len(appareils), 1)
        self.assertEqual(appareils[0]["etat"], "device")
        self.assertEqual(appareils[0]["modele"], "Quest 2")
        self.assertFalse(appareils[0]["wifi"])

    def test_connecte(self):
        self.assertTrue(self.quest.connecte())

    def test_adb_introuvable(self):
        quest = Quest({"adb": "/chemin/qui/nexiste/pas/adb"})
        with self.assertRaises(ErreurAdb) as ctx:
            quest.appareils()
        self.assertIn("adb est introuvable", str(ctx.exception))
        self.assertIn("Platform Tools", str(ctx.exception),
                      "le message doit dire comment installer adb")


class TestAucunCasque(BaseQuest):
    scenario = "absent"

    def test_aucun_appareil(self):
        self.assertEqual(self.quest.appareils(), [])
        self.assertFalse(self.quest.connecte())

    def test_message_explicite(self):
        with self.assertRaises(ErreurAdb) as ctx:
            self.quest.verifier_connexion()
        message = str(ctx.exception)
        self.assertIn("Aucun casque détecté", message)
        self.assertIn("connecter --ip", message,
                      "le message doit indiquer la marche à suivre")


class TestNonAutorise(BaseQuest):
    scenario = "non_autorise"

    def test_casque_non_autorise(self):
        with self.assertRaises(ErreurAdb) as ctx:
            self.quest.verifier_connexion()
        message = str(ctx.exception)
        self.assertIn("non autorisé", message)
        self.assertIn("débogage USB", message,
                      "le message doit expliquer l'action à faire dans le casque")


class TestEtat(BaseQuest):

    def test_batterie(self):
        self.assertEqual(self.quest.batterie(), 73)

    def test_modele(self):
        self.assertEqual(self.quest.modele(), "Quest 2")

    def test_paquets(self):
        paquets = self.quest.paquets()
        self.assertIn("com.DefaultCompany.APEX", paquets)
        self.assertIn("com.oculus.browser", paquets)

    def test_filtre_paquets(self):
        self.assertEqual(self.quest.paquets("apex"), ["com.DefaultCompany.APEX"])

    def test_application_active(self):
        actif = self.quest.application_active()
        self.assertIn("com.DefaultCompany.APEX", actif)

    def test_etat_complet(self):
        etat = self.quest.etat()
        self.assertEqual(etat["batterie"], 73)
        self.assertEqual(etat["liaison"], "USB")
        self.assertTrue(etat["jeu_installe"])

    def test_adresse_ip(self):
        self.assertEqual(self.quest.adresse_ip(), "192.168.1.42")


class TestWifi(BaseQuest):

    def test_activation_wifi(self):
        cible = self.quest.activer_wifi()
        self.assertEqual(cible, "192.168.1.42:5555")
        self.assertEqual(self.quest.config["derniere_ip"], "192.168.1.42")

    def test_connexion_ip_explicite(self):
        self.assertEqual(self.quest.connecter_wifi("192.168.1.99"),
                         "192.168.1.99:5555")

    def test_connexion_avec_port(self):
        self.assertEqual(self.quest.connecter_wifi("192.168.1.99:5555"),
                         "192.168.1.99:5555")


class TestWifiDetecte(BaseQuest):
    scenario = "wifi"

    def test_liaison_wifi_identifiee(self):
        self.assertTrue(self.quest.appareils()[0]["wifi"])
        self.assertEqual(self.quest.etat()["liaison"], "Wi-Fi")


class TestPilotage(BaseQuest):

    def test_lancer(self):
        self.assertEqual(self.quest.lancer(), "com.DefaultCompany.APEX")

    def test_arreter(self):
        self.assertEqual(self.quest.arreter(), "com.DefaultCompany.APEX")

    def test_reveiller(self):
        self.quest.reveiller()  # ne doit pas lever


class TestJeuAbsent(BaseQuest):
    scenario = "jeu_absent"

    def test_message_liste_les_applications(self):
        """Le message d'erreur doit permettre de trouver le bon identifiant."""
        with self.assertRaises(ErreurAdb) as ctx:
            self.quest.lancer()
        message = str(ctx.exception)
        self.assertIn("n'est pas installée", message)
        self.assertIn("com.autre.jeu", message,
                      "les applications présentes doivent être listées")
        self.assertIn("config.json", message)


class TestLancementEchoue(BaseQuest):
    scenario = "lancement_echoue"

    def test_echec_signale(self):
        with self.assertRaises(ErreurAdb):
            self.quest.lancer()


class TestRecuperation(BaseQuest):

    def test_localiser_donnees(self):
        dossiers = self.quest.localiser_donnees()
        self.assertEqual(dossiers,
                         ["/sdcard/Android/data/com.DefaultCompany.APEX/files"])

    def test_lister_sessions(self):
        sessions = self.quest.lister_sessions()
        self.assertEqual(len(sessions), 2)
        self.assertTrue(all(s.endswith(("partie1", "partie2")) for s in sessions))

    def test_recuperer(self):
        rapport = self.quest.recuperer(destination=self.tmp / "recup",
                                       participant="apex_001")
        self.assertEqual(len(rapport["recuperes"]), 2)
        self.assertEqual(rapport["echecs"], [])

        cible = Path(rapport["destination"])
        self.assertTrue(cible.exists())
        self.assertIn("APEX_001", cible.name,
                      "le code participant doit apparaître dans le nom du dossier")

        fichiers = list(cible.rglob("CSV_OptionsGame.csv"))
        self.assertEqual(len(fichiers), 2)

    def test_dossier_recupere_est_importable(self):
        """
        Le dossier produit doit être directement sélectionnable dans
        l'application web : il doit contenir le marqueur de partie.
        """
        rapport = self.quest.recuperer(destination=self.tmp / "recup")
        racine = Path(rapport["destination"])

        sys.path.insert(0, str(ICI.parent))
        from web_app.services.imports import detecter_dossiers_parties

        detectes = detecter_dossiers_parties(racine)
        self.assertEqual(len(detectes), 2,
                         "l'import de l'application web doit reconnaître les parties")


class TestSansDonnees(BaseQuest):
    scenario = "sans_donnees"

    def test_message_indique_les_emplacements(self):
        with self.assertRaises(ErreurAdb) as ctx:
            self.quest.recuperer()
        message = str(ctx.exception)
        self.assertIn("Aucun dossier de session", message)
        self.assertIn("/sdcard/Android/data", message,
                      "les emplacements explorés doivent figurer dans le message")
        self.assertIn("config.json", message)



# ---------------------------------------------------------------------------
# Ajouts : veille et diagnostic
# ---------------------------------------------------------------------------

class TestVeille(BaseQuest):
    """
    Le casque se met en veille dès qu'il n'est plus porté. Sans neutralisation,
    lancer le jeu avant de le poser sur la tête du participant n'a pas d'effet
    utile : c'est le cœur du besoin exprimé.
    """

    def test_methodes_acceptees(self):
        acceptees = self.quest.maintenir_eveille(True)
        self.assertTrue(acceptees, "au moins une méthode doit être tentée")

    def test_reactivation(self):
        self.quest.maintenir_eveille(False)  # ne doit pas lever


class TestDiagnostic(BaseQuest):

    def test_tout_vert(self):
        etapes = self.quest.diagnostic()
        titres = [e["titre"] for e in etapes]
        self.assertIn("ADB installé", titres)
        self.assertIn("Jeu APEX installé", titres)
        self.assertIn("Dossier de données trouvé", titres)
        self.assertTrue(all(e["ok"] for e in etapes),
                        [e["titre"] for e in etapes if not e["ok"]])

    def test_arret_si_adb_absent(self):
        quest = Quest({"adb": "/introuvable/adb"})
        etapes = quest.diagnostic()
        self.assertEqual(len(etapes), 1, "inutile de poursuivre sans adb")
        self.assertFalse(etapes[0]["ok"])
        self.assertIn("Platform Tools", etapes[0]["remede"])


class TestDiagnosticJeuAbsent(BaseQuest):
    scenario = "jeu_absent"

    def test_remede_indique_la_commande(self):
        etapes = {e["titre"]: e for e in self.quest.diagnostic()}
        jeu = etapes["Jeu APEX installé"]
        self.assertFalse(jeu["ok"])
        self.assertIn("com.autre.jeu", jeu["detail"],
                      "les applications présentes doivent aider à trouver le bon id")
        self.assertIn("configurer --package", jeu["remede"])


class TestDiagnosticNonAutorise(BaseQuest):
    scenario = "non_autorise"

    def test_arret_et_remede(self):
        etapes = self.quest.diagnostic()
        dernier = etapes[-1]
        self.assertFalse(dernier["ok"])
        self.assertIn("débogage USB", dernier["remede"])
        self.assertIn("mode développeur", dernier["remede"])


class TestDiagnosticSansDonnees(BaseQuest):
    scenario = "sans_donnees"

    def test_remede_donne_la_commande_de_recherche(self):
        etapes = {e["titre"]: e for e in self.quest.diagnostic()}
        d = etapes["Dossier de données trouvé"]
        self.assertFalse(d["ok"])
        self.assertIn("CSV_OptionsGame.csv", d["remede"],
                      "le remède doit donner la commande pour localiser les CSV")



class TestLimiteDeJeu(BaseQuest):
    """
    La limite de jeu est le principal risque d'interruption d'une séance : si
    elle se déclenche, la grille s'affiche, le jeu s'arrête, et la mesure est
    perdue. En position assise, avec l'investigateur présent, elle ne protège
    de rien — la désactiver est plus sûr pour les données que la maintenir.
    """

    def test_etat_limite_active_par_defaut(self):
        etat = self.quest.limite_etat()
        self.assertTrue(etat["active"])
        self.assertTrue(etat["services_disponibles"])

    def test_desactiver_change_vraiment_l_etat(self):
        """
        Le test qui compte : après désactivation, le casque doit *dire* que la
        limite est désactivée. Vérifier qu'une commande a été envoyée ne
        prouverait rien.
        """
        self.assertTrue(self.quest.limite_etat()["active"])
        self.quest.limite_definir(False)
        self.assertFalse(self.quest.limite_etat()["active"])

    def test_aller_retour(self):
        self.quest.limite_definir(False)
        self.assertFalse(self.quest.limite_etat()["active"])
        self.quest.limite_definir(True)
        self.assertTrue(self.quest.limite_etat()["active"],
                        "la limite doit pouvoir être rétablie")

    def test_les_deux_leviers_sont_posés(self):
        """
        Propriété système et services officiels sont indépendants. N'en poser
        qu'un laisserait la limite active par l'autre chemin, sans que rien ne
        le signale.
        """
        self.quest.config["pin_store"] = "1234"
        self.quest.limite_definir(False)
        etat = self.quest.limite_etat()
        self.assertTrue(etat["pause_propriete"])
        self.assertIs(etat["desactivee_services"], True)

    def test_desactivation_avec_pin(self):
        self.quest.config["pin_store"] = "1234"
        resultat = self.quest.limite_definir(False)
        self.assertFalse(resultat["active"])
        self.assertTrue(resultat["voie_officielle"],
                        "avec un PIN, la voie officielle doit aboutir")

    def test_desactivation_sans_pin_passe_par_la_propriete(self):
        """
        Un casque de laboratoire n'est pas toujours provisionné avec un compte
        de test. Le repli n'est pas un contournement : c'est le cas courant.
        """
        self.quest.config["pin_store"] = ""
        resultat = self.quest.limite_definir(False)
        self.assertFalse(resultat["voie_officielle"])
        self.assertTrue(any("Propriété système : appliquée" in l
                            for l in resultat["journal"]), resultat["journal"])

    def test_reactivation(self):
        resultat = self.quest.limite_definir(True)
        self.assertTrue(resultat["active"])

    def test_redefinir_efface_le_trace(self):
        self.assertEqual(self.quest.limite_redefinir(), "com.oculus.guardian")

    def test_simuler_le_port(self):
        self.assertEqual(self.quest.simuler_port(True), "prox_close")
        self.assertEqual(self.quest.simuler_port(False), "prox_far")


class TestLimiteSansServicesDeTest(BaseQuest):
    """Casque non provisionné : les services officiels sont muets."""
    scenario = "sans_services_test"

    def test_etat_signale_l_indisponibilite(self):
        etat = self.quest.limite_etat()
        self.assertFalse(etat["services_disponibles"])
        self.assertIsNone(etat["desactivee_services"])

    def test_desactivation_reussit_quand_meme(self):
        resultat = self.quest.limite_definir(False)
        self.assertFalse(resultat["voie_officielle"])
        self.assertFalse(resultat["active"])


class TestLimiteEchecComplet(BaseQuest):
    """
    Les deux voies échouent : il faut le dire, pas laisser croire que la
    limite est désactivée. Un faux positif ici, c'est une séance interrompue
    au milieu et une mesure perdue.
    """
    scenario = "setprop_refuse"

    def test_echec_explicite(self):
        self.quest.config["pin_store"] = ""
        with self.assertRaises(ErreurAdb) as ctx:
            self.quest.limite_definir(False)
        self.assertIn("PIN", str(ctx.exception))


class TestRedefinirRefuse(BaseQuest):
    scenario = "clear_refuse"

    def test_message_oriente_vers_le_casque(self):
        with self.assertRaises(ErreurAdb) as ctx:
            self.quest.limite_redefinir()
        self.assertIn("Paramètres", str(ctx.exception))


class TestPreparation(BaseQuest):
    """
    L'enchaînement complet avant de tendre le casque. Ce qui compte n'est pas
    qu'il réussisse toujours, mais qu'il aille au bout : une étape ratée ne
    doit pas priver l'investigateur des suivantes, avec un participant qui
    attend.
    """

    def test_enchainement_complet(self):
        self.quest.config["pin_store"] = "1234"
        self.quest.reveiller()
        self.assertEqual(self.quest.simuler_port(True), "prox_close")
        self.assertTrue(self.quest.maintenir_eveille(True))
        self.assertFalse(self.quest.limite_definir(False)["active"])
        self.assertEqual(self.quest.lancer(), "com.DefaultCompany.APEX")


class TestConfigurationPreservee(unittest.TestCase):
    """
    Une configuration passée explicitement ne doit jamais être réécrite sur
    disque : les tests ne peuvent pas altérer la configuration du poste.
    """

    def test_config_reelle_intacte(self):
        import quest as module
        avant = module.CONFIG_PATH.read_text(encoding="utf-8") \
            if module.CONFIG_PATH.exists() else None

        tmp = Path(tempfile.mkdtemp(prefix="apex_cfg_"))
        try:
            adb = creer_faux_adb(tmp, "normal")
            q = Quest({"adb": str(adb), "package": "x", "activite": "",
                       "dossiers_donnees": [], "port_wifi": 5555})
            q.connecter_wifi("10.0.0.1")

            apres = module.CONFIG_PATH.read_text(encoding="utf-8") \
                if module.CONFIG_PATH.exists() else None
            self.assertEqual(avant, apres,
                             "config.json ne doit pas être modifié par les tests")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestTelecommande(unittest.TestCase):
    """
    La page servie au téléphone pilote un appareil médical posé sur la tête
    d'un patient. Trois exigences : personne ne commande sans le jeton, une
    action ne s'exécute pas deux fois en parallèle, et une panne du casque
    renvoie un message plutôt qu'une page morte.
    """

    @classmethod
    def setUpClass(cls):
        import telecommande
        cls.T = telecommande

    def setUp(self):
        import threading
        self.tmp = Path(tempfile.mkdtemp(prefix="apex_tc_"))
        (self.tmp / "_etat_casque.json").unlink(missing_ok=True)
        adb = creer_faux_adb(self.tmp, getattr(self, "scenario", "normal"))
        self.T.Handler.quest = Quest({
            "adb": str(adb), "package": "com.DefaultCompany.APEX", "activite": "",
            "dossiers_donnees": ["/sdcard/Android/data/{package}/files"],
            "destination_import": str(self.tmp / "recup"),
            "port_wifi": 5555, "pin_store": "1234",
        })
        self.serveur = self.T.Serveur(("127.0.0.1", 0), self.T.Handler)
        self.port = self.serveur.server_address[1]
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()

    def tearDown(self):
        self.serveur.shutdown()
        self.serveur.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- utilitaires -------------------------------------------------------

    def get(self, chemin):
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}{chemin}", timeout=20) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def post(self, nom, jeton=None):
        import json as _json
        import urllib.error
        import urllib.request
        jeton = self.T.JETON if jeton is None else jeton
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/action?jeton={jeton}&nom={nom}",
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, _json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, _json.loads(exc.read().decode("utf-8"))

    # -- accès -------------------------------------------------------------

    def test_page_refusee_sans_jeton(self):
        self.assertEqual(self.get("/")[0], 403)

    def test_page_servie_avec_jeton(self):
        code, corps = self.get(f"/?jeton={self.T.JETON}")
        self.assertEqual(code, 200)
        self.assertIn("Préparer la séance", corps)

    def test_action_refusee_avec_mauvais_jeton(self):
        code, r = self.post("arreter", jeton="pas-le-bon")
        self.assertEqual(code, 403)
        self.assertFalse(r["ok"])

    def test_jeton_assez_long(self):
        """Un jeton court se devinerait par balayage depuis le même réseau."""
        self.assertGreaterEqual(len(self.T.JETON), 10)

    def test_action_inconnue_rejetee(self):
        code, r = self.post("effacer_tout")
        self.assertEqual(code, 400)
        self.assertFalse(r["ok"])

    # -- actions -----------------------------------------------------------

    def test_etat_renvoie_le_casque(self):
        code, r = self.post("etat")
        self.assertTrue(r["ok"])
        self.assertTrue(r["etat"]["connecte"])
        self.assertEqual(r["etat"]["batterie"], 73)

    def test_desactiver_la_limite_agit_vraiment(self):
        self.assertTrue(self.post("etat")[1]["etat"]["limite"])
        code, r = self.post("limite_desactiver")
        self.assertTrue(r["ok"], r.get("erreur"))
        self.assertFalse(r["etat"]["limite"],
                         "l'état renvoyé doit refléter le changement")

    def test_retablir_la_limite(self):
        self.post("limite_desactiver")
        code, r = self.post("limite_activer")
        self.assertTrue(r["ok"])
        self.assertTrue(r["etat"]["limite"])

    def test_lancer_et_arreter(self):
        self.assertTrue(self.post("lancer")[1]["ok"])
        self.assertTrue(self.post("arreter")[1]["ok"])

    def test_preparer_enchaine_tout(self):
        code, r = self.post("preparer")
        self.assertTrue(r["ok"], r.get("erreur"))
        self.assertEqual(len(r["messages"]), 5, r["messages"])
        self.assertTrue(all(m.startswith("OK") for m in r["messages"]), r["messages"])
        self.assertFalse(r["etat"]["limite"])

    def test_pas_de_double_execution(self):
        """
        Un écran tactile invite aux appuis répétés. Deux commandes ADB
        simultanées sur le même casque produiraient des résultats incohérents.
        """
        import threading
        resultats = []
        verrous = [threading.Thread(target=lambda: resultats.append(self.post("preparer")))
                   for _ in range(3)]
        for t in verrous:
            t.start()
        for t in verrous:
            t.join(timeout=60)
        self.assertEqual(len(resultats), 3)
        self.assertTrue(all(r[1]["ok"] for r in resultats),
                        [r[1].get("erreur") for r in resultats])


class TestTelecommandeCasqueAbsent(TestTelecommande):
    """Casque débranché : la page doit rester utilisable et le dire."""
    scenario = "absent"

    def test_page_servie_avec_jeton(self):
        code, corps = self.get(f"/?jeton={self.T.JETON}")
        self.assertEqual(code, 200)

    def test_etat_renvoie_le_casque(self):
        code, r = self.post("etat")
        self.assertTrue(r["ok"])
        self.assertFalse(r["etat"]["connecte"])
        self.assertIsNone(r["etat"]["batterie"])

    def test_desactiver_la_limite_agit_vraiment(self):
        code, r = self.post("limite_desactiver")
        self.assertFalse(r["ok"])
        self.assertTrue(r["erreur"], "un échec doit être expliqué")

    def test_retablir_la_limite(self):
        self.assertFalse(self.post("limite_activer")[1]["ok"])

    def test_lancer_et_arreter(self):
        self.assertFalse(self.post("lancer")[1]["ok"])

    def test_preparer_enchaine_tout(self):
        code, r = self.post("preparer")
        self.assertFalse(r["ok"])
        self.assertIn("échec", r["erreur"].lower())

    def test_pas_de_double_execution(self):
        self.skipTest("sans casque, la concurrence n'a rien à protéger")



if __name__ == "__main__":
    unittest.main(verbosity=2)
