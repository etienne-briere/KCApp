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

    def launch_game(self) -> bool:
        """Lance la scène de jeu depuis le menu"""
        return self.send_command("launchGame", "true")

    def return_to_menu(self) -> bool:
        """Retourne au menu principal depuis la scène de jeu"""
        return self.send_command("returnToMenu", "true")

    def quit_game(self) -> bool:
        """Quitte le jeu Unity"""
        return self.send_command("quitGame", "true")

    def recenter_view(self) -> bool:
        """Recentre l'orientation du joueur dans le jeu (équivalent à l'appui long sur le bouton Oculus)"""
        return self.send_command("resetView", "true")

    def restore_view(self) -> bool:
        """Restaure la vue d'origine du jeu"""
        return self.send_command("restoreView", "true")

    def set_target_hr(self, target_hr: float) -> bool:
        """Envoie la FC cible à Unity"""
        return self.send_command("target_hr", str(target_hr))
    
    def set_age_player(self, age: int) -> bool:
        """Envoie l'âge du joueur à Unity"""
        return self.send_command("age", str(age))

    def set_weight_player(self, weight) -> bool:
        """Poids du joueur en kg (0 = non renseigné), pour l'estimation des kcal dans Unity"""
        try:
            w = max(0.0, float(weight or 0))
        except (TypeError, ValueError):
            w = 0.0
        value = str(int(w)) if w == int(w) else f"{w:.1f}"
        return self.send_command("userWeight", value)

    def set_sex_player(self, sex: str) -> bool:
        """Sexe du joueur : "M", "F" ou "N" (non renseigné), pour l'estimation des kcal dans Unity"""
        # send_command remplace une valeur vide par le nom de la commande : "N" explicite.
        return self.send_command("userSex", sex if sex in ("M", "F") else "N")

    def set_player_name(self, name: str) -> bool:
        """Envoie le nom du joueur à Unity"""
        return self.send_command("playerName", name)
    
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

    def set_warmup_enabled(self, enabled: bool) -> bool:
        """Active/Désactive la période de warmup (modes PID/DRL)"""
        return self.send_command("warmupEnabled", "1" if enabled else "0")

    def set_warmup_duration(self, duration_seconds: int) -> bool:
        """Paramètre la durée du warmup (en secondes, modes PID/DRL)"""
        return self.send_command("warmupDuration", str(duration_seconds))

    def set_require_hr_signal(self, enabled: bool) -> bool:
        """Active/Désactive l'exigence du signal FC (modes Fixe/Incrémental)"""
        return self.send_command("requireHRSignal", "1" if enabled else "0")

    def set_brick_speed(self, speed: int) -> bool:
        """Paramètre la vitesse des briques (tous modes)"""
        return self.send_command("brickSpeed", str(speed))

    def set_environment(self, environment: str) -> bool:
        """Change l'environnement du jeu (Cosmos, Forest, Sea, Mountain, Sky) — uniquement dans le menu"""
        return self.send_command("environment", environment)

    # ========== CONTRÔLEUR HYBRIDE (Unity, branche feature/controleur-hybride-1hz) ==========

    def set_controller_setup(self, drl_model: str, pid_warmup: bool, pid_backup: bool) -> bool:
        """
        Réglage du contrôleur pour le mode DRL, appliqué au prochain lancement
        ou redémarrage de partie (même traduction que le menu Options du jeu) :
        drl_model = "deployed" (DRL actuel) ou "run3", PID d'échauffement, PID de secours.
        """
        value = f"{drl_model},{1 if pid_warmup else 0},{1 if pid_backup else 0}"
        return self.send_command("controllerSetup", value)

    def set_pid_backup(self, enabled: bool) -> bool:
        """
        Active/désactive le PID de secours en direct, pendant une partie
        déjà en cours (contrairement à controllerSetup, qui ne prend effet
        qu'au prochain lancement/redémarrage).
        """
        return self.send_command("backupPid", "1" if enabled else "0")

    def set_controller_state(self, state: str) -> bool:
        """
        Bascule de contrôleur EN COURS DE PARTIE (appliquée à la seconde suivante) :
        PID, DRL_DEPLOYED, DRL_RUN3, PID_BACKUP ou MANUAL.
        """
        return self.send_command("controllerState", state)

    def set_manual_cpm(self, cpm: int) -> bool:
        """Passe en cadence manuelle (ou change la cadence si déjà en manuel)"""
        return self.send_command("manualCpm", str(int(cpm)))

    def request_config_refresh(self) -> bool:
        """Demande à Unity de renvoyer l'ensemble de ses réglages actuels"""
        return self.send_command("requestConfig", "true")

    def set_stream_game(self, command: str)-> bool:
        """Activation/Désactivation du stream de l'écran du jeux"""
        return self.send_command("stream_game", command)
