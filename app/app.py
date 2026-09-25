# Class KivyMD
import asyncio

from kivymd.app import MDApp
from kivymd.toast import toast

# Class Kivy
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.utils import platform

# Custom modules
from config import THEME_STYLE, PRIMARY_PALETTE, ACCENT_PALETTE
from app.ble.ble_manager import BLEManager
from app.network.websocket_server import WebSocketServer
from app.network.udp_discovery import UDPDiscovery
from app.network.udp_controller import UDPController
from app.network.quest_client import QuestClient
from app.data.player_store import PlayerStore
from app.data.hr_session import HRSession
from app.controllers.adaptive_controller import AdaptiveController
from app.data.game_session import GameSession
# from ui.widgets.status_bar import StatusBar

# Logger
from utils.logger import get_logger
from utils.ressource_path import resource_path

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
        self.hr_session = None
        self.quest_client = None
        # self.status_bar = None

        logger.info("Initialisation de l'application KCApp")

    def build(self):
        '''
        Construction de l'UI
        '''
        logger.info("Construction de l'interface...")

        # Initialiser les gestionnaires
        self.ble_manager = BLEManager()
        self.player_store = PlayerStore()
        self.ws_server = WebSocketServer()
        self.udp_discovery = UDPDiscovery()
        self.udp_controller = UDPController(self.udp_discovery)
        self.session = GameSession()
        self.adaptive_controller = AdaptiveController()
        self.quest_client = QuestClient()

        # Définir le thème de l'application
        self.theme_cls.theme_style = THEME_STYLE
        self.theme_cls.primary_palette = PRIMARY_PALETTE
        self.theme_cls.accent_palette = ACCENT_PALETTE

        # Charger les fichiers .kv
        # Builder.load_file("ui/kv/status_bar.kv")
        # Builder.load_file("ui/kv/home_screen.kv")
        # Builder.load_file("ui/kv/scan_screen.kv")
        # Builder.load_file("ui/kv/pilotage_screen.kv")
        # Builder.load_file("ui/kv/profil_screen.kv")
        # Builder.load_file("ui/kv/tracking_screen.kv")
        # Builder.load_file("ui/kv/game_screen.kv")

        Builder.load_file(resource_path("ui/kv/status_bar.kv"))
        Builder.load_file(resource_path("ui/kv/home_screen.kv"))
        Builder.load_file(resource_path("ui/kv/scan_screen.kv"))
        Builder.load_file(resource_path("ui/kv/control_menu_screen.kv"))
        Builder.load_file(resource_path("ui/kv/headset_screen.kv"))
        Builder.load_file(resource_path("ui/kv/pilotage_screen.kv"))
        Builder.load_file(resource_path("ui/kv/player_profile_screen.kv"))
        Builder.load_file(resource_path("ui/kv/profil_screen.kv"))
        Builder.load_file(resource_path("ui/kv/tracking_screen.kv"))
        Builder.load_file(resource_path("ui/kv/game_screen.kv"))

        return Builder.load_file(resource_path("ui/kv/main.kv"))

    def on_start(self):
        '''
        Exécuter après le chargement de l'ui
        '''
        logger.info("Démarrage de l'application")

        self._request_android_permissions()
        self._start_background_tracker()

        # ScreenManager
        self.sm = self.root.ids.screen_manager

        # Démarrer la découverte Unity automatiquement
        self.udp_discovery.start_discovery()

    def _start_background_tracker(self):
        """
        Démarre le service "Tracker" (voir buildozer.spec et service.py) qui
        protège le process (donc le BLE/UDP de l'app principale, inchangés)
        d'un gel par Android quand l'intervenant passe sur une autre app.

        Le nom de classe Java généré par p4a suit le schéma
        "<package.domain>.<package.name>.Service<NomDuService>" (voir
        buildozer.spec : package.domain=org.m2s.apex, package.name=
        APEX_control, service=Tracker). Si le service ne démarre pas
        (exception au premier lancement sur l'appareil), vérifier le nom
        exact généré dans
        .buildozer/android/platform/build-*/dists/*/src/main/java/ et
        corriger la chaîne ci-dessous en conséquence.
        """
        if platform != "android":
            return

        try:
            from jnius import autoclass

            service = autoclass("org.m2s.apex.APEX_control.ServiceTracker")
            py_activity = autoclass("org.kivy.android.PythonActivity")
            service.start(py_activity.mActivity, "")
            logger.info("🔒 Service Tracker démarré (protection arrière-plan)")
        except Exception:
            logger.exception("⚠️ Échec du démarrage du service Tracker")

    def _request_android_permissions(self):
        """
        Demande au runtime BLUETOOTH_SCAN/BLUETOOTH_CONNECT (Android 12+,
        API 31+) : bleak (backend p4android) ne demande que les permissions
        de localisation avant un scan BLE, jamais celles-ci — sans cet appel,
        le scan/appairage du capteur FC échoue silencieusement sur les
        appareils récents (ex. Android 16) malgré leur déclaration dans
        buildozer.spec.
        """
        if platform != "android":
            return

        from android.permissions import Permission, request_permissions

        request_permissions([
            Permission.BLUETOOTH_SCAN,
            Permission.BLUETOOTH_CONNECT,
        ])
    
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
    
    def change_screen(self, screen_name, title, show_back=False):
        """Change l'écran actif et met à jour le titre de la top bar

        Args:
            screen_name: Nom de l'écran à afficher
            title: Nouveau titre pour la top bar
            show_back: Si True, affiche une flèche retour vers le menu
                Contrôle au lieu de l'icône par défaut (sous-écrans
                Casque VR / Contrôle du jeu, voir control_menu_screen.kv)
        """
        self.root.ids.screen_manager.current = screen_name
        self.root.ids.top_bar.title = title

        if show_back:
            self.root.ids.top_bar.left_action_items = [
                ["arrow-left", lambda x: self.change_screen("control_menu", "Contrôle")]
            ]
        else:
            self.root.ids.top_bar.left_action_items = [["account-circle", lambda x: None]]