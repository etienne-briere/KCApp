# KCApp — APEX Control

Application Kivy/KivyMD (tablette Android + poste Windows) qui fait le pont
entre un capteur de fréquence cardiaque Bluetooth et le jeu VR **APEX**
(Unity, casque Meta Quest), dans le cadre du projet de recherche
Rennes 2 / VIRTUOUS. Elle est pilotée par un intervenant au lit du
participant : profil joueur, scan du capteur FC, suivi de la séance, et
pilotage du jeu (mode, contrôleur PID/DRL, paramètres de jeu).

Nom de build Android : `APEX Control` (`org.m2s.apex.apex_control`, voir
[buildozer.spec](buildozer.spec)).

## Ce que fait l'application

1. **Capte la fréquence cardiaque** via Bluetooth Low Energy (ceinture/montre
   Garmin, Polar, etc. — `app/ble/ble_manager.py`, filtrée par
   `BLE_TARGET_DEVICES` dans [config.py](config.py)).
2. **Transmet la FC à Unity** en continu par WebSocket
   (`app/network/websocket_server.py`).
3. **Dialogue avec Unity en UDP** pour la découverte du jeu sur le réseau, la
   configuration de partie et le pilotage du contrôleur adaptatif
   (`app/network/udp_discovery.py`, `app/network/udp_controller.py`) :
   changement de mode (manuel / PID / DRL / DRL Run 3), bascule PID
   d'échauffement ou de secours, cadence manuelle, etc. — voir
   [CONTROLEUR_HYBRIDE_TABLETTE.md](CONTROLEUR_HYBRIDE_TABLETTE.md).
4. **Gère les profils joueur** (nom, âge, poids, sexe) persistés dans
   `player_profiles.json` (`app/data/player_store.py`), utilisés par Unity
   pour l'estimation des kcal dépensées (équations de Keytel).
5. **Enregistre la séance** (métriques FC, événements de jeu) et exporte en
   CSV via le submodule partagé [csv_export_kit](csv_export_kit/README.md).
6. **Pilote le casque Meta Quest à distance par ADB** (préparation de
   séance, désactivation de la limite de jeu, récupération des CSV) grâce au
   module [quest_control](quest_control/README.md), intégré à l'app via
   `app/network/quest_client.py` et aussi utilisable en standalone depuis un
   poste Windows.

## Architecture du dépôt

```
app/
  ble/           Scan et connexion au capteur de fréquence cardiaque (BLE)
  network/       WebSocket (FC -> Unity), UDP (découverte/pilotage du jeu),
                  pont ADB vers le casque Quest
  controllers/   Logique applicative (ex. AdaptiveController : réagit aux
                  events FC / connexion Unity)
  data/          Profils joueur, configuration et métriques de séance,
                  export CSV
ui/
  screens/kv/    Écrans Kivy (accueil, scan BLE, profil joueur, pilotage du
                  jeu, casque VR, suivi de séance...)
  widgets/       Composants réutilisables (ex. encadré joueur dans la top bar)
quest_control/   Outil (et lib) de pilotage ADB du casque Meta Quest,
                  utilisable en CLI, interface web mobile, ou intégré à KCApp
csv_export_kit/  Submodule Git partagé avec l'app perform (export CSV)
utils/           Logger, bus d'événements, helpers divers
config.py        Paramètres (thème, ports réseau, filtre BLE)
main.py          Point d'entrée desktop (asyncio + Kivy)
service.py       Service Android "Tracker" (évite le gel du process en
                  arrière-plan, voir buildozer.spec)
buildozer.spec   Configuration de build Android (Buildozer / python-for-android)
```

## Prérequis

- Python 3.10+ (voir `.venv` pour l'environnement de développement Windows)
- Dépendances : `pip install -r requirements.txt`
- Un casque Meta Quest avec le jeu APEX installé, et/ou un simulateur
  (`quest_control --simulateur`, voir sa documentation)
- Un capteur de fréquence cardiaque Bluetooth compatible (Garmin, Polar, etc.)

## Lancer l'application (poste Windows, développement)

```bash
python main.py
```

## Générer l'APK Android

Sur une machine Linux/WSL avec Buildozer installé :

```bash
buildozer android debug
```

L'APK est produit dans `bin/`. Voir
[CONTROLEUR_HYBRIDE_TABLETTE.md](CONTROLEUR_HYBRIDE_TABLETTE.md) pour les
détails de signature et de compatibilité avec la version Unity.

## Pilotage à distance du casque (sans le manipuler)

Voir [quest_control/README.md](quest_control/README.md) : diagnostic,
préparation de séance, désactivation de la limite de jeu, récupération des
données, en ligne de commande ou depuis une télécommande web (téléphone).

## Sous-module

`csv_export_kit` est un submodule Git partagé avec l'application `performApp`.
Après un clone :

```bash
git submodule update --init --recursive
```
