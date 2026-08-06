# Piloter le casque Meta Quest depuis une tablette Android

**Étude APEX** — ID-RCB 2026-A00405-46

Ce dossier contient de quoi ajouter le pilotage du casque à une application
Android existante — en l'occurrence celle qui transmet déjà la fréquence
cardiaque au jeu. Objectif : **plus d'ordinateur dans la chambre**. La tablette
prépare le casque et lance la séance.

Tout se joue en trois classes Kotlin, une dépendance, et un fichier de clé.

**Le nom du jeu sur le casque :  "com.m2s.apexexperiment"**

---

## Est-ce que ça marche ? Oui, et voici pourquoi

Le protocole ADB est du TCP. Rien n'impose que le client soit un PC : c'est un
usage, pas une contrainte technique. Une bibliothèque Kotlin,
[Kadb](https://github.com/flyfishxu/Kadb), en fournit une implémentation qui
parle directement au démon `adbd` du casque, sans binaire `adb` ni serveur ADB.
Elle cible explicitement Android à partir de l'API 23.

Ce qui reste à régler, ce sont deux conditions côté casque. Elles sont
franchissables, mais aucune n'est automatique — autant les connaître avant de
commencer.

### Condition 1 — le casque doit écouter sur le réseau

Le démon n'accepte les connexions TCP qu'après un `adb tcpip 5555`, donné une
fois depuis un poste relié en USB.

**Ce réglage ne survit pas à un redémarrage du casque.** C'est la principale
limite opérationnelle, et elle est connue : le comportement est le même avec
tous les outils de pilotage sans fil. Trois façons de vivre avec :

- ne pas éteindre le casque entre les séances — la veille suffit, le réglage
  tient ;
- rebrancher trente secondes en USB après un arrêt complet ;
- laisser le code poser `persist.adb.tcp.port` à chaque connexion
  (`ClientCasque.tenterPersistanceReseau`, appelé automatiquement). L'effet
  varie selon la version de firmware : c'est un bonus, jamais un acquis.

### Condition 2 — la clé du client doit être reconnue

Le casque n'autorise pas un appareil, il autorise une **clé**. Une clé inconnue
déclenche une demande d'autorisation affichée *dans le casque* — donc il faut
le porter, ce qu'on cherche précisément à éviter.

**La solution :** recopier dans l'application la clé du poste qui pilote déjà
le casque. Elle est déjà autorisée, et l'autorisation suit la clé, pas la
machine. Un script s'en charge :

```bash
python quest_android/outils/preparer_cle.py
```

Il localise la clé, **vérifie que le casque l'accepte bien** — sans quoi la
recopier produirait une application qui ne se connecte pas —, et la dépose sous
le nom attendu.

> La clé est un secret : quiconque la détient peut piloter le casque sur le
> réseau. Elle ne va pas dans un dépôt de code ni dans un courriel. Le script
> refuse d'ailleurs d'écrire dans un dossier suivi par Git.

---

## Contenu du dossier

```
quest_android/
├── README.md                          ce guide
├── outils/
│   └── preparer_cle.py                extrait la clé ADB déjà autorisée
└── src/main/java/fr/univrennes2/apex/casque/
    ├── ClientCasque.kt                connexion ADB et gestion de la clé
    ├── CasqueQuest.kt                 les commandes de séance
    ├── CasqueViewModel.kt             état observable, coroutines, verrou
    └── EcranCasque.kt                 écran Compose d'exemple
```

`ClientCasque` et `CasqueQuest` ne dépendent d'aucune bibliothèque
d'interface : elles s'utilisent depuis n'importe quelle architecture. Le
`ViewModel` et l'écran Compose sont des commodités, à reprendre ou à ignorer.

---

## Intégration, pas à pas

### 1. Dépendance

Dans le `build.gradle.kts` du module :

```kotlin
dependencies {
    implementation("com.flyfishxu:kadb:2.1.3")

    // Déjà présents dans la plupart des applications ; à ajouter sinon.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.4")
}
```

`minSdk 23` suffit. Vérifiez la version disponible sur
[Maven Central](https://central.sonatype.com/artifact/com.flyfishxu/kadb) — la
bibliothèque évolue.

### 2. Permission réseau

```xml
<uses-permission android:name="android.permission.INTERNET" />
```

C'est tout : une connexion TCP vers une adresse du réseau local ne demande rien
d'autre. Si l'application vise Android 9 ou plus récent et parle en clair sur le
réseau local, ajoutez une politique de sécurité réseau autorisant le trafic non
chiffré vers l'adresse du casque, ou `android:usesCleartextTraffic="true"` sur
l'`<application>`.

### 3. Copier les sources

Recopiez les quatre fichiers `.kt` dans votre arborescence. Adaptez le `package`
si votre convention diffère — c'est la seule modification nécessaire.

### 4. Provisionner la clé

```bash
python quest_android/outils/preparer_cle.py --sortie ~/cle_apex
```

Puis déposez le fichier obtenu dans `app/src/main/assets/adbkey`, et ajoutez au
`.gitignore` :

```
app/src/main/assets/adbkey
```

Au démarrage de l'application, une fois :

```kotlin
ClientCasque.preparerIdentite(applicationContext)
```

Le `CasqueViewModel` fourni le fait déjà dans son `init`.

### 5. Brancher l'écran

```kotlin
val modele: CasqueViewModel = viewModel()
EcranCasque(modele)
```

Ou, sans passer par l'écran fourni :

```kotlin
ClientCasque.connecter("192.168.1.42").use { client ->
    val casque = CasqueQuest(client, paquetJeu = "com.VotreSociete.APEX")
    casque.preparerSeance(codePin = "1234")
}
```

**Jamais sur le fil principal.** Une commande traverse le réseau et attend la
réponse du casque : quelques centaines de millisecondes en temps normal,
plusieurs secondes quand il dort. Le `ViewModel` fourni s'en charge
(`Dispatchers.IO`).

---

## Ce que fait `preparerSeance`

Dans l'ordre du soin, casque désinfecté et posé sur la table :

| # | Étape                          | Pourquoi                                                                 |
| - | ------------------------------- | ------------------------------------------------------------------------ |
| 1 | Réveil de l'appareil           | il dort entre deux séances                                              |
| 2 | Capteur de proximité leurré   | sinon il s'endort dès qu'il quitte une tête, et le jeu ne démarre pas |
| 3 | Veille automatique neutralisée | la préparation dure plus longtemps que le délai de veille              |
| 4 | Limite de jeu désactivée      | voir ci-dessous                                                          |
| 5 | Jeu lancé                      | le participant n'a plus qu'à mettre le casque                           |

**Un échec n'interrompt pas la suite.** Chaque étape rapporte son issue, et
l'appelant décide. Mieux vaut un casque partiellement préparé avec un message
clair qu'un arrêt au premier obstacle, avec un participant qui attend.

### Pourquoi désactiver la limite de jeu

Le participant est assis au bord du lit ou dans un fauteuil, l'investigateur est
présent, et l'amplitude du geste ne dépasse pas la longueur des bras. Le risque
dont la limite protège — heurter un mur en se déplaçant — n'existe pas dans ce
contexte. En revanche, une limite qui se déclenche en pleine séance affiche la
grille, interrompt le jeu, et la partie est perdue avec la mesure.

**Pour la qualité des données, la supprimer est plus sûr que la maintenir.**

Deux mécanismes sont tentés dans l'ordre :

1. les **services de test officiels** de Horizon OS v44 et suivants
   (`content://com.oculus.rc`, méthode `SET_PROPERTY`), voie documentée par
   Meta, qui exige un compte développeur connecté sur le casque et son code PIN
   Store ;
2. la propriété système `debug.oculus.guardian_pause`, qui fonctionne sans code
   PIN mais suspend aussi le passthrough — sans conséquence ici, le jeu
   s'affichant en environnement virtuel complet.

Le second n'est pas un contournement du premier : un casque de laboratoire n'est
pas toujours provisionné avec un compte de test, et c'est le cas courant.
`limiteActive()` interroge **les deux**, car ils sont indépendants — n'en
consulter qu'un annoncerait une limite désactivée alors qu'elle ne l'est pas, et
la séance s'interromprait quand même.

Aucune commande ADB ne permet de **dessiner** une limite à distance : le tracé
est un geste, pas un réglage. `effacerLimiteMemorisee()` existe, mais il oblige
quelqu'un à remettre le casque au prochain démarrage.

---

## L'identifiant du jeu

« APEX_experiment » est le nom affiché dans le casque. L'identifiant technique
attendu par ADB ressemble à `com.VotreSociete.APEX`. C'est la confusion la plus
fréquente au premier lancement.

```kotlin
casque.devinerPaquetJeu()          // null si le choix est ambigu
casque.listerApplications("apex")  // pour trancher à la main
```

`devinerPaquetJeu` rend `null` plutôt que de choisir quand plusieurs candidats
existent : lancer silencieusement une autre application serait pire que de ne
rien lancer.

---

## Points de vigilance à vérifier sur le matériel

Ces trois points dépendent du firmware du casque et du réseau de
l'établissement. Ils ne se vérifient qu'avec l'appareil sous la main.

**L'isolation du Wi-Fi.** Beaucoup de réseaux hospitaliers empêchent deux
appareils de se voir. Le pilotage sans fil est alors impossible, quel que soit
le client. Testez-le avant de compter dessus ; à défaut, un point d'accès dédié
résout le problème.

**Les champs de la réponse shell.** `ClientCasque.shell` lit `exitCode`,
`output` et `errorOutput` sur la réponse de Kadb. Si une version future les
renomme, c'est le seul endroit à corriger.

**L'appairage sans fil d'Android 11.** Kadb propose `Kadb.pair(hôte, port, code)`, qui supprimerait le besoin d'un premier branchement USB. Encore
faut-il que le casque expose l'écran de débogage sans fil avec code
d'appairage — ce que les versions de Horizon OS ne font pas toutes. À essayer :
si l'écran existe, la condition 1 disparaît.

---

## Vérifier sans casque

Le code de ce dossier est la transposition fidèle de
`quest_control/quest.py`, l'outil Python déjà en service. **Les commandes shell
sont identiques**, y compris la détection des échecs — un incident survenu sur
la tablette doit être reproductible depuis l'ordinateur, et inversement.

Côté Python, un casque simulé permet de dérouler tout l'enchaînement sans
matériel :

```bash
python quest_control/quest.py --simulateur preparer
python quest_control/quest.py --simulateur --scenario jeu_absent preparer
python quest_control/test_quest.py          # 71 vérifications
```

C'est le meilleur moyen de comprendre ce que le code Kotlin doit faire, et de
comparer les sorties. Les scénarios disponibles couvrent les pannes :
casque absent, débogage non autorisé, jeu non installé, lancement refusé,
services de test indisponibles, propriété système refusée.

---

## Et si ça ne marche pas ?

| Symptôme                                                          | Cause probable                                                                                                                                |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Casque injoignable`                                             | mode réseau non activé (`adb tcpip 5555` après un redémarrage), ou Wi-Fi isolant les appareils                                          |
| Connexion qui reste bloquée                                       | clé non autorisée : le casque attend une validation affichée dans le casque. Vérifiez`preparerIdentite` et le fichier `assets/adbkey` |
| `L'application n'est pas installée`                             | identifiant de paquet erroné — la liste des applications présentes figure dans le message                                                  |
| `Lancement impossible`                                           | préciser l'activité de démarrage, souvent`com.unity3d.player.UnityPlayerActivity`                                                        |
| La grille de limite s'affiche pendant la séance                   | `definirLimite(false)` a échoué des deux côtés ; renseigner le code PIN Store                                                           |
| Le jeu se met en pause avant que le participant ne mette le casque | capteur de proximité non neutralisé sur ce firmware — lancer le jeu juste avant de tendre le casque                                        |

---

## Ce que ce dossier ne fait pas

- **Il ne récupère pas les données de séance.** `Kadb` sait faire du `pull`,
  mais le rapatriement des CSV reste côté poste investigateur, là où vit
  l'application qui les importe.
- **Il ne voit pas ce qui est affiché dans le casque.** Pour cela, le *casting*
  vers l'application mobile Meta Quest.
- **Il ne remplace pas la surveillance du participant.** Le pilotage concerne
  l'appareil, pas la séance.
