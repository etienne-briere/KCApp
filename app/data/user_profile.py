class UserProfile:
    """Gestionnaire du profil utilisateur"""
    id: str
    age: int
    name: str
    hr_max: int

    def __init__(self):
        self.age = 25  # Valeur par défaut
        self.name = ""

    def update_from_udp(self, key, value):
        if key == "userAge":
            self.age = int(value)
        elif key == "playerName":
            self.name = value
    
    def calculate_max_hr(self):
        """Calcule la FCmax basée sur l'âge"""
        return 211 - (self.age * 0.64)