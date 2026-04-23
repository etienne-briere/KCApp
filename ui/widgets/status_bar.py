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
from utils.event_bus import event_bus
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

        # Abonnement aux EventBus
        event_bus.subscribe("heart_rate_received", self.handle_hr_received)
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)
    
    def on_parent(self, widget, parent):
        '''Appelé automatiquement si ajout/suppresion dans l'UI'''
        # sécurité si widget retiré
        if parent is None:
            event_bus.unsubscribe("heart_rate_received", self.handle_hr_received)
            event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)

    def update_status(self, dt):

        # Récupérer les managers de l'application
        app = App.get_running_app()
        self.udp_discovery = app.udp_discovery
        self.ws_server = app.ws_server

        # Vérifier les connexions BLE et Wi-Fi
        self.ble_connected = is_bluetooth_enabled()
        self.wifi_connected = is_wifi_enabled()

         # Si pas de FC depuis 5 secondes → capteur considéré inactif
        if time() - self.last_hr_received > 3:
            self.hr_sensor_connected = False
        else:
            self.hr_sensor_connected = True
    
    # ========== CALLBACKS UDP ==========
    
    def handle_unity_connection(self, data):
        """Callback quand Unity se connecte ou se déconnecte"""
        ip = data.get("ip")
        self.unity_connected = data["connected"]
        
        if self.unity_connected:
            toast(f"Unity connected ({ip})")
        else :
            toast("Unity disconnected")
    
    # ========== CALLBACKS HR ==========
    
    def handle_hr_received(self, bpm):
        """Callback quand FC reçue"""
        logger.debug(f"📊 Nouvelle donnée: {bpm} BPM.")

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