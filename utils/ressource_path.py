import os
import sys


def resource_path(relative_path):
    """
    Retourne le chemin absolu compatible dev + PyInstaller
    """

    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)