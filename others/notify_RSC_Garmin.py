from bleak import BleakClient
from bleak.uuids import normalize_uuid_str
import asyncio
import struct

# Adresse Bluetooth de la montre Garmin
GARMIN_ADDRESS = "A0:9E:1A:AF:CE:DE"

# RUNNING SPEED AND CADENCE SERVICE
CHAR_RSC_FEATURE = normalize_uuid_str('2a54') # read
CHAR_RSC_MEASUREMENT = normalize_uuid_str('2a53') # notify

def parse_rsc_data(data):
    """ Décode les données reçues de la caractéristique Running Speed and Cadence """
    if len(data) < 5:
        print("⚠️ Données RSC invalides ou incomplètes !")
        return

    # Extraction des valeurs depuis la trame binaire
    flags = data[0]  # 1er octet = flags
    speed_raw = struct.unpack_from('<H', data, 1)[0]  # 2e et 3e octets = Vitesse (LSB)
    cadence_raw = struct.unpack_from('<H', data, 3)[0]  # 4e et 5e octets = Cadence (LSB)

    # Conversion des valeurs (unités standard RSC)
    speed_mps = speed_raw / 256.0  # Vitesse en mètres par seconde
    speed_kmh = speed_mps * 3.6  # Conversion en km/h
    cadence_ppm = cadence_raw  # Cadence directement en pas par minute (ppm)

    # Affichage des valeurs
    print(f"🏃‍♂️ Vitesse: {speed_mps:.2f} m/s ({speed_kmh:.2f} km/h), Cadence: {cadence_ppm} ppm")

async def notify_rsc(address):
    """ Se connecte à la montre Garmin et récupère les données RSC en temps réel """
    async with BleakClient(address) as client:
        print(f"✅ Connecté à {address}")

        # Vérification de la présence de la caractéristique
        if CHAR_RSC_MEASUREMENT not in [char.uuid for service in client.services for char in service.characteristics]:
            print(f"❌ ERREUR : Caractéristique {CHAR_RSC_MEASUREMENT} introuvable !")
            return

        # Callback pour recevoir les données RSC
        def rsc_callback(sender, data):
            parse_rsc_data(data)

        # Démarrage des notifications
        await client.start_notify(CHAR_RSC_MEASUREMENT, rsc_callback)

        # Boucle infinie pour écouter les données
        while True:
            await asyncio.sleep(1)

# Lancer le programme
asyncio.run(notify_rsc(GARMIN_ADDRESS))
