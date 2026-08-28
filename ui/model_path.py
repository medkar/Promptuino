"""Ou vit `model.onnx` — source de verite unique, sans Qt.

⛔ **Le modele NE PEUT PAS etre ecrit a cote du code une fois l'app
installee.** PyInstaller pose le bundle dans `C:\\Program Files\\…`, qui
n'est pas accessible en ecriture a un utilisateur sans droits admin. Le
telechargement echouait donc a l'installation reelle sur :

    PermissionError: [Errno 13] Permission denied:
    'C:\\Program Files\\Promptuino\\_internal\\assets\\rag\\model\\model.onnx.partial'

Trouve le 2026-08-28 en installant l'artefact produit par la CI. Aucun test
ne pouvait l'attraper : en developpement, `assets/` est dans le depot, donc
inscriptible, et tout se passait bien.

**Deux emplacements, dans cet ordre :**

1. **a cote du code**, s'il y est deja — c'est le cas en developpement (le
   fichier est gitignore mais present) et ce le serait d'un build qui
   choisirait de l'embarquer. On ne re-telecharge pas ce qu'on a.
2. sinon, **dans le dossier de donnees de l'utilisateur**, a cote de
   `session.json`. Inscriptible, survit a une desinstallation, et partage
   entre une install et une execution depuis les sources.

⚠️ Le TOKENIZER, lui, reste toujours a cote du code : il est versionne dans
le depot (16 Mo) et embarque dans le bundle, donc jamais telecharge.
"""
from __future__ import annotations

from pathlib import Path

# `Path(__file__).parent.parent` : la racine du depot en dev, `_internal/` en
# bundle PyInstaller 6.x. ⚠️ Piege a ne pas refaire : `sys.executable.parent`
# pointe vers le dossier RACINE du bundle, frere de `_internal/`, pas dedans.
_BASE_CODE = Path(__file__).resolve().parent.parent
from .paths import DATA_DIR
_DOSSIER_UTILISATEUR = DATA_DIR / "model"

MODEL_NAME = "model.onnx"


def bundled_model_path() -> Path:
    """Emplacement a cote du code (lecture seule une fois installe)."""
    return _BASE_CODE / "assets" / "rag" / "model" / MODEL_NAME


def user_model_path() -> Path:
    """Emplacement inscriptible, ou le telechargement depose le fichier."""
    return _DOSSIER_UTILISATEUR / MODEL_NAME


def model_path() -> Path:
    """Le chemin a UTILISER — celui qui existe, sinon celui a remplir."""
    embarque = bundled_model_path()
    if embarque.is_file():
        return embarque
    return user_model_path()


def is_model_available() -> bool:
    """True si un `model.onnx` exploitable est present quelque part."""
    p = model_path()
    try:
        return p.is_file() and p.stat().st_size > 1_000_000   # > 1 Mio
    except OSError:
        return False
