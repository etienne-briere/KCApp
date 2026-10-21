"""
Récepteur du flux vidéo « vue du joueur » : un thread lit le port UDP, assemble
les images (voir game_stream_protocol) et garde la plus récente.

L'interface Kivy n'a qu'à appeler get_latest() ; le décodage du JPEG se fait côté
interface (thread principal), le thread réseau ne fait que de l'assemblage.
"""

from __future__ import annotations

import socket
import threading
import time
from collections import deque
from typing import Deque, Optional, Tuple

from app.network.game_stream_protocol import FrameAssembler, MAX_DATAGRAM
from config import UDP_PORT_STREAM
from utils.logger import get_logger

logger = get_logger(__name__)

STATS_WINDOW_S = 2.0      # fenêtre de calcul des img/s et du débit


class GameStreamReceiver:
    def __init__(self, port: int = UDP_PORT_STREAM):
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._assembler = FrameAssembler()
        self._seq = 0
        self._latest: Optional[Tuple[int, bytes, float]] = None     # (numéro, jpeg, heure de réception)
        self._recent: Deque[Tuple[float, int]] = deque()            # (heure, octets) des images livrées
        self._lock = threading.Lock()
        self.error: Optional[str] = None

    # ------------------------------------------------------------------ cycle de vie
    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        if self._running:
            return True
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Un tampon large absorbe une rafale (une image = 20 à 80 datagrammes envoyés d'un coup).
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
            except OSError:
                pass
            sock.bind(("0.0.0.0", self.port))
            sock.settimeout(0.5)
        except OSError as exc:
            sock.close()
            self.error = f"port UDP {self.port} indisponible ({exc})"
            logger.error("Flux vidéo : %s", self.error)
            return False
        self.error = None
        self._sock = sock
        self._assembler.reset()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="GameStreamReceiver", daemon=True)
        self._thread.start()
        logger.info("Flux vidéo : écoute UDP sur le port %s", self.port)
        return True

    def stop(self) -> None:
        self._running = False
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        with self._lock:
            self._latest = None
            self._recent.clear()

    # ------------------------------------------------------------------ réception
    def _loop(self) -> None:
        sock = self._sock
        while self._running and sock is not None:
            try:
                data, _addr = sock.recvfrom(MAX_DATAGRAM)
            except socket.timeout:
                continue
            except OSError:
                break
            jpeg = self._assembler.feed(data)
            if jpeg is None:
                continue
            now = time.time()
            with self._lock:
                self._seq += 1
                self._latest = (self._seq, jpeg, now)
                self._recent.append((now, len(jpeg)))
                self._purge(now)

    def _purge(self, now: float) -> None:
        while self._recent and now - self._recent[0][0] > STATS_WINDOW_S:
            self._recent.popleft()

    # ------------------------------------------------------------------ lecture (thread principal)
    def get_latest(self, after_seq: int = 0) -> Optional[Tuple[int, bytes, float]]:
        """Dernière image complète si elle est plus récente que `after_seq`, sinon None."""
        with self._lock:
            item = self._latest
        if item is not None and item[0] > after_seq:
            return item
        return None

    def stats(self) -> dict:
        """Cadence et débit sur les dernières secondes, et compteurs de pertes."""
        now = time.time()
        with self._lock:
            self._purge(now)
            n = len(self._recent)
            octets = sum(b for _t, b in self._recent)
        fps = n / STATS_WINDOW_S
        return {
            "fps": fps,
            "kbps": octets / STATS_WINDOW_S / 1024.0,
            "frames_ok": self._assembler.frames_ok,
            "frames_dropped": self._assembler.frames_dropped,
            "packets_bad": self._assembler.packets_bad,
        }
