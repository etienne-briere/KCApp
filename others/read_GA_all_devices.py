import asyncio
from bleak import BleakClient

# Adresse MAC de ta montre Garmin
DEVICE_ADDRESS = "A0:9E:1A:AF:CE:DE"

# UUIDs des caractéristiques du service Generic Access
CHAR_DEVICE_NAME = "00002a00-0000-1000-8000-00805f9b34fb"  # Nom de l'appareil
CHAR_APPEARANCE = "00002a01-0000-1000-8000-00805f9b34fb"  # Type d'appareil
CHAR_PPCP = "00002a04-0000-1000-8000-00805f9b34fb" # Peripheral Preferred Connection Parameters

# Dictionnaire des apparences Bluetooth
APPEARANCE_CODES = {
    0x00C1: "Generic Watch",
    0x00C2: "Sports Watch",
    # Ajoute d'autres codes si nécessaire
}

async def read_generic_access(address):
    async with BleakClient(address) as client:
        print(f"🔗 Connecté à {address}")

        # Lecture du nom de l'appareil
        name_bytes = await client.read_gatt_char(CHAR_DEVICE_NAME)
        device_name = name_bytes.decode("utf-8")
        print(f"📥 Données brutes reçues : {name_bytes}")
        print(f"📛 Nom de l'appareil : {device_name}")

        # Lecture du type d'appareil
        appearance_bytes = await client.read_gatt_char(CHAR_APPEARANCE)
        appearance_value = int.from_bytes(appearance_bytes, byteorder="little")
        device_appearance = get_device_appearance(appearance_value)
        print(f"📥 Données brutes reçues : {appearance_bytes}")
        print(f"📌 Type d'appareil (Appearance) : {device_appearance}")

        # Lecture des données brutes
        data = await client.read_gatt_char(CHAR_PPCP)
        print(f"📥 Données brutes reçues : {data}")

        # Décode les valeurs (format Little Endian, 2 octets par paramètre)
        min_interval = int.from_bytes(data[0:2], byteorder="little") * 1.25  # en ms
        max_interval = int.from_bytes(data[2:4], byteorder="little") * 1.25  # en ms
        latency = int.from_bytes(data[4:6], byteorder="little")  # Nombre d'intervalles ignorés
        timeout = int.from_bytes(data[6:8], byteorder="little") * 10  # en ms

        # Affichage des résultats
        print(f"🔹 Intervalle Min de connexion : {min_interval} ms")
        print(f"🔹 Intervalle Max de connexion : {max_interval} ms")
        print(f"🔹 Latence périphérique : {latency} intervalles")
        print(f"🔹 Timeout supervision : {timeout} ms")


def get_device_appearance(appearance_value):
    return APPEARANCE_CODES.get(appearance_value, f"Unknown ({hex(appearance_value)})")

asyncio.run(read_generic_access(DEVICE_ADDRESS))


