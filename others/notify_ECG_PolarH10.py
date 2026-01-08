from bleak import BleakClient
from bleak.uuids import normalize_uuid_str
import asyncio
import sys
from PolarH10 import PolarH10
import math

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

# START PSS STREAM REQUEST
HR_ENABLE = bytearray([0x01, 0x00]) # activer les notifs du service HR
HR_DISABLE = bytearray([0x00, 0x00]) # désactover les notifs

# ECG and ACC Notify Requests
ECG_WRITE = bytearray([0x02, 0x00, 0x00, 0x01, 0x82, 0x00, 0x01, 0x01, 0x0E, 0x00])
ACC_WRITE = bytearray([0x02, 0x02, 0x00, 0x01, 0xC8, 0x00, 0x01, 0x01, 0x10, 0x00, 0x02, 0x01, 0x08, 0x00])

ECG_SAMPLING_FREQ = 130
ecg_stream_values = []
ecg_stream_times = []

# Device Adress
ADDRESS = "A0:9E:1A:AF:CE:DE"

UUID_TEST = CHAR2_PSS_unknown
CCCD = 51

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

        def ecg_data_conv(sender, data):
            # [00 EA 1C AC CC 99 43 52 08 00 68 00 00 58 00 00 46 00 00 3D 00 00 32 00 00 26 00 00 16 00 00 04 00 00 ...]
            # 00 = ECG; EA 1C AC CC 99 43 52 08 = last sample timestamp in nanoseconds; 00 = ECG frameType, sample0 = [68 00 00] microVolts(104) , sample1, sample2, ....
            if data[0] == 0x00:  # Vérifie que c'est bien une trame ECG
                timestamp = PolarH10.convert_to_unsigned_long(data, 1, 8) / 1.0e9  # Convertit en secondes
                step = 3  # ECG sur 3 octets
                time_step = 1.0 / ECG_SAMPLING_FREQ
                samples = data[10:]
                n_samples = len(samples) // step
                sample_timestamp = timestamp - (n_samples - 1) * time_step

                for i in range(n_samples):
                    ecg = PolarH10.convert_array_to_signed_int(samples, i * step, step)  # Convertit en entier signé
                    ecg_stream_values.append(ecg)
                    ecg_stream_times.append(sample_timestamp)
                    sample_timestamp += time_step
                    print(f"⚠️ {ecg} µV")  # Vérifier si une conversion est nécessaire

        await asyncio.sleep(2)  # Attendre 2 secondes avant d'activer les notifications
        await client.write_gatt_char("fb005c81-02e7-f387-1cad-8acd2d8df0c8", ECG_WRITE, response=True)
        await client.start_notify(uuid, ecg_data_conv) # active le descriptors correspondant à l'UUID

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

