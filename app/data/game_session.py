
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
                 age, hr_max, model, duration,
                 state_times=None, state_values=None):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = f"session_{self.timestamp}.csv"

        self.hr_times = hr_times
        self.hr_values = hr_values
        self.hrmax_values = hrmax_values
        self.target_times = target_times
        self.target_values = target_values
        self.cpm_times = cpm_times
        self.cpm_values = cpm_values
        self.state_times = state_times or []
        self.state_values = state_values or []

        self.age = age
        self.hr_max = hr_max
        self.model = model
        self.duration = duration

    def export_csv(self, folder: str = SESSIONS_DIR,
                    include_target: bool = True, include_cpm: bool = True,
                    include_state: bool = True) -> str:
        """
        Écrit le CSV sur disque : une ligne par mesure de FC (la métrique
        la plus dense), avec la %FC cible, les cubes/min et l'état de
        partie (idle/playing/paused) reportés à leur dernière valeur
        connue à cet instant (aucune valeur interpolée/inventée entre
        deux mesures réelles).

        include_target / include_cpm / include_state : n'inclut la colonne
        correspondante que si demandé — pour target/cpm ça reflète les
        cases à cocher du graphique au moment de l'export.

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
            if include_state:
                header.append("etat")
            writer.writerow(header)

            target_idx = 0
            cpm_idx = 0
            state_idx = 0
            last_target = ""
            last_cpm = ""
            last_state = ""

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

                if include_state:
                    while state_idx < len(self.state_times) and self.state_times[state_idx] <= t:
                        last_state = self.state_values[state_idx]
                        state_idx += 1

                row = [round(t, 2), bpm, round(pct, 1) if pct is not None else ""]
                if include_target:
                    row.append(last_target)
                if include_cpm:
                    row.append(last_cpm)
                if include_state:
                    row.append(last_state)
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
        self.game_state = "menu"  # le jeu démarre toujours sur l'écran Menu
        self.start_time = None

        # Ancrage du décompte du temps de session restant (voir
        # set_game_state / get_remaining_seconds). Volontairement séparé de
        # start_time, qui lui est posé dès userHRMTarget — reçu dès la
        # connexion Unity, bien avant le vrai game_state:Playing.
        self.playing_anchor = None
        self.paused_accum = 0.0
        self._paused_at = None

        # Historique des segments d'état (idle/playing/paused), en secondes
        # relatives à start_time — même référentiel que hr_session/config/
        # metrics — pour matérialiser les périodes idle/paused sur le
        # graphique FC et dans l'export CSV (voir get_inactive_segments /
        # get_state_history).
        self.state_segments = []
        self._current_segment = None

        # Sessions passées en attente d'export ou de suppression (voir
        # reset() et l'écran HR Tracking)
        self.pending_sessions = []

    # ========== GESTION DE SESSION ==========

    def set_game_state(self, raw_state):
        """
        Met à jour game_state et ancre le décompte du temps restant en
        conséquence (voir get_remaining_seconds). Appelé directement depuis
        le thread de réception UDP (udp_discovery.py) : le suivi des
        transitions reste correct même si aucun écran n'affiche la session
        à cet instant.
        """
        state = (raw_state or "idle").lower()
        previous = (self.game_state or "idle").lower()

        if state != previous:
            self._close_current_segment()
            if self.start_time is not None:
                self._current_segment = {
                    "state": state,
                    "start": time.time() - self.start_time,
                    "end": None,
                }
                self.state_segments.append(self._current_segment)

        if state == "playing" and previous != "playing":
            if previous == "paused":
                if self._paused_at is not None:
                    self.paused_accum += time.time() - self._paused_at
                    self._paused_at = None
            else:
                # Premier "Playing" de la session (pas une reprise après pause)
                self.playing_anchor = time.time()
                self.paused_accum = 0.0

        elif state == "paused" and previous != "paused":
            self._paused_at = time.time()

        elif state in ("idle", "menu"):
            # "menu" : le joueur n'est pas (encore) dans la scène de jeu —
            # traité comme "idle" pour l'ancrage du décompte (nouvelle
            # session en attente de démarrage).
            self.playing_anchor = None
            self.paused_accum = 0.0
            self._paused_at = None

        self.game_state = raw_state or "idle"

    def get_remaining_seconds(self):
        """
        Temps de session restant (secondes), ou None si non calculable
        (durée inconnue, ou état "paused"/inconnu — dans ce cas l'appelant
        doit conserver la dernière valeur affichée plutôt que d'afficher 0).
        """
        duration = self.config.session_duration
        state = (self.game_state or "idle").lower()

        if state == "playing" and duration is not None and self.playing_anchor is not None:
            elapsed = time.time() - self.playing_anchor - self.paused_accum
            return max(0, duration - elapsed)
        if state in ("idle", "menu"):
            return duration
        return None

    def _close_current_segment(self):
        """Ferme le segment d'état en cours sur l'instant présent."""
        if self._current_segment is not None and self.start_time is not None:
            self._current_segment["end"] = time.time() - self.start_time
        self._current_segment = None

    def _open_segment_at_zero(self):
        """
        Amorce un segment pour l'état courant à t=0, au moment où
        start_time vient d'être posé (start_recording/reset) — sans ça, le
        segment actif au tout début de l'enregistrement ne serait jamais
        capturé (set_game_state n'ouvre un segment que sur un changement
        d'état, pas sur la simple apparition de start_time).
        """
        self.state_segments = []
        state = (self.game_state or "idle").lower()
        self._current_segment = {"state": state, "start": 0.0, "end": None}
        self.state_segments.append(self._current_segment)

    def get_inactive_segments(self):
        """
        Segments (début_s, fin_s) où l'état n'était pas "playing" (idle ou
        paused), en secondes relatives à start_time — pour l'affichage de
        bandes sur le graphique FC. Le segment en cours, s'il y en a un,
        est fermé sur l'instant présent (pas encore de "end" enregistré).
        """
        if self.start_time is None:
            return []

        now = time.time() - self.start_time
        segments = []
        for seg in self.state_segments:
            if seg["state"] == "playing":
                continue
            end = seg["end"] if seg["end"] is not None else now
            segments.append((seg["start"], end))
        return segments

    def get_state_history(self):
        """
        (temps_s, état) à chaque changement d'état, triés par temps —
        pour l'export CSV (reporté à la dernière valeur connue, comme
        cible_pct/cpm — voir SessionRecord.export_csv).
        """
        times = [seg["start"] for seg in self.state_segments]
        values = [seg["state"] for seg in self.state_segments]
        return times, values

    def start_recording(self):
        """Démarre l'enregistrement des données de la session"""
        if self.is_recording:
            return

        self.start_time = time.time()
        self.is_recording = True
        self._open_segment_at_zero()

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
        self._open_segment_at_zero()

        return record

    # ========== EXPORT ==========

    def snapshot(self) -> SessionRecord:
        """Capture un instantané figé de la session courante, sans la modifier"""
        if not self.hr_session.hr_time:
            return None

        state_times, state_values = self.get_state_history()

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
            state_times=state_times,
            state_values=state_values,
        )

    def export_csv(self, folder: str = SESSIONS_DIR,
                    include_target: bool = True, include_cpm: bool = True,
                    include_state: bool = True):
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

        return record.export_csv(folder, include_target=include_target, include_cpm=include_cpm,
                                  include_state=include_state)
