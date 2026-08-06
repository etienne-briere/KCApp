# -*- coding: utf-8 -*-
"""
Premier essai de QuestAndroid contre un vrai casque.

Volontairement en lecture seule : aucune commande qui change l'état du
casque (pas de am start/stop, pas de setprop, pas de pm clear). L'idée est de
valider la connexion et l'authentification RSA d'abord, avant de risquer quoi
que ce soit sur une vraie séance.

Prérequis :
  - le casque doit déjà écouter en TCP (normalement déjà le cas si
    `quest_control/quest.py etat` fonctionne actuellement) ;
  - la clé de ce PC (~/.android/adbkey) doit déjà être autorisée par le
    casque — c'est le cas si adb.exe s'y connecte déjà sans redemander
    d'autorisation.

Usage :
    python quest_control/essai_reel.py 192.168.1.239
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transport_android import QuestAndroid  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage : python quest_control/essai_reel.py <adresse-ip-du-casque>")
        return 1

    ip = sys.argv[1]
    cle = Path.home() / ".android" / "adbkey"
    if not cle.exists():
        print(f"Clé introuvable : {cle}")
        print("Vérifiez que adb.exe s'est déjà connecté au moins une fois "
              "depuis ce compte Windows.")
        return 1

    print(f"Connexion à {ip} avec la clé {cle} ...")
    quest = QuestAndroid(ip=ip, chemin_cle=cle)

    try:
        quest.verifier_connexion()
    except Exception as exc:
        print(f"Échec de connexion : {exc}")
        return 1

    print("Connecté.\n")
    print("Modèle              :", quest.modele())
    print("Batterie             :", quest.batterie(), "%")
    print("Application active  :", quest.application_active() or "(aucune)")
    installe = quest.config["package"] in quest.paquets()
    print("Jeu APEX installé   :", "oui" if installe else "non")
    print("Sessions sur casque :", len(quest.lister_sessions()))

    print("\nSi ces informations sont cohérentes avec ce que renvoie déjà "
          "`quest.py etat`, l'authentification RSA et le transport adb-shell "
          "fonctionnent correctement sur ce casque.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())