"""Tests du flux vidéo « vue du joueur » (sans Kivy, sans casque) :

    python -m unittest discover -s tests -v        (ou : python -m pytest tests)
"""

import io
import os
import random
import socket
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.network.game_stream_protocol import (HEADER_SIZE, PAYLOAD_SIZE, FrameAssembler,  # noqa: E402
                                              fragment_frame)
from app.network.game_stream_receiver import GameStreamReceiver  # noqa: E402


def faux_jpeg(taille: int, graine: int = 0) -> bytes:
    """Un « JPEG » de la taille voulue : seul l'en-tête FFD8 compte pour l'assembleur."""
    rnd = random.Random(graine)
    return b"\xff\xd8" + bytes(rnd.getrandbits(8) for _ in range(taille - 2))


def liste(jpeg: bytes, fid: int):
    return list(fragment_frame(jpeg, fid))


class AssembleurTest(unittest.TestCase):
    def test_ordre_normal(self):
        jpeg = faux_jpeg(30_000)
        a = FrameAssembler()
        paquets = liste(jpeg, 1)
        self.assertGreater(len(paquets), 20)
        for p in paquets[:-1]:
            self.assertIsNone(a.feed(p))
        self.assertEqual(a.feed(paquets[-1]), jpeg)
        self.assertEqual(a.frames_ok, 1)

    def test_paquets_melanges(self):
        jpeg = faux_jpeg(25_000, 2)
        paquets = liste(jpeg, 7)
        random.Random(3).shuffle(paquets)
        a = FrameAssembler()
        resultats = [a.feed(p) for p in paquets]
        self.assertEqual([r for r in resultats if r], [jpeg])

    def test_image_trop_petite_pour_fragmenter(self):
        jpeg = faux_jpeg(500)
        paquets = liste(jpeg, 0)
        self.assertEqual(len(paquets), 1)
        self.assertEqual(FrameAssembler().feed(paquets[0]), jpeg)

    def test_fragment_manquant_image_abandonnee_puis_suivante_ok(self):
        a = FrameAssembler()
        p1 = liste(faux_jpeg(10_000, 1), 1)
        del p1[3]                                  # un fragment perdu
        for p in p1:
            self.assertIsNone(a.feed(p))
        suivante = faux_jpeg(10_000, 2)
        sortie = [a.feed(p) for p in liste(suivante, 2)]
        self.assertEqual([s for s in sortie if s], [suivante])
        self.assertEqual(a.frames_dropped, 1)      # l'image 1 est comptée comme perdue
        self.assertEqual(a.frames_ok, 1)

    def test_image_ancienne_en_retard_ignoree(self):
        a = FrameAssembler()
        for p in liste(faux_jpeg(5_000, 1), 5):
            a.feed(p)
        tard = liste(faux_jpeg(5_000, 2), 4)       # image 4 arrivant après la 5
        self.assertTrue(all(a.feed(p) is None for p in tard))
        self.assertGreater(a.packets_late, 0)

    def test_doublons_ne_cassent_rien(self):
        jpeg = faux_jpeg(8_000, 4)
        a = FrameAssembler()
        sortie = []
        for p in liste(jpeg, 9):
            sortie.append(a.feed(p))
            sortie.append(a.feed(p))               # chaque fragment reçu deux fois
        self.assertEqual([s for s in sortie if s], [jpeg])

    def test_paquets_invalides(self):
        a = FrameAssembler()
        for bruit in (b"", b"x" * 5, b"XX" + b"\x00" * 30, b"KV\x09\x00" + b"\x00" * 30):
            self.assertIsNone(a.feed(bruit))
        self.assertEqual(a.packets_bad, 4)
        # Ne commençant pas par FFD8 : refusé une fois l'image complète
        self.assertIsNone(FrameAssembler().feed(next(iter(fragment_frame(b"pas un jpeg" * 10, 1)))))

    def test_bouclage_du_numero_d_image(self):
        a = FrameAssembler()
        for fid in (0xFFFFFFFE, 0xFFFFFFFF, 0, 1):
            jpeg = faux_jpeg(3_000, fid & 0xFF)
            sortie = [a.feed(p) for p in liste(jpeg, fid)]
            self.assertEqual([s for s in sortie if s], [jpeg], f"image {fid}")

    def _livrer(self, a, jpeg, fid, now):
        return [r for r in (a.feed(p, now) for p in liste(jpeg, fid)) if r]

    def test_unity_redemarre_apres_un_silence(self):
        """Scène rechargée : les numéros repartent de 1 après quelques secondes de silence."""
        a = FrameAssembler()
        for fid in range(1, 51):
            self.assertTrue(self._livrer(a, faux_jpeg(3_000, fid), fid, now=fid * 0.1))
        neuf = faux_jpeg(3_000, 99)
        self.assertEqual(self._livrer(a, neuf, 1, now=5.0 + 3.0), [neuf])

    def test_unity_redemarre_sans_silence_mais_numero_tres_en_arriere(self):
        a = FrameAssembler()
        for fid in range(1, 501):
            self._livrer(a, faux_jpeg(1_500, fid), fid, now=fid * 0.01)
        neuf = faux_jpeg(1_500, 7)
        self.assertEqual(self._livrer(a, neuf, 2, now=5.02), [neuf])

    def test_retard_recent_reste_ignore(self):
        a = FrameAssembler()
        for fid in range(10, 21):
            self._livrer(a, faux_jpeg(1_500, fid), fid, now=fid * 0.01)
        self.assertEqual(self._livrer(a, faux_jpeg(1_500, 3), 15, now=0.25), [])

    def test_taille_des_datagrammes(self):
        for p in liste(faux_jpeg(60_000), 1):
            self.assertLessEqual(len(p), HEADER_SIZE + PAYLOAD_SIZE)
            self.assertLess(len(p), 1400)          # sous la MTU Wi-Fi courante, jamais fragmenté par IP

    def test_perte_aleatoire(self):
        """2 % de pertes de paquets : on perd des images entières, jamais une image corrompue."""
        rnd = random.Random(11)
        a = FrameAssembler()
        envoyees, recues = [], []
        for fid in range(200):
            jpeg = faux_jpeg(20_000, fid)
            envoyees.append(jpeg)
            for p in liste(jpeg, fid):
                if rnd.random() < 0.02:
                    continue
                r = a.feed(p)
                if r:
                    recues.append(r)
        self.assertTrue(all(r in envoyees for r in recues))
        self.assertGreater(len(recues), 80)        # ~17 paquets/image : ~70 % des images passent
        self.assertEqual(a.frames_ok, len(recues))


class RecepteurSocketTest(unittest.TestCase):
    def test_reception_reelle_sur_loopback(self):
        # Port libre choisi par le système
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()

        rec = GameStreamReceiver(port=port)
        self.assertTrue(rec.start())
        try:
            emetteur = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            jpeg = faux_jpeg(40_000, 5)
            for p in liste(jpeg, 1):
                emetteur.sendto(p, ("127.0.0.1", port))
            t0 = time.time()
            item = None
            while item is None and time.time() - t0 < 2:
                item = rec.get_latest(0)
                time.sleep(0.01)
            self.assertIsNotNone(item)
            self.assertEqual(item[1], jpeg)
            self.assertIsNone(rec.get_latest(item[0]))          # rien de plus récent
            self.assertGreater(rec.stats()["fps"], 0)
        finally:
            emetteur.close()
            rec.stop()
        self.assertFalse(rec.running)

    def test_port_deja_pris(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("0.0.0.0", 0))
        rec = GameStreamReceiver(port=s.getsockname()[1])
        try:
            self.assertFalse(rec.start())
            self.assertIn("indisponible", rec.error)
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
