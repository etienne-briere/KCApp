import os

# Configuration de l'application
APP_TITLE = 'BLE VR Data Bridge'
DEBUG_MODE = os.getenv('DEBUG', 'True').lower() == 'true'

# Configuration du thème
THEME_STYLE = "Dark"  # "Light" ou "Dark"
PRIMARY_PALETTE = "Blue"
ACCENT_PALETTE = "Amber"

# Configuration BLE
BLE_SCAN_TIMEOUT = 3
BLE_TARGET_DEVICES = ["Forerunner", "Polar", "vívoactiv" , "Instinct"]  # Filtre pour les marques ciblées

# Paramètres WebSocket
WEBSOCKET_HOST = "0.0.0.0"
WEBSOCKET_PORT = 8765

# Paramètres UDP
UDP_PORT_SEND = 5003
UDP_PORT_RECEIVE = 5006
UDP_PING_TIMEOUT = 3.0  # Secondes avant de considérer Unity déconnecté

