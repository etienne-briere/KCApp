from datetime import datetime
from typing import List, Optional, Tuple, Callable
from collections import deque
import json

from utils.logger import get_logger

logger = get_logger(__name__)

class HRSession:
    """Gestionnaire centralisé des données de fréquence cardiaque"""
    
    def __init__(self, max_points: int = 3600):
        """
        Args:
            max_points: Nombre maximum de points à conserver (défaut: 1h à 1Hz)
        """
        # Données de session
        self.data_hr: deque = deque(maxlen=max_points)  # (timestamp, bpm, hr_percent)
        self.session_start_time: Optional[datetime] = None
        self.is_recording = False
        
        # Statistiques
        self.total_points = 0
        self.max_hr = 0
        self.min_hr = 999
        self.avg_hr = 0
        
        # Callbacks
        self.on_data_added: Optional[Callable] = None
        
        logger.info(f"Session HR initialisée (max: {max_points} points)")
    
    # ========== GESTION DE SESSION ==========
    
    def start_recording(self):
        """Démarre l'enregistrement de la session"""
        if self.is_recording:
            logger.warning("⚠️ Enregistrement déjà en cours")
            return
        
        self.session_start_time = datetime.now()
        self.is_recording = True
        logger.info(f"📹 Enregistrement démarré: {self.session_start_time}")
    
    def stop_recording(self):
        """Arrête l'enregistrement"""
        if not self.is_recording:
            logger.warning("⚠️ Aucun enregistrement en cours")
            return
        
        self.is_recording = False
        duration = self.get_session_duration()
        logger.info(f"⏹️ Enregistrement arrêté - Durée: {duration}s")
    
    def clear_session(self):
        """Réinitialise la session (pas utilisé)"""
        self.data_hr.clear()
        self.session_start_time = None
        self.is_recording = False
        self.total_points = 0
        self.max_hr = 0
        self.min_hr = 999
        self.avg_hr = 0
        
        logger.info("🗑️ Session réinitialisée")
    
    # ========== AJOUT DE DONNÉES ==========
    
    def add_heart_rate(self, bpm: int, hr_percent: Optional[float] = None):
        """
        Ajoute une donnée de FC à la session
        
        Args:
            bpm: Fréquence cardiaque en BPM
            hr_percent: Pourcentage de FCmax (optionnel)
        """
        if not self.is_recording:
            logger.debug("⚠️ Enregistrement non démarré - donnée ignorée")
            return
        
        # Calculer le timestamp relatif (secondes depuis le début)
        elapsed_time = self.get_session_duration()
        
        # Ajouter les données
        self.data_hr.append((elapsed_time, bpm, hr_percent))
        self.total_points += 1
        
        # Mettre à jour les statistiques
        self._update_stats(bpm)
        
        logger.debug(f"➕ HR ajoutée: {bpm} BPM à t={elapsed_time}s")
        
        # Callback
        if self.on_data_added:
            self.on_data_added(elapsed_time, bpm, hr_percent)
    
    def _update_stats(self, bpm: int):
        """Met à jour les statistiques de la session"""
        self.max_hr = max(self.max_hr, bpm)
        self.min_hr = min(self.min_hr, bpm)
        
        # Calculer la moyenne
        if self.data_hr:
            total = sum(point[1] for point in self.data_hr)
            self.avg_hr = total / len(self.data_hr)
    
    # ========== RÉCUPÉRATION DE DONNÉES ==========
    
    def get_all_data(self) -> List[Tuple[float, int, Optional[float]]]:
        """
        Retourne toutes les données de la session (pas utilisé)
        
        Returns:
            List de tuples (timestamp, bpm, hr_percent)
        """
        return list(self.data_hr)
    
    def get_data_for_graph(self) -> Tuple[List[float], List[int]]:
        """
        Retourne les données formatées pour le graphique (pas utilisé)
        
        Returns:
            Tuple (times, bpms)
        """
        if not self.data_hr:
            return [], []
        
        times = [point[0] for point in self.data_hr]
        bpms = [point[1] for point in self.data_hr]
        
        return times, bpms
    
    def get_data_for_graph_percent(self) -> Tuple[List[float], List[float]]:
        """
        Retourne les données en % FCmax pour le graphique
        
        Returns:
            Tuple (times, hr_percents)
        """
        if not self.data_hr:
            return [], []
        
        times = [point[0] for point in self.data_hr]
        hr_percents = [point[2] if point[2] is not None else 0 for point in self.data_hr]
        
        return times, hr_percents
    
    # ========== STATISTIQUES ==========
    
    def get_session_duration(self) -> float:
        """
        Retourne la durée de la session en secondes
        
        Returns:
            Durée en secondes
        """
        if not self.session_start_time:
            return 0.0
        
        return (datetime.now() - self.session_start_time).total_seconds()
    
    def get_stats(self) -> dict:
        """
        Retourne les statistiques de la session
        
        Returns:
            Dictionnaire avec les stats
        """
        return {
            'duration': self.get_session_duration(),
            'total_points': self.total_points,
            'max_hr': self.max_hr if self.max_hr > 0 else None,
            'min_hr': self.min_hr if self.min_hr < 999 else None,
            'avg_hr': round(self.avg_hr, 1) if self.avg_hr > 0 else None,
            'is_recording': self.is_recording,
            'start_time': self.session_start_time.isoformat() if self.session_start_time else None
        }
    
    # ========== SAUVEGARDE / CHARGEMENT ==========
    
    def save_to_file(self, filepath: str) -> bool:
        """
        Sauvegarde la session dans un fichier JSON
        
        Args:
            filepath: Chemin du fichier
            
        Returns:
            True si sauvegarde réussie
        """
        try:
            data = {
                'session_info': {
                    'start_time': self.session_start_time.isoformat() if self.session_start_time else None,
                    'duration': self.get_session_duration(),
                    'total_points': self.total_points
                },
                'statistics': self.get_stats(),
                'data': [
                    {
                        'time': point[0],
                        'bpm': point[1],
                        'hr_percent': point[2]
                    }
                    for point in self.data_hr
                ]
            }
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"💾 Session sauvegardée: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde session: {e}")
            return False