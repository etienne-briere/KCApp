# Class KivyMD
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.toast import toast

# Class Kivy
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty, ObjectProperty
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


class SessionRow(MDBoxLayout):
    '''
    Ligne de la liste "Sessions à exporter" : nom de fichier + actions
    supprimer/exporter. Le kv correspondant est défini dans
    tracking_screen.kv (<SessionRow>:).
    '''
    record = ObjectProperty(None)
    # Nommage volontairement sans préfixe "on_" : Kivy réserve ce préfixe
    # pour ses hooks d'événements automatiques, un ObjectProperty nommé
    # ainsi ne reçoit jamais la valeur passée au constructeur.
    delete_callback = ObjectProperty(None)
    export_callback = ObjectProperty(None)


class TrackingScreen(MDScreen):
    '''
    ECRAN DE SUIVI DE LA FC
    '''
    # Properties pour l'UI
    heart_rate_label = StringProperty("--")
    cpm_label = StringProperty("--")

    # Affichage du graphique (activé par défaut)
    show_target = BooleanProperty(True)
    show_cpm = BooleanProperty(True)

    # Sessions passées en attente d'export ou de suppression
    has_pending_sessions = BooleanProperty(False)

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

        # S'abonner aux événements globaux (EventBus) pour recevoir les données de FC et de CPM
        event_bus.subscribe("heart_rate_received", self.on_hr_received)
        event_bus.subscribe("cpm_received", self.on_cpm_received)

        # Charger toutes les data pré-existantes dans le graphique
        self.load_existing_data()

        # Reconstruire la liste des sessions en attente d'export/suppression
        self._rebuild_pending_sessions_ui()

    def on_leave(self):
        """Appelé à la sortie de l'écran"""
        # Nettoyer les callbacks pour éviter les fuites de mémoire et les appels indésirables
        event_bus.unsubscribe("heart_rate_received", self.on_hr_received)
        event_bus.unsubscribe("cpm_received", self.on_cpm_received)
    
    # ========== GESTION DES DONNÉES EXISTANTES ==========

    def load_existing_data(self):
        """Charge toutes les données de la session dans le graphique"""
        hr_times, hrmax_percents = self.session.hr_session.get_graph_percent()

        # Réafficher la dernière valeur connue de chaque métrique
        if self.session.hr_session.hr_history:
            self.heart_rate_label = str(self.session.hr_session.hr_history[-1])
        if self.session.metrics.cpm_history:
            self.cpm_label = str(int(self.session.metrics.cpm_history[-1]))

        if hr_times and hrmax_percents:
            logger.info(f"📊 Chargement de {len(hr_times)} points existants")

            # Mettre à jour le graphique
            self.line_hr.set_data(hr_times, hrmax_percents)

            self.line_cpm.set_data(self.session.metrics.cpm_time, self.session.metrics.cpm_history)

            self.line_target.set_visible(self.show_target)
            self.line_cpm.set_visible(self.show_cpm)

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
            "Connectez votre capteur pour démarrer le suivi",
            ha="center",
            va="center",
            transform=self.ax1.transAxes,
            color="#9e9e9e",
            fontsize=14,
        )

        # Labels des axes (gris foncé, cohérent avec le thème clair de l'app)
        self.ax1.set_xlabel("Temps (s)", color="#616161")
        self.ax1.set_ylabel("FCmax (%)", color="#616161")
        self.ax2.set_ylabel("Cubes / min", color="#616161")

        # Couleurs des axes
        self.ax1.tick_params(axis='x', colors='#616161')  # temps
        self.ax1.tick_params(axis='y', colors='#616161')  # %FCmax
        self.ax2.tick_params(axis='y', colors='#616161')  # CPM

        # Couleur du contour des axes
        for spine in self.ax1.spines.values():
            spine.set_color('#bdbdbd')

        # ligne %FCmax cible
        self.line_target, = self.ax1.plot([], [], color='#2D7D32', linestyle='--', linewidth=2, drawstyle='steps-post', label='FCmax cible (%)')

        # ligne %FCmax (vide au départ)
        self.line_hr, = self.ax1.plot([], [], color='#C62828', linewidth=2, label='FCmax (%)')

        # ligne CPM (vide au départ) — couleur primaire de l'app (Teal)
        self.line_cpm, = self.ax2.plot([], [], color='#009688', linewidth=2, label='Cubes/min')

        self.plots = {
            "hr": {"line": self.line_hr, "label": "FCmax (%)"},
            "cpm": {"line": self.line_cpm, "label": "Cubes/min"},
            "target": {"line": self.line_target, "label": "FCmax cible (%)"},
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
        self.heart_rate_label = str(bpm)

        # forcer la mise à jour du graphique avec la cible actuelle
        self.session.config.update_target(self.session.config.target_hr_percent)

        self.update_graph()

    def on_cpm_received(self, value):

        # UI label
        self.cpm_label = str(int(value))

        self.update_graph()

    def on_toggle_target(self, active):
        """Afficher/masquer la %FC cible sur le graphique"""
        self.show_target = active
        self.update_graph()

    def on_toggle_cpm(self, active):
        """Afficher/masquer les cubes/min sur le graphique"""
        self.show_cpm = active
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

        if self.show_target and target_times and target_values:
            target_values = np.array(target_values, dtype=float)

            lower = target_values - 5
            upper = target_values

            self.target_zone = self.ax1.fill_between(
                target_times,
                lower,
                upper,
                color='#2D7D32',
                alpha=0.15
            )

        # UI
        self.ax1.set_ylabel("FCmax (%)", color="#C62828", fontsize=12)
        self.ax2.set_ylabel("Cubes / min", color="#009688", fontsize=12)

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
        self.line_target.set_visible(self.show_target)

        # ligne %FCmax
        self.line_hr.set_data(hr_times, hrmax_percents)

        # ligne CPM
        self.line_cpm.set_data(cpm_times, cpm_values)
        self.line_cpm.set_visible(self.show_cpm)

        # Axe de droite (Cubes/min) masqué avec sa ligne
        self.ax2.get_yaxis().set_visible(self.show_cpm)
        self.ax2.spines['right'].set_visible(self.show_cpm)

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

            if line is not None and len(line.get_xdata()) > 0 and line.get_visible():
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
                facecolor='#ffffff',
                edgecolor='#bdbdbd',
                labelcolor='#424242'
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
        # Archiver la session dans la liste "à exporter" (voir
        # GameSession.reset()) plutôt que de forcer un export immédiat :
        # l'utilisateur choisit ensuite de l'exporter ou de la supprimer.
        record = self.session.reset()
        if record:
            self._add_session_row(record)

        self.ax1.set_xlim(0, 600)
        self.ax1.set_ylim(0, 100)
        self.fig.canvas.draw_idle()

    def export_session(self):
        """Exporte la session en cours en CSV, sans la réinitialiser"""
        path = self.session.export_csv(
            include_target=self.show_target,
            include_cpm=self.show_cpm,
        )

        if path:
            toast(f"Session exportée : {path}")
        else:
            toast("Aucune donnée à exporter")

    # ========== SESSIONS EN ATTENTE D'EXPORT/SUPPRESSION ==========

    def _rebuild_pending_sessions_ui(self):
        """Reconstruit la liste à partir de session.pending_sessions"""
        self.ids.pending_sessions_list.clear_widgets()
        for record in self.session.pending_sessions:
            self._add_session_row(record)

    def _add_session_row(self, record):
        row = SessionRow(
            record=record,
            delete_callback=self._delete_pending_session,
            export_callback=self._export_pending_session,
        )
        self.ids.pending_sessions_list.add_widget(row)
        self.has_pending_sessions = True

    def _remove_session_row(self, row):
        if row.record in self.session.pending_sessions:
            self.session.pending_sessions.remove(row.record)
        self.ids.pending_sessions_list.remove_widget(row)
        self.has_pending_sessions = bool(self.session.pending_sessions)

    def _delete_pending_session(self, row):
        """Supprime une session en attente sans jamais l'écrire sur disque"""
        self._remove_session_row(row)
        toast("Session supprimée")

    def _export_pending_session(self, row):
        """Exporte une session en attente en CSV, puis la retire de la liste"""
        path = row.record.export_csv(
            include_target=self.show_target,
            include_cpm=self.show_cpm,
        )
        toast(f"Session exportée : {path}")
        self._remove_session_row(row)
