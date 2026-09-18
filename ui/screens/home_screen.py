from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.app import App
from utils.logger import get_logger
from kivy.clock import Clock
from kivy.clock import mainthread
from utils.event_bus import event_bus
from kivymd.toast import toast

from app.network.connectivity import is_wifi_enabled, get_wifi_ssid


logger = get_logger(__name__)

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
    hr_target = StringProperty("Unknown")
    age_user = StringProperty("Unknown")

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
            self.hr_target = f"{self.session.config.target_hr_percent} %"

        # S'abonner pour écouter les eventbus
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.subscribe("session_updated", self.on_session_updated)
        event_bus.subscribe("wifi_status_changed", self.handle_wifi_status)
        event_bus.subscribe("hr_sensor_status_changed", self.handle_hr_sensor_status)
        event_bus.subscribe("heart_rate_received", self.handle_heart_rate_received)
        event_bus.subscribe("connection_changed", self.handle_connection_changed)

    def on_leave(self):
        event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.unsubscribe("session_updated", self.on_session_updated)
        event_bus.unsubscribe("wifi_status_changed", self.handle_wifi_status)
        event_bus.unsubscribe("hr_sensor_status_changed", self.handle_hr_sensor_status)
        event_bus.unsubscribe("heart_rate_received", self.handle_heart_rate_received)
        event_bus.unsubscribe("connection_changed", self.handle_connection_changed)

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
        self.hr_target = f"{session.config.target_hr_percent} %"

    # ===== Foncions reliées à l'UI =====
    def force_reconnect(self):
        """Bouton pour forcer la reconnexion"""
        app = App.get_running_app()

        # Forcer la reconnexion en arrêtant le serveur WebSocket et en redémarrant la découverte UDP
        app.ws_server.stop()
        app.udp_discovery.force_reconnect()
        self.unity_connected = False
    
    def send_new_age(self):
        app = App.get_running_app()

        try:
            age = int(self.ids.age_input.text)

            if 5 <= age <= 100:  # validation logique
                app.user_profile.age = age
                print("Age mis à jour :", age)

                # Envoyer via UDP
                if self.udp_controller:
                    self.udp_controller.set_age_player(age)

            else:
                toast("Age invalide")
        except ValueError:
            print("Entrée âge invalide")
            toast("Age invalide")