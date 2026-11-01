"""Smoke test: topbar undo/redo arrows + Édition menu plumbing.

Verifies that the TopBar exposes two arrow buttons placed just LEFT of the
mode selector ([undo][redo] | selector), visible only when the selector is
(Studio tab), emitting undo_clicked/redo_clicked without stealing focus;
that StudioView exposes the public API the Édition menu + arrows call
(undo / redo / copy_code_to_clipboard / clear_prompt); and that the new
i18n keys exist in the 4 languages.

Run: python scripts/smoke_test_undo_redo_ui.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ui.i18n import TRANSLATIONS
from ui.topbar import TopBar

app = QApplication.instance() or QApplication(sys.argv)

# 1) i18n: the 7 new keys exist and are non-empty in FR/EN/ES/IT.
KEYS = ("menu_edit", "mn_undo", "mn_redo", "mn_copy_code",
        "mn_clear_prompt", "topbar_undo_tip", "topbar_redo_tip")
for code, strings in TRANSLATIONS.items():
    for key in KEYS:
        val = getattr(strings, key, None)
        assert val, f"i18n key {key!r} missing/empty for lang {code!r}"
print("i18n keys OK (4 languages)")

# 2) TopBar: arrows hidden by default, shown with the mode selector,
#    positioned [undo][redo] just left of it, and emitting the signals.
bar = TopBar()
bar.resize(1200, 48)
assert not bar._btn_undo.isVisible() and not bar._btn_redo.isVisible()

bar.show()
bar.set_mode_visible(True)
assert bar._btn_undo.isVisible() and bar._btn_redo.isVisible()

sel_x = bar.mode_selector.geometry().x()
undo_x, redo_x = bar._btn_undo.x(), bar._btn_redo.x()
assert undo_x == 8, f"undo must be anchored at the left edge (8px), got {undo_x}"
assert undo_x < redo_x < sel_x, (
    f"expected [undo][redo] left of selector, got undo={undo_x} "
    f"redo={redo_x} selector={sel_x}"
)
assert bar._btn_undo.toolTip() and bar._btn_redo.toolTip()
# A click must not steal the focus from the editor/prompt.
assert bar._btn_undo.focusPolicy() == Qt.FocusPolicy.NoFocus
assert bar._btn_redo.focusPolicy() == Qt.FocusPolicy.NoFocus

fired = []
bar.undo_clicked.connect(lambda: fired.append("undo"))
bar.redo_clicked.connect(lambda: fired.append("redo"))
bar._btn_undo.click()
bar._btn_redo.click()
assert fired == ["undo", "redo"], fired

bar.set_mode_visible(False)
assert not bar._btn_undo.isVisible() and not bar._btn_redo.isVisible()
print("TopBar arrows OK (visibility, position, signals, NoFocus)")

# 3) StudioView public API used by the Édition menu + arrows.
from ui.studio_view import StudioView
for name in ("undo", "redo", "copy_code_to_clipboard", "clear_prompt"):
    assert callable(getattr(StudioView, name, None)), f"StudioView.{name} missing"
print("StudioView API OK (undo/redo/copy_code_to_clipboard/clear_prompt)")

print("\nsmoke_test_undo_redo_ui: ALL OK")
