import time
import unicodedata

from kivy.app import App
from kivy.clock import Clock
from kivy.utils import platform
from kivymd.toast import toast
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog

from utils.logger import get_logger

logger = get_logger(__name__)

ACTION_TIMEOUT = 8
# Durée minimum d'affichage du toast "action en cours", pour qu'il reste
# lisible même si la confirmation (session_updated) arrive très vite.
MIN_TOAST_DURATION = 2


def _strip_emoji_prefix(text):
    """
    Les messages ci-dessous commencent par un emoji (lisible dans les
    logs), mais la police par défaut de Kivy ne les a pas : à l'écran, un
    toast les affiche comme un cadre avec une croix. On ne garde ce
    préfixe que pour les logs, pas pour ce qui est affiché à l'utilisateur.
    """
    i = 0
    while i < len(text):
        char = text[i]
        if char.isspace() or char == "️" or unicodedata.category(char).startswith("S"):
            i += 1
            continue
        break
    return text[i:]


class _DismissableToast:
    """
    Toast qu'on peut faire disparaître avant son délai normal, dès qu'une
    confirmation arrive (ou au timeout de secours) — contrairement à
    kivymd.toast.toast(), qui s'efface toujours après une durée fixe.
    Reste cependant affiché au moins MIN_TOAST_DURATION, même si dismiss()
    est appelé avant (voir dismiss()).

    Sur Android, le toast natif (android.widget.Toast) n'a pas de délai
    réglable à volonté ; on force une durée longue et on le fait
    disparaître plus tôt via cancel() dès que possible.
    """

    def __init__(self):
        self._kivy_toast = None
        self._android_toast = None
        self._shown_at = None

    def show(self, text):
        Clock.unschedule(self._deferred_dismiss)
        self._dismiss_now()
        self._shown_at = time.monotonic()
        if platform == "android":
            self._show_android(text)
        else:
            self._show_kivy(text)

    def _show_kivy(self, text):
        from kivymd.toast.kivytoast.kivytoast import Toast

        self._kivy_toast = Toast(duration=ACTION_TIMEOUT + 1, _md_bg_color=[0.2, 0.2, 0.2, 1])
        self._kivy_toast.toast(text)

    def _show_android(self, text):
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        JToast = autoclass("android.widget.Toast")
        JString = autoclass("java.lang.String")

        @run_on_ui_thread
        def _make():
            android_toast = JToast.makeText(activity, JString(text), JToast.LENGTH_LONG)
            android_toast.show()
            self._android_toast = android_toast

        _make()

    def dismiss(self):
        """
        Referme le toast, sauf s'il est affiché depuis moins de
        MIN_TOAST_DURATION : dans ce cas, le retrait est reporté pour
        qu'il reste visible le temps minimum voulu.
        """
        if self._shown_at is None:
            return
        remaining = MIN_TOAST_DURATION - (time.monotonic() - self._shown_at)
        if remaining > 0:
            Clock.unschedule(self._deferred_dismiss)
            Clock.schedule_once(self._deferred_dismiss, remaining)
        else:
            self._dismiss_now()

    def _deferred_dismiss(self, *_args):
        self._dismiss_now()

    def _dismiss_now(self):
        Clock.unschedule(self._deferred_dismiss)
        self._shown_at = None
        if self._kivy_toast is not None:
            self._kivy_toast.fade_out()
            self._kivy_toast = None
        if self._android_toast is not None:
            from android.runnable import run_on_ui_thread

            android_toast = self._android_toast

            @run_on_ui_thread
            def _cancel():
                android_toast.cancel()

            _cancel()
            self._android_toast = None


class GameActionsController:
    """
    Enveloppe app.udp_controller pour les actions de contrôle du jeu
    (lancer/pause/reprendre/restart/retour menu/quitter), avec le toast
    "action en cours" (voir _DismissableToast) et les toasts d'échec
    communs.

    Partagé par PilotageScreen et QuickActionsBar : évite que les deux
    UI qui exposent ces actions divergent au fil des correctifs. Les
    callbacks on_action_start/on_action_end restent disponibles pour
    piloter un indicateur supplémentaire propre à l'UI hôte (ex. le
    spinner de la Card "Actions du jeu" de PilotageScreen).
    """

    def __init__(self, on_action_start=None, on_action_end=None):
        self.on_action_start = on_action_start
        self.on_action_end = on_action_end
        self._dialog_confirm_quit = None
        self._action_toast = _DismissableToast()

    @property
    def udp_controller(self):
        return App.get_running_app().udp_controller

    def run(self, envoyer, message_reussite, message_echec):
        """
        Envoie une commande de jeu et affiche un toast "action en cours"
        jusqu'à confirmation (prochain "session_updated", voir
        stop_spinner) ou timeout de secours.
        """
        if not self.udp_controller:
            return False
        success = envoyer()
        if success:
            logger.info(message_reussite)
            self._action_toast.show(_strip_emoji_prefix(message_reussite))
            if self.on_action_start:
                self.on_action_start()
            Clock.unschedule(self._stop_spinner_clock)
            Clock.schedule_once(self._stop_spinner_clock, ACTION_TIMEOUT)
        else:
            toast(_strip_emoji_prefix(message_echec))
        return success

    def _stop_spinner_clock(self, *_):
        self.stop_spinner()

    def stop_spinner(self):
        Clock.unschedule(self._stop_spinner_clock)
        self._action_toast.dismiss()
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
                toast(_strip_emoji_prefix("❌ Échec de la fermeture du jeu"))
