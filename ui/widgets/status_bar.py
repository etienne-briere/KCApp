import asyncio
from time import time

from kivy.properties import BooleanProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.toast import toast

from app.network.connectivity import is_bluetooth_enabled, is_wifi_enabled
from kivy.clock import Clock
from kivy.app import App
from kivy.animation import Animation

# Logger
from utils.logger import get_logger

logger = get_logger(__name__)

class StatusBar(MDBoxLayout):
    """
    Widget pour afficher l'état BLE, Wi-Fi et capteur FC.
    Les icônes changent automatiquement selon les propriétés.
    """
    ble_connected = BooleanProperty(False)
    wifi_connected = BooleanProperty(False)
    hr_sensor_connected = BooleanProperty(False)
    unity_connected = BooleanProperty(False)
    adaptive_mode_enabled = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_hr_received = 0

    def on_kv_post(self, base_widget):
        Clock.schedule_interval(self.update_status, 2)
        # Vérification régulière du timeout HR
        # Clock.schedule_interval(self.check_hr_timeout, 1)

    def update_status(self, dt):

        # Récupérer les managers de l'application
        app = App.get_running_app()
        self.ble_manager = app.ble_manager
        self.udp_discovery = app.udp_discovery
        self.ws_server = app.ws_server
        
        # callbacks UDP
        self.udp_discovery.on_unity_connected2 = self.handle_unity_connected
        self.udp_discovery.on_unity_disconnected2 = self.handle_unity_disconnected

        # callback pour recevoir la FC en temps réel
        self.ble_manager.on_hr_received = self.handle_hr_received

        # Callbacks WebSocket
        self.ws_server.on_client_connected = self.on_ws_client_connected
        self.ws_server.on_client_disconnected = self.on_ws_client_disconnected

        # Vérifier les connexions BLE et Wi-Fi
        self.ble_connected = is_bluetooth_enabled()
        self.wifi_connected = is_wifi_enabled()

        # Vérifier la connexion Unity
        self.unity_connected = self.udp_discovery.is_unity_connected()

        # Vérifier la connexion du capteur de FC
        self.hr_sensor_connected = self.ble_manager.is_connected
    
    # ========== CALLBACKS UDP ==========

    def handle_unity_connected(self, ip_unity: str, dt=0):
        """Callback quand Unity se connecte"""
        if not self.unity_connected:
            self.unity_connected = True
            toast("Unity connected")
            
    def handle_unity_disconnected(self, dt=0):
        """Callback quand Unity se déconnecte"""
        if self.unity_connected:
            self.unity_connected = False
            toast("Unity disconnected")
    
    # ========== CALLBACKS HR ==========
    
    def handle_hr_received(self, bpm):
        """Callback quand FC reçue"""
        logger.debug(f"📊 Nouvelle donnée: {bpm} BPM.")

        # Notif que le capteur est connecté
        # self.hr_sensor_connected = True

        # Mettre à jour le timestamp de la dernière FC reçue
        self.last_hr_received = time()

        print(f"Unity connected: {self.unity_connected}, Adaptive mode: {self.adaptive_mode_enabled}, WS running: {self.ws_server.is_running}")
        if self.adaptive_mode_enabled and self.unity_connected:
            if not self.ws_server.is_running:
                # # Activer le serveur WebSocket
                asyncio.ensure_future(self._start_server())
                
                # Notifier Unity du démarrage du serveur websocket
                if self.udp_discovery:
                    self.udp_discovery.send_message("command_ws", "1")

        if self.ws_server.is_running:
            # Envoyer les données FC via WebSocket
            asyncio.ensure_future(self.ws_server.send_data_to_clients(bpm))
        
        if not self.unity_connected and self.ws_server.is_running:
            # désactiver le serveur WebSocket
            asyncio.ensure_future(self._stop_server())

            # # Notifier Unity de l'arrêt du serveur websocket
            # if self.udp_discovery:
            #     self.udp_discovery.send_message("command_ws", "0")
    
    # def check_hr_timeout(self, dt):
    #     """Vérifie si HR n’a plus été reçu depuis 2 secondes"""
    #     if self.hr_sensor_connected:
    #         elapsed = time() - self.last_hr_received
    #         if elapsed > 2:  # 2 secondes sans ping
    #             self.hr_sensor_connected = False
    #             if hasattr(self.ids, 'hr_icon'):
    #                 self.ids.hr_icon.icon = "heart-off"
    #                 self.ids.hr_icon.opacity = 1
    #                 Animation.cancel_all(self.ids.hr_icon)
    
    # ========== CALLBACKS WEBSOCKET ==========
    
    def on_ws_client_connected(self, websocket):
        """Callback quand un client se connecte"""
        print(f"🔗 [WS] Client Unity connecté")
        self.adaptive_mode_enabled = True
        
    def on_ws_client_disconnected(self, websocket):
        """Callback quand un client se déconnecte"""
        print(f"🔌 [WS] Client Unity déconnecté")

    # ========== GESTION WEBSOCKET ==========
    
    async def _start_server(self):
        """Démarre le serveur WebSocket"""
        success = await self.ws_server.start()

        if success:
            toast("Adaptive mode ON")
        else:
            toast("Adaptive mode failed to start")
            
    async def _stop_server(self):
        """Arrête le serveur WebSocket"""
        await self.ws_server.stop()
        toast("Adaptive mode OFF")