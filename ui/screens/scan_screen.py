# Class KivyMD
from kivymd.uix.screen import MDScreen
from kivymd.uix.list import TwoLineAvatarIconListItem, IconLeftWidget

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

# Couleurs partagées avec les bannières/icônes de statut (ui/kv/status_bar.kv)
GREY = (0.5, 0.5, 0.5, 1)
GREEN_FG = (0.176, 0.490, 0.196, 1)
RED_FG = (0.776, 0.157, 0.157, 1)
AMBER_FG = (0.780, 0.518, 0.047, 1)

class ScanScreen(MDScreen):
    '''
    ECRAN DU SCAN BLE
    '''

    # Properties pour la mise à jour dynamique de l'UI (reconnu dans .kv avec root)
    heart_rate_text = StringProperty("--")
    battery_text = StringProperty("-- %")
    battery_icon = StringProperty("battery-high")
    battery_color = ListProperty([0, 1, 0, 1])  # Vert par défaut

    # État du scan/de la connexion BLE
    is_busy = BooleanProperty(False)
    scan_status_text = StringProperty("Appuyez sur le bouton pour démarrer le scan")
    scan_status_color = ListProperty(GREY)
    connecting_address = StringProperty("")
    connected_address = StringProperty("")
    connected_has_heart_rate = BooleanProperty(True)
    # Propriété réactive (et non un simple attribut) pour que le kv puisse
    # afficher/masquer la card des résultats selon qu'elle est vide ou non.
    devices_found = ListProperty([])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ligne de la liste de chaque appareil, par adresse (pour mettre à
        # jour son texte de statut en 2e ligne)
        self.device_status_items = {}

    def on_enter(self):
        '''
        Activer dès l'ouverture de l'écran
        '''

        # Récupérer les managers de l'application
        app = App.get_running_app()
        self.ble_manager = app.ble_manager
        self.session = app.session
        # self.hr_session = app.hr_session

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
        self._set_scan_status("Recherche d'appareils…", GREY, busy=True)
        self.ids.devices_list.clear_widgets()
        self.device_status_items = {}
        asyncio.ensure_future(self._scan())

    async def _scan(self):
        """Lance le scan BLE"""
        # Déconnecter si déjà connecté
        if self.ble_manager.is_connected:
            self._set_scan_status("Déconnexion en cours…", GREY, busy=True)
            self.heart_rate_text = "--"
            self.battery_text = "-- %"
            await self.ble_manager.disconnect()
            self._set_scan_status("Recherche d'appareils…", GREY, busy=True)

        # Lancer le scan
        await self.ble_manager.scan_devices()

    def on_scan_complete(self, devices):
        """Callback de fin de scan"""
        self.devices_found = devices

        if not devices:
            self._set_scan_status("Aucun appareil trouvé", RED_FG)
            return

        # Des appareils sont trouvés : la liste ci-dessous prend le relais
        # pour l'état de connexion (donc pas de redite ici), mais le
        # nombre trouvé reste une info utile à afficher à côté du bouton.
        count = len(devices)
        self._set_scan_status(
            f"{count} appareil{'s' if count > 1 else ''} trouvé{'s' if count > 1 else ''}",
            GREEN_FG,
        )

        for device in devices:
            item = TwoLineAvatarIconListItem(
                text=device.name or device.address,
                secondary_text="Appareil détecté",
            )
            item.secondary_theme_text_color = "Custom"
            item.secondary_text_color = GREY
            item.add_widget(IconLeftWidget(icon="bluetooth"))
            item.bind(on_release=lambda *_, d=device: self.on_device_selected(d))
            self.device_status_items[device.address] = item
            self.ids.devices_list.add_widget(item)

        self._refresh_device_status_labels()

    def on_device_selected(self, device):
        """Appareil sélectionné dans la liste"""
        if self.connecting_address:
            # Une connexion est déjà en cours : ignorer le tap plutôt que
            # de griser toute la liste (ça masquerait le badge ambre sur
            # la ligne en cours de connexion).
            return
        asyncio.create_task(self._connect(device))

    # ========== CONNEXION ==========

    async def _connect(self, device):
        """Se connecte à un appareil"""
        self.connecting_address = device.address
        self.connected_address = ""
        self._refresh_device_status_labels()
        self.is_busy = True
        await self.ble_manager.connect_to_device(device)

    def on_connection_changed(self, data):
        """Callback de changement de connexion"""
        # data contient {"is_connected": bool, "device": device}
        is_connected = data["is_connected"]
        device = data["device"]

        if is_connected:
            self.connecting_address = ""
            self.is_busy = False
            self.connected_address = device.address
            self.connected_has_heart_rate = data.get("has_heart_rate", True)
            # Démarrer l'enregistrement des données FC
            self.session.start_recording()
            # Déjà visible sur la ligne de l'appareil (vert, ou rouge si
            # pas de capteur FC), inutile de le répéter ici.
        else:
            self.connected_address = ""

            # BLEManager déconnecte l'appareil précédent avant de se
            # connecter au nouveau (device=None ici) : si on est déjà en
            # train de se connecter à un AUTRE appareil, c'est cette étape
            # intermédiaire, pas un vrai échec — ne pas interrompre le
            # badge "Connexion en cours..." du nouvel appareil.
            is_switch_intermediate = device is None and self.connecting_address
            if not is_switch_intermediate:
                self.connecting_address = ""
                self.is_busy = False
                # Pas d'état "échec"/"déconnecté" dédié sur la ligne : on
                # garde ce libellé pour ce cas précis.
                self._set_scan_status("Déconnecté", RED_FG)

        self._refresh_device_status_labels()
    
    # ========== DATA ==========
    
    def on_heart_rate_received(self, bpm):
        """Callback quand FC reçue"""
        self.heart_rate_text = f"{bpm}"   
    
    def on_battery_received(self, level):
        """Callback batterie"""
        self.battery_text = f"{level} %"
        if level != "--":
            self.update_battery_icon(level)
    
    # ========== UI HELPERS ==========
    
    def _set_scan_status(self, text, color, busy=False):
        """Met à jour le libellé de statut du scan/de la connexion"""
        self.scan_status_text = text
        self.scan_status_color = color
        self.is_busy = busy

    def _refresh_device_status_labels(self):
        """Met à jour le texte de statut (2e ligne) de chaque appareil de la liste"""
        for address, item in self.device_status_items.items():
            if address == self.connected_address:
                if self.connected_has_heart_rate:
                    item.secondary_text = "Connecté"
                    item.secondary_text_color = GREEN_FG
                else:
                    item.secondary_text = "Connecté — pas de service FC"
                    item.secondary_text_color = RED_FG
            elif address == self.connecting_address:
                item.secondary_text = "Connexion en cours…"
                item.secondary_text_color = AMBER_FG
            else:
                item.secondary_text = "Appareil détecté"
                item.secondary_text_color = GREY
    
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
    
        