"""TODO #31 — synthetic `manual` feature (hand edits) + right-click attribution.

Step 1: MANUAL_ID + ai_features + intent exclusion (recombine / review C) +
recombine preservation. (Later steps add capture, dropdown, context menu, merge.)
"""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)


def test_ai_features_excludes_manual():
    from ui.generation.feature_model import Feature, ai_features, MANUAL_ID
    f1 = Feature(id="f1", prompt="a")
    m = Feature(id=MANUAL_ID, prompt="should-not-leak")
    assert [f.id for f in ai_features([f1, m])] == ["f1"]


def test_build_intent_excludes_manual_even_with_prompt():
    # The manual feature is excluded by ID (not just by its empty prompt): even
    # if it carried a bogus prompt, it must never reach the review-C intent.
    from ui.generation.feature_model import Feature, MANUAL_ID
    from ui.generation.behavior_review import build_intent
    f1 = Feature(id="f1", prompt="clignoter une led")
    m = Feature(id=MANUAL_ID, prompt="SENTINEL manual intent")
    intent = build_intent([f1, m])
    assert "clignoter" in intent
    assert "SENTINEL" not in intent


def test_recombine_preserves_manual_and_excludes_its_intent():
    # Recombine collapses the AI features into f1 — but the `manual` feature has
    # no intent, so it must be PRESERVED (last), not lost, and never appear in
    # the combined prompt.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature, MANUAL_ID
    v = StudioView()
    v._on_mode_changed("advanced")
    real = Feature(id="f1", prompt="blink led",
                   loop_lines=["digitalWrite(13, HIGH);"])
    manual = Feature(id=MANUAL_ID, prompt="SENTINEL", summary="Éditions manuelles",
                     loop_lines=["Serial.println(42);"])
    v._features = [real, manual]
    captured = {}

    def _fake_from_parsed(p, fid, prompt, summary, prompts=None,
                          carry_from=None):
        captured.update(prompt=prompt)
        return Feature(id=fid, prompt=prompt, prompts=prompts or [])
    v._feature_from_parsed = _fake_from_parsed
    v._set_code_with_attribution = lambda *a, **k: None
    v._start_assembly_verify = lambda: True          # stop before finalize
    v._on_recombine_done("void setup(){}\nvoid loop(){}\n")
    assert [f.id for f in v._features] == ["f1", MANUAL_ID]   # manual preserved, last
    assert "blink led" in captured["prompt"]
    assert "SENTINEL" not in captured["prompt"]              # manual intent excluded


def test_dropdown_manual_row_no_regen_deletable_labeled():
    # In a regen-enabled (IA) window, the `manual` row shows NO ↻ (no prompt to
    # replay), stays deletable (🗑), and uses the i18n label.
    from ui.feature_dropdown import FeatureDropdown
    from ui.generation.feature_model import Feature, MANUAL_ID
    from ui.i18n import lang_manager
    dd = FeatureDropdown()                       # IA window: regen enabled
    dd.set_features([Feature(id="f1", prompt="LED"),
                     Feature(id=MANUAL_ID, prompt="", summary="x"),
                     Feature(id="f2", prompt="Bouton")])
    assert len(dd._regen_btns) == 2              # only the 2 real features
    assert len(dd._delete_btns) == 3             # manual deletable too
    manual_cb = next(cb for fid, cb in dd._rows if fid == MANUAL_ID)
    assert manual_cb.text() == lang_manager.current.studio_manual_feature_label


def _f1_with_trailing_orphan(before: bool):
    """(features, code, owners) for a single feature whose loop gained ONE
    hand-typed line — placed AFTER (trailing) or BEFORE (interleaved) its own
    loop line, with owner None."""
    from ui.generation.feature_model import Feature
    from ui.generation.assembler import assemble_with_map
    f1 = Feature(id="f1", prompt="led", loop_lines=["digitalWrite(13, HIGH);"])
    code, owners = assemble_with_map([f1])
    lines = code.split("\n"); owners = list(owners)
    idx = lines.index("  digitalWrite(13, HIGH);")
    at = idx if before else idx + 1
    lines.insert(at, "  Serial.println(1);"); owners.insert(at, None)
    return [f1], "\n".join(lines), owners


def test_sync_captures_trailing_orphan_to_manual():
    from ui.generation.feature_model import MANUAL_ID
    from ui.generation.feature_resync import sync_features_from_editor
    from ui.generation import assemble, is_dirty
    feats, code, owners = _f1_with_trailing_orphan(before=False)
    res = sync_features_from_editor(feats, code, owners, manual_id=MANUAL_ID)
    assert [f.id for f in res] == ["f1", MANUAL_ID]        # manual last
    assert "Serial.println(1);" in res[-1].loop_lines      # captured
    assert not is_dirty(assemble(res), code)               # round-trips


def test_sync_interleaved_orphan_does_not_roundtrip_with_manual():
    # An orphan BEFORE the feature line, regrouped last as manual, reorders ->
    # assemble no longer reproduces the editor (the caller then falls back).
    from ui.generation.feature_model import MANUAL_ID
    from ui.generation.feature_resync import sync_features_from_editor
    from ui.generation import assemble, is_dirty
    feats, code, owners = _f1_with_trailing_orphan(before=True)
    with_manual = sync_features_from_editor(feats, code, owners, manual_id=MANUAL_ID)
    assert is_dirty(assemble(with_manual), code)           # interleaved -> mismatch
    neighbor = sync_features_from_editor(feats, code, owners)   # legacy mode
    assert [f.id for f in neighbor] == ["f1"]              # no manual
    assert not is_dirty(assemble(neighbor), code)          # attached to f1, order kept


def test_verified_resync_captures_standalone_hand_edit():
    from ui.studio_view import StudioView
    from ui.generation.feature_model import MANUAL_ID
    v = StudioView()
    v._on_mode_changed("advanced")
    feats, code, owners = _f1_with_trailing_orphan(before=False)
    v._features = feats
    ed = v._editor
    ed.blockSignals(True); ed.setPlainText(code); ed.blockSignals(False)
    ed.set_line_owners(owners)
    out = v._verified_resync(v._features, ed, capture_manual=True)
    assert [f.id for f in out] == ["f1", MANUAL_ID]
    assert "Serial.println(1);" in out[-1].loop_lines


def test_verified_resync_interleaved_falls_back_to_neighbor():
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    feats, code, owners = _f1_with_trailing_orphan(before=True)
    v._features = feats
    ed = v._editor
    ed.blockSignals(True); ed.setPlainText(code); ed.blockSignals(False)
    ed.set_line_owners(owners)
    out = v._verified_resync(v._features, ed, capture_manual=True)
    assert [f.id for f in out] == ["f1"]                   # no manual (fallback)
    assert "Serial.println(1);" in out[0].loop_lines       # attached to f1


def test_apply_verified_resync_captures_manual_without_touching_text():
    # The commit path adds `manual`, re-poses owners, saves — and NEVER re-sets
    # the editor text (cursor + undo stack preserved).
    from ui.studio_view import StudioView
    from ui.generation.feature_model import MANUAL_ID
    v = StudioView()
    v._on_mode_changed("advanced")
    feats, code, owners = _f1_with_trailing_orphan(before=False)
    v._features = feats
    ed = v._editor
    ed.blockSignals(True); ed.setPlainText(code); ed.blockSignals(False)
    ed.set_line_owners(owners)
    saved = {"n": 0}
    v.save_project = lambda *a, **k: saved.__setitem__("n", saved["n"] + 1)
    v._apply_verified_resync("ia", capture_manual=True, save=True)
    assert [f.id for f in v._features] == ["f1", MANUAL_ID]   # captured
    assert ed.toPlainText() == code                          # text untouched
    assert saved["n"] == 1                                    # persisted


def test_schedule_manual_capture_skipped_when_busy():
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed("advanced")
    v._loading = False
    v._manual_capture_timer.stop()
    v._gen_busy = object()                       # a generation is running
    v._schedule_manual_capture("ia")
    assert not v._manual_capture_timer.isActive()   # not scheduled while busy
    v._gen_busy = None
    v._schedule_manual_capture("ia")
    assert v._manual_capture_timer.isActive()        # scheduled when idle


def test_feature_menu_items_always_offers_manual():
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature, MANUAL_ID
    v = StudioView(); v._on_mode_changed("advanced")
    v._features = [Feature(id="f1", prompt="led")]
    ids = [i for i, _l, _c in v._feature_menu_items("ia")]
    assert ids == ["f1", MANUAL_ID]                # manual offered even if absent
    v._features = [Feature(id="f1", prompt="led"), Feature(id=MANUAL_ID, prompt="")]
    ids = [i for i, _l, _c in v._feature_menu_items("ia")]
    assert ids.count(MANUAL_ID) == 1              # not duplicated when present


def test_selected_line_range_from_selection():
    from ui.code_editor import CodeEditor
    from PyQt6.QtGui import QTextCursor
    ed = CodeEditor()
    ed.setPlainText("l0\nl1\nl2\nl3\n")
    cur = ed.textCursor()
    cur.setPosition(ed.document().findBlockByNumber(1).position())
    cur.setPosition(ed.document().findBlockByNumber(2).position() + 1,
                    QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(cur)
    assert ed._selected_line_range(None) == (1, 2)   # event unused with a selection


def _f1_two_loop_lines():
    from ui.generation.feature_model import Feature
    from ui.generation.assembler import assemble_with_map
    f1 = Feature(id="f1", prompt="led",
                 loop_lines=["Serial.println(1);", "digitalWrite(13, HIGH);"])
    code, owners = assemble_with_map([f1])
    return f1, code, list(owners)


def test_assign_trailing_line_to_manual_is_canonical():
    from ui.studio_view import StudioView
    from ui.generation.feature_model import MANUAL_ID
    v = StudioView(); v._on_mode_changed("advanced")
    f1, code, owners = _f1_two_loop_lines()
    v._features = [f1]
    ed = v._editor
    ed.blockSignals(True); ed.setPlainText(code); ed.blockSignals(False)
    ed.set_line_owners(owners)
    v.save_project = lambda *a, **k: None
    idx = code.split("\n").index("  digitalWrite(13, HIGH);")   # LAST loop line
    v._on_assign_lines(idx, idx, MANUAL_ID, "ia")
    manual = next(f for f in v._features if f.id == MANUAL_ID)
    assert "digitalWrite(13, HIGH);" in manual.loop_lines        # canonical move
    assert "digitalWrite(13, HIGH);" not in v._features[0].loop_lines
    assert ed.toPlainText() == code                              # text untouched


def test_assign_interleaved_line_keeps_visual_override():
    # Re-attributing a line that is NOT a clean trailing block can't round-trip
    # (manual is last) -> the model stays best-effort, but the visual override
    # + the dropdown presence are guaranteed.
    from ui.studio_view import StudioView
    from ui.generation.feature_model import MANUAL_ID
    v = StudioView(); v._on_mode_changed("advanced")
    f1, code, owners = _f1_two_loop_lines()
    v._features = [f1]
    ed = v._editor
    ed.blockSignals(True); ed.setPlainText(code); ed.blockSignals(False)
    ed.set_line_owners(owners)
    v.save_project = lambda *a, **k: None
    idx = code.split("\n").index("  Serial.println(1);")         # FIRST loop line
    v._on_assign_lines(idx, idx, MANUAL_ID, "ia")
    assert ed.line_owners()[idx] == MANUAL_ID                    # visual override
    assert ed.toPlainText() == code                             # text untouched
    assert any(f.id == MANUAL_ID for f in v._features)          # surfaced in dropdown


def test_reassign_all_manual_lines_drops_empty_manual():
    # After moving every manual line to a real feature, the now-empty `manual`
    # bucket must disappear from the model/dropdown (user-reported 2026-07-07).
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature, MANUAL_ID
    from ui.generation.assembler import assemble_with_map
    v = StudioView(); v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led", loop_lines=["digitalWrite(13, HIGH);"])
    manual = Feature(id=MANUAL_ID, prompt="", loop_lines=["Serial.println(1);"])
    v._features = [f1, manual]
    code, owners = assemble_with_map(v._features)
    ed = v._editor
    ed.blockSignals(True); ed.setPlainText(code); ed.blockSignals(False)
    ed.set_line_owners(list(owners))
    v.save_project = lambda *a, **k: None
    idx = code.split("\n").index("  Serial.println(1);")
    v._on_assign_lines(idx, idx, "f1", "ia")            # move manual's only line
    assert all(f.id != MANUAL_ID for f in v._features)  # empty manual dropped


def test_sync_drops_empty_manual():
    # sync_features_from_editor never returns an empty `manual`, even if one was
    # present in the input.
    from ui.generation.feature_model import Feature, MANUAL_ID
    from ui.generation.feature_resync import sync_features_from_editor
    from ui.generation.assembler import assemble_with_map
    f1 = Feature(id="f1", prompt="led", loop_lines=["digitalWrite(13, HIGH);"])
    feats = [f1, Feature(id=MANUAL_ID, prompt="")]      # manual already empty
    code, owners = assemble_with_map([f1])              # no line owned by manual
    res = sync_features_from_editor(feats, code, list(owners), manual_id=MANUAL_ID)
    assert all(f.id != MANUAL_ID for f in res)


def test_delete_manual_removes_its_code():
    from ui.studio_view import StudioView
    from ui.generation.feature_model import Feature, MANUAL_ID
    from ui.generation import assemble
    v = StudioView(); v._on_mode_changed("advanced")
    f1 = Feature(id="f1", prompt="led", loop_lines=["digitalWrite(13, HIGH);"])
    manual = Feature(id=MANUAL_ID, prompt="", loop_lines=["Serial.println(1);"])
    v._features = [f1, manual]
    v._set_code_with_attribution(assemble(v._features), v._features)
    assert "Serial.println(1);" in v.get_code()
    v.save_project = lambda *a, **k: None
    v._delete_features({MANUAL_ID}, target="ia")
    assert "Serial.println(1);" not in v.get_code()      # manual code removed
    assert all(f.id != MANUAL_ID for f in v._features)


def test_transfer_manual_copies_when_dest_has_none():
    from ui.feature_transfer import TransferStaging
    from ui.generation.feature_model import Feature, MANUAL_ID
    ia = [Feature(id="f1", prompt="led"),
          Feature(id=MANUAL_ID, prompt="", loop_lines=["Serial.println(1);"])]
    st = TransferStaging(ia, [])
    st.transfer(MANUAL_ID, "ia", "stable", 0)
    _, stable_out, _ = st.result()
    m = [f for f in stable_out if f.id == MANUAL_ID]
    assert len(m) == 1 and "Serial.println(1);" in m[0].loop_lines


def test_transfer_manual_merges_into_existing_and_is_idempotent():
    from ui.feature_transfer import TransferStaging
    from ui.generation.feature_model import Feature, MANUAL_ID
    ia_m = Feature(id=MANUAL_ID, prompt="", loop_lines=["Serial.println(1);"])
    st_m = Feature(id=MANUAL_ID, prompt="", loop_lines=["digitalWrite(2, HIGH);"])
    st = TransferStaging([Feature(id="f1", prompt="led"), ia_m], [st_m])
    st.transfer(MANUAL_ID, "ia", "stable", 99)
    _, out, _ = st.result()
    m = [f for f in out if f.id == MANUAL_ID]
    assert len(m) == 1                                    # single bucket
    assert "digitalWrite(2, HIGH);" in m[0].loop_lines    # dest kept
    assert "Serial.println(1);" in m[0].loop_lines        # source merged
    st.transfer(MANUAL_ID, "ia", "stable", 99)            # again -> idempotent
    _, out2, _ = st.result()
    m2 = [f for f in out2 if f.id == MANUAL_ID]
    assert m2[0].loop_lines.count("Serial.println(1);") == 1


TESTS = [
    test_ai_features_excludes_manual,
    test_build_intent_excludes_manual_even_with_prompt,
    test_recombine_preserves_manual_and_excludes_its_intent,
    test_dropdown_manual_row_no_regen_deletable_labeled,
    test_sync_captures_trailing_orphan_to_manual,
    test_sync_interleaved_orphan_does_not_roundtrip_with_manual,
    test_verified_resync_captures_standalone_hand_edit,
    test_verified_resync_interleaved_falls_back_to_neighbor,
    test_apply_verified_resync_captures_manual_without_touching_text,
    test_schedule_manual_capture_skipped_when_busy,
    test_feature_menu_items_always_offers_manual,
    test_selected_line_range_from_selection,
    test_assign_trailing_line_to_manual_is_canonical,
    test_assign_interleaved_line_keeps_visual_override,
    test_reassign_all_manual_lines_drops_empty_manual,
    test_sync_drops_empty_manual,
    test_delete_manual_removes_its_code,
    test_transfer_manual_copies_when_dest_has_none,
    test_transfer_manual_merges_into_existing_and_is_idempotent,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        t()
        passed += 1
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0)
