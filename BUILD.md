# Build de l'installeur Windows PromptuinoUI

L'app est livrée sous forme d'un installeur Windows `.exe` autonome qui
pose PromptuinoUI dans `Program Files` (ou `%LOCALAPPDATA%\Programs` en
non-admin), crée les raccourcis menu démarrer + bureau, et permet la
désinstallation propre depuis Paramètres → Apps.

**L'installeur final fait ~450 Mo** (modèle RAG ONNX 449 Mo embarqué inclus).
Zéro édition de fichier à faire avant build, zéro téléchargement au 1er
lancement, zéro dépendance réseau côté testeur.

Le module `ui/onnx_setup.py` reste présent comme fallback : si le modèle
disparaît ou est corrompu, un dialog propose de le re-télécharger (à
configurer avec une URL valide à ce moment-là). En usage normal, il n'est
jamais déclenché.

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
3. `pyinstaller build\promptuinoui.spec --noconfirm` → `dist\PromptuinoUI\` (~218 Mo)
4. Inno Setup compile → `build\output\PromptuinoUI-Setup.exe` (~60 Mo)

Durée totale : ~3-5 minutes (la compression LZMA2 du modèle 449 Mo prend
la majorité du temps).

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
- `assets\rag\model\*` incluant `model.onnx` (~449 Mo)
- Tout `ui\` + `main.py` (compilés en `.pyc`)

## Ce qui N'EST PAS embarqué

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
4. Install (~30-60s, le modèle 449 Mo se décompresse)
5. Lancement auto de l'app si coché
6. L'app démarre directement — aucune action réseau requise

**Pas besoin d'avoir Python installé** sur la machine du destinataire.

## Partage du fichier

`build\output\PromptuinoUI-Setup.exe` (~450 Mo) peut être :
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
| Dialog "Téléchargement du modèle" apparaît au lancement | Modèle absent du bundle (PyInstaller a échoué silencieusement) | Vérifier `dist\PromptuinoUI\_internal\assets\rag\model\model.onnx` existe |
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
