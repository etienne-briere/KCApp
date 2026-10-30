from kivy.app import App
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.stencilview import StencilView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout

from app.controllers.game_actions import GameActionsController
from utils.event_bus import event_bus
from utils.logger import get_logger

logger = get_logger(__name__)


class ClippedBox(StencilView, MDBoxLayout):
    """MDBoxLayout dont le contenu est découpé à sa taille, pour que le
    panneau d'actions ne dépasse pas visuellement pendant l'animation
    d'ouverture/fermeture (voir QuickActionsBar)."""


class HandleBar(ButtonBehavior, AnchorLayout):
    """Languette cliquable sur toute sa surface (pas seulement son icône
    chevron) — plus facile à toucher sur tablette/casque."""


class QuickActionsBar(MDFloatLayout):
    """
    Barre d'actions rapides repliée par défaut (languette centrée en bas
    de la zone d'écran, juste au-dessus de la navigation), dépliable
    depuis n'importe quel écran pour lancer/piloter la partie sans
    passer par l'écran Pilotage.

    Vit au même niveau que le ScreenManager (voir ui/kv/main.kv), donc
    au-dessus de l'écran affiché peu importe lequel : elle s'abonne
    elle-même à l'event_bus dès son montage (même mécanisme que
    StatusBar), indépendamment du cycle on_enter/on_leave d'un écran.
    """

    is_open = BooleanProperty(False)
    game_state = StringProperty("disconnected")
    unity_connected = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Partagé avec PilotageScreen (voir ui/screens/pilotage_screen.py)
        # pour que les deux UI qui exposent ces actions restent cohérentes.
        # Pas de callback on_action_start/on_action_end ici : le toast
        # "action en cours" de GameActionsController suffit, pas besoin
        # d'un spinner propre à la languette.
        self._game_actions = GameActionsController()

    def on_kv_post(self, base_widget):
        app = App.get_running_app()
        session = getattr(app, "session", None)
        if session is not None:
            self.game_state = session.game_state.capitalize()
        udp_discovery = getattr(app, "udp_discovery", None)
        if udp_discovery is not None:
            self.unity_connected = udp_discovery.is_unity_connected()

        event_bus.subscribe("session_updated", self.on_session_updated)
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)

    def on_parent(self, widget, parent):
        """Sécurité si le widget est retiré (comme StatusBar)."""
        if parent is None:
            event_bus.unsubscribe("session_updated", self.on_session_updated)
            event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)

    def toggle(self):
        self.is_open = not self.is_open

    def close(self):
        self.is_open = False

    # ========== CALLBACKS ==========

    def on_session_updated(self, session):
        self.game_state = session.game_state.capitalize()
        # Un nouvel état confirme que Unity a bien traité la dernière
        # commande envoyée — inutile d'attendre le timeout de secours.
        self._game_actions.stop_spinner()

    def handle_unity_connection(self, data):
        self.unity_connected = data["connected"]

    # ========== ACTIONS DU JEU ==========
    # Logique commune (envoi UDP, spinner, toast d'échec, confirmation de
    # sortie) dans GameActionsController (self._game_actions).

    def launch_game(self):
        self._game_actions.launch_game()

    def pause_game(self):
        self._game_actions.pause_game()

    def resume_game(self):
        self._game_actions.resume_game()

    def restart_game(self):
        self._game_actions.restart_game()

    def return_to_menu(self):
        self._game_actions.return_to_menu()

    def refresh_config(self):
        self._game_actions.refresh_config()

    def confirm_quit_game(self):
        self._game_actions.confirm_quit_game()
