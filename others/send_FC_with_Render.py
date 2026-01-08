from bleak import BleakClient, BleakScanner
from bleak.uuids import normalize_uuid_str
import time
import asyncio
import websockets
import aiohttp  # Pour envoyer une requête HTTP

# UUID GENERIC ACCESS SERVICE
CHAR_DEVICE_NAME = normalize_uuid_str('2a00')  # UUID de la characteristic du device name

# UUID HEART RATE SERVICE
CHAR_HR_MEASUREMENT = normalize_uuid_str('2a37')  # UUID de la characteristic HR

# UUID BATTERY SERVICE
CHAR_BATTERY_LEVEL = normalize_uuid_str('2a19')  # UUID du service battery level

async def scan_devices():
    print("🔍 Recherche d'appareils Bluetooth...")
    devices = await BleakScanner.discover()
    device_names = [device.name for device in devices if device.name]  # Récupère tous les noms scannés

    ## Nombre d'appareils trouvés
    nb_device_names = len(device_names)

    ## Afficher le nom des appareils disponibles
    if device_names:
        print("📶 Appareils détectés :")
        for i_name in range(nb_device_names):
            name = device_names[i_name]
            print(f"▫️ {name} (\033[91m{i_name + 1}\033[0m)")

    return devices, device_names

async def handle_device():
    device_names = None
    devices = None
    choice_device_ble = "r"  # Initialisation pour entrer dans la boucle

    while True:
        if choice_device_ble == "r":
            devices, device_names = await scan_devices()  # Lancer le scan
            if not device_names:
                print("❌ Aucun appareil détecté.")
                print(input("🔄 Press [ENTER] pour relancer le scan"))
                continue  # Aucun appareil trouvé, on relance le scan

        choice_device_ble = input("\n🔢 Numéro de l'appareil à connecter ('r' pour rescanner) : ")

        if choice_device_ble == "r":
            continue  # Relancer le scan

        try:
            choice_device_ble = int(choice_device_ble) - 1  # Convertir en index
            if 0 <= choice_device_ble <= len(device_names) - 1:
                # print(f"✅ Appareil sélectionné : {device_names[choice_device_ble]}")
                break  # Sortie de la boucle une fois un choix valide fait
            else:
                print("⚠️ Choix invalide. Veuillez entrer un numéro correct.")
        except ValueError:
            print("⚠️ Entrée invalide. Veuillez entrer un numéro valide.")

    return devices, device_names, choice_device_ble


async def countdown(seconds):
    for i in range(seconds, 0, -1):
        print(f"⏳ En cours... ({i}s)", end="\r")
        await asyncio.sleep(1)
    print(" " * 50, end="\r")  # Efface la ligne après le décompte

async def wake_up_server():
    """Envoie une requête HTTP pour réveiller le service Render."""
    # Choix du port sur lequel envoyer les données
    port = input("\n🌐 Numéro du port Websocket (8766 ou 8767) : ")

    # 🎯 Adresse https pour lancer le serveur Render
    wake_up_url = f"https://websocket-{port}.onrender.com"  # URL HTTP du serveur
    print("⏰ Réveil du serveur Render...")
    async with aiohttp.ClientSession() as session:
        try:
            countdown_task = asyncio.create_task(countdown(60))  # Lance le décompte en parallèle
            async with session.get(wake_up_url) as response:
                countdown_task.cancel()  # Arrête le décompte si la connexion réussit
                print(f"✅ Serveur réveillé ({response.status})")
        except Exception as e:
            print(f"⚠️ Impossible de réveiller le serveur : {e}")

    return port

async def send_heart_rate():
    """Trouve la montre Garmin et envoie la FC en continue au serveur WebSocket"""
    while True :
        devices, device_names, choice_device_ble = await handle_device()

        ## Nom de l'appareil choisi
        device_name_target = device_names[choice_device_ble]

        for device in devices:
            if device.name and device_name_target in device.name:
                print(f"⏳ Connexion en cours à {device.name} ({device.address})")

                async with BleakClient(device.address) as client:
                    print(f"✅ Connexion à {device.name} réussie !")

                    # Vérification de la présence de la caractéristique HR
                    if CHAR_HR_MEASUREMENT not in [char.uuid for service in client.services for char in
                                                   service.characteristics]:
                        print(f"❌ ERREUR : {device.name} ne diffuse pas de données de FC !\n")
                        print(input("🔄 Press [ENTER] pour relancer le scan"))
                        devices, device_names, choice_device_ble = await handle_device()
                        continue # relance boucle while
                    else:
                        print(f"🔊 {device.name} diffuse des données de FC !")

                    # Vérification de la présence de la caractéristique BATTERY_LEVEL
                    if CHAR_BATTERY_LEVEL in [char.uuid for service in client.services for char in
                                              service.characteristics]:
                        battery_level = await client.read_gatt_char(CHAR_BATTERY_LEVEL)
                        battery_percentage = battery_level[0]  # Le niveau de la batterie est un octet
                        print(f"🔋 {battery_percentage}%")

                    # Réveiller le serveur
                    port = await wake_up_server()

                    # 🎯 Adresse du serveur WebSocket
                    server_url = f"wss://websocket-{port}.onrender.com/ws"

                    # Attendre quelques secondes pour laisser Render démarrer
                    for i in range(5, 0, -1):
                        print(f"⏳ Démarrage du serveur WebSocket... ({i}s)", end="\r")
                        await asyncio.sleep(1)

                    print("\n🚀 Connexion WebSocket...")
                    async with websockets.connect(server_url) as websocket:
                        print("✅ Connexion WebSocket réussie !")

                        start_time = time.time()  # Définir le temps de départ à 0

                        async def callback(sender, data):
                            heart_rate = int(data[1])
                            timestamp = time.time() - start_time  # Temps écoulé depuis le début
                            print(f"❤️ {heart_rate} BPM (t = {timestamp:.2f}s)")

                            # Envoie la FC au serveur WebSocket
                            await websocket.send(str(heart_rate))
                            print(f"📤 Envoyé : {heart_rate} BPM")

                        await client.start_notify(CHAR_HR_MEASUREMENT, callback)

                        # Boucle infinie pour garder la connexion active
                        while True:
                            await asyncio.sleep(1)

    # if not device_names:
    #     print("❌ Aucun appareil détecté.")
    #     return


# Exécute le script
asyncio.run(send_heart_rate())
