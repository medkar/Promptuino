"""La reflexion en configuration : un reglage par moteur local, un niveau
pour ChatGPT (TODO #123, decisions de l'auteur du 2026-11-06).

DESACTIVEE par defaut sur les moteurs locaux -- avant, Ollama envoyait deja
`think: false`, mais LM Studio laissait gemma-4 reflechir, et la reponse
sortait coupee. ChatGPT : le cran du milieu.

Fichier de configuration ISOLE : la constante de module `CONFIG_PATH` est
detournee vers un dossier temporaire.

Run : python scripts/test_ai_config_reflexion.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.ai_config as aicfg
from ui.ai_config import AIConfig

_VRAI_CHEMIN = aicfg.CONFIG_PATH


def _fresh(tmp: str) -> AIConfig:
    aicfg.CONFIG_PATH = Path(tmp) / "config.json"
    return AIConfig()


def test_thinking_is_off_by_default_and_chatgpt_sits_in_the_middle():
    with tempfile.TemporaryDirectory() as tmp:
        c = _fresh(tmp)
        assert c.ollama_think is False
        assert c.lmstudio_think is False
        assert c.chatgpt_reasoning == "medium"


def test_each_setting_persists_on_its_own():
    with tempfile.TemporaryDirectory() as tmp:
        c = _fresh(tmp)
        c.ollama_think = True
        c.chatgpt_reasoning = "high"
        relu = _fresh(tmp)
        assert relu.ollama_think is True
        assert relu.lmstudio_think is False
        assert relu.chatgpt_reasoning == "high"


def test_an_unknown_level_falls_back_to_the_middle():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "config.json").write_text(
            json.dumps({"chatgpt_reasoning": "turbo"}), encoding="utf-8")
        c = _fresh(tmp)
        assert c.chatgpt_reasoning == "medium"
        c.chatgpt_reasoning = "nimporte"
        assert c.chatgpt_reasoning == "medium"


def test_a_change_tells_the_status_bar():
    """Meme signal que les autres reglages du moteur : la barre d'etat et
    l'onglet IA s'y abonnent."""
    with tempfile.TemporaryDirectory() as tmp:
        c = _fresh(tmp)
        vus = []
        c.changed.connect(vus.append)
        c.lmstudio_think = True
        c.lmstudio_think = True          # inchange : pas de second signal
        c.chatgpt_reasoning = "low"
        assert len(vus) == 2, vus


TESTS = [
    test_thinking_is_off_by_default_and_chatgpt_sits_in_the_middle,
    test_each_setting_persists_on_its_own,
    test_an_unknown_level_falls_back_to_the_middle,
    test_a_change_tells_the_status_bar,
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
