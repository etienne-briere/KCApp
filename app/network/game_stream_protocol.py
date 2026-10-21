"""
Protocole du flux vidéo « vue du joueur » (Unity -> tablette), en UDP.

Chaque image est un JPEG autonome (pas de dépendance entre images). Comme un
datagramme UDP fiable ne dépasse pas ~1 400 octets, l'image est découpée en
fragments, chacun précédé d'un en-tête de 12 octets (gros-boutiste) :

    offset  taille  contenu
    0       2       magic            b"KV"
    2       1       version          1
    3       1       flags            0 (réservé)
    4       4       frame_id         numéro d'image, croît de 1, repart à 0 après 2^32
    8       2       frag_idx         numéro du fragment, de 0 à frag_count - 1
    10      2       frag_count       nombre total de fragments de l'image
    12      ...     charge utile     morceau du JPEG (1 200 octets au plus)

Côté Unity, l'émetteur est GameStreamer.cs ; les deux fichiers doivent rester
d'accord sur cet en-tête.

Politique de perte : une image à laquelle il manque un fragment est abandonnée
(jamais attendue), et dès qu'une image plus récente arrive, les images plus
anciennes encore incomplètes sont abandonnées aussi. La latence reste donc
bornée à une image, au prix d'images sautées si le Wi-Fi perd des paquets.

Ce module n'a aucune dépendance Kivy : il se teste seul (tests/).
"""

from __future__ import annotations

import struct
import time
from typing import Dict, Iterator, List, Optional, Tuple

MAGIC = b"KV"
VERSION = 1
HEADER = struct.Struct(">2sBBIHH")
HEADER_SIZE = HEADER.size            # 12
PAYLOAD_SIZE = 1200                   # octets de JPEG par datagramme
MAX_DATAGRAM = 2048                   # taille de lecture du socket (large marge)
JPEG_SOI = b"\xff\xd8"                # début de tout fichier JPEG
MAX_INFLIGHT = 4                      # images en cours d'assemblage conservées au plus
LATE_WINDOW = 256                     # un fragment « en retard » de plus de 256 images = nouvelle numérotation
GAP_RESET_S = 1.0                     # silence plus long : nouveau flux (Unity redémarré), on repart de zéro


def _newer(a: int, b: int) -> bool:
    """Vrai si l'image `a` est plus récente que `b` (compare modulo 2^32)."""
    return a != b and ((a - b) & 0xFFFFFFFF) < 0x80000000


def fragment_frame(jpeg: bytes, frame_id: int, payload_size: int = PAYLOAD_SIZE) -> Iterator[bytes]:
    """Découpe un JPEG en datagrammes prêts à émettre (utilisé par le faux émetteur et les tests)."""
    count = max(1, -(-len(jpeg) // payload_size))
    if count > 0xFFFF:
        raise ValueError(f"image trop grosse : {len(jpeg)} octets")
    for idx in range(count):
        chunk = jpeg[idx * payload_size:(idx + 1) * payload_size]
        yield HEADER.pack(MAGIC, VERSION, 0, frame_id & 0xFFFFFFFF, idx, count) + chunk


class FrameAssembler:
    """Reconstitue les images à partir des datagrammes reçus, dans n'importe quel ordre."""

    def __init__(self, max_inflight: int = MAX_INFLIGHT):
        self.max_inflight = max_inflight
        self._inflight: Dict[int, Tuple[int, Dict[int, bytes]]] = {}
        self._last_done: Optional[int] = None
        self._last_done_time = 0.0
        self.frames_ok = 0
        self.frames_dropped = 0      # images abandonnées (fragment manquant ou remplacée par plus récente)
        self.packets_bad = 0         # datagrammes ignorés (mauvais en-tête, image trop vieille exclue)
        self.packets_late = 0        # fragments d'une image déjà livrée ou dépassée

    def feed(self, datagram: bytes, now: Optional[float] = None) -> Optional[bytes]:
        """Traite un datagramme. Renvoie le JPEG complet quand une image vient d'être terminée, sinon None.

        `now` (secondes, horloge monotone) ne sert qu'aux tests ; par défaut time.monotonic().
        """
        if now is None:
            now = time.monotonic()
        if len(datagram) <= HEADER_SIZE:
            self.packets_bad += 1
            return None
        magic, version, _flags, frame_id, idx, count = HEADER.unpack_from(datagram)
        if magic != MAGIC or version != VERSION or count == 0 or idx >= count:
            self.packets_bad += 1
            return None

        # Unity redémarré (changement de scène, nouveau lancement) : ses numéros d'image repartent de zéro. On le
        # reconnaît à un silence, ou à un numéro très en arrière ; sans cela, tout serait pris pour du « retard ».
        if self._last_done is not None and now - self._last_done_time > GAP_RESET_S:
            self.reset()
        if self._last_done is not None and not _newer(frame_id, self._last_done):
            if ((self._last_done - frame_id) & 0xFFFFFFFF) <= LATE_WINDOW:
                self.packets_late += 1      # image déjà livrée, ou un peu plus ancienne que la dernière livrée
                return None
            self.reset()

        entry = self._inflight.get(frame_id)
        if entry is None:
            # Nouvelle image : les images plus anciennes encore incomplètes sont désormais inutiles.
            for old in [k for k in self._inflight if _newer(frame_id, k)]:
                del self._inflight[old]
                self.frames_dropped += 1
            entry = (count, {})
            self._inflight[frame_id] = entry
            # Garde-fou (déséquilibre extrême) : on ne garde que les images les plus récentes.
            while len(self._inflight) > self.max_inflight:
                oldest = self._oldest()
                del self._inflight[oldest]
                self.frames_dropped += 1
        elif entry[0] != count:
            self.packets_bad += 1           # incohérent avec les autres fragments de cette image
            return None

        entry[1][idx] = datagram[HEADER_SIZE:]
        if len(entry[1]) < count:
            return None

        # Image complète.
        del self._inflight[frame_id]
        for old in [k for k in self._inflight if _newer(frame_id, k)]:
            del self._inflight[old]
            self.frames_dropped += 1
        self._last_done = frame_id
        self._last_done_time = now
        jpeg = b"".join(entry[1][i] for i in range(count))
        if not jpeg.startswith(JPEG_SOI):
            self.packets_bad += 1
            return None
        self.frames_ok += 1
        return jpeg

    def _oldest(self) -> int:
        ids: List[int] = list(self._inflight)
        oldest = ids[0]
        for k in ids[1:]:
            if _newer(oldest, k):
                oldest = k
        return oldest

    def reset(self) -> None:
        self._inflight.clear()
        self._last_done = None
