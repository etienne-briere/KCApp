import asyncio

from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty
from kivy.app import App
from utils.logger import get_logger
from utils.event_bus import event_bus
from kivymd.toast import toast
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton

logger = get_logger(__name__)


class HeadsetScreen(MDScreen):
    """Écran de pilotage du casque VR (préparation avant séance)"""

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

        self.quest_client = app.quest_client

        # Re-refléter l'état du casque si on revient sur l'écran après coup
        self.casque_connecte = self.quest_client.connecte
        if self.quest_client.ip:
            self.casque_ip = self.quest_client.ip
        self.casque_statut = "Casque prêt" if self.casque_connecte else "Casque non connecté"

        event_bus.subscribe("casque_connecte", self.handle_casque_connecte)
        event_bus.subscribe("casque_erreur", self.handle_casque_erreur)
        event_bus.subscribe("casque_prepare", self.handle_casque_prepare)

    def on_leave(self):
        event_bus.unsubscribe("casque_connecte", self.handle_casque_connecte)
        event_bus.unsubscribe("casque_erreur", self.handle_casque_erreur)
        event_bus.unsubscribe("casque_prepare", self.handle_casque_prepare)

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
        """
        Champ IP du casque modifié.

        Le strip() se fait ici plutôt que dans le kv (headset_screen.kv,
        condition "disabled" du bouton Préparer) : kv ne crée pas de
        binding réactif correct quand on appelle une méthode directement
        sur la propriété observée dans l'expression — root.casque_ip
        change bien, mais "root.casque_ip.strip()" ne se réévalue jamais.
        """
        self.casque_ip = value.strip()

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
