# -*- coding: utf-8 -*-
"""
Découverte automatique de l'adresse IP du casque Meta Quest sur le réseau
local de la tablette, pour éviter la saisie manuelle dans l'écran de
pilotage.

Le casque n'annonce rien lui-même (pas de service mDNS fiable en mode
`adb tcpip` classique). La découverte se fait donc en deux passes, de la
moins chère à la plus chère :

  1. Réessayer la dernière IP connue (mémorisée par `Quest.connecter_wifi`
     dans quest_control/config.json) — cas le plus fréquent, puisque l'IP ne
     change pas tant que le casque reste allumé (voir la discussion sur la
     persistance du mode TCP).
  2. À défaut, balayage TCP pur (sans protocole ADB) de tout le sous-réseau
     de la tablette sur le port ADB — quelques centaines de ms à 1-2 s selon
     la taille du réseau. Chaque hôte qui répond est ensuite vérifié par une
     vraie connexion ADB authentifiée, et son modèle doit contenir "quest" :
     ça élimine les faux positifs (un téléphone de labo en debug USB/Wi-Fi
     sur le même réseau, par exemple) sans jamais piloter un appareil qui
     n'est pas le casque — même logique prudente que `devinerPaquetJeu()`
     dans quest_control/quest.py : pas de réponse plutôt qu'une mauvaise
     réponse.

Hypothèse simplificatrice : sous-réseau en /24 (masque 255.255.255.0),
courant sur un Wi-Fi domestique ou de laboratoire mais pas garanti sur tous
les réseaux (voir la mise en garde sur l'isolation Wi-Fi hospitalière dans
quest_control/README.md) — à ajuster si le réseau cible est structuré
autrement.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path
from typing import List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Même bootstrap que quest_client.py, pour que ce module reste utilisable
# indépendamment de l'ordre d'import.
_RACINE = Path(__file__).resolve().parent.parent.parent
_QUEST_CONTROL = _RACINE / "quest_control"
if str(_QUEST_CONTROL) not in sys.path:
    sys.path.insert(0, str(_QUEST_CONTROL))

_CONCURRENCE_MAX = 50
_TIMEOUT_SONDE = 0.3  # secondes — sonde TCP pure, pas de protocole ADB


def _ip_locale() -> Optional[str]:
    """IP de la tablette sur le réseau Wi-Fi actuel (aucun paquet envoyé)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _candidats_sous_reseau(ip_locale: str) -> List[str]:
    """Toutes les IP du /24 déduit de l'IP locale, sauf elle-même."""
    prefixe = ".".join(ip_locale.split(".")[:3])
    return [f"{prefixe}.{dernier}" for dernier in range(1, 255)
            if f"{prefixe}.{dernier}" != ip_locale]


async def _port_ouvert(ip: str, port: int, timeout: float) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout)
    except (OSError, asyncio.TimeoutError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass
    return True


async def _balayer_port(port: int) -> List[str]:
    """IP du sous-réseau qui ont `port` ouvert (sonde TCP, pas ADB)."""
    ip_locale = _ip_locale()
    if not ip_locale:
        logger.warning("⚠️ IP locale introuvable, balayage réseau impossible")
        return []

    candidats = _candidats_sous_reseau(ip_locale)
    semaphore = asyncio.Semaphore(_CONCURRENCE_MAX)

    async def sonder(ip: str) -> Optional[str]:
        async with semaphore:
            return ip if await _port_ouvert(ip, port, _TIMEOUT_SONDE) else None

    resultats = await asyncio.gather(*(sonder(ip) for ip in candidats))
    return [ip for ip in resultats if ip]


async def decouvrir_casque(chemin_cle: Path, port: int = 5555,
                            derniere_ip: Optional[str] = None) -> Optional[str]:
    """
    Retourne l'IP du casque sur le réseau, ou None si introuvable.

    N'effectue jamais de connexion ADB à l'aveugle : chaque candidat est
    validé par une authentification réelle + vérification du modèle avant
    d'être retenu.
    """
    from transport_android import QuestAndroid
    from quest import ErreurAdb

    async def est_le_casque(ip: str) -> bool:
        def verifier() -> bool:
            quest = QuestAndroid(ip=ip, chemin_cle=chemin_cle)
            quest.verifier_connexion()
            return "quest" in quest.modele().lower()

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, verifier)
        except ErreurAdb:
            return False
        except Exception as exc:  # noqa: BLE001 — un candidat qui plante n'annule pas les autres
            logger.debug(f"Candidat {ip} écarté : {exc}")
            return False

    if derniere_ip and await est_le_casque(derniere_ip):
        logger.info(f"✅ Casque retrouvé à la dernière IP connue : {derniere_ip}")
        return derniere_ip

    logger.info("🔍 Balayage du réseau local pour trouver le casque...")
    candidats = await _balayer_port(port)
    if derniere_ip in candidats:
        candidats.remove(derniere_ip)  # déjà testée juste au-dessus

    for ip in candidats:
        if await est_le_casque(ip):
            logger.info(f"✅ Casque trouvé à {ip}")
            return ip

    logger.warning("⚠️ Casque introuvable sur le réseau")
    return None
