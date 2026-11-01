"""open_modify_flow (flux GUIDÉ) : un popup explicatif ; si l'utilisateur
confirme, on bascule Débutant->Intermédiaire et on recopie le texte dans le
prompt, mais on N'OUVRE PAS la modale à sa place. Si l'utilisateur annule, rien
ne change. On monkeypatche `_confirm_modify_guidance` pour ne pas bloquer sur
le QMessageBox, et `_open_action_modal` pour prouver qu'il n'est jamais appelé.
Run : python scripts/test_studio_open_modify_flow.py
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

from ui.studio_view import StudioView


def test_confirmed_switches_and_fills_without_opening_modal():
    v = StudioView()
    v._on_mode_changed("beginner")
    opened = {"n": 0}
    v._confirm_modify_guidance = lambda: True          # popup confirmé
    v._open_action_modal = lambda *a, **k: opened.__setitem__("n", opened["n"] + 1)
    v.open_modify_flow("LED sur D9 : clignote plus vite")
    _APP.processEvents()

    assert v._current_mode == "intermediate", v._current_mode   # basculé
    assert v.get_prompt() == "LED sur D9 : clignote plus vite"  # prompt rempli
    assert opened["n"] == 0, "on n'ouvre PAS la modale à la place de l'utilisateur"
    print("  OK — confirmé : bascule + prompt, sans ouvrir la modale")


def test_cancelled_does_nothing():
    v = StudioView()
    v._on_mode_changed("beginner")
    v._confirm_modify_guidance = lambda: False         # popup annulé
    v.open_modify_flow("fais clignoter une LED")
    _APP.processEvents()

    assert v._current_mode == "beginner", v._current_mode      # pas de bascule
    assert v.get_prompt() != "fais clignoter une LED"          # prompt non rempli
    print("  OK — annulé : aucun changement")


TESTS = [
    test_confirmed_switches_and_fills_without_opening_modal,
    test_cancelled_does_nothing,
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
