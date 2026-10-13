# Traduction française et couleurs des états de partie envoyés par Unity,
# partagées par la bannière Home et l'encadré joueur de la top bar.
# "disconnected" n'est pas envoyé par Unity : posé localement dès qu'Unity
# n'est plus joignable (voir udp_discovery.py/_check_unity_connection), pour
# le distinguer de "menu" dans le badge, le graphique et l'export CSV.
GAME_STATE_LABELS = {
    "menu": "Menu",
    "ready": "Prêt",
    "playing": "En cours",
    "paused": "En pause",
    "finished": "Terminé",
    "disconnected": "Jeu déconnecté",
}

# Couleurs du badge d'état de partie (mêmes valeurs que GREEN/AMBER/BLUE/
# PURPLE/RED _FG/_BG dans status_bar.kv). "ready" n'a pas d'entrée dédiée :
# il retombe sur le gris par défaut (état neutre, en attente).
GAME_STATE_COLORS = {
    "playing": {"fg": (0.176, 0.490, 0.196, 1), "bg": (0.906, 0.961, 0.914, 1)},
    "paused": {"fg": (0.780, 0.518, 0.047, 1), "bg": (1, 0.976, 0.882, 1)},
    # "Menu" : le joueur est connecté mais pas encore dans la scène de jeu.
    "menu": {"fg": (0.098, 0.463, 0.824, 1), "bg": (0.890, 0.949, 0.992, 1)},
    # "Finished" : la session est terminée.
    "finished": {"fg": (0.482, 0.122, 0.635, 1), "bg": (0.953, 0.898, 0.961, 1)},
    # "Jeu déconnecté" : mêmes couleurs que les autres indicateurs de
    # déconnexion de l'app (RED_FG/RED_BG dans status_bar.kv).
    "disconnected": {"fg": (0.776, 0.157, 0.157, 1), "bg": (0.988, 0.910, 0.906, 1)},
}
GAME_STATE_DEFAULT_COLOR = {"fg": (0.459, 0.459, 0.459, 1), "bg": (0.925, 0.925, 0.925, 1)}


def game_state_style(raw_state):
    """(libellé français, couleur texte, couleur fond) d'un état de partie brut"""
    raw_state = raw_state or "Menu"
    key = raw_state.lower()
    colors = GAME_STATE_COLORS.get(key, GAME_STATE_DEFAULT_COLOR)
    return GAME_STATE_LABELS.get(key, raw_state.capitalize()), colors["fg"], colors["bg"]
