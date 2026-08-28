# PyInstaller spec file for PromptuinoUI.
#
# Build (depuis la racine du repo) :
#   pyinstaller build/promptuinoui.spec --noconfirm
#
# Produit : dist/PromptuinoUI/  (mode one-folder)
#
# Le modele ONNX (~449 Mo) est EXCLU de l'installeur ; il sera telecharge
# au 1er lancement via ui/onnx_setup.py. Configurer l'URL avant build :
# ui/onnx_setup.py:ONNX_MODEL_URL.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# `Analysis.location` est le repertoire du spec ; on remonte au repo root.
SPEC_DIR = Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent

# ─── Data files (assets non-Python) ───────────────────────────────────────
# Tout assets/ inclus le modele ONNX (~449 Mo) embarque pour zero edit /
# zero download au 1er lancement. Installeur final ~500 Mo compresse.
# Format PyInstaller : list[(src, dest_dir_in_bundle)].
datas = []
for path in (REPO_ROOT / "assets").rglob("*"):
    if not path.is_file():
        continue
    rel = path.relative_to(REPO_ROOT)
    datas.append((str(path), str(rel.parent)))

# ─── Binaires embarques ───────────────────────────────────────────────────
# arduino-cli.exe pose a la racine de l'app, retrouve par _candidate_paths()
# dans ui/arduino_cli.py.
binaries = [
    (str(SPEC_DIR / "third_party" / "arduino-cli.exe"), "."),
]

# ─── Modules a exclure (gain de taille / hygiene) ─────────────────────────
# tkinter, matplotlib, etc. ne sont pas utilises par l'app.
# torch/transformers/sklearn/onnx : deps dev (optimum) inutiles en runtime
# car on charge model.onnx directement via onnxruntime + tokenizers. Sans
# exclusion explicite, PyInstaller embarque ~390 Mo de surplus.
excludes = [
    "tkinter",
    "matplotlib",
    "scipy",
    "pandas",
    "IPython",
    "jupyter",
    "pytest",
    "_pytest",
    "test",   # tests stdlib (rarement utiles en runtime)
    "tests",  # tests du projet (non distribues)
    # Deps dev/training : runtime utilise seulement onnxruntime + tokenizers
    "torch",
    "torchvision",
    "torchaudio",
    "transformers",
    "sklearn",
    "scikit_learn",
    "onnx",   # onnxruntime suffit pour l'inference, onnx (le builder) non
    "hf_xet",
    "huggingface_hub",
    "optimum",
    "datasets",
    "safetensors",
    "accelerate",
]

# ─── Hidden imports (modules importes dynamiquement) ──────────────────────
# Les backends IA (ui/ai_backends/) font des imports DIFFERES (a l'interieur
# des methodes) que PyInstaller ne detecte PAS par scan statique. On les
# force via hiddenimports + collect_all (= recupere aussi les sous-modules,
# datas, binaries).
hiddenimports = [
    # google.generativeai / google.ai.generativelanguage / anthropic removed:
    # those SDKs are no longer used — the app now talks to all providers via
    # a unified OpenAI-compatible HTTP adapter (ui/ai_backends/openai_compat.py).
]

# collect_all : recupere tous les sous-modules d'un package (PyInstaller
# scan statique manque les imports dynamiques internes du SDK).
_collect_targets = []  # emptied: Gemini/Anthropic SDKs removed from the project
for _pkg in _collect_targets:
    _datas, _binaries, _hidden = collect_all(_pkg)
    datas += _datas
    binaries += _binaries
    hiddenimports += _hidden


block_cipher = None


a = Analysis(
    [str(REPO_ROOT / "main.py")],
    pathex=[str(REPO_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PromptuinoUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX pas indispensable, complique le debug
    console=False,       # app GUI : pas de fenetre console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,           # TODO: ajouter une icone .ico si dispo
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PromptuinoUI",
)
