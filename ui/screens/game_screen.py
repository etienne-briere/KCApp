from kivymd.uix.screen import MDScreen
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.app import App
from PIL import Image as PILImage
import io
import time

from utils.logger import get_logger

logger = get_logger(__name__)

class GameScreen(MDScreen):
    """Écran de streaming du jeu Unity"""
    
    # Properties pour l'UI
    is_streaming = BooleanProperty(False)
    has_signal = BooleanProperty(False)
    current_fps = NumericProperty(0)
    stream_width = NumericProperty(1920)
    stream_height = NumericProperty(1080)
    latency_ms = NumericProperty(0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Managers
        self.udp_discovery = None
        self.udp_controller = None

        # Streaming
        self.latest_img = None
        self.last_img_time = 0
        self.update_event = None
        self.no_signal_texture = None
    
    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        app = App.get_running_app()
        self.udp_discovery = app.udp_discovery
        self.udp_controller = app.udp_controller
        
        # Charger l'image "NO SIGNAL"
        self.load_no_signal_texture()
        
        # Démarrer le streaming
        self.start_streaming()
        
        # Démarrer la mise à jour des images (30 FPS)
        self.update_event = Clock.schedule_interval(self.update_image, 1 / 30.)
            
    def on_leave(self):
        """Appelé à la sortie de l'écran"""
        # Arrêter le streaming
        self.stop_streaming()
        
        # Arrêter la mise à jour
        if self.update_event:
            Clock.unschedule(self.update_image)
            self.update_event = None
        
        logger.info("Écran de streaming désactivé")
    
    # ========== GESTION DU STREAMING ==========
    
    def load_no_signal_texture(self):
        """Charge la texture 'NO SIGNAL'"""
        try:
            # Vous pouvez aussi créer une texture vide ou utiliser une image
            # Pour l'instant on laisse vide, le message "NO SIGNAL" s'affichera
            pass
        except Exception as e:
            logger.error(f"Erreur chargement texture NO SIGNAL: {e}")
    
    def start_streaming(self):
        """Démarre le streaming depuis Unity"""
        if not self.udp_controller:
            logger.warning("UDP Controller non disponible")
            return
        
        # Envoyer commande START à Unity
        success = self.udp_controller.send_command("stream_game", "START")
        
        if success:
            self.is_streaming = True
            logger.info("🎥 Streaming démarré")
        else:
            logger.warning("⚠️ Échec démarrage streaming (Unity non connecté)")
    
    def stop_streaming(self):
        """Arrête le streaming depuis Unity"""
        if not self.udp_controller:
            return
        
        # Envoyer commande STOP à Unity
        self.udp_controller.send_command("stream_game", "STOP")
        
        self.is_streaming = False
        self.has_signal = False
        
        logger.info("🛑 Streaming arrêté")
    
    # def toggle_stream(self):
    #     """Toggle streaming ON/OFF"""
    #     if self.is_streaming:
    #         self.stop_streaming()
    #     else:
    #         self.start_streaming()
    
    # ========== MISE À JOUR DES IMAGES ==========
    
    def update_image(self, dt):
        """Met à jour l'image affichée (appelé 30 fois par seconde)"""
        now = time.time()
        
        # Récupérer l'image depuis UDP discovery (si implémenté)
        if hasattr(self.udp_discovery, 'latest_img') and self.udp_discovery.latest_img:
            self.latest_img = self.udp_discovery.latest_img
            self.last_img_time = getattr(self.udp_discovery, 'last_img_time', now)
        
        # Si on a une image
        if self.latest_img:
            try:
                # Convertir l'image binaire en PIL Image
                pil_image = PILImage.open(io.BytesIO(self.latest_img)).convert('RGB')
                
                # Mettre à jour la résolution
                # self.stream_width, self.stream_height = pil_image.size
                
                # Créer une texture Kivy
                tex = Texture.create(size=pil_image.size, colorfmt='rgb')
                tex.blit_buffer(pil_image.tobytes(), colorfmt='rgb', bufferfmt='ubyte')
                tex.flip_vertical()
                
                # Afficher la texture
                self.ids.game_image.texture = tex
                
                # # Indiquer qu'on a un signal
                self.has_signal = True
                
                # # Calculer FPS
                # self.update_fps()
                
                # # Calculer latence
                # self.latency_ms = int((now - self.last_img_time) * 1000)
                
            except Exception as e:
                logger.error(f"Erreur affichage image: {e}")
                self.has_signal = False
        
        # Si plus de 2 secondes sans nouvelle image
        if now - self.last_img_time > 2:
            self.has_signal = False
            self.current_fps = 0
    
    # def update_fps(self):
    #     """Calcule et met à jour le FPS"""
    #     self.frame_count += 1
    #     current_time = time.time()
        
    #     # Calculer FPS chaque seconde
    #     if current_time - self.fps_update_time >= 1.0:
    #         self.current_fps = self.frame_count
    #         self.frame_count = 0
    #         self.fps_update_time = current_time
    
    # ========== CONTRÔLES ==========
    
    # def toggle_fullscreen(self):
    #     """Toggle plein écran (à implémenter)"""
    #     from kivy.core.window import Window
        
    #     # Toggle fullscreen
    #     if Window.fullscreen == 'auto':
    #         Window.fullscreen = False
    #         logger.info("Mode fenêtre")
    #     else:
    #         Window.fullscreen = 'auto'
    #         logger.info("Mode plein écran")