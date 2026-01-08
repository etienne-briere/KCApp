import asyncio
import bleak
from config import BLE_SCAN_TIMEOUT, BLE_TARGET_DEVICES
from ble.constants import HEART_RATE_UUID, CHAR_BATTERY_LEVEL
from typing import Optional, Callable, List

from utils.logger import get_logger

logger = get_logger(__name__)

class BLEManager:
    """Gestionnaire BLE pour capteur de FC"""
    
    def __init__(self):
        # État du scan
        self.devices_found: List = []
        self.is_scanning = False
        
        # État de la connexion
        self.client: Optional[bleak.BleakClient] = None
        self.connected_device = None
        self.is_connected = False
        
        # Callbacks vide pour l'UI (définis dans scan_screen.py)
        self.on_scan_complete: Optional[Callable] = None
        self.on_connection_changed: Optional[Callable] = None
        self.on_heart_rate: Optional[Callable] = None
        self.on_battery_level: Optional[Callable] = None
    
    # ========== Scan BLE ========== #

    async def scan_devices(self, timeout: float = BLE_SCAN_TIMEOUT) -> List:
        """
        Scanner les appareils BLE et filtrer les appareils cibles
        
        Returns:
            List: Appareils trouvés
        """
        try:
            self.is_scanning = True
            logger.info(f"🔍 Démarrage du scan BLE (timeout: {timeout}s)")
            
            # Scanner les appareils
            devices_scanned = await bleak.BleakScanner.discover(timeout)
            
            # Filtrer les appareils cibles
            self.devices_found = [
                d for d in devices_scanned 
                if any(brand in (d.name or "") for brand in BLE_TARGET_DEVICES)
            ]
            
            logger.info(f"✅ {len(self.devices_found)} appareils trouvés")
            
            # Callback UI
            if self.on_scan_complete:
                self.on_scan_complete(self.devices_found)
            
            return self.devices_found
            
        except OSError as e:
            logger.error(f"❌ Erreur Bluetooth : {e}")
            if self.on_scan_complete:
                self.on_scan_complete([])
            return []
        
        finally:
            self.is_scanning = False
    
    def get_device_by_address(self, address: str):
        """Trouve un appareil par son adresse"""
        return next((d for d in self.devices_found if d.address == address), None)
    
    # ========== Connexion BLE ========== #

    async def connect_to_device(self, device) -> bool:
        """
        Se connecte à un appareil BLE
        
        Args:
            device: Appareil BLE à connecter
            
        Returns:
            bool: True si connexion réussie
        """
        # Déconnecter l'appareil précédent si nécessaire
        if self.is_connected:
            await self.disconnect()
        
        try:
            logger.info(f"🔗 Connexion à {device.name}...")
            
            # Créer le client et se connecter
            self.client = bleak.BleakClient(device)
            await self.client.connect()
            
            self.connected_device = device
            self.is_connected = True
            
            logger.info(f"✅ Connecté à {device.name}")
            
            # Callback UI
            if self.on_connection_changed:
                self.on_connection_changed(True, device)
            
            # Lire le niveau de batterie initial
            await self._read_initial_battery()
            
            # Démarrer les notifications de fréquence cardiaque
            if self._has_heart_rate_service():
                await self._start_heart_rate_notifications()
                
                # Maintenir la connexion active
                asyncio.create_task(self._keep_alive())
            else:
                logger.warning("⚠️ Service de fréquence cardiaque non disponible")
            
            return True
            
        except bleak.exc.BleakError as e:
            logger.error(f"❌ Erreur de connexion : {e}")
            self.is_connected = False
            
            # Callback UI
            if self.on_connection_changed:
                self.on_connection_changed(False, device)
            
            return False
    
    async def disconnect(self):
        """Déconnecte l'appareil actuel"""
        if self.client and self.is_connected:
            try:
                logger.info(f"🔌 Déconnexion de {self.connected_device.name}...")
                await self.client.disconnect()
                logger.info("✅ Déconnecté")
                
            except Exception as e:
                logger.error(f"Erreur lors de la déconnexion : {e}")
            
            finally:
                self.is_connected = False
                self.client = None
                
                # Callback UI
                if self.on_connection_changed:
                    self.on_connection_changed(False, None)
    
    # ========== Services BLE ========== #

    def _has_heart_rate_service(self) -> bool:
        """Vérifie si le service de fréquence cardiaque est disponible"""
        if not self.client or not self.client.services:
            return False
        
        return HEART_RATE_UUID in [
            char.uuid 
            for service in self.client.services 
            for char in service.characteristics
        ]
    
    def _has_battery_service(self) -> bool:
        """Vérifie si le service de batterie est disponible"""
        if not self.client or not self.client.services:
            return False
        
        return CHAR_BATTERY_LEVEL in [
            char.uuid 
            for service in self.client.services 
            for char in service.characteristics
        ]
    
    async def _read_initial_battery(self):
        """Lit le niveau de batterie initial"""
        if not self._has_battery_service():
            return
        
        try:
            battery_data = await self.client.read_gatt_char(CHAR_BATTERY_LEVEL)
            battery_level = battery_data[0]
            logger.info(f"🔋 Batterie : {battery_level}%")
            
            # Callback UI
            if self.on_battery_level:
                self.on_battery_level(battery_level)
                
        except Exception as e:
            logger.error(f"Erreur lecture batterie : {e}")
    
    async def _start_heart_rate_notifications(self):
        """Démarre les notifications de fréquence cardiaque"""
        try:
            await self.client.start_notify(HEART_RATE_UUID, self._on_hr_data_received)
            logger.info("📡 Notifications de fréquence cardiaque activées")
            
        except Exception as e:
            logger.error(f"Erreur activation notifications : {e}")
    
    async def _on_hr_data_received(self, sender, data):
        """Callback pour les données de fréquence cardiaque"""
        heart_rate = int(data[1])
        logger.debug(f"❤️ {heart_rate} BPM")
        
        # Callback UI
        if self.on_heart_rate:
            self.on_heart_rate(heart_rate)
    
    async def _keep_alive(self):
        """Maintient la connexion active"""
        while self.is_connected:
            await asyncio.sleep(1)