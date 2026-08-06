# -*- coding: utf-8 -*-
"""
APEX Quest Control — pilotage du casque Meta Quest depuis le poste.

Objectif : ne plus toucher au casque une fois qu'il est désinfecté et posé sur
la tête du participant. Tout se pilote depuis l'ordinateur — lancement du jeu,
arrêt, récupération des données de séance.

Ce module s'appuie sur ADB (Android Debug Bridge), l'outil officiel de
communication avec un appareil Android. Le Quest en est un.

    python quest_control/quest.py diagnostic
    python quest_control/quest.py connecter --ip 192.168.1.42
    python quest_control/quest.py preparer          <- avant chaque séance
    python quest_control/quest.py limite etat
    python quest_control/quest.py arreter
    python quest_control/quest.py recuperer --participant APEX_001

`preparer` enchaîne tout ce qu'il faut faire avant de tendre le casque :
réveil, neutralisation du capteur de proximité et de la veille, désactivation
de la limite de jeu, lancement du jeu. Une seule commande, casque posé sur la
table, désinfecté, jamais remis sur le nez de l'investigateur.

Prérequis, à faire une seule fois par casque : activer le mode développeur
depuis l'application mobile Meta Quest, puis autoriser le débogage USB lors du
premier branchement. Voir quest_control/README.md.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
from console import configurer_console  # noqa: E402

configurer_console()

RACINE = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

#: Configuration par défaut. Écrasée par config.json s'il existe.
DEFAUT = {
    "package": "com.DefaultCompany.APEX",
    "activite": "",
    "dossiers_donnees": [
        "/sdcard/Android/data/{package}/files",
        "/sdcard/APEX",
        "/sdcard/Download/APEX",
    ],
    "destination_import": "quest_control/donnees_recuperees",
    "adb": "adb",
    "port_wifi": 5555,
    # Code PIN Store du compte connecté sur le casque. Requis par les services
    # de test officiels de Horizon OS pour modifier la limite de jeu. Sans lui,
    # l'application se rabat sur la propriété système, qui suffit en pratique.
    "pin_store": "",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def charger_config() -> dict:
    config = dict(DEFAUT)
    if CONFIG_PATH.exists():
        try:
            config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            print(f"config.json illisible ({exc}), valeurs par défaut utilisées.")
    return config


def enregistrer_config(config: dict, chemin: Optional[Path] = None) -> None:
    (chemin or CONFIG_PATH).write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Couche ADB
# ---------------------------------------------------------------------------

class ErreurAdb(RuntimeError):
    pass


@dataclass
class Resultat:
    code: int
    sortie: str
    erreur: str

    @property
    def ok(self) -> bool:
        return self.code == 0


class Quest:
    """Interface avec un casque Meta Quest via ADB."""

    def __init__(self, config: Optional[dict] = None,
                 chemin_config: Optional[Path] = None):
        # Une configuration passée explicitement n'est jamais réécrite sur
        # disque tant que chemin_config n'est pas fourni : les tests ne doivent
        # pas polluer la configuration réelle du poste.
        self.config = config or charger_config()
        self.chemin_config = chemin_config or (CONFIG_PATH if config is None else None)
        self.adb = self.config.get("adb", "adb")

    def _sauver_config(self) -> None:
        if self.chemin_config is not None:
            enregistrer_config(self.config, self.chemin_config)

    # -- primitives --------------------------------------------------------

    def _executer(self, args: List[str], timeout: int = 120) -> Resultat:
        if shutil.which(self.adb) is None:
            raise ErreurAdb(
                "adb est introuvable. Installez les « SDK Platform Tools » "
                "d'Android, ou renseignez le chemin complet de adb dans "
                "quest_control/config.json."
            )
        try:
            r = subprocess.run([self.adb] + args, capture_output=True,
                               text=True, timeout=timeout)
            return Resultat(r.returncode, r.stdout.strip(), r.stderr.strip())
        except subprocess.TimeoutExpired:
            return Resultat(1, "", f"Délai dépassé ({timeout} s)")

    def shell(self, commande: str, timeout: int = 60) -> Resultat:
        return self._executer(["shell", commande], timeout)

    # -- connexion ---------------------------------------------------------

    def appareils(self) -> List[dict]:
        """Liste les appareils vus par ADB."""
        r = self._executer(["devices", "-l"], timeout=20)
        appareils = []
        for ligne in r.sortie.splitlines()[1:]:
            if not ligne.strip():
                continue
            morceaux = ligne.split()
            serie, etat = morceaux[0], morceaux[1]
            modele = ""
            for m in morceaux[2:]:
                if m.startswith("model:"):
                    modele = m.split(":", 1)[1].replace("_", " ")
            appareils.append({
                "serie": serie,
                "etat": etat,
                "modele": modele,
                "wifi": ":" in serie,
            })
        return appareils

    def connecte(self) -> bool:
        return any(a["etat"] == "device" for a in self.appareils())

    def verifier_connexion(self) -> None:
        appareils = self.appareils()
        if not appareils:
            raise ErreurAdb(
                "Aucun casque détecté. Branchez le câble USB, ou connectez-vous "
                "en Wi-Fi avec :  python quest_control/quest.py connecter --ip <adresse>"
            )
        non_autorises = [a for a in appareils if a["etat"] == "unauthorized"]
        if non_autorises and not self.connecte():
            raise ErreurAdb(
                "Casque détecté mais non autorisé. Mettez le casque et acceptez "
                "la demande « Autoriser le débogage USB » qui s'y affiche."
            )
        if not self.connecte():
            etats = ", ".join(f"{a['serie']} ({a['etat']})" for a in appareils)
            raise ErreurAdb(f"Casque non prêt : {etats}")

    def adresse_ip(self) -> Optional[str]:
        """Adresse IP du casque sur le réseau Wi-Fi."""
        r = self.shell("ip route", timeout=20)
        m = re.search(r"src\s+(\d+\.\d+\.\d+\.\d+)", r.sortie)
        if m:
            return m.group(1)
        r = self.shell("ip addr show wlan0", timeout=20)
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", r.sortie)
        return m.group(1) if m else None

    def activer_wifi(self, ip: Optional[str] = None) -> str:
        """
        Bascule la connexion ADB sur le Wi-Fi.

        À faire une fois, casque branché en USB. Ensuite le câble peut être
        retiré : le casque reste pilotable tant qu'il est allumé et sur le
        même réseau.
        """
        self.verifier_connexion()
        port = self.config.get("port_wifi", 5555)

        if ip is None:
            ip = self.adresse_ip()
            if not ip:
                raise ErreurAdb(
                    "Adresse IP du casque introuvable. Vérifiez qu'il est "
                    "connecté au Wi-Fi, ou passez --ip explicitement."
                )

        r = self._executer(["tcpip", str(port)], timeout=30)
        if not r.ok:
            raise ErreurAdb(f"Passage en mode TCP impossible : {r.erreur}")

        time.sleep(2)
        cible = f"{ip}:{port}"
        r = self._executer(["connect", cible], timeout=30)
        if "connected" not in r.sortie.lower():
            raise ErreurAdb(f"Connexion à {cible} impossible : {r.sortie} {r.erreur}")

        self.config["derniere_ip"] = ip
        self._sauver_config()
        return cible

    def connecter_wifi(self, ip: str) -> str:
        port = self.config.get("port_wifi", 5555)
        cible = ip if ":" in ip else f"{ip}:{port}"
        r = self._executer(["connect", cible], timeout=30)
        if "connected" not in r.sortie.lower():
            raise ErreurAdb(f"Connexion à {cible} impossible : {r.sortie} {r.erreur}")
        self.config["derniere_ip"] = cible.split(":")[0]
        self._sauver_config()
        return cible

    # -- état du casque ----------------------------------------------------

    def batterie(self) -> Optional[int]:
        r = self.shell("dumpsys battery | grep level", timeout=20)
        m = re.search(r"level:\s*(\d+)", r.sortie)
        return int(m.group(1)) if m else None

    def modele(self) -> str:
        return self.shell("getprop ro.product.model", timeout=20).sortie or "inconnu"

    def paquets(self, filtre: str = "") -> List[str]:
        """Liste les applications installées, éventuellement filtrées."""
        commande = "pm list packages -3"
        r = self.shell(commande, timeout=40)
        noms = [l.replace("package:", "").strip() for l in r.sortie.splitlines()
                if l.startswith("package:")]
        if filtre:
            noms = [n for n in noms if filtre.lower() in n.lower()]
        return sorted(noms)

    def application_active(self) -> str:
        r = self.shell(
            "dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity'",
            timeout=30)
        m = re.search(r"([a-zA-Z0-9_.]+)/([a-zA-Z0-9_.]+)", r.sortie)
        return m.group(0) if m else ""

    def etat(self) -> dict:
        self.verifier_connexion()
        appareil = next(a for a in self.appareils() if a["etat"] == "device")
        return {
            "serie": appareil["serie"],
            "liaison": "Wi-Fi" if appareil["wifi"] else "USB",
            "modele": self.modele(),
            "batterie": self.batterie(),
            "application_active": self.application_active(),
            "jeu_installe": self.config["package"] in self.paquets(),
        }

    # -- pilotage du jeu ---------------------------------------------------

    def lancer(self, package: Optional[str] = None) -> str:
        """
        Démarre le jeu sur le casque.

        Le participant n'a plus qu'à mettre le casque : l'application est déjà
        au premier plan.
        """
        self.verifier_connexion()
        package = package or self.config["package"]

        if package not in self.paquets():
            installees = self.paquets()
            raise ErreurAdb(
                f"L'application « {package} » n'est pas installée sur ce casque.\n"
                "Applications trouvées :\n  "
                + "\n  ".join(installees[:20] if installees else ["(aucune)"])
                + "\n\nCorrigez « package » dans quest_control/config.json."
            )

        activite = self.config.get("activite", "")
        if activite:
            r = self.shell(f"am start -n {package}/{activite}", timeout=40)
        else:
            # Laisse Android résoudre l'activité de lancement déclarée.
            r = self.shell(
                f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
                timeout=40)

        # `monkey` et `am start` signalent leurs échecs sur la sortie standard
        # avec un code de retour nul : se fier au seul code de retour laisserait
        # croire que le jeu tourne alors que rien n'a démarré.
        echecs = ("error", "exception", "aborted", "no activities found",
                  "events injected: 0", "does not exist")
        sortie = (r.sortie + " " + r.erreur).lower()
        if not r.ok or any(motif in sortie for motif in echecs):
            raise ErreurAdb(
                f"Lancement impossible : {r.sortie or r.erreur}\n"
                "Si l'application est bien installée, précisez son activité de "
                "lancement dans quest_control/config.json (champ « activite »), "
                "par exemple com.unity3d.player.UnityPlayerActivity."
            )

        time.sleep(2)
        return package

    def arreter(self, package: Optional[str] = None) -> str:
        self.verifier_connexion()
        package = package or self.config["package"]
        self.shell(f"am force-stop {package}", timeout=30)
        return package

    def reveiller(self) -> None:
        """Sort le casque de veille — utile avant un lancement."""
        self.shell("input keyevent KEYCODE_WAKEUP", timeout=20)

    def maintenir_eveille(self, actif: bool = True) -> List[str]:
        """
        Neutralise la mise en veille automatique du casque.

        Point crucial pour l'usage prévu ici : le Quest possède un capteur de
        proximité qui suspend l'appareil dès qu'il n'est plus porté. Lancer le
        jeu avant de poser le casque sur la tête du participant n'a donc
        d'intérêt que si cette mise en veille est désactivée — sans quoi
        l'application se met en pause entre le lancement et le port effectif.

        Meta a changé plusieurs fois le mécanisme selon les versions de
        firmware. On tente donc les méthodes connues successivement, et on
        retourne la liste de celles que l'appareil a acceptées.

        À vérifier sur votre matériel : selon la version installée, aucune,
        une seule ou plusieurs peuvent fonctionner.
        """
        valeur = "1" if actif else "0"
        tentatives = [
            ("diffusion prox_close",
             f"am broadcast -a com.oculus.vrpowermanager.prox_close"
             if actif else
             "am broadcast -a com.oculus.vrpowermanager.prox_open"),
            ("réglage disable_proximity_sensor",
             f"settings put global disable_proximity_sensor {valeur}"),
            ("écran maintenu allumé",
             f"svc power stayon {'true' if actif else 'false'}"),
        ]

        acceptees = []
        for libelle, commande in tentatives:
            r = self.shell(commande, timeout=20)
            sortie = (r.sortie + r.erreur).lower()
            if r.ok and not any(m in sortie for m in
                                ("error", "exception", "unknown", "failure",
                                 "not found", "denied")):
                acceptees.append(libelle)
        return acceptees

    # -- diagnostic --------------------------------------------------------

    # -- limite de jeu (guardian) ------------------------------------------

    #: Fournisseur de contenu exposé par les « Scriptable Testing Services »
    #: de Horizon OS v44+. C'est la voie officielle et documentée par Meta
    #: pour agir sur la limite sans mettre le casque.
    URI_TESTING = "content://com.oculus.rc"

    #: Paquet système qui gère la limite. Effacer ses données force le casque
    #: à redemander un tracé au prochain port.
    PAQUET_GUARDIAN = "com.oculus.guardian"

    def _appel_testing(self, methode: str, extras: Optional[List[str]] = None,
                       timeout: int = 40) -> Resultat:
        """
        Appelle les services de test de Horizon OS.

        Ils exigent un compte développeur ou un compte de test connecté, et le
        code PIN Store associé pour les écritures. Sans cela, la commande
        échoue proprement — d'où le repli sur la propriété système.
        """
        commande = f"content call --uri {self.URI_TESTING} --method {methode}"
        for extra in (extras or []):
            commande += f" --extra '{extra}'"
        return self.shell(commande, timeout=timeout)

    def limite_etat(self) -> dict:
        """
        Dit si la limite de jeu est active, et par quel mécanisme.

        Deux sources indépendantes, car les deux leviers coexistent : la
        propriété système `debug.oculus.guardian_pause`, et la propriété
        `disable_guardian` des services de test. L'une peut être posée sans
        l'autre, et croire n'en interroger qu'une conduirait à annoncer une
        limite désactivée alors qu'elle ne l'est pas.
        """
        self.verifier_connexion()

        prop = self.shell("getprop debug.oculus.guardian_pause", timeout=20)
        pause = prop.sortie.strip() == "1"

        officiel = self._appel_testing("GET_PROPERTY")
        texte = officiel.sortie + officiel.erreur
        if "disable_guardian=true" in texte.replace(" ", ""):
            desactivee_officiellement = True
        elif "disable_guardian=false" in texte.replace(" ", ""):
            desactivee_officiellement = False
        else:
            desactivee_officiellement = None   # services indisponibles

        return {
            "active": not (pause or desactivee_officiellement is True),
            "pause_propriete": pause,
            "desactivee_services": desactivee_officiellement,
            "services_disponibles": desactivee_officiellement is not None,
        }

    def limite_definir(self, active: bool, pin: Optional[str] = None) -> dict:
        """
        Active ou désactive la limite de jeu, sans mettre le casque.

        **Pourquoi désactiver plutôt que retracer.** Le participant est assis
        au bord du lit ou dans un fauteuil, l'investigateur est présent, et
        l'amplitude du geste ne dépasse pas la longueur des bras. Le risque
        que la limite protège — heurter un mur en se déplaçant — n'existe pas
        ici. En revanche, une limite qui se déclenche en pleine séance affiche
        la grille et interrompt le jeu : la partie est perdue, et avec elle la
        mesure. Sur le plan des données, supprimer la limite est plus sûr que
        la maintenir.

        Deux mécanismes sont tentés dans l'ordre :

        1. Les services de test officiels (Horizon OS v44+). Ils exigent un
           compte développeur connecté et le code PIN Store, mais c'est la
           voie documentée et la plus stable.
        2. La propriété `debug.oculus.guardian_pause`, qui fonctionne sans
           PIN mais suspend aussi le passthrough. Sans conséquence ici : le
           jeu s'affiche en environnement virtuel complet.

        Le repli n'est pas un contournement : c'est la reconnaissance qu'un
        casque de laboratoire n'est pas toujours provisionné avec un compte
        de test.
        """
        self.verifier_connexion()
        pin = pin or self.config.get("pin_store", "")
        journal = []

        # 1. Voie officielle
        extras = [f"disable_guardian:b:{'true' if not active else 'false'}"]
        if pin:
            extras.append(f"PIN:s:{pin}")
        officiel = self._appel_testing("SET_PROPERTY", extras)
        reussite_officielle = "Success=true" in (officiel.sortie + officiel.erreur)
        journal.append(
            "Services de test : " +
            ("appliqué" if reussite_officielle
             else "indisponible" + (" (aucun code PIN configuré)" if not pin else ""))
        )

        # 2. Propriété système, toujours posée : elle ne coûte rien et couvre
        #    le cas où les services de test ne sont pas accessibles.
        valeur = "0" if active else "1"
        prop = self.shell(f"setprop debug.oculus.guardian_pause {valeur}", timeout=20)
        journal.append("Propriété système : " + ("appliquée" if prop.ok else "refusée"))

        if not reussite_officielle and not prop.ok:
            raise ErreurAdb(
                "La limite de jeu n'a pas pu être modifiée.\n"
                + "\n".join(journal) +
                "\n\nVérifiez que le mode développeur est actif sur le casque. "
                "Pour la voie officielle, renseignez le code PIN Store :\n"
                "    python quest_control/quest.py configurer --pin 1234"
            )

        return {
            "active": active,
            "voie_officielle": reussite_officielle,
            "journal": journal,
        }

    def limite_redefinir(self) -> str:
        """
        Efface la limite mémorisée pour que le casque en redemande une.

        À n'utiliser que si vous voulez *vraiment* retracer une limite : le
        casque redemandera un tracé au prochain port, ce qui suppose que
        quelqu'un le mette et manipule les manettes. Dans le déroulé de
        l'étude, c'est précisément ce qu'on cherche à éviter — préférez
        `limite_definir(False)`.

        Aucune commande ADB ne permet de *dessiner* une limite à distance :
        le tracé est un geste, pas un réglage.
        """
        self.verifier_connexion()
        r = self.shell(f"pm clear {self.PAQUET_GUARDIAN}", timeout=40)
        if not r.ok or "Success" not in (r.sortie + r.erreur):
            raise ErreurAdb(
                f"Impossible d'effacer la limite mémorisée : "
                f"{r.sortie or r.erreur}\n"
                "Cette opération demande souvent des droits que le mode "
                "développeur seul n'accorde pas. Passez alors par le casque : "
                "Paramètres > Limite > Effacer l'historique."
            )
        return self.PAQUET_GUARDIAN

    def simuler_port(self, porte: bool = True) -> str:
        """
        Fait croire au casque qu'il est porté, ou qu'il ne l'est plus.

        Le capteur de proximité suspend l'appareil dès que le casque quitte la
        tête. Pendant la préparation — désinfection, réglage de la sangle,
        lancement du jeu — le casque est posé : sans ce leurre, il se met en
        veille et le jeu ne démarre pas.
        """
        self.verifier_connexion()
        action = "prox_close" if porte else "prox_far"
        self.shell(f"am broadcast -a com.oculus.vrpowermanager.{action}", timeout=20)
        return action

    def diagnostic(self) -> List[dict]:
        """
        Passe en revue tout ce qui doit être vrai pour que le pilotage
        fonctionne, et indique quoi faire pour chaque point en défaut.

        Conçu pour la première mise en service sur le matériel réel : c'est le
        seul moment où l'on découvre l'identifiant du jeu, l'emplacement des
        CSV et le comportement du capteur de proximité.
        """
        etapes = []

        def noter(titre, ok, detail="", remede=""):
            etapes.append({"titre": titre, "ok": ok,
                           "detail": detail, "remede": remede})

        # 1. adb
        if shutil.which(self.adb) is None:
            noter("ADB installé", False, f"introuvable : {self.adb}",
                  "Installez les SDK Platform Tools, ou renseignez le chemin "
                  "complet de adb.exe dans quest_control/config.json.")
            return etapes
        noter("ADB installé", True, shutil.which(self.adb))

        # 2. casque détecté et autorisé
        appareils = self.appareils()
        if not appareils:
            noter("Casque détecté", False, "aucun appareil",
                  "Branchez le câble USB. Vérifiez que le casque est allumé.")
            return etapes
        if not self.connecte():
            etats = ", ".join(f"{a['serie']} ({a['etat']})" for a in appareils)
            noter("Casque autorisé", False, etats,
                  "Mettez le casque et acceptez « Autoriser le débogage USB ». "
                  "Si rien ne s'affiche, activez le mode développeur dans "
                  "l'application mobile Meta Quest.")
            return etapes
        appareil = next(a for a in appareils if a["etat"] == "device")
        noter("Casque détecté et autorisé", True,
              f"{appareil['modele']} par {'Wi-Fi' if appareil['wifi'] else 'USB'}")

        # 3. batterie
        batterie = self.batterie()
        if batterie is not None:
            noter("Batterie suffisante", batterie >= 30, f"{batterie} %",
                  "" if batterie >= 30 else
                  "Rechargez avant la séance : une coupure en cours de partie "
                  "fait perdre les données de celle-ci.")

        # 4. jeu installé
        paquets = self.paquets()
        attendu = self.config["package"]
        if attendu in paquets:
            noter("Jeu APEX installé", True, attendu)
        else:
            apercu = ", ".join(paquets[:8]) or "(aucune)"
            noter("Jeu APEX installé", False,
                  f"« {attendu} » absent. Applications présentes : {apercu}",
                  "Relevez le bon identifiant avec la commande « applications », "
                  "puis : python quest_control/quest.py configurer --package <id>")

        # 5. emplacement des données
        dossiers = self.localiser_donnees()
        if dossiers:
            sessions = self.lister_sessions()
            noter("Dossier de données trouvé", True,
                  f"{dossiers[0]} — {len(sessions)} séance(s)")
        else:
            noter("Dossier de données trouvé", False,
                  "aucun des emplacements connus ne contient de séance",
                  "Lancez une partie de test dans le casque, puis cherchez où "
                  "elle a été écrite : adb shell find /sdcard -name "
                  "CSV_OptionsGame.csv. Ajoutez le chemin dans "
                  "« dossiers_donnees » de config.json.")

        # 6. mise en veille
        acceptees = self.maintenir_eveille(True)
        if acceptees:
            noter("Veille automatique neutralisée", True, ", ".join(acceptees))
        else:
            noter("Veille automatique neutralisée", False,
                  "aucune méthode acceptée par ce firmware",
                  "Le casque risque de se mettre en veille entre le lancement "
                  "et le port. Contournement : lancer le jeu juste avant de "
                  "tendre le casque au participant.")

        return etapes

    # -- récupération des données -----------------------------------------

    def _dossiers_candidats(self) -> List[str]:
        package = self.config["package"]
        return [d.format(package=package) for d in self.config["dossiers_donnees"]]

    def localiser_donnees(self) -> List[str]:
        """Cherche où le jeu écrit ses CSV."""
        trouves = []
        for dossier in self._dossiers_candidats():
            r = self.shell(f'ls -d "{dossier}" 2>/dev/null', timeout=20)
            if r.sortie.strip() and "No such file" not in r.sortie:
                trouves.append(dossier)
        return trouves

    def lister_sessions(self, dossier: Optional[str] = None) -> List[str]:
        """Liste les dossiers de session présents sur le casque."""
        dossiers = [dossier] if dossier else self.localiser_donnees()
        sessions = []
        for d in dossiers:
            r = self.shell(f'find "{d}" -name CSV_OptionsGame.csv 2>/dev/null',
                           timeout=60)
            for ligne in r.sortie.splitlines():
                ligne = ligne.strip()
                if ligne.endswith("CSV_OptionsGame.csv"):
                    sessions.append(str(Path(ligne).parent))
        return sorted(set(sessions))

    def recuperer(self, destination: Optional[Path] = None,
                  participant: str = "", effacer: bool = False) -> dict:
        """
        Copie les dossiers de session du casque vers le poste.

        Les fichiers sont déposés dans un dossier horodaté, prêt à être
        sélectionné dans l'application web lors de la création de la séance.
        """
        self.verifier_connexion()

        sessions = self.lister_sessions()
        if not sessions:
            emplacements = "\n  ".join(self._dossiers_candidats())
            raise ErreurAdb(
                "Aucun dossier de session trouvé sur le casque.\n"
                f"Emplacements explorés :\n  {emplacements}\n\n"
                "Ajustez « dossiers_donnees » dans quest_control/config.json."
            )

        base = Path(destination) if destination else (
            RACINE / self.config["destination_import"])
        etiquette = participant.strip().upper() or "seance"
        cible = base / f"{etiquette}_{datetime.now():%Y-%m-%d_%H-%M}"
        cible.mkdir(parents=True, exist_ok=True)

        rapport = {"destination": str(cible), "recuperes": [], "echecs": []}

        for distant in sessions:
            nom = Path(distant).name
            local = cible / nom
            r = self._executer(["pull", distant, str(local)], timeout=300)
            if r.ok:
                rapport["recuperes"].append(nom)
                if effacer:
                    self.shell(f'rm -rf "{distant}"', timeout=60)
            else:
                rapport["echecs"].append(f"{nom} : {r.erreur or r.sortie}")

        return rapport


# ---------------------------------------------------------------------------
# Interface en ligne de commande
# ---------------------------------------------------------------------------

VERT, ROUGE, JAUNE, GRIS, RAZ = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"


def cmd_etat(quest: Quest, args) -> int:
    appareils = quest.appareils()
    if not appareils:
        print(f"{ROUGE}Aucun casque détecté.{RAZ}")
        print("\n  Branchez le câble USB, ou connectez-vous en Wi-Fi :")
        print("    python quest_control/quest.py connecter --ip <adresse>")
        derniere = quest.config.get("derniere_ip")
        if derniere:
            print(f"\n  Dernière adresse utilisée : {derniere}")
        return 1

    print("Appareils vus par ADB :")
    for a in appareils:
        marque = VERT + "●" + RAZ if a["etat"] == "device" else JAUNE + "○" + RAZ
        liaison = "Wi-Fi" if a["wifi"] else "USB"
        print(f"  {marque} {a['serie']:24s} {a['etat']:14s} {liaison:6s} {a['modele']}")

    if not quest.connecte():
        print(f"\n{JAUNE}Casque détecté mais pas prêt.{RAZ}")
        print("  Mettez le casque et acceptez « Autoriser le débogage USB ».")
        return 1

    etat = quest.etat()
    print(f"\n{'Modèle':22s} {etat['modele']}")
    print(f"{'Liaison':22s} {etat['liaison']}")
    batterie = etat["batterie"]
    if batterie is not None:
        couleur = VERT if batterie > 40 else (JAUNE if batterie > 15 else ROUGE)
        print(f"{'Batterie':22s} {couleur}{batterie} %{RAZ}")
    print(f"{'Jeu APEX installé':22s} "
          + (f"{VERT}oui{RAZ}" if etat["jeu_installe"] else f"{ROUGE}non{RAZ}"))
    if etat["application_active"]:
        print(f"{'Application au premier plan':22s} {etat['application_active']}")

    if not etat["jeu_installe"]:
        print(f"\n{JAUNE}Applications installées sur ce casque :{RAZ}")
        for nom in quest.paquets()[:25]:
            print(f"    {nom}")
        print(f"\n  Renseignez le bon identifiant dans {GRIS}quest_control/config.json{RAZ}")

    sessions = quest.lister_sessions()
    print(f"\n{'Sessions sur le casque':22s} {len(sessions)}")
    for s in sessions[:8]:
        print(f"    {GRIS}{s}{RAZ}")
    if len(sessions) > 8:
        print(f"    {GRIS}… et {len(sessions) - 8} autres{RAZ}")
    return 0


def cmd_connecter(quest: Quest, args) -> int:
    if args.ip:
        cible = quest.connecter_wifi(args.ip)
        print(f"{VERT}Connecté à {cible}{RAZ}")
    else:
        print("Passage en Wi-Fi — le casque doit être branché en USB.")
        cible = quest.activer_wifi()
        print(f"{VERT}Connecté à {cible}{RAZ}")
        print("\nVous pouvez débrancher le câble. Le casque reste pilotable")
        print("tant qu'il est allumé et sur le même réseau.")
    return 0


def cmd_lancer(quest: Quest, args) -> int:
    quest.reveiller()
    quest.maintenir_eveille(True)
    package = quest.lancer(args.package)
    print(f"{VERT}Jeu lancé{RAZ} : {package}")
    print("Le casque peut être posé sur la tête du participant.")
    return 0


def cmd_arreter(quest: Quest, args) -> int:
    package = quest.arreter(args.package)
    print(f"{VERT}Jeu arrêté{RAZ} : {package}")
    return 0


def cmd_limite(quest: Quest, args) -> int:
    """Consulte ou modifie la limite de jeu."""
    if args.action == "etat":
        etat = quest.limite_etat()
        print(f"\n  Limite de jeu : "
              + (f"{ROUGE}ACTIVE{RAZ}" if etat["active"]
                 else f"{VERT}désactivée{RAZ}"))
        print(f"  {GRIS}propriété debug.oculus.guardian_pause : "
              f"{'posée' if etat['pause_propriete'] else 'absente'}{RAZ}")
        if etat["services_disponibles"]:
            print(f"  {GRIS}services de test Horizon : disable_guardian = "
                  f"{etat['desactivee_services']}{RAZ}")
        else:
            print(f"  {GRIS}services de test Horizon : indisponibles "
                  f"(casque non provisionné, ou code PIN manquant){RAZ}")
        print()
        return 0

    if args.action == "redefinir":
        print(f"\n  {JAUNE}Cette commande efface la limite mémorisée.{RAZ}")
        print("  Le casque en redemandera une au prochain port : quelqu'un")
        print("  devra le mettre et tracer la limite avec les manettes.")
        print("  Pour une séance en position assise, préférez :")
        print(f"      python quest_control/quest.py limite desactiver\n")
        if not args.oui:
            reponse = input("  Confirmer l'effacement ? [o/N] ").strip().lower()
            if reponse not in ("o", "oui", "y"):
                print("  Annulé.")
                return 0
        quest.limite_redefinir()
        print(f"  {VERT}Limite effacée.{RAZ} Elle sera redemandée au prochain port.\n")
        return 0

    active = args.action == "activer"
    resultat = quest.limite_definir(active)
    etat = f"{VERT}désactivée{RAZ}" if not active else "réactivée"
    print(f"\n  Limite de jeu {etat}.")
    for ligne in resultat["journal"]:
        print(f"  {GRIS}{ligne}{RAZ}")
    if not active:
        print(f"  {GRIS}Le passthrough peut rester indisponible tant que la "
              f"limite est suspendue.{RAZ}")
    print()
    return 0


def cmd_preparer(quest: Quest, args) -> int:
    """
    Prépare le casque pour une séance, en une commande.

    L'enchaînement suit l'ordre du soin : on réveille l'appareil, on neutralise
    ce qui pourrait interrompre la séance, puis on lance le jeu. Chaque étape
    est annoncée et son échec n'interrompt pas les suivantes — mieux vaut un
    casque partiellement préparé et un message clair qu'un arrêt au premier
    obstacle, avec un participant qui attend.
    """
    etapes = []

    def etape(libelle, action):
        try:
            action()
            etapes.append((libelle, True, ""))
        except Exception as exc:                      # noqa: BLE001
            etapes.append((libelle, False, str(exc).splitlines()[0]))

    print("\n" + "=" * 62)
    print("  Préparation du casque")
    print("=" * 62 + "\n")

    etape("Réveil de l'appareil", quest.reveiller)
    etape("Simulation du port (capteur de proximité)",
          lambda: quest.simuler_port(True))
    etape("Veille automatique neutralisée",
          lambda: quest.maintenir_eveille(True))
    if not args.garder_limite:
        etape("Limite de jeu désactivée", lambda: quest.limite_definir(False))
    if not args.sans_lancer:
        etape("Jeu lancé", lambda: quest.lancer(args.package))

    for libelle, ok, detail in etapes:
        marque = f"{VERT}OK{RAZ}   " if ok else f"{ROUGE}ÉCHEC{RAZ}"
        print(f"  {marque}  {libelle}")
        if detail:
            print(f"         {GRIS}{detail}{RAZ}")

    rates = [e for e in etapes if not e[1]]
    print()
    if rates:
        print(f"  {JAUNE}{len(rates)} étape(s) en échec. Le casque peut tout de "
              f"même être utilisable —{RAZ}")
        print(f"  {JAUNE}vérifiez avant de le tendre au participant.{RAZ}\n")
        return 1

    print(f"  {VERT}Casque prêt.{RAZ} Vous pouvez le tendre au participant.\n")
    return 0


def cmd_recuperer(quest: Quest, args) -> int:
    rapport = quest.recuperer(
        destination=Path(args.destination) if args.destination else None,
        participant=args.participant or "",
        effacer=args.effacer,
    )
    n = len(rapport["recuperes"])
    print(f"{VERT}{n} session(s) récupérée(s){RAZ}")
    for nom in rapport["recuperes"]:
        print(f"    {nom}")
    for echec in rapport["echecs"]:
        print(f"  {ROUGE}échec{RAZ} {echec}")

    print(f"\nDossier : {rapport['destination']}")
    print("\nDans l'application web : + Session, puis sélectionnez ce dossier.")
    if args.effacer:
        print(f"{JAUNE}Les données ont été effacées du casque.{RAZ}")
    return 0 if not rapport["echecs"] else 1


def cmd_diagnostic(quest: Quest, args) -> int:
    print("Diagnostic de mise en service\n")
    etapes = quest.diagnostic()
    for e in etapes:
        marque = f"{VERT}✓{RAZ}" if e["ok"] else f"{ROUGE}✗{RAZ}"
        print(f"  {marque} {e['titre']}")
        if e["detail"]:
            print(f"      {GRIS}{e['detail']}{RAZ}")
        if not e["ok"] and e["remede"]:
            for ligne in _envelopper(e["remede"], 68):
                print(f"      {JAUNE}{ligne}{RAZ}")
        print()

    manques = [e for e in etapes if not e["ok"]]
    if manques:
        print(f"{ROUGE}{len(manques)} point(s) à régler avant utilisation.{RAZ}")
        return 1
    print(f"{VERT}Tout est en place. Le pilotage du casque est opérationnel.{RAZ}")
    return 0


def _envelopper(texte: str, largeur: int) -> List[str]:
    mots, lignes, courante = texte.split(), [], ""
    for mot in mots:
        if len(courante) + len(mot) + 1 > largeur:
            lignes.append(courante)
            courante = mot
        else:
            courante = f"{courante} {mot}".strip()
    if courante:
        lignes.append(courante)
    return lignes


def cmd_applications(quest: Quest, args) -> int:
    quest.verifier_connexion()
    noms = quest.paquets(args.filtre or "")
    print(f"{len(noms)} application(s) installée(s) :")
    for nom in noms:
        marque = f" {VERT}<- configurée{RAZ}" if nom == quest.config["package"] else ""
        print(f"    {nom}{marque}")

    if not args.adopter:
        # Le nom affiché dans le casque (« APEX_experiment ») n'est pas
        # l'identifiant technique attendu par ADB : c'est la source de confusion
        # la plus fréquente au premier lancement.
        candidats = [n for n in noms if "apex" in n.lower()]
        if candidats and quest.config["package"] not in candidats:
            print(f"\n  {JAUNE}Le jeu semble être : {candidats[0]}{RAZ}")
            print(f"  {GRIS}Pour l'adopter : python quest_control/quest.py "
                  f"applications --filtre apex --adopter{RAZ}")
        return 0

    candidats = [n for n in noms if "apex" in n.lower()] or noms
    if len(candidats) != 1:
        print(f"\n  {ROUGE}Impossible de choisir automatiquement "
              f"({len(candidats)} candidat(s)).{RAZ}")
        print(f"  {GRIS}Affinez le filtre, ou fixez le paquet à la main :{RAZ}")
        print(f"  {GRIS}python quest_control/quest.py configurer "
              f"--package <identifiant>{RAZ}")
        return 1

    quest.config["package"] = candidats[0]
    enregistrer_config(quest.config)
    print(f"\n  {VERT}Jeu configuré : {candidats[0]}{RAZ}\n")
    return 0


def cmd_configurer(quest: Quest, args) -> int:
    if args.package:
        quest.config["package"] = args.package
    if args.activite is not None:
        quest.config["activite"] = args.activite
    if args.dossier:
        quest.config["dossiers_donnees"] = [args.dossier]
    if args.pin is not None:
        quest.config["pin_store"] = args.pin
    enregistrer_config(quest.config)

    # Le code PIN ouvre l'accès aux services de test du casque : il n'a pas à
    # s'afficher dans un terminal partagé, ni à finir dans un journal.
    affichable = dict(quest.config)
    if affichable.get("pin_store"):
        affichable["pin_store"] = "****"
    print("Configuration enregistrée :")
    print(json.dumps(affichable, ensure_ascii=False, indent=2))
    return 0



def activer_simulateur(scenario: str = "normal") -> Quest:
    """
    Fabrique un Quest branché sur un casque simulé.

    Le faux casque et son état vivent dans un dossier temporaire : rien de ce
    qui est fait en mode simulation ne touche la configuration réelle du poste
    ni un appareil branché. C'est délibéré — on doit pouvoir répéter le geste
    du soir avant une inclusion sans crainte.
    """
    import tempfile

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from simulateur import creer_faux_adb

    dossier = Path(tempfile.mkdtemp(prefix="apex_simulateur_"))
    adb = creer_faux_adb(dossier, scenario)
    return Quest({
        "adb": str(adb),
        "package": "com.DefaultCompany.APEX",
        "activite": "",
        "dossiers_donnees": ["/sdcard/Android/data/{package}/files"],
        "destination_import": str(dossier / "donnees_recuperees"),
        "port_wifi": 5555,
        "pin_store": "1234",
    })


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pilotage du casque Meta Quest pour l'étude APEX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    parser.add_argument("--simulateur", action="store_true",
                        help="travailler sur un casque simulé, sans matériel")
    parser.add_argument("--scenario", default="normal", metavar="NOM",
                        help="comportement du casque simulé : normal, absent, "
                             "jeu_absent, lancement_echoue, sans_services_test, "
                             "setprop_refuse, clear_refuse, sans_donnees")
    sous = parser.add_subparsers(dest="commande")

    sous.add_parser("etat", help="état du casque et des données présentes")
    sous.add_parser("diagnostic",
                    help="vérifie tout ce qui doit être configuré (à faire en premier)")

    c = sous.add_parser("connecter", help="connexion Wi-Fi")
    c.add_argument("--ip", help="adresse IP du casque")

    c = sous.add_parser("preparer",
                        help="tout préparer et lancer le jeu, en une commande")
    c.add_argument("--package", help="identifiant de l'application")
    c.add_argument("--garder-limite", action="store_true",
                   help="ne pas désactiver la limite de jeu")
    c.add_argument("--sans-lancer", action="store_true",
                   help="préparer sans démarrer le jeu")

    c = sous.add_parser("limite", help="limite de jeu (guardian)")
    c.add_argument("action", choices=["etat", "desactiver", "activer", "redefinir"],
                   help="etat : consulter · desactiver : la suspendre · "
                        "activer : la rétablir · redefinir : effacer le tracé "
                        "mémorisé, le casque en redemandera un")
    c.add_argument("--oui", action="store_true",
                   help="ne pas demander confirmation")

    c = sous.add_parser("lancer", help="démarrer le jeu")
    c.add_argument("--package", help="identifiant de l'application")

    c = sous.add_parser("arreter", help="arrêter le jeu")
    c.add_argument("--package")

    c = sous.add_parser("recuperer", help="rapatrier les données de séance")
    c.add_argument("--participant", help="code participant, pour nommer le dossier")
    c.add_argument("--destination", help="dossier de destination")
    c.add_argument("--effacer", action="store_true",
                   help="effacer les données du casque après copie")

    c = sous.add_parser("applications",
                        help="lister les applications installées, et trouver "
                             "l'identifiant du jeu")
    c.add_argument("--filtre", help="filtrer par nom")
    c.add_argument("--adopter", action="store_true",
                   help="enregistrer l'application trouvée comme jeu de l'étude")

    c = sous.add_parser("configurer", help="modifier la configuration")
    c.add_argument("--package")
    c.add_argument("--activite")
    c.add_argument("--dossier")
    c.add_argument("--pin", help="code PIN Store, pour les services de test "
                                 "officiels de Horizon OS")

    args = parser.parse_args()
    if not args.commande:
        parser.print_help()
        return 0

    commandes = {
        "etat": cmd_etat, "diagnostic": cmd_diagnostic,
        "connecter": cmd_connecter, "lancer": cmd_lancer,
        "preparer": cmd_preparer, "limite": cmd_limite,
        "arreter": cmd_arreter, "recuperer": cmd_recuperer,
        "applications": cmd_applications, "configurer": cmd_configurer,
    }

    if args.simulateur:
        quest = activer_simulateur(args.scenario)
        print(f"{JAUNE}Mode simulateur ({args.scenario}) — aucun casque réel "
              f"n'est piloté.{RAZ}")
    else:
        quest = Quest()

    try:
        return commandes[args.commande](quest, args)
    except ErreurAdb as exc:
        print(f"{ROUGE}{exc}{RAZ}")
        return 1
    except KeyboardInterrupt:
        print("\nInterrompu.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
