import time
from utils.event_bus import event_bus

class SessionConfig:
    """Paramètres du jeu"""
    def __init__(self, session):
        self.session = session

        self.model = "Unknown"
        self.target_hr_percent = None
        self.obs_enabled = None
        self.left_hand_enabled = None
        self.right_hand_enabled = None
        self.cube_per_min = None
        self.session_duration = None  # secondes
        self.obstacle_probability = None  # %
        self.incremental_steps = None
        self.incremental_min_cpm = None
        self.incremental_max_cpm = None
        self.adaptive_min_cpm = None
        self.adaptive_max_cpm = None
        self.warmup_enabled = None
        self.warmup_duration = None  # secondes

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
            self.obs_enabled = value.strip().lower() == "true"

        elif key == "leftHand":
            self.left_hand_enabled = value.strip().lower() == "true"

        elif key == "rightHand":
            self.right_hand_enabled = value.strip().lower() == "true"

        elif key == "fixedCpm":
            self.cube_per_min = int(value)

        elif key == "sessionDuration":
            self.session_duration = int(value)

        elif key == "obstacleProbability":
            self.obstacle_probability = int(value)

        elif key == "incrementalSteps":
            self.incremental_steps = int(value)

        elif key == "incrementalMinCpm":
            self.incremental_min_cpm = int(value)

        elif key == "incrementalMaxCpm":
            self.incremental_max_cpm = int(value)

        elif key == "adaptiveMinCpm":
            self.adaptive_min_cpm = int(value)

        elif key == "adaptiveMaxCpm":
            self.adaptive_max_cpm = int(value)

        elif key == "warmupEnabled":
            self.warmup_enabled = value.strip().lower() == "true"

        elif key == "warmupDuration":
            self.warmup_duration = int(value)
    
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

