from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.app import App
from utils.logger import get_logger
from kivy.uix.image import AsyncImage
from kivy.clock import Clock
from kivy.clock import mainthread
from utils.event_bus import event_bus
from kivymd.toast import toast


logger = get_logger(__name__)

class HomeScreen(MDScreen):
    """Écran d'accueil"""
    
    unity_connected = BooleanProperty(False)
    status_icon_source = StringProperty("assets/loading.gif")
    selected_model = StringProperty("PID")
    age_user = StringProperty("")
    
    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        app = App.get_running_app()

        # Managers
        self.udp_discovery = app.udp_discovery
        self.udp_controller = app.udp_controller
        self.session = app.session

        # Vérifier la connexion Unity (au cas où on arrive dans l'écran après la connexion)
        self.unity_connected = self.udp_discovery.is_unity_connected()
        if self.unity_connected :
            self.selected_model = self.session.config.model
            self.age_user = str(self.session.user_profile.age)

        # S'abonner pour écouter les eventbus
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.subscribe("unity_ping_received", self.handle_ping_received)
        event_bus.subscribe("session_updated", self.on_session_updated)
    
    def on_leave(self):
        event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.unsubscribe("unity_ping_received", self.handle_ping_received)
        event_bus.subscribe("session_updated", self.on_session_updated)

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
    
    
    def on_session_updated(self, session):
         # Mise à jour UI
        self.selected_model = session.config.model
        self.age_user = str(session.user_profile.age)

    # ===== Foncions reliées à l'UI =====

    def force_reconnect(self):
        """Bouton pour forcer la reconnexion"""
        app = App.get_running_app()

        # Forcer la reconnexion en arrêtant le serveur WebSocket et en redémarrant la découverte UDP
        app.ws_server.stop()
        app.udp_discovery.force_reconnect()
        self.unity_connected = False
    
    def send_new_age(self):
        app = App.get_running_app()

        try:
            age = int(self.ids.age_input.text)

            if 5 <= age <= 100:  # validation logique
                app.user_profile.age = age
                print("Age mis à jour :", age)

                # Envoyer via UDP
                if self.udp_controller:
                    self.udp_controller.set_age_player(age)

            else:
                toast("Age invalide")
        except ValueError:
            print("Entrée âge invalide")
            toast("Age invalide")