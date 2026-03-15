from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty
from kivy.app import App
from utils.logger import get_logger
from kivy.uix.image import AsyncImage
from kivy.clock import Clock
from kivy.clock import mainthread


logger = get_logger(__name__)

class HomeScreen(MDScreen):
    """Écran d'accueil"""
    
    unity_connected = BooleanProperty(False)
    status_icon_source = StringProperty("assets/loading.gif")
    
    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        app = App.get_running_app()

        # Managers
        self.udp_discovery = app.udp_discovery
        
        # Configurer les callbacks UDP
        self.udp_discovery.on_unity_connected = self.handle_unity_connected
        self.udp_discovery.on_unity_disconnected = self.handle_unity_disconnected
        self.udp_discovery.on_ping_received = self.handle_ping_received

        # Vérifier la connexion Unity (au cas où on arrive dans l'écran après la connexion)
        self.unity_connected = self.udp_discovery.is_unity_connected()

    # ========== CALLBACKS UDP ==========

    @mainthread
    def handle_unity_connected(self, ip_unity: str, dt=0):
        """Callback quand Unity se connecte"""
        self.unity_connected = True

    @mainthread
    def handle_unity_disconnected(self, dt=0):
        """Callback quand Unity se déconnecte"""
        self.unity_connected = False
    
    def handle_ping_received(self):
        """Callback quand un ping Unity est reçu"""
        # Optionnel : afficher un indicateur visuel
        if hasattr(self.ids, 'ping_indicator'):
            # Animation de pulsation
            from kivy.animation import Animation
            anim = (
                Animation(opacity=1, duration=0.1) +
                Animation(opacity=0.3, duration=0.3)
            )
            anim.start(self.ids.ping_indicator)

    def force_reconnect(self):
        """Bouton pour forcer la reconnexion"""
        app = App.get_running_app()
        app.udp_discovery.force_reconnect()
        self.unity_connected = False
