# Vue du joueur : flux vidéo Unity → tablette (UDP)

Affiche sur la tablette ce que voit le joueur dans le casque (onglet **Vue joueur**).
Les images passent par UDP : une image perdue est simplement sautée, jamais attendue.

## Comment ça marche

```
Tablette (KCApp)                                   Casque (APEXergame)
  GameScreen ── stream_config:8,480,50 ────────►  UDPListener (port 5003)
             ── stream_game:START (toutes les 2 s) ►   └─ GameStreamer
                                                       caméra miroir → texture réduite
                                                       → lecture GPU asynchrone → JPEG
  GameStreamReceiver ◄── images JPEG fragmentées ──    → fragments de 1 200 octets
  (UDP, port 5007)         en UDP vers la tablette     (thread d'envoi dédié)
```

- **Demande** : sur le canal UDP habituel (clé:valeur, port 5003). `stream_game:START` sert aussi de « bail » :
  Unity coupe le flux de lui-même après 6 s sans START (tablette plantée, Wi-Fi coupé, scène rechargée), et la tablette
  le relance automatiquement. Quitter l'onglet envoie `stream_game:STOP`.
- **Images** : un JPEG par image, découpé en fragments de 1 200 octets précédés d'un en-tête de 12 octets
  (`app/network/game_stream_protocol.py` ↔ `GameStreamer.cs`, à garder d'accord). Une image à laquelle il manque un
  fragment est abandonnée ; dès qu'une image plus récente arrive, les plus anciennes incomplètes le sont aussi.
  La latence reste donc d'au plus une image.
- **Sans la tablette, rien ne tourne côté casque** : ni caméra, ni texture, ni socket.

## Réglages

Dans [config.py](config.py) (envoyés à Unity à chaque démarrage du flux) :

| Réglage | Défaut | Rôle |
|---|---|---|
| `STREAM_FPS` | 8 | valeur par défaut au premier lancement ; ensuite le choix fait à l'écran est mémorisé (`stream_settings.json`). images/s (1 à 15). **Première chose à baisser si le jeu saccade.** |
| `STREAM_WIDTH` | 480 | valeur par défaut (idem, choix mémorisé). largeur en pixels (240 à 960), hauteur en 16:9 |
| `STREAM_QUALITY` | 50 | qualité JPEG (20 à 90) |
| `STREAM_FLIP_VERTICAL` | False | **mettre à True si l'image apparaît à l'envers** (voir ci-dessous) |
| `UDP_PORT_STREAM` | 5007 | port de réception sur la tablette (identique côté Unity : `GameStreamer.DefaultPort`) |

Ordre de grandeur : 480 px à 8 img/s ≈ 100 à 250 ko/s, soit 1 à 2 Mbit/s.

## Essayer sans casque

```bash
python tools/fake_unity_stream.py                 # faux Unity (découverte, ping, flux)
python tools/fake_unity_stream.py --loss 0.02     # avec 2 % de paquets perdus
python tools/fake_unity_stream.py --self-test     # sans l'app : mesure img/s et débit reçus
python main.py                                    # puis onglet « Vue joueur »
python -m unittest discover -s tests -v           # tests de l'assemblage des images
```

Pillow est requis pour le faux Unity (`pip install pillow`) mais **pas** pour l'app : le décodage JPEG de l'écran
passe par Kivy (SDL2), car Pillow n'est pas dans le build Android.

## Premier essai sur le casque : points à vérifier

1. **Orientation** : si l'image est à l'envers, `STREAM_FLIP_VERTICAL = True`. Le sens des lignes renvoyées par la lecture
   GPU dépend de l'API graphique (Vulkan / OpenGL ES) et n'a pas pu être testé sans casque.
2. **Fluidité du jeu** : la caméra miroir refait un rendu de la scène à chaque image envoyée. Surveiller le temps de
   frame (OVR Metrics Tool). Si le jeu accroche, baisser `STREAM_FPS` (5) et/ou `STREAM_WIDTH` (320).
3. **Aucun signal** : vérifier que la tablette et le casque sont sur le même Wi-Fi, que le réseau n'isole pas les
   appareils entre eux (fréquent à l'hôpital) et que l'UDP n'y est pas filtré. Sur un poste Windows, autoriser Python
   dans le pare-feu pour le port UDP 5007.
4. **Caméra** : Unity copie `Camera.main`. Si aucune caméra n'est taguée `MainCamera`, la première caméra active qui rend
   à l'écran est utilisée ; le message `[Stream] ...` du logcat indique ce qui se passe.

## Choix de l'image/seconde et de la résolution

En haut de l'écran « Vue joueur », deux groupes de boutons (comme dans APA Control) :
**2 / 4 / 8 / 12 img/s** et **320 / 480 / 640 px**. Le choix est envoyé tout de suite à Unity
(`stream_config`, appliqué à chaud sans relancer le flux), mémorisé dans `stream_settings.json`
et réutilisé au prochain lancement. Les valeurs proposées se changent dans `config.py`
(`STREAM_FPS_CHOICES`, `STREAM_WIDTH_CHOICES` ; mettre aussi les boutons du `.kv` en cohérence).
