from kivy.app import App
import asyncio
import websockets
from functools import partial
from typing import Set, Optional, Callable

from utils.logger import get_logger
from config import WEBSOCKET_HOST, WEBSOCKET_PORT

logger = get_logger(__name__)

class WebSocketServer:
    """Serveur WebSocket pour communiquer la FC reçue vers Unity"""
    
    def __init__(self):
        self.server: Optional[websockets.WebSocketServer] = None
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.is_running = False
        
        # Callbacks vers pilotage_screen
        self.on_message_received: Optional[Callable] = None
        self.on_client_connected: Optional[Callable] = None
        self.on_client_disconnected: Optional[Callable] = None

        # # Callbacks vers tracking_screen
        # self.on_client_connected_tracking: Optional[Callable] = None
        # self.on_client_disconnected_tracking: Optional[Callable] = None
    
    async def start(self, host: str = WEBSOCKET_HOST, port: int = WEBSOCKET_PORT) -> bool:
        """
        Démarre le serveur WebSocket
        
        Args:
            host: Adresse IP du serveur
            port: Port du serveur
            
        Returns:
            bool: True si démarré avec succès
        """
        if self.is_running:
            logger.warning("⚠️ Serveur déjà actif")
            return False
        
        try:
            self.server = await websockets.serve(
                partial(self._websocket_handler, path="/"),
                host,
                port
            )
            
            self.is_running = True
            logger.info(f"✅ Serveur WebSocket démarré sur {host}:{port}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur démarrage serveur : {e}")
            return False
    
    async def stop(self):
        """Arrête le serveur WebSocket"""
        if not self.is_running or not self.server:
            logger.warning("⚠️ Aucun serveur à arrêter")
            return
        
        try:
            # Fermer toutes les connexions clients
            if self.clients:
                await asyncio.gather(
                    *[client.close() for client in self.clients],
                    return_exceptions=True
                )
                self.clients.clear()
            
            # Fermer le serveur
            self.server.close()
            await self.server.wait_closed()
            
            self.server = None
            self.is_running = False
            
            logger.info("🛑 Serveur WebSocket arrêté")
            
                
        except Exception as e:
            logger.error(f"❌ Erreur arrêt serveur : {e}")
    
    async def _websocket_handler(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """
        Gestionnaire de connexion WebSocket
        
        Args:
            websocket: Client WebSocket connecté
            path: Chemin de connexion
        """
        # Ajouter le client
        self.clients.add(websocket)
        client_address = websocket.remote_address
        logger.info(f"🔗 Client connecté : {client_address}")
        
        # Callback vers pilotage_screen
        if self.on_client_connected:
            self.on_client_connected(websocket)

        # # Callback vers tracking_screen
        # if self.on_client_connected_tracking:
        #     self.on_client_connected_tracking(websocket)
        
        try:
            # Écouter les messages du client (pas utilisé ?)
            async for message in websocket:
                logger.debug(f"📩 Message reçu de {client_address} : {message}")
                
                # Callback (si besoin) pour traiter les messages reçus du client
                if self.on_message_received:
                    self.on_message_received(websocket, message)
                    
        except websockets.ConnectionClosed as e:
            logger.info(f"⚠️ Client déconnecté : {client_address} - {e}")
            
        except Exception as e:
            logger.error(f"❌ Erreur WebSocket : {e}")
            
        finally:
            # Retirer le client
            self.clients.discard(websocket)
            logger.info(f"🔌 Client retiré : {client_address}")
            
            # Callback vers pilotage_screen
            if self.on_client_disconnected:
                self.on_client_disconnected(websocket)
            
            # Callback vers tracking_screen
            if self.on_client_disconnected_tracking:
                self.on_client_disconnected_tracking(websocket)
    
    async def send_data_to_clients(self, data: int) -> bool:
        """
        Envoie les données au client Unity connecté
        
        Args:
            data: Data à envoyer
        """
        
        message = str(data)
        await asyncio.gather(*[client.send(message) for client in self.clients])
        logger.info(f"FC envoyé : {message}")
        return True
    
    def get_connected_clients_count(self) -> int:
        """Retourne le nombre de clients connectés"""
        return len(self.clients)
    
    def is_client_connected(self, websocket: websockets.WebSocketServerProtocol) -> bool:
        """Vérifie si un client est connecté"""
        return websocket in self.clients