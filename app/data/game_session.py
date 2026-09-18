
from app.data.session_config import SessionConfig
from app.data.hr_session import HRSession
from app.data.user_profile import UserProfile
from app.data.game_metrics import GameMetrics

import csv
import os
import time
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

SESSIONS_DIR = "sessions"


class SessionRecord:
    """
    Instantané figé des données d'une session terminée (créé par
    GameSession.reset()), en attente d'export CSV ou de suppression par
    l'utilisateur — voir l'écran HR Tracking.
    """

    def __init__(self, hr_times, hr_values, hrmax_values,
                 target_times, target_values, cpm_times, cpm_values,
                 age, hr_max, model, duration):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = f"session_{self.timestamp}.csv"

        self.hr_times = hr_times
        self.hr_values = hr_values
        self.hrmax_values = hrmax_values
        self.target_times = target_times
        self.target_values = target_values
        self.cpm_times = cpm_times
        self.cpm_values = cpm_values

        self.age = age
        self.hr_max = hr_max
        self.model = model
        self.duration = duration

    def export_csv(self, folder: str = SESSIONS_DIR,
                    include_target: bool = True, include_cpm: bool = True) -> str:
        """
        Écrit le CSV sur disque : une ligne par mesure de FC (la métrique
        la plus dense), avec la %FC cible et les cubes/min reportés à
        leur dernière valeur connue à cet instant (aucune valeur
        interpolée/inventée entre deux mesures réelles).

        include_target / include_cpm : n'inclut la colonne correspondante
        que si demandé — reflète les cases à cocher du graphique au
        moment de l'export.

        Returns:
            str: chemin du fichier créé
        """
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, self.filename)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["# Date", self.timestamp])
            writer.writerow(["# Âge patient", self.age])
            writer.writerow(["# FCmax estimée (bpm)", round(self.hr_max, 1)])
            writer.writerow(["# Modèle de jeu", self.model])
            writer.writerow(["# Durée (s)", round(self.duration, 1)])
            writer.writerow([])

            header = ["temps_s", "bpm", "fcmax_pct"]
            if include_target:
                header.append("cible_pct")
            if include_cpm:
                header.append("cpm")
            writer.writerow(header)

            target_idx = 0
            cpm_idx = 0
            last_target = ""
            last_cpm = ""

            for t, bpm, pct in zip(self.hr_times, self.hr_values, self.hrmax_values):
                # Avancer chaque curseur jusqu'à la dernière valeur connue au temps t
                if include_target:
                    while target_idx < len(self.target_times) and self.target_times[target_idx] <= t:
                        last_target = self.target_values[target_idx]
                        target_idx += 1

                if include_cpm:
                    while cpm_idx < len(self.cpm_times) and self.cpm_times[cpm_idx] <= t:
                        last_cpm = self.cpm_values[cpm_idx]
                        cpm_idx += 1

                row = [round(t, 2), bpm, round(pct, 1) if pct is not None else ""]
                if include_target:
                    row.append(last_target)
                if include_cpm:
                    row.append(last_cpm)
                writer.writerow(row)

        logger.info(f"💾 Session exportée : {path}")
        return path


class GameSession:

    def __init__(self, user_profile=None):
        self.user_profile = user_profile if user_profile else UserProfile()
        self.config = SessionConfig(self)
        self.hr_session = HRSession(self)
        self.metrics = GameMetrics(self)

        # Initialisation des états
        self.is_recording = False
        self.game_state = "idle"
        self.start_time = None

        # Sessions passées en attente d'export ou de suppression (voir
        # reset() et l'écran HR Tracking)
        self.pending_sessions = []

    # ========== GESTION DE SESSION ==========

    def start_recording(self):
        """Démarre l'enregistrement des données de la session"""
        if self.is_recording:
            return

        self.start_time = time.time()
        self.is_recording = True

        logger.info("▶️ Recording started")

    def stop_recording(self):
        """Arrête l'enregistrement"""
        self.is_recording = False

        logger.info(f"⏹️ Recording stopped ({self.get_duration():.1f}s)")

    def reset(self):
        """
        Archive la session courante (si elle contient des données de FC)
        dans pending_sessions pour export/suppression différés, puis la
        réinitialise.

        Returns:
            SessionRecord: l'instantané archivé, ou None si la session
            était vide (rien à archiver).
        """
        record = self.snapshot()
        if record:
            self.pending_sessions.append(record)

        self.start_time = time.time()
        self.hr_session.reset()
        self.metrics.reset()
        self.config.reset()

        return record

    # ========== EXPORT ==========

    def snapshot(self) -> SessionRecord:
        """Capture un instantané figé de la session courante, sans la modifier"""
        if not self.hr_session.hr_time:
            return None

        return SessionRecord(
            hr_times=list(self.hr_session.hr_time),
            hr_values=list(self.hr_session.hr_history),
            hrmax_values=list(self.hr_session.hrmax_percent_history),
            target_times=list(self.config.target_time),
            target_values=list(self.config.target_history),
            cpm_times=list(self.metrics.cpm_time),
            cpm_values=list(self.metrics.cpm_history),
            age=self.user_profile.age,
            hr_max=self.user_profile.calculate_max_hr(),
            model=self.config.model,
            duration=self.hr_session.get_duration(),
        )

    def export_csv(self, folder: str = SESSIONS_DIR,
                    include_target: bool = True, include_cpm: bool = True):
        """
        Exporte immédiatement la session en cours (sans la réinitialiser
        ni l'archiver dans pending_sessions).

        Returns:
            str: chemin du fichier créé, ou None si aucune donnée de FC
        """
        record = self.snapshot()
        if not record:
            logger.info("📊 Aucune donnée de FC à exporter")
            return None

        return record.export_csv(folder, include_target=include_target, include_cpm=include_cpm)
