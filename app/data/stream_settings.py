"""
Réglages de la « Vue du joueur » (images/seconde et largeur en pixels),
mémorisés entre deux lancements de l'application dans un petit fichier JSON
(même principe que player_store.py).
"""

import json
import os

from config import STREAM_FPS, STREAM_FPS_CHOICES, STREAM_WIDTH, STREAM_WIDTH_CHOICES
from utils.logger import get_logger

logger = get_logger(__name__)


class StreamSettings:
    """fps et width : toujours une des valeurs proposées (sinon valeur par défaut de config.py)."""

    def __init__(self, path: str = "stream_settings.json"):
        self.path = path
        self.fps = STREAM_FPS
        self.width = STREAM_WIDTH
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("fps") in STREAM_FPS_CHOICES:
                self.fps = data["fps"]
            if data.get("width") in STREAM_WIDTH_CHOICES:
                self.width = data["width"]
        except (json.JSONDecodeError, OSError, AttributeError) as e:
            logger.warning(f"⚠️ Impossible de charger {self.path} : {e}")

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"fps": self.fps, "width": self.width}, f, indent=2)
        except OSError as e:
            logger.warning(f"⚠️ Impossible d'enregistrer {self.path} : {e}")
