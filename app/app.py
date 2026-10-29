# Class KivyMD
import asyncio

from kivymd.app import MDApp
from kivymd.toast import toast

# Class Kivy
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import BooleanProperty
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

    # Top bar / barre de statut / navigation du bas visibles ou non — lu
    # par ui/kv/main.kv. Passé à False par GameScreen.toggle_fullscreen()
    # pour le plein écran de la vidéo (voir ui/screens/game_screen.py).
    chrome_visible = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.ble_manager = None
        self.ws_server = None
        self.udp_discovery = None
        self.udp_controller = None
        self.hr_session = None
        self.quest_client = None
        # self.status_bar = None

        # Navigation courante (écran, titre, flèche retour, cible du retour)
        # — voir change_screen/go_back/open_player_profile
        self._current_nav = ("home", "Accueil", False, None)

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
        Builder.load_file(resource_path("ui/kv/quick_actions_bar.kv"))
        Builder.load_file(resource_path("ui/kv/player_chip.kv"))
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

        self._add_player_chip_to_top_bar()

        # Démarrer la découverte Unity automatiquement
        self.udp_discovery.start_discovery()

    def _start_background_tracker(self):
        """
        Démarre le service "Tracker" (voir buildozer.spec et service.py) qui
        protège le process (donc le BLE/UDP de l'app principale, inchangés)
        d'un gel par Android quand l'intervenant passe sur une autre app.

        Le nom de classe Java généré par p4a suit le schéma
        "<package.domain>.<package.name minuscule>.Service<NomDuService>"
        (voir buildozer.spec : package.domain=org.m2s.apex, package.name=
        APEX_control -> org.m2s.apex.apex_control (Android exige un nom de
        paquet en minuscules — confirmé par le chemin de la clé ADB attendue
        par QuestClient : /data/user/0/org.m2s.apex.apex_control/files/),
        service=Tracker. Si le service ne démarre pas (exception au premier
        lancement sur l'appareil), vérifier le nom exact généré dans
        .buildozer/android/platform/build-*/dists/*/src/main/java/ et
        corriger la chaîne ci-dessous en conséquence.
        """
        if platform != "android":
            return

        try:
            from jnius import autoclass

            service = autoclass("org.m2s.apex.apex_control.ServiceTracker")
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
    
    def _add_player_chip_to_top_bar(self):
        """
        Insère l'encadré joueur (PlayerChip) dans la MDTopAppBar, juste
        après ses icônes de gauche et avant le titre. On garde la top bar
        KivyMD (style, titre) plutôt que d'en réécrire une : seul cet ajout
        est nécessaire. La boîte des icônes (left_actions) est reconstruite
        à chaque changement de left_action_items, mais pas sa boîte parente,
        donc l'encadré n'est jamais retiré.
        """
        from ui.widgets.player_chip import PlayerChip

        top_bar = self.root.ids.top_bar
        left_actions = top_bar.ids.left_actions
        right_actions = top_bar.ids.right_actions
        title = top_bar.ids.label_title
        row = left_actions.parent
        chip = PlayerChip()
        # children est en ordre inverse : index de left_actions = juste après elle
        row.add_widget(chip, index=row.children.index(left_actions))

        # Titre masqué sur smartphone (même seuil dp(600) que le reste de
        # l'UI) : l'espace restant une fois le chip joueur placé le rend
        # illisible même réduit. label_title appartient à la kv rule
        # interne de MDTopAppBar, donc pas accessible depuis ui/kv/main.kv
        # — on le pilote ici en Python plutôt que par binding kv. opacity
        # (pas text) pour ne pas entrer en conflit avec le binding
        # `text: root.title` de MDTopAppBar, qui écrase label_title.text
        # à chaque app.change_screen().
        def update_title_visibility(*_):
            is_phone = Window.width < dp(600)
            title.font_style = "Subtitle1" if is_phone else "H6"
            title.opacity = 0 if is_phone else 1

        Window.bind(width=update_title_visibility)
        update_title_visibility()

        # L'encadré décale le titre vers la droite : on compense avec un
        # padding asymétrique pour qu'il reste centré sur toute la largeur de
        # la barre (et non sur l'espace restant entre l'encadré et la droite).
        def center_title(*_):
            offset = left_actions.width + chip.width - right_actions.width
            base = dp(12)
            title.padding = [base + max(0, -offset), 0, base + max(0, offset), 0]

        for widget in (left_actions, chip, right_actions):
            widget.bind(width=center_title)
        center_title()

    def change_screen(self, screen_name, title, show_back=False, back_target=None):
        """Change l'écran actif et met à jour le titre de la top bar

        Args:
            screen_name: Nom de l'écran à afficher
            title: Nouveau titre pour la top bar
            show_back: Si True, affiche une flèche retour avant l'encadré
                joueur (sous-écrans Casque VR / Contrôle du jeu / Profil
                du joueur, voir control_menu_screen.kv)
            back_target: Arguments de change_screen pour la flèche retour
                (par défaut le menu Contrôle) — voir open_player_profile
        """
        self.root.ids.screen_manager.current = screen_name
        self.root.ids.top_bar.title = title
        self._current_nav = (screen_name, title, show_back, back_target)

        if show_back:
            target = back_target or ("control_menu", "Contrôle")
            self.root.ids.top_bar.left_action_items = [
                ["arrow-left", lambda x: self.change_screen(*target)]
            ]
        else:
            # Pas d'icône : l'encadré joueur (PlayerChip) sert de bouton profil
            self.root.ids.top_bar.left_action_items = []

    def open_player_profile(self, edit=False):
        """
        Ouvre le Profil du joueur depuis n'importe quel écran (encadré joueur
        de la top bar, icône profil, crayon de Home) : la flèche retour
        ramène à l'écran d'où l'on vient, avec son propre titre et retour.

        Args:
            edit: Ouvrir directement le formulaire de modification du joueur
        """
        screen = self.root.ids.screen_manager.get_screen("player_profile")
        if self._current_nav[0] == "player_profile":
            if edit:
                screen.open_edit_form()
            return

        if edit:
            screen.request_edit_on_enter()
        self.change_screen("player_profile", "Profil du joueur", True, back_target=self._current_nav)