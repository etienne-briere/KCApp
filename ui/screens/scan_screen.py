# Class KivyMD
from kivymd.uix.screen import MDScreen
from kivymd.uix.list import TwoLineIconListItem, IconLeftWidget

# Class Kivy
from kivy.app import App
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.animation import Animation
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.clock import Clock

# Custom modules
from app import data
from utils.event_bus import event_bus
from utils.logger import get_logger
logger = get_logger(__name__)

from datetime import datetime

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

    # État du scan/de la connexion BLE
    is_busy = BooleanProperty(False)
    scan_status_text = StringProperty("Appuyez sur le bouton pour démarrer le scan")
    scan_status_color = ListProperty(GREY)
    connecting_address = StringProperty("")
    connected_address = StringProperty("")
    connected_has_heart_rate = BooleanProperty(True)
    connected_has_battery = BooleanProperty(True)
    # Appareil toujours « connecté » côté BLE mais plus aucune FC reçue
    # (même critère que l'icône cœur barré de la status bar, qui émet
    # hr_sensor_status_changed) : le capteur s'est déconnecté tout seul.
    hr_signal_lost = BooleanProperty(False)
    # Propriété réactive (et non un simple attribut) pour que le kv puisse
    # afficher/masquer la card des résultats selon qu'elle est vide ou non.
    devices_found = ListProperty([])
    # Historique des appareils déjà connectés (card "MES APPAREILS")
    known_devices = ListProperty([])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ligne de chaque appareil, par adresse, avec son texte par défaut
        # (pour mettre à jour son texte de statut en 2e ligne) — une entrée
        # par liste (appareils détectés par un scan / appareils connus)
        self.device_status_items = {}
        self.known_status_items = {}

        # Indique qu'une déconnexion est déclenchée par un nouveau scan (et
        # non par un échec/une perte de connexion) : on évite alors d'afficher
        # "Déconnecté", le statut de recherche restant affiché à la place.
        self._rescan_disconnect = False

    def on_enter(self):
        '''
        Activer dès l'ouverture de l'écran
        '''

        # Récupérer les managers de l'application
        app = App.get_running_app()
        self.ble_manager = app.ble_manager
        self.session = app.session
        self.known_devices_store = app.known_devices_store
        # self.hr_session = app.hr_session

        self._refresh_known_devices_card()

        # S'abonner aux événements globaux (EventBus) pour recevoir les données de FC et batterie
        event_bus.subscribe("heart_rate_received", self.on_heart_rate_received) 
        event_bus.subscribe("battery_received", self.on_battery_received)
        event_bus.subscribe("connection_changed", self.on_connection_changed)
        event_bus.subscribe("scan_completed", self.on_scan_complete)
        event_bus.subscribe("hr_sensor_status_changed", self.on_hr_sensor_status_changed)

        # L'évènement n'est reçu que sur cet écran : resynchroniser avec la
        # status bar au cas où le capteur aurait décroché entre-temps.
        if app.root and self.connected_address:
            self._set_hr_signal_lost(not app.root.ids.status_bar.hr_sensor_connected)
    
    def on_leave(self):
        """Sortie de l'écran"""

        # Nettoyer les callbacks pour éviter les fuites de mémoire et les appels indésirables
        event_bus.unsubscribe("heart_rate_received", self.on_heart_rate_received)
        event_bus.unsubscribe("battery_received", self.on_battery_received)
        event_bus.unsubscribe("connection_changed", self.on_connection_changed)
        event_bus.unsubscribe("scan_completed", self.on_scan_complete)
        event_bus.unsubscribe("hr_sensor_status_changed", self.on_hr_sensor_status_changed)

    # ========== SCAN ==========
    
    def start_ble_scan(self):
        """Démarrer le scan BLE"""
        self._set_scan_status("Recherche d'appareils…", GREY, busy=True)
        self.ids.devices_list.clear_widgets()
        self.device_status_items = {}
        self.devices_found = []
        asyncio.ensure_future(self._scan())

    async def _scan(self):
        """Lance le scan BLE"""
        # Déconnecter si déjà connecté (sans afficher de statut intermédiaire :
        # "Recherche d'appareils…" reste affiché pendant toute l'opération)
        if self.ble_manager.is_connected:
            self._rescan_disconnect = True
            self.heart_rate_text = "--"
            self.battery_text = "-- %"
            await self.ble_manager.disconnect()

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
            item = TwoLineIconListItem(
                text=device.name or device.address,
                secondary_text="Appareil détecté",
            )
            item.secondary_theme_text_color = "Custom"
            item.secondary_text_color = GREY
            item.secondary_font_style = "Caption" if Window.width >= dp(600) else "Overline"
            # KivyMD centre l'icône sur toute la hauteur de la card, mais son
            # padding haut/bas par défaut pour 2 lignes (20dp/15dp) n'est pas
            # symétrique : le bloc titre+sous-titre se retrouve décalé vers
            # le bas par rapport à l'icône. Égaliser les deux recentre le texte.
            item._txt_top_pad = dp(17.5)
            item._txt_bot_pad = dp(17.5)
            item.add_widget(IconLeftWidget(icon="bluetooth"))
            item.bind(on_release=lambda *_, d=device: self.on_device_selected(d))
            self.device_status_items[device.address] = (item, "Appareil détecté")
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

    def on_known_device_selected(self, address):
        """Appareil sélectionné dans la card "MES APPAREILS" : reconnexion directe"""
        if self.connecting_address:
            return
        asyncio.create_task(self._connect_known(address))

    # ========== CONNEXION ==========

    async def _connect(self, device):
        """Se connecte à un appareil"""
        self.connecting_address = device.address
        self.connected_address = ""
        self._refresh_device_status_labels()
        self.is_busy = True
        await self.ble_manager.connect_to_device(device)

    async def _connect_known(self, address):
        """Se reconnecte directement à un appareil connu, sans repasser par l'écran de scan"""
        self.connecting_address = address
        self.connected_address = ""
        self._refresh_device_status_labels()
        self.is_busy = True
        found = await self.ble_manager.connect_by_address(address)

        if not found:
            self.connecting_address = ""
            self.is_busy = False
            self._set_scan_status("Appareil introuvable — relancez un scan", RED_FG)
            self._refresh_device_status_labels()

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
            self.connected_has_battery = data.get("has_battery", True)
            self.hr_signal_lost = False
            # Démarrer l'enregistrement des données FC
            self.session.start_recording()
            # Mémoriser l'appareil (card "MES APPAREILS")
            self.known_devices_store.add(device.name, device.address)
            self._refresh_known_devices_card()
            # Déjà visible sur la ligne de l'appareil (vert, ou rouge si
            # pas de capteur FC), inutile de le répéter ici.
        else:
            self.connected_address = ""
            self.hr_signal_lost = False

            # BLEManager déconnecte l'appareil précédent avant de se
            # connecter au nouveau (device=None ici) : si on est déjà en
            # train de se connecter à un AUTRE appareil, c'est cette étape
            # intermédiaire, pas un vrai échec — ne pas interrompre le
            # badge "Connexion en cours..." du nouvel appareil.
            is_switch_intermediate = device is None and self.connecting_address
            # Flag consommé ici (et non juste après le await disconnect() côté
            # _scan) car event_bus.emit différète le callback via
            # Clock.schedule_once : le remettre à False trop tôt côté
            # appelant créerait une course où ce handler s'exécute après.
            is_rescan_disconnect = self._rescan_disconnect
            self._rescan_disconnect = False
            if not is_switch_intermediate and not is_rescan_disconnect:
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
        self._set_hr_signal_lost(False)

    def on_hr_sensor_status_changed(self, data):
        """Callback de la status bar : FC reçue récemment ou non"""
        self._set_hr_signal_lost(not data["connected"])

    def _set_hr_signal_lost(self, lost):
        # Sans service FC, aucune trame n'est attendue : rien à signaler de plus.
        lost = bool(lost and self.connected_address and self.connected_has_heart_rate)
        if lost == self.hr_signal_lost:
            return
        self.hr_signal_lost = lost
        if lost:
            self.heart_rate_text = "--"
        self._refresh_device_status_labels()
    
    def on_battery_received(self, level):
        """Callback batterie"""
        self.battery_text = f"{level} %"
        self._refresh_device_status_labels()
    
    # ========== UI HELPERS ==========

    def _refresh_known_devices_card(self):
        """Reconstruit la card "MES APPAREILS" à partir de l'historique enregistré"""
        self.ids.known_devices_list.clear_widgets()
        self.known_devices = self.known_devices_store.devices
        self.known_status_items = {}

        for device in self.known_devices:
            address = device["address"]
            default_text = "Déjà connecté"
            try:
                dt = datetime.fromisoformat(device.get("last_connected", ""))
                default_text = f"Dernière connexion : {dt.strftime('%d/%m %H:%M')}"
            except ValueError:
                pass

            item = TwoLineIconListItem(
                text=device["name"],
                secondary_text=default_text,
            )
            item.secondary_theme_text_color = "Custom"
            item.secondary_text_color = GREY
            item.secondary_font_style = "Caption" if Window.width >= dp(600) else "Overline"
            # Voir le commentaire équivalent dans on_scan_complete
            item._txt_top_pad = dp(17.5)
            item._txt_bot_pad = dp(17.5)
            item.add_widget(IconLeftWidget(icon="bluetooth"))
            item.bind(on_release=lambda *_, a=address: self.on_known_device_selected(a))
            self.known_status_items[address] = (item, default_text)
            self.ids.known_devices_list.add_widget(item)

    def _set_scan_status(self, text, color, busy=False):
        """Met à jour le libellé de statut du scan/de la connexion"""
        self.scan_status_text = text
        self.scan_status_color = color
        self.is_busy = busy

    def _refresh_device_status_labels(self):
        """Met à jour le texte de statut (2e ligne) de chaque appareil des deux listes
        (appareils détectés par un scan et appareils connus)"""
        for items in (self.device_status_items, self.known_status_items):
            for address, (item, default_text) in items.items():
                self._apply_device_status(item, address, default_text)

    def _apply_device_status(self, item, address, default_text):
        """Applique le texte/la couleur de statut à une ligne d'appareil donnée"""
        if address == self.connected_address:
            if self.hr_signal_lost:
                item.secondary_text = "Déconnecté — FC non reçue"
                item.secondary_text_color = RED_FG
            elif self.connected_has_heart_rate:
                if self.connected_has_battery:
                    item.secondary_text = f"Connecté — {self.battery_text}"
                else:
                    item.secondary_text = "Connecté"
                item.secondary_text_color = GREEN_FG
            else:
                item.secondary_text = "Connecté — pas de service FC"
                item.secondary_text_color = RED_FG
        elif address == self.connecting_address:
            item.secondary_text = "Connexion en cours…"
            item.secondary_text_color = AMBER_FG
        else:
            item.secondary_text = default_text
            item.secondary_text_color = GREY
