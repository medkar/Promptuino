"""Smoke: feature transfer popup on a real StudioView (offscreen).
3 IA features (2 linked by PIN_LED), dialog built (not exec'ed), links
computed, transfer simulated through _do_transfer, then applied through the
studio path. ASCII-only prints (Windows console)."""
import os
import sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.studio_view import StudioView
from ui.generation import Feature, assemble
from ui.feature_transfer_dialog import FeatureTransferDialog

f1 = Feature(id="f1", prompt="allume la led", summary="LED",
             global_lines=["const int PIN_LED = 5;"],
             setup_lines=["pinMode(PIN_LED, OUTPUT);"],
             loop_lines=["digitalWrite(PIN_LED, HIGH);"])
f2 = Feature(id="f2", prompt="clignote", summary="Clignotement",
             loop_lines=["digitalWrite(PIN_LED, LOW);", "delay(500);"])
f3 = Feature(id="f3", prompt="buzzer", summary="Buzzer",
             global_lines=["const int PIN_BUZZER = 9;"],
             loop_lines=["tone(PIN_BUZZER, 440);"])

sv = StudioView()
sv._on_mode_changed("advanced")
sv._features = [f1, f2, f3]
sv._set_code_with_attribution(assemble([f1, f2, f3]), sv._features)
sv.save_project = lambda *a, **k: None          # no disk writes in smoke

# Build the dialog exactly like the chevron handler does.
dlg = FeatureTransferDialog(sv._features, sv._stable_features, parent=sv)
assert len(dlg._cards["ia"]) == 3 and len(dlg._cards["stable"]) == 0
pairs = dlg._links_overlay.edge_pairs()
assert ("ia", "f1", "f2") in pairs, pairs
print("dialog built, link f1->f2 detected:", pairs)

# Drag f2 to stable (via the drop router): provider f1 must travel along.
dlg._handle_drop("f2", "ia", "stable", 0)
assert [c.fid for c in dlg._cards["stable"]] == ["f1", "f2"]
assert ("stable", "f1", "f2") in dlg._links_overlay.edge_pairs()
print("transfer f2 -> stable carried f1, links follow")

# Trash f3 on the IA side (delayed), recap reflects both gestures.
dlg._toggle_delete("f3", "ia")
print("recap line:", repr(dlg._lbl_recap.text()))
assert dlg.staging.has_changes()

# Apply through the studio path (same call the chevron handler makes).
ia, stable, removed = dlg.result()
sv._apply_feature_transfer(ia, stable, removed,
                           ia_changed=True, stable_changed=True,
                           recap_msg="smoke")
assert [f.id for f in sv._features] == ["f1", "f2"]          # f3 deleted
assert [f.id for f in sv._stable_features] == ["f1", "f2"]
st_code = sv._stable_panel.editor.toPlainText()
assert "PIN_LED" in st_code and "PIN_BUZZER" not in st_code
assert "PIN_BUZZER" not in sv.get_code()
assert "f1" in sv._stable_panel.editor.line_owners()
print("apply: IA=[f1,f2] stable=[f1,f2], code + attribution coherents")

print("\nsmoke_test_feature_transfer: ALL OK")
