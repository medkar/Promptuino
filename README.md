# Promptuino

> Describe what you want to build. Get the code **and** the wiring diagram.
>
> *[Version française](#promptuino-fr)*

Promptuino turns a plain-language description into an Arduino sketch, then
**draws the wiring diagram by reading the generated code**. The goal is to
lower the entry barrier to embedded programming: plug the board in, describe
what you want, upload.

It is built for teaching — schools, workshops, self-taught beginners — where
the first obstacle is rarely the algorithm. It is *"which pin goes where, and
why isn't it lighting up"*.

---

## What it does

- **Code generation** from a natural-language prompt, with compilation and
  upload to the board without leaving the window.
- **A wiring diagram deduced from the code**: components are recognised in the
  sketch, placed on a breadboard and connected by a wire router, with
  pin-by-pin wiring instructions.
- **Guided library selection**: 155 documented corpus entries and 200+
  identified components; for everything else, a search in the official Arduino
  library registry.
- **A conversational assistant** anchored on the current project — it sees the
  code and the hardware, not just the question.
- **Four languages**: French, English, Spanish, Italian.

## Three modes

The interface reveals controls progressively, without ever changing what is
sent to the model or what is stored in the project.

| Mode | For whom |
|---|---|
| **Beginner** | plug in, describe, upload — nothing else on screen |
| **Intermediate** | the code becomes visible and editable, feature by feature |
| **Advanced** | dual editor (generated / stable code), transfer, repair tools |

## It runs on your machine

Generation runs on a local model served by [Ollama](https://ollama.com), and
`arduino-cli` ships inside the installer. **No account and no API key are
needed**, and nothing you write leaves your machine.

⚠️ **Ollama is not bundled — install it separately**, then pull a model
(`ollama pull gemma3:4b` or the model of your choice). Promptuino detects
whether the server is running, but cannot install it for you.

Two downloads happen once, then everything works offline: the model you
pull through Ollama, and the embedding model the installer fetches
(~449 MB, see below).

A remote backend stays available for those who want one — the application
speaks the OpenAI-compatible protocol and connects to Gemini, OpenAI,
Anthropic, Mistral, DeepSeek, Qwen or any compatible URL, **with your own
key**, stored in the system keyring.

## Install

### Windows — installer

**No installer has been released yet.** When one is, it will appear under
the repository *Releases*: a self-contained package that sets up the
application, its dependencies and `arduino-cli`. A macOS installer is
planned but does not exist yet either; until then, run from source.

The **embedding model** (`paraphrase-multilingual-MiniLM-L12-v2`, ~449 MB) is
downloaded from [Hugging Face](https://huggingface.co) during installation
rather than shipped inside the installer. Without it, library search is
disabled — and the application says so instead of pretending.

### From source

```bash
git clone https://github.com/medkar/Promptuino.git
cd Promptuino
pip install -r requirements.txt
python main.py
```

Python 3.12 or newer.

⚠️ **Two dependencies are not in the repository**, for size reasons:

- the **ONNX model** (`assets/rag/model/model.onnx`) — generate it with
  `scripts/export_onnx_model.py`, or let the application offer to download it;
- **`arduino-cli`** — required to compile and upload.

## Project status

The generator, the assistant and the compile chain are usable day to day. Two
things deserve to be said plainly:

- **The wiring diagram is experimental by construction.** It is *deduced* from
  the code, so it sometimes guesses. The rule held throughout the project is
  never to present a guess as a certainty: when the application has guessed,
  it says so, and offers to correct it.
- **Only Arduino is supported.** ESP32 appears in the interface but is
  deliberately disabled until it is genuinely supported.

## Under the hood

- **PyQt6** for the interface, **PyInstaller + Inno Setup** for the installer
- **Local RAG**: ONNX embeddings over a curated corpus of Arduino libraries,
  with lexical and semantic selection, no network call
- **Static analysis of the sketch** for component recognition, then breadboard
  placement and A\* wire routing
- **241 test scripts**, runnable in one command:
  ```bash
  python scripts/run_all_tests.py -j 6
  ```

## License

Promptuino is distributed under the **GNU General Public License v3.0** — the
same license as [Fritzing](https://fritzing.org). See [LICENSE](LICENSE).

This is not merely a preference: the application is built on **PyQt6**, whose
open-source license is itself GPL v3. Redistribution follows from that.

The embedding model,
[`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2),
is distributed by its authors under **Apache-2.0**. Promptuino downloads an
ONNX export of it from
[`medkar/promptuino-embeddings`](https://huggingface.co/medkar/promptuino-embeddings),
pinned to a fixed revision so that every install gets the exact file the
retrieval thresholds were measured against.

---
---

<a id="promptuino-fr"></a>

# Promptuino — version française

> Décrire ce qu'on veut faire. Obtenir le code **et** le schéma de câblage.

Promptuino génère du code Arduino à partir d'une description en langage
naturel, puis **dessine le schéma de câblage en relisant le code généré**.
L'objectif est de réduire la barrière d'entrée à la programmation embarquée :
brancher la carte, décrire en français, téléverser.

L'application est pensée pour l'enseignement — collège, lycée, ateliers,
autodidactes — là où le premier obstacle n'est pas l'algorithme mais
*« quelle patte va où, et pourquoi ça ne s'allume pas »*.

## Ce que ça fait

- **Génération de code** à partir d'un prompt en langage naturel, avec
  compilation et téléversement vers la carte sans quitter la fenêtre.
- **Schéma de câblage déduit du code** : les composants sont reconnus dans le
  sketch, placés sur une breadboard et reliés par un routeur de fils, avec les
  instructions de branchement broche par broche.
- **Choix de la bibliothèque guidé** : 155 entrées de corpus documentées et
  plus de 200 composants identifiés ; pour tout le reste, une recherche dans
  le registre officiel Arduino.
- **Assistant conversationnel** ancré sur le projet en cours — il voit le code
  et le matériel, pas seulement la question.
- **Quatre langues** : français, anglais, espagnol, italien.

## Trois modes

L'interface expose les contrôles progressivement, sans jamais changer ce qui
est envoyé au modèle ni ce qui est enregistré dans le projet.

| Mode | Pour qui |
|---|---|
| **Débutant** | brancher, décrire, téléverser — rien d'autre à l'écran |
| **Intermédiaire** | le code devient visible et modifiable, fonctionnalité par fonctionnalité |
| **Avancé** | double éditeur (code généré / code stable), transfert, outils de réparation |

## Tout tourne sur votre machine

La génération s'appuie sur un modèle local servi par
[Ollama](https://ollama.com), et `arduino-cli` est embarqué dans l'installeur.
**Aucun compte ni clé d'API** ne sont nécessaires, et rien de ce que vous
écrivez ne quitte votre machine.

⚠️ **Ollama n'est pas embarqué — il faut l'installer séparément**, puis
récupérer un modèle (`ollama pull gemma3:4b`, ou celui de votre choix).
Promptuino détecte si le serveur tourne, mais ne peut pas l'installer à
votre place.

Deux téléchargements ont lieu une fois pour toutes, ensuite tout fonctionne
hors ligne : le modèle récupéré via Ollama, et le modèle d'embeddings que
l'installation télécharge (~449 Mo, voir ci-dessous).

Un backend distant reste possible pour qui le veut — l'application parle le
protocole OpenAI-compatible et sait se connecter à Gemini, OpenAI, Anthropic,
Mistral, DeepSeek, Qwen ou à n'importe quelle URL compatible, **avec votre
propre clé**, stockée dans le trousseau du système.

## Installation

### Windows — installeur

**Aucun installeur n'est encore publié.** Quand ce sera le cas, il
apparaîtra dans les *Releases* du dépôt : un paquet autonome qui pose
l'application, ses dépendances et `arduino-cli`. Un installeur macOS est
prévu mais n'existe pas non plus ; d'ici là, lancer depuis les sources.

Le **modèle d'embeddings** (`paraphrase-multilingual-MiniLM-L12-v2`, ~449 Mo)
est téléchargé depuis [Hugging Face](https://huggingface.co) pendant
l'installation plutôt qu'embarqué dans l'installeur. Sans lui, la recherche de
bibliothèques est désactivée — et l'application le dit plutôt que de faire
semblant.

### Depuis les sources

```bash
git clone https://github.com/medkar/Promptuino.git
cd Promptuino
pip install -r requirements.txt
python main.py
```

Python 3.12 ou plus récent.

⚠️ **Deux dépendances ne sont pas dans le dépôt**, pour des raisons de taille :

- le **modèle ONNX** (`assets/rag/model/model.onnx`) — à générer avec
  `scripts/export_onnx_model.py`, ou à laisser l'application le proposer ;
- **`arduino-cli`** — nécessaire pour compiler et téléverser.

## État du projet

Le générateur, l'assistant et la chaîne de compilation sont utilisables au
quotidien. Deux choses méritent d'être dites franchement :

- **Le schéma de câblage est expérimental par construction.** Il est *déduit*
  du code, donc il devine parfois. La règle tenue dans tout le projet est de
  ne jamais présenter une supposition comme une certitude : quand
  l'application a deviné, elle l'écrit, et propose de corriger.
- **Seul l'Arduino est pris en charge.** L'ESP32 est visible dans l'interface
  mais volontairement désactivé tant qu'il n'est pas réellement supporté.

## Sous le capot

- **PyQt6** pour l'interface, **PyInstaller + Inno Setup** pour l'installeur
- **RAG local** : embeddings ONNX + un corpus curé de bibliothèques Arduino,
  avec sélection lexicale et sémantique, sans appel réseau
- **Analyse statique du sketch** pour la reconnaissance des composants, puis
  placement sur breadboard et routage A\* des fils
- **241 scripts de test** exécutables d'un coup :
  ```bash
  python scripts/run_all_tests.py -j 6
  ```

## Licence

Promptuino est distribué sous **GNU General Public License v3.0** — la même
licence que [Fritzing](https://fritzing.org). Voir [LICENSE](LICENSE).

Ce choix n'est pas seulement une préférence : l'application est bâtie sur
**PyQt6**, dont la licence open source est elle-même la GPL v3. Toute
redistribution en découle.

Le modèle d'embeddings,
[`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2),
est distribué par ses auteurs sous **Apache-2.0**. Promptuino en télécharge un
export ONNX depuis
[`medkar/promptuino-embeddings`](https://huggingface.co/medkar/promptuino-embeddings),
épinglé sur une révision fixe pour que chaque installation reçoive exactement
le fichier sur lequel les seuils de recherche ont été mesurés.
