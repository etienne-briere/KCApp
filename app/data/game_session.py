
from app.data.session_config import SessionConfig
from app.data.hr_session import HRSession
from app.data.user_profile import UserProfile
from app.data.game_metrics import GameMetrics

import time

class GameSession:

    def __init__(self, user_profile=None):
        self.user_profile = user_profile if user_profile else UserProfile()
        self.config = SessionConfig()
        self.hr_session = HRSession(self)
        self.metrics = GameMetrics(self)

        self.game_state = "idle" 

        # Temps de début de la session pour calcul du temps relatif dans les graphiques
        self.start_time = time.time()
        print(f"GameSession initialized at {self.start_time}")
    
    def reset(self):
        """Réinitialise la session"""
        self.start_time = time.time()

        self.hr_session.reset()
        self.metrics.reset()

        
