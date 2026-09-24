from kivymd.uix.screen import MDScreen
from kivy.properties import StringProperty, BooleanProperty
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivymd.toast import toast
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.menu import MDDropdownMenu

from utils.event_bus import event_bus
from utils.logger import get_logger

logger = get_logger(__name__)


class PlayerProfileScreen(MDScreen):
    """Écran de gestion du profil joueur (nom, âge) accessible depuis le menu Contrôle"""

    unity_connected = BooleanProperty(False) # connexion Unity
    player_name = StringProperty("") # nom du profil actif (affiché sur le sélecteur)
    player_age = StringProperty("") # âge du profil actif (affiché sous le sélecteur)

    # Card "Nouveau joueur"
    show_new_form = BooleanProperty(False)
    new_name_field_text = StringProperty("")
    new_age_field_text = StringProperty("25")

    # Card "Modification du joueur"
    show_edit_form = BooleanProperty(False)
    edit_name_field_text = StringProperty("")
    edit_age_field_text = StringProperty("25")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._active_profile_name = None
        self._pending_open_edit = False

    def on_enter(self):
        """Appelé à l'ouverture de l'écran"""
        app = App.get_running_app()

        self.udp_controller = app.udp_controller
        self.udp_discovery = app.udp_discovery
        self.session = app.session
        self.player_store = app.player_store

        self.unity_connected = self.udp_discovery.is_unity_connected()
        self._sync_active_profile(self.session.user_profile)

        event_bus.subscribe("session_updated", self.on_session_updated)
        event_bus.subscribe("unity_connection_changed", self.handle_unity_connection)

        # Ouverture directe du formulaire d'édition demandée depuis un autre
        # écran (ex. icône crayon sur Home) via request_edit_on_enter() —
        # ScreenManager.on_current ne dispatche on_enter qu'après la
        # transition (asynchrone dès qu'il y a un écran précédent), donc un
        # appel direct à open_edit_form() juste après app.change_screen()
        # s'exécuterait avant que cet écran ait fini de s'initialiser.
        if self._pending_open_edit:
            self._pending_open_edit = False
            self.open_edit_form()

    def request_edit_on_enter(self):
        """
        À appeler AVANT app.change_screen(...) depuis un autre écran, pour
        ouvrir directement le formulaire d'édition dès l'arrivée ici.
        """
        self._pending_open_edit = True

    def on_leave(self):
        event_bus.unsubscribe("session_updated", self.on_session_updated)
        event_bus.unsubscribe("unity_connection_changed", self.handle_unity_connection)
        self._close_player_menu()

    def on_session_updated(self, session):
        self._sync_active_profile(session.user_profile)

    @mainthread
    def handle_unity_connection(self, data):
        self.unity_connected = data["connected"]

    def _sync_active_profile(self, user_profile):
        """
        Reflète le nom du profil actif sur le bouton sélecteur. Les
        formulaires (Nouveau / Modification) ne sont peuplés qu'à l'ouverture
        explicite via leurs icônes respectives — pas de resynchronisation
        automatique le temps qu'ils sont ouverts.
        """
        self.player_name = user_profile.name
        self.player_age = str(user_profile.age) if user_profile.name else ""

        # Le profil actif n'est reconnu comme "existant" (modifiable) que
        # s'il correspond à un profil réellement enregistré dans le store.
        if user_profile.name and self.player_store.get(user_profile.name):
            self._active_profile_name = user_profile.name
        else:
            self._active_profile_name = None

    # ========== SÉLECTION ==========

    def open_player_menu(self, caller):
        """Ouvre le menu déroulant de sélection du profil joueur"""
        self._close_player_menu()

        names = self.player_store.names()
        if not names:
            toast("Aucun profil enregistré — créez-en un")
            return

        items = [
            {
                "text": name,
                "on_release": lambda name=name: self.on_player_select(name),
            }
            for name in names
        ]
        self._player_menu = MDDropdownMenu(caller=caller, items=items, width_mult=4)
        # Un clic en dehors du menu (dismiss) déclenche par défaut une
        # animation de réduction avant de retirer le widget de la Window ;
        # pendant toute cette durée il reste attaché et intercepte tous les
        # clics de l'écran (cf. pilotage_screen.py/open_model_menu). On
        # force donc un retrait immédiat.
        self._player_menu.bind(on_dismiss=lambda *_: self._close_player_menu())
        self._player_menu.open()

    def _close_player_menu(self):
        menu = getattr(self, "_player_menu", None)
        if menu is not None:
            self._player_menu = None
            Clock.schedule_once(lambda dt: Window.remove_widget(menu), 0)

    def on_player_select(self, name):
        """Sélection d'un profil existant dans le menu : devient le profil actif"""
        self._close_player_menu()
        profile = self.player_store.get(name)
        if not profile:
            return

        self._active_profile_name = profile["name"]
        self.show_new_form = False
        self.show_edit_form = False
        self._apply_active_profile(profile["name"], profile["age"])

    # ========== NOUVEAU JOUEUR ==========

    def open_new_form(self):
        """Icône « account-plus » : affiche la card Nouveau joueur (vide)"""
        self.new_name_field_text = ""
        self.new_age_field_text = "25"
        self.show_edit_form = False
        self.show_new_form = True

    def create_player(self):
        """Bouton « Créer » de la card Nouveau joueur"""
        name = self.ids.new_name_field.text.strip()
        if not name:
            toast("Le nom du joueur est requis")
            return

        try:
            age = int(self.ids.new_age_field.text)
        except ValueError:
            toast("Âge invalide")
            return
        age = max(5, min(100, age))

        self.player_store.add(name, age)

        self._active_profile_name = name
        self.show_new_form = False
        self._apply_active_profile(name, age)
        toast(f"Profil « {name} » créé")

    # ========== MODIFICATION DU JOUEUR ==========

    def open_edit_form(self):
        """Icône « account-edit » : affiche la card Modification du profil actif"""
        if not self._active_profile_name:
            toast("Sélectionnez d'abord un profil à modifier")
            return

        profile = self.player_store.get(self._active_profile_name)
        if not profile:
            return

        self.edit_name_field_text = profile["name"]
        self.edit_age_field_text = str(profile["age"])
        self.show_new_form = False
        self.show_edit_form = True

    def save_edited_player(self):
        """Bouton « Enregistrer » de la card Modification du joueur"""
        name = self.ids.edit_name_field.text.strip()
        if not name:
            toast("Le nom du joueur est requis")
            return

        try:
            age = int(self.ids.edit_age_field.text)
        except ValueError:
            toast("Âge invalide")
            return
        age = max(5, min(100, age))

        old_name = self._active_profile_name
        if old_name and old_name != name:
            self.player_store.rename(old_name, name)
        self.player_store.add(name, age)

        self._active_profile_name = name
        self.show_edit_form = False
        self._apply_active_profile(name, age)
        toast(f"Profil « {name} » mis à jour")

    # ========== SUPPRESSION ==========

    def confirm_delete_player(self):
        """Icône « account-remove » : demande confirmation avant suppression"""
        if not self._active_profile_name:
            toast("Sélectionnez d'abord un profil à supprimer")
            return

        name = self._active_profile_name
        if not hasattr(self, "_dialog_confirm_delete") or self._dialog_confirm_delete is None:
            self._dialog_confirm_delete = MDDialog(
                title="Supprimer ce profil ?",
                buttons=[
                    MDFlatButton(
                        text="ANNULER",
                        on_release=lambda *_: self._dialog_confirm_delete.dismiss(),
                    ),
                    MDFlatButton(
                        text="SUPPRIMER",
                        on_release=lambda *_: self._delete_active_player(),
                    ),
                ],
            )
        self._dialog_confirm_delete.text = f"Le profil « {name} » sera définitivement supprimé de la liste."
        self._dialog_confirm_delete.open()

    def _delete_active_player(self):
        """Confirmation du dialog : supprime le profil actif du store"""
        self._dialog_confirm_delete.dismiss()

        name = self._active_profile_name
        if not name:
            return

        self.player_store.remove(name)
        self._active_profile_name = None
        self.player_name = ""
        self.player_age = ""
        self.show_new_form = False
        self.show_edit_form = False

        # Si le profil supprimé était le profil actif de la session, on le
        # retire aussi de l'affichage (ex. Home) — sans redémarrer un envoi
        # UDP, il n'y a rien de plus pertinent à pousser à Unity ici.
        if self.session.user_profile.name == name:
            self.session.user_profile.name = ""

        toast(f"Profil « {name} » supprimé")

    # ========== COMMUN ==========

    def _apply_active_profile(self, name, age):
        """Fait de ce profil le profil actif de la session, et le pousse à Unity"""
        self.session.user_profile.name = name
        self.session.user_profile.age = age
        self.player_name = name
        self.player_age = str(age)
        logger.info(f"👤 Profil joueur actif : {name}, {age} ans")

        if self.udp_controller:
            self.udp_controller.set_player_name(name)
            self.udp_controller.set_age_player(age)
            logger.info(f"📤 Profil joueur envoyé : {name}, {age} ans")
