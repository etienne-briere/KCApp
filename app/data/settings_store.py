import json
import os

from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CPM_STEP = 5
DEFAULT_HR_STEP = 1


class SettingsStore:
    """
    Réglages de l'application (pas des boutons +/-, et à terme d'autres
    valeurs par défaut) sauvegardés sur disque, pour l'écran Paramètres
    (menu Contrôle) — même principe que player_store.py.
    """

    def __init__(self, path: str = "app_settings.json"):
        self.path = path
        self.cpm_step = DEFAULT_CPM_STEP
        self.hr_step = DEFAULT_HR_STEP
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.cpm_step = self._clamp_cpm_step(data.get("cpm_step", DEFAULT_CPM_STEP))
            self.hr_step = self._clamp_hr_step(data.get("hr_step", DEFAULT_HR_STEP))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"⚠️ Impossible de charger {self.path} : {e}")

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"cpm_step": self.cpm_step, "hr_step": self.hr_step}, f, indent=2)
        except OSError as e:
            logger.error(f"❌ Impossible d'enregistrer {self.path} : {e}")

    @staticmethod
    def _clamp_cpm_step(value):
        return max(1, min(50, int(value)))

    @staticmethod
    def _clamp_hr_step(value):
        return max(1, min(20, int(value)))

    def set_cpm_step(self, value):
        """Définit le pas des boutons +/- des champs cpm (1 à 50), et sauvegarde"""
        self.cpm_step = self._clamp_cpm_step(value)
        self._save()
        return self.cpm_step

    def set_hr_step(self, value):
        """Définit le pas des boutons +/- du champ %FCmax cible (1 à 20), et sauvegarde"""
        self.hr_step = self._clamp_hr_step(value)
        self._save()
        return self.hr_step
