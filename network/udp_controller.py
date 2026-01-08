from network.udp_discovery import UDPDiscovery
from utils.logger import get_logger

logger = get_logger(__name__)

class UDPController:
    """Contrôleur pour envoyer des commandes au jeu Unity"""
    
    def __init__(self, udp_discovery: UDPDiscovery):
        self.discovery = udp_discovery
    
    def send_command(self, command: str, value: str = "") -> bool:
        """
        Envoie une commande au jeu Unity
        
        Args:
            command: Nom de la commande
            value: Valeur associée (optionnel)
            
        Returns:
            bool: True si envoyé
        """
        if not self.discovery.is_unity_connected():
            logger.warning(f"⚠️ Impossible d'envoyer '{command}' : Unity non connecté")
            return False
        
        # Préparer le message
        message_value = value if value else command
        return self.discovery.send_message(command, message_value)
    
    # ========== COMMANDES SPÉCIFIQUES ==========
    
    def set_difficulty(self, difficulty: str) -> bool:
        """Définit la difficulté du jeu"""
        return self.send_command("difficulty", difficulty)
    
    def set_speed(self, speed: float) -> bool:
        """Définit la vitesse du jeu"""
        return self.send_command("speed", str(speed))
    
    def pause_game(self) -> bool:
        """Met le jeu en pause"""
        return self.send_command("pause", "true")
    
    def resume_game(self) -> bool:
        """Reprend le jeu"""
        return self.send_command("pause", "false")
    
    def restart_game(self) -> bool:
        """Redémarre le jeu"""
        return self.send_command("restart", "true")
    
    def set_target_hr(self, target_hr: float) -> bool:
        """Envoie la FC cible à Unity"""
        return self.send_command("target_hr", str(target_hr))