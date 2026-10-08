import time


SEX_LABELS = {"": "Non renseigné", "M": "Homme", "F": "Femme"}


def normalize_sex(value) -> str:
    """Ramène une valeur de sexe à "M", "F" ou "" (non renseigné)."""
    v = str(value or "").strip().upper()
    if v in ("M", "H", "HOMME", "MALE", "1"):
        return "M"
    if v in ("F", "FEMME", "FEMALE", "2"):
        return "F"
    return ""


def format_weight(weight) -> str:
    """Poids pour affichage/saisie : "72", "72.5" ou "" si non renseigné."""
    try:
        w = float(weight or 0)
    except (TypeError, ValueError):
        return ""
    if w <= 0:
        return ""
    return str(int(w)) if w == int(w) else f"{w:.1f}"


class UserProfile:
    """Gestionnaire du profil utilisateur"""
    id: str
    age: int
    name: str
    weight: float  # kg, 0 = non renseigné (estimation des kcal en fin de partie)
    sex: str  # "M", "F" ou "" (non renseigné)
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
        self.weight = 0.0
        self.sex = ""
        self._age_override_until = 0.0
        self._name_override_until = 0.0
        self._weight_override_until = 0.0
        self._sex_override_until = 0.0

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

    def set_weight_locally(self, weight) -> None:
        """Équivalent de set_age_locally pour le poids (kg, 0 ou None = non renseigné)."""
        self.weight = float(weight or 0)
        self._weight_override_until = time.time() + self._GRACE_PERIOD

    def set_sex_locally(self, sex) -> None:
        """Équivalent de set_age_locally pour le sexe ("M", "F" ou "")."""
        self.sex = normalize_sex(sex)
        self._sex_override_until = time.time() + self._GRACE_PERIOD

    def update_from_udp(self, key, value):
        if key == "userAge":
            if time.time() < self._age_override_until:
                return
            self.age = int(value)
        elif key == "playerName":
            if time.time() < self._name_override_until:
                return
            self.name = value
        elif key == "userWeight":
            if time.time() < self._weight_override_until:
                return
            try:
                self.weight = max(0.0, float(value))
            except ValueError:
                pass
        elif key == "userSex":
            if time.time() < self._sex_override_until:
                return
            self.sex = normalize_sex(value)

    def calculate_max_hr(self):
        """Calcule la FCmax basée sur l'âge"""
        return 211 - (self.age * 0.64)