import time
from utils.event_bus import event_bus

class SessionConfig:
    """Paramètres du jeu"""
    def __init__(self, session):
        self.session = session

        self.model = "Unknown"
        self.target_hr_percent = None
        self.obs_enabled = None

        self.target_time = []
        self.target_history = []

    def update_from_udp(self, key, value):
        if key == "SelectedModel":
            self.model = value

        elif key == "userHRMTarget":
            self.target_hr_percent = int(value)
            self.session.start_recording() 

            # stocker dans l'historique
            t = time.time() - self.session.start_time
            self.target_time.append(t)
            self.target_history.append(self.target_hr_percent)
        
        elif key == "obs":
            self.obs_enabled = bool(value)
    
    def update_target(self, target_percent):
        """Met à jour la cible de FC et stocke dans l'historique"""
        self.target_hr_percent = target_percent

        # stocker dans l'historique
        t = time.time() - self.session.start_time
        self.target_time.append(t)
        self.target_history.append(target_percent)
    
    def reset(self):
        """Réinitialise les données"""
        self.target_time.clear()
        self.target_history.clear()

