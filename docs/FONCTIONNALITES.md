# PromptuinoUI — Fonctionnalités

Document de référence décrivant le fonctionnement du logiciel et l'ensemble
des fonctionnalités implémentées.

---

## 1. Vue d'ensemble

**PromptuinoUI** est une interface desktop PyQt6 pour **Promptuino**, un
outil éducatif qui génère du code embarqué à partir de prompts en langage
naturel. Son but : réduire la barrière d'entrée à la programmation
embarquée pour les enseignants, étudiants et makers.

### Plateformes cibles

- **Arduino** (AVR : Uno, Mega, Nano, Leonardo, Pro Mini, etc.) — seul
  environnement actif.
- **ESP32** (DevKit, S2, S3, C3, Wemos D1 Mini, …) — **bientôt disponible** :
  visible mais grisé / non sélectionnable dans l'UI.

> STM32 et Raspberry Pi ont été retirés (décision 2026-06-21).

### Modes UX progressifs

L'interface s'adapte au niveau de l'utilisateur :

| Mode              | Affichage                                                                 |
| ----------------- | ------------------------------------------------------------------------- |
| **Débutant**      | prompt + bouton « Générer » + compile/upload. Code masqué.                |
| **Intermédiaire** | + éditeur de code coloré + sortie de compilation.                         |
| **Avancé**        | + panneau Fonctionnalités latéral + outils IA (expliquer, linter, etc.). |

Le sélecteur de mode se trouve au centre de la barre supérieure.

### Langues supportées

L'interface est entièrement traduite en **français, anglais, espagnol et
italien**. Le changement de langue est instantané (Affichage → Langue ou
Paramètres → Langue). Au démarrage, l'app revient toujours sur le
français — la langue n'est pas persistée entre sessions.

### Thèmes

Mode **sombre** (par défaut) et **clair**, basculables via le toggle de
la barre supérieure ou Ctrl+Shift+T. Le thème est appliqué en temps réel
à tous les widgets (palettes Qt + signaux observés).

---

## 2. Architecture de la fenêtre

```
┌─────────────┬──────────────────────────────────────────┐
│             │  TopBar : Mode  ·  Thème  ·  Paramètres  │
│   Sidebar   ├──────────────────────────────────────────┤
│   (200/52)  │                                          │
│             │  QStackedWidget  (vue active)            │
│             │                                          │
└─────────────┴──────────────────────────────────────────┘
                StatusBar : IA  ·  Carte
```

### Sidebar repliable

Cinq onglets, dans l'ordre :

1. **Studio** — l'éditeur principal (icône terminal).
2. **Projets** — la bibliothèque de projets utilisateur (icône dossier).
3. **Librairies** — la gestion des libs Arduino (icône pile de livres).
4. **Carte** — la sélection de carte/port (icône CPU).
5. **Modèle IA** — le choix du backend IA (icône étincelles).

Cliquer sur le bouton de pli réduit la sidebar à 52 px (icônes seules).

### Barre de menus

| Menu          | Actions                                                                            |
| ------------- | ---------------------------------------------------------------------------------- |
| **Fichier**   | Nouveau projet, Ouvrir un projet, Enregistrer, Paramètres, Quitter                 |
| **Carte**     | Aller à l'onglet Carte                                                             |
| **Affichage** | Thème (Ctrl+Shift+T), Langue (FR/EN/ES/IT), Sidebar (Ctrl+B), Plein écran (F11), Ouvrir le dossier des projets |
| **Aide**      | À propos, Mode débug — afficher le prompt IA                                       |

### Barre d'état

Affiche en permanence en bas à droite :
- **Modèle IA** : pastille rouge/verte + nom du backend actif (ex. « Claude
  Code »).
- **Carte** : pastille rouge/verte + carte+port (ex. « Arduino Uno —
  COM3 »).

---

## 3. Configuration initiale

Au tout premier lancement, un **WelcomeDialog** modal s'affiche pour
demander à l'utilisateur où stocker ses projets et librairies. Le dossier
choisi devient la racine du **workspace** :

```
<workspace>/
├── Arduino/
│   ├── libraries/    ← arduino-cli installe les libs ici
│   └── projects/     ← .ino + .promptuino.json
└── ESP32/  {libraries, projects}   ← bientôt disponible
```

Cette racine est modifiable à tout moment via **Paramètres → Stockage**.
Les vues Projets et Librairies se rafraîchissent automatiquement à chaque
changement de racine.

---

## 4. Détection automatique de la carte (USB)

Au démarrage, un thread scanne tous les ports série pour comparer les
**VID:PID** à un catalogue connu (`_KNOWN_DEVICES` dans
`ui/board_manager.py`). Si une carte connue est branchée, l'environnement
et le modèle sont détectés et la barre d'état passe au vert.

Une fois l'app lancée, **USBWatcher** continue à surveiller les ports
toutes les secondes pour détecter les branchements/débranchements à
chaud. Aucune action manuelle n'est nécessaire dans le cas nominal.

### Sélection manuelle (onglet Carte)

Si la carte n'est pas reconnue, l'utilisateur peut basculer en mode
manuel :
1. Choix de l'environnement (Arduino ; ESP32 grisé, bientôt disponible).
2. Choix du modèle dans le dropdown.
3. Choix du port série.
4. Validation → la barre d'état passe en mode **Manuel**.

Le board manager (`ui/board_manager.py`) maintient un état global
(`DISCONNECTED` / `CONNECTED` / `MANUAL`) que tous les widgets observent
via le signal `board_manager.changed`.

---

## 5. Studio — l'éditeur principal

C'est l'onglet par défaut au démarrage. Le Studio est l'écran de travail
quotidien : on y décrit la fonctionnalité, on génère le code, on compile
et on téléverse.

### Layout

```
┌──────────────┬─────────────────────────────┬──────────┐
│              │  Code (CodeEditor)          │          │
│   Prompt     ├─────────────────────────────┤  Panneau │
│   utilisateur│  Sortie compilation         │  Fonct.  │
│              │  + Moniteur série           │ (avancé) │
└──────────────┴─────────────────────────────┴──────────┘
        Boutons : Générer · Compiler · Téléverser · Enregistrer
```

Les colonnes sont redimensionnables (QSplitter).

### Génération de code

1. L'utilisateur écrit en langage naturel dans la colonne prompt
   (ex. « fais clignoter la LED de la pin 13 toutes les 500 ms »).
2. Au clic sur **Générer**, le système :
   - **Augmente** le prompt avec le contexte RAG (voir §10) — exemples
     d'API et descriptions des librairies pertinentes injectés en haut.
   - Envoie le prompt augmenté au backend IA actif (Claude Code,
     Anthropic API, Gemini ou Ollama).
   - Parse les marqueurs spéciaux retournés par l'IA pour assigner les
     lignes générées à une **fonctionnalité** (voir §6).
   - Insère le code dans l'éditeur sans écraser ce qui existe déjà :
     les nouvelles fonctionnalités s'ajoutent au code existant.

L'éditeur utilise une coloration syntaxique Arduino/C++ adaptée au thème
(dark/light), avec gutter de numéros de ligne.

### Compilation et téléversement

Le bouton **Compiler & Téléverser** lance la chaîne `arduino-cli` :

1. Vérification du **core** (ex. `arduino:avr`) — installation auto si
   manquant.
2. Détection des `#include` et **installation auto des librairies**
   manquantes via `arduino-cli lib install`.
3. **Compilation** avec le FQBN dérivé de la carte.
4. Si la compilation échoue, **boucle de réparation IA** (jusqu'à 3
   tentatives) : le code et l'erreur sont renvoyés à l'IA qui produit une
   version corrigée, puis on recompile.
5. **Téléversement** sur le port série.

Toute la chaîne tourne dans un `QThread` (`CompileThread`) pour ne pas
bloquer l'UI. Une barre de statut indique en temps réel l'étape en cours
(« Compilation 1/3 », « Réparation IA », « Téléversement », etc.).

### Détection automatique d'arduino-cli

Sur Windows, le binaire `arduino-cli` est cherché dans le `PATH` puis dans
les emplacements connus (`C:\Program Files\Arduino CLI\arduino-cli.exe`,
`%LOCALAPPDATA%\Programs\Arduino CLI\…`). Sur macOS/Linux, on cherche
aussi `/usr/local/bin`, `/opt/homebrew/bin`, `~/.local/bin`. L'utilisateur
n'a généralement rien à configurer après installation officielle.

### Sauvegarde des projets

`Ctrl+S` ou **Fichier → Enregistrer** sérialise le projet actuel :
- Le **code** dans `<projet>.ino`.
- Le **prompt courant**, les **fonctionnalités** (avec leurs prompts et
  plages de lignes), le **mode**, la **carte**, la date de modification
  et un hash du code dans `<projet>.promptuino.json`.

Le titre de la fenêtre reflète le nom du projet ouvert. Au prochain
démarrage, le dernier projet ouvert est restauré automatiquement
(persisté dans `session.json`).

---

## 6. Système de fonctionnalités multiples

Plutôt que de regénérer tout le code à chaque demande, PromptuinoUI gère
le code **par fonctionnalités**. Chaque génération IA crée une ou
plusieurs fonctionnalités, et les générations suivantes s'y ajoutent
sans tout remplacer.

### Marqueurs IA

Pendant le round-trip avec l'IA, le code est parsemé de commentaires
spéciaux (parsés ensuite par l'app) :

```c
/* <<< fn-1 | Clignotement LED >>> */
void blink() { /* ... */ }
/* <<< /fn-1 >>> */
```

Une fonctionnalité peut aussi déclarer ses **exports** — variables ou
fonctions qu'elle expose pour que d'autres puissent les utiliser :

```c
/* <<< fn-1_exports >>>
led_state: bool — état actuel de la LED
<<< end >>> */
```

### Tracking ligne → fonctionnalité

`FunctionTracker` taggue chaque ligne de l'éditeur avec l'id de sa
fonctionnalité d'origine. Quand l'utilisateur édite le code, les tags
suivent automatiquement les insertions/suppressions.

### Graphe de dépendances

`code_analyzer.analyze_code()` analyse statiquement le code et produit un
graphe `{consumer_id → {producer_id, …}}` qui détermine quelles
fonctionnalités utilisent les exports d'autres fonctionnalités. Cela permet :
- D'afficher les dépendances dans le panneau latéral.
- De cascader les suppressions (supprimer une fonctionnalité dont d'autres
  dépendent affiche un avertissement).
- De refuser une régénération qui casserait le contrat d'exports.

### Panneau Fonctionnalités (mode avancé)

Affiché à droite du Studio en mode avancé. Chaque fonctionnalité y
apparaît comme une carte avec :
- Une **pastille de couleur** (palette de 8 couleurs pastels).
- Un **nom** (auto « Fonctionnalité 1 » ou personnalisable par
  double-clic).
- Le **prompt** d'origine tronqué.
- Boutons **Régénérer** (modifier la description et relancer l'IA) et
  **Supprimer** (avec cascade sur les dépendants).

Un **Ctrl+Z** dédié annule la dernière opération sur une fonctionnalité.

---

## 7. Outils IA (mode avancé)

Le menu **Outils** du Studio ouvre cinq dialogs spécialisés. Chacun lance
une opération IA en background dans un thread dédié et présente le
résultat dans une fenêtre séparée — l'éditeur principal n'est jamais
modifié sans accord explicite.

### 7.1 Expliquer le code

Sélectionnez des lignes, cliquez sur **Expliquer** — l'IA produit une
explication pédagogique en markdown (avec coloration des blocs de code
inline). Boutons **Relancer** et **Fermer**.

### 7.2 Détecter les antipatterns

Lance automatiquement un **lint** orienté embarqué : `delay()` bloquant,
classe `String` dynamique sur Uno, `pinMode` manquant, conflit avec la
LED de la pin 13, `int` au lieu de `unsigned long` pour `millis()`, etc.
Présente une liste d'avertissements avec sévérité et explication.

### 7.3 Ajouter des commentaires pédagogiques

Affiche le code original à gauche et la version commentée à droite. Le
bouton **Appliquer** remplace le code dans le Studio (le surlignage par
fonctionnalité est conservé tant que les marqueurs n'ont pas bougé).

### 7.4 Réparer le code

Lance une réparation IA (différente de la boucle automatique de
compilation) en mode interactif. Affiche un **diff** ligne à ligne entre
le code original et le code réparé, plus une explication des
modifications. **Appliquer** pour valider.

### 7.5 Simulation pas à pas

L'IA déroule mentalement `setup()` puis N itérations de `loop()` et
produit une **trace d'exécution** en markdown — utile pour comprendre le
flux sans matériel.

---

## 8. Vue Projets

L'onglet **Projets** liste tous les projets enregistrés dans le workspace,
groupés par plateforme.

### Filtrage et création

- **Filtres** : « Tous » + un onglet par plateforme (Arduino ; ESP32 grisé,
  bientôt disponible).
- **+ Nouveau projet** : ouvre un mini-formulaire (nom + plateforme), crée
  le dossier et bascule directement sur le Studio.

### Carte de projet

Chaque projet est représenté par une carte affichant :
- Une icône dossier + le **nom** du projet.
- Des **badges** : type de carte + mode utilisé.
- L'aperçu du **prompt** d'origine (tronqué).
- La liste des **fonctionnalités** (jusqu'à 3 visibles, chevron pour
  étendre).
- La **date** de dernière modification.
- Boutons **Ouvrir** et **Ouvrir le dossier**.
- Menu kebab `⋯` : **Renommer**, **Dupliquer**, **Supprimer**.

### Sélection multiple

Maintenir `Ctrl` ou `Maj` pour sélectionner plusieurs projets et les
supprimer en lot.

---

## 9. Vue Librairies

L'onglet **Librairies** est une interface graphique pour `arduino-cli
lib`. Il permet d'installer, rechercher et supprimer les librairies par
plateforme **sans toucher à l'installation Arduino IDE de l'utilisateur**
— chaque plateforme a son propre `arduino-cli.yaml` qui isole le dossier
`libraries/`.

### Liste des librairies installées

Au chargement, la vue affiche les librairies installées pour la
plateforme active. Chaque carte montre :
- Une **icône bleue indigo** (pile de livres) devant le nom.
- Le **nom** + **version**.
- L'**auteur**.
- Une courte **description**.
- Un bouton `⋯` qui ouvre un menu :
  - **Ouvrir le dossier** (lance l'explorateur natif sur `install_dir`).
  - **Supprimer** (confirmation puis `arduino-cli lib uninstall`).

### Recherche et installation

La barre de recherche (debounce 350 ms, minimum 2 caractères) lance
`arduino-cli lib search`. Les résultats remplacent la liste des installées
le temps de la requête. Chaque résultat propose :
- Un bouton **Installer** (passe en « Installation… » pendant l'opération).
- Un badge **Installée** (bouton désactivé) si la lib est déjà présente.

### Bandeau d'erreur

Si `arduino-cli` n'est pas trouvé, un bandeau d'avertissement explicite
s'affiche en haut de la vue.

---

## 10. Modèle IA et backends

L'onglet **Modèle IA** permet de choisir le moteur de génération. Quatre
backends sont disponibles, sélectionnables en un clic :

| Backend            | Description                                              | Clé API |
| ------------------ | -------------------------------------------------------- | ------- |
| **Claude Code**    | utilise le CLI `claude` installé localement              | non     |
| **Anthropic API**  | appel direct API Anthropic (Claude Sonnet)               | oui     |
| **Gemini**         | appel API Google Gemini                                  | oui     |
| **Ollama**         | serveur local Ollama (`localhost:11434`), modèle au choix | non     |

### Stockage des clés API

Les clés API sont stockées via **keyring** (Windows Credential Manager,
macOS Keychain, libsecret sous Linux) — **jamais en clair sur disque**.
Les anciennes versions stockaient la clé dans un JSON ; au premier
lancement après mise à jour, la clé est migrée vers keyring puis
supprimée du JSON.

### Sélection du backend

Le backend actif est appelé pour toutes les opérations IA (génération,
réparation, lint, simulation, etc.). Tous les backends implémentent
la même interface (`AIBackend`) ; le code applicatif est agnostique.

La barre d'état affiche en permanence le nom du backend actif (pastille
verte si disponible, rouge sinon).

### Mode débug — afficher le prompt IA

**Aide → Mode débug** : au lieu d'envoyer le prompt au backend, l'app
ouvre un dialog avec le prompt final tel qu'il aurait été envoyé. Utile
pour vérifier le contenu RAG, la mise en sandwich, et débugger les
templates.

---

## 11. Système RAG (retrieval-augmented generation)

Le RAG fournit à l'IA des **exemples concrets** d'usage des librairies
embarquées avant la génération, ce qui élimine les hallucinations
d'API (`Wire.read()` qui n'existe pas, `Servo.set()` au lieu de
`.write()`, etc.).

### Pipeline

1. **Corpus** : `assets/rag/corpus.json` contient ~38 entrées (Tier 1+2+3
   livrés) couvrant les composants courants : capteurs (DHT22, BME280,
   MQ-135, CCS811, MH-Z19, PIR, MFRC522), afficheurs (LCD HD44780,
   LCD I2C, OLED SSD1306, ILI9341), drivers moteurs (L298N, L293D, DRV8833,
   TB6612FNG), GPS (TinyGPS++), claviers (Keypad), LoRa, etc.
   Chaque entrée a une description, des mots-clés multilingues
   (FR/EN/ES/IT) et un exemple de code.
2. **Embeddings** : modèle `paraphrase-multilingual-MiniLM-L12-v2`
   exporté en ONNX **fp32** (449 Mo, livré avec l'app — pas d'appel
   réseau). Inférence via `onnxruntime` + `tokenizers`. Pas de PyTorch
   en production.
3. **Indexation** : `assets/rag/embeddings.npy` (matrice float32 L2-
   normalisée, alignée sur l'ordre du corpus).
4. **Retrieval** : à chaque génération, `retrieve_libs(prompt, k=3,
   threshold=0.25)` calcule la similarité cosinus du prompt avec toutes
   les entrées et retourne les top-K au-dessus du seuil.
5. **Augmentation (sandwich light)** : le prompt envoyé à l'IA prend la
   forme :

   ```
   Task: <tâche nue extraite du prompt utilisateur>

   <contexte RAG : libs candidates + signatures API + exemples>

   ---

   <prompt utilisateur complet, instructions, etc.>
   ```

   La tâche nue est répétée en haut (~10 tokens) pour conserver
   l'attention du modèle sur l'objectif sans dupliquer tout le
   boilerplate (Serial, `PROMPTUINO_NAME`, `EXAMPLE`).

### Failsafe

Tout échec du RAG (corpus manquant, modèle introuvable, erreur d'encoding)
retourne une liste vide. La génération continue normalement, juste sans
contexte enrichi.

### Scripts du pipeline

| Script                              | Rôle                                                      |
| ----------------------------------- | --------------------------------------------------------- |
| `scripts/extract_api_signatures.py` | Extrait les signatures publiques des librairies clonées.  |
| `scripts/enrich_corpus_with_api.py` | Enrichit `corpus.json` avec les signatures extraites.     |
| `scripts/build_rag_embeddings.py`   | Encode le corpus et génère `embeddings.npy`.              |
| `scripts/export_onnx_model.py`      | Exporte le modèle sentence-transformers en ONNX.          |
| `scripts/smoke_test_rag.py`         | Teste le retrieval sur des prompts représentatifs (FR).   |
| `scripts/smoke_test_rag_multilingual.py` | Étend le smoke test à FR/EN/ES/IT (152 cas).         |
| `scripts/generate_rag_diagram.py`   | Produit le schéma `docs/rag_system_diagram.png`.          |

---

## 12. Moniteur série

Intégré au bas du Studio (visible en mode intermédiaire et avancé). Il
permet de lire et écrire sur le port série de la carte connectée sans
quitter l'app.

### Fonctionnalités

- **Détection automatique du baud rate** : un regex (`Serial.begin(...)`)
  scanne le code de l'éditeur pour pré-remplir le baud (9600 par défaut).
- **Liste des baud rates** : 300 → 115200, modifiable à la volée
  (réouvre le port).
- **Champ de saisie** + bouton **Envoyer** pour transmettre une commande.
- **Autoscroll** (case cochée par défaut) : le moniteur suit toujours la
  dernière ligne reçue.
- **Lecture non-bloquante** : un `QThread` lit le port toutes les 20 ms et
  émet `data_received(str)`, `error(str)` ou `disconnected()`.

---

## 13. Paramètres et personnalisation

**Fichier → Paramètres** ouvre un dialog avec deux catégories :

### Stockage

- Chemin du **workspace** (parcourir → QFileDialog).
- Validation → émet `session.workspace_root_changed` ; toutes les vues
  (Projets, Librairies, WorkspaceManager) se rafraîchissent.

### Langue

Quatre boutons radio (FR/EN/ES/IT). Changement instantané : toutes les
chaînes sont mises à jour en temps réel via le signal `lang_manager.changed`.

---

## 14. Fichiers persistés

| Fichier                             | Contenu                                              |
| ----------------------------------- | ---------------------------------------------------- |
| `~/Documents/Promptuino/session.json`  | Workspace root, dernier projet ouvert.            |
| `~/Documents/Promptuino/config.json`   | Backend IA actif, modèle Ollama choisi.           |
| `<workspace>/<plat>/projects/<projet>/<projet>.ino` | Code source.                       |
| `<workspace>/<plat>/projects/<projet>/<projet>.promptuino.json` | Métadonnées projet.    |
| `<workspace>/<plat>/libraries/`     | Librairies arduino-cli (par plateforme).             |
| `<workspace>/<plat>/arduino-cli.yaml` | Config arduino-cli isolée (redirige `directories.user`). |
| **Keyring système**                 | Clés API Anthropic et Gemini (jamais sur disque).    |

---

## 15. Raccourcis clavier

| Raccourci         | Action                                       |
| ----------------- | -------------------------------------------- |
| `Ctrl+N`          | Nouveau projet                               |
| `Ctrl+O`          | Ouvrir un projet                             |
| `Ctrl+S`          | Enregistrer le projet courant                |
| `Ctrl+Q`          | Quitter                                      |
| `Ctrl+B`          | Replier / déplier la sidebar                 |
| `Ctrl+Shift+T`    | Basculer thème clair / sombre                |
| `F11`             | Plein écran                                  |
| `Ctrl+Z` (Studio) | Annuler la dernière opération sur une fonctionnalité |

---

## 16. Architecture (vue de haut)

PromptuinoUI suit un découpage modulaire strict :

- **Singletons module-level** observables via signaux Qt :
  `theme_manager`, `lang_manager`, `board_manager`, `session`,
  `workspace_manager`, `project_manager`, `ai_config`. Tous les widgets
  s'abonnent au signal `changed` de chaque singleton et se rafraîchissent
  en temps réel.
- **Workers Qt** pour toute opération > 100 ms : compilation, IA, scan
  USB. L'UI ne se bloque jamais.
- **Backends IA pluggables** derrière une interface abstraite
  (`AIBackend`). Ajouter un backend = sous-classer + enregistrer dans
  `factory.BACKEND_DEFS`.
- **Persistance JSON atomique** pour la session, la config et les
  projets ; **keyring** pour les secrets.
- **Pas de dépendance circulaire** entre modules — DAG strict.

### Structure du repo

```
PromptuinoUI/
├── main.py                         # Point d'entrée
├── ui/
│   ├── main_window.py              # Fenêtre principale + menus
│   ├── sidebar.py · topbar.py      # Navigation
│   ├── theme.py · i18n.py          # Thème + 4 langues
│   ├── board_manager.py · board_view.py · usb_watcher.py  # Cartes
│   ├── arduino_cli.py              # Compile / upload / fix loop
│   ├── workspace.py · session.py · project_manager.py     # Persistance
│   ├── projects_view.py · library_view.py · ia_view.py    # Vues onglets
│   ├── studio_view.py · code_editor.py                    # Studio
│   ├── code_analyzer.py · function_deps.py                # Analyse
│   ├── function_tracker.py · function_markers.py          # Fonctionnalités
│   ├── functions_panel.py                                 # Panneau latéral
│   ├── explain_code_dialog.py · lint_code_dialog.py       # Outils IA
│   ├── repair_code_dialog.py · add_comments_dialog.py
│   ├── simulate_code_dialog.py
│   ├── ai_backends/                # openai_compat · providers · ollama_backend · claude_code · factory · base
│   ├── ai_config.py                # Backend actif + clés (keyring)
│   ├── rag.py                      # Retrieval-augmented generation
│   ├── serial_monitor.py           # Moniteur série
│   ├── statusbar.py · settings_dialog.py · welcome_dialog.py
│   ├── icons.py                    # SVG inline (style Lucide)
│   └── toggle_switch.py · auto_hide_scrollbar.py
├── scripts/                        # Pipeline RAG + helpers
├── assets/                         # i18n JSON · RAG corpus + modèle ONNX
└── docs/                           # Documentation
```

---

## 17. Liens

- **PromptuinoUI** (interface) : https://github.com/medkar/PromptuinoUI
- **Promptuino** (modules historiques) : https://github.com/medkar/promptuino
