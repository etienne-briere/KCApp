import socket
import ipaddress
import threading
import time
from typing import Optional, Callable
from utils.logger import get_logger
from config import UDP_PORT_SEND, UDP_PORT_RECEIVE, UDP_PING_TIMEOUT

logger = get_logger(__name__)

class UDPDiscovery:
    """Gestion de la découverte d'IP Unity via UDP avec reconnexion automatique"""
    
    def __init__(self):
        self.ip_python: Optional[str] = None
        self.ip_unity: Optional[str] = None
        
        # Threads
        self.send_thread: Optional[threading.Thread] = None
        self.receive_thread: Optional[threading.Thread] = None
        
        # Flags de contrôle
        self.send_ip_running = False
        self.listen_udp = False
        self.auto_reconnect = True
        
        # Dernière réception de ping
        self.last_ping_time = time.time()
        self.was_connected = False
        
        # Callbacks (lien vers app/app.py)
        self.on_unity_connected: Optional[Callable] = None
        self.on_unity_disconnected: Optional[Callable] = None
        self.on_ping_received: Optional[Callable] = None

    # ========== DÉMARRAGE / ARRÊT ==========
    
    def start_discovery(self, auto_reconnect: bool = True):
        """Démarre la découverte d'Unity
        
        Args:
            auto_reconnect: Si True, relance automatiquement la découverte après déconnexion
        """
        if self.send_ip_running or self.listen_udp:
            logger.warning("⚠️ Découverte déjà en cours")
            return
        
        self.auto_reconnect = auto_reconnect
        
        # Récupérer l'IP locale
        self.ip_python = self.get_local_ip()
        logger.info(f"📱 IP locale : {self.ip_python}")
        
        # # Démarrer l'envoi d'IP
        # self.send_ip_running = True
        # self.send_thread = threading.Thread(target=self._send_ip_loop, daemon=True)
        # self.send_thread.start()

        # Démarrer l'envoi d'IP
        self._start_ip_broadcast()
        
        # Démarrer l'écoute UDP
        self.listen_udp = True
        self.receive_thread = threading.Thread(target=self._udp_receiver_loop, daemon=True)
        self.receive_thread.start()
        
        logger.info("🔍 Découverte Unity démarrée")
    
    def stop_discovery(self):
        """Arrête la découverte d'Unity"""
        self.send_ip_running = False
        self.listen_udp = False
        
        # Attendre la fin des threads
        if self.send_thread and self.send_thread.is_alive():
            self.send_thread.join(timeout=2)
        
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2)
        
        logger.info("🛑 Découverte Unity arrêtée")
    
    def _start_ip_broadcast(self):
        """Démarre (ou redémarre) l'envoi d'IP en broadcast"""
        # Arrêter le thread précédent s'il existe
        if self.send_thread and self.send_thread.is_alive():
            self.send_ip_running = False
            self.send_thread.join(timeout=1)
        
        # Démarrer un nouveau thread d'envoi
        self.send_ip_running = True
        self.send_thread = threading.Thread(target=self._send_ip_loop, daemon=True)
        self.send_thread.start()
        
        logger.info("📡 Broadcast IP démarré")
    
    # ========== ENVOI IP ==========
    
    def _send_ip_loop(self):
        """Envoie l'IP locale en broadcast UDP jusqu'à réception de Unity"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # Liste des IP possibles sur le réseau
            possible_ips = self.get_possible_ips(self.ip_python)
            
            logger.info(f"📡 Recherche Unity sur {len(possible_ips)} IPs possibles...")
            
            while self.send_ip_running:
                for ip_possible in possible_ips:
                    if not self.send_ip_running:
                        break
                    
                    # Message : IP Unity testée + IP Python
                    message = f"IP_Unity:{ip_possible}/IP_Python:{self.ip_python}"
                    
                    try:
                        # Envoyer le message
                        sock.sendto(message.encode(), (ip_possible, UDP_PORT_SEND))
                        logger.debug(f"📤 Test IP: {ip_possible}")
                    except Exception as e:
                        logger.debug(f"⚠️ Erreur envoi vers {ip_possible}: {e}")
                
                # Pause entre chaque scan complet du réseau
                time.sleep(0.1)
            
            sock.close()
            logger.info("📡 Envoi IP arrêté")
            
        except Exception as e:
            logger.error(f"❌ Erreur boucle envoi IP : {e}")
    
    # ========== RÉCEPTION UDP ==========
    
    def _udp_receiver_loop(self):
        """Écoute les messages UDP de Unity"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", UDP_PORT_RECEIVE))
            sock.settimeout(1.0)  # Timeout pour vérifier le flag périodiquement
            
            logger.info(f"👂 Écoute UDP sur port {UDP_PORT_RECEIVE}")
            
            while self.listen_udp:
                try:
                    # Vérifier la connexion Unity (timeout ping)
                    self._check_unity_connection()
                    
                    # Recevoir un message
                    data, address = sock.recvfrom(65535) # Taille max UDP (65KB)
                    
                    logger.debug(f"📥 Message UDP reçu de {address}: {data[:50]}")
                    
                    # Traiter le message
                    self._handle_udp_message(data, address)
                    
                except socket.timeout:
                    continue
                    
                except Exception as e:
                    logger.error(f"❌ Erreur réception UDP : {e}")
            
            sock.close()
            logger.info("👂 Écoute UDP arrêtée")
            
        except Exception as e:
            logger.error(f"❌ Erreur boucle réception UDP : {e}")
    
    def _handle_udp_message(self, data: bytes, address: tuple):
        """
        Traite un message UDP reçu
        
        Args:
            data: Données reçues
            address: Adresse de l'expéditeur
        """
        # IP Unity reçue
        if data.startswith(b'IP_Unity:'):
            message = data.decode()
            self.ip_unity = message.split("IP_Unity:")[1].strip()
            
            logger.info(f"✅ Unity connecté : {self.ip_unity}")
            
            # Arrêter l'envoi d'IP
            self.send_ip_running = False
            
            # Initialiser le timestamp du ping
            self.last_ping_time = time.time()
            
            # Callback
            if self.on_unity_connected:
                self.on_unity_connected(self.ip_unity)
        
        # Ping de Unity
        elif data == b'ping_Unity':
            self.last_ping_time = time.time()
            logger.debug("Ping Unity reçu")
            
            # Callback
            if self.on_ping_received:
                self.on_ping_received()
    
    def _check_unity_connection(self):
        """Vérifie si Unity est toujours connecté (timeout ping)"""
        if not self.ip_unity:
            return
        
        elapsed = time.time() - self.last_ping_time
        
        # Si pas de ping depuis 3 secondes
        if elapsed > UDP_PING_TIMEOUT:
            if self.ip_unity:  # Unity était connecté
                logger.warning("⚠️ Unity déconnecté (timeout ping)")
                
                # Renvoyer l'IP pour reconnecter
                self._start_ip_broadcast()
                
                # Callback de déconnexion (une seule fois)
                if self.on_unity_disconnected:
                    self.on_unity_disconnected()
                    self.ip_unity = None  # Reset pour éviter les appels multiples
        
     # ========== ENVOI DE MESSAGES ==========
    
    def send_message(self, message_id: str, value: str) -> bool:
        """
        Envoie un message UDP à Unity
        
        Args:
            message_id: Identifiant du message
            value: Valeur à envoyer
            
        Returns:
            bool: True si envoyé avec succès
        """
        if not self.ip_unity:
            logger.warning("⚠️ Impossible d'envoyer : Unity non connecté")
            return False
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            message = f"{message_id}:{value}"
            # Envoi du message
            sock.sendto(message.encode(), (self.ip_unity, UDP_PORT_SEND))
            
            logger.debug(f"📤 Message envoyé à Unity : {message}")
            sock.close()
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur envoi UDP : {e}")
            return False


    # ========== UTILITAIRES ==========
    
    def get_local_ip(self) -> str:
        """
        Récupère l'IP locale de l'appareil
        
        Returns:
            str: Adresse IP locale
        """
        try:
            # Se connecter fictivement à un serveur externe pour obtenir l'IP locale
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.error(f"❌ Erreur récupération IP : {e}")
            return "127.0.0.1"
    
    def get_possible_ips(self, local_ip: str) -> list[str]:
        """
        Retourne toutes les IP possibles sur le même sous-réseau
        
        Args:
            local_ip: IP locale (ex: "192.168.1.12")
            
        Returns:
            list: Liste des IP possibles sur le réseau
        """
        try:
            # Supposer un masque /24 (255.255.255.0)
            network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
            
            # Toutes les adresses utilisables (exclut network et broadcast)
            possible_ips = [str(ip) for ip in network.hosts()]
            
            logger.debug(f"📡 {len(possible_ips)} IPs possibles sur le réseau")
            return possible_ips
            
        except Exception as e:
            logger.error(f"❌ Erreur calcul IPs : {e}")
            return []
    
    def is_unity_connected(self) -> bool:
        """Vérifie si Unity est connecté"""
        return self.ip_unity is not None
    
    def force_reconnect(self):
        """
        Force la relance de la découverte (utile pour un bouton "Reconnect")
        """
        logger.info("🔄 Reconnexion forcée...")
        
        # Réinitialiser l'état
        self.ip_unity = None
        self.was_connected = False
        
        # Relancer le broadcast
        if self.listen_udp:
            self._start_ip_broadcast()
        else:
            self.start_discovery(auto_reconnect=self.auto_reconnect)
    