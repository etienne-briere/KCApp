import json
import os

from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_AGE = 25


class PlayerStore:
    """
    Gère la liste des profils joueurs (nom + âge) sauvegardée sur disque,
    pour le sélecteur de profil de l'écran Pilotage (section "Profil du
    joueur").
    """

    def __init__(self, path: str = "player_profiles.json"):
        self.path = path
        self.profiles = self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [p for p in data if "name" in p and "age" in p]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"⚠️ Impossible de charger {self.path} : {e}")
            return []

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"❌ Impossible d'enregistrer {self.path} : {e}")

    def names(self):
        """Liste des noms de profils, dans l'ordre d'enregistrement"""
        return [p["name"] for p in self.profiles]

    def get(self, name):
        """Renvoie le profil {name, age} correspondant, ou None"""
        for p in self.profiles:
            if p["name"] == name:
                return p
        return None

    def add(self, name, age):
        """Ajoute un nouveau profil, ou met à jour l'âge si le nom existe déjà"""
        existing = self.get(name)
        if existing:
            existing["age"] = age
        else:
            self.profiles.append({"name": name, "age": age})
        self._save()

    def ensure(self, name, default_age=DEFAULT_AGE):
        """
        S'assure qu'un profil existe pour ce nom, en l'ajoutant avec l'âge
        par défaut s'il n'existe pas encore (ex. playerName reçu de Unity
        pour un joueur pas encore enregistré localement). Ne touche pas à
        un profil déjà existant (ne modifie pas son âge).
        """
        if not self.get(name):
            self.add(name, default_age)
            logger.info(f"👤 Nouveau profil ajouté automatiquement : {name} ({default_age} ans)")

    def rename(self, old_name, new_name):
        """Renomme un profil existant, sans changer son âge"""
        if old_name == new_name:
            return
        profile = self.get(old_name)
        if profile:
            profile["name"] = new_name
            self._save()

    def remove(self, name):
        """Supprime un profil de la liste"""
        profile = self.get(name)
        if profile:
            self.profiles.remove(profile)
            self._save()
