"""Tests de la taille de contexte en configuration : Ollama ET LM Studio.

Decision de l'auteur du 2026-11-06 : la meme mecanique sur les deux
moteurs, de 16 384 (ce que Promptuino demande) au maximum du modele, par pas
de 1 024 -- plus les cinq paliers 2 048..32 768 d'Ollama. Le maximum depend
du MODELE : il s'applique a l'usage (`ui.contexte.ramener`), pas ici.

Fichier de configuration ISOLE : la constante de module `CONFIG_PATH` est
detournee vers un dossier temporaire.

Run : python scripts/test_ai_config_ollama_ctx.py
"""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.ai_config as aicfg
from ui.ai_config import AIConfig

_VRAI_CHEMIN = aicfg.CONFIG_PATH


def _fresh(tmp: str) -> AIConfig:
    """A config instance bound to an isolated temp file."""
    aicfg.CONFIG_PATH = Path(tmp) / "config.json"
    return AIConfig()


def test_both_engines_default_to_what_promptuino_needs():
    with tempfile.TemporaryDirectory() as tmp:
        c = _fresh(tmp)
        assert c.ollama_num_ctx == 16384
        assert c.lmstudio_num_ctx == 16384


def test_any_step_persists_on_both_engines():
    with tempfile.TemporaryDirectory() as tmp:
        c = _fresh(tmp)
        c.ollama_num_ctx = 20480
        c.lmstudio_num_ctx = 65536
        relu = _fresh(tmp)
        assert (relu.ollama_num_ctx, relu.lmstudio_num_ctx) == (20480, 65536)


def test_a_value_lands_on_a_step_never_under_the_floor():
    with tempfile.TemporaryDirectory() as tmp:
        c = _fresh(tmp)
        c.ollama_num_ctx = 20001
        assert c.ollama_num_ctx == 19456
        c.lmstudio_num_ctx = 100
        assert c.lmstudio_num_ctx == 16384
        c.ollama_num_ctx = "abc"
        assert c.ollama_num_ctx == 16384


def test_an_old_small_ollama_setting_is_raised_to_the_floor():
    """Avant le 2026-11-06, le curseur proposait 2 048..8 192 : une valeur
    enregistree ainsi passe au plancher a la lecture."""
    import json
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "config.json").write_text(
            json.dumps({"ollama_num_ctx": 8192}), encoding="utf-8")
        assert _fresh(tmp).ollama_num_ctx == 16384


TESTS = [
    test_both_engines_default_to_what_promptuino_needs,
    test_any_step_persists_on_both_engines,
    test_a_value_lands_on_a_step_never_under_the_floor,
    test_an_old_small_ollama_setting_is_raised_to_the_floor,
]


def main() -> int:
    failed = 0
    try:
        for t in TESTS:
            try:
                t(); print(f"OK   {t.__name__}")
            except Exception as e:
                failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    finally:
        aicfg.CONFIG_PATH = _VRAI_CHEMIN
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
