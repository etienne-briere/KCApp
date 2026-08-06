# -*- coding: utf-8 -*-
"""
Stub minimal pour `shared/console.py`, absent de ce dépôt.

`quest_control/quest.py` importe `configurer_console` et l'appelle une seule
fois, au chargement du module, sans utiliser de valeur de retour :

    from console import configurer_console
    configurer_console()

Le seul effet observable de son absence était une `ModuleNotFoundError` à
l'import — rien d'autre dans quest_control ne dépend de ce module. Vu que
`quest.py` utilise des couleurs ANSI dans sa sortie CLI (VERT, ROUGE, JAUNE),
la fonction d'origine faisait vraisemblablement deux choses : activer
l'interprétation des séquences ANSI dans le terminal Windows (désactivée par
défaut sur les consoles anciennes), et forcer un encodage de sortie en UTF-8
pour les accents. Ce stub fait ça, sans dépendance externe.

Si vous retrouvez le vrai fichier `shared/console.py` du dépôt d'origine,
remplacez-le par celui-ci — celui-ci est une reconstitution, pas l'original.
"""

from __future__ import annotations

import sys


def configurer_console() -> None:
    """Rend le terminal Windows utilisable : couleurs ANSI et UTF-8."""
    _activer_ansi_windows()
    _forcer_utf8()


def _activer_ansi_windows() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(
                handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        # Terminal qui ne supporte pas ce mode (ancienne console cmd.exe,
        # sortie redirigée vers un fichier, etc.) : les codes ANSI
        # s'afficheront tels quels plutôt que comme des couleurs, sans
        # bloquer le programme.
        pass


def _forcer_utf8() -> None:
    for flux in (sys.stdout, sys.stderr):
        reconfigure = getattr(flux, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass