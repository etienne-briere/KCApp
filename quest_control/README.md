# Pilotage du casque Meta Quest depuis le poste

Permet de lancer le jeu et de rapatrier les données de séance **sans toucher au
casque** une fois qu'il est désinfecté, et sans naviguer dans son interface.

Trois façons de s'en servir : en ligne de commande, depuis un **téléphone**
(page web servie par le poste), ou depuis l'application web.

---

## État de validation

| | |
|---|---|
| Logique logicielle | **Testée** — 71 tests contre un casque simulé reproduisant les sorties réelles, cas d'échec compris |
| Télécommande téléphone | **Testée** — jeton, actions, concurrence, casque absent |
| Sur un vrai casque | **Non validé** — aucun Meta Quest n'a été utilisé pendant le développement |

Cinq éléments ne peuvent être établis qu'avec le matériel : la présence d'ADB
sur le poste, l'activation du mode développeur, l'identifiant exact du jeu,
l'emplacement où il écrit ses CSV, et le comportement du capteur de proximité
selon la version de firmware.

**Commencez par le diagnostic**, qui vérifie ces cinq points et indique quoi
faire pour chacun :

```bash
python quest_control/quest.py diagnostic
```

ou, depuis l'application web : onglet **Casque → Diagnostic**.

---

## Ce que ça change concrètement

| Sans l'outil | Avec l'outil |
|---|---|
| Mettre le casque pour lancer le jeu, le retirer, le redésinfecter | Cliquer sur « Lancer le jeu » depuis le poste |
| Brancher le casque, chercher les dossiers dans l'explorateur | Cliquer sur « Récupérer les données » |
| Risque d'oublier une séance sur le casque | La liste des séances présentes est affichée |
| Batterie découverte à plat au moment de la séance | Niveau de batterie visible en permanence |

---

## Installation, une seule fois

### 1. Installer ADB sur le poste

ADB (Android Debug Bridge) est l'outil officiel de Google pour dialoguer avec un
appareil Android. Le Quest en est un.

- Télécharger les **SDK Platform Tools** depuis
  `developer.android.com/studio/releases/platform-tools`
- Décompresser l'archive
- Ajouter le dossier au `PATH`, ou renseigner le chemin complet de `adb.exe`
  dans `quest_control/config.json`

Si vous avez déjà Android Studio pour compiler l'APK de la tablette, ADB est
déjà installé — généralement dans
`%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`.

### 2. Activer le mode développeur sur le casque

- Dans l'application mobile **Meta Quest**, sélectionner le casque
- **Paramètres du casque → Mode développeur → Activer**
- Un compte développeur Meta est requis ; sa création est gratuite

### 3. Autoriser le poste

- Brancher le casque en USB
- **Mettre le casque** : une fenêtre « Autoriser le débogage USB ? » s'affiche
- Cocher « Toujours autoriser depuis cet ordinateur », puis accepter

C'est la seule fois où il faut porter le casque pour la configuration.

### 4. Vérifier

```bash
python quest_control/quest.py diagnostic
```

Six points sont contrôlés. Chaque point en défaut affiche la commande ou la
manipulation à effectuer.

---

## Filaire, sans fil, et depuis un téléphone

**ADB fonctionne des deux façons.** Le câble USB n'est indispensable qu'une
fois, pour autoriser le débogage. Ensuite, `connecter` bascule la liaison en
Wi-Fi et le câble devient inutile tant que le casque reste allumé sur le même
réseau.

**La solution retenue pour le pilotage depuis un téléphone : une page web
servie par le poste.** Pas d'application à distribuer ni à maintenir en
parallèle du script Python — voir plus bas pour la voie retenue quand on veut
se passer du poste entièrement.

```bash
python quest_control/telecommande.py
```

Le poste affiche une adresse à ouvrir sur votre téléphone. Vous obtenez un
grand bouton **Préparer la séance**, l'état du casque en direct — connexion,
batterie, application au premier plan, limite de jeu — et les commandes
séparées. Rien à installer sur le téléphone : c'est une page.

Le poste garde la connexion ADB et exécute tout ; le téléphone n'est qu'un jeu
de boutons. Il doit donc rester allumé et sur le même réseau. La tablette de
recueil, déjà présente dans la chambre, fait aussi bien qu'un téléphone.

> Le lien contient un jeton régénéré à chaque démarrage. Sur un réseau
> hospitalier partagé, une page qui pilote un appareil ne doit pas être
> atteignable par simple balayage de ports. Ce n'est pas de la sécurité forte,
> c'est la précaution minimale.

---

## Et depuis une tablette, sans ordinateur ?

La voie retenue : faire tourner KCApp lui-même en APK sur la tablette
(Buildozer / python-for-android), plutôt que de développer et maintenir un
second client dans un autre langage. `quest.py` n'invoque jamais le binaire
`adb` directement — seulement `self.shell(...)` et `self._executer(...)` — ce
qui permet à `transport_android.py` de remplacer uniquement la couche
transport (ADB en sockets purs, via `adb-shell`) sans toucher à la logique
métier de préparation de séance, de limite de jeu ou de récupération des
données.

Le point qui rend la chose praticable : le casque n'autorise pas un appareil
mais une **clé**, et celle de ce poste est déjà autorisée. La recopier dans le
dossier privé de l'application sur la tablette lui transmet l'autorisation —
plus personne n'a à mettre le casque pour valider quoi que ce soit.

```bash
python quest_control/push_adb_key.py
```

Voir `quest_control/transport_android.py` pour le détail de cette couche
transport et ses dépendances (`adb-shell[pythonrsa]`).

---

## La limite de jeu

C'est le premier risque d'interruption d'une séance. Si la limite se déclenche,
la grille s'affiche, le jeu s'arrête, et la mesure est perdue.

```bash
python quest_control/quest.py limite etat        # est-elle active ?
python quest_control/quest.py limite desactiver  # la suspendre
python quest_control/quest.py limite activer     # la rétablir
```

### Pourquoi désactiver plutôt que retracer

Le participant est assis au bord du lit ou dans un fauteuil, l'investigateur est
présent, et l'amplitude du geste ne dépasse pas la longueur des bras. Le risque
dont la limite protège — heurter un mur en se déplaçant — n'existe pas dans ce
contexte. En revanche, une limite qui se déclenche en pleine séance coûte une
partie entière. **Pour la qualité des données, la supprimer est plus sûr que la
maintenir.**

Rétablissez-la (`limite activer`) si le casque doit servir hors du protocole.

### Deux mécanismes, essayés dans l'ordre

1. Les **services de test officiels** de Horizon OS v44+
   (`content://com.oculus.rc`, méthode `SET_PROPERTY`). Voie documentée par
   Meta, mais elle exige un compte développeur ou de test connecté sur le
   casque et son code PIN Store :

   ```bash
   python quest_control/quest.py configurer --pin 1234
   ```

2. La propriété système `debug.oculus.guardian_pause`, qui fonctionne sans PIN.
   Effet de bord : le passthrough est suspendu, sans conséquence ici puisque le
   jeu s'affiche en environnement virtuel complet.

Le second n'est pas un contournement du premier : un casque de laboratoire
n'est pas toujours provisionné avec un compte de test, et c'est le cas courant.
`limite etat` interroge les deux, car ils sont indépendants — n'en consulter
qu'un annoncerait une limite désactivée alors qu'elle ne l'est pas.

### Retracer réellement une limite

```bash
python quest_control/quest.py limite redefinir
```

Efface le tracé mémorisé : le casque en redemandera un au prochain port.
**Quelqu'un devra alors mettre le casque et tracer la limite aux manettes** —
exactement ce qu'on cherche à éviter. Aucune commande ADB ne permet de
*dessiner* une limite à distance : le tracé est un geste, pas un réglage.

---

## Préparer une séance, en une commande

```bash
python quest_control/quest.py preparer
```

Enchaîne, dans l'ordre du soin :

1. réveil de l'appareil ;
2. neutralisation du capteur de proximité — sans quoi le casque posé sur la
   table se met en veille et le jeu ne démarre pas ;
3. neutralisation de la veille automatique ;
4. désactivation de la limite de jeu ;
5. lancement du jeu.

Chaque étape est annoncée, et son échec n'interrompt pas les suivantes : mieux
vaut un casque partiellement préparé avec un message clair qu'un arrêt au
premier obstacle, avec un participant qui attend. Le code de retour vaut 1 si
une étape a échoué.

Options : `--sans-lancer` pour tout préparer sans démarrer le jeu,
`--garder-limite` pour laisser la limite active.

---

## Configurer l'identifiant du jeu

Le nom affiché dans le casque — « APEX_experiment » — n'est pas l'identifiant
technique attendu par ADB. C'est la source de confusion la plus fréquente au
premier lancement : l'identifiant ressemble à `com.VotreSociete.APEX`.

Pour le trouver et l'enregistrer d'un coup :

```bash
python quest_control/quest.py applications --filtre apex --adopter
```

Si plusieurs candidats apparaissent, la commande refuse de choisir à votre
place et affiche la liste. Fixez alors l'identifiant à la main :

```bash
python quest_control/quest.py configurer --package com.VotreSociete.APEX
```

Si le lancement échoue malgré un identifiant correct, précisez l'activité de
démarrage — pour une application Unity, c'est presque toujours la même :

```bash
python quest_control/quest.py configurer --activite com.unity3d.player.UnityPlayerActivity
```

---

## La mise en veille automatique

C'est le point le plus susceptible de vous surprendre. Le Quest possède un
capteur de proximité qui suspend l'appareil dès qu'il n'est plus porté. Lancer
le jeu avant de poser le casque sur la tête du participant n'a donc d'intérêt
que si cette veille est neutralisée — sans quoi l'application se met en pause
entre le lancement et le port effectif.

L'outil tente automatiquement trois méthodes connues à chaque lancement, et le
diagnostic indique celles que votre firmware accepte. Meta ayant modifié ce
mécanisme à plusieurs reprises, **il faut le vérifier sur votre matériel**.

Si aucune méthode ne fonctionne, le contournement est simple : lancez le jeu
juste avant de tendre le casque au participant, plutôt qu'en début de
préparation. Vous perdez quelques secondes, pas la fonctionnalité.

---

## Passer en Wi-Fi

Le câble USB n'est nécessaire que pour la première connexion. Ensuite :

```bash
python quest_control/quest.py connecter
```

Le casque est détecté, son adresse IP relevée, et la liaison bascule en Wi-Fi.
Vous pouvez débrancher le câble : le casque reste pilotable tant qu'il est
allumé et sur le même réseau.

Aux séances suivantes, si la connexion est perdue :

```bash
python quest_control/quest.py connecter --ip 192.168.1.42
```

> **En milieu hospitalier**, le Wi-Fi isole souvent les appareils les uns des
> autres, ce qui empêche cette liaison. Testez-la avant de compter dessus. À
> défaut, un câble USB long ou un point d'accès dédié résout le problème.

---

## Utilisation courante

### Depuis un téléphone

```bash
python quest_control/telecommande.py
```

puis ouvrir l'adresse affichée. Un bouton **Préparer la séance**, l'état en
direct, et les commandes séparées.

### En ligne de commande

```bash
python quest_control/quest.py diagnostic                      # à faire en premier
python quest_control/quest.py preparer                        # avant chaque séance
python quest_control/quest.py etat                            # état du casque
python quest_control/quest.py limite etat                     # limite de jeu
python quest_control/quest.py arreter                         # arrêter le jeu
python quest_control/quest.py recuperer --participant APEX_001
```

Les dossiers récupérés atterrissent dans
`quest_control/donnees_recuperees/APEX_001_2026-07-31_10-15/`, prêts à être
sélectionnés dans l'application web au moment de créer la séance.

L'option `--effacer` supprime les données du casque après copie. **Ne l'utilisez
qu'après avoir vérifié l'import dans l'eCRF** : c'est une suppression
définitive de données sources.

---

## En cas de problème

| Message | Cause et solution |
|---|---|
| `adb est introuvable` | Platform Tools non installés, ou absents du `PATH`. Renseigner le chemin complet dans `config.json`. |
| `Aucun casque détecté` | Câble non branché, casque éteint, ou liaison Wi-Fi perdue. Rebrancher l'USB et refaire `connecter`. |
| `Casque détecté mais non autorisé` | Mettre le casque et accepter la demande de débogage USB. |
| `L'application n'est pas installée` | L'identifiant de paquet est faux. La liste des applications présentes est affichée dans le message : corriger avec `configurer --package`. |
| `Lancement impossible` | Préciser l'activité de démarrage avec `configurer --activite`. |
| `Aucun dossier de session trouvé` | Le jeu écrit ailleurs que dans les emplacements explorés. Les chemins testés figurent dans le message ; ajouter le bon dans `dossiers_donnees` de `config.json`. Pour le localiser : `adb shell find /sdcard -name CSV_OptionsGame.csv` |
| Le jeu se met en pause avant que le participant ne mette le casque | Capteur de proximité non neutralisé sur ce firmware. Lancez le jeu juste avant de tendre le casque. |
| La grille de limite s'affiche en pleine séance | `python quest_control/quest.py limite desactiver`, puis relancer la partie. Vérifier ensuite avec `limite etat`. |
| `La limite de jeu n'a pas pu être modifiée` | Les deux mécanismes ont échoué. Vérifier le mode développeur, puis renseigner le code PIN Store : `configurer --pin 1234`. |
| La télécommande affiche « Lien invalide ou expiré » | Le jeton change à chaque démarrage. Reprendre l'adresse affichée par le poste. |
| La télécommande n'est pas joignable depuis le téléphone | Réseau hospitalier isolant les appareils, ou pare-feu Windows. Autoriser Python sur le réseau privé, ou passer par un point d'accès dédié. |

---

## Tester sans casque

Deux niveaux, selon ce que vous voulez vérifier.

### La suite de tests

```bash
python quest_control/test_quest.py
```

71 vérifications contre un casque simulé qui reproduit les sorties réelles
d'ADB, y compris les cas d'échec : casque absent, débogage non autorisé, jeu
non installé, lancement refusé, services de test indisponibles, propriété
système refusée. Le casque simulé **mémorise son état** : désactiver la limite
change ce que `limite etat` répond ensuite, sinon le test ne prouverait rien.

### Parcourir l'interface vous-même

C'est ce qu'il faut faire avant la première inclusion, pour répéter le geste :

```bash
python quest_control/quest.py --simulateur preparer
python quest_control/quest.py --simulateur limite etat
python quest_control/telecommande.py --simulateur
```

La télécommande s'ouvre alors sur un casque simulé : les boutons répondent,
l'état évolue, rien ne sort du poste. Vous pouvez l'ouvrir sur votre téléphone
et vérifier que l'interface vous convient au lit du patient.

Pour voir comment l'outil réagit quand ça se passe mal :

```bash
python quest_control/quest.py --simulateur --scenario jeu_absent preparer
python quest_control/telecommande.py --simulateur --scenario absent
```

Scénarios : `normal`, `absent`, `non_autorise`, `wifi`, `jeu_absent`,
`lancement_echoue`, `sans_donnees`, `sans_services_test`, `setprop_refuse`,
`clear_refuse`.

### Ce que le simulateur ne dit pas

Le comportement réel d'un firmware Meta, qui varie d'une version à l'autre :
l'identifiant exact du jeu, l'emplacement où il écrit ses CSV, la réaction du
capteur de proximité, et le fait que les services de test soient accessibles ou
non sur votre casque. **Une séance d'essai sur le matériel reste indispensable
avant la première inclusion** — le simulateur sert à arriver préparé, pas à
s'en passer.

---

## Ce que l'outil ne fait pas

- **Il ne voit pas ce qui est affiché dans le casque.** Pour cela, utilisez le
  *casting* vers l'application mobile Meta Quest, ou `scrcpy` si vous voulez
  l'écran déporté sur le poste.
- **Il ne configure pas les options de jeu** (position, bras actifs,
  environnement). Ces choix sont faits par le participant dans le casque : ils
  font partie de l'intervention.
- **Il ne trace pas de limite de jeu à distance.** Il peut la désactiver ou
  effacer celle qui est mémorisée, mais dessiner une limite suppose de porter
  le casque et de manipuler les manettes.
- **Il ne remplace pas la surveillance du participant.** Le pilotage à distance
  concerne l'appareil, pas la séance.
