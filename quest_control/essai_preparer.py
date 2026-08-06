# -*- coding: utf-8 -*-
"""
Teste `preparer` (réveil, capteur de proximité, veille, limite, lancement du
jeu) avec QuestAndroid, contre un vrai casque.

Ce script ne réimplémente rien : il appelle directement `cmd_preparer`, la
même fonction que `quest_control/quest.py preparer` utilise déjà sur le PC —
on lui passe juste une instance de `QuestAndroid` au lieu d'une instance de
`Quest`. Si ça fonctionne ici, c'est la preuve que la logique d'orchestration
(inchangée) et le nouveau transport (adb-shell) fonctionnent ensemble sur du
matériel réel, exactement comme le fait déjà l'outil PC.

ATTENTION — contrairement à essai_reel.py, ceci N'EST PAS en lecture seule :

  - le capteur de proximité est leurré (le casque croit être porté) ;
  - la mise en veille automatique est neutralisée ;
  - par défaut, la limite de jeu (guardian) est désactivée ;
  - par défaut, le jeu APEX est lancé sur le casque.

C'est exactement ce que fait `python quest_control/quest.py preparer` sur le
PC : aucun risque nouveau, mais les mêmes effets réels sur le casque. Prévoir
de pouvoir arrêter le jeu ensuite (`python quest_control/quest.py arreter`)
et de redéfinir la limite si besoin.

Usage :
    # étape 1 — prudent : ni la limite ni le jeu ne sont touchés
    python quest_control/essai_preparer.py 192.168.1.62 --garder-limite --sans-lancer

    # étape 2 — une fois l'étape 1 validée : l'enchaînement complet
    python quest_control/essai_preparer.py 192.168.1.62
"""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quest import cmd_preparer  # noqa: E402  (réutilisée telle quelle)
from transport_android import QuestAndroid  # noqa: E402


def main() -> int:
    arguments = sys.argv[1:]
    if not arguments:
        print("Usage : python quest_control/essai_preparer.py <ip> "
              "[--garder-limite] [--sans-lancer]")
        return 1

    ip = arguments[0]
    options = arguments[1:]
    garder_limite = "--garder-limite" in options
    sans_lancer = "--sans-lancer" in options

    cle = Path.home() / ".android" / "adbkey"
    if not cle.exists():
        print(f"Clé introuvable : {cle}")
        return 1

    print(f"Connexion à {ip} ...")
    quest = QuestAndroid(ip=ip, chemin_cle=cle)
    quest.verifier_connexion()
    print("Connecté.\n")

    if garder_limite or sans_lancer:
        print("Mode prudent :",
              "limite non touchée," if garder_limite else "",
              "jeu non lancé." if sans_lancer else "")
        print()

    args = Namespace(garder_limite=garder_limite, sans_lancer=sans_lancer,
                      package=None)
    return cmd_preparer(quest, args)


if __name__ == "__main__":
    raise SystemExit(main())