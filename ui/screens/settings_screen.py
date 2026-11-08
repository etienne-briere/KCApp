from kivymd.uix.screen import MDScreen
from kivymd.toast import toast
from kivy.app import App
from kivy.properties import NumericProperty

from utils.logger import get_logger

logger = get_logger(__name__)


class SettingsScreen(MDScreen):
    """Réglages par défaut de l'application (pas des boutons +/-, fluidité/qualité d'image, etc.)"""

    fps_choice = NumericProperty(0)    # img/s par défaut (bouton sélectionné)
    width_choice = NumericProperty(0)  # largeur par défaut en px (bouton sélectionné)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = App.get_running_app()
        self.settings_store = app.settings_store
        self.stream_settings = app.stream_settings
        self.fps_choice = self.stream_settings.fps
        self.width_choice = self.stream_settings.width

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

    def set_stream_option(self, fps=None, width=None):
        """Fluidité/qualité d'image par défaut (Vue du joueur) — même logique que GameScreen.set_stream_option"""
        if fps is not None:
            self.fps_choice = self.stream_settings.fps = int(fps)
            logger.info(f"🔧 Fluidité par défaut : {fps} img/s")
        if width is not None:
            self.width_choice = self.stream_settings.width = int(width)
            logger.info(f"🔧 Qualité d'image par défaut : {width} px")
        self.stream_settings.save()
