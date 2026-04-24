# Class KivyMD
from kivymd.uix.screen import MDScreen
from kivymd.toast import toast

# Class Kivy
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty
from kivy.app import App
from kivy.clock import Clock

# Custom modules
import matplotlib.pyplot as plt

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

        # Session
        self.hr_session = None
        
        # Initialisation du temps
        # self.time = 0
        
        # Configuration Matplotlib
        self.fig = None
        self.line_hr = None
        self.line_hr_target = None
        self.placeholder_text = None

        # UDP Controller
        self.udp_controller = None

        # # Debounce pour éviter trop d'envois UDP
        # self.slider_update_event = None
    
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
        self.hr_session = app.hr_session

        # S'abonner aux événements globaux (EventBus) pour recevoir les données de FC
        # event_bus.subscribe("heart_rate_received", self.on_heart_rate_received)
        event_bus.subscribe("hr_data_updated", self.on_hr_updated)
        
        # Charger toutes les data pré-existantes dans le graphique
        self.load_existing_data()
            
    def on_leave(self):
        """Appelé à la sortie de l'écran"""
        
        # Nettoyer les callbacks pour éviter les fuites de mémoire et les appels indésirables
        event_bus.unsubscribe("hr_data_updated", self.on_hr_updated)
    
    # ========== GESTION DES DONNÉES EXISTANTES ==========

    def load_existing_data(self):
        """Charge toutes les données de la session dans le graphique"""
        times, hr_percents = self.hr_session.get_graph_percent()
        
        if times and hr_percents:
            logger.info(f"📊 Chargement de {len(times)} points existants")
            
            # Mettre à jour le graphique
            self.line_hr.set_data(times, hr_percents)
            
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

        # Couleurs des axes
        self.ax1.tick_params(axis='x', colors='grey')  # temps
        self.ax1.tick_params(axis='y', colors='grey')  # %FCmax

        # Couleur du contour des axes
        for spine in self.ax1.spines.values():
            spine.set_color('grey')

        # Limites des axes
        self.ax1.set_xlim(0, 600)  # 10 minutes
        self.ax1.set_ylim(0, 100)  # 0-100% FCmax
        
        # Créer la ligne HR (vide au départ)
        self.line_hr, = self.ax1.plot([], [], 'r-', linewidth=2, label='HR (%)')
        self.ax1.legend(loc='upper left', facecolor='#1e1e1e', edgecolor='white', labelcolor='white')
        
        # ✨ Zone de remplissage HR (initialement vide)
        self.fill_hr = None

        # Créer la ligne HR target (vide au départ)
        self.line_hr_target, = self.ax1.plot([], [], 'b-', linewidth=2, label='HR Target (%)')

        # Ajouter la figure au widget
        self.ids.hr_graph_widget.figure = self.fig
    
    # --- CALLBACK ----#
    
    def on_hr_updated(self, point):

        bpm = point["bpm"]
        t = point["t"]

        # UI label
        self.ids.heart_rate_label.text = str(bpm)

        # update graph incrementally (IMPORTANT)
        self.line_hr.set_data(
            [p["t"] for p in self.hr_session.data],
            [p["percent"] or 0 for p in self.hr_session.data]
        )

        self.fig.canvas.draw_idle()
                
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
        
        # MAJ UI
        self.ax1.set_ylabel("HRmax (%)", color="red", fontsize=12)
        
        # Supprimer le placeholder
        if self.placeholder_text:
            self.placeholder_text.set_visible(False)

        # ✨ Supprimer l'ancien remplissage
        if self.fill_hr:
            self.fill_hr.remove()
        
        # Si on n'a pas reçu de données récentes, on ne fait rien
        if not self.hr_session.is_recording:
            return
        
        # Récupérer TOUTES les données de la session
        times, hr_percents = self.hr_session.get_graph_percent()

        if not times:
            return
        
        # Mettre à jour la ligne HR du graphique
        self.line_hr.set_data(times, hr_percents)

        # # ✨ Créer le nouveau remplissage sous la courbe
        # self.fill_hr = self.ax1.fill_between(
        #     times, 
        #     0,  # Base : 0
        #     hr_percents,  # Hauteur : valeurs HR
        #     alpha=0.3,  # Transparence
        #     color='red',  # Couleur
        #     interpolate=True
        # )

        # # Incrémenter le temps
        # self.time += 1
        
        # Forcer le redessinage
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

        # Rafraîchir le widget
        self.ids.hr_graph_widget.figure = self.fig    