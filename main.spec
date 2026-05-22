# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# =========================================================
# KIVYMD (IMPORTANT pour ton erreur icon_definitions)
# =========================================================
kivymd_hidden = collect_submodules('kivymd')
kivymd_datas = collect_data_files('kivymd')

# =========================================================
# BLEAK (Bluetooth Windows)
# =========================================================
bleak_hidden = collect_submodules('bleak')

# =========================================================
# KIVY (minimal safe, PAS collect_submodules entier)
# =========================================================
kivy_hidden = [
    'kivy.config',
    'kivy.core.window',
    'kivy.core.text',
    'kivy.graphics',
    'kivy.lang',
]

# =========================================================
# DATA (TON PROJET)
# =========================================================
datas = [
    ('assets', 'assets'),
    ('ui', 'ui'),
    ('ui/kv', 'ui/kv'),
]

# Ajouter datas KivyMD (icônes, fonts, etc.)
datas += kivymd_datas
datas += collect_data_files('kivy_matplotlib_widget')


# =========================================================
# ANALYSIS
# =========================================================
a = Analysis(
    ['main.py'],

    pathex=[],

    binaries=[],

    datas=datas,

    hiddenimports=(
        kivymd_hidden +
        bleak_hidden +
        kivy_hidden +
        [
            # sécurité KivyMD (évite crash icon_definitions)
            'kivymd.icon_definitions',
            'kivymd.icon_definitions.md_icons',

            # souvent utilisés indirectement
            'kivymd.app',
            'kivymd.uix.button',
            'kivymd.uix.label',
            'kivymd.uix.dialog',
            'kivymd.toast',
            'kivy_matplotlib_widget',
            'kivy_matplotlib_widget.uix.graph_widget',
            'ui.widgets',
            'ui.widgets.my_widget',
            'ui.widgets.status_bar',
            'ui.widgets.status_bar.StatusBar'
        ]
    ),

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    excludes=[
        'kivy.tests',
        'kivy.garden',   # IMPORTANT: évite ton crash précédent
    ],

    noarchive=False,
)

# =========================================================
# PYZ
# =========================================================
pyz = PYZ(a.pure)

# =========================================================
# EXE
# =========================================================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,

    name='KCApp',

    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,

    console=True,   # mets True si debug

    # icon='assets/icon.ico',
)

# =========================================================
# COLLECT
# =========================================================
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,

    strip=False,
    upx=True,
    upx_exclude=[],

    name='KCApp',
)