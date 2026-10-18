from kivy.app import App
from kivy.clock import Clock
from kivymd.toast import toast
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog

from utils.logger import get_logger

logger = get_logger(__name__)

ACTION_TIMEOUT = 8


class GameActionsController:
    """
    Enveloppe app.udp_controller pour les actions de contrôle du jeu
    (lancer/pause/reprendre/restart/retour menu/quitter), avec le
    spinner "action en cours" et les toasts communs.

    Partagé par PilotageScreen et QuickActionsBar : évite que les deux
    UI qui exposent ces actions divergent au fil des correctifs. Les
    callbacks on_action_start/on_action_end pilotent le spinner de l'UI
    hôte (chacune a le sien).
    """

    def __init__(self, on_action_start=None, on_action_end=None):
        self.on_action_start = on_action_start
        self.on_action_end = on_action_end
        self._dialog_confirm_quit = None

    @property
    def udp_controller(self):
        return App.get_running_app().udp_controller

    def run(self, envoyer, message_reussite, message_echec):
        """
        Envoie une commande de jeu et déclenche le spinner de l'UI hôte
        jusqu'à confirmation (prochain "session_updated", voir
        stop_spinner) ou timeout de secours.
        """
        if not self.udp_controller:
            return False
        success = envoyer()
        if success:
            logger.info(message_reussite)
            if self.on_action_start:
                self.on_action_start()
            Clock.unschedule(self._stop_spinner_clock)
            Clock.schedule_once(self._stop_spinner_clock, ACTION_TIMEOUT)
        else:
            toast(message_echec)
        return success

    def _stop_spinner_clock(self, *_):
        self.stop_spinner()

    def stop_spinner(self):
        Clock.unschedule(self._stop_spinner_clock)
        if self.on_action_end:
            self.on_action_end()

    def pause_game(self):
        self.run(lambda: self.udp_controller.pause_game(),
                  "⏸️ Jeu en pause", "❌ Échec de la mise en pause")

    def resume_game(self):
        self.run(lambda: self.udp_controller.resume_game(),
                  "▶️ Jeu repris", "❌ Échec de la reprise")

    def restart_game(self):
        self.run(lambda: self.udp_controller.restart_game(),
                  "🔄 Jeu redémarré", "❌ Échec du redémarrage")

    def launch_game(self):
        self.run(lambda: self.udp_controller.launch_game(),
                  "🚀 Partie lancée", "❌ Échec du lancement de la partie")

    def return_to_menu(self):
        self.run(lambda: self.udp_controller.return_to_menu(),
                  "↩️ Retour au menu", "❌ Échec du retour au menu")

    def confirm_quit_game(self):
        """Demande confirmation avant de fermer le jeu"""
        if self._dialog_confirm_quit is None:
            self._dialog_confirm_quit = MDDialog(
                title="Quitter le jeu ?",
                text="Le jeu va se fermer sur le casque.",
                buttons=[
                    MDFlatButton(
                        text="ANNULER",
                        on_release=lambda *_: self._dialog_confirm_quit.dismiss(),
                    ),
                    MDFlatButton(
                        text="QUITTER",
                        on_release=lambda *_: self._confirm_quit_game(),
                    ),
                ],
            )
        self._dialog_confirm_quit.open()

    def _confirm_quit_game(self):
        self._dialog_confirm_quit.dismiss()
        if self.udp_controller:
            success = self.udp_controller.quit_game()
            if success:
                logger.info("🚪 Jeu quitté")
            else:
                toast("❌ Échec de la fermeture du jeu")
