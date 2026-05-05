# Class KivyMD
from kivymd.uix.screen import MDScreen
from kivymd.toast import toast

# Class Kivy
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty
from kivy.app import App
from kivy.clock import Clock

# Custom modules
import matplotlib.pyplot as plt
import time

# Standard library
import asyncio
from utils.event_bus import event_bus
from utils.logger import get_logger

logger = get_logger(__name__)

class TrackingScreen(MDScreen):
    '''
    ECRAN DE SUIVI DE LA FC
    '''
    # Properties pour l'UI
    heart_rate_label = StringProperty("--")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Configuration Matplotlib
        self.fig = None
        self.line_hr = None
        self.placeholder_text = None

        # UDP Controller
        self.udp_controller = None
    
    def on_kv_post(self, base_widget):
        """
        Appelé automatiquement quand le kv est chargé
        et que les ids sont disponibles.
        """
        # Initialiser le graphique Matplotlib
        self.init_graph()
    
    def on_pre_enter(self):
        """Appelé à l'ouverture de l'écran"""
        # Récupérer les managers
        app = App.get_running_app()
        self.ble_manager = app.ble_manager
        self.udp_discovery = app.udp_discovery
        self.udp_controller = app.udp_controller
        self.session = app.session

        # S'abonner aux événements globaux (EventBus) pour recevoir les données de FC
        event_bus.subscribe("heart_rate_received", self.on_hr_received)
        
        # Charger toutes les data pré-existantes dans le graphique
        self.load_existing_data()
            
    def on_leave(self):
        """Appelé à la sortie de l'écran"""
        # Nettoyer les callbacks pour éviter les fuites de mémoire et les appels indésirables
        event_bus.unsubscribe("heart_rate_received", self.on_hr_received)

    
    # ========== GESTION DES DONNÉES EXISTANTES ==========

    def load_existing_data(self):
        """Charge toutes les données de la session dans le graphique"""
        hr_times, hrmax_percents = self.session.hr_session.get_graph_percent()
        
        if hr_times and hrmax_percents:
            logger.info(f"📊 Chargement de {len(hr_times)} points existants")
            
            # Mettre à jour le graphique
            self.line_hr.set_data(hr_times, hrmax_percents)

            self.line_cpm.set_data(self.session.metrics.cpm_time, self.session.metrics.cpm_history)
            
            # Redessiner
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()
        else:
            logger.info("📊 Aucune donnée existante à charger")
    
    # ========== GRAPHIQUE MATPLOTLIB ==========

    def init_graph(self):
        """Initialise le graphique Matplotlib"""
        
        # Créer la figure et les axes
        self.fig, self.ax1 = plt.subplots()

        # Axe secondaire (CPM)
        self.ax2 = self.ax1.twinx()

        # Style du graphique
        self.fig.patch.set_alpha(0.0) # Fond transparent
        self.ax1.set_facecolor("none") # Fond transparent
        self.ax1.margins(x=0, y=0) # Pas de marges autour des données
        self.fig.tight_layout() # Ajuster le layout
        self.ax1.grid(True, alpha=0.2) # Grille légère

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
        self.ax1.set_xlabel("Time (s)", color="grey")
        self.ax1.set_ylabel("HRmax (%)", color="grey")
        self.ax2.set_ylabel("Cubes / min", color="grey")

        # Couleurs des axes
        self.ax1.tick_params(axis='x', colors='grey')  # temps
        self.ax1.tick_params(axis='y', colors='grey')  # %FCmax
        self.ax2.tick_params(axis='y', colors='grey')  # CPM

        # Couleur du contour des axes
        for spine in self.ax1.spines.values():
            spine.set_color('grey')
        
        # ligne HR (vide au départ)
        self.line_hr, = self.ax1.plot([], [], 'r-', linewidth=2, label='HRmax (%)')
        self.ax1.legend(loc='upper left', facecolor='#1e1e1e', edgecolor='white', labelcolor='white')
    
        # ligne CPM (vide au départ)
        self.line_cpm, = self.ax2.plot([], [], 'cyan', linewidth=2, label='CPM')
        self.ax2.legend(loc='upper right', facecolor='#1e1e1e', edgecolor='white', labelcolor='white')

        # Limites des axes
        self.ax1.set_xlim(0, 600)  # 10 minutes
        self.ax1.set_ylim(0, 100)  # 0-100 %FCmax
        self.ax2.set_ylim(30, 200) # 30-200 CPM

        # Ajouter la figure au widget
        self.ids.hr_graph_widget.figure = self.fig
    
    #==== CALLBACK ====#
    
    def on_hr_received(self, bpm):

        # UI label
        self.ids.heart_rate_label.text = str(bpm)
        
        self.update_graph()

    def update_graph(self):
        '''Mettre à jour le graphique'''

        # UI
        self.ax1.set_ylabel("HRmax (%)", color="red", fontsize=12)
        self.ax2.set_ylabel("Cubes / min", color="skyblue", fontsize=12)

        # Supprimer le placeholder
        if self.placeholder_text:
            self.placeholder_text.set_visible(False)
        
        hr_times, hrmax_percents = self.session.hr_session.get_graph_percent()

        # ligne HR
        self.line_hr.set_data(hr_times, hrmax_percents)

        # ligne CPM
        self.line_cpm.set_data(
            self.session.metrics.cpm_time,
            self.session.metrics.cpm_history
        )

        # Ajuster les limites de l'axe CPM en fonction des données
        self.ax2.relim() 
        self.ax2.autoscale_view() 

        # Redessiner
        self.fig.canvas.draw_idle()
    
    def reset_graph(self):
        self.session.reset()
        self.ax1.set_xlim(0, 600)
        self.fig.canvas.draw_idle()
         