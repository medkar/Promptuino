"""Test offscreen du bouton additif « Corriger dans Studio » (sous-projet 2).

Run : QT_QPA_PLATFORM=offscreen python scripts/test_correction_studio_offer.py
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from PyQt6.QtWidgets import QApplication, QPushButton
from ui.chat.chat_controller import ChatController
from ui.chat.chat_view import ChatView
from ui.i18n import lang_manager, TRANSLATIONS

_qapp = QApplication.instance() or QApplication([])
_keep_alive: list = []


def _make_view():
    view = ChatView(ChatController(backend=None, user_mode="beginner"))
    _keep_alive.append(view)
    return view


def _offer_buttons(view):
    """Boutons « Corriger dans Studio » presents dans la vue."""
    label = lang_manager.current.chat_correction_to_studio
    return [b for b in view.findChildren(QPushButton) if b.text() == label]


def test_i18n_offer_key_all_langs():
    for code, strings in TRANSLATIONS.items():
        v = getattr(strings, "chat_correction_studio_offer", None)
        assert isinstance(v, str) and v.strip(), f"{code}.chat_correction_studio_offer manquant"
    print("  [OK] cle i18n chat_correction_studio_offer dans les 4 langues")


def test_offer_appears_and_emits_corrected_prompt():
    view = _make_view()
    captured = []
    # Le bouton route vers le flux Modifier (signal request_modify_in_studio),
    # avec le texte BRUT de l'eleve : le prefixe magique « CORRECTION » a ete
    # retire (703a528), le marqueur d'intention passe autrement.
    view.request_modify_in_studio.connect(captured.append)
    view._streaming_bubble = None
    view._streaming_user_text = "mets la LED sur D9"
    view._streaming_correction_intent = True
    view._pending_correction = None
    view._on_stream_done("Tu peux changer la broche dans loop().")
    btns = _offer_buttons(view)
    assert len(btns) == 1, f"attendu 1 bouton offer, vu {len(btns)}"
    btns[0].click()
    assert captured == ["mets la LED sur D9"], captured
    print("  [OK] bouton offer present + emet le texte user brut (flux Modifier)")


def test_no_offer_when_no_correction_intent():
    view = _make_view()
    view._streaming_bubble = None
    view._streaming_user_text = "comment marche un pull-up ?"
    view._streaming_correction_intent = False
    view._pending_correction = None
    view._on_stream_done("Un pull-up maintient la broche a HIGH au repos.")
    assert _offer_buttons(view) == [], "aucun bouton offer attendu"
    print("  [OK] pas de bouton offer si pas d'intention de correction")


def test_no_offer_when_filet_armed():
    view = _make_view()
    view._streaming_bubble = None
    view._streaming_user_text = "corrige ce composant"
    view._streaming_correction_intent = True
    view._pending_correction = {"pins": "A4/A5"}   # filet arme
    view._on_stream_done("Reponse du modele dans la conversation de correction.")
    assert _offer_buttons(view) == [], "pas de double bouton en session filet armee"
    print("  [OK] pas de bouton offer general en session filet armee")


TESTS = [
    test_i18n_offer_key_all_langs,
    test_offer_appears_and_emits_corrected_prompt,
    test_no_offer_when_no_correction_intent,
    test_no_offer_when_filet_armed,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
