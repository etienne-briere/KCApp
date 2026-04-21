class UserProfile:
    """Gestionnaire du profil utilisateur"""
    
    def __init__(self):
        self.age = 25  # Valeur par défaut
        self.weight = 70 # Valeur par défaut en kg (pas utilisé)
        self.height = 175 # Valeur par défaut en cm (pas utilisé)
    
    def calculate_max_hr(self):
        """Calcule la FCmax basée sur l'âge"""
        return 211 - (self.age * 0.64)