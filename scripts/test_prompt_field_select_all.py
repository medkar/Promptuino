"""Champ prompt (_PromptTextEdit) : clic/Tab dans un champ DÉJÀ REMPLI
sélectionne tout le texte (pour le remplacer d'un coup). Champ vide ou focus
programmatique -> pas de sélection.

Qt requis (offscreen) ; skip propre si absent.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFocusEvent
    from PyQt6.QtCore import Qt, QEvent
    _HAS_QT = True
    _APP = QApplication.instance() or QApplication([])
except Exception:
    _HAS_QT = False


def _focus(widget, reason):
    widget.focusInEvent(QFocusEvent(QEvent.Type.FocusIn, reason))
    _APP.processEvents()   # laisse le QTimer(0) -> selectAll se declencher


def test_click_selects_all_when_filled():
    from ui.studio_view import _PromptTextEdit
    w = _PromptTextEdit()
    w.setPlainText("clignoter une LED sur D13")
    _focus(w, Qt.FocusReason.MouseFocusReason)
    assert w.textCursor().selectedText() == "clignoter une LED sur D13"


def test_tab_selects_all_when_filled():
    from ui.studio_view import _PromptTextEdit
    w = _PromptTextEdit()
    w.setPlainText("texte")
    _focus(w, Qt.FocusReason.TabFocusReason)
    assert w.textCursor().selectedText() == "texte"


def test_empty_field_no_selection():
    from ui.studio_view import _PromptTextEdit
    w = _PromptTextEdit()
    _focus(w, Qt.FocusReason.MouseFocusReason)
    assert w.textCursor().selectedText() == ""


def test_programmatic_focus_no_selection():
    """Focus non-clic/non-Tab (ex. setFocus applicatif) -> pas de selectAll."""
    from ui.studio_view import _PromptTextEdit
    w = _PromptTextEdit()
    w.setPlainText("ne pas selectionner")
    _focus(w, Qt.FocusReason.OtherFocusReason)
    assert w.textCursor().selectedText() == ""


TESTS = [
    test_click_selects_all_when_filled,
    test_tab_selects_all_when_filled,
    test_empty_field_no_selection,
    test_programmatic_focus_no_selection,
]


def main() -> None:
    if not _HAS_QT:
        print("SKIP (PyQt6 absent)")
        os._exit(0)
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:
            print(f"FAIL {t.__name__}: {exc}")
            failed += 1
    print(f"OK : {len(TESTS)} tests" if not failed else f"{failed} failed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
