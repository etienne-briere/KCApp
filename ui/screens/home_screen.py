from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty
from kivy.app import App
from utils.logger import get_logger

logger = get_logger(__name__)

class HomeScreen(MDScreen):
    """Écran d'accueil"""
    
    unity_status_text = StringProperty("Waiting for Unity...")
    unity_ip_text = StringProperty("--")
    unity_connected = BooleanProperty(False)
    
    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        app = App.get_running_app()
        
        # Configurer les callbacks UDP
        app.udp_discovery.on_unity_connected = self.on_unity_connected
        app.udp_discovery.on_unity_disconnected = self.on_unity_disconnected
        app.udp_discovery.on_ping_received = self.on_ping_received
        
        # Vérifier si déjà connecté
        if app.udp_discovery.is_unity_connected():
            self.on_unity_connected(app.udp_discovery.ip_unity)
        else:
            self.unity_status_text = "Searching for Unity..."
            self.unity_connected = False
        
        logger.info("Écran d'accueil affiché")
    
    def on_unity_connected(self, ip_unity: str):
        """Callback quand Unity se connecte"""
        logger.info(f"✅ Unity connecté : {ip_unity}")
        self.unity_status_text = "Unity Connected"
        self.unity_ip_text = ip_unity
        self.unity_connected = True
        
        # Mettre à jour l'UI
        if hasattr(self.ids, 'status_label'):
            self.ids.status_label.text = f"Connected: {ip_unity}"
            self.ids.status_icon.icon = "check-circle"
            self.ids.status_icon.text_color = [0, 1, 0, 1]  # Vert
    
    def on_unity_disconnected(self):
        """Callback quand Unity se déconnecte"""
        logger.warning("⚠️ Unity déconnecté - Recherche en cours...")
        
        self.unity_status_text = "Searching for Unity..."
        self.unity_ip_text = "--"
        self.unity_connected = False
                
        # Mettre à jour l'UI
        if hasattr(self.ids, 'status_label'):
            self.ids.status_label.text = "Searching for Unity..."
            self.ids.status_icon.icon = "loading"
            self.ids.status_icon.text_color = [1, 0.65, 0, 1]  # Orange
    
    def on_ping_received(self):
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
                
        self.unity_status_text = "Searching for Unity..."
        self.unity_connected = False