"""
Écran « Vue du joueur » : affiche en direct ce que voit le joueur dans le casque.

Principe (voir app/network/game_stream_protocol.py pour le détail du protocole) :
  - la tablette demande le flux à Unity par le canal UDP habituel
    (stream_config:<fps>,<largeur>,<qualité> puis stream_game:START) ;
  - Unity renvoie des images JPEG fragmentées en UDP vers le port UDP_PORT_STREAM ;
  - GameStreamReceiver les assemble ; cet écran décode la plus récente et l'affiche.

« Bail » : Unity arrête tout seul le flux s'il ne reçoit pas stream_game:START
depuis 6 s ; la tablette le renvoie donc toutes les STREAM_LEASE_RENEW_S secondes.
Si la tablette plante, si le Wi-Fi coupe ou si la scène du jeu change, le flux
s'arrête puis reprend sans intervention.
"""

import io
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivymd.uix.screen import MDScreen

from app.network.game_stream_receiver import GameStreamReceiver
from config import (STREAM_FLIP_VERTICAL, STREAM_FPS, STREAM_LEASE_RENEW_S, STREAM_NO_SIGNAL_S,
                    STREAM_QUALITY, STREAM_WIDTH, UDP_PORT_STREAM)
from utils.logger import get_logger

logger = get_logger(__name__)


class GameScreen(MDScreen):
    """Écran de streaming du jeu Unity"""

    # Properties pour l'UI
    is_streaming = BooleanProperty(False)     # Unity a reçu notre demande de flux
    has_signal = BooleanProperty(False)       # des images arrivent
    current_fps = NumericProperty(0)
    stream_width = NumericProperty(0)
    stream_height = NumericProperty(0)
    status_text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.udp_discovery = None
        self.udp_controller = None
        self.receiver = None
        self._last_seq = 0
        self._last_frame_time = 0.0
        self._last_stats_time = 0.0
        self._renew_event = None
        self._update_event = None

    # ========== CYCLE DE VIE ==========

    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        app = App.get_running_app()
        self.udp_discovery = app.udp_discovery
        self.udp_controller = app.udp_controller

        self._last_seq = 0
        self._last_frame_time = 0.0
        self.has_signal = False
        self.is_streaming = False
        self.current_fps = 0

        self.receiver = GameStreamReceiver(port=UDP_PORT_STREAM)
        if not self.receiver.start():
            self.status_text = f"Réception impossible : {self.receiver.error}"
            return

        self._renew_stream(0)
        self._renew_event = Clock.schedule_interval(self._renew_stream, STREAM_LEASE_RENEW_S)
        self._update_event = Clock.schedule_interval(self._update_image, 1 / 30.)

    def on_leave(self):
        """Appelé à la sortie de l'écran : on coupe le flux côté Unity et on libère le port"""
        for event in (self._renew_event, self._update_event):
            if event is not None:
                event.cancel()
        self._renew_event = self._update_event = None

        if self.udp_controller and self.udp_discovery and self.udp_discovery.is_unity_connected():
            self.udp_controller.set_stream_game("STOP")
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver = None

        self.is_streaming = False
        self.has_signal = False
        self.current_fps = 0
        self.status_text = ""
        self.ids.game_image.texture = None
        logger.info("Écran de streaming désactivé")

    # ========== DEMANDE DE FLUX ==========

    def _renew_stream(self, _dt):
        """Demande (ou renouvelle le bail du) flux. Silencieux tant que le jeu n'est pas connecté."""
        if not self.udp_discovery or not self.udp_discovery.is_unity_connected():
            self.is_streaming = False
            return
        if not self.is_streaming:
            # Premier START (ou reprise après une coupure) : on renvoie aussi les réglages.
            self.udp_controller.set_stream_config(STREAM_FPS, STREAM_WIDTH, STREAM_QUALITY)
        self.is_streaming = bool(self.udp_controller.set_stream_game("START"))

    # ========== MISE À JOUR DES IMAGES ==========

    def _decode(self, jpeg):
        """JPEG -> texture Kivy (décodeur SDL2 de Kivy : pas besoin de Pillow, absent du build Android)."""
        try:
            tex = CoreImage(io.BytesIO(jpeg), ext="jpg", nocache=True).texture
        except Exception as exc:  # noqa: BLE001
            logger.debug("Image du flux illisible : %s", exc)
            return None
        if tex is not None and STREAM_FLIP_VERTICAL:
            tex.flip_vertical()
        return tex

    def _update_image(self, _dt):
        """Appelé 30 fois par seconde ; ne décode que quand une nouvelle image est arrivée"""
        now = time.time()
        if self.receiver is None:
            return

        item = self.receiver.get_latest(self._last_seq)
        if item is not None:
            self._last_seq, jpeg, _t = item
            tex = self._decode(jpeg)
            if tex is not None:
                self.ids.game_image.texture = tex
                self.stream_width, self.stream_height = tex.size
                self._last_frame_time = now

        self.has_signal = (now - self._last_frame_time) < STREAM_NO_SIGNAL_S

        if now - self._last_stats_time >= 1.0:
            self._last_stats_time = now
            self._update_status()

    def _update_status(self):
        stats = self.receiver.stats()
        self.current_fps = round(stats["fps"])
        connected = bool(self.udp_discovery and self.udp_discovery.is_unity_connected())
        if not connected:
            self.status_text = "En attente du jeu (Unity non connecté)"
        elif not self.has_signal:
            self.status_text = "Connexion au flux vidéo…"
        else:
            self.status_text = (f"{self.current_fps} img/s · {self.stream_width}×{self.stream_height} · "
                                f"{stats['kbps']:.0f} ko/s · {stats['frames_dropped']} perdues")
