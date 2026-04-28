class SessionConfig:
    """Paramètres du jeu"""
    def __init__(self):
        self.model = None
        self.target_hr_percent = None
        self.obs_enabled = None

    def update_from_udp(self, key, value):
        if key == "SelectedModel":
            self.model = value
        elif key == "userHRMTarget":
            self.target_hr_percent = float(value)
        elif key == "obs":
            self.obs_enabled = bool(value)