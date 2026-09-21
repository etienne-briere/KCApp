from app.network.udp_discovery import UDPDiscovery
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
    
    def set_age_player(self, age: int) -> bool:
        """Envoie l'âge du joueur à Unity"""
        return self.send_command("age", str(age))
    
    def set_obstacle(self, command: str)-> bool:
        """Active/Désactive les obstacles"""
        return self.send_command("obs", command)
    
    def set_cube_rate(self, cube_rate: int)-> bool:
        """Paramètre le nombre de cubes par minute"""
        return self.send_command("fixedCpm", str(cube_rate))

    def set_left_hand(self, enabled: bool) -> bool:
        """Active/Désactive l'interaction avec la main gauche"""
        return self.send_command("leftHand", "1" if enabled else "0")

    def set_right_hand(self, enabled: bool) -> bool:
        """Active/Désactive l'interaction avec la main droite"""
        return self.send_command("rightHand", "1" if enabled else "0")

    def set_session_duration(self, duration_seconds: int) -> bool:
        """Paramètre la durée de session (en secondes)"""
        return self.send_command("sessionDuration", str(duration_seconds))

    def set_obstacle_probability(self, probability: int) -> bool:
        """Paramètre la probabilité d'apparition des obstacles (%)"""
        return self.send_command("obstacleProbability", str(probability))

    def set_selected_model(self, model_index: int) -> bool:
        """Change le mode de jeu sélectionné (0=Fixe, 1=Incrémental, 2=PID, 3=DRL)"""
        return self.send_command("SelectedModel", str(model_index))

    def set_incremental_steps(self, steps: int) -> bool:
        """Paramètre le nombre de paliers du mode incrémental"""
        return self.send_command("incrementalSteps", str(steps))

    def set_incremental_min_cpm(self, cpm: int) -> bool:
        """Paramètre le cpm minimum du mode incrémental"""
        return self.send_command("incrementalMinCpm", str(cpm))

    def set_incremental_max_cpm(self, cpm: int) -> bool:
        """Paramètre le cpm maximum du mode incrémental"""
        return self.send_command("incrementalMaxCpm", str(cpm))

    def set_adaptive_min_cpm(self, cpm: int) -> bool:
        """Paramètre le cpm minimum des modes adaptatifs (PID/DRL)"""
        return self.send_command("adaptiveMinCpm", str(cpm))

    def set_adaptive_max_cpm(self, cpm: int) -> bool:
        """Paramètre le cpm maximum des modes adaptatifs (PID/DRL)"""
        return self.send_command("adaptiveMaxCpm", str(cpm))

    def set_stream_game(self, command: str)-> bool:
        """Activation/Désactivation du stream de l'écran du jeux"""
        return self.send_command("stream_game", command)
