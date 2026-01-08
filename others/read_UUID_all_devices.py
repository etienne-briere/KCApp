from bleak import BleakClient
import asyncio
from bleak.uuids import normalize_uuid_str
import sys
import struct

# GENERIC ACCESS SERVICE
CHAR_DEVICE_NAME = normalize_uuid_str('2a00') # device name
CHAR_APPAREANCE = normalize_uuid_str('2a01') # apparence de l'appareil
CHAR_CONNECTION_PARAMETERS = normalize_uuid_str('2a04') #
CHAR_CENTRAL_ADRESS_RESOLUTION = normalize_uuid_str('2aa6') #

# HEART RATE SERVICE
CHAR_BODY_SENSOR = normalize_uuid_str('2a38') # UUID de la localisation du capteur (si 1 = poitrine)

# DEVICE INFORMATION SERVICE
CHAR_MANUFACTURER_NAME = normalize_uuid_str('2a29')
CHAR_MODEL_NBR = normalize_uuid_str('2a24')
CHAR_SERIAL_NUMBER = normalize_uuid_str('2a25')
CHAR_HARDWARE_REVISION = normalize_uuid_str('2a27')
CHAR_FIRMWARE_REVISION = normalize_uuid_str('2a26')
CHAR_SOFTWARE_REVISION = normalize_uuid_str('2a28')
CHAR_SYSTEM_ID = normalize_uuid_str('2a23')

# BATTERY SERVICE
CHAR_BATTERY_LEVEL = normalize_uuid_str('2a19') # UUID du service battery level

# UNKNOWN 1 SERVICE (POLAR H10)
CHAR_U1 = "6217ff4c-c8ec-b1fb-1380-3ad986708e2d"

# POLAR SENSOR STREAMING SERVICE
CHAR1_unknown = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"  # read, write, indicate – Request stream settings?
CHAR2_unknown = "fb005c82-02e7-f387-1cad-8acd2d8df0c8" # notify Start the notify stream? (HRV ou ACC ou ECG??)

# RUNNING SPEED AND CADENCE SERVICE
CHAR_RSC_FEATURE = normalize_uuid_str('2a54') # read

# VENDOR SPECIFIC SERVICE
CHAR_VENDOR = normalize_uuid_str('4a02') # read, write, notify

# Device Adress
ADDRESS = "A0:9E:1A:AF:CE:DE"

UUID_test = CHAR_BATTERY_LEVEL

async def read_heart_rate(address, uuid):
    async with BleakClient(address) as client:
        print(f"🔗 Connecté à {address}")

        # Vérification de la présence de la caractéristique
        if uuid not in [char.uuid for service in client.services for char in service.characteristics]:
            print(f"❌ ERREUR : Caractéristique {uuid} introuvable !")
            sys.exit(1)  # Quitter le programme avec une erreur

        #while True:
        data = await client.read_gatt_char(uuid)
        print(f"📥 Données brutes reçues : {data}")

        # Essayer plusieurs indices pour trouver la FC
        data_value = [data[i] for i in range(len(data))]
        print(f"🔹 Valeurs possibles : {data_value}")

        # Décodage en texte
        ## Méthode 1
        try:
            data_string = data.decode("utf-8")
            print(f"Decode en texte : {data_string}")
        except UnicodeDecodeError:
            print("⚠️ Impossible de décoder en UTF-8")

        # Décodage en entier
        if len(data) == 1:
            int_value = data[0]  # Si un seul octet
        elif len(data) == 2:
            int_value = int.from_bytes(data, byteorder="little", signed=False)  # Si deux octets
        else:
            int_value = int.from_bytes(data[:4], byteorder="little",
                                       signed=False)  # Si plusieurs octets, prendre les 4 premiers
        print(f"🟢 Décodage en entier : {int_value}")

        # Décodage en flottant
        if len(data) >= 4:
            try:
                float_value = struct.unpack('<f', data[:4])[0]  # Lire un float en little-endian
                print(f"🔵 Décodage en flottant : {float_value}")
            except struct.error:
                print("⚠️ Impossible de décoder en float (données insuffisantes ou format incorrect)")

        await asyncio.sleep(1)

asyncio.run(read_heart_rate(ADDRESS, UUID_test))
