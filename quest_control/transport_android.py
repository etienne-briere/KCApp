# -*- coding: utf-8 -*-
"""
Transport ADB pur Python pour `quest.py`, à utiliser quand KCApp tourne dans
l'APK (Buildozer / python-for-android) plutôt que sur le poste Windows.

Pourquoi ce fichier existe : `Quest._executer` (dans quest.py) invoque le
binaire `adb` via `subprocess`. Il n'y a pas de binaire `adb` dans un APK.
`adb-shell` réimplémente le protocole ADB en sockets purs — c'est l'équivalent
Python de ce que fait Kadb côté Kotlin dans quest_android/.

Toute la logique métier de quest.py (preparer, limite_definir,
maintenir_eveille, lancer, recuperer, diagnostic, ...) continue de fonctionner
SANS AUCUNE MODIFICATION : elle n'appelle jamais adb directement, seulement
`self.shell(...)` et `self._executer(...)`. Ce fichier ne remplace donc que la
couche transport, par héritage.

Dépendances à ajouter (buildozer.spec, android.requirements, et
requirements.txt pour la build PC si vous voulez tester ce transport hors
casque) :

    adb-shell[pythonrsa]

Le variant "pythonrsa" est important : il utilise les paquets purs Python
`rsa` + `pyasn1` pour signer le challenge d'authentification, au lieu de
`cryptography` ou `pycryptodome` (qui embarquent du code compilé et
demandent une recette python-for-android). Avec pythonrsa, aucune recette p4a
supplémentaire n'est nécessaire.

Clé ADB : réutilisez le fichier produit par
`quest_android/outils/preparer_cle.py` (même format de clé qu'attend adb-shell
— un fichier privé, et son `.pub` à côté). Embarquez-le comme asset de l'appli
et ne le versionnez jamais (voir la mise en garde du README quest_android).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.exceptions import AdbCommandFailureException, TcpTimeoutException

from quest import ErreurAdb, Quest, Resultat


def _charger_signataire(chemin_cle_privee: Path) -> PythonRSASigner:
    """
    Charge la paire de clés ADB.

    `chemin_cle_privee` pointe vers la clé privée (ex. celle déposée par
    preparer_cle.py sous `app/src/main/assets/adbkey` côté Kotlin — même
    format ici). La clé publique associée est attendue au même endroit avec
    un `.pub` en plus, ce que produit déjà preparer_cle.py.
    """
    prive = chemin_cle_privee.read_text()
    publique = chemin_cle_privee.with_name(chemin_cle_privee.name + ".pub").read_text()
    return PythonRSASigner(publique, prive)


class QuestAndroid(Quest):
    """
    Même API que `Quest`, même comportement métier (hérité tel quel), mais
    qui parle ADB en TCP pur Python au lieu d'invoquer un binaire externe.

    Utilisation depuis KCApp :

        quest = QuestAndroid(ip="192.168.1.42",
                              chemin_cle=Path(app.user_data_dir) / "adbkey")
        quest.preparer_seance(pin="1234")   # méthode héritée, inchangée
    """

    def __init__(self, ip: str, chemin_cle: Path,
                 config: Optional[dict] = None,
                 chemin_config: Optional[Path] = None):
        super().__init__(config=config, chemin_config=chemin_config)
        self._ip = ip
        self._port = self.config.get("port_wifi", 5555)
        self._device = AdbDeviceTcp(
            ip, self._port, default_transport_timeout_s=20.)
        self._signataire = _charger_signataire(chemin_cle)
        self._connecte = False

    # -- remplace l'unique point de passage vers l'extérieur ---------------

    def _executer(self, args, timeout: int = 120) -> Resultat:
        """
        Traduit les mêmes formes d'appel que la version PC — `["shell", cmd]`,
        `["pull", distant, local]`, `["connect", cible]`, `["devices", "-l"]`,
        `["tcpip", port]` — vers adb-shell. `quest.py` continue d'appeler
        `self.shell(...)` et `self._executer(...)` sans savoir que le
        transport a changé.
        """
        commande, *reste = args
        try:
            if commande == "shell":
                self._assurer_connexion()
                sortie = self._device.shell(reste[0], timeout_s=timeout)
                return Resultat(0, (sortie or "").strip(), "")

            if commande == "pull":
                self._assurer_connexion()
                distant, local = reste
                self._device.pull(distant, local, timeout_s=timeout)
                return Resultat(0, "", "")

            if commande == "connect":
                self._assurer_connexion(forcer=True)
                return Resultat(0, f"connected to {self._ip}:{self._port}", "")

            if commande == "devices":
                # Pas d'énumération possible en socket pur : un seul
                # appareil ciblé, à l'adresse configurée. On reproduit le
                # format texte attendu par `Quest.appareils()` pour ne pas
                # devoir réécrire cette méthode (voir appareils() ci-dessous,
                # qui de toute façon la court-circuite).
                etat = "device" if self._est_connecte() else "offline"
                return Resultat(
                    0,
                    f"List of devices attached\n{self._ip}:{self._port}\t{etat}",
                    "")

            if commande == "tcpip":
                # Sans objet depuis l'appli : le casque doit déjà écouter en
                # TCP (condition 1 documentée dans quest_android/README.md).
                # Ce réglage se pose une fois, casque branché en USB — pas
                # depuis un client qui n'est déjà qu'en Wi-Fi.
                return Resultat(
                    0, "",
                    "tcpip : sans effet depuis QuestAndroid, "
                    "le casque doit déjà écouter en TCP")

        except (AdbCommandFailureException, TcpTimeoutException, OSError) as exc:
            return Resultat(1, "", str(exc))

        raise NotImplementedError(f"commande ADB non gérée par QuestAndroid : {commande}")

    def _assurer_connexion(self, forcer: bool = False) -> None:
        if self._connecte and not forcer:
            return
        try:
            self._device.close()
        except Exception:
            pass
        self._connecte = bool(self._device.connect(
            rsa_keys=[self._signataire], auth_timeout_s=15.))
        if not self._connecte:
            raise ErreurAdb(
                f"Connexion à {self._ip}:{self._port} impossible. Vérifiez que "
                "le casque écoute en Wi-Fi (adb tcpip côté casque, voir "
                "quest_android/README.md) et que la clé embarquée dans "
                "l'application est bien celle déjà autorisée par le casque."
            )

    def _est_connecte(self) -> bool:
        try:
            self._assurer_connexion()
            return True
        except ErreurAdb:
            return False

    # -- les méthodes suivantes ne passaient pas par _executer : elles
    #    parsaient directement la sortie texte de `adb devices -l`, propre au
    #    binaire adb. Un client TCP direct connaît déjà son unique cible, pas
    #    besoin de parser quoi que ce soit ici. -----------------------------

    def appareils(self):
        etat = "device" if self._est_connecte() else "offline"
        return [{"serie": f"{self._ip}:{self._port}", "etat": etat,
                 "modele": "", "wifi": True}]

    def connecte(self) -> bool:
        return self._est_connecte()

    def verifier_connexion(self) -> None:
        self._assurer_connexion()

    def activer_wifi(self, ip: Optional[str] = None) -> str:
        raise ErreurAdb(
            "Sans objet depuis l'application Android : le passage en mode "
            "TCP (adb tcpip) se fait une fois, depuis un poste branché en "
            "USB au casque — voir quest_android/README.md, condition 1."
        )

    def connecter_wifi(self, ip: str) -> str:
        self._ip = ip
        self._device = AdbDeviceTcp(
            ip, self._port, default_transport_timeout_s=20.)
        self._connecte = False
        self._assurer_connexion(forcer=True)
        self.config["derniere_ip"] = ip
        self._sauver_config()
        return f"{ip}:{self._port}"

    # -- non couvert par ce brouillon -----------------------------------
    #
    # `Quest.diagnostic()` appelle `shutil.which(self.adb)` directement (pas
    # via _executer) pour vérifier qu'un binaire adb est installé — non
    # pertinent ici. À surcharger si vous voulez un diagnostic depuis l'appli
    # ; sinon, ne pas l'appeler depuis KCApp côté Android suffit.