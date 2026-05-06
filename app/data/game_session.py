
from app.data.session_config import SessionConfig
from app.data.hr_session import HRSession
from app.data.user_profile import UserProfile
from app.data.game_metrics import GameMetrics

import time
from utils.logger import get_logger

logger = get_logger(__name__)

class GameSession:

    def __init__(self, user_profile=None):
        self.user_profile = user_profile if user_profile else UserProfile()
        self.config = SessionConfig()
        self.hr_session = HRSession(self)
        self.metrics = GameMetrics(self)

        # Initialisation des états
        self.is_recording = False
        self.game_state = "idle" 
        self.start_time = None
    
    # ========== GESTION DE SESSION ==========
    
    def start_recording(self):
        """Démarre l'enregistrement des données de la session"""
        if self.is_recording:
            return
        
        self.start_time = time.time()
        self.is_recording = True

        logger.info("▶️ Recording started")
    
    def stop_recording(self):
        """Arrête l'enregistrement"""
        self.is_recording = False

        logger.info(f"⏹️ Recording stopped ({self.get_duration():.1f}s)")
    
    def reset(self):
        """Réinitialise la session"""
        self.start_time = time.time()
        self.hr_session.reset()
        self.metrics.reset()

        
