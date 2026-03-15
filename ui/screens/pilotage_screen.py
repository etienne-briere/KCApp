from kivymd.uix.screen import MDScreen
from kivy.properties import BooleanProperty, NumericProperty
from kivy.clock import Clock
from kivy.app import App
from kivymd.toast import toast

import asyncio

from utils.logger import get_logger

logger = get_logger(__name__)

class PilotageScreen(MDScreen):
    """Écran de contrôle du jeu Unity"""

    # Properties pour l'UI
    unity_connected = BooleanProperty(False) # connexion Unity
    obstacles_enabled = BooleanProperty(True) # obtacles
    adaptive_mode_enabled = BooleanProperty(False) # mode adaptatif
    cube_per_min = NumericProperty(60) # cubes/min
    target_hr = NumericProperty(50)  # % FCmax
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.udp_controller = None
        self.udp_discovery = None

        # Fréquence de cube
        self.cube_frequency = round(1/(self.cube_per_min/60), 2)
        
        # Debounce pour les sliders
        self.cube_frequency_event = None
        self.target_hr_event = None

        # WebSocket Server
        self.ws_server = None

        # UDP
        self.udp_controller = None
        self.udp_discovery = None
    
    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        # Managers
        app = App.get_running_app()
        self.ble_manager = app.ble_manager
        self.ws_server = app.ws_server
        self.udp_controller = app.udp_controller
        self.udp_discovery = app.udp_discovery
        self.hr_session = app.hr_session

        # Callback pour recevoir la FC en temps réel
        self.ble_manager.on_heart_rate_pilotage = self.on_new_hr_data

        # Callbacks WebSocket
        self.ws_server.on_client_connected = self.on_ws_client_connected
        self.ws_server.on_client_disconnected = self.on_ws_client_disconnected

        # Configurer les callbacks UDP (détecter connexion/déconnexion Unity)
        app.udp_discovery.on_unity_connected = self.handle_unity_connected
        app.udp_discovery.on_unity_disconnected = self.handle_unity_disconnected

        # Vérifier la connexion Unity (au cas où on arrive dans l'écran après la connexion)
        self.unity_connected = self.udp_discovery.is_unity_connected()

        # Vérifier l'activation du serveur ws (au cas où on arrive dans l'écran après la déconnexion)
        self.adaptive_mode_enabled = self.ws_server.is_running
    
    # ========== CALLBACKS UDP ==========

    def handle_unity_connected(self, ip_unity: str, dt=0):
        """Callback quand Unity se connecte"""
        self.unity_connected = True

    def handle_unity_disconnected(self, dt=0):
        """Callback quand Unity se déconnecte"""
        self.unity_connected = False

    # ========== OBSTACLES ==========
    
    def on_obstacles_toggle(self, is_active):
        """Toggle obstacles ON/OFF"""
        self.obstacles_enabled = is_active
        logger.info(f"🎮 Obstacles: {'ON' if is_active else 'OFF'}")
        
        # Envoyer via UDP
        if self.udp_controller:
            self.udp_controller.set_obstacle("1" if is_active else "0")
    
    # ========== ADAPTIVE MODE ==========
    
    def on_adaptive_mode_toggle(self, is_active):
        """Toggle mode adaptatif ON/OFF"""
        self.adaptive_mode_enabled = is_active
        logger.info(f"❤️ Mode adaptatif: {'ON' if is_active else 'OFF'}")
        
        # Vérifier la connexion Unity
        self.unity_connected = self.udp_discovery.is_unity_connected()
        
        if is_active == True :

            # Vérifier qu'un appareil est connecté
            if not self.ble_manager or not self.ble_manager.is_connected:
                self.adaptive_mode_enabled = False
                toast("Please connect to a HR sensor")
                return
            
            # Vérifier que Unity est connecté
            if not self.unity_connected :
                self.adaptive_mode_enabled = False
                toast("Please connect the game")
                return
            
            # Activer le serveur WebSocket
            asyncio.ensure_future(self._start_server())

            # Notifier Unity du démarrage du serveur websocket
            if self.udp_discovery:
                self.udp_discovery.send_message("command_ws", "1")
                
                # Envoyer le %FCmax cible
                self.send_target_hr()
        else : 
            # désactiver le serveur WebSocket
            asyncio.ensure_future(self._stop_server())

            # Notifier Unity de l'arrêt du serveur websocket
            if self.udp_discovery:
                self.udp_discovery.send_message("command_ws", "0")

                # Envoyer la fréquence de cube
                self.send_cube_frequency()
        
    
    # ========== CUBE FREQUENCY ==========
    
    def on_cube_frequency_change(self, value):
        """Slider cube frequency changé"""
        self.cube_per_min = value

        self.cube_frequency = round(1/(self.cube_per_min/60), 2)

    def on_cube_frequency_touch_up(self):
        """Appelé quand l'utilisateur relâche le slider"""
        logger.debug(f"🎯 Slider relâché à {self.cube_per_min} cubes/min")

        self.send_cube_frequency()
    
    def send_cube_frequency(self):
        """Envoie la fréquence des cubes à Unity"""
        if self.udp_controller:
            success = self.udp_controller.set_cube_rate(self.cube_frequency)
            if success:
                logger.info(f"📤 Cube frequency envoyée: {self.cube_frequency}")
    
    # ========== TARGET HR ==========
    
    def on_target_hr_change(self, value):
        """Slider target HR changé"""
        self.target_hr = value
        logger.debug(f"🎯 Target HR: {value}%")
        
    def on_target_hr_touch_up(self):
        """Appelé quand l'utilisateur relâche le slider"""
        logger.debug(f"🎯 Slider relâché à {self.target_hr}")

        self.send_target_hr()
    
    def send_target_hr(self):
        """Envoie la FC cible à Unity"""
        if self.udp_controller:
            success = self.udp_controller.set_target_hr(self.target_hr)
            if success:
                logger.info(f"📤 Target HR envoyée: {self.target_hr}%")
    
    # ========== GAME ACTIONS ==========
    
    def pause_game(self):
        """Met le jeu en pause"""
        if self.udp_controller:
            success = self.udp_controller.pause_game()
            if success:
                logger.info("⏸️ Jeu en pause")
            else:
                toast("❌ Failed to pause")
    
    def resume_game(self):
        """Reprend le jeu"""
        if self.udp_controller:
            success = self.udp_controller.resume_game()
            if success:
                logger.info("▶️ Jeu repris")
            else:
                toast("❌ Failed to resume")
    
    def restart_game(self):
        """Redémarre le jeu"""
        if self.udp_controller:
            success = self.udp_controller.restart_game()
            if success:
                logger.info("🔄 Jeu redémarré")
            else:
                toast("❌ Failed to restart")
    
    # ========== GESTION WEBSOCKET ==========
    
    async def _start_server(self):
        """Démarre le serveur WebSocket"""
        success = await self.ws_server.start()

        if success:
            self.adaptive_mode_enabled = True
            logger.info("Serveur WebSocket activé")
        else:
            self.adaptive_mode_enabled = False
            
    async def _stop_server(self):
        """Arrête le serveur WebSocket"""
        await self.ws_server.stop()
        self.adaptive_mode_enabled = False
        
    
    # ========== CALLBACKS HR SESSION ==========

    def on_new_hr_data(self, bpm):
        """Callback quand FC reçue"""

        logger.debug(f"📊 Nouvelle donnée: {bpm} BPM.")

        if self.adaptive_mode_enabled:
            # Envoyer les données FC via WebSocket
            asyncio.ensure_future(self.ws_server.send_data_to_clients(bpm))    
    
    # ========== CALLBACKS WEBSOCKET ==========
    
    def on_ws_client_connected(self, websocket):
        """Callback quand un client se connecte"""
        print(f"🔗 Client Unity connecté")
        self.adaptive_mode_enabled = True

    def on_ws_client_disconnected(self, websocket):
        """Callback quand un client se déconnecte"""
        self.adaptive_mode_enabled = False
        print(f"🔌 Client Unity déconnecté")
