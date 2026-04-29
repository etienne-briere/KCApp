import asyncio
from time import time

from kivy.properties import BooleanProperty, StringProperty, ListProperty
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
    hr_data_sent = BooleanProperty(False)
    hr_icon_color = ListProperty([1, 0, 0, 1])  # rouge par défaut

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_hr_received = 0

    def on_kv_post(self, base_widget):

        Clock.schedule_interval(self.update_status, 2)

        # Abonnement aux EventBus
        event_bus.subscribe("heart_rate_received", self.handle_hr_received)
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.subscribe("hr_data_sent", self.handle_hr_sent)
    
    def on_parent(self, widget, parent):
        '''Appelé automatiquement si ajout/suppresion dans l'UI'''
        # sécurité si widget retiré
        if parent is None:
            event_bus.unsubscribe("heart_rate_received", self.handle_hr_received)
            event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)
            event_bus.unsubscribe("hr_data_sent", self.handle_hr_sent)

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
    
    # ========== CALLBACKS ==========
    
    def handle_unity_connection(self, data):
        """Callback quand Unity se connecte ou se déconnecte"""
        ip = data.get("ip")
        self.unity_connected = data["connected"]
        
        if self.unity_connected:
            toast(f"Unity connected ({ip})")
        else :
            toast("Unity disconnected")
        
    def handle_hr_received(self, bpm):
        """Callback quand FC reçue"""

        # Mettre à jour le timestamp de la dernière FC reçue
        self.last_hr_received = time()
    
    def handle_hr_sent (self, data):
        self.hr_data_sent = data

    # # ========== GESTION WEBSOCKET ==========
    
    # async def _start_server(self):
    #     """Démarre le serveur WebSocket"""
    #     success = await self.ws_server.start()

    #     if success:
    #         toast("Adaptive mode ON")
    #     else:
    #         toast("Adaptive mode failed to start")
            
    # async def _stop_server(self):
    #     """Arrête le serveur WebSocket"""
    #     await self.ws_server.stop()
    #     toast("Adaptive mode OFF")
    

    # === Gestion de l'icône HR ===
    def on_hr_sensor_connected(self, *args):
        self.update_hr_color()

    def on_hr_data_sent(self, *args):
        self.update_hr_color()

    def update_hr_color(self):
        if not self.hr_sensor_connected:
            self.hr_icon_color = (1, 0, 0, 1) # rouge
        elif self.hr_data_sent:
            self.hr_icon_color = (0, 1, 0, 1) # vert
        else:
            self.hr_icon_color = (1, 1, 0, 1) # jaune