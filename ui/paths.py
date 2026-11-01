"""Ou vivent les donnees de Promptuino — un seul endroit qui le decide.

Arborescence, decidee le 2026-08-28 :

    ~/Documents/Promptuino/
    ├── projets/     <- espace de travail (DEPLACABLE, reglage utilisateur)
    └── data/        <- session, composants, preferences, modele, cache

⚠️ **Pourquoi les projets ne sont PAS dans `data/`, ni `data/` dans les
projets.** L'espace de travail est fait pour bouger : un reglage permet de le
poser sur OneDrive ou un lecteur reseau. Le dossier de donnees, lui, ne bouge
pas. Imbriquer le mobile dans le fixe rendait le reglage incoherent, et
melangeait un modele de 448 Mio et un cache avec le travail de l'eleve --
vider les donnees de l'app aurait efface ses projets.

⛔ **Ce melange a DEJA eu lieu et il a laisse des debris** : un
`arduino-cli.yaml` pointant `directories.user` sur le dossier de donnees y
avait fait creer `libraries/`, `deps/` et un `projects/` vide, a cote de
`session.json`. C'est ce constat qui a tranche le decoupage.

**Chaque module garde SA constante** (`session._SESSION_PATH`,
`declared_components._LIBRARY_PATH`…), calculee ici a l'import. Les tests les
detournent une par une, et ce contrat ne change pas — voir la lecon
`feedback_a_test_that_writes_must_hijack_the_real_path`.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

RACINE = Path.home() / "Documents" / "Promptuino"
DATA_DIR = RACINE / "data"
DEFAULT_WORKSPACE = RACINE / "projets"

# Ce qui vivait a plat dans `~/Documents/Promptuino/` avant le 2026-08-28.
# Liste EXPLICITE : une migration qui deplacerait << tout ce qui traine >>
# emporterait aussi les debris de l'ancien arduino-cli (`libraries/`, `deps/`,
# un `projects/` vide), qui n'ont rien a faire dans `data/`.
_A_MIGRER = (
    "session.json",
    "components.json",
    "component-libs.json",
    "registry-cache.json",
    "config.json",
    "model",
    "crash-reports",
)


def _migrer() -> None:
    """Descend les donnees de `~/Documents/Promptuino/` vers `data/`.

    ⚠️ **Appelee a l'IMPORT de ce module, et c'est voulu.** `ui/session.py`
    instancie son singleton au niveau module (`session = Session()`), donc il
    LIT le disque des qu'il est importe : une migration declenchee depuis
    `main()` arriverait trop tard. Ce module etant importe par tous les
    magasins, son import est le seul point qui precede toutes les lectures.

    Prudente par construction : ne deplace qu'une liste connue, n'ecrase
    jamais une cible existante, ne supprime rien, et n'echoue jamais bruyamment
    -- au pire l'app repart sur des donnees vides, ce qu'elle sait deja faire.
    """
    try:
        # ⛔ JAMAIS pendant les tests. Cette fonction DEPLACE de vrais fichiers
        # de l'utilisateur ; declenchee par un simple import depuis un test,
        # elle toucherait ses donnees reelles. `scripts/run_all_tests.py` pose
        # la variable, et un test lance a la main peut faire pareil.
        if os.environ.get("PROMPTUINO_NO_MIGRATION"):
            return
        if not RACINE.is_dir():
            return
        restants = [n for n in _A_MIGRER
                    if (RACINE / n).exists() and not (DATA_DIR / n).exists()]
        if not restants:
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for nom in restants:
            try:
                shutil.move(str(RACINE / nom), str(DATA_DIR / nom))
            except Exception:
                pass          # un fichier verrouille ne doit pas bloquer les autres
    except Exception:
        pass


_migrer()
