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
import numpy as np

# Standard library
import asyncio

from pyparsing import line
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
        self.target_zone = None
        self.target_received = False

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

        if self.session.config.target_hr_percent is not None:
            self.target_received = True

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

        # ligne %FCmax cible
        self.line_target, = self.ax1.plot([], [], color='green', linestyle='--', linewidth=2, drawstyle='steps-post', label='Target %HRmax')
        
        # ligne %FCmax (vide au départ)
        self.line_hr, = self.ax1.plot([], [], 'r-', linewidth=2, label='HRmax (%)')
    
        # ligne CPM (vide au départ)
        self.line_cpm, = self.ax2.plot([], [], 'cyan', linewidth=2, label='CPM')

        self.plots = {
            "hr": {"line": self.line_hr, "label": "HRmax (%)"},
            "cpm": {"line": self.line_cpm, "label": "CPM"},
            "target": {"line": self.line_target, "label": "Target %HRmax"},
        }

        # Limites des axes
        self.ax1.set_xlim(0, 600)  # 10 minutes
        self.ax1.set_ylim(0, 100)  # 0-100 %FCmax
        self.ax2.set_ylim(20, 210) # CPM

        self.update_legend()

        # Ajouter la figure au widget
        self.ids.hr_graph_widget.figure = self.fig
    
    #==== CALLBACK =====#
    
    def on_hr_received(self, bpm):

        # UI label
        self.ids.heart_rate_label.text = str(bpm)

        # forcer la mise à jour du graphique avec la cible actuelle
        self.session.config.update_target(self.session.config.target_hr_percent) 

        self.update_graph()
    
    #==== GRAPHIQUE =====#

    def update_graph(self):
        '''Mettre à jour le graphique'''

        # Données à afficher
        hr_times, hrmax_percents = self.session.hr_session.get_graph_percent()
        cpm_times, cpm_values = self.session.metrics.cpm_time, self.session.metrics.cpm_history
        target_times, target_values = self.session.config.target_time or [], self.session.config.target_history or []

        # supprimer ancienne zone
        if self.target_zone:
            self.target_zone.remove()
            self.target_zone = None

        if target_times and target_values:
            target_values = np.array(target_values, dtype=float)

            lower = target_values - 5
            upper = target_values

            self.target_zone = self.ax1.fill_between(
                target_times,
                lower,
                upper,
                color='green',
                alpha=0.15
            )

        # UI
        self.ax1.set_ylabel("HRmax (%)", color="red", fontsize=12)
        self.ax2.set_ylabel("Cubes / min", color="skyblue", fontsize=12)

        # Supprimer le placeholder
        if self.placeholder_text:
            self.placeholder_text.set_visible(False)

        # target = self.session.config.target_hr_percent

        # if target is not None:
        #     # créer ligne si elle n'existe pas encore
        #     self.target_line = self.ax1.axhline(
        #         y=target,
        #         color='green',
        #         linestyle='--',
        #         linewidth=1,
        #         label='Target %HRmax'
        #     )
        #     self.update_legend()

        #     # gérer la zone
        #     if self.target_zone:
        #         self.target_zone.remove()
        #         self.low_zone.remove()
        #         self.high_zone.remove()
        #         self.update_legend()

        #     # zone cible
        #     self.target_zone = self.ax1.axhspan(target - 5, target, color='green', alpha=0.1)
        #     # trop bas
        #     self.low_zone = self.ax1.axhspan(0, target - 5, color='blue', alpha=0.05)
        #     # trop haut
        #     self.high_zone = self.ax1.axhspan(target, 100, color='red', alpha=0.05)

        # ligne %FCmax cible
        self.line_target.set_data(target_times, target_values)
        
        # ligne %FCmax
        self.line_hr.set_data(hr_times, hrmax_percents)

        # ligne CPM
        self.line_cpm.set_data(cpm_times, cpm_values)

        self.update_legend()

        # Ajuster les limites de l'axe HR en fonction des données
        self.ax1.relim()
        self.ax1.autoscale_view()

        # Ajuster les limites de l'axe CPM en fonction des données
        self.ax2.relim() 
        self.ax2.autoscale_view() 

        # Redessiner
        self.fig.canvas.draw_idle()
    
    def is_line_valid(self, line):
        return line is not None and len(line.get_xdata()) > 0
    
    def update_legend(self):

        lines = []
        labels = []

        for plot in self.plots.values():
            line = plot["line"]

            if line is not None and len(line.get_xdata()) > 0:
                lines.append(line)
                labels.append(plot["label"])

        # supprimer ancienne légende
        if hasattr(self, "legend") and self.legend:
            self.legend.remove()
            self.legend = None

        # 🔥 IMPORTANT : recréer même si vide plus tard
        if lines:
            self.legend = self.ax1.legend(
                lines,
                labels,
                loc='upper left',
                facecolor='#1e1e1e',
                edgecolor='white',
                labelcolor='white'
            )

    def center_graph(self):
        '''Recentrer le graphique à partir du début de la partie'''
        
        # Moment du slice du 1er cube
        game_start_time = self.session.metrics.cpm_time[0] if self.session.metrics.cpm_time else 0
        
        # MAJ UI
        self.ax1.set_xlim(game_start_time, game_start_time + 600)
        self.ax1.set_ylim(0, 100)

        # Redessiner graphe
        self.fig.canvas.draw_idle()
    
    def reset_graph(self):
        self.session.reset()
        self.ax1.set_xlim(0, 600)
        self.ax1.set_ylim(0, 100)
        self.fig.canvas.draw_idle()
         