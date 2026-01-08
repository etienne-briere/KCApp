from bleak import BleakScanner
import asyncio

async def scan_ble():
    devices = await BleakScanner.discover()
    for device in devices:
        print(f"Nom: {device.name}, Adresse: {device.address}")

asyncio.run(scan_ble())


