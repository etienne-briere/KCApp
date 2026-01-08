from kivymd.app import MDApp

from kivy.lang import Builder
from kivy.core.window import Window

from config import THEME_STYLE, PRIMARY_PALETTE, ACCENT_PALETTE
from ble.manager import BLEManager
from network.websocket_server import WebSocketServer
from network.udp_discovery import UDPDiscovery
from network.udp_controller import UDPController
from data.user_profile import UserProfile

from utils.logger import get_logger

logger = get_logger(__name__)

class KCApp(MDApp):
    """
    Application principale KCApp
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.ble_manager = None
        self.ws_server = None
        self.udp_discovery = None
        self.udp_controller = None

        logger.info("Initialisation de l'application KCApp")

    def build(self):
        '''
        Construction de l'UI
        '''
        logger.info("Construction de l'interface...")

        # Initialiser les gestionnaires
        self.ble_manager = BLEManager()
        self.user_profile = UserProfile()
        self.ws_server = WebSocketServer() 
        self.udp_discovery = UDPDiscovery()
        self.udp_controller = UDPController(self.udp_discovery)

        # Définir le thème de l'application
        self.theme_cls.theme_style = THEME_STYLE 
        self.theme_cls.primary_palette = PRIMARY_PALETTE
        self.theme_cls.accent_palette = ACCENT_PALETTE

        # Charger les fichiers .kv
        Builder.load_file("ui/kv/home_screen.kv")
        Builder.load_file("ui/kv/scan_screen.kv")
        Builder.load_file("ui/kv/pilotage_screen.kv")
        Builder.load_file("ui/kv/profil_screen.kv")
        Builder.load_file("ui/kv/tracking_screen.kv")
        Builder.load_file("ui/kv/game_screen.kv")

        return Builder.load_file("ui/kv/main.kv")
    
    def on_start(self):
        '''
        Exécuter après le chargement de l'ui
        '''
        logger.info("Démarrage de l'application")

        # ScreenManager
        self.sm = self.root.ids.screen_manager

        # Démarrer la découverte Unity automatiquement
        self.udp_discovery.start_discovery()
    
    def on_stop(self):
        """
        Appelé à l'arrêt de l'application - nettoyage des ressources
        """

        logger.info("Arrêt de l'application - nettoyage des ressources")

        # Arrêter UDP
        if self.udp_discovery:
            self.udp_discovery.stop_discovery()

        # Arrêter le serveur WebSocket si actif
        if self.ws_server and self.ws_server.is_running:
            import asyncio
            asyncio.ensure_future(self.ws_server.stop())
        
        # Déconnecter les périphériques BLE
        if self.ble_manager:
            import asyncio
            asyncio.ensure_future(self.ble_manager.disconnect())
        
        logger.info("Nettoyage terminé")
    
    def change_screen(self, screen_name, title):
        """Change l'écran actif et met à jour le titre de la top bar
        
        Args:
            screen_name: Nom de l'écran à afficher
            title: Nouveau titre pour la top bar
        """
        logger.debug(f"Navigation vers l'écran: {screen_name}")
        self.root.ids.screen_manager.current = screen_name
        self.root.ids.top_bar.title = title