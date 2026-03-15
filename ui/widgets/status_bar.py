from time import time

from kivy.properties import BooleanProperty
from kivymd.uix.boxlayout import MDBoxLayout

from network.connectivity import is_bluetooth_enabled, is_wifi_enabled
from kivy.clock import Clock
from kivy.app import App
from kivy.animation import Animation


class StatusBar(MDBoxLayout):
    """
    Widget pour afficher l'état BLE, Wi-Fi et capteur FC.
    Les icônes changent automatiquement selon les propriétés.
    """
    ble_connected = BooleanProperty(False)
    wifi_connected = BooleanProperty(False)
    hr_connected = BooleanProperty(False)

    def on_kv_post(self, base_widget):
        Clock.schedule_interval(self.update_status, 2)
        # Vérification régulière du timeout HR
        Clock.schedule_interval(self.check_hr_timeout, 1)

    def update_status(self, dt):

        # Récupérer les managers de l'application
        app = App.get_running_app()
        self.ble_manager = app.ble_manager

        self.ble_connected = is_bluetooth_enabled()
        self.wifi_connected = is_wifi_enabled()

        # callback
        self.ble_manager.on_hr_received = self.handle_hr_received
    
    def handle_hr_received(self):
        """Callback quand FC reçue"""
        
        self.hr_connected = True
        self.last_hr_received = time()

        if hasattr(self.ids, 'hr_icon'):
            self.ids.hr_icon.icon="heart"
            # Animation de pulsation
            anim = (
                Animation(opacity=1, duration=0.5) +
                Animation(opacity=0.3, duration=0.5)
            )
            anim.start(self.ids.hr_icon)
    
    def check_hr_timeout(self, dt):
        """Vérifie si HR n’a plus été reçu depuis 2 secondes"""
        if self.hr_connected:
            elapsed = time() - self.last_hr_received
            if elapsed > 2:  # 2 secondes sans ping
                self.hr_connected = False
                if hasattr(self.ids, 'hr_icon'):
                    self.ids.hr_icon.icon = "heart-off"
                    self.ids.hr_icon.opacity = 1
                    Animation.cancel_all(self.ids.hr_icon)


            
    