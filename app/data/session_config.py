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
        self.require_hr_signal = None
        self.brick_speed = None  # vitesse des briques (tous modes)
        self.environment = None  # environnement choisi par le joueur (Cosmos, Forest, Sea, Mountain, Sky)

        # Contrôleur hybride (Unity) : réglages persistants, renvoyés par Unity
        self.controller_config = None   # off, legacy_drl, hybrid_short_term, drl_run3, drl_run3_no_warmup, pid_only, custom
        self.drl_model = None           # deployed / run3
        self.pid_warmup = None          # PID pendant l'échauffement
        self.pid_backup = None          # PID de secours (cycle limite)
        # État en cours de partie (envoyé par Unity à chaque bascule)
        self.controller_state = None    # PID_WARMUP, DRL, PID_BACKUP, MANUAL, PID, LEGACY_xxx
        self.controller_switch_reason = None

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

        elif key == "requireHRSignal":
            self.require_hr_signal = value.strip().lower() == "true"

        elif key == "brickSpeed":
            self.brick_speed = int(value)

        elif key == "environment":
            self.environment = value.strip()

        elif key == "controllerConfig":
            self.controller_config = value.strip().lower()

        elif key == "drlModel":
            self.drl_model = value.strip().lower()

        elif key == "warmupPid":
            self.pid_warmup = value.strip().lower() in ("true", "1")

        elif key == "backupPid":
            self.pid_backup = value.strip().lower() in ("true", "1")

        elif key == "controllerState":
            self.controller_state = value.strip()

        elif key == "controllerSwitchReason":
            self.controller_switch_reason = value.strip()

    @property
    def uses_hybrid_controller(self):
        """Vrai si Unity utilise le contrôleur hybride en mode DRL (configuration différente de off)"""
        return self.controller_config not in (None, "", "off", "pid_only")

    @property
    def effective_pid_warmup(self):
        return bool(self.uses_hybrid_controller and self.pid_warmup)

    @property
    def effective_pid_backup(self):
        return bool(self.uses_hybrid_controller and self.pid_backup)

    @property
    def is_drl_run3(self):
        """Mode DRL avec le modèle Run 3"""
        return bool(self.uses_hybrid_controller and self.drl_model == "run3")
    
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

