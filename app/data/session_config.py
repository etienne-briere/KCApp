class SessionConfig:
    """Paramètres envoyés par Unity"""
    def __init__(self):
        self.model = None
        self.target_hr_percent = None

    def update_from_udp(self, key, value):
        if key == "SelectedModel":
            self.model = value
        elif key == "targetHR":
            self.target_hr_percent = float(value)