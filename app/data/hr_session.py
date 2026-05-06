from kivy.app import App

from datetime import datetime
import time

from typing import List, Optional, Tuple, Callable
import json
import uuid

from utils.event_bus import event_bus
from utils.logger import get_logger

logger = get_logger(__name__)

class HRSession:
    """Gestionnaire des données physiologiques"""
    
    def __init__(self, session):

        self.session = session

        # Historique des données de FC brute
        self.hr_history = []
        self.hr_time = []

        # Historique des données de %FCmax
        self.hrmax_percent_history = []

        # S'abonner aux évenements
        event_bus.subscribe("heart_rate_received", self.on_hr_received)

    def reset(self):
        """Réinitialise la session"""
        self.hr_history.clear()
        self.hr_time.clear()
        self.hrmax_percent_history.clear()

    # ============== CALLBACKS ==============

    def on_hr_received(self, bpm: int):

        # Calcul du %FCmax
        hrmax_percent = self._compute_percent(bpm)

        # Calcul du temps relatif depuis le début de la session
        t = time.time() - self.session.start_time

        # Enregistrer les données
        self.hr_history.append(bpm)
        self.hr_time.append(t)
        self.hrmax_percent_history.append(hrmax_percent)

    # =========================
    # CALCULS
    # =========================

    def _compute_percent(self, bpm: int) -> Optional[float]:
        try:
            app = App.get_running_app()
            max_hr = app.user_profile.calculate_max_hr()
            return (bpm / max_hr) * 100
        except:
            return None
    
    # =========================
    # GRAPH DATA
    # =========================

    def get_graph_data(self):
        return (self.hr_time, self.hr_history)

    def get_graph_percent(self):
        return (self.hr_time, self.hrmax_percent_history)

    # =========================
    # STATS
    # =========================

    def get_duration(self) -> float:
        if not self.session.start_time:
            return 0
        return time.time() - self.session.start_time

    # =========================
    # EXPORT
    # =========================

    # def save_json(self, path: str):

    #     payload = {
    #         "session_id": self.session_id,
    #         "duration": self.get_duration(),
    #         "data": list(self.data)
    #     }

    #     with open(path, "w") as f:
    #         json.dump(payload, f, indent=2)

    #     logger.info(f"💾 JSON saved: {path}")

    # def save_csv(self):

    #     from datetime import datetime
    #     path = f"sessions/session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    #     with open(path, "w") as f:
    #         f.write("Time,FC,%FCmax\n")

    #         for p in self.data:
    #             f.write(
    #                 f"{p['t']},{p['bpm']},{p['percent']}\n"
    #             )

    #     logger.info(f"💾 CSV saved: {path}")