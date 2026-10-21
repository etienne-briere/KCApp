import os

# Configuration de l'application
APP_TITLE = 'BLE VR Data Bridge'
DEBUG_MODE = os.getenv('DEBUG', 'True').lower() == 'true'

# Configuration du thème
THEME_STYLE = "Light"  # "Light" ou "Dark" - Light retenu pour un usage clinique
PRIMARY_PALETTE = "Teal"
ACCENT_PALETTE = "Amber"

# Configuration BLE
BLE_SCAN_TIMEOUT = 3
BLE_TARGET_DEVICES = ["Forerunner", "Polar", "Vantage","vívoactiv" , "Instinct"]  # Filtre pour les marques ciblées

# Paramètres WebSocket
WEBSOCKET_HOST = "0.0.0.0"
WEBSOCKET_PORT = 8765

# Paramètres UDP
UDP_PORT_SEND = 5003
UDP_PORT_RECEIVE = 5006
UDP_PING_TIMEOUT = 3  # Secondes avant de considérer Unity déconnecté

# Flux vidéo « vue du joueur » (Unity -> tablette, UDP, images JPEG fragmentées)
# Voir app/network/game_stream_protocol.py et, côté Unity, GameStreamer.cs
UDP_PORT_STREAM = 5007       # port local où la tablette reçoit les images (doit être le même côté Unity)
STREAM_FPS = 8               # images par seconde demandées à Unity (1 à 15) ; baisser si le jeu saccade
STREAM_WIDTH = 480           # largeur de l'image en pixels (240 à 960), hauteur en 16:9
STREAM_FPS_CHOICES = (2, 4, 8, 12)      # choix proposés dans l'écran Vue du joueur (img/s)
STREAM_WIDTH_CHOICES = (320, 480, 640)  # choix proposés dans l'écran Vue du joueur (px)
STREAM_QUALITY = 50          # qualité JPEG (20 à 90)
STREAM_FLIP_VERTICAL = False # passer à True si l'image apparaît à l'envers au premier essai sur le casque
STREAM_LEASE_RENEW_S = 2.0   # la tablette renvoie stream_game:START à cette période (Unity coupe après 6 s sans START)
STREAM_NO_SIGNAL_S = 2.0     # sans image depuis ce délai : « aucun signal »
