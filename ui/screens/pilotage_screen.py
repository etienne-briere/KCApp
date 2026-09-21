from kivymd.uix.screen import MDScreen
from kivy.properties import BooleanProperty, NumericProperty
from kivy.app import App
from kivymd.toast import toast

from utils.event_bus import event_bus
from utils.logger import get_logger

logger = get_logger(__name__)

class PilotageScreen(MDScreen):
    """Écran de contrôle du jeu Unity"""

    # Properties pour l'UI
    unity_connected = BooleanProperty(False) # connexion Unity
    obs_enabled = BooleanProperty(False) # obtacles
    left_hand_enabled = BooleanProperty(True) # main gauche
    right_hand_enabled = BooleanProperty(True) # main droite
    cube_per_min = NumericProperty(60) # cubes/min
    target_hr = NumericProperty(50)  # % FCmax

    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        app = App.get_running_app()

        # Managers
        self.udp_controller = app.udp_controller
        self.udp_discovery = app.udp_discovery
        self.hr_session = app.hr_session
        self.session = app.session

        # Vérifier la connexion Unity (au cas où on arrive dans l'écran après la connexion)
        self.unity_connected = self.udp_discovery.is_unity_connected()
        if self.unity_connected:
            if self.session.config.target_hr_percent is not None:
                self.target_hr = self.session.config.target_hr_percent
            if self.session.config.obs_enabled is not None:
                self.obs_enabled = self.session.config.obs_enabled
            if self.session.config.left_hand_enabled is not None:
                self.left_hand_enabled = self.session.config.left_hand_enabled
            if self.session.config.right_hand_enabled is not None:
                self.right_hand_enabled = self.session.config.right_hand_enabled
            if self.session.config.cube_per_min is not None:
                self.cube_per_min = self.session.config.cube_per_min

        # S'abonner pour écouter les eventbus
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.subscribe("session_updated", self.on_session_updated)

    def on_leave(self):
        event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.unsubscribe("session_updated", self.on_session_updated)

    # ========== CALLBACKS ==========

    def handle_unity_connection(self, data):
        connected = data["connected"]
        self.unity_connected = connected

    def on_session_updated(self, session):
         # Mise à jour UI
        if session.config.target_hr_percent is not None:
            self.target_hr = session.config.target_hr_percent
        if session.config.obs_enabled is not None:
            self.obs_enabled = session.config.obs_enabled
        if session.config.left_hand_enabled is not None:
            self.left_hand_enabled = session.config.left_hand_enabled
        if session.config.right_hand_enabled is not None:
            self.right_hand_enabled = session.config.right_hand_enabled
        if session.config.cube_per_min is not None:
            self.cube_per_min = session.config.cube_per_min

    # ========== OBSTACLES ==========

    def on_obstacles_toggle(self, is_active):
        """Toggle obstacles ON/OFF"""
        self.session.config.obs_enabled = is_active
        logger.info(f"🎮 Obstacles: {'ON' if is_active else 'OFF'}")

        # Envoyer via UDP
        if self.udp_controller:
            self.udp_controller.set_obstacle("1" if is_active else "0")

    # ========== MAINS ==========

    def on_left_hand_toggle(self, is_active):
        """Active/désactive l'interaction avec la main gauche"""
        if not is_active and not self.right_hand_enabled:
            # Au moins une main doit rester active
            toast("Au moins une main doit être active")
            self.ids.left_hand_checkbox.active = True
            return

        self.left_hand_enabled = is_active
        self.session.config.left_hand_enabled = is_active
        logger.info(f"🖐️ Main gauche: {'ON' if is_active else 'OFF'}")

        if self.udp_controller:
            self.udp_controller.set_left_hand(is_active)

    def on_right_hand_toggle(self, is_active):
        """Active/désactive l'interaction avec la main droite"""
        if not is_active and not self.left_hand_enabled:
            # Au moins une main doit rester active
            toast("Au moins une main doit être active")
            self.ids.right_hand_checkbox.active = True
            return

        self.right_hand_enabled = is_active
        self.session.config.right_hand_enabled = is_active
        logger.info(f"🖐️ Main droite: {'ON' if is_active else 'OFF'}")

        if self.udp_controller:
            self.udp_controller.set_right_hand(is_active)

    # ========== CUBE FREQUENCY ==========

    def on_cube_frequency_change(self, value):
        """Slider cube frequency changé"""
        self.cube_per_min = value

    def on_cube_frequency_touch_up(self):
        """Appelé quand l'utilisateur relâche le slider"""
        logger.debug(f"🎯 Slider relâché à {self.cube_per_min} cubes/min")

        self.send_cube_frequency()

    def send_cube_frequency(self):
        """Envoie le nombre de cubes/min à Unity"""
        if self.udp_controller:
            success = self.udp_controller.set_cube_rate(int(self.cube_per_min))
            if success:
                logger.info(f"📤 Cubes/min envoyés: {int(self.cube_per_min)}")

    # ========== TARGET HR ==========

    def on_target_hr_change(self, value):
        """Slider target HR changé"""
        self.target_hr = value

    def on_target_hr_touch_up(self):
        """Appelé quand l'utilisateur relâche le slider"""
        logger.debug(f"🎯 Slider relâché à {self.target_hr}")
        self.session.config.update_target(self.target_hr)

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
                toast("❌ Échec de la mise en pause")

    def resume_game(self):
        """Reprend le jeu"""
        if self.udp_controller:
            success = self.udp_controller.resume_game()
            if success:
                logger.info("▶️ Jeu repris")
            else:
                toast("❌ Échec de la reprise")

    def restart_game(self):
        """Redémarre le jeu"""
        if self.udp_controller:
            success = self.udp_controller.restart_game()
            if success:
                logger.info("🔄 Jeu redémarré")
            else:
                toast("❌ Échec du redémarrage")
