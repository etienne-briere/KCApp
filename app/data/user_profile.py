import time


class UserProfile:
    """Gestionnaire du profil utilisateur"""
    id: str
    age: int
    name: str
    hr_max: int

    # Fenêtre pendant laquelle un écho UDP contredisant un changement local
    # récent (age/name) est ignoré — voir set_age_locally/set_name_locally.
    # Nécessaire car Unity peut renvoyer un instantané de son état courant
    # (userAge/playerName) juste après avoir reçu notre propre mise à jour,
    # avant de l'avoir lui-même appliquée côté jeu : sans ce délai, cet écho
    # encore périmé écrase la valeur qu'on vient de poser localement.
    _GRACE_PERIOD = 3.0

    def __init__(self):
        self.age = 25  # Valeur par défaut
        self.name = ""
        self._age_override_until = 0.0
        self._name_override_until = 0.0

    def set_age_locally(self, age: int) -> None:
        """
        Pose l'âge suite à une action locale (sélection/édition de profil,
        voir player_profile_screen.py/pilotage_screen.py) plutôt qu'un
        update_from_udp — protège la valeur contre un écho périmé de Unity
        pendant _GRACE_PERIOD.
        """
        self.age = age
        self._age_override_until = time.time() + self._GRACE_PERIOD

    def set_name_locally(self, name: str) -> None:
        """Équivalent de set_age_locally pour le nom."""
        self.name = name
        self._name_override_until = time.time() + self._GRACE_PERIOD

    def update_from_udp(self, key, value):
        if key == "userAge":
            if time.time() < self._age_override_until:
                return
            self.age = int(value)
        elif key == "playerName":
            if time.time() < self._name_override_until:
                return
            self.name = value

    def calculate_max_hr(self):
        """Calcule la FCmax basée sur l'âge"""
        return 211 - (self.age * 0.64)