from kivymd.uix.screen import MDScreen
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivymd.toast import toast
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.menu import MDDropdownMenu

from utils.event_bus import event_bus
from utils.logger import get_logger

logger = get_logger(__name__)

class PilotageScreen(MDScreen):
    """Écran de contrôle du jeu Unity"""

    # Modes de jeu (index envoyé/reçu via la clé SelectedModel)
    MODEL_ORDER = ["FIXE", "INCREMENTAL", "PID", "DRL"]
    MODEL_LABELS = {
        "FIXE": "Fixe",
        "INCREMENTAL": "Incrémental",
        "PID": "PID (adaptatif)",
        "DRL": "DRL (adaptatif)",
    }

    # Properties pour l'UI
    unity_connected = BooleanProperty(False) # connexion Unity
    selected_model = StringProperty("FIXE") # mode de jeu appliqué (confirmé)
    pending_model = StringProperty("FIXE") # mode sélectionné dans le menu (pas encore appliqué)
    session_duration_min = NumericProperty(10) # durée de session (min)
    obs_enabled = BooleanProperty(False) # obtacles
    obstacle_probability = NumericProperty(25) # % probabilité d'apparition
    left_hand_enabled = BooleanProperty(True) # main gauche
    right_hand_enabled = BooleanProperty(True) # main droite
    cube_per_min = NumericProperty(60) # cubes/min
    target_hr = NumericProperty(50)  # % FCmax
    incremental_steps = NumericProperty(10) # mode incrémental : nombre de paliers
    incremental_min_cpm = NumericProperty(30) # mode incrémental : cpm minimum
    incremental_max_cpm = NumericProperty(200) # mode incrémental : cpm maximum
    adaptive_min_cpm = NumericProperty(30) # modes PID/DRL : cpm minimum
    adaptive_max_cpm = NumericProperty(200) # modes PID/DRL : cpm maximum
    warmup_enabled = BooleanProperty(False) # modes PID/DRL : warmup
    warmup_duration = NumericProperty(90) # modes PID/DRL : durée du warmup (s)
    require_hr_signal = BooleanProperty(False) # modes Fixe/Incrémental : signal FC requis
    player_name = StringProperty("") # nom du profil joueur actif
    game_state = StringProperty("Menu") # état de partie reçu de Unity (Menu/Idle/Playing/Paused)

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

        # S'abonner pour écouter les eventbus
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.subscribe("session_updated", self.on_session_updated)

    def on_leave(self):
        event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.unsubscribe("session_updated", self.on_session_updated)
        self._close_model_menu()
        self._close_player_menu()

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
        if config_model not in self.MODEL_ORDER or config_model == self.selected_model:
            return

        if self.pending_model == self.selected_model:
            self.pending_model = config_model
        self.selected_model = config_model

    def on_session_updated(self, session):
         # Mise à jour UI
        self.player_name = session.user_profile.name
        self.game_state = session.game_state.capitalize()
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

        self.session.user_profile.name = profile["name"]
        self.session.user_profile.age = profile["age"]
        self.player_name = profile["name"]
        logger.info(f"👤 Profil joueur actif : {profile['name']}, {profile['age']} ans")

        if self.udp_controller:
            self.udp_controller.set_player_name(profile["name"])
            self.udp_controller.set_age_player(profile["age"])
            logger.info(f"📤 Profil joueur envoyé : {profile['name']}, {profile['age']} ans")

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
        """Sélection d'un mode dans le menu (pas encore envoyé à Unity)"""
        self.pending_model = model_name
        self._close_model_menu()

    def apply_model_change(self):
        """Bouton « Appliquer » : demande confirmation avant de changer de mode"""
        if self.pending_model == self.selected_model:
            return

        if not hasattr(self, "_dialog_confirm_model") or self._dialog_confirm_model is None:
            self._dialog_confirm_model = MDDialog(
                title="Redémarrer la session ?",
                text="Changer de mode de jeu va redémarrer la session en cours.",
                buttons=[
                    MDFlatButton(
                        text="ANNULER",
                        on_release=lambda *_: self._dialog_confirm_model.dismiss(),
                    ),
                    MDFlatButton(
                        text="CONFIRMER",
                        on_release=lambda *_: self._confirm_model_change(),
                    ),
                ],
            )
        self._dialog_confirm_model.open()

    def _confirm_model_change(self):
        """Envoie le mode sélectionné à Unity et redémarre la partie"""
        self._dialog_confirm_model.dismiss()

        index = self.MODEL_ORDER.index(self.pending_model)
        self.selected_model = self.pending_model
        self.session.config.model = self.pending_model
        logger.info(f"🎮 Mode de jeu: {self.pending_model}")

        if self.udp_controller:
            success = self.udp_controller.set_selected_model(index)
            if success:
                logger.info(f"📤 Mode de jeu envoyé: {self.pending_model} (index {index})")

            # Redémarre le jeu pour que le nouveau mode soit pris en compte
            self.restart_game()

    # ========== DURÉE DE SESSION ==========

    def on_session_duration_change(self, value):
        """Slider durée de session changé"""
        self.session_duration_min = value

    def on_session_duration_touch_up(self):
        """Appelé quand l'utilisateur relâche le slider"""
        logger.debug(f"🎯 Slider relâché à {self.session_duration_min} min")

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
                                "cube_per_min", 15, 200, "set_cube_rate",
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

    def on_warmup_toggle(self, is_active):
        """Active/désactive le warmup (modes PID/DRL)"""
        self.warmup_enabled = is_active
        self.session.config.warmup_enabled = is_active
        logger.info(f"🔥 Warmup: {'ON' if is_active else 'OFF'}")

        if self.udp_controller:
            self.udp_controller.set_warmup_enabled(is_active)

    def on_warmup_duration_submit(self, text):
        """Champ durée de warmup validé"""
        self._submit_int_field(text, "warmup_duration_field", "warmup_duration",
                                "warmup_duration", 0, None, "set_warmup_duration",
                                "Durée warmup")

    def on_require_hr_signal_toggle(self, is_active):
        """Active/désactive l'exigence du signal FC (modes Fixe/Incrémental)"""
        self.require_hr_signal = is_active
        self.session.config.require_hr_signal = is_active
        logger.info(f"❤️ Signal FC requis: {'ON' if is_active else 'OFF'}")

        if self.udp_controller:
            self.udp_controller.set_require_hr_signal(is_active)

    # ========== GAME ACTIONS ==========

    def pause_game(self):
        """Met le jeu en pause"""
        if self.udp_controller:
            success = self.udp_controller.pause_game()
            if success:
                logger.info("⏸️ Jeu en pause")
            else:
                toast("❌ Échec de la mise en pause")

    def resume_game(self):
        """Reprend le jeu"""
        if self.udp_controller:
            success = self.udp_controller.resume_game()
            if success:
                logger.info("▶️ Jeu repris")
            else:
                toast("❌ Échec de la reprise")

    def restart_game(self):
        """Redémarre le jeu"""
        if self.udp_controller:
            success = self.udp_controller.restart_game()
            if success:
                logger.info("🔄 Jeu redémarré")
            else:
                toast("❌ Échec du redémarrage")
