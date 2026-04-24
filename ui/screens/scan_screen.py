# Class KivyMD
from kivymd.uix.screen import MDScreen
from kivymd.uix.menu import MDDropdownMenu

# Class Kivy
from kivy.app import App
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.animation import Animation
from kivy.metrics import sp
from kivy.clock import Clock

# Custom modules
from app import data
from utils.event_bus import event_bus
from utils.logger import get_logger
logger = get_logger(__name__)

# BLE library
import asyncio

class ScanScreen(MDScreen):
    '''
    ECRAN DU SCAN BLE
    '''

    # Properties pour la mise à jour dynamique de l'UI (reconnu dans .kv avec root)
    heart_rate_text = StringProperty("--")
    battery_text = StringProperty("-- %")
    battery_icon = StringProperty("battery-high")
    battery_color = ListProperty([0, 1, 0, 1])  # Vert par défaut
    
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Liste vide des appareils BLE
        self.devices_found = []

    def on_enter(self):
        '''
        Activer dès l'ouverture de l'écran
        '''

        # Récupérer les managers de l'application
        app = App.get_running_app()
        self.ble_manager = app.ble_manager
        self.hr_session = app.hr_session

        # S'abonner aux événements globaux (EventBus) pour recevoir les données de FC et batterie
        event_bus.subscribe("heart_rate_received", self.on_heart_rate_received) 
        event_bus.subscribe("battery_received", self.on_battery_received)
        event_bus.subscribe("connection_changed", self.on_connection_changed)
        event_bus.subscribe("scan_completed", self.on_scan_complete)
    
    def on_leave(self):
        """Sortie de l'écran"""

        # Nettoyer les callbacks pour éviter les fuites de mémoire et les appels indésirables
        event_bus.unsubscribe("heart_rate_received", self.on_heart_rate_received)
        event_bus.unsubscribe("battery_received", self.on_battery_received)
        event_bus.unsubscribe("connection_changed", self.on_connection_changed)
        event_bus.unsubscribe("scan_completed", self.on_scan_complete)

    # ========== SCAN ==========
    
    def start_ble_scan(self):
        """Démarrer le scan BLE"""
        self.update_button_state("scanning")
        asyncio.ensure_future(self._scan())
    
    async def _scan(self):
        """Lance le scan BLE"""
        # Déconnecter si déjà connecté
        if self.ble_manager.is_connected:
            self.update_button_state("disconnecting")
            self.update_heart_rate("--")
            self.update_battery("--")
            await self.ble_manager.disconnect()
            self.update_button_state("scanning")
        
        # Lancer le scan
        await self.ble_manager.scan_devices()
    
    def on_scan_complete(self, devices):
        """Callback de fin de scan"""
        if not devices:
            self.update_button_state("no_devices")
            self.devices_found = []
        else:
            self.devices_found = devices
            count = len(devices)
            self.ids.devices_list_button.text = f"{count} device{'s' if count > 1 else ''} found"
            self.ids.devices_list_button.icon = "menu-swap"
            self.ids.devices_list_button.icon_color = "white"
            self.ids.devices_list_button.line_color = "white"

    # ========== MENU ==========
    
    def open_devices_menu(self, caller_button):
        """Ouvre le menu des appareils"""
        devices = self.devices_found
        
        if not devices:
            return
        
        menu_items = [
            {"text": d.name, "on_release": lambda x=d: self.on_device_selected(x)}
            for d in devices
        ]
        
        self.devices_menu = MDDropdownMenu(
            caller=caller_button,
            items=menu_items,
            width_mult=4
        )
        self.devices_menu.open()
    
    def on_device_selected(self, device):
        """Appareil sélectionné"""
        self.devices_menu.dismiss()
        asyncio.create_task(self._connect(device))

    # ========== CONNEXION ==========
    
    async def _connect(self, device):
        """Se connecte à un appareil"""
        self.update_button_state("connecting", device.name)
        await self.ble_manager.connect_to_device(device)
    
    def on_connection_changed(self, data):
        """Callback de changement de connexion"""
        # data contient {"is_connected": bool, "device": device}
        is_connected = data["is_connected"]
        device = data["device"]
        
        if is_connected:
            # Démarrer l'enregistrement des données FC
            self.hr_session.start_recording()
            self.update_button_state("connected", device.name)
        else:
            # Arrêter l'enregistrement des données FC
            self.hr_session.stop_recording()
            self.update_button_state("disconnected")
    
    # ========== DATA ==========
    
    def on_heart_rate_received(self, bpm):
        """Callback quand FC reçue"""
        
        self.ids.heart_rate_label.text = f"{bpm}"   
        
    def calculate_hr_percent(self, bpm: int) -> float:
        """Calcule le % de FCmax"""
        app = App.get_running_app()
        max_hr = app.user_profile.calculate_max_hr()
        return (bpm / max_hr) * 100
    
    def on_battery_received(self, level):
        """Callback batterie"""
        self.ids.battery_label.text = f"{level} %"
        if level != "--":
            self.update_battery_icon(level)
    
    # ========== UI HELPERS ==========
    
    def update_button_state(self, state, device_name=None):
        """Met à jour l'état du bouton"""
        button = self.ids.devices_list_button
        
        states = {
            "scanning": ("Scanning for devices…", "bluetooth-transfer", "orange"),
            "disconnecting": ("Disconnecting...", "bluetooth-off", "red"),
            "no_devices": ("No devices found", "bluetooth-off", "red"),
            "connecting": (f"Connecting to {device_name}...", "bluetooth-transfer", "orange"),
            "connected": (f"Connected to {device_name}!", "bluetooth-connect", [0, 1, 0, 1]),
            "disconnected": ("Disconnected", "bluetooth-off", "red")
        }
        
        if state in states:
            text, icon, color = states[state]
            button.text = text
            button.icon = icon
            button.icon_color = color
            button.line_color = color
    
    def update_battery_icon(self, level):
        """Met à jour l'icône batterie"""
        icon = self.ids.battery_icon
        
        if level >= 70:
            icon.icon, icon.text_color = "battery-high", [0, 1, 0, 1]
        elif 30 <= level < 70:
            icon.icon, icon.text_color = "battery-medium", [0.5, 1, 0, 1]
        elif 10 <= level < 30:
            icon.icon, icon.text_color = "battery-low", [1, 0.65, 0, 1]
        else:
            icon.icon, icon.text_color = "battery-alert", [1, 0, 0, 1]
    
        