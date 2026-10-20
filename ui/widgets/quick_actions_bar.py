from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.stencilview import StencilView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout

from app.controllers.game_actions import GameActionsController
from utils.event_bus import event_bus
from utils.logger import get_logger

logger = get_logger(__name__)

# Distance de glissement (au-delà de laquelle un déplacement autorisé —
# voir _DRAG_HOLD_DELAY — est traité comme tel plutôt qu'un simple tap qui
# ouvre/ferme le panneau — voir HandleBar.on_touch_move).
_DRAG_THRESHOLD = dp(8)
# Durée d'appui maintenu avant que le glissement ne soit autorisé. Sans ce
# délai, un simple mouvement du doigt juste après l'appui (ex. sur
# Android) ne déclenchait jamais le glissement — l'appui maintenu lève
# l'ambiguïté avec un tap avant même de regarder le déplacement.
_DRAG_HOLD_DELAY = 1.0


class ClippedBox(StencilView, MDBoxLayout):
    """MDBoxLayout dont le contenu est découpé à sa taille, pour que le
    panneau d'actions ne dépasse pas visuellement pendant l'animation
    d'ouverture/fermeture (voir QuickActionsBar)."""


class HandleBar(ButtonBehavior, AnchorLayout):
    """
    Languette cliquable sur toute sa surface (pas seulement son icône
    chevron) — plus facile à toucher sur tablette/casque. Également
    déplaçable horizontalement le long du bas de l'écran, mais seulement
    après un appui maintenu _DRAG_HOLD_DELAY (voir on_touch_down/
    _enable_drag) : le déplacement devient alors possible au-delà de
    _DRAG_THRESHOLD, ajustant parent.handle_center_x (lié au pos_hint de
    cette languette dans le .kv) plutôt que de laisser ButtonBehavior
    déclencher on_release.

    Centrée en bas plutôt que sur un bord vertical : sur Android, un
    bord d'écran est souvent réservé aux gestes système (retour, home),
    qui interceptent le glissement avant même qu'il n'arrive à l'app.

    Pas de mémorisation d'une session à l'autre pour l'instant — la
    position revient à sa valeur par défaut à chaque redémarrage de
    l'app.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._drag_start_x = None
        self._drag_start_center_x = None
        self._dragging = False
        self._drag_allowed = False
        self._drag_allowed_event = None

    def on_touch_down(self, touch):
        handled = super().on_touch_down(touch)
        if handled and touch.grab_current is self:
            self._drag_start_x = touch.x
            self._drag_start_center_x = self.parent.handle_center_x if self.parent else 0.5
            self._dragging = False
            self._drag_allowed = False
            self._drag_allowed_event = Clock.schedule_once(self._enable_drag, _DRAG_HOLD_DELAY)
        return handled

    def _enable_drag(self, *_args):
        self._drag_allowed = True

    def on_touch_move(self, touch):
        if touch.grab_current is self and self._drag_start_x is not None:
            dx = touch.x - self._drag_start_x
            if self._drag_allowed and not self._dragging and abs(dx) > _DRAG_THRESHOLD:
                self._dragging = True
            if self._dragging and self.parent and self.parent.width:
                delta_fraction = dx / self.parent.width
                new_center_x = self._drag_start_center_x + delta_fraction
                # Marge pour que la languette ne sorte jamais de l'écran.
                margin = (self.width / 2 + dp(4)) / self.parent.width
                new_center_x = max(margin, min(1 - margin, new_center_x))
                self.parent.handle_center_x = new_center_x
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            if self._drag_allowed_event is not None:
                self._drag_allowed_event.cancel()
                self._drag_allowed_event = None
            was_dragging = self._dragging
            self._drag_start_x = None
            self._dragging = False
            self._drag_allowed = False
            if was_dragging:
                # Déplacement : on relâche sans déclencher on_release,
                # sinon le panneau s'ouvrirait/fermerait après un glisser.
                touch.ungrab(self)
                self.last_touch = touch
                self._do_release()
                return True
        return super().on_touch_up(touch)


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
    # Position horizontale de la languette (fraction 0-1 de la largeur
    # de l'écran), ajustable en la faisant glisser — voir HandleBar. Pas
    # de mémorisation entre sessions : revient à cette valeur par défaut
    # à chaque redémarrage de l'app.
    handle_center_x = NumericProperty(0.5)
    # "Restaurer la vue d'origine" n'a de sens qu'après un "Recentrer la
    # vue" — voir recenter_view()/restore_view(). Propre à cette UI,
    # comme dans PilotageScreen (ui/screens/pilotage_screen.py), qui a sa
    # propre instance de GameActionsController et ne partage donc pas cet
    # état avec elle.
    vue_recentree = BooleanProperty(False)

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

    def recenter_view(self):
        if self._game_actions.recenter_view():
            self.vue_recentree = True

    def restore_view(self):
        if self._game_actions.restore_view():
            self.vue_recentree = False

    def confirm_quit_game(self):
        self._game_actions.confirm_quit_game()
