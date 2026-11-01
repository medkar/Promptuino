"""Smoke #29 : selection fonctionnalite -> surlignage + scroll ; survol ->
apercu ; multi. La selection/survol vit dans le CodePanel (dropdown ->
signaux internes). Un seul StudioView par process (contrainte Qt du projet)."""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from ui.studio_view import StudioView
from ui.generation import Feature, assemble

f1 = Feature(id="f1", prompt="led", summary="LED",
             global_lines=["const int PIN_LED = 5;"],
             setup_lines=["pinMode(PIN_LED, OUTPUT);"],
             loop_lines=["digitalWrite(PIN_LED, HIGH);"])
f2 = Feature(id="f2", prompt="buzzer", summary="Buzzer",
             global_lines=["const int PIN_BUZZER = 9;"],
             setup_lines=["pinMode(PIN_BUZZER, OUTPUT);"],
             loop_lines=["tone(PIN_BUZZER, 440);"])

sv = StudioView()
sv._current_mode = "intermediate"
sv._features = [f1, f2]
sv._set_code_with_attribution(assemble([f1, f2]), sv._features)
sv._refresh_feature_chips()

panel = sv._code_panel
owners = sv._editor.line_owners()
assert "f1" in owners and "f2" in owners, owners
print("carte posee:", {o for o in owners if o})

# Selection f2 (chemin dropdown -> _on_chips_selection dans le panneau).
panel.feature_dropdown.selection_changed.emit(["f2"])
assert panel._selected_ids == ["f2"]
sels = sv._editor.extraSelections()
assert any(s.format.background().color().alpha() == 64 for s in sels), \
    "aucun fond de fonctionnalite pose"
# Scroll : le curseur est sur une ligne possedee par f2.
cur_block = sv._editor.textCursor().blockNumber()
assert owners[cur_block] == "f2", (cur_block, owners[cur_block])
print("selection -> surlignage + scroll OK")

# Actions ↻/🗑 posees PAR LIGNE : une paire par fonctionnalite (independamment
# des cases cochees).
assert len(panel.feature_dropdown._delete_btns) == 2, "manque un 🗑 par ligne"
assert len(panel.feature_dropdown._regen_btns) == 2, "manque un ↻ par ligne"
print("actions par ligne presentes OK")

# Survol f1 = apercu ADDITIF ; leave = retombe.
panel.feature_dropdown.hover_preview.emit("f1")
n_hover = len([s for s in sv._editor.extraSelections()
               if s.format.background().color().alpha() == 64])
panel.feature_dropdown.hover_preview.emit("")
n_after = len([s for s in sv._editor.extraSelections()
               if s.format.background().color().alpha() == 64])
assert n_hover > n_after, (n_hover, n_after)
print("hover additif puis retire OK")

# Deselection -> plus de fond de surlignage.
panel.clear_selection()
assert not [s for s in sv._editor.extraSelections()
            if s.format.background().color().alpha() == 64]
print("\nsmoke_test_chip_highlight: ALL OK")
