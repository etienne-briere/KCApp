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
    is_scanning = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Initialisation des variables
        self.devices_target = None # Appareils BLE cibles détectés
        self.devices_menu = None
        self.client = None
        self.heart_rate_data = None # valeur par defaut
        self.heart_animation = None
        self.beat_event = None  # Pour le Clock
    
    def on_enter(self):
        '''
        Activer dès l'ouverture de l'écran
        '''
        # 🔗 Lien vers l'écran d'acceuil
        self.home_screen = self.manager.get_screen('home')

        # Récupérer le BLE Manager depuis l'app
        app = App.get_running_app()
        self.ble_manager = app.ble_manager

        # Configurer les callbacks (manager.py -> scan_screen.py)
        # utile pour appeler les fonctions de scan_screen.py depuis ble/manager.py
        self.ble_manager.on_scan_complete = self.on_scan_complete
        self.ble_manager.on_connection_changed = self.on_connection_changed
        self.ble_manager.on_heart_rate = self.on_heart_rate_received
        self.ble_manager.on_battery_level = self.on_battery_received

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
        else:
            count = len(devices)
            self.ids.devices_list_button.text = f"{count} device{'s' if count > 1 else ''} found"
            self.ids.devices_list_button.icon = "menu-swap"
            self.ids.devices_list_button.icon_color = "white"
            self.ids.devices_list_button.line_color = "white"

    # ========== MENU ==========
    
    def open_devices_menu(self, caller_button):
        """Ouvre le menu des appareils"""
        devices = self.ble_manager.devices_found
        
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
    
    def on_connection_changed(self, is_connected, device):
        """Callback de changement de connexion"""
        if is_connected:
            self.update_button_state("connected", device.name)
        else:
            self.update_button_state("disconnected")
    
    # ========== DATA ==========
    
    def on_heart_rate_received(self, heart_rate):
        """Callback fréquence cardiaque"""
        self.update_heart_rate(heart_rate)
        # if heart_rate > 0:
        #     self.animate_heart(heart_rate)
    
    def on_battery_received(self, battery_level):
        """Callback batterie"""
        self.update_battery(battery_level)
    
    def update_heart_rate(self, bpm):
        """Met à jour l'affichage FC"""
        self.ids.heart_rate_label.text = f"{bpm}"
    
    def update_battery(self, level):
        """Met à jour l'affichage batterie"""
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

    # ========== ANIMATIONS (pas utilisées)==========
    
    def animate_heart(self, bpm):
        """Anime le cœur"""
        if not self.ids.get('heart_icon'):
            return
        
        if self.beat_event:
            self.beat_event.cancel()
        
        interval = 60.0 / bpm

        def beat(dt):
            icon = self.ids.get('heart_icon')
            if not icon:
                return False
            
            anim = (
                Animation(font_size=sp(40), duration=0.1, t='out_cubic') +
                Animation(font_size=sp(35), duration=0.15, t='in_cubic')
            )
            anim.start(icon)
        
        beat(0)
        self.beat_event = Clock.schedule_interval(beat, interval)
    
    # ========== SCREEN LIFECYCLE ==========
    def on_leave(self):
        """Sortie de l'écran"""
        if self.beat_event:
            self.beat_event.cancel()