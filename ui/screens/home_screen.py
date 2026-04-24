from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.app import App
from utils.logger import get_logger
from kivy.uix.image import AsyncImage
from kivy.clock import Clock
from kivy.clock import mainthread
from utils.event_bus import event_bus

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

        # Vérifier la connexion Unity (au cas où on arrive dans l'écran après la connexion)
        self.unity_connected = self.udp_discovery.is_unity_connected()

        # S'abonner pour écouter les eventbus
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.subscribe("unity_ping_received", self.handle_ping_received)
    
    def on_leave(self):
        event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.unsubscribe("unity_ping_received", self.handle_ping_received)

    # ========== CALLBACKS UDP ==========

    @mainthread
    def handle_unity_connection(self, data):
        connected = data["connected"]
        self.unity_connected = connected
    
    def handle_ping_received(self, data):
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

        # Forcer la reconnexion en arrêtant le serveur WebSocket et en redémarrant la découverte UDP
        app.ws_server.stop()
        app.udp_discovery.force_reconnect()
        self.unity_connected = False
    
    def update_age(self, value):
        app = App.get_running_app()

        try:
            if value == "":
                return  # ou une valeur par défaut

            age = int(value)

            if 5 <= age <= 100:  # validation logique
                app.user_profile.age = age
                print("Age mis à jour :", age)
            else:
                print("Âge hors limites")
        except ValueError:
            print("Entrée âge invalide")