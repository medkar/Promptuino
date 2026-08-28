"""GenerationModal : default_action ne dépend plus du préfixe CORRECTION ;
default_override force l'action pré-sélectionnée.
Run : python scripts/test_gen_modal_default_override.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.generation.feature_model import Feature
from ui.generation.gen_modal import (
    GenerationModal, default_action, REGENERATE, ADD, CORRECT,
)

_FEATS = [Feature(id="f1", prompt="p", summary="Clignote la LED — D5")]


def test_default_action_ignores_correction_prefix():
    assert default_action(_FEATS, "CORRECTION change la LED") == ADD
    assert default_action([], "CORRECTION peu importe") == REGENERATE


def test_default_override_forces_correct():
    m = GenerationModal(_FEATS, "change la LED", None, default_override=CORRECT)
    assert m._rb[CORRECT].isChecked() is True


def test_no_override_uses_default_add_when_features():
    m = GenerationModal(_FEATS, "ajoute un buzzer", None)
    assert m._rb[ADD].isChecked() is True


TESTS = [
    test_default_action_ignores_correction_prefix,
    test_default_override_forces_correct,
    test_no_override_uses_default_add_when_features,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}", flush=True)
            os._exit(1)
    print(f"OK : {len(TESTS)} tests", flush=True)
    os._exit(0)


if __name__ == "__main__":
    main()
