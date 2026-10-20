# Class KivyMD
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.toast import toast

# Class Kivy
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty, ObjectProperty
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import Metrics
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform

# Custom modules
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import time
import numpy as np

# Standard library
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "csv_export_kit"))
from csv_export.platform_io import default_export_dir, pick_export_folder, share_file_android  # noqa: E402

from pyparsing import line
from utils.event_bus import event_bus
from utils.logger import get_logger

logger = get_logger(__name__)

# Couleurs/labels des bandes d'état inactif (mêmes valeurs FG que la
# bannière Home, voir ui/game_state_style.py)
# — cohérence visuelle entre l'écran d'accueil et le graphique de suivi.
_INACTIVE_STATE_STYLES = {
    "menu": {"color": (0.098, 0.463, 0.824, 1), "label": "Menu"},
    "ready": {"color": (0.459, 0.459, 0.459, 1), "label": "Prêt"},
    "paused": {"color": (0.780, 0.518, 0.047, 1), "label": "En pause"},
    "finished": {"color": (0.482, 0.122, 0.635, 1), "label": "Terminé"},
    # Posé localement (pas envoyé par Unity) dès qu'Unity n'est plus
    # joignable — voir udp_discovery.py/_check_unity_connection.
    "disconnected": {"color": (0.776, 0.157, 0.157, 1), "label": "Jeu déconnecté"},
}
_DEFAULT_INACTIVE_STYLE = {"color": (0.459, 0.459, 0.459, 1), "label": "Inactif"}
# Ordre d'affichage dans la légende, pour un ordre stable d'un tracé à l'autre.
_INACTIVE_STATE_ORDER = ["disconnected", "menu", "ready", "paused", "finished"]


class GraphAwareScrollView(ScrollView):
    '''
    ScrollView qui laisse un widget enfant (ici le graphique matplotlib)
    gérer lui-même tout toucher qui le concerne — molette de souris,
    pan à un doigt, zoom pincé à deux doigts — au lieu de systématiquement
    faire défiler la page.

    Sans ça, ScrollView.on_scroll_start/on_touch_down intercepte tout
    toucher sur son contenu (sauf tout en haut/bas de page) avant même
    qu'il puisse atteindre un enfant plus bas dans l'arbre. Pour la molette,
    le graphique ne recevait alors jamais l'événement nécessaire à son
    zoom. Pour un pincement à deux doigts sur tablette/mobile, c'est pire :
    ScrollView garde le PREMIER doigt en attente (pour décider si c'est un
    tap ou un scroll) et ne le transmet au graphique qu'après un délai —
    le second doigt du pincement arrive donc seul côté graphique, qui n'a
    alors qu'un seul point de contact et ne peut pas calculer de zoom.
    '''
    no_scroll_widget = ObjectProperty(None, allownone=True)

    def on_touch_down(self, touch):
        if self.no_scroll_widget is not None:
            touch.push()
            touch.apply_transform_2d(self.to_local)
            collides = self.no_scroll_widget.collide_point(*touch.pos)
            touch.pop()
            if collides:
                # Contourne la gestion de scroll/molette de ScrollView et
                # redispatche immédiatement aux enfants (dont le
                # graphique), qui gère pan/zoom lui-même.
                return self.simulate_touch_down(touch)
        return super().on_touch_down(touch)


# Modes adaptatifs : seuls modes qui envoient une %FC cible à Unity (voir
# pilotage_screen.py). Partagé par le graphique et la liste d'export.
ADAPTIVE_MODELS = ("PID", "DRL")


class SessionRow(MDBoxLayout):
    '''
    Carte de la liste "Sessions à exporter" : nom de fichier, cases à
    cocher propres à CETTE session (indépendantes des cases d'affichage du
    graphique) pour choisir quelles données inclure, et actions
    supprimer/exporter. Le kv correspondant est défini dans
    tracking_screen.kv (<SessionRow>:).
    '''
    record = ObjectProperty(None)
    # Nommage volontairement sans préfixe "on_" : Kivy réserve ce préfixe
    # pour ses hooks d'événements automatiques, un ObjectProperty nommé
    # ainsi ne reçoit jamais la valeur passée au constructeur.
    delete_callback = ObjectProperty(None)
    export_callback = ObjectProperty(None)

    # Ce que CETTE session inclura à son prochain export — indépendant des
    # cases d'affichage du graphique (show_game_state sur
    # TrackingScreen, qui ne contrôle que l'affichage du graphique).
    # FC n'a pas de case : toujours incluse. La %FC cible et les cubes/min
    # non plus : ils suivent le contenu de la session (voir on_record).
    include_target = BooleanProperty(False)
    include_cpm = BooleanProperty(False)
    include_state = BooleanProperty(True)

    def on_record(self, instance, record):
        """
        %FC cible incluse uniquement si la session était en mode adaptatif,
        cubes/min dès que la session en contient (comme sur le graphique).
        """
        self.include_target = bool(record and record.model in ADAPTIVE_MODELS)
        self.include_cpm = bool(record and record.cpm_values)


class TrackingScreen(MDScreen):
    '''
    ECRAN DE SUIVI DE LA FC
    '''
    # Contrôleur en cours de partie : libellés des états et des raisons de bascule envoyés par Unity
    CONTROLLER_STATE_LABELS = {
        "PID_WARMUP": "PID (échauffement)",
        "DRL": "DRL",
        "PID_BACKUP": "PID de secours",
        "MANUAL": "Manuel",
        "PID": "PID",
        "LEGACY_DRL": "DRL (ancien contrôleur)",
        "LEGACY_PID": "PID (ancien contrôleur)",
        "LEGACY_FIXED": "Fixe",
        "LEGACY_INCREMENTAL": "Incrémental",
    }
    SWITCH_REASON_LABELS = {
        "start": "début de partie",
        "warmup_end": "fin de l'échauffement",
        "early_overshoot": "dépassement précoce",
        "third_dive": "3e plongée (cycle limite)",
        "floor_time": "trop de temps au plancher",
        "pid_windup": "PID saturé",
        "persistent_overshoot": "dépassement persistant",
        "teacher_override": "commande tablette",
        "model_error": "erreur du modèle",
    }

    # Properties pour l'UI
    heart_rate_label = StringProperty("--")
    hrmax_percent_label = StringProperty("--")
    patient_age = StringProperty("--")
    cpm_label = StringProperty("--")
    # Capteur toujours connecté côté BLE mais plus aucune FC reçue (même
    # critère que l'icône cœur barré de la status bar) — voir scan_screen.py.
    hr_signal_lost = BooleanProperty(False)
    # %FCmax/âge n'ont pas de sens sans profil actif — voir tracking_screen.kv
    player_selected = BooleanProperty(False)

    # Affichage du graphique : seul l'état du jeu a une case (désactivée par
    # défaut). La %FC cible suit target_available, les cubes/min s'affichent
    # dès que des cpm ont été reçus de Unity (voir update_graph).
    show_game_state = BooleanProperty(False)

    # Mode de jeu courant — mirroir de session.config.model (pas une
    # propriété Kivy) pour permettre au kv de réagir à son changement.
    current_model = StringProperty("Unknown")
    # %FC cible (courbe du graphique + Card de saisie) affichée uniquement en
    # mode adaptatif : les autres modes n'envoient jamais de cible FC à Unity.
    target_available = BooleanProperty(False)
    # Card "FC cible" (modifiable ici comme dans l'écran Contrôle)
    target_hr = NumericProperty(50)  # % FCmax
    # Cards "Cpm minimum / maximum" des modes adaptatifs (comme l'écran Contrôle)
    adaptive_min_cpm = NumericProperty(30)
    adaptive_max_cpm = NumericProperty(200)
    # Card "Cadence fixe" du mode Fixe (comme l'écran Contrôle)
    fixed_cpm = NumericProperty(60)
    unity_connected = BooleanProperty(False)

    # État de partie reçu de Unity (Menu/Ready/Playing/Paused/Finished) —
    # la Card "Contrôleur en cours de partie" n'est affichée que pendant
    # une partie en cours (game_state == "Playing").
    game_state = StringProperty("Menu")
    controller_state_label = StringProperty("") # contrôleur actif en cours de partie (texte affiché)
    controller_reason_label = StringProperty("") # raison de la dernière bascule
    manual_cpm = NumericProperty(60) # cadence du mode manuel (cubes/min)
    # Bouton PID/DRL_DEPLOYED/DRL_RUN3 à styliser comme actif (puce verte),
    # "" si aucun ne correspond à l'état courant (ex: Manuel) — voir
    # _controller_button_for_state.
    active_controller_button = StringProperty("")
    # Toggle "PID de secours" sous le graphique (mode DRL) : bascule
    # automatique si le DRL entre en cycle limite, modifiable en cours de partie.
    pid_backup = BooleanProperty(False)

    # Sessions passées en attente d'export ou de suppression
    has_pending_sessions = BooleanProperty(False)

    # Le choix du dossier (plyer.filechooser) n'a d'effet que sur desktop —
    # sur Android le fichier va toujours dans le stockage applicatif puis
    # est partagé via la feuille de partage (voir _finish_export).
    can_choose_export_folder = BooleanProperty(platform != "android")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Dossier d'export courant, modifiable via choose_export_folder()
        # sur desktop. Reste au défaut sur Android (non affiché dans l'UI).
        self.export_folder = default_export_dir("KCApp")

        # Configuration Matplotlib
        self.fig = None
        self.line_hr = None
        self.placeholder_text = None
        self.target_zone = None
        self.target_received = False

        # Bandes colorées par état inactif (voir update_graph / GameSession.get_inactive_segments)
        self.inactive_zone_artists = []
        self.inactive_state_styles = []

        # UDP Controller
        self.udp_controller = None

        # Dernier modèle DRL choisi manuellement via les boutons DRL/DRL Run 3
        # ("deployed"/"run3", voir switch_controller) — Unity ne renvoie que
        # l'état générique "DRL" (pas lequel des deux modèles), donc
        # config.is_drl_run3 (le modèle CONFIGURÉ pour la partie, pas
        # forcément celui en cours après une bascule manuelle) ne suffit
        # pas à savoir lequel mettre en évidence. None tant qu'aucune
        # bascule manuelle n'a eu lieu dans cette partie (on se fie alors à
        # config.is_drl_run3) — remis à None en sortant de Playing (voir
        # _sync_controller_state) pour repartir sur la config à la prochaine partie.
        self._manual_drl_variant = None

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

        self._sync_model(self.session.config.model)
        self._sync_player_age(self.session.user_profile)
        self._sync_target_hr(self.session.config.target_hr_percent)
        self._sync_cpm_fields(self.session.config)
        self.unity_connected = self.udp_discovery.is_unity_connected()
        self.game_state = self.session.game_state.capitalize()
        self._sync_controller_state(self.session.config)
        self._sync_pid_backup(self.session.config)

        # S'abonner aux événements globaux (EventBus) pour recevoir les données de FC et de CPM
        event_bus.subscribe("heart_rate_received", self.on_hr_received)
        event_bus.subscribe("cpm_received", self.on_cpm_received)
        event_bus.subscribe("session_updated", self.on_session_updated)
        event_bus.subscribe("hr_sensor_status_changed", self.on_hr_sensor_status_changed)
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)

        # Charger toutes les data pré-existantes dans le graphique
        self.load_existing_data()

        # L'évènement n'est reçu que sur cet écran : resynchroniser avec la
        # status bar au cas où le capteur aurait décroché entre-temps.
        if app.root:
            self._set_hr_signal_lost(not app.root.ids.status_bar.hr_sensor_connected)

        # Reconstruire la liste des sessions en attente d'export/suppression
        self._rebuild_pending_sessions_ui()

    def on_leave(self):
        """Appelé à la sortie de l'écran"""
        # Nettoyer les callbacks pour éviter les fuites de mémoire et les appels indésirables
        event_bus.unsubscribe("heart_rate_received", self.on_hr_received)
        event_bus.unsubscribe("cpm_received", self.on_cpm_received)
        event_bus.unsubscribe("session_updated", self.on_session_updated)
        event_bus.unsubscribe("hr_sensor_status_changed", self.on_hr_sensor_status_changed)
        event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)

    def on_session_updated(self, session):
        self._sync_model(session.config.model)
        self._sync_player_age(session.user_profile)
        self._sync_target_hr(session.config.target_hr_percent)
        self._sync_cpm_fields(session.config)
        self.game_state = session.game_state.capitalize()
        self._sync_controller_state(session.config)
        self._sync_pid_backup(session.config)

    def _sync_controller_state(self, config):
        """État du contrôleur en cours de partie — uniquement pendant une partie en cours"""
        if self.game_state == "Playing" and config.controller_state:
            state = config.controller_state
            self.controller_state_label = self.CONTROLLER_STATE_LABELS.get(state, state)
            reason = config.controller_switch_reason or ""
            self.controller_reason_label = self.SWITCH_REASON_LABELS.get(reason, reason)
            self.active_controller_button = self._controller_button_for_state(state, config)
        elif self.game_state != "Playing":
            self.controller_state_label = ""
            self.controller_reason_label = ""
            self.active_controller_button = ""
            self._manual_drl_variant = None

    def _controller_button_for_state(self, state, config):
        """
        Bouton PID/DRL_DEPLOYED/DRL_RUN3/MANUAL (carte "Contrôleur en cours
        de partie") correspondant à l'état courant, pour le mettre en
        évidence (puce verte) — "" si aucun ne correspond. PID/PID_WARMUP/
        PID_BACKUP tournent sur le même algorithme PID (voir discussion),
        donc tous les trois mettent en évidence le bouton PID.
        """
        if state in ("PID", "PID_WARMUP", "PID_BACKUP", "LEGACY_PID"):
            return "PID"
        if state == "DRL":
            # Unity ne renvoie que l'état générique "DRL", pas le modèle en
            # cours : on se fie à la dernière bascule manuelle de cette
            # partie si elle existe, sinon au modèle configuré.
            variant = self._manual_drl_variant
            if variant is None:
                variant = "run3" if config.is_drl_run3 else "deployed"
            return "DRL_RUN3" if variant == "run3" else "DRL_DEPLOYED"
        if state == "LEGACY_DRL":
            # Version Unity antérieure au contrôleur hybride : un seul DRL
            # possible, Run 3 n'a pas de sens ici.
            return "DRL_DEPLOYED"
        if state == "MANUAL":
            return "MANUAL"
        return ""

    def _sync_pid_backup(self, config):
        """Toggle PID de secours : reflète le réglage courant du contrôleur hybride"""
        if config.controller_config is not None:
            self.pid_backup = config.effective_pid_backup

    def handle_unity_connection(self, data):
        self.unity_connected = data["connected"]

    def _sync_target_hr(self, value):
        """Reflète la FC cible reçue de Unity, sans écraser une saisie en cours"""
        self._sync_field("target_hr_field", "target_hr", value)

    def _sync_cpm_fields(self, config):
        self._sync_field("adaptive_min_cpm_field", "adaptive_min_cpm", config.adaptive_min_cpm)
        self._sync_field("adaptive_max_cpm_field", "adaptive_max_cpm", config.adaptive_max_cpm)
        self._sync_field("fixed_cpm_field", "fixed_cpm", config.cube_per_min)

    def _sync_field(self, field_id, prop_name, value):
        """Reflète une valeur reçue de Unity dans un champ, sans écraser une saisie en cours"""
        if value is None:
            return
        field = self.ids.get(field_id)
        if field is not None and field.focus:
            return
        setattr(self, prop_name, value)
        if field is not None:
            field.text = str(int(value))

    def _submit_cpm_field(self, text, field_id, prop_name, config_attr,
                          min_value, max_value, send_method_name, label):
        """Champ cpm validé — même logique que l'écran Contrôle (_submit_int_field)"""
        field = self.ids[field_id]
        try:
            value = int(text)
        except ValueError:
            toast("Valeur invalide")
            field.text = str(int(getattr(self, prop_name)))
            return

        value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)

        field.text = str(value)
        if value == getattr(self.session.config, config_attr):
            return

        setattr(self, prop_name, value)
        setattr(self.session.config, config_attr, value)
        logger.info(f"🔧 {label}: {value}")

        if self.udp_controller and getattr(self.udp_controller, send_method_name)(value):
            logger.info(f"📤 {label} envoyé: {value}")

    def on_adaptive_min_cpm_submit(self, text):
        self._submit_cpm_field(text, "adaptive_min_cpm_field", "adaptive_min_cpm", "adaptive_min_cpm",
                               0, None, "set_adaptive_min_cpm", "Cpm min adaptatif")

    def on_adaptive_max_cpm_submit(self, text):
        self._submit_cpm_field(text, "adaptive_max_cpm_field", "adaptive_max_cpm", "adaptive_max_cpm",
                               0, None, "set_adaptive_max_cpm", "Cpm max adaptatif")

    def on_fixed_cpm_submit(self, text):
        """Cadence du mode Fixe : mêmes bornes (30-200) que l'écran Contrôle"""
        self._submit_cpm_field(text, "fixed_cpm_field", "fixed_cpm", "cube_per_min",
                               30, 200, "set_cube_rate", "Cubes par minute")

    def on_target_hr_submit(self, text):
        """Champ FC cible validé (Entrée ou perte de focus) — même logique que l'écran Contrôle"""
        try:
            value = int(text)
        except ValueError:
            toast("Valeur invalide")
            self.ids.target_hr_field.text = str(int(self.target_hr))
            return

        value = max(10, min(100, value))
        self.ids.target_hr_field.text = str(value)
        if value == self.session.config.target_hr_percent:
            return

        self.target_hr = value
        self.session.config.update_target(value)
        logger.info(f"🎯 FC cible: {value}%")

        if self.udp_controller and self.udp_controller.set_target_hr(value):
            logger.info(f"📤 Target HR envoyée: {value}%")
        self.update_graph()

    # ========== CONTRÔLEUR HYBRIDE : BASCULE EN COURS DE PARTIE ==========

    def switch_controller(self, state):
        """Boutons PID / DRL / DRL Run 3 : bascule à la seconde suivante"""
        if not self.udp_controller:
            return
        label = {"PID": "PID", "DRL_DEPLOYED": "DRL", "DRL_RUN3": "DRL Run 3"}.get(state, state)
        if self.udp_controller.set_controller_state(state):
            toast(f"Bascule demandée : {label}")
            logger.info(f"📤 Bascule contrôleur demandée : {state}")
            # Mise à jour optimiste du bouton en évidence — sans attendre
            # l'écho d'Unity, qui ne distingue pas DRL/DRL Run 3 dans son
            # état générique "DRL" (voir _controller_button_for_state).
            self.active_controller_button = state
            if state in ("DRL_DEPLOYED", "DRL_RUN3"):
                self._manual_drl_variant = "run3" if state == "DRL_RUN3" else "deployed"
        else:
            toast("❌ Échec de l'envoi")

    def on_pid_backup_toggle(self, is_active):
        """Toggle PID de secours sous le graphique (mode DRL) : envoyé à Unity, modifiable en cours de partie"""
        if is_active == self.pid_backup:
            return
        self.pid_backup = is_active

        cfg = self.session.config
        drl_model = "run3" if cfg.is_drl_run3 else "deployed"
        pid_warmup = bool(cfg.pid_warmup)
        if self.udp_controller and self.udp_controller.set_controller_setup(drl_model, pid_warmup, is_active):
            logger.info(f"📤 PID de secours : {'ON' if is_active else 'OFF'}")
        else:
            toast("❌ Échec de l'envoi")
        # Miroir local de la traduction faite par Unity (HybridControllerPrefs.ApplyMenuChoice),
        # comme _send_controller_setup dans pilotage_screen.py.
        if drl_model == "deployed" and not pid_warmup and not is_active:
            cfg.controller_config = "off"
        elif drl_model == "run3" and not is_active:
            cfg.controller_config = "drl_run3" if pid_warmup else "drl_run3_no_warmup"
        else:
            cfg.controller_config = "custom"
        cfg.drl_model = drl_model
        cfg.pid_backup = is_active

    def _parse_manual_cpm(self, text):
        """Valide/clampe la cadence manuelle saisie et met à jour la propriété + le champ. None si invalide."""
        try:
            value = int(text)
        except ValueError:
            toast("Valeur invalide")
            self.ids.manual_cpm_field.text = str(int(self.manual_cpm))
            return None
        value = max(30, min(200, value))
        self.manual_cpm = value
        self.ids.manual_cpm_field.text = str(value)
        return value

    def on_manual_cpm_submit(self, text):
        """
        Champ cadence manuelle validé : si le mode Manuel est déjà actif,
        applique directement la nouvelle valeur (pas besoin de recliquer
        sur le bouton) ; sinon se contente de mémoriser la valeur, en
        attendant que le bouton Manuel passe réellement en mode manuel.
        """
        value = self._parse_manual_cpm(text)
        if value is not None and self.active_controller_button == "MANUAL":
            self._send_manual_cpm()

    def apply_manual_cpm(self):
        """Bouton Manuel : passe en cadence manuelle (ou change la cadence)"""
        if self._parse_manual_cpm(self.ids.manual_cpm_field.text) is None:
            return
        self._send_manual_cpm()

    def _send_manual_cpm(self):
        if self.udp_controller and self.udp_controller.set_manual_cpm(self.manual_cpm):
            toast(f"Cadence manuelle : {int(self.manual_cpm)} cubes/min")
            logger.info(f"📤 Cadence manuelle : {self.manual_cpm}")
            # Mise à jour optimiste, comme switch_controller — sans attendre l'écho d'Unity.
            self.active_controller_button = "MANUAL"
        else:
            toast("❌ Échec de l'envoi")

    def _sync_model(self, model):
        """
        Reflète session.config.model (pas une propriété Kivy) dans
        current_model, et n'affiche la %FC cible (courbe + Card de saisie)
        qu'en mode adaptatif (PID/DRL).
        """
        self.current_model = model
        target_available = model in ADAPTIVE_MODELS
        if target_available != self.target_available:
            self.target_available = target_available
            self.update_graph()

    def _sync_player_age(self, user_profile):
        """
        Reflète user_profile.age/name (pas des propriétés Kivy) dans
        patient_age/player_selected. %FCmax et âge n'ont pas de sens sans
        profil actif — on garde le label visible ("-- % FCmax · -- ans")
        plutôt que de le masquer, voir hrmax_percent_label.
        """
        self.player_selected = bool(user_profile.name)
        self.patient_age = str(user_profile.age) if self.player_selected else "--"
        if not self.player_selected:
            self.hrmax_percent_label = "--"

    # ========== GESTION DES DONNÉES EXISTANTES ==========

    def load_existing_data(self):
        """Charge toutes les données de la session dans le graphique"""
        hr_times, hrmax_percents = self.session.hr_session.get_graph_percent()

        # Réafficher la dernière valeur connue de chaque métrique
        if self.session.hr_session.hr_history:
            self.heart_rate_label = str(self.session.hr_session.hr_history[-1])
        if self.player_selected and self.session.hr_session.hrmax_percent_history:
            self.hrmax_percent_label = self._format_percent(
                self.session.hr_session.hrmax_percent_history[-1])
        if self.session.metrics.cpm_history:
            self.cpm_label = str(int(self.session.metrics.cpm_history[-1]))

        if hr_times and hrmax_percents:
            logger.info(f"📊 Chargement de {len(hr_times)} points existants")

            # Mettre à jour le graphique
            self.line_hr.set_data(hr_times, hrmax_percents)

            self.line_cpm.set_data(self.session.metrics.cpm_time, self.session.metrics.cpm_history)

            self.line_target.set_visible(self.target_available)
            self.line_cpm.set_visible(bool(self.session.metrics.cpm_history))

            # Redessiner
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()
        else:
            logger.info("📊 Aucune donnée existante à charger")
    
    # ========== GRAPHIQUE MATPLOTLIB ==========

    def init_graph(self):
        """Initialise le graphique Matplotlib"""

        # dpi = 100 (défaut desktop) mis à l'échelle par Metrics.density,
        # PAS Metrics.dpi (le DPI physique brut de l'écran, qui peut
        # dépasser 300 sur une tablette récente — bien trop pour la taille
        # visuelle voulue). Metrics.density est le facteur qu'utilise déjà
        # tout le reste de l'app via dp() ; s'y aligner ici garde le texte
        # du graphique à une taille cohérente avec le reste de l'UI, quel
        # que soit l'appareil — voir
        # kivy_matplotlib_widget/uix/graph_widget.py::_onSize, qui
        # dimensionne la figure à partir de ce dpi.
        self.fig, self.ax1 = plt.subplots(dpi=100 * Metrics.density)

        # Axe secondaire (CPM)
        self.ax2 = self.ax1.twinx()

        # Style du graphique
        self.fig.patch.set_alpha(0.0) # Fond transparent
        self.ax1.set_facecolor("none") # Fond transparent
        self.ax1.margins(x=0, y=0) # Pas de marges autour des données
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

        # Ajuster le layout maintenant que les labels/légende existent — le
        # faire plus tôt (avant qu'ils ne soient posés) ne réservait pas de
        # place pour eux, ce qui coupait "Temps (s)" en bas du graphique.
        self.fig.tight_layout()

        # Ajouter la figure au widget
        self.ids.hr_graph_widget.figure = self.fig
        # Réajuste le layout à la taille réelle du widget une fois que Kivy
        # l'a posé (au premier appel, tight_layout ci-dessus tourne encore
        # sur la taille par défaut de matplotlib, pas celle de la Card).
        self.ids.hr_graph_widget.bind(size=self._on_graph_widget_resize)

    def _on_graph_widget_resize(self, *args):
        self.fig.tight_layout()
        self.fig.canvas.draw_idle()
    
    #==== CALLBACK =====#
    
    def on_hr_received(self, bpm):

        # UI label
        self.heart_rate_label = str(bpm)
        self._set_hr_signal_lost(False)
        if self.player_selected and self.session.hr_session.hrmax_percent_history:
            self.hrmax_percent_label = self._format_percent(
                self.session.hr_session.hrmax_percent_history[-1])

        # forcer la mise à jour du graphique avec la cible actuelle (la
        # dernière valeur connue, qui peut être un point de rampe de warmup
        # — voir SessionConfig.refresh_target_now)
        self.session.config.refresh_target_now()

        self.update_graph()

    def on_hr_sensor_status_changed(self, data):
        """Callback de la status bar : FC reçue récemment ou non"""
        self._set_hr_signal_lost(not data["connected"])

    def _set_hr_signal_lost(self, lost):
        # Signal "perdu" seulement si un capteur FC est censé émettre : pas
        # de capteur connecté (ou sans service FC) n'est pas une perte.
        ble = self.ble_manager
        lost = bool(lost and ble.is_connected and ble._has_heart_rate_service())
        self.hr_signal_lost = lost
        if lost:
            self.heart_rate_label = "--"
            self.hrmax_percent_label = "--"

    @staticmethod
    def _format_percent(value):
        """None si FCmax non calculable (âge inconnu) — voir HRSession._compute_percent"""
        return f"{int(round(value))}" if value is not None else "--"

    def on_cpm_received(self, value):

        # UI label
        self.cpm_label = str(int(value))

        self.update_graph()

    def on_toggle_game_state(self, active):
        """Afficher/masquer les bandes idle/paused sur le graphique"""
        self.show_game_state = active
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

        # supprimer anciennes bandes d'état inactif et redessiner à jour
        for artist in self.inactive_zone_artists:
            artist.remove()
        self.inactive_zone_artists = []

        inactive_segments = self.session.get_inactive_segments() if self.show_game_state else []
        seen_states = set()
        for start, end, state in inactive_segments:
            style = _INACTIVE_STATE_STYLES.get(state, _DEFAULT_INACTIVE_STYLE)
            self.inactive_zone_artists.append(
                self.ax1.axvspan(start, end, color=style["color"], alpha=0.15, linewidth=0, zorder=0)
            )
            seen_states.add(state)

        # Une entrée de légende par état réellement apparu dans la session,
        # dans un ordre stable (menu -> ready -> paused -> finished).
        ordered_states = [s for s in _INACTIVE_STATE_ORDER if s in seen_states]
        ordered_states += sorted(seen_states - set(_INACTIVE_STATE_ORDER))
        self.inactive_state_styles = [
            _INACTIVE_STATE_STYLES.get(s, _DEFAULT_INACTIVE_STYLE) for s in ordered_states
        ]

        if self.target_available and target_times and target_values:
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
        self.line_target.set_visible(self.target_available)

        # ligne %FCmax
        self.line_hr.set_data(hr_times, hrmax_percents)

        # ligne CPM : affichée dès que Unity a envoyé des cpm (partie lancée),
        # avec son axe de droite — rien à montrer avant.
        has_cpm = bool(cpm_values)
        self.line_cpm.set_data(cpm_times, cpm_values)
        self.line_cpm.set_visible(has_cpm)
        self.ax2.get_yaxis().set_visible(has_cpm)
        self.ax2.spines['right'].set_visible(has_cpm)

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

        for style in self.inactive_state_styles:
            lines.append(Patch(facecolor=style["color"], alpha=0.3))
            labels.append(style["label"])

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

        # Durée totale de la session configurée (Pilotage) plutôt que les
        # 10 minutes fixes par défaut — None tant qu'Unity ne l'a pas
        # encore envoyée (avant toute connexion), auquel cas on garde 600s.
        duration = self.session.config.session_duration or 600

        # MAJ UI
        self.ax1.set_xlim(game_start_time, game_start_time + duration)
        self.ax1.set_ylim(0, 100)

        # Redessiner graphe
        self.fig.canvas.draw_idle()
    
    def reset_graph(self):
        """
        Réinitialise la session en cours (voir GameSession.clear()) sans
        l'archiver — la mise en attente pour export se fait maintenant via
        le bouton dédié (voir queue_session_for_export).
        """
        self.session.clear()

        self.ax1.set_xlim(0, 600)
        self.ax1.set_ylim(0, 100)
        self.fig.canvas.draw_idle()

    def choose_export_folder(self):
        """
        Ouvre le sélecteur de dossier desktop (plyer). Sans effet sur
        Android — le bouton correspondant y est masqué (voir
        can_choose_export_folder).
        """
        pick_export_folder(self._on_export_folder_selected)

    def _on_export_folder_selected(self, selection):
        if not selection:
            return
        self.export_folder = selection[0]
        toast(f"Dossier d'export : {self.export_folder}")

    def queue_session_for_export(self):
        """
        Met la session en cours en attente d'export (voir
        GameSession.archive_current_session) sans la réinitialiser : le
        graphique continue d'afficher les données en cours.
        """
        record = self.session.archive_current_session()
        if record:
            self._add_session_row(record)
            toast("Session mise en attente d'export")
        else:
            toast("Aucune donnée à mettre en attente")

    def _finish_export(self, path):
        """
        Confirme l'export, et partage le fichier via la feuille de partage
        Android — sur Android le fichier est écrit dans le stockage
        applicatif, inaccessible autrement à l'utilisateur.
        """
        toast(f"Session exportée : {path}")
        if platform == "android":
            share_file_android(path)

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
        """
        Exporte une session en attente en CSV, selon les cases à cocher
        propres à CETTE ligne (row.include_*) — indépendantes des cases
        d'affichage du graphique. La ligne reste dans la liste ; suppression
        toujours manuelle via le bouton "Supprimer".
        """
        if row.record and not row.record.filename.lower().endswith(".csv"):
            row.record.filename += ".csv"
            if "filename_field" in row.ids:
                row.ids.filename_field.text = row.record.filename

        path = row.record.export_csv(
            folder=self.export_folder,
            include_target=row.include_target,
            include_cpm=row.include_cpm,
            include_state=row.include_state,
        )
        self._finish_export(path)
