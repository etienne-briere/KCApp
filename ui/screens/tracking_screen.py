# Class KivyMD
from kivymd.uix.screen import MDScreen
from kivymd.toast import toast

# Class Kivy
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty
from kivy.app import App
from kivy.clock import Clock

# Custom modules
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from config import WEBSOCKET_HOST, WEBSOCKET_PORT
import asyncio

from utils.logger import get_logger
logger = get_logger(__name__)

class TrackingScreen(MDScreen):
    '''
    ECRAN DE SUIVI DE LA FC
    '''

    # Properties pour l'UI
    heart_rate_label = StringProperty("--")
    target_hr_value = NumericProperty(50)
    server_ws_running = BooleanProperty(False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Données
        self.data_hr = []  # Liste des (temps, %FCmax)
        self.data_hr_target = []  # Liste des %FC cible
        self.time = 0
        self.last_bpm = None
        self.max_hr = 180  # Valeur par défaut, sera calculée
        
        # Configuration Matplotlib
        self.fig = None
        self.ax = None
        self.line_hr = None
        self.line_hr_target = None
        self.placeholder_text = None
        
        # Animation du cœur
        self.beat_event = None

        # WebSocket Server
        self.ws_server = None
    
    def on_kv_post(self, base_widget):
        """
        Appelé automatiquement quand le kv est chargé
        et que les ids sont disponibles.
        """
        # Initialiser le graphique Matplotlib
        self.setup_graph()
    
    def on_pre_enter(self):
        """Appelé à l'ouverture de l'écran"""
        # Récupérer les managers
        app = App.get_running_app()
        self.ble_manager = app.ble_manager
        self.ws_server = app.ws_server
        self.udp_discovery = app.udp_discovery
        
        # Callbacks BLE
        self.ble_manager.on_heart_rate = self.on_heart_rate_received

        # Callbacks WebSocket
        self.ws_server.on_message_received = self.on_ws_message_received
        self.ws_server.on_client_connected = self.on_ws_client_connected
        self.ws_server.on_client_disconnected = self.on_ws_client_disconnected
                
        # Démarrer la mise à jour du graphique (1 Hz)
        self.update_event = Clock.schedule_interval(self.update_graph, 1)
        
        logger.info("Écran de tracking activé")
    
    def on_leave(self):
        """Appelé à la sortie de l'écran"""
        # Arrêter le serveur ws si actif
        if self.ws_server and self.ws_server.is_running:
            asyncio.ensure_future(self.ws_server.stop())
        
        # Arrêter les mises à jour
        if self.update_event:
            self.update_event.cancel()
        
        logger.info("Écran de tracking désactivé")
    
    # ========== GRAPHIQUE MATPLOTLIB ==========

    def setup_graph(self):
        """Initialise le graphique Matplotlib"""
        
        # Créer la figure et les axes
        self.fig, self.ax1 = plt.subplots()

        # Ajout du 2ème axe Y (%FC cible)
        self.ax2 = self.ax1.twinx()

        # Style du graphique
        self.fig.patch.set_alpha(0.0) # Fond transparent
        self.ax1.set_facecolor("none") # Fond transparent
        self.ax1.margins(x=0, y=0) # Pas de marges autour des données
        self.fig.tight_layout() # Ajuster le layout
        self.ax1.grid(True, alpha=0.3) # Grille légère

        # Texte indicatif quand pas de données
        self.placeholder_text = self.ax1.text(
            0.5,
            0.5,
            "Connect your sensor to start tracking",
            ha="center",
            va="center",
            transform=self.ax1.transAxes,
            color="grey",
            fontsize=14,
        )
        
        # Labels des axes
        self.ax1.set_ylabel("HRmax (%)", color="grey")
        self.ax1.set_xlabel("Time (s)", color="grey")
        self.ax2.set_ylabel("HR target (%)", color="grey")

        # Couleurs des axes
        self.ax1.tick_params(axis='x', colors='grey')  # temps
        self.ax1.tick_params(axis='y', colors='grey')  # %FCmax
        self.ax2.tick_params(axis='y', colors='grey')  # %FC cible

        # Couleur du contour des axes
        for spine in self.ax1.spines.values():
            spine.set_color('grey')

        # Limites des axes
        self.ax1.set_xlim(0, 600)  # 10 minutes
        self.ax1.set_ylim(0, 100)  # 0-100% FCmax
        self.ax2.set_ylim(0, 100)  # 0-100% FC cible
        
        # Créer la ligne HR (vide au départ)
        self.line_hr, = self.ax1.plot([], [], 'r-', linewidth=2, label='HR (%)')
        self.ax1.legend(loc='upper left', facecolor='#1e1e1e', edgecolor='white', labelcolor='white')
        
        # Créer la ligne HR target (vide au départ)
        self.line_hr_target, = self.ax1.plot([], [], 'b-', linewidth=2, label='HR Target (%)')

        # Ajouter la figure au widget
        self.ids.hr_graph_widget.figure = self.fig
        
        logger.debug("Graphique Matplotlib initialisé")
    
    def update_graph(self, dt):
        """Met à jour le graphique toutes les secondes"""
        
        # Vérifier qu'un appareil est connecté
        if not self.ble_manager or not self.ble_manager.is_connected:
            # Afficher le texte indicatif
            self.placeholder_text.set_visible(True)

            # Forcer le redessinage
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()
            return
        
        # Si on n'a pas reçu de données récentes, on ne fait rien
        if self.last_bpm is None or self.last_bpm == "--":
            return
        
        # MAJ du graphique
        self.ax1.set_ylabel("HRmax (%)", color="red", 
                            fontsize=12, fontweight="bold"
                            )
        self.placeholder_text.set_visible(False)
      
        # Calculer le % de FCmax
        hr_percent = self.calculate_hr_percent(self.last_bpm)
        
        # Ajouter les données de FC
        self.data_hr.append((self.time, hr_percent))
        self.time += 1

        # Garder seulement les 600 dernières secondes (10 minutes)
        if len(self.data_hr) > 600:
            self.data_hr = self.data_hr[-600:]
            # Ajuster l'échelle X
            self.ax.set_xlim(self.data_hr[0][0], self.data_hr[-1][0])
        
        # Mettre à jour la ligne HR du graphique
        if self.data_hr:
            times, hr_values = zip(*self.data_hr)
            self.line_hr.set_data(times, hr_values)
        
        if self.ids.target_hr_slider.disabled == False:
            # Récupérer la valeur cible
            target_percent = self.ids.target_hr_slider.value
            self.data_hr_target.append((self.time, target_percent))

            # Mettre à jour la ligne HR target du graphique
            if self.data_hr_target:
                times, hr_target_values = zip(*self.data_hr_target)
                self.line_hr_target.set_data(times, hr_target_values)
        else:
            # Effacer les données de la ligne HR target
            self.data_hr_target = []
            self.line_hr_target.set_data([], [])
        
        # Forcer le redessinage
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

        # # Envoyer les données via WebSocket
        # if self.server_ws_running:
        #     asyncio.ensure_future(self.ws_server.send_data_to_clients(self.last_bpm))
        
        # Rafraîchir le widget
        self.ids.hr_graph_widget.figure = self.fig
            
    def calculate_hr_percent(self, bpm):
        """
        Calcule le pourcentage de FCmax
        """
        app = App.get_running_app()
        self.max_hr = app.user_profile.calculate_max_hr()
        
        hr_percent = (bpm / self.max_hr) * 100

        return hr_percent

    # ========== RÉCEPTION DES DONNÉES ==========
    
    def on_heart_rate_received(self, bpm):
        """
        Callback appelé quand une nouvelle FC est reçue
        
        Args:
            bpm: Fréquence cardiaque en BPM
        """        
        # Mettre à jour l'affichage
        self.update_heart_rate(bpm)

        # Envoyer les données FC via WebSocket si le client Unity est connecté
        if self.ws_server.is_client_connected():
            asyncio.ensure_future(self.ws_server.send_data_to_clients(bpm))
    
    def update_heart_rate(self, bpm):
        """
        Met à jour l'affichage de la fréquence cardiaque
        
        Args:
            bpm: Fréquence cardiaque en BPM
        """
        # Mettre à jour le label
        self.ids.heart_rate_label.text = f"{bpm}"
        
        # Mémoriser la dernière valeur
        self.last_bpm = bpm
    
    # ========== GESTION SERVEUR WEBSOCKET ==========

    def on_toggle(self, instance):
        """Gère l'activation/désactivation du serveur WebSocket"""
        if instance.state == 'down':
            # Vérifier qu'un appareil est connecté
            if not self.ble_manager or not self.ble_manager.is_connected:
                toast("Please connect to a HR sensor")
                instance.state = 'normal'
                return

            # Activer les contrôles (%FC cible)
            self.ids.target_hr_slider.disabled = False

            # MAJ du graphique
            if self.ax2:
                self.ax2.set_ylabel("HR target (%)", color="blue", 
                                   fontsize=12, fontweight="bold")

            # Démarrer le serveur WS
            asyncio.ensure_future(self._start_server())

            # Notifier Unity du démarrage du serveur websocket
            self.udp_discovery.send_message("command_ws", "START")

        else:
            # Désactiver les contrôles (%FC cible)
            self.ids.target_hr_slider.disabled = True

            # MAJ du graphique
            if self.ax2:
                self.ax2.set_ylabel("HR target (%)", color="grey", 
                                   fontsize=10, fontweight="normal")

            # Arrêter le serveur
            asyncio.ensure_future(self._stop_server())
        
    async def _start_server(self):
        """Démarre le serveur WebSocket"""
        success = await self.ws_server.start()
        
        if success:
            self.server_ws_running = True
            toast("Server started")
            logger.info("Serveur WebSocket activé")
        else:
            toast("Failed to start server")
            # Remettre le bouton en état normal
            self.ids.server_toggle_button.state = 'normal'
    
    async def _stop_server(self):
        """Arrête le serveur WebSocket"""
        await self.ws_server.stop()
        self.server_ws_running = False
        toast("Server stopped")
        logger.info("Serveur WebSocket désactivé") 

    # ========== CALLBACKS WEBSOCKET ==========
    
    def on_ws_message_received(self, websocket, message):
        """Callback quand un message est reçu d'un client"""
        logger.info(f"📩 Message reçu depuis Unity : {message}")
        
        # # Traiter le message si nécessaire
        # try:
        #     data = json.loads(message)
        #     # Exemple : Unity envoie une commande
        #     if 'command' in data:
        #         self.handle_unity_command(data['command'])
        # except json.JSONDecodeError:
        #     logger.warning(f"⚠️ Message invalide : {message}")
    
    def on_ws_client_connected(self, websocket):
        """Callback quand un client se connecte"""
        toast(f"Unity connected")
        logger.info(f"🔗 Client Unity connecté")
    
    def on_ws_client_disconnected(self, websocket):
        """Callback quand un client se déconnecte"""
        toast(f"Unity disconnected")
        logger.info(f"🔌 Client Unity déconnecté")
    
    def handle_unity_command(self, command: str):
        """Traite une commande reçue depuis Unity"""
        logger.info(f"🎮 Commande Unity : {command}")
        # Implémenter la logique selon les commandes