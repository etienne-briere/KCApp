"""
Faux jeu Unity pour essayer l'écran « Vue du joueur » sans casque.

Il imite ce que fait Unity côté réseau :
  - il écoute le port 5003 (UDPListener) et répond à la découverte (IP_Unity:...),
    puis envoie ping_Unity toutes les 2 s à l'app (port 5006) ;
  - sur stream_config / stream_game:1 (START), il envoie des images JPEG fragmentées
    en UDP vers <IP de l'app>:5007 (GameStreamer), avec le même bail de 6 s ;
  - stream_game:0 (STOP), ou 6 s sans « 1 », arrête le flux.

Usage (poste, dans le dossier du projet) :
    python tools/fake_unity_stream.py                 # flux normal
    python tools/fake_unity_stream.py --loss 0.02     # 2 % de paquets perdus
    python tools/fake_unity_stream.py --self-test     # sans app : joue aussi le rôle de la tablette

Puis lancer l'app (python main.py) et ouvrir l'onglet « Vue joueur ».
Nécessite Pillow : pip install pillow
"""

import argparse
import io
import os
import random
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.network.game_stream_protocol import PAYLOAD_SIZE, fragment_frame  # noqa: E402

PORT_UNITY = 5003        # écoute (comme UDPListener)
PORT_PYTHON = 5006       # réponses vers l'app (comme UDPSender)
PORT_STREAM = 5007       # flux vidéo vers l'app
LEASE_S = 6.0


def lire_pillow():
    try:
        from PIL import Image, ImageDraw
        return Image, ImageDraw
    except ImportError:
        sys.exit("Pillow est nécessaire pour ce faux jeu : pip install pillow")


class FauxUnity:
    def __init__(self, loss: float, ip_locale_unity: str):
        self.loss = loss
        self.ip_unity = ip_locale_unity
        self.fps, self.width, self.quality = 10, 480, 50
        self.dest_ip = None            # app Python (source des datagrammes reçus)
        self.lease_until = 0.0
        self.running = True
        self.frame_id = 0
        self.sent_frames = 0
        self.Image, self.ImageDraw = lire_pillow()
        self.rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.rx.bind(("0.0.0.0", PORT_UNITY))
        self.tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # -- messages entrants (même format « clé:valeur » que le vrai jeu) --------------
    def boucle_reception(self):
        self.rx.settimeout(0.5)
        while self.running:
            try:
                data, (ip, _port) = self.rx.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            msg = data.decode("utf-8", "replace").strip()
            if msg.startswith("IP_Unity:"):
                # Découverte : n'importe quelle adresse testée répond comme si elle était le jeu.
                self.dest_ip = ip
                self.tx.sendto(f"IP_Unity:{self.ip_unity}".encode(), (ip, PORT_PYTHON))
                self.tx.sendto(f"IP_Python:{ip}".encode(), (ip, PORT_PYTHON))
                continue
            cle, _, valeur = msg.partition(":")
            if cle == "stream_config":
                try:
                    f, w, q = (int(float(x)) for x in valeur.split(",")[:3])
                    self.fps = max(1, min(15, f))
                    self.width = max(240, min(960, w))
                    self.quality = max(20, min(90, q))
                    print(f"[fake] stream_config -> {self.fps} img/s, {self.width} px, q{self.quality}")
                except ValueError:
                    print(f"[fake] stream_config illisible : {valeur!r}")
            elif cle == "stream_game":
                self.dest_ip = ip
                if valeur in ("1",) or valeur.upper() == "START":
                    if time.time() > self.lease_until:
                        print(f"[fake] START -> flux vers {ip}:{PORT_STREAM}")
                    self.lease_until = time.time() + LEASE_S
                elif valeur == "0" or valeur.upper() == "STOP":
                    self.lease_until = 0.0
                    print("[fake] STOP")
            else:
                print(f"[fake] message reçu : {msg}")

    def boucle_ping(self):
        while self.running:
            if self.dest_ip:
                self.tx.sendto(b"ping_Unity", (self.dest_ip, PORT_PYTHON))
            time.sleep(2.0)

    # -- images ------------------------------------------------------------------------
    def image(self, n: int) -> bytes:
        w, h = self.width, round(self.width * 9 / 16)
        im = self.Image.new("RGB", (w, h))
        d = self.ImageDraw.Draw(im)
        for y in range(0, h, 4):                      # dégradé vertical animé
            c = int(255 * y / h)
            d.rectangle([0, y, w, y + 4], fill=((c + n * 3) % 256, 80, 255 - c))
        x = int((n * 7) % (w - 40))
        d.ellipse([x, h // 2 - 20, x + 40, h // 2 + 20], fill=(255, 255, 0))
        d.text((8, 8), f"image {n}  {w}x{h}  q{self.quality}", fill=(255, 255, 255))
        d.text((8, h - 16), "HAUT = ciel ; si ce texte est a l'envers : STREAM_FLIP_VERTICAL", fill=(255, 255, 255))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=self.quality)
        return buf.getvalue()

    def boucle_flux(self):
        suivant = time.time()
        while self.running:
            now = time.time()
            if now > self.lease_until or not self.dest_ip:
                time.sleep(0.1)
                suivant = time.time()
                continue
            if now < suivant:
                time.sleep(min(0.005, suivant - now))
                continue
            suivant += 1.0 / self.fps
            self.frame_id += 1
            jpeg = self.image(self.frame_id)
            for i, paquet in enumerate(fragment_frame(jpeg, self.frame_id, PAYLOAD_SIZE)):
                if self.loss and random.random() < self.loss:
                    continue
                self.tx.sendto(paquet, (self.dest_ip, PORT_STREAM))
                if i % 8 == 7:
                    time.sleep(0.001)               # même lissage que GameStreamer.cs
            self.sent_frames += 1

    def lancer(self):
        for cible in (self.boucle_reception, self.boucle_ping, self.boucle_flux):
            threading.Thread(target=cible, daemon=True).start()

    def arreter(self):
        self.running = False


def ip_locale() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def auto_test(secondes: float) -> int:
    """Joue le rôle de la tablette : demande le flux, mesure ce qui arrive, affiche le bilan."""
    from app.network.game_stream_receiver import GameStreamReceiver
    rec = GameStreamReceiver(PORT_STREAM)
    if not rec.start():
        print("auto-test impossible :", rec.error)
        return 1
    tab = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tab.sendto(b"stream_config:10,480,50", ("127.0.0.1", PORT_UNITY))
    t0, derniere, vues = time.time(), 0, 0
    try:
        while time.time() - t0 < secondes:
            tab.sendto(b"stream_game:1", ("127.0.0.1", PORT_UNITY))
            fin = time.time() + 1.0
            while time.time() < fin:
                item = rec.get_latest(derniere)
                if item:
                    derniere, vues = item[0], vues + 1
                time.sleep(0.005)
            st = rec.stats()
            print(f"[auto-test] {st['fps']:.1f} img/s · {st['kbps']:.0f} ko/s · perdues {st['frames_dropped']}")
        tab.sendto(b"stream_game:0", ("127.0.0.1", PORT_UNITY))
    finally:
        rec.stop()
    print(f"[auto-test] {vues} images vues en {secondes:.0f} s")
    return 0 if vues > 0 else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--loss", type=float, default=0.0, help="proportion de paquets perdus (ex. 0.02)")
    ap.add_argument("--self-test", action="store_true", help="joue aussi le rôle de la tablette, quelques secondes")
    ap.add_argument("--duree", type=float, default=6.0, help="durée du self-test en secondes")
    args = ap.parse_args()

    faux = FauxUnity(args.loss, ip_locale())
    faux.lancer()
    print(f"[fake] faux Unity à l'écoute sur UDP {PORT_UNITY} (IP {faux.ip_unity}), perte simulée {args.loss:.0%}")
    try:
        if args.self_test:
            time.sleep(0.3)
            return auto_test(args.duree)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        faux.arreter()


if __name__ == "__main__":
    sys.exit(main())
