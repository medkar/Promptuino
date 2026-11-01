# Build de l'installeur Windows PromptuinoUI

L'app est livrée sous forme d'un installeur Windows `.exe` autonome qui
pose PromptuinoUI dans `Program Files` (ou `%LOCALAPPDATA%\Programs` en
non-admin), crée les raccourcis menu démarrer + bureau, et permet la
désinstallation propre depuis Paramètres → Apps.

**L'installeur final fait ~59 Mio** — mesuré sur les artefacts produits par la
CI, pas estimé.

⛔ **Ce document a longtemps annoncé « ~450 Mo, modèle embarqué », et ce n'est
plus vrai.** Ça l'a été : le modèle d'embeddings ONNX (~449 Mo) était
réellement dans le paquet. Il en est sorti le **2026-08-28** (TODO #74) et les
chiffres de ce fichier n'avaient pas suivi — le document décrivait donc un
installeur qui n'existe plus. Corrigé le 2026-08-31 en relevant les tailles
réelles.

**Le modèle est téléchargé PENDANT l'installation**, pas embarqué. La section
`[Run]` de `build\installer.iss` rappelle l'application elle-même en
`--download-model`, pour que l'URL épinglée et l'empreinte SHA-256 ne vivent
qu'à un seul endroit (`ui/onnx_setup.py`) — une seconde implémentation côté
installeur serait un second endroit à tenir à jour.

⚠️ Inno ne vérifie **pas** le code de sortie d'une entrée `[Run]` : un réseau
filtré ne fait donc pas échouer l'installation, et l'application repropose le
téléchargement à son premier lancement. Ce chemin-là n'est plus un secours
exceptionnel — c'est le chemin **normal** dès que l'installation n'a pas pu
télécharger.

## Prérequis sur la machine de build

| Outil | Pourquoi | Install |
|---|---|---|
| Python 3.12+ | runtime + PyInstaller | déjà présent |
| PyInstaller | empaquette Python + deps en .exe + folder | `pip install pyinstaller` |
| Inno Setup 6 | génère le .exe d'install Windows | `winget install JRSoftware.InnoSetup` |
| arduino-cli.exe | binaire embarqué dans l'app | copié dans `build\third_party\` |

## Build complet (one-shot)

Depuis la racine du repo, en PowerShell :

```powershell
.\build\build_installer.ps1
```

Le script enchaîne :
1. Vérification prérequis (arduino-cli, Inno Setup, PyInstaller)
2. Nettoyage `dist\` et `build\promptuinoui\`
3. `pyinstaller build\promptuinoui.spec --noconfirm` → `dist\PromptuinoUI\`
   (~218 Mo, **sans** le modèle)
4. Inno Setup compile → `build\output\PromptuinoUI-Setup.exe` (~59 Mio)

Durée totale : ~3-5 minutes.

## Build étape par étape (debug)

Si tu veux comprendre / déboguer chaque étape séparément :

```powershell
# 1. PyInstaller seul
pyinstaller build\promptuinoui.spec --noconfirm

# 2. Test du dist (l'exe doit lancer sans erreur)
.\dist\PromptuinoUI\PromptuinoUI.exe

# 3. Inno Setup seul (suppose dist\PromptuinoUI\ existe)
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" build\installer.iss
```

## Ce qui est embarqué dans l'installeur

- `PromptuinoUI.exe` (bootstrap PyInstaller) + `_internal\` (Python + libs)
- PyQt6 + Qt6 (73 Mo)
- onnxruntime (33 Mo)
- numpy (27 Mo total avec numpy.libs)
- tokenizers (7 Mo)
- arduino-cli.exe (37 Mo) — bundlé dans `_internal\`
- `assets\wiring\*` (SVG des cartes, breadboards, composants — 812 Ko)
- `assets\rag\corpus.json` + `assets\rag\embeddings.npy` (corpus + embeddings — ~16 Mo)
- `assets\rag\model\*` **sauf `model.onnx`** (tokenizer et configuration, ~5 Mo)
- Tout `ui\` + `main.py` (compilés en `.pyc`)

## Ce qui N'EST PAS embarqué

- **`model.onnx` (~449 Mo)** — l'exclusion est **explicite** dans
  `build\promptuinoui.spec`, jamais implicite : s'en remettre au fait que le
  fichier est gitignoré ferait diverger un build local (qui l'a sous la main)
  d'un build CI (qui ne l'a pas), **sans que rien ne le dise**. Il est
  téléchargé à l'installation, cf. l'en-tête de ce document.
- `torch`, `transformers`, `sklearn`, `optimum`, `huggingface_hub`, `datasets`,
  `safetensors`, `accelerate`, `onnx` (le builder) — deps dev uniquement
- `.claude/`, `.planning/`, `CLAUDE.md`, `TODO.md` — artefacts dev
- `tests/`, `scripts/` — non distribués
- `.git/` — non distribué

## Test d'install sur la machine du destinataire

Sur Windows 10/11, **double-clic sur `PromptuinoUI-Setup.exe`** :
1. Sélection langue (FR/EN)
2. Choix du répertoire d'install (défaut : `C:\Program Files\PromptuinoUI`)
3. Option raccourci bureau
4. Install (quelques secondes), **puis téléchargement du modèle d'embeddings
   (~448 Mio)** — c'est l'étape longue, et c'est la seule qui demande du réseau
5. Lancement auto de l'app si coché
6. Si le téléchargement a échoué (réseau filtré d'établissement, annulation),
   l'application démarre **quand même** et le repropose ; d'ici là la recherche
   de bibliothèques est désactivée, et l'application le dit plutôt que de faire
   semblant

**Pas besoin d'avoir Python installé** sur la machine du destinataire.

## Partage du fichier

`build\output\PromptuinoUI-Setup.exe` (~59 Mio) peut être :
- Uploadé sur Google Drive / OneDrive / WeTransfer
- Mis en release GitHub (gratuit, public, max 2 Go par asset)
- Hébergé sur un serveur perso / S3

## Erreurs courantes

| Erreur au build | Cause | Fix |
|---|---|---|
| `pyinstaller introuvable` | pas installé | `pip install pyinstaller` |
| `Inno Setup 6 introuvable` | pas installé | `winget install JRSoftware.InnoSetup` |
| `arduino-cli.exe introuvable` | binaire absent de `build\third_party\` | Copier depuis `C:\Program Files\Arduino CLI\` |
| `Build PYZ failed` (PyInstaller) | dep manquante | Vérifier que tout dans `requirements.txt` est installé |

| Erreur au runtime de l'app | Cause | Fix |
|---|---|---|
| Dialog "Téléchargement du modèle" apparaît au lancement | **Attendu** si le téléchargement de l'installation n'a pas abouti (réseau filtré, annulation) — le modèle n'est PAS dans le bundle | Accepter le téléchargement, ou déposer `model.onnx` à la main (`PROMPTUINO_ONNX_URL` accepte aussi une URL locale) |
| `arduino-cli introuvable` au runtime | binaire pas dans le bundle | Vérifier `dist\PromptuinoUI\_internal\arduino-cli.exe` |
| App crash silencieux au lancement | dépendance Python manquante | Rebuild en passant `console=True` dans le spec pour voir stderr |

## Versioning

La version embarquée dans l'installeur est dans `build\installer.iss` :

```iss
#define MyAppVersion "0.1.0"
```

Bump à la main avant chaque release. Inno Setup détecte les versions existantes
via `AppId` (GUID fixe) — un nouveau setup met automatiquement à jour
l'install précédente sans avoir à désinstaller manuellement.
