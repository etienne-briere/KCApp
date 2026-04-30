import time
MAX_POINTS = 6000

class SessionConfig:
    """Paramètres du jeu"""
    def __init__(self):
        self.model = "Unknown"
        self.target_hr_percent = None
        self.obs_enabled = None
        self.game_state = None

        # # valeur instantanée
        # self.cpm = None

    #    # historique CPM
    #     self.cpm_history = []
    #     self.cpm_time = []

        self.start_time = None

    def update_from_udp(self, key, value):
        if key == "SelectedModel":
            self.model = value
        elif key == "userHRMTarget":
            self.target_hr_percent = int(value)
        elif key == "obs":
            self.obs_enabled = bool(value)
        # elif key == "game_state":
        #     self.game_state = value
        # elif key == "cpm":
        #     self.cpm = float(value)

        #     # stockage pour graphe
        #     self.cpm_history.append(self.cpm)
            
        #     current_time = time.time()

        #     # Initialisation du temps de départ
        #     if self.start_time is None:
        #         self.start_time = current_time

        #     # Temps relatif (en secondes depuis le début)
        #     relative_time = current_time - self.start_time

        #     self.cpm_time.append(relative_time)

        #     if len(self.cpm_history) > MAX_POINTS:
        #         self.cpm_history.pop(0)
        #         self.cpm_time.pop(0)
