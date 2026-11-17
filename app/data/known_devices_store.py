import json
import os
from datetime import datetime

from utils.logger import get_logger

logger = get_logger(__name__)

# Nombre d'appareils conservés dans l'historique (les plus anciens sont
# retirés), pour garder la card "MES APPAREILS" de l'écran Capteur courte.
MAX_DEVICES = 5


class KnownDevicesStore:
    """
    Gère l'historique des appareils BLE déjà connectés (nom, adresse, date
    de dernière connexion) sauvegardé sur disque, pour la card "MES
    APPAREILS" de l'écran Capteur.
    """

    def __init__(self, path: str = "known_devices.json"):
        self.path = path
        self.devices = self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [d for d in data if "address" in d]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"⚠️ Impossible de charger {self.path} : {e}")
            return []

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.devices, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"❌ Impossible d'enregistrer {self.path} : {e}")

    def add(self, name, address):
        """
        Enregistre un appareil comme connu (ou met à jour sa date de
        dernière connexion s'il l'est déjà), en tête de liste (les plus
        récents affichés en premier dans la card).
        """
        self.devices = [d for d in self.devices if d["address"] != address]
        self.devices.insert(0, {
            "name": name or address,
            "address": address,
            "last_connected": datetime.now().isoformat(timespec="seconds"),
        })
        del self.devices[MAX_DEVICES:]
        self._save()
