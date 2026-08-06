# -*- coding: utf-8 -*-
"""
Casque simulé, pour travailler sans matériel.

Ce module fabrique un faux `adb` : un script qui répond aux mêmes commandes
qu'un vrai casque et mémorise son état. Il sert à deux choses, et c'est
délibéré qu'il ne soit pas cantonné aux tests.

1. **La suite de tests** l'utilise pour vérifier le pilotage sans matériel.
2. **Vous** pouvez l'utiliser pour parcourir la télécommande depuis votre
   téléphone avant d'avoir un casque sous la main :

       python quest_control/telecommande.py --simulateur
       python quest_control/quest.py --simulateur preparer

Ce que le simulateur montre : l'enchaînement des commandes, l'interface, les
messages d'erreur, la mémorisation de l'état de la limite de jeu. Ce qu'il ne
montre pas : le comportement réel d'un firmware Meta, qui varie d'une version
à l'autre. Une séance d'essai sur le vrai casque reste indispensable avant la
première inclusion — le simulateur sert à arriver préparé, pas à s'en passer.

Scénarios disponibles :

    normal               casque connecté, jeu installé, données présentes
    absent               aucun casque branché
    non_autorise         casque branché mais débogage non autorisé
    wifi                 casque joint par le réseau
    jeu_absent           le paquet APEX n'est pas installé
    lancement_echoue     le jeu refuse de démarrer
    sans_donnees         aucune séance enregistrée
    sans_services_test   casque non provisionné (services Horizon muets)
    setprop_refuse       le firmware refuse la propriété système
    clear_refuse         effacement de la limite refusé
"""

from __future__ import annotations

import stat
from pathlib import Path

#: Scénarios reconnus, pour valider une saisie utilisateur.
SCENARIOS = (
    "normal", "absent", "non_autorise", "wifi", "jeu_absent",
    "lancement_echoue", "sans_donnees", "sans_services_test",
    "setprop_refuse", "clear_refuse",
)


GABARIT = r'''#!/usr/bin/env python3
import json
import os
import sys
SCENARIO = "__SCENARIO__"
args = sys.argv[1:]

# Le faux casque conserve son état sur disque. Sans cela, désactiver la limite
# n'aurait aucun effet observable et un bug passerait inaperçu : le test
# vérifierait seulement qu'une commande a été envoyée, pas qu'elle a agi.
ETAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_etat_casque.json")


def etat_lu():
    try:
        with open(ETAT, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"guardian_pause": "", "disable_guardian": False}


def etat_ecrit(**kw):
    e = etat_lu()
    e.update(kw)
    with open(ETAT, "w", encoding="utf-8") as f:
        json.dump(e, f)

def dire(t):
    sys.stdout.write(t)
    sys.exit(0)

if args[:1] == ["devices"]:
    if SCENARIO == "absent":
        dire("List of devices attached\n\n")
    if SCENARIO == "non_autorise":
        dire("List of devices attached\n1WMHH815X10001\tunauthorized\n\n")
    if SCENARIO == "wifi":
        dire("List of devices attached\n192.168.1.42:5555\tdevice product:hollywood "
             "model:Quest_2 device:hollywood\n\n")
    dire("List of devices attached\n1WMHH815X10001\tdevice product:hollywood "
         "model:Quest_2 device:hollywood transport_id:1\n\n")

if args[:1] == ["tcpip"]:
    dire("restarting in TCP mode port: 5555\n")

if args[:1] == ["connect"]:
    dire("connected to %s\n" % args[1])

if args[:1] == ["pull"]:
    import os, shutil
    distant, local = args[1], args[2]
    os.makedirs(local, exist_ok=True)
    for nom in ("CSV_OptionsGame.csv", "CSV_GameInfo.csv",
                "CSV_Physiology_Intensity.csv"):
        open(os.path.join(local, nom), "w").write("colonne;valeur\n1;2\n")
    dire("3 files pulled, 0 skipped.\n")

if args[:1] == ["shell"]:
    cmd = " ".join(args[1:])

    # -- limite de jeu (guardian) --
    if "content call" in cmd and "GET_PROPERTY" in cmd:
        if SCENARIO in ("sans_services_test", "jeu_absent"):
            dire("Result: null\n")
        desactive = "true" if etat_lu()["disable_guardian"] else "false"
        dire("Result: Bundle[{disable_guardian=%s, disable_dialogs=false}]\n"
             % desactive)
    if "content call" in cmd and "SET_PROPERTY" in cmd:
        if SCENARIO == "sans_services_test":
            dire("Result: Bundle[{Success=false, Error=Not provisioned}]\n")
        if "PIN:s:" not in cmd:
            dire("Result: Bundle[{Success=false, Error=PIN required}]\n")
        etat_ecrit(disable_guardian="disable_guardian:b:true" in cmd)
        dire("Result: Bundle[{Success=true}]\n")
    if cmd.startswith("getprop debug.oculus.guardian_pause"):
        dire(etat_lu()["guardian_pause"] + "\n")
    if cmd.startswith("setprop debug.oculus.guardian_pause"):
        if SCENARIO == "setprop_refuse":
            sys.stderr.write("setprop: failed to set property\n")
            sys.exit(1)
        etat_ecrit(guardian_pause=cmd.split()[-1].replace("0", ""))
        dire("")
    if cmd.startswith("pm clear"):
        if SCENARIO == "clear_refuse":
            dire("Error: java.lang.SecurityException\n")
        dire("Success\n")
    if "vrpowermanager" in cmd:
        dire("Broadcasting: Intent { act=com.oculus.vrpowermanager.prox_close }\n")

    if "dumpsys battery" in cmd:
        dire("  level: 73\n")
    if "ro.product.model" in cmd:
        dire("Quest 2\n")
    if "pm list packages" in cmd:
        if SCENARIO == "jeu_absent":
            dire("package:com.oculus.browser\npackage:com.autre.jeu\n")
        dire("package:com.DefaultCompany.APEX\npackage:com.oculus.browser\n")
    if "mResumedActivity" in cmd or "topResumedActivity" in cmd:
        dire("    topResumedActivity=ActivityRecord{a1b2 u0 "
             "com.DefaultCompany.APEX/com.unity3d.player.UnityPlayerActivity}\n")
    if cmd.startswith("ip route"):
        dire("192.168.1.0/24 dev wlan0 proto kernel scope link src 192.168.1.42\n")
    if "monkey -p" in cmd:
        if SCENARIO == "lancement_echoue":
            dire("** No activities found to run, monkey aborted.\n")
        dire("Events injected: 1\n")
    if cmd.startswith("am start"):
        dire("Starting: Intent { cmp=... }\n")
    if cmd.startswith("am force-stop"):
        dire("")
    if cmd.startswith("input keyevent"):
        dire("")
    if cmd.startswith("ls -d"):
        if SCENARIO == "sans_donnees":
            dire("")
        if "/sdcard/Android/data" in cmd:
            dire("/sdcard/Android/data/com.DefaultCompany.APEX/files\n")
        dire("")
    if cmd.startswith("find"):
        if SCENARIO == "sans_donnees":
            dire("")
        base = "/sdcard/Android/data/com.DefaultCompany.APEX/files"
        dire(base + "/2026-07-31_10-15_APEX_001/partie1/CSV_OptionsGame.csv\n"
             + base + "/2026-07-31_10-15_APEX_001/partie2/CSV_OptionsGame.csv\n")
    if cmd.startswith("rm -rf"):
        dire("")
    dire("")

sys.exit(0)
'''


def creer_faux_adb(dossier: Path, scenario: str = "normal") -> Path:
    """Écrit un faux `adb` exécutable dans `dossier` et retourne son chemin."""
    if scenario not in SCENARIOS:
        raise ValueError(
            f"Scénario inconnu : {scenario!r}. Disponibles : {', '.join(SCENARIOS)}")
    chemin = dossier / "adb"
    chemin.write_text(GABARIT.replace("__SCENARIO__", scenario), encoding="utf-8")
    chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return chemin
