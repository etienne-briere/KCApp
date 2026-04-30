from datetime import datetime
import time
from kivy.app import App


from typing import List, Optional, Tuple, Callable
from collections import deque
import json
import uuid

from utils.event_bus import event_bus
from utils.logger import get_logger

logger = get_logger(__name__)

class HRSession:
    """Gestionnaire des données physiologiques"""
    
    def __init__(self, max_points: int = 3600):
        """
        Args:
            max_points: Nombre maximum de points à conserver (défaut: 1h à 1Hz)
        """
        app = App.get_running_app()
        self.session = app.session
        self.session_id = str(uuid.uuid4())

        # stockage des points (dict)
        self.data: deque = deque(maxlen=max_points)

        self.start_time: Optional[float] = None
        self.is_recording = False

        # stats O(1)
        self.sum_hr = 0
        self.max_hr = 0
        self.min_hr = 999

        logger.info(f"🆕 HRSession init ({self.session_id})")

        event_bus.subscribe("heart_rate_received", self.on_hr_received)
    
    # ========== GESTION DE SESSION ==========
    
    def start_recording(self):
        """Démarre l'enregistrement de la session"""
        if self.is_recording:
            return
        
        self.start_time = time.time()
        self.is_recording = True

        logger.info("▶️ HR recording started")
    
    def stop_recording(self):
        """Arrête l'enregistrement"""
        self.is_recording = False
        logger.info(f"⏹️ HR recording stopped ({self.get_duration():.1f}s)")

    def reset(self):
        """Réinitialise la session"""
        self.data.clear()
        self.sum_hr = 0
        self.max_hr = 0
        self.min_hr = 999
        self.start_time = time.time()

    # =========================
    # INPUT (EVENT BUS)
    # =========================

    def on_hr_received(self, bpm: int):

        if not self.is_recording:
            return

        # éviter les fausses valeurs 
        if bpm < 30 or bpm > 220:
            return

        t = time.time() - self.session.start_time

        percent = self._compute_percent(bpm)

        point = {
            "t": t,
            "bpm": bpm,
            "percent": percent
        }

        self.data.append(point)

        # stats O(1)
        self.sum_hr += bpm
        self.max_hr = max(self.max_hr, bpm)
        self.min_hr = min(self.min_hr, bpm)

        event_bus.emit("hr_data_updated", point)

    # =========================
    # CALCULS
    # =========================

    def _compute_percent(self, bpm: int) -> Optional[float]:
        try:
            from kivy.app import App
            max_hr = App.get_running_app().user_profile.calculate_max_hr()
            return (bpm / max_hr) * 100
        except:
            return None
    
    # =========================
    # GRAPH DATA
    # =========================

    def get_graph_data(self) -> Tuple[List[float], List[int]]:
        return (
            [p["t"] for p in self.data],
            [p["bpm"] for p in self.data]
        )

    def get_graph_percent(self) -> Tuple[List[float], List[float]]:
        return (
            [p["t"] for p in self.data],
            [p["percent"] or 0 for p in self.data]
        )

    # =========================
    # STATS
    # =========================

    def get_duration(self) -> float:
        if not self.start_time:
            return 0
        return time.time() - self.start_time

    def get_stats(self) -> dict:
        n = len(self.data)

        return {
            "duration": self.get_duration(),
            "points": n,
            "max": self.max_hr if n else None,
            "min": self.min_hr if n else None,
            "avg": (self.sum_hr / n) if n else None
        }

    # =========================
    # EXPORT
    # =========================

    def save_json(self, path: str):

        payload = {
            "session_id": self.session_id,
            "duration": self.get_duration(),
            "data": list(self.data)
        }

        with open(path, "w") as f:
            json.dump(payload, f, indent=2)

        logger.info(f"💾 JSON saved: {path}")

    def save_csv(self):

        from datetime import datetime
        path = f"sessions/session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        with open(path, "w") as f:
            f.write("Time,FC,%FCmax\n")

            for p in self.data:
                f.write(
                    f"{p['t']},{p['bpm']},{p['percent']}\n"
                )

        logger.info(f"💾 CSV saved: {path}")