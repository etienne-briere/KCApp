from kivymd.uix.screen import MDScreen
from kivymd.toast import toast
from kivy.app import App

from utils.logger import get_logger

logger = get_logger(__name__)


class SettingsScreen(MDScreen):
    """Réglages par défaut de l'application (pas des boutons +/-, etc.)"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = App.get_running_app()
        self.settings_store = app.settings_store

    def on_hr_step_submit(self, text):
        """Champ pas %FCmax validé"""
        try:
            value = int(text)
        except ValueError:
            toast("Valeur invalide")
            self.ids.hr_step_field.text = str(self.settings_store.hr_step)
            return

        value = self.settings_store.set_hr_step(value)
        self.ids.hr_step_field.text = str(value)
        logger.info(f"🔧 Pas %FCmax cible : {value}")

    def on_cpm_step_submit(self, text):
        """Champ pas cadence (cpm) validé"""
        try:
            value = int(text)
        except ValueError:
            toast("Valeur invalide")
            self.ids.cpm_step_field.text = str(self.settings_store.cpm_step)
            return

        value = self.settings_store.set_cpm_step(value)
        self.ids.cpm_step_field.text = str(value)
        logger.info(f"🔧 Pas cadence (cpm) : {value}")
