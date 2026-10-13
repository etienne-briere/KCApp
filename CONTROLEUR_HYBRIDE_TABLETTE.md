# App tablette : contrôleur hybride (version 2.4)

À utiliser avec la branche Unity `feature/controleur-hybride-1hz` (commandes UDP décrites dans `CONTROLEUR_HYBRIDE_1HZ.md` du projet Unity). Avec une version Unity plus ancienne, les nouveaux boutons n'ont aucun effet (Unity ignore les clés inconnues).

## Ce qui change dans l'écran Pilotage

**Mode de jeu** : nouvelle entrée **DRL Run 3 (adaptatif)**. Elle envoie le mode DRL (`SelectedModel:3`) et le modèle Run 3 (`controllerSetup`), puis redémarre la partie, comme pour un changement de mode.

**Options PID/DRL**, visibles seulement en mode DRL ou DRL Run 3 :

- **PID d'échauffement** : le PID commande pendant les 90 s d'échauffement, puis le DRL prend la main ;
- **PID de secours (si cycle limite)** : bascule automatique en PID si le DRL entre en cycle limite ;
- pris en compte au prochain lancement ou redémarrage de partie (message `controllerSetup:<deployed|run3>,<0|1>,<0|1>`).

« Warmup » a été renommé **Warmup (rampe de la cible)** pour le distinguer du PID d'échauffement.

**Nouvelle carte « Contrôleur en cours de partie »** (active pendant une partie ou une pause) :

- affiche le contrôleur actif et la raison de la dernière bascule (renvoyés par Unity : `controllerState`, `controllerSwitchReason`) ;
- boutons **PID**, **DRL**, **DRL Run 3**, **PID secours** : bascule à la seconde suivante (`controllerState:...`) ;
- champ **cadence manuelle** + bouton **Manuel** (`manualCpm:...`).

## Profil du joueur : poids et sexe

Les cartes **Nouveau joueur** et **Modification du joueur** ont deux champs facultatifs : **Poids (kg)** et **Sexe** (Non renseigné / Homme / Femme). Ils sont enregistrés avec le profil (`player_profiles.json`, les anciens profils restent valides) et envoyés à Unity avec le nom et l'âge à chaque sélection de profil (`userWeight:72`, `userSex:M`, `F` ou `N`). Unity s'en sert pour estimer les kcal dépensées (équations de Keytel : FC, poids, âge, sexe) et les affiche sur le bilan de fin de partie. Sans poids ou sans sexe, la ligne kcal n'est pas affichée. Sous le sélecteur de profil : « 30 ans · 72 kg · Femme ».

## Fichiers modifiés

- `app/network/udp_controller.py` : `set_controller_setup`, `set_controller_state`, `set_manual_cpm` ;
- `app/data/session_config.py` et `app/network/udp_discovery.py` : réception des clés `controllerConfig`, `drlModel`, `warmupPid`, `backupPid`, `controllerState`, `controllerSwitchReason` ;
- `ui/screens/pilotage_screen.py`, `ui/kv/pilotage_screen.kv` : interface ;
- `app/data/player_store.py`, `app/data/user_profile.py`, `ui/screens/player_profile_screen.py`, `ui/kv/player_profile_screen.kv` : poids et sexe du profil (`set_weight_player`, `set_sex_player` dans `udp_controller.py`, réception `userWeight` / `userSex` dans `udp_discovery.py`) ;
- `buildozer.spec` : version 2.4.

## Générer l'APK

Sur la machine habituelle de build (Linux ou WSL avec buildozer déjà installé) :

```bash
cd KCApp-main
buildozer android debug
```

L'APK est produit dans `bin/` (`apex_control-2.4-arm64-v8a-debug.apk`). Le construire sur la même machine que la version précédente garde la même signature : l'installation se fait alors par-dessus l'ancienne version, sans la désinstaller (et sans perdre les profils enregistrés sur la tablette).
