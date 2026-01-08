from bleak import BleakClient
from bleak.uuids import normalize_uuid_str
import asyncio
import sys

# Device Adress
ADDRESS = "A0:9E:1A:AF:CE:DE"

# UUID Heart Rate
CHAR_HR_MEASUREMENT = normalize_uuid_str('2a37') # UUID de la characteristic HR

async def notify_heart_rate(address):
    "Affiche les valeurs de FC en continue de l'appareil"
    async with BleakClient(address) as client: # Connection à l'appareil (via son adresse)
        print(f"Connecté à {address}")

        # Vérification de la présence de la caractéristique
        if CHAR_HR_MEASUREMENT not in [char.uuid for service in client.services for char in service.characteristics]:
            print(f"❌ ERREUR : Caractéristique {CHAR_HR_MEASUREMENT} introuvable !")
            sys.exit(1)  # Quitter le programme avec une erreur



        def hr_callback(sender, data):
            heart_rate = int(data[1])  # FC stockée en 2e octet (1er octet = flag)
            print(f"💓 {heart_rate} bpm")

        await client.start_notify(CHAR_HR_MEASUREMENT, hr_callback)

        while True:
            await asyncio.sleep(1)

asyncio.run(notify_heart_rate(ADDRESS))

