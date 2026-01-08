from bleak import BleakClient
from bleak.uuids import normalize_uuid_str
import asyncio
import sys

# HEART RATE SERVICE
CHAR_HR_MEASUREMENT = normalize_uuid_str('2a37') # UUID de la characteristic HR

# BATTERY SERVICE
CHAR_BATTERY_LEVEL = normalize_uuid_str('2a19') # UUID du service battery level

# POLAR SENSOR STREAMING SERVICE
CHAR1_PSS_unknown = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"  # read, write, indicate – Request stream settings?
CHAR2_PSS_unknown = "fb005c82-02e7-f387-1cad-8acd2d8df0c8" # notify Start the notify stream? (HRV ou ACC ou ECG??)

# POLAR ELECTRO Oy SERVICE
CHAR1_ELECTRO_unknown = "fb005c51-02e7-f387-1cad-8acd2d8df0c8" #write-without-response, write, notify
CHAR2_ELECTRO_unknown = "fb005c52-02e7-f387-1cad-8acd2d8df0c8" #notify
CHAR3_ELECTRO_unknown = "fb005c53-02e7-f387-1cad-8acd2d8df0c8" #write-without-response, write

# RUNNING SPEED AND CADENCE SERVICE
CHAR_RSC_FEATURE = normalize_uuid_str('2a54') # read
CHAR_RSC_MEASUREMENT = normalize_uuid_str('2a53') # notify

# VENDOR SPECIFIC SERVICE
CHAR_VENDOR = normalize_uuid_str('4a02') # read, write, notify

# START PSS STREAM REQUEST
HR_ENABLE = bytearray([0x01, 0x00]) # activer les notifs du service HR
HR_DISABLE = bytearray([0x00, 0x00]) # désactiver les notifs

# ECG and ACC Notify Requests
ECG_WRITE = bytearray([0x02, 0x00, 0x00, 0x01, 0x82, 0x00, 0x01, 0x01, 0x0E, 0x00])
ACC_WRITE = bytearray([0x02, 0x02, 0x00, 0x01, 0xC8, 0x00, 0x01, 0x01, 0x10, 0x00, 0x02, 0x01, 0x08, 0x00])

# Device Adress
ADDRESS = "A0:9E:1A:AF:CE:DE"

UUID_TEST = CHAR_HR_MEASUREMENT
CCCD = 37 # handle du descriptors associé à l'UUID_TEST

async def notify_UUID(address, uuid):
    "Affiche les valeurs que renvoie l'UUID en temps réel"
    async with BleakClient(address) as client: # Connection à l'appareil (via son adresse)
        print(f"🔗 Connecté à {address}")

        # Vérification de la présence de la caractéristique
        if uuid not in [char.uuid for service in client.services for char in service.characteristics]:
            print(f"❌ ERREUR : Caractéristique {uuid} introuvable !")
            sys.exit(1)  # Quitter le programme avec une erreur

        def callback(sender, data):
            print (f"📥 Données brutes reçues : {data}")
            data_value = [data[i] for i in range(len(data))]
            print(f"🔹 Valeurs possibles : {data_value}")

        await asyncio.sleep(2)  # Attendre 2 secondes avant d'activer les notifications
        #await client.write_gatt_char("fb005c81-02e7-f387-1cad-8acd2d8df0c8", ACC_WRITE, response=True)
        await client.start_notify(uuid, callback) # active le descriptors correspondant à l'UUID

        # Information sur l'état d'activation
        value = await client.read_gatt_descriptor(CCCD)
        print(f"Valeur actuelle du CCCD : {value}")

        if value[0] == 0:
            print("NOTIFY/INDICATE désactivé")
        elif value[0] == 1:
            print("NOTIFY activé")
        elif value[0] == 2:
            print("INDICATE activé")

        while True:
            await asyncio.sleep(1)

asyncio.run(notify_UUID(ADDRESS,UUID_TEST))

