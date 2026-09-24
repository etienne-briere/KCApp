from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty
from kivy.app import App
from utils.logger import get_logger
from kivy.clock import Clock
from kivy.clock import mainthread
from kivymd.toast import toast
from utils.event_bus import event_bus

from app.network.connectivity import is_wifi_enabled, get_wifi_ssid


logger = get_logger(__name__)

# Couleurs du badge d'état de partie (mêmes valeurs que GREEN/AMBER/BLUE
# _FG/_BG dans status_bar.kv) — calculées ici plutôt qu'avec un ternaire en
# kv sur root.game_state.lower(), qui ne se rebindait pas de façon fiable.
_GAME_STATE_COLORS = {
    "playing": {"fg": (0.176, 0.490, 0.196, 1), "bg": (0.906, 0.961, 0.914, 1)},
    "paused": {"fg": (0.780, 0.518, 0.047, 1), "bg": (1, 0.976, 0.882, 1)},
    # "Menu" : le joueur est connecté mais pas encore dans la scène de jeu.
    "menu": {"fg": (0.098, 0.463, 0.824, 1), "bg": (0.890, 0.949, 0.992, 1)},
}
_GAME_STATE_DEFAULT_COLOR = {"fg": (0.459, 0.459, 0.459, 1), "bg": (0.925, 0.925, 0.925, 1)}


class HomeScreen(MDScreen):
    """Écran d'accueil"""

    unity_connected = BooleanProperty(False)
    unity_ip = StringProperty("")
    wifi_connected = BooleanProperty(False)
    wifi_ssid = StringProperty("")
    hr_sensor_connected = BooleanProperty(False)
    hr_data_sent = BooleanProperty(False)
    hr_sensor_name = StringProperty("")
    heart_rate_text = StringProperty("--")
    selected_model = StringProperty("Unknown")
    age_user = StringProperty("Unknown")
    # Feedback spécifique au mode de jeu en cours (voir _update_mode_feedback) :
    # cpm en Fixe, paliers + plage cpm en Incrémental, %FC cible en PID/DRL.
    mode_feedback_icon = StringProperty("target")
    mode_feedback_text = StringProperty("Unknown")
    # Défaut volontairement non vide : le mode Fixe remet ce texte à "" ; si
    # la valeur par défaut était déjà "", ce premier appel ne changerait
    # rien, Kivy ne déclencherait jamais on_text sur le MDLabel lié, et son
    # calcul de texture (donc sa taille) resterait indéterminé — décalant
    # verticalement le BoxLayout qui l'englobe (adaptive_size sur une
    # hauteur jamais recalculée). Ne pas remettre "" ici.
    mode_feedback_subtext = StringProperty("Unknown")
    player_name = StringProperty("")
    game_state = StringProperty("Menu")
    game_state_fg = ListProperty(_GAME_STATE_DEFAULT_COLOR["fg"])
    game_state_bg = ListProperty(_GAME_STATE_DEFAULT_COLOR["bg"])
    session_remaining_text = StringProperty("--:--")

    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        app = App.get_running_app()

        # Managers
        self.udp_discovery = app.udp_discovery
        self.udp_controller = app.udp_controller
        self.session = app.session

        # Vérifier la connexion Unity (au cas où on arrive dans l'écran après la connexion)
        self.unity_connected = self.udp_discovery.is_unity_connected()
        self.unity_ip = self.udp_discovery.ip_unity or ""

        # Refléter l'état Wi-Fi courant (mis à jour ensuite via l'event bus)
        self.wifi_connected = is_wifi_enabled()
        self.wifi_ssid = (get_wifi_ssid() or "") if self.wifi_connected else ""

        # Refléter l'état FC courant : StatusBar tourne en permanence (quel
        # que soit l'écran affiché) et est la seule source à connaître le
        # délai depuis la dernière trame FC reçue — on se resynchronise sur
        # elle ici, sinon la bannière resterait figée sur sa dernière valeur
        # si le capteur s'est (dé)connecté pendant qu'on était sur un autre
        # écran (ex. Sensor, où se fait l'appairage BLE).
        # `app.root` n'existe pas encore au tout premier `on_enter` (déclenché
        # pendant la construction du kv, avant l'affectation de app.root) —
        # sans conséquence puisqu'à ce stade le capteur n'est de toute façon
        # pas connecté.
        if app.root:
            status_bar = app.root.ids.status_bar
            self.hr_sensor_connected = status_bar.hr_sensor_connected
            self.hr_data_sent = status_bar.hr_data_sent
        connected_device = app.ble_manager.connected_device
        self.hr_sensor_name = (connected_device.name or connected_device.address) if connected_device else ""
        if self.unity_connected :
            self.selected_model = self.session.config.model
            self.age_user = str(self.session.user_profile.age)
            self._update_mode_feedback(self.session.config)
            self.player_name = self.session.user_profile.name
            self._set_game_state(self.session.game_state)
            self._refresh_session_remaining()

        # S'abonner pour écouter les eventbus
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.subscribe("session_updated", self.on_session_updated)
        event_bus.subscribe("wifi_status_changed", self.handle_wifi_status)
        event_bus.subscribe("hr_sensor_status_changed", self.handle_hr_sensor_status)
        event_bus.subscribe("heart_rate_received", self.handle_heart_rate_received)
        event_bus.subscribe("connection_changed", self.handle_connection_changed)

        # Tick d'affichage du décompte (recalcule chaque seconde à partir
        # de session.get_remaining_seconds(), qui reste correct même quand
        # cet écran n'était pas affiché — voir _refresh_session_remaining)
        Clock.schedule_interval(self._refresh_session_remaining, 1)

    def on_leave(self):
        event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.unsubscribe("session_updated", self.on_session_updated)
        event_bus.unsubscribe("wifi_status_changed", self.handle_wifi_status)
        event_bus.unsubscribe("hr_sensor_status_changed", self.handle_hr_sensor_status)
        event_bus.unsubscribe("heart_rate_received", self.handle_heart_rate_received)
        event_bus.unsubscribe("connection_changed", self.handle_connection_changed)
        Clock.unschedule(self._refresh_session_remaining)

    # ========== CALLBACKS UDP ==========

    @mainthread
    def handle_unity_connection(self, data):
        connected = data["connected"]
        self.unity_connected = connected
        self.unity_ip = data.get("ip") or ""
    
    @mainthread
    def handle_wifi_status(self, data):
        self.wifi_connected = data["connected"]
        self.wifi_ssid = data["ssid"]

    @mainthread
    def handle_hr_sensor_status(self, data):
        self.hr_sensor_connected = data["connected"]
        self.hr_data_sent = data["data_sent"]
        if not self.hr_sensor_connected:
            self.heart_rate_text = "--"

    def handle_heart_rate_received(self, bpm):
        """Callback quand une trame FC est reçue"""
        self.heart_rate_text = f"{bpm}"

    def handle_connection_changed(self, data):
        """Callback de (dé)connexion BLE : garde le nom du capteur à jour"""
        device = data["device"]
        if data["is_connected"] and device:
            self.hr_sensor_name = device.name or device.address
        elif not data["is_connected"]:
            self.hr_sensor_name = ""

    def on_session_updated(self, session):
         # Mise à jour UI
        self.selected_model = session.config.model
        self.age_user = str(session.user_profile.age)
        self._update_mode_feedback(session.config)
        self.player_name = session.user_profile.name
        self._set_game_state(session.game_state)
        self._refresh_session_remaining()

    def _set_game_state(self, raw_state):
        """Met à jour le label d'état ET les couleurs du badge associées."""
        raw_state = raw_state or "Idle"
        self.game_state = raw_state.capitalize()
        colors = _GAME_STATE_COLORS.get(raw_state.lower(), _GAME_STATE_DEFAULT_COLOR)
        self.game_state_fg = colors["fg"]
        self.game_state_bg = colors["bg"]

    def _update_mode_feedback(self, config):
        """
        Met à jour l'icône/texte affichés dans la card "Session en cours"
        selon le mode de jeu : cpm en Fixe, paliers + plage cpm en
        Incrémental, %FC cible + plage cpm adaptative en PID/DRL (seuls
        modes où Unity reçoit réellement une cible FC).
        """
        model = config.model
        self.mode_feedback_subtext = ""

        if model == "FIXE":
            self.mode_feedback_icon = "speedometer"
            cpm = config.cube_per_min
            self.mode_feedback_text = f"{int(cpm)} cpm" if cpm is not None else "-- cpm"

        elif model == "INCREMENTAL":
            self.mode_feedback_icon = "stairs"
            steps = config.incremental_steps
            min_cpm = config.incremental_min_cpm
            max_cpm = config.incremental_max_cpm

            # L'icône "stairs" porte déjà le sens de "paliers" — pas besoin
            # de le répéter en toutes lettres, juste le nombre.
            self.mode_feedback_text = str(int(steps)) if steps is not None else "--"
            if min_cpm is not None and max_cpm is not None:
                self.mode_feedback_subtext = f"{int(min_cpm)}-{int(max_cpm)} cpm"

        else:
            self.mode_feedback_icon = "target"
            target = config.target_hr_percent
            self.mode_feedback_text = f"{int(target)} %" if target is not None else "Unknown"

            min_cpm = config.adaptive_min_cpm
            max_cpm = config.adaptive_max_cpm
            if min_cpm is not None and max_cpm is not None:
                self.mode_feedback_subtext = f"{int(min_cpm)}-{int(max_cpm)} cpm"

    def _refresh_session_remaining(self, *_):
        """
        Rafraîchit l'affichage du temps de session restant.

        Le calcul lui-même (ancrage sur la transition vers "Playing", suivi
        des pauses) vit dans GameSession.get_remaining_seconds() — mis à
        jour en continu depuis le thread UDP (udp_discovery.py), donc
        toujours correct même quand cet écran n'est pas affiché. Ici on ne
        fait que lire cette valeur pour l'afficher ; en "Paused" (ou état
        inconnu), get_remaining_seconds() renvoie None et on garde la
        dernière valeur affichée telle quelle.
        """
        session = getattr(self, "session", None)
        if session is None or not self.unity_connected:
            return

        remaining = session.get_remaining_seconds()
        if remaining is not None:
            self.session_remaining_text = self._format_duration(remaining)

    @staticmethod
    def _format_duration(total_seconds):
        if total_seconds is None:
            return "--:--"
        total_seconds = max(0, int(total_seconds))
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    # ===== Foncions reliées à l'UI =====
    def force_reconnect(self):
        """Bouton pour forcer la reconnexion"""
        app = App.get_running_app()

        # Forcer la reconnexion en arrêtant le serveur WebSocket et en redémarrant la découverte UDP
        app.ws_server.stop()
        app.udp_discovery.force_reconnect()
        self.unity_connected = False

    # ===== Actions rapides du jeu (sécurité pendant la session) =====
    def pause_game(self):
        """Met le jeu en pause"""
        if self.udp_controller:
            success = self.udp_controller.pause_game()
            if success:
                logger.info("⏸️ Jeu en pause")
            else:
                toast("❌ Échec de la mise en pause")

    def resume_game(self):
        """Reprend le jeu"""
        if self.udp_controller:
            success = self.udp_controller.resume_game()
            if success:
                logger.info("▶️ Jeu repris")
            else:
                toast("❌ Échec de la reprise")

    def restart_game(self):
        """Redémarre le jeu"""
        if self.udp_controller:
            success = self.udp_controller.restart_game()
            if success:
                logger.info("🔄 Jeu redémarré")
            else:
                toast("❌ Échec du redémarrage")