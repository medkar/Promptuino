"""Le reglage de contexte (le MEME widget sur Ollama et LM Studio, 2026-11-06).

Decisions de l'auteur : du plancher (16 384) au maximum du modele, par pas de
1 024 ; aucune valeur sous le plancher ; un modele trop petit est bloque.
Aucune ecriture disque : `_save_backend` est neutralise sur l'instance.

Run : python scripts/test_ia_ollama_ctx_slider.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])   # keep a module-level ref

from ui.contexte_curseur import CurseurContexte, tokens


def test_the_range_follows_the_models_maximum():
    w = CurseurContexte()
    assert w.regler(131072, 20000) == 19456, "ramene sur un pas"
    assert w._slider.minimum() * 1024 == 16384
    assert w._slider.maximum() * 1024 == 131072
    assert w.regler(32768, 65536) == 32768, "jamais au-dela du modele"
    assert w.regler(131072, 2048) == 16384, "jamais sous le plancher"


def test_setting_the_range_never_counts_as_a_user_choice():
    """Choisir un modele ou rouvrir la page ne doit rien enregistrer."""
    w = CurseurContexte()
    recus = []
    w.valeur_validee.connect(recus.append)
    w.regler(131072, 65536)
    w.regler(32768, 65536)
    assert recus == [], recus


def test_a_keyboard_step_is_a_choice_and_says_its_value():
    w = CurseurContexte()
    w.regler(131072, 16384)
    recus = []
    w.valeur_validee.connect(recus.append)
    w._slider.setValue(w._slider.value() + 4)          # comme un PageUp
    assert recus == [20480], recus
    assert w._lbl_valeur.text() == tokens(20480)


def test_an_unusable_model_blocks_the_setting():
    w = CurseurContexte()
    w.bloquer(8192)
    assert not w._slider.isEnabled()
    assert w._lbl_valeur.text() == tokens(8192)


def test_the_ollama_page_writes_the_setting_and_both_engines_share_it():
    from ui.ai_config import ai_config
    from ui.ia_view import _BackendSection
    ai_config._save_backend = lambda: None    # no disk writes during the test
    avant = ai_config._data["ollama_num_ctx"]
    try:
        sec = _BackendSection("ollama")
        sec._ctx.regler(131072, 16384)
        sec._ctx._slider.setValue(32)                  # 32 x 1 024
        assert ai_config.ollama_num_ctx == 32768
    finally:
        ai_config._data["ollama_num_ctx"] = avant
        del ai_config._save_backend


TESTS = [
    test_the_range_follows_the_models_maximum,
    test_setting_the_range_never_counts_as_a_user_choice,
    test_a_keyboard_step_is_a_choice_and_says_its_value,
    test_an_unusable_model_blocks_the_setting,
    test_the_ollama_page_writes_the_setting_and_both_engines_share_it,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)   # bypass Qt teardown (avoids GC-order crash on exit)


if __name__ == "__main__":
    main()
