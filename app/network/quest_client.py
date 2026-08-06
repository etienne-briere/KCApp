# -*- coding: utf-8 -*-
"""
Pont entre KCApp (Kivy/asyncio) et le pilotage ADB du casque Meta Quest.

Enveloppe `QuestAndroid` (quest_control/transport_android.py) dans une API
asynchrone. Les commandes ADB sont bloquantes — parfois plusieurs secondes,
un casque qui dort — donc chaque appel est délégué à un thread via
`loop.run_in_executor` : il ne faut jamais bloquer la boucle asyncio
principale de Kivy (voir main.py, `app.async_run("asyncio")` — un blocage ici
gèlerait toute l'interface, pas seulement l'écran de pilotage du casque).

L'IP peut être fournie explicitement (`se_connecter(ip)`) ou retrouvée
automatiquement (`se_connecter_auto()`, voir quest_discovery.py) : dernière
IP connue en premier, balayage du sous-réseau en secours.

Utilisation typique, depuis un écran ou un contrôleur Kivy :

    app = App.get_running_app()

    async def preparer():
        if await app.quest_client.se_connecter_auto():
            resultat = await app.quest_client.preparer_seance()
            if resultat["reussi"]:
                toast("Casque prêt")
            else:
                toast("Casque partiellement préparé — voir les logs")

    asyncio.ensure_future(preparer())

État exposé via l'event bus existant (`utils/event_bus.py`), pour rester
cohérent avec le reste de l'appli (ws_server, udp_discovery, ...) :

    casque_connecte     {"ip": str}
    casque_erreur       {"message": str}
    casque_prepare      {"etapes": [...], "reussi": bool}
    casque_jeu_arrete   {}
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

from kivy.utils import platform

from utils.logger import get_logger
from utils.event_bus import event_bus

logger = get_logger(__name__)

# Racine de KCApp : .../KCApp/app/network/quest_client.py -> .../KCApp
_RACINE = Path(__file__).resolve().parent.parent.parent
_QUEST_CONTROL = _RACINE / "quest_control"
if str(_QUEST_CONTROL) not in sys.path:
    sys.path.insert(0, str(_QUEST_CONTROL))


def _chemin_cle_par_defaut() -> Path:
    """
    Emplacement de la clé ADB selon la plateforme.

    - Windows (poste de développement, ou build PC) : la clé déjà utilisée
      par adb.exe pour ce casque, sous le profil utilisateur — c'est celle
      qu'utilisent déjà `quest_control/essai_reel.py` et `essai_preparer.py`.
    - Android : clé embarquée comme asset de l'application, provisionnée par
      `quest_android/outils/preparer_cle.py` (voir son README). Le chemin
      exact dépend de la façon dont l'asset est packagé côté Buildozer — à
      confirmer/ajuster une fois cette étape traitée, ce chemin est une
      hypothèse raisonnable, pas une valeur vérifiée sur APK réel.
    """
    if platform == "android":
        from android.storage import app_storage_path  # type: ignore
        return Path(app_storage_path()) / "adbkey"
    return Path.home() / ".android" / "adbkey"


class QuestClient:
    """
    API asynchrone de pilotage du casque, pour les écrans/contrôleurs Kivy.

    Ne connecte rien à la construction : appeler `se_connecter(ip)` d'abord.
    """

    def __init__(self, chemin_cle: Optional[Path] = None):
        self._chemin_cle = chemin_cle or _chemin_cle_par_defaut()
        self._quest = None  # QuestAndroid, créé lors de la connexion
        self.connecte = False
        self.ip: Optional[str] = None

        # Temporaire : pour connaître le chemin exact où déposer adbkey /
        # adbkey.pub sur cette installation (visible via `adb logcat`).
        # À retirer une fois la clé provisionnée sur les tablettes.
        logger.info(f"📁 Clé ADB attendue ici : {self._chemin_cle}")

    # -- infrastructure -------------------------------------------------

    @staticmethod
    async def _en_arriere_plan(fonction, *args, **kwargs):
        """Exécute un appel bloquant (ADB) hors de la boucle asyncio principale."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fonction(*args, **kwargs))

    # -- connexion --------------------------------------------------------

    async def se_connecter(self, ip: str) -> bool:
        """Ouvre (ou ré-ouvre) la connexion ADB vers le casque à `ip`."""
        from transport_android import QuestAndroid
        from quest import ErreurAdb

        if not self._chemin_cle.exists():
            message = f"Clé ADB introuvable : {self._chemin_cle}"
            logger.error(f"❌ {message}")
            event_bus.emit("casque_erreur", {"message": message})
            return False

        def connecter():
            quest = QuestAndroid(ip=ip, chemin_cle=self._chemin_cle)
            # connecter_wifi (pas verifier_connexion) : mémorise aussi l'IP
            # dans quest_control/config.json, réutilisée par se_connecter_auto.
            quest.connecter_wifi(ip)
            return quest

        try:
            self._quest = await self._en_arriere_plan(connecter)
        except ErreurAdb as exc:
            self.connecte = False
            logger.error(f"❌ Connexion au casque impossible : {exc}")
            event_bus.emit("casque_erreur", {"message": str(exc)})
            return False

        self.connecte = True
        self.ip = ip
        logger.info(f"✅ Casque joignable à {ip}")
        event_bus.emit("casque_connecte", {"ip": ip})
        return True

    async def se_connecter_auto(self) -> bool:
        """
        Retrouve le casque sans IP fournie : dernière IP connue en premier,
        balayage du sous-réseau en secours (voir quest_discovery.py).

        Émet les mêmes événements que se_connecter() une fois l'IP trouvée
        — casque_erreur avec un message explicite si rien n'est trouvé.
        """
        from app.network.quest_discovery import decouvrir_casque
        from quest import charger_config

        if not self._chemin_cle.exists():
            message = f"Clé ADB introuvable : {self._chemin_cle}"
            logger.error(f"❌ {message}")
            event_bus.emit("casque_erreur", {"message": message})
            return False

        derniere_ip = charger_config().get("derniere_ip") or None
        ip = await decouvrir_casque(self._chemin_cle, derniere_ip=derniere_ip)

        if not ip:
            message = "Casque introuvable sur le réseau"
            logger.warning(f"⚠️ {message}")
            event_bus.emit("casque_erreur", {"message": message})
            return False

        return await self.se_connecter(ip)

    def deconnecter(self) -> None:
        """Oublie la connexion courante (ne coupe rien côté casque)."""
        self._quest = None
        self.connecte = False
        self.ip = None

    # -- pilotage de séance -------------------------------------------------

    async def preparer_seance(self, desactiver_limite: bool = True,
                               lancer_jeu: bool = True) -> dict:
        """
        Réveil, capteur de proximité leurré, veille neutralisée, limite de
        jeu désactivée, jeu lancé — même séquence que
        `quest_control/quest.py preparer` (voir `cmd_preparer`).

        Chaque étape rapporte son issue indépendamment des autres : un échec
        n'interrompt pas la suite (voir quest_android/README.md, "un échec
        n'interrompt pas la suite" — mieux vaut un casque partiellement
        préparé avec un message clair qu'un arrêt au premier obstacle).
        """
        if not self.connecte or self._quest is None:
            raise RuntimeError(
                "preparer_seance() appelé sans connexion active — "
                "appeler se_connecter(ip) d'abord.")

        def sequence():
            etapes = []

            def etape(nom, action):
                try:
                    action()
                    etapes.append({"etape": nom, "ok": True, "detail": ""})
                except Exception as exc:  # noqa: BLE001 — même choix que quest.py
                    etapes.append({"etape": nom, "ok": False,
                                    "detail": str(exc).splitlines()[0]})

            etape("reveil", self._quest.reveiller)
            etape("proximite", lambda: self._quest.simuler_port(True))
            etape("veille", lambda: self._quest.maintenir_eveille(True))
            if desactiver_limite:
                etape("limite", lambda: self._quest.limite_definir(False))
            if lancer_jeu:
                etape("lancement", self._quest.lancer)
            return etapes

        etapes = await self._en_arriere_plan(sequence)
        echecs = [e for e in etapes if not e["ok"]]

        if echecs:
            logger.warning(f"⚠️ Préparation partielle : {len(echecs)} étape(s) en échec")
        else:
            logger.info("✅ Casque prêt")

        resultat = {"etapes": etapes, "reussi": not echecs}
        event_bus.emit("casque_prepare", resultat)
        return resultat

    async def arreter_jeu(self) -> bool:
        """Arrête le jeu APEX sur le casque."""
        if not self.connecte or self._quest is None:
            return False
        try:
            await self._en_arriere_plan(self._quest.arreter)
        except Exception as exc:
            logger.error(f"❌ Arrêt du jeu impossible : {exc}")
            return False
        logger.info("🛑 Jeu arrêté")
        event_bus.emit("casque_jeu_arrete", {})
        return True

    async def etat(self) -> Optional[dict]:
        """État courant du casque : modèle, batterie, application active, ..."""
        if not self.connecte or self._quest is None:
            return None
        try:
            return await self._en_arriere_plan(self._quest.etat)
        except Exception as exc:
            logger.error(f"❌ Lecture de l'état du casque impossible : {exc}")
            return None
