from kivy.app import App
from kivy.properties import ListProperty, StringProperty
from kivy.utils import escape_markup
from kivymd.uix.card import MDCard

from ui.game_state_style import GAME_STATE_DEFAULT_COLOR, game_state_style
from utils.event_bus import event_bus


class PlayerChip(MDCard):
    """
    Encadré de la top bar : profil joueur actif + état de partie, visible
    depuis tous les écrans. Un appui ouvre l'écran Profil du joueur (voir
    KCApp.open_player_profile). Inséré dans la MDTopAppBar par
    KCApp.on_start, entre l'icône de gauche et le titre.
    """

    # Au-delà, le nom est tronqué pour laisser de la place au titre de l'écran
    _MAX_NAME_LENGTH = 18
    # Libellés raccourcis par rapport à la bannière Home, faute de place
    _SHORT_STATE_LABELS = {"disconnected": "Déconnecté"}

    player_name = StringProperty("")
    player_age = StringProperty("")  # "12 ans", vide sans profil actif
    game_state_label = StringProperty("")
    game_state_fg = ListProperty(GAME_STATE_DEFAULT_COLOR["fg"])
    game_state_bg = ListProperty(GAME_STATE_DEFAULT_COLOR["bg"])

    def on_kv_post(self, base_widget):
        # session_updated couvre profil (sélection, UDP playerName) et état
        # de partie (UDP game_state, "disconnected" posé à la coupure Unity)
        event_bus.subscribe("session_updated", self.refresh)
        self.refresh()

    def refresh(self, *_):
        session = App.get_running_app().session
        name = session.user_profile.name or ""
        if len(name) > self._MAX_NAME_LENGTH:
            name = name[:self._MAX_NAME_LENGTH - 1] + "…"
        # Le label est en markup (âge en plus petit) : neutraliser [ ] & du nom
        self.player_name = escape_markup(name)
        self.player_age = f"{session.user_profile.age} ans" if name else ""

        label, self.game_state_fg, self.game_state_bg = game_state_style(session.game_state)
        self.game_state_label = self._SHORT_STATE_LABELS.get((session.game_state or "").lower(), label)
