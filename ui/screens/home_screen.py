import asyncio

from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.app import App
from utils.logger import get_logger
from kivy.clock import Clock
from kivy.clock import mainthread
from utils.event_bus import event_bus
from kivymd.toast import toast
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton

from app.network.connectivity import is_wifi_enabled, get_wifi_ssid


logger = get_logger(__name__)

class HomeScreen(MDScreen):
    """Écran d'accueil"""

    unity_connected = BooleanProperty(False)
    wifi_connected = BooleanProperty(False)
    wifi_ssid = StringProperty("")
    hr_sensor_connected = BooleanProperty(False)
    hr_data_sent = BooleanProperty(False)
    selected_model = StringProperty("Unknown")
    hr_target = StringProperty("Unknown")
    age_user = StringProperty("Unknown")

    # Casque VR (préparation avant séance)
    casque_ip = StringProperty("")
    casque_connecte = BooleanProperty(False)
    casque_en_cours = BooleanProperty(False)
    casque_statut = StringProperty("Casque non connecté")
    # Limite de zone (Guardian) : active par défaut. Les patients sont amenés
    # à être debout pendant la séance et doivent être alertés (grille) s'ils
    # sortent de la zone tracée, pour éviter de percuter un objet. À
    # désactiver seulement en connaissance de cause (voir quest_control/
    # quest.py, limite_definir).
    casque_limite_active = BooleanProperty(True)

    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        app = App.get_running_app()

        # Managers
        self.udp_discovery = app.udp_discovery
        self.udp_controller = app.udp_controller
        self.session = app.session
        self.quest_client = app.quest_client

        # Vérifier la connexion Unity (au cas où on arrive dans l'écran après la connexion)
        self.unity_connected = self.udp_discovery.is_unity_connected()

        # Refléter l'état Wi-Fi courant (mis à jour ensuite via l'event bus)
        self.wifi_connected = is_wifi_enabled()
        self.wifi_ssid = (get_wifi_ssid() or "") if self.wifi_connected else ""

        # Refléter l'état FC courant : StatusBar tourne en permanence (quel
        # que soit l'écran affiché) et est la seule source à connaître le
        # délai depuis la dernière trame FC reçue — on se resynchronise sur
        # elle ici, sinon la bannière resterait figée sur sa dernière valeur
        # si le capteur s'est (dé)connecté pendant qu'on était sur un autre
        # écran (ex. Sensor, où se fait l'appairage BLE).
        # `app.root` n'existe pas encore au tout premier `on_enter` (déclenché
        # pendant la construction du kv, avant l'affectation de app.root) —
        # sans conséquence puisqu'à ce stade le capteur n'est de toute façon
        # pas connecté.
        if app.root:
            status_bar = app.root.ids.status_bar
            self.hr_sensor_connected = status_bar.hr_sensor_connected
            self.hr_data_sent = status_bar.hr_data_sent
        if self.unity_connected :
            self.selected_model = self.session.config.model
            self.age_user = str(self.session.user_profile.age)
            self.hr_target = f"{self.session.config.target_hr_percent} %"

        # Re-refléter l'état du casque si on revient sur l'écran après coup
        self.casque_connecte = self.quest_client.connecte
        if self.quest_client.ip:
            self.casque_ip = self.quest_client.ip
        self.casque_statut = "Casque prêt" if self.casque_connecte else "Casque non connecté"

        # S'abonner pour écouter les eventbus
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.subscribe("session_updated", self.on_session_updated)
        event_bus.subscribe("casque_connecte", self.handle_casque_connecte)
        event_bus.subscribe("casque_erreur", self.handle_casque_erreur)
        event_bus.subscribe("casque_prepare", self.handle_casque_prepare)
        event_bus.subscribe("wifi_status_changed", self.handle_wifi_status)
        event_bus.subscribe("hr_sensor_status_changed", self.handle_hr_sensor_status)

    def on_leave(self):
        event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)
        event_bus.unsubscribe("session_updated", self.on_session_updated)
        event_bus.unsubscribe("casque_connecte", self.handle_casque_connecte)
        event_bus.unsubscribe("casque_erreur", self.handle_casque_erreur)
        event_bus.unsubscribe("casque_prepare", self.handle_casque_prepare)
        event_bus.unsubscribe("wifi_status_changed", self.handle_wifi_status)
        event_bus.unsubscribe("hr_sensor_status_changed", self.handle_hr_sensor_status)

    # ========== CALLBACKS UDP ==========

    @mainthread
    def handle_unity_connection(self, data):
        connected = data["connected"]
        self.unity_connected = connected
    
    @mainthread
    def handle_wifi_status(self, data):
        self.wifi_connected = data["connected"]
        self.wifi_ssid = data["ssid"]

    @mainthread
    def handle_hr_sensor_status(self, data):
        self.hr_sensor_connected = data["connected"]
        self.hr_data_sent = data["data_sent"]

    def on_session_updated(self, session):
         # Mise à jour UI
        self.selected_model = session.config.model
        self.age_user = str(session.user_profile.age)
        self.hr_target = f"{session.config.target_hr_percent} %"

    # ===== Foncions reliées à l'UI =====
    def force_reconnect(self):
        """Bouton pour forcer la reconnexion"""
        app = App.get_running_app()

        # Forcer la reconnexion en arrêtant le serveur WebSocket et en redémarrant la découverte UDP
        app.ws_server.stop()
        app.udp_discovery.force_reconnect()
        self.unity_connected = False
    
    def send_new_age(self):
        app = App.get_running_app()

        try:
            age = int(self.ids.age_input.text)

            if 5 <= age <= 100:  # validation logique
                app.user_profile.age = age
                print("Age mis à jour :", age)

                # Envoyer via UDP
                if self.udp_controller:
                    self.udp_controller.set_age_player(age)

            else:
                toast("Age invalide")
        except ValueError:
            print("Entrée âge invalide")
            toast("Age invalide")

    # ========== CASQUE VR (QUEST) ==========

    def afficher_info_casque(self):
        """
        Explique les prérequis côté casque pour que le pilotage ADB
        fonctionne — voir quest_control/README.md pour le détail complet.
        """
        texte = (
            "[b]Une fois par casque[/b]\n"
            "Mode développeur activé (application mobile Meta Quest), puis "
            "« Autoriser le débogage USB » accepté au premier branchement.\n\n"
            "[b]Après chaque redémarrage complet du casque[/b]\n"
            "Le débogage réseau ne survit pas à un redémarrage. Rebranchez "
            "le casque en USB à un PC et lancez :\n"
            "python quest_control/quest.py connecter\n"
            "Tant que le casque reste allumé (veille comprise), pas besoin "
            "de rebrancher.\n\n"
            "[b]Réseau[/b]\n"
            "La tablette et le casque doivent être sur le même réseau "
            "Wi-Fi. Certains réseaux (hospitaliers, notamment) isolent les "
            "appareils entre eux — le pilotage sans fil est alors "
            "impossible, quel que soit le réglage.\n\n"
            "[b]Symptôme « Casque introuvable » ou connexion refusée[/b]\n"
            "C'est presque toujours l'un des deux points ci-dessus : casque "
            "redémarré depuis la dernière connexion, ou réseau isolant les "
            "appareils."
        )

        if not hasattr(self, "_dialog_info_casque") or self._dialog_info_casque is None:
            self._dialog_info_casque = MDDialog(
                title="Paramétrer le casque pour l'ADB",
                text=texte,
                size_hint=(0.85, None),
                buttons=[
                    MDFlatButton(
                        text="COMPRIS",
                        on_release=lambda *_: self._dialog_info_casque.dismiss(),
                    ),
                ],
            )
        self._dialog_info_casque.open()

    def on_casque_ip_change(self, value):
        """Champ IP du casque modifié"""
        self.casque_ip = value

    def on_toggle_limite(self, active):
        """
        Interrupteur « Alerte de zone » : active par défaut, car les
        patients sont amenés à être debout pendant la séance et doivent
        être alertés s'ils sortent de la zone tracée. Le désactiver est une
        dérogation explicite de l'investigateur, pas le comportement
        attendu du protocole.
        """
        self.casque_limite_active = active

    def preparer_casque(self):
        """
        Bouton « Préparer le casque » : connexion ADB puis enchaînement
        complet (réveil, capteur de proximité, veille, limite de jeu selon
        l'interrupteur, lancement) — même séquence que quest_control/quest.py
        preparer, validée sur le vrai casque avant d'être branchée ici.
        """
        if self.casque_en_cours:
            return

        ip = self.casque_ip.strip()
        if not ip:
            toast("Renseignez l'adresse IP du casque")
            return

        if not self.quest_client:
            toast("❌ Pilotage du casque indisponible")
            return

        self.casque_en_cours = True
        self.casque_statut = f"Connexion à {ip}..."
        asyncio.ensure_future(self._preparer_casque_async(ip))

    async def _preparer_casque_async(self, ip):
        try:
            connecte = await self.quest_client.se_connecter(ip)
            if not connecte:
                # L'erreur détaillée est déjà remontée via l'event bus
                # (voir handle_casque_erreur) — rien de plus à faire ici.
                return

            self.casque_statut = "Préparation en cours..."
            await self.quest_client.preparer_seance(
                desactiver_limite=not self.casque_limite_active)
        finally:
            self.casque_en_cours = False

    def detecter_casque(self):
        """
        Bouton « Détecter » : cherche le casque automatiquement (dernière IP
        connue, puis balayage réseau en secours — voir quest_discovery.py).
        Remplit le champ IP et connecte si trouvé ; ne prépare pas le casque
        automatiquement, ça reste une action explicite séparée.
        """
        if self.casque_en_cours:
            return
        if not self.quest_client:
            toast("❌ Pilotage du casque indisponible")
            return

        self.casque_en_cours = True
        self.casque_statut = "Recherche du casque sur le réseau..."
        asyncio.ensure_future(self._detecter_casque_async())

    async def _detecter_casque_async(self):
        try:
            await self.quest_client.se_connecter_auto()
        finally:
            self.casque_en_cours = False

    def handle_casque_connecte(self, data):
        self.casque_connecte = True
        self.casque_ip = data["ip"]
        logger.info(f"🥽 Casque connecté : {data['ip']}")

    def handle_casque_erreur(self, data):
        self.casque_connecte = False
        self.casque_en_cours = False
        self.casque_statut = f"Erreur : {data['message']}"
        toast(f"❌ {data['message']}")

    def handle_casque_prepare(self, data):
        self.casque_en_cours = False
        if data["reussi"]:
            self.casque_statut = "Casque prêt"
            toast("Casque prêt")
        else:
            echecs = ", ".join(e["etape"] for e in data["etapes"] if not e["ok"])
            self.casque_statut = f"Étapes en échec : {echecs}"
            toast("⚠️ Casque partiellement préparé — vérifiez avant la séance")