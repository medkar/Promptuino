"""FeatureTransferDialog: columns/cards/trash/recap (no real drag — the drop
logic is driven through _do_transfer/_handle_drop directly)."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)
from ui.generation.feature_model import Feature
from ui.feature_transfer_dialog import FeatureTransferDialog
from ui.i18n import lang_manager


def _led(fid="f1", prompt="allume la led"):
    return Feature(id=fid, prompt=prompt,
                   global_lines=["const int PIN_LED = 13;"],
                   setup_lines=["pinMode(PIN_LED, OUTPUT);"],
                   loop_lines=["digitalWrite(PIN_LED, HIGH);"])


def _blink(fid="f2", prompt="fais la clignoter"):
    return Feature(id=fid, prompt=prompt,
                   loop_lines=["digitalWrite(PIN_LED, LOW);", "delay(500);"])


def _buzzer(fid="f3", prompt="buzzer sur la 9"):
    return Feature(id=fid, prompt=prompt,
                   global_lines=["const int PIN_BUZZER = 9;"],
                   loop_lines=["tone(PIN_BUZZER, 440);"])


def _dlg(ia=None, stable=None, **kw):
    ia = [_led(), _blink(), _buzzer()] if ia is None else ia
    stable = [_buzzer()] if stable is None else stable
    return FeatureTransferDialog(ia, stable, **kw)


def test_columns_populated():
    d = _dlg()
    assert len(d._cards["ia"]) == 3
    assert len(d._cards["stable"]) == 1
    assert d._cards["ia"][0].fid == "f1"


def test_trash_marks_and_recap_updates():
    d = _dlg()
    d._toggle_delete("f3", "ia")
    assert d.staging.is_deleted("f3", "ia")
    card = next(c for c in d._cards["ia"] if c.fid == "f3")
    assert card.deleted
    assert "1" in d._lbl_recap.text()          # "1 suppression(s)"
    d._toggle_delete("f3", "ia")               # restore
    assert not d.staging.is_deleted("f3", "ia")


def test_do_transfer_rebuilds_columns():
    d = _dlg()
    d._do_transfer("f2", "stable", 0)          # carries provider f1
    ids = [c.fid for c in d._cards["stable"]]
    assert ids == ["f1", "f2", "f3"], ids      # group inserted above f3
    assert len(d._cards["ia"]) == 3            # source untouched
    assert "2" in d._lbl_recap.text()          # 2 transfers


def test_transfer_all_button():
    d = _dlg()
    d._transfer_all("ia", "stable")             # IA → stable (default)
    assert [c.fid for c in d._cards["stable"]] == ["f1", "f2", "f3"]
    assert d.staging.has_changes()


def test_transfer_all_back_button():
    # « ← Tout transférer » under the stable column copies stable → IA.
    d = _dlg(ia=[_led()], stable=[_buzzer(), _blink("f2", "clignote")])
    d._transfer_all("stable", "ia")
    assert [c.fid for c in d._cards["ia"]] == ["f3", "f2"]   # IA now mirrors stable
    assert len(d._cards["stable"]) == 2                      # source untouched
    assert d.staging.has_changes()


def test_both_transfer_buttons_present_and_labelled():
    for lang in ("fr", "en", "es", "it"):
        lang_manager.set_language(lang)
        d = _dlg()
        assert d._transfer_btns["ia"].text()
        assert d._transfer_btns["stable"].text()
        # Distinct labels (forward vs back).
        assert d._transfer_btns["ia"].text() != d._transfer_btns["stable"].text()
    lang_manager.set_language("fr")


def test_cards_live_in_a_bounded_scroll_box():
    d = _dlg()
    for side in ("ia", "stable"):
        assert d._boxes[side].maximumHeight() < 16777215     # a real cap
        # The drop-target column is the scroll's widget (cards scroll inside).
        assert d._scrolls[side].widget() is d._columns[side]


def test_result_passthrough():
    d = _dlg()
    d._toggle_delete("f1", "ia")
    ia, _stable, removed = d.result()
    assert [f.id for f in ia] == ["f2", "f3"]
    assert removed == {"f1"}


def test_dependency_tooltip_mentions_link():
    d = _dlg()
    card_f2 = next(c for c in d._cards["ia"] if c.fid == "f2")
    assert "PIN_LED" in card_f2.toolTip()      # "Uses PIN_LED from ..."


def test_i18n_title_and_buttons_all_langs():
    for lang in ("fr", "en", "es", "it"):
        lang_manager.set_language(lang)
        d = _dlg()
        assert d.windowTitle()
        assert d._btn_apply.text()
        assert d._transfer_btns["ia"].text()
        assert d._btn_cancel.text()
    lang_manager.set_language("fr")


def test_no_changes_recap_empty():
    d = _dlg()
    assert d._lbl_recap.text() == ""
    assert not d.staging.has_changes()


def test_drop_index_from_y_position():
    d = _dlg()
    d.show(); _APP.processEvents()
    cards = d._cards["ia"]
    assert d._drop_index_for("ia", cards[0].y() - 2) == 0          # above 1st
    assert d._drop_index_for("ia", cards[-1].y()
                             + cards[-1].height() + 2) == 3        # below last
    mid = cards[1].y() + cards[1].height() // 2
    assert d._drop_index_for("ia", mid - 2) in (1, 2)              # around 2nd
    d.hide()


def test_handle_drop_cross_column_transfers():
    d = _dlg()
    d._handle_drop("f2", "ia", "stable", 0)     # carries provider f1
    assert [c.fid for c in d._cards["stable"]] == ["f1", "f2", "f3"]


def test_handle_drop_same_column_reorders():
    d = _dlg()
    d._handle_drop("f3", "ia", "ia", 0)
    assert [c.fid for c in d._cards["ia"]] == ["f3", "f1", "f2"]


def test_handle_drop_reorder_respects_dependency():
    d = _dlg()
    # f2 depends on f1: dropping f2 at index 0 pulls f1 above it.
    d._handle_drop("f2", "ia", "ia", 0)
    assert [c.fid for c in d._cards["ia"]] == ["f1", "f2", "f3"]


def test_handle_drop_below_own_position_index_shift():
    d = _dlg()
    # f1 dragged below f3 (display insertion index 3): lands at the end,
    # its consumer f2 slides just below it (constraint).
    d._handle_drop("f1", "ia", "ia", 3)
    assert [c.fid for c in d._cards["ia"]] == ["f3", "f1", "f2"]


def test_group_drag_pixmap_builds():
    d = _dlg()
    d.show(); _APP.processEvents()
    pm = d._group_pixmap("f2", "ia")            # f1 + f2 stacked
    assert not pm.isNull() and pm.height() > 0
    d.hide()


def test_links_overlay_collects_intra_column_edges():
    d = _dlg()
    pairs = d._links_overlay.edge_pairs()
    assert ("ia", "f1", "f2") in pairs, pairs   # provider f1 -> consumer f2
    # No edge involves f3 (independent), one single edge at init.
    assert len(pairs) == 1, pairs


def test_links_overlay_follows_transfer():
    d = _dlg()
    d._do_transfer("f2", "stable", 0)           # f1+f2 land in stable too
    pairs = d._links_overlay.edge_pairs()
    assert ("ia", "f1", "f2") in pairs, pairs
    assert ("stable", "f1", "f2") in pairs, pairs


def test_link_curves_stay_inside_overlay():
    # Bug 2026-07-06: links hooked on the outer card edges and bulged
    # OUTSIDE the host (x < 0 / x > width) -> clipped away, invisible.
    # The host now reserves side margins; every curve point must be inside.
    d = _dlg()
    d._do_transfer("f2", "stable", 0)           # link on both sides
    d.show(); _APP.processEvents()
    ov = d._links_overlay
    cards = {(s, c.fid): c for s in ("ia", "stable") for c in d._cards[s]}
    for side, provider, consumer in ov.edge_pairs():
        a, b = cards[(side, provider)], cards[(side, consumer)]
        x1, _y1, ctrl, x2, _y2 = ov.link_points(side, a, b)
        for x in (x1, ctrl, x2):
            assert 0 <= x <= ov.width(), (side, x, ov.width())
    d.hide()


def test_cards_keep_color_through_reorder():
    # Colors are ID-derived (feature_color), NOT position-derived: reordering
    # must never recolor a card (user feedback 2026-07-06).
    d = _dlg()
    before = {c.fid: c.color for c in d._cards["ia"]}
    d._handle_drop("f3", "ia", "ia", 0)         # f3 jumps to the top
    after = {c.fid: c.color for c in d._cards["ia"]}
    assert after == before, (before, after)
    # Same feature transferred to the other column keeps its color too.
    d._do_transfer("f2", "stable", 0)
    stable_colors = {c.fid: c.color for c in d._cards["stable"]}
    assert stable_colors["f2"] == before["f2"]
    assert stable_colors["f1"] == before["f1"]


def test_apply_accepts_directly_when_safe():
    # user 2026-07-07: a routine (risk-free) transfer applies directly, no
    # recap confirmation. (result() is overridden to return the transfer tuple,
    # so we spy on accept/reject.)
    d = _dlg()
    d._toggle_delete("f3", "ia")               # stage a safe change
    assert d.staging.has_changes()
    assert d._risk_warnings(lang_manager.current) == []   # no risk
    calls = {"accept": 0, "reject": 0}
    d.accept = lambda: calls.__setitem__("accept", calls["accept"] + 1)
    d.reject = lambda: calls.__setitem__("reject", calls["reject"] + 1)
    d._on_apply()
    assert calls == {"accept": 1, "reject": 0}


def test_apply_without_changes_rejects():
    d = _dlg()
    assert not d.staging.has_changes()
    calls = {"accept": 0, "reject": 0}
    d.accept = lambda: calls.__setitem__("accept", calls["accept"] + 1)
    d.reject = lambda: calls.__setitem__("reject", calls["reject"] + 1)
    d._on_apply()
    assert calls == {"accept": 0, "reject": 1}


def test_apply_confirms_only_when_risky():
    # A hand-edited (dirty) window that would be rewritten IS a risk -> the
    # confirmation is shown; confirming applies.
    d = _dlg(dirty_stable=True)
    d._do_transfer("f2", "stable", 0)          # rewrites the stable window
    assert d._side_changed("stable")
    assert d._risk_warnings(lang_manager.current)         # a risk exists
    calls = {"confirm": 0, "accept": 0}
    d._confirm_risk = lambda lines: calls.__setitem__("confirm", 1) or True
    d.accept = lambda: calls.__setitem__("accept", 1)
    d._on_apply()
    assert calls == {"confirm": 1, "accept": 1}


def test_apply_risky_cancel_aborts():
    # Cancelling the risk confirmation must NOT apply.
    d = _dlg(dirty_stable=True)
    d._do_transfer("f2", "stable", 0)
    d._confirm_risk = lambda lines: False       # user cancels
    accepted = {"n": 0}
    d.accept = lambda: accepted.__setitem__("n", 1)
    d._on_apply()
    assert accepted["n"] == 0


def test_manual_card_shows_i18n_label():
    # The manual bucket has no prompt/summary -> its card must show the i18n
    # « Éditions manuelles », not the raw id « manual » (user 2026-07-07).
    from ui.generation.feature_model import Feature, MANUAL_ID
    from ui.i18n import lang_manager
    d = _dlg(ia=[_led(), Feature(id=MANUAL_ID, prompt="")], stable=[])
    card = next(c for c in d._cards["ia"] if c.fid == MANUAL_ID)
    assert card._lbl.text() == lang_manager.current.studio_manual_feature_label


TESTS = [
    test_columns_populated,
    test_manual_card_shows_i18n_label,
    test_apply_accepts_directly_when_safe,
    test_apply_without_changes_rejects,
    test_apply_confirms_only_when_risky,
    test_apply_risky_cancel_aborts,
    test_trash_marks_and_recap_updates,
    test_do_transfer_rebuilds_columns,
    test_transfer_all_button,
    test_transfer_all_back_button,
    test_both_transfer_buttons_present_and_labelled,
    test_cards_live_in_a_bounded_scroll_box,
    test_result_passthrough,
    test_dependency_tooltip_mentions_link,
    test_i18n_title_and_buttons_all_langs,
    test_no_changes_recap_empty,
    test_drop_index_from_y_position,
    test_handle_drop_cross_column_transfers,
    test_handle_drop_same_column_reorders,
    test_handle_drop_reorder_respects_dependency,
    test_handle_drop_below_own_position_index_shift,
    test_group_drag_pixmap_builds,
    test_links_overlay_collects_intra_column_edges,
    test_links_overlay_follows_transfer,
    test_link_curves_stay_inside_overlay,
    test_cards_keep_color_through_reorder,
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
