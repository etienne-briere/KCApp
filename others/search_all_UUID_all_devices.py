from bleak import BleakClient
import asyncio

ADDRESS = "A0:9E:1A:AF:CE:DE"  # Remplace par l'adresse de ta montre


async def list_services(address):
    async with BleakClient(address) as client:
        print(f"Connecté à {address}")
        services = await client.get_services()

        for service in services:
            print(f"Service: {service.uuid}")
            for char in service.characteristics:
                print(f" - Caractéristique: {char.uuid}")


asyncio.run(list_services(ADDRESS))
