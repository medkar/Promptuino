"""La barre d'etat nomme le moteur ET son modele, LM Studio compris.

Releve par l'auteur le 2026-11-06 : sur LM Studio, le bas de l'ecran disait
« Modele : lmstudio » -- l'identifiant interne -- au lieu du modele choisi.
`display_name` prevoyait Ollama, ChatGPT et les fournisseurs cloud, et
LM Studio retombait sur son identifiant brut.

Lecture seule : `ai_config._data` est modifie en memoire puis restaure,
jamais enregistre.

Run: python scripts/test_status_bar_model_name.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from ui.ai_config import ai_config  # noqa: E402


class _Config:
    """Pose des valeurs dans `ai_config._data` le temps d'un bloc."""

    def __init__(self, **valeurs):
        self.valeurs, self.avant = valeurs, {}

    def __enter__(self):
        for cle, valeur in self.valeurs.items():
            self.avant[cle] = ai_config._data.get(cle)
            ai_config._data[cle] = valeur

    def __exit__(self, *a):
        for cle, valeur in self.avant.items():
            ai_config._data[cle] = valeur


def test_lmstudio_shows_the_chosen_model_not_its_id():
    with _Config(ai_backend="lmstudio", lmstudio_model="google/gemma-4-e4b"):
        nom = ai_config.display_name()
    assert nom == "LM Studio (google/gemma-4-e4b)", nom


def test_lmstudio_without_a_model_says_so_rather_than_its_id():
    with _Config(ai_backend="lmstudio", lmstudio_model=""):
        nom = ai_config.display_name()
    assert nom == "LM Studio (?)", nom
    assert "lmstudio" not in nom


def test_ollama_is_unchanged():
    with _Config(ai_backend="ollama", ollama_model="gemma4:e2b"):
        assert ai_config.display_name() == "Ollama (gemma4:e2b)"


def test_choosing_a_model_refreshes_the_status_bar_on_every_engine():
    """La barre d'etat se met a jour sur `ai_config.changed`. Le setter
    d'Ollama l'emettait ; ceux de LM Studio et de ChatGPT non -- le bandeau
    gardait l'ancien modele jusqu'a un autre evenement. L'enregistrement est
    neutralise sur l'INSTANCE (c'est lui que les setters appellent) : rien
    n'atteint le fichier de l'utilisateur."""
    recus = []
    ai_config.changed.connect(recus.append)
    ai_config._save_backend = lambda: None
    try:
        for cle in ("lmstudio_model", "chatgpt_model", "ollama_model"):
            avant = getattr(ai_config, cle)
            try:
                recus.clear()
                setattr(ai_config, cle, avant + "-test")
                assert recus, f"{cle} : la barre d'etat n'est pas prevenue"
            finally:
                ai_config._data[cle] = avant
    finally:
        del ai_config._save_backend
        ai_config.changed.disconnect(recus.append)


TESTS = [
    test_lmstudio_shows_the_chosen_model_not_its_id,
    test_lmstudio_without_a_model_says_so_rather_than_its_id,
    test_ollama_is_unchanged,
    test_choosing_a_model_refreshes_the_status_bar_on_every_engine,
]


def _empreinte() -> str:
    import hashlib
    from ui.ai_config import CONFIG_PATH
    return (hashlib.md5(CONFIG_PATH.read_bytes()).hexdigest()
            if CONFIG_PATH.exists() else "-")


def main():
    avant = _empreinte()
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    if _empreinte() != avant:
        failed += 1
        print("FAIL la configuration de l'utilisateur a ete modifiee")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
