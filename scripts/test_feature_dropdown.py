"""FeatureDropdown : sélection multiple cochable + émission au repli."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)
from ui.feature_dropdown import FeatureDropdown
from ui.generation.feature_model import Feature


def _feat(fid, prompt):
    # Feature réel (feature_combo_label lit summary/first_prompt + all_text).
    return Feature(id=fid, prompt=prompt)


def test_button_disabled_when_no_features():
    dd = FeatureDropdown()
    dd.set_features([])
    assert not dd._btn.isEnabled()
    dd.set_features([_feat("f1", "LED"), _feat("f2", "Bouton")])
    assert dd._btn.isEnabled()


def test_multi_select_and_emit_on_close():
    dd = FeatureDropdown()
    got = []
    dd.selection_changed.connect(lambda ids: got.append(list(ids)))
    dd.set_features([_feat("f1", "LED"), _feat("f2", "Bouton"), _feat("f3", "Buzzer")])
    dd._open()
    dd._rows[0][1].setChecked(True)
    dd._rows[2][1].setChecked(True)
    assert dd.selected_ids() == ["f1", "f3"]
    dd._close()                      # repli -> émission
    assert got and got[-1] == ["f1", "f3"]


def test_selection_emitted_live_on_toggle_without_closing():
    # Cocher une case émet la sélection IMMÉDIATEMENT (popup encore ouvert) ->
    # surlignage instantané et persistant, sans attendre la fermeture.
    dd = FeatureDropdown()
    got = []
    dd.selection_changed.connect(lambda ids: got.append(list(ids)))
    dd.set_features([_feat("f1", "LED"), _feat("f2", "Bouton")])
    dd._open()
    dd._rows[0][1].setChecked(True)          # coche f1 -> émission live
    assert got and got[-1] == ["f1"]         # émis SANS avoir refermé
    dd._rows[1][1].setChecked(True)          # coche f2 -> émission live
    assert got[-1] == ["f1", "f2"]
    dd._rows[0][1].setChecked(False)         # décoche f1 -> émission live
    assert got[-1] == ["f2"]


def test_rebuild_keeps_selection_without_spurious_emit():
    # Un rebuild (set_features) restaure l'état coché SANS ré-émettre (connexion
    # toggled posée APRÈS setChecked).
    dd = FeatureDropdown()
    got = []
    dd.set_features([_feat("f1", "LED"), _feat("f2", "Bouton")])
    dd._rows[0][1].setChecked(True)
    dd.selection_changed.connect(lambda ids: got.append(list(ids)))
    dd.set_features([_feat("f1", "LED"), _feat("f2", "Bouton"), _feat("f3", "Buzzer")])
    assert got == []                         # aucune émission pendant le rebuild
    assert dd.selected_ids() == ["f1"]       # sélection préservée


def test_selection_survives_refresh_for_present_ids():
    dd = FeatureDropdown()
    dd.set_features([_feat("f1", "LED"), _feat("f2", "Bouton")])
    dd._open(); dd._rows[0][1].setChecked(True); dd._close()
    dd.set_features([_feat("f1", "LED"), _feat("f2", "Bouton"), _feat("f3", "Buzzer")])
    assert dd.selected_ids() == ["f1"]


def test_clear_selection_emits_empty():
    dd = FeatureDropdown()
    got = []
    dd.selection_changed.connect(lambda ids: got.append(list(ids)))
    dd.set_features([_feat("f1", "LED")])
    dd._open(); dd._rows[0][1].setChecked(True); dd._close()
    dd.clear_selection()
    assert dd.selected_ids() == []
    assert got[-1] == []


def test_busy_disables_button():
    dd = FeatureDropdown()
    dd.set_features([_feat("f1", "LED")])
    dd.set_busy(True)
    assert not dd._btn.isEnabled()
    dd.set_busy(False)
    assert dd._btn.isEnabled()


def test_per_line_actions_one_per_row():
    # Un bouton ↻ et un bouton 🗑 par ligne, independamment des cases cochees.
    dd = FeatureDropdown()
    dd.set_features([_feat("f1", "LED"), _feat("f2", "Bouton")])
    assert len(dd._regen_btns) == 2 and len(dd._delete_btns) == 2
    dd.set_features([_feat("f1", "LED")])    # rebuild -> listes reconstruites
    assert len(dd._regen_btns) == 1 and len(dd._delete_btns) == 1


def test_stable_dropdown_has_no_regen_button():
    dd = FeatureDropdown(can_regenerate=False)
    dd.set_features([_feat("f1", "LED"), _feat("f2", "Bouton")])
    assert dd._regen_btns == []              # pas de ↻ cote stable
    assert len(dd._delete_btns) == 2         # 🗑 par ligne toujours present


def test_per_line_action_emits_its_own_feature():
    # ↻/🗑 d'une ligne agissent sur SA fonctionnalite (pas la selection cochee).
    dd = FeatureDropdown()
    got = {}
    dd.regen_requested.connect(lambda ids: got.__setitem__("regen", list(ids)))
    dd.delete_requested.connect(lambda ids: got.__setitem__("delete", list(ids)))
    dd.set_features([_feat("f1", "LED"), _feat("f2", "Bouton")])
    dd._regen_btns[1].click()                # ligne f2
    dd._delete_btns[0].click()               # ligne f1
    assert got["regen"] == ["f2"]
    assert got["delete"] == ["f1"]


TESTS = [
    test_button_disabled_when_no_features,
    test_multi_select_and_emit_on_close,
    test_selection_emitted_live_on_toggle_without_closing,
    test_rebuild_keeps_selection_without_spurious_emit,
    test_selection_survives_refresh_for_present_ids,
    test_clear_selection_emits_empty,
    test_busy_disables_button,
    test_per_line_actions_one_per_row,
    test_stable_dropdown_has_no_regen_button,
    test_per_line_action_emits_its_own_feature,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
