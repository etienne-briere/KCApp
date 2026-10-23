from kivymd.uix.screen import MDScreen
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivymd.toast import toast
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.menu import MDDropdownMenu

from app.controllers.game_actions import GameActionsController
from utils.event_bus import event_bus
from utils.logger import get_logger

logger = get_logger(__name__)

class PilotageScreen(MDScreen):
    """Écran de contrôle du jeu Unity"""

    # Modes de jeu (index envoyé/reçu via la clé SelectedModel).
    # DRL_RUN3 n'est pas un index Unity : c'est le mode DRL (index 3) avec le
    # modèle Run 3 du contrôleur hybride (clé controllerSetup).
    MODEL_ORDER = ["FIXE", "INCREMENTAL", "PID", "DRL", "DRL_RUN3"]
    MODEL_INDEX = {"FIXE": 0, "INCREMENTAL": 1, "PID": 2, "DRL": 3, "DRL_RUN3": 3}
    DRL_MODES = ("DRL", "DRL_RUN3")
    MODEL_LABELS = {
        "FIXE": "Fixe",
        "INCREMENTAL": "Incrémental",
        "PID": "PID (adaptatif)",
        "DRL": "DRL (adaptatif)",
        "DRL_RUN3": "DRL Run 3 (adaptatif)",
    }

    # Environnements du jeu (valeurs de la clé environment, envoyées/reçues telles quelles)
    ENVIRONMENT_ORDER = ["Cosmos", "Forest", "Sea", "Mountain", "Sky"]
    ENVIRONMENT_LABELS = {
        "Cosmos": "Cosmos",
        "Forest": "Forêt",
        "Sea": "Mer",
        "Mountain": "Montagne",
        "Sky": "Ciel",
    }

    # Properties pour l'UI
    unity_connected = BooleanProperty(False) # connexion Unity
    selected_model = StringProperty("FIXE") # mode de jeu appliqué (confirmé)
    pending_model = StringProperty("FIXE") # mode sélectionné dans le menu (appliqué tout de suite, sauf confirmation de redémarrage en attente)
    session_duration_min = NumericProperty(10) # durée de session (min)
    obs_enabled = BooleanProperty(False) # obtacles
    obstacle_probability = NumericProperty(25) # % probabilité d'apparition
    left_hand_enabled = BooleanProperty(True) # main gauche
    right_hand_enabled = BooleanProperty(True) # main droite
    cube_per_min = NumericProperty(60) # cubes/min
    target_hr = NumericProperty(50)  # % FCmax
    incremental_steps = NumericProperty(10) # mode incrémental : nombre de paliers
    incremental_min_cpm = NumericProperty(10) # mode incrémental : cpm minimum
    incremental_max_cpm = NumericProperty(200) # mode incrémental : cpm maximum
    adaptive_min_cpm = NumericProperty(10) # modes PID/DRL : cpm minimum
    adaptive_max_cpm = NumericProperty(200) # modes PID/DRL : cpm maximum
    warmup_enabled = BooleanProperty(False) # modes PID/DRL : warmup
    warmup_duration = NumericProperty(90) # modes PID/DRL : durée du warmup (s)
    require_hr_signal = BooleanProperty(False) # modes Fixe/Incrémental : signal FC requis
    brick_speed = NumericProperty(8) # vitesse des briques (tous modes)
    pid_warmup = BooleanProperty(False) # mode DRL : PID pendant l'échauffement (prochaine partie)
    pid_backup = BooleanProperty(False) # mode DRL : PID de secours si cycle limite (prochaine partie)
    player_name = StringProperty("") # nom du profil joueur actif
    environment = StringProperty("") # environnement du jeu (Cosmos/Forest/Sea/Mountain/Sky), vide si inconnu
    game_state = StringProperty("Menu") # état de partie reçu de Unity (Menu/Ready/Playing/Paused/Finished)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Pour redémarrer la partie après un changement de mode confirmé
        # (voir _apply_model_change) — même mécanisme que QuickActionsBar
        # (ui/widgets/quick_actions_bar.py), avec sa propre instance
        # puisque PilotageScreen n'a plus de spinner/toast propre à piloter.
        self._game_actions = GameActionsController()

    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        app = App.get_running_app()

        # Managers
        self.udp_controller = app.udp_controller
        self.udp_discovery = app.udp_discovery
        self.hr_session = app.hr_session
        self.session = app.session
        self.player_store = app.player_store

        self.player_name = self.session.user_profile.name
        self.game_state = self.session.game_state.capitalize()
        self.environment = self.session.config.environment or ""

        # Vérifier la connexion Unity (au cas où on arrive dans l'écran après la connexion)
        self.unity_connected = self.udp_discovery.is_unity_connected()
        if self.unity_connected:
            if self.session.config.target_hr_percent is not None:
                self.target_hr = self.session.config.target_hr_percent
            if self.session.config.obs_enabled is not None:
                self.obs_enabled = self.session.config.obs_enabled
            if self.session.config.obstacle_probability is not None:
                self.obstacle_probability = self.session.config.obstacle_probability
            if self.session.config.left_hand_enabled is not None:
                self.left_hand_enabled = self.session.config.left_hand_enabled
            if self.session.config.right_hand_enabled is not None:
                self.right_hand_enabled = self.session.config.right_hand_enabled
            if self.session.config.cube_per_min is not None:
                self.cube_per_min = self.session.config.cube_per_min
            if self.session.config.session_duration is not None:
                self.session_duration_min = round(self.session.config.session_duration / 60)
            self._sync_model_from_config(self.session.config.model)
            if self.session.config.incremental_steps is not None:
                self.incremental_steps = self.session.config.incremental_steps
            if self.session.config.incremental_min_cpm is not None:
                self.incremental_min_cpm = self.session.config.incremental_min_cpm
            if self.session.config.incremental_max_cpm is not None:
                self.incremental_max_cpm = self.session.config.incremental_max_cpm
            if self.session.config.adaptive_min_cpm is not None:
                self.adaptive_min_cpm = self.session.config.adaptive_min_cpm
            if self.session.config.adaptive_max_cpm is not None:
                self.adaptive_max_cpm = self.session.config.adaptive_max_cpm
            if self.session.config.warmup_enabled is not None:
                self.warmup_enabled = self.session.config.warmup_enabled
            if self.session.config.warmup_duration is not None:
                self.warmup_duration = self.session.config.warmup_duration
            if self.session.config.require_hr_signal is not None:
                self.require_hr_signal = self.session.config.require_hr_signal
            if self.session.config.brick_speed is not None:
                self.brick_speed = self.session.config.brick_speed
            self._sync_controller_from_config(self.session.config)

        # S'abonner pour écouter les eventbus
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.subscribe("session_updated", self.on_session_updated)

    def on_leave(self):
        event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.unsubscribe("session_updated", self.on_session_updated)
        self._close_model_menu()
        self._close_player_menu()
        self._close_environment_menu()

    # ========== CALLBACKS ==========

    def handle_unity_connection(self, data):
        connected = data["connected"]
        self.unity_connected = connected

    def _sync_model_from_config(self, config_model):
        """
        Resynchronise le mode de jeu depuis session.config, sans écraser une
        sélection locale non confirmée dans le menu déroulant (pending_model
        != selected_model) — sinon un message UDP quelconque (ex: cpm, très
        fréquent en jeu) redéclenche session_updated et fait revenir le menu
        à l'ancien mode avant même que l'utilisateur ait pu cliquer Appliquer.
        """
        # Mode DRL avec le modèle Run 3 (contrôleur hybride) : affiché comme "DRL Run 3"
        if config_model == "DRL" and self.session.config.is_drl_run3:
            config_model = "DRL_RUN3"

        if config_model not in self.MODEL_ORDER or config_model == self.selected_model:
            return

        if self.pending_model == self.selected_model:
            self.pending_model = config_model
        self.selected_model = config_model

    def on_session_updated(self, session):
         # Mise à jour UI
        self.player_name = session.user_profile.name
        self.game_state = session.game_state.capitalize()
        if session.config.environment is not None:
            self.environment = session.config.environment
        if session.config.target_hr_percent is not None:
            self.target_hr = session.config.target_hr_percent
        if session.config.obs_enabled is not None:
            self.obs_enabled = session.config.obs_enabled
        if session.config.obstacle_probability is not None:
            self.obstacle_probability = session.config.obstacle_probability
        if session.config.left_hand_enabled is not None:
            self.left_hand_enabled = session.config.left_hand_enabled
        if session.config.right_hand_enabled is not None:
            self.right_hand_enabled = session.config.right_hand_enabled
        if session.config.cube_per_min is not None:
            self.cube_per_min = session.config.cube_per_min
        if session.config.session_duration is not None:
            self.session_duration_min = round(session.config.session_duration / 60)
        self._sync_model_from_config(session.config.model)
        if session.config.incremental_steps is not None:
            self.incremental_steps = session.config.incremental_steps
        if session.config.incremental_min_cpm is not None:
            self.incremental_min_cpm = session.config.incremental_min_cpm
        if session.config.incremental_max_cpm is not None:
            self.incremental_max_cpm = session.config.incremental_max_cpm
        if session.config.adaptive_min_cpm is not None:
            self.adaptive_min_cpm = session.config.adaptive_min_cpm
        if session.config.adaptive_max_cpm is not None:
            self.adaptive_max_cpm = session.config.adaptive_max_cpm
        if session.config.warmup_enabled is not None:
            self.warmup_enabled = session.config.warmup_enabled
        if session.config.warmup_duration is not None:
            self.warmup_duration = session.config.warmup_duration
        if session.config.require_hr_signal is not None:
            self.require_hr_signal = session.config.require_hr_signal
        if session.config.brick_speed is not None:
            self.brick_speed = session.config.brick_speed
        self._sync_controller_from_config(session.config)

    def _sync_controller_from_config(self, config):
        """Cases PID d'échauffement (prochain lancement) / de secours (applicable en cours de partie)"""
        # Comme pour le mode de jeu : ne pas écraser un choix local pas encore appliqué
        if config.controller_config is not None and self.pending_model == self.selected_model:
            self.pid_warmup = config.effective_pid_warmup
            self.pid_backup = config.effective_pid_backup

    def _submit_int_field(self, text, field_id, prop_name, config_attr,
                           min_value, max_value, controller_method_name, label):
        """Validation générique d'un champ numérique (paliers, cpm min/max, probabilité...)"""
        try:
            value = int(text)
        except ValueError:
            toast("Valeur invalide")
            self.ids[field_id].text = str(int(getattr(self, prop_name)))
            return

        value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)

        setattr(self, prop_name, value)
        self.ids[field_id].text = str(value)
        setattr(self.session.config, config_attr, value)
        logger.info(f"🔧 {label}: {value}")

        if self.udp_controller:
            send_fn = getattr(self.udp_controller, controller_method_name)
            success = send_fn(value)
            if success:
                logger.info(f"📤 {label} envoyé: {value}")

    # ========== PROFIL DU JOUEUR ==========

    def open_player_menu(self, caller):
        """Ouvre le menu déroulant de sélection du profil joueur"""
        self._close_player_menu()

        names = self.player_store.names()
        if not names:
            toast("Aucun profil enregistré")
            return

        items = [
            {
                "text": name,
                "on_release": lambda name=name: self.on_player_select(name),
            }
            for name in names
        ]
        self._player_menu = MDDropdownMenu(caller=caller, items=items, width_mult=4)
        # Voir open_model_menu : retrait immédiat pour éviter les zones
        # mortes de clic laissées par l'animation de dismiss par défaut.
        self._player_menu.bind(on_dismiss=lambda *_: self._close_player_menu())
        self._player_menu.open()

    def _close_player_menu(self):
        menu = getattr(self, "_player_menu", None)
        if menu is not None:
            self._player_menu = None
            Clock.schedule_once(lambda dt: Window.remove_widget(menu), 0)

    def on_player_select(self, name):
        """Sélection d'un profil dans le menu : devient le profil actif de la session"""
        self._close_player_menu()
        profile = self.player_store.get(name)
        if not profile:
            return

        self.session.user_profile.set_name_locally(profile["name"])
        self.session.user_profile.set_age_locally(profile["age"])
        weight = self.player_store.weight_of(profile)
        sex = self.player_store.sex_of(profile)
        self.session.user_profile.set_weight_locally(weight)
        self.session.user_profile.set_sex_locally(sex)
        self.player_name = profile["name"]
        logger.info(f"👤 Profil joueur actif : {profile['name']}, {profile['age']} ans")

        if self.udp_controller:
            self.udp_controller.set_player_name(profile["name"])
            self.udp_controller.set_age_player(profile["age"])
            self.udp_controller.set_weight_player(weight)
            self.udp_controller.set_sex_player(sex)
            logger.info(f"📤 Profil joueur envoyé : {profile['name']}, {profile['age']} ans")

        # user_profile n'est pas une Kivy Property : sans cet évènement,
        # les autres écrans (Home, Tracking) ne rafraîchissent leur âge
        # affiché qu'au prochain message UDP reçu de Unity, pas
        # immédiatement — et pas du tout si Unity est déconnecté.
        event_bus.emit("session_updated", self.session)

    # ========== ENVIRONNEMENT ==========

    def open_environment_menu(self, caller):
        """Ouvre le menu déroulant de sélection de l'environnement"""
        self._close_environment_menu()

        items = [
            {
                "text": self.ENVIRONMENT_LABELS[name],
                "on_release": lambda name=name: self.on_environment_select(name),
            }
            for name in self.ENVIRONMENT_ORDER
        ]
        self._environment_menu = MDDropdownMenu(caller=caller, items=items, width_mult=4)
        # Voir open_model_menu : retrait immédiat pour éviter les zones
        # mortes de clic laissées par l'animation de dismiss par défaut.
        self._environment_menu.bind(on_dismiss=lambda *_: self._close_environment_menu())
        self._environment_menu.open()

    def _close_environment_menu(self):
        menu = getattr(self, "_environment_menu", None)
        if menu is not None:
            self._environment_menu = None
            Clock.schedule_once(lambda dt: Window.remove_widget(menu), 0)

    def on_environment_select(self, name):
        """Sélection d'un environnement : envoyé immédiatement à Unity (menu du jeu uniquement)"""
        self._close_environment_menu()
        if self.game_state != "Menu":
            toast("Changement d'environnement disponible uniquement dans le menu du jeu")
            return
        if name == self.environment:
            return

        self.environment = name
        self.session.config.environment = name
        logger.info(f"🌄 Environnement : {name}")

        if self.udp_controller:
            success = self.udp_controller.set_environment(name)
            if success:
                logger.info(f"📤 Environnement envoyé : {name}")

    # ========== MODE DE JEU ==========

    def open_model_menu(self, caller):
        """Ouvre le menu déroulant de sélection du mode de jeu"""
        self._close_model_menu()

        items = [
            {
                "text": self.MODEL_LABELS[name],
                "on_release": lambda name=name: self.on_model_select(name),
            }
            for name in self.MODEL_ORDER
        ]
        self._model_menu = MDDropdownMenu(caller=caller, items=items, width_mult=4)
        # Par défaut, un clic en dehors du menu (dismiss) déclenche une
        # animation de réduction avant de retirer le widget de la Window
        # (cf. MotionDropDownMenuBehavior.on_dismiss dans KivyMD). Pendant
        # toute cette animation, le widget reste attaché à la Window et son
        # on_touch_down intercepte TOUS les clics de l'écran, provoquant des
        # zones mortes de clic tant qu'elle n'est pas terminée. On force donc
        # un retrait immédiat (sans animation) dès que le menu est fermé de
        # cette façon.
        self._model_menu.bind(on_dismiss=lambda *_: self._close_model_menu())
        self._model_menu.open()

    def _close_model_menu(self):
        """
        Retire le menu de la fenêtre, sans passer par l'animation de
        dismiss() (dont le callback de nettoyage ne se déclenche pas
        toujours dans cette version de KivyMD, laissant un widget invisible
        qui intercepte indéfiniment les clics sur cet écran).

        Le retrait est différé à la prochaine frame (Clock.schedule_once) :
        appeler Window.remove_widget() de façon synchrone, alors qu'on est
        encore au milieu du dispatch tactile de l'item de menu qui vient
        d'être cliqué, laisse le système tactile de Kivy dans un état
        incohérent et bloque le clic suivant sur l'écran.
        """
        menu = getattr(self, "_model_menu", None)
        if menu is not None:
            self._model_menu = None
            Clock.schedule_once(lambda dt: Window.remove_widget(menu), 0)

    def on_model_select(self, model_name):
        """
        Sélection d'un mode dans le menu : appliqué tout de suite — sauf si
        une partie est Playing/Paused, où une confirmation est demandée
        d'abord puisque ça va la redémarrer (voir _apply_or_confirm_model_change).
        """
        self.pending_model = model_name
        self._close_model_menu()
        self._apply_or_confirm_model_change()

    def _apply_or_confirm_model_change(self):
        if self.pending_model == self.selected_model:
            return

        if self.game_state not in ("Playing", "Paused"):
            self._apply_model_change(restart=False)
            return

        self._confirm_restart(
            "Changer de mode de jeu va redémarrer la session en cours.",
            on_confirm=lambda: self._apply_model_change(restart=True),
            on_cancel=lambda: setattr(self, "pending_model", self.selected_model),
        )

    def _confirm_restart(self, text, on_confirm, on_cancel=None):
        """
        Dialogue de confirmation partagé par tous les réglages qui
        redémarrent la partie en cours (mode de jeu, warmup, PID
        d'échauffement) : annule en rappelant on_cancel (en général pour
        remettre l'UI dans son état précédent), confirme en rappelant
        on_confirm (qui applique le réglage et redémarre).
        """
        def _confirm(*_):
            dialog.dismiss()
            on_confirm()

        def _cancel(*_):
            dialog.dismiss()
            if on_cancel:
                on_cancel()

        dialog = MDDialog(
            title="Redémarrer la session ?",
            text=text,
            buttons=[
                MDFlatButton(text="ANNULER", on_release=_cancel),
                MDFlatButton(text="CONFIRMER", on_release=_confirm),
            ],
        )
        dialog.open()

    def _apply_model_change(self, restart):
        """Envoie le mode sélectionné (+ réglages du contrôleur hybride) à Unity"""
        index = self.MODEL_INDEX[self.pending_model]
        self.selected_model = self.pending_model
        # session.config.model garde le nom Unity (DRL), le modèle Run 3 passe par controllerSetup
        self.session.config.model = "DRL" if self.pending_model in self.DRL_MODES else self.pending_model
        logger.info(f"🎮 Mode de jeu: {self.pending_model}")

        if self.udp_controller:
            success = self.udp_controller.set_selected_model(index)
            if success:
                logger.info(f"📤 Mode de jeu envoyé: {self.pending_model} (index {index})")

            # Modes DRL : modèle (actuel / Run 3) + PID d'échauffement + PID de secours
            if self.pending_model in self.DRL_MODES:
                self._send_controller_setup(self.pending_model)

            # Redémarre le jeu seulement si une partie était effectivement en cours
            if restart:
                self._game_actions.restart_game()

    # ========== DURÉE DE SESSION ==========

    def on_session_duration_submit(self, text):
        """Champ durée de session (min) validé"""
        try:
            value = int(text)
        except ValueError:
            toast("Valeur invalide")
            self.ids.session_duration_field.text = str(int(self.session_duration_min))
            return

        value = max(1, min(20, value))
        self.session_duration_min = value
        self.ids.session_duration_field.text = str(value)
        self.send_session_duration()

    def send_session_duration(self):
        """Envoie la durée de session (en secondes) à Unity"""
        duration_seconds = int(self.session_duration_min) * 60
        self.session.config.session_duration = duration_seconds

        if self.udp_controller:
            success = self.udp_controller.set_session_duration(duration_seconds)
            if success:
                logger.info(f"📤 Durée de session envoyée: {duration_seconds}s")

    # ========== OBSTACLES ==========

    def on_obstacles_toggle(self, is_active):
        """Toggle obstacles ON/OFF"""
        self.obs_enabled = is_active
        self.session.config.obs_enabled = is_active
        logger.info(f"🎮 Obstacles: {'ON' if is_active else 'OFF'}")

        # Envoyer via UDP
        if self.udp_controller:
            self.udp_controller.set_obstacle("1" if is_active else "0")

    def on_obstacle_probability_submit(self, text):
        """Champ probabilité obstacles validé (Entrée ou perte de focus)"""
        self._submit_int_field(text, "obstacle_probability_field", "obstacle_probability",
                                "obstacle_probability", 0, 100, "set_obstacle_probability",
                                "Probabilité obstacles")

    # ========== MAINS ==========

    def on_left_hand_toggle(self, is_active):
        """Active/désactive l'interaction avec la main gauche"""
        if not is_active and not self.right_hand_enabled:
            # Au moins une main doit rester active
            toast("Au moins une main doit être active")
            self.ids.left_hand_checkbox.active = True
            return

        self.left_hand_enabled = is_active
        self.session.config.left_hand_enabled = is_active
        logger.info(f"🖐️ Main gauche: {'ON' if is_active else 'OFF'}")

        if self.udp_controller:
            self.udp_controller.set_left_hand(is_active)

    def on_right_hand_toggle(self, is_active):
        """Active/désactive l'interaction avec la main droite"""
        if not is_active and not self.left_hand_enabled:
            # Au moins une main doit rester active
            toast("Au moins une main doit être active")
            self.ids.right_hand_checkbox.active = True
            return

        self.right_hand_enabled = is_active
        self.session.config.right_hand_enabled = is_active
        logger.info(f"🖐️ Main droite: {'ON' if is_active else 'OFF'}")

        if self.udp_controller:
            self.udp_controller.set_right_hand(is_active)

    # ========== CUBE FREQUENCY ==========

    def on_cube_frequency_submit(self, text):
        """Champ cubes par minute validé"""
        self._submit_int_field(text, "cube_frequency_field", "cube_per_min",
                                "cube_per_min", 10, 200, "set_cube_rate",
                                "Cubes par minute")

    # ========== MODE INCRÉMENTAL ==========

    def on_incremental_steps_submit(self, text):
        """Champ paliers incrémental validé"""
        self._submit_int_field(text, "incremental_steps_field", "incremental_steps",
                                "incremental_steps", 1, None, "set_incremental_steps",
                                "Paliers incrémental")

    def on_incremental_min_cpm_submit(self, text):
        """Champ cpm minimum incrémental validé"""
        self._submit_int_field(text, "incremental_min_cpm_field", "incremental_min_cpm",
                                "incremental_min_cpm", 0, None, "set_incremental_min_cpm",
                                "Cpm min incrémental")

    def on_incremental_max_cpm_submit(self, text):
        """Champ cpm maximum incrémental validé"""
        self._submit_int_field(text, "incremental_max_cpm_field", "incremental_max_cpm",
                                "incremental_max_cpm", 0, None, "set_incremental_max_cpm",
                                "Cpm max incrémental")

    # ========== TARGET HR ==========

    def on_target_hr_submit(self, text):
        """Champ FC cible validé"""
        try:
            value = int(text)
        except ValueError:
            toast("Valeur invalide")
            self.ids.target_hr_field.text = str(int(self.target_hr))
            return

        value = max(10, min(100, value))
        self.target_hr = value
        self.ids.target_hr_field.text = str(value)
        self.session.config.update_target(value)
        logger.info(f"🎯 FC cible: {value}%")

        self.send_target_hr()

    def send_target_hr(self):
        """Envoie la FC cible à Unity"""
        if self.udp_controller:
            success = self.udp_controller.set_target_hr(self.target_hr)
            if success:
                logger.info(f"📤 Target HR envoyée: {self.target_hr}%")

    # ========== MODE ADAPTATIF (PID / DRL) ==========

    def on_adaptive_min_cpm_submit(self, text):
        """Champ cpm minimum adaptatif validé"""
        self._submit_int_field(text, "adaptive_min_cpm_field", "adaptive_min_cpm",
                                "adaptive_min_cpm", 0, None, "set_adaptive_min_cpm",
                                "Cpm min adaptatif")

    def on_adaptive_max_cpm_submit(self, text):
        """Champ cpm maximum adaptatif validé"""
        self._submit_int_field(text, "adaptive_max_cpm_field", "adaptive_max_cpm",
                                "adaptive_max_cpm", 0, None, "set_adaptive_max_cpm",
                                "Cpm max adaptatif")

    def _apply_warmup_enabled(self, is_active):
        """Applique directement warmup_enabled (voir on_warmup_mode_select pour la confirmation de redémarrage)"""
        self.warmup_enabled = is_active
        self.session.config.warmup_enabled = is_active
        logger.info(f"🔥 Warmup: {'ON' if is_active else 'OFF'}")
        if self.udp_controller:
            self.udp_controller.set_warmup_enabled(is_active)

    def _apply_pid_warmup(self, is_active):
        """Applique directement pid_warmup (voir on_warmup_mode_select pour la confirmation de redémarrage)"""
        self.pid_warmup = is_active
        self._on_controller_option_changed()

    def on_warmup_mode_select(self, mode):
        """
        Sélecteur "Échauffement" ("none"/"pid"/"drl" : Card dédiée, Aucun/
        PID/DRL en modes DRL, Aucun/PID seulement en mode PID pur) : regroupe
        warmup_enabled et pid_warmup en un seul choix, pour éviter les
        combinaisons invalides (ex. PID d'échauffement actif sans rampe).
        pid_warmup n'a de sens qu'en mode DRL (voir effective_pid_warmup) :
        en mode PID pur, le choix "PID" ne touche que warmup_enabled.

        Ne prend effet qu'au prochain lancement : un seul dialogue de
        confirmation et un seul redémarrage, même si les deux réglages
        changent à la fois.
        """
        target_enabled = mode != "none"
        if self.pending_model in self.DRL_MODES:
            target_pid = mode == "pid"
        else:
            target_pid = self.pid_warmup

        enabled_changes = target_enabled != self.warmup_enabled
        pid_changes = target_pid != self.pid_warmup
        if not enabled_changes and not pid_changes:
            return

        def _apply():
            if enabled_changes:
                self._apply_warmup_enabled(target_enabled)
            if pid_changes:
                self._apply_pid_warmup(target_pid)

        if self.game_state not in ("Playing", "Paused"):
            _apply()
            return

        def _on_confirm():
            _apply()
            self._game_actions.restart_game()

        self._confirm_restart(
            "Ce réglage ne prend effet qu'au prochain lancement : redémarrer la partie maintenant ?",
            on_confirm=_on_confirm,
        )

    def on_warmup_duration_submit(self, text):
        """
        Champ durée de warmup validé : ne prend effet qu'au prochain
        lancement, donc redémarre la partie (avec confirmation) si elle est
        Playing/Paused ; sinon applique directement.
        """
        try:
            value = int(text)
        except ValueError:
            toast("Valeur invalide")
            self.ids.warmup_duration_field.text = str(int(self.warmup_duration))
            return

        value = max(0, value)
        self.ids.warmup_duration_field.text = str(value)
        if value == self.warmup_duration:
            return

        # Un Entrée déclenche à la fois on_text_validate et la perte de
        # focus qui suit (voir pilotage_screen.kv) : les deux rappellent
        # cette méthode avec le même texte avant que le dialogue ne soit
        # confirmé/annulé (donc avant que self.warmup_duration ne change) —
        # sans ce garde-fou, ça ouvrirait le dialogue deux fois.
        if getattr(self, "_warmup_duration_pending", None) == value:
            return
        self._warmup_duration_pending = value
        previous = self.warmup_duration

        def _apply():
            self._warmup_duration_pending = None
            self.warmup_duration = value
            self.session.config.warmup_duration = value
            logger.info(f"🔧 Durée warmup: {value}")
            if self.udp_controller and self.udp_controller.set_warmup_duration(value):
                logger.info(f"📤 Durée warmup envoyé: {value}")

        if self.game_state not in ("Playing", "Paused"):
            _apply()
            return

        def _on_confirm():
            _apply()
            self._game_actions.restart_game()

        def _on_cancel():
            self._warmup_duration_pending = None
            self.ids.warmup_duration_field.text = str(previous)

        self._confirm_restart(
            "Ce réglage ne prend effet qu'au prochain lancement : redémarrer la partie maintenant ?",
            on_confirm=_on_confirm,
            on_cancel=_on_cancel,
        )

    def on_require_hr_signal_toggle(self, is_active):
        """Active/désactive l'exigence du signal FC (modes Fixe/Incrémental)"""
        self.require_hr_signal = is_active
        self.session.config.require_hr_signal = is_active
        logger.info(f"❤️ Signal FC requis: {'ON' if is_active else 'OFF'}")

        if self.udp_controller:
            self.udp_controller.set_require_hr_signal(is_active)

    # ========== CONTRÔLEUR HYBRIDE : RÉGLAGES (prochaine partie) ==========

    def _send_controller_setup(self, model_name):
        """Envoie modèle DRL + PID d'échauffement + PID de secours (pris en compte au prochain lancement)"""
        drl_model = "run3" if model_name == "DRL_RUN3" else "deployed"
        if self.udp_controller and self.udp_controller.set_controller_setup(drl_model, self.pid_warmup, self.pid_backup):
            logger.info(f"📤 Contrôleur : {drl_model}, PID échauffement={self.pid_warmup}, PID secours={self.pid_backup}")
        self._mirror_controller_config(drl_model, self.pid_warmup, self.pid_backup)

    def _mirror_controller_config(self, drl_model, pid_warmup, pid_backup):
        """Miroir local de la traduction faite par Unity (HybridControllerPrefs.ApplyMenuChoice)"""
        cfg = self.session.config
        if drl_model == "deployed" and not pid_warmup and not pid_backup:
            cfg.controller_config = "off"
        elif drl_model == "run3" and not pid_backup:
            cfg.controller_config = "drl_run3" if pid_warmup else "drl_run3_no_warmup"
        else:
            cfg.controller_config = "custom"
        cfg.drl_model = drl_model
        cfg.pid_warmup = pid_warmup
        cfg.pid_backup = pid_backup

    def _on_controller_option_changed(self):
        # Envoi immédiat seulement si le mode DRL est déjà appliqué ; sinon il
        # part avec le prochain lancement (voir _apply_model_change).
        if self.selected_model in self.DRL_MODES and self.pending_model == self.selected_model:
            self._send_controller_setup(self.selected_model)

    def on_pid_backup_toggle(self, is_active):
        """
        Case PID de secours (modes DRL) : si une partie est déjà en cours
        (Playing), envoie directement backupPid (appliqué en direct côté
        Unity) plutôt que de repartir avec tout controllerSetup (qui ne
        prendrait effet qu'au prochain lancement/redémarrage) ; sinon
        repart avec le reste du contrôleur via controllerSetup comme
        d'habitude.
        """
        if is_active == self.pid_backup:
            return
        self.pid_backup = is_active

        if self.game_state == "Playing":
            cfg = self.session.config
            if self.udp_controller and self.udp_controller.set_pid_backup(is_active):
                logger.info(f"📤 PID de secours (direct) : {'ON' if is_active else 'OFF'}")
            self._mirror_controller_config(cfg.drl_model, self.pid_warmup, is_active)
        else:
            self._on_controller_option_changed()

    # ========== VITESSE DES BRIQUES ==========

    def on_brick_speed_submit(self, text):
        """Champ vitesse des briques validé"""
        self._submit_int_field(text, "brick_speed_field", "brick_speed",
                                "brick_speed", 1, None, "set_brick_speed",
                                "Vitesse des briques")

