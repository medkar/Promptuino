"""TransferStaging: staging model of the transfer popup (pure, no Qt)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.generation.feature_model import Feature
from ui.feature_transfer import TransferStaging


def _led(fid="f1", prompt="allume la led"):
    return Feature(id=fid, prompt=prompt,
                   global_lines=["const int PIN_LED = 13;"],
                   setup_lines=["pinMode(PIN_LED, OUTPUT);"],
                   loop_lines=["digitalWrite(PIN_LED, HIGH);"])


def _blink(fid="f2", prompt="fais la clignoter"):
    # Depends on PIN_LED provided by _led.
    return Feature(id=fid, prompt=prompt,
                   loop_lines=["digitalWrite(PIN_LED, LOW);", "delay(500);"])


def _buzzer(fid="f3", prompt="buzzer sur la 9"):
    return Feature(id=fid, prompt=prompt,
                   global_lines=["const int PIN_BUZZER = 9;"],
                   loop_lines=["tone(PIN_BUZZER, 440);"])


def test_init_deep_copies_sources():
    src_ia, src_st = [_led()], [_buzzer()]
    st = TransferStaging(src_ia, src_st)
    st.ia[0].global_lines.append("int hacked = 1;")
    assert src_ia[0].global_lines == ["const int PIN_LED = 13;"]
    assert st.stable is not src_st


def test_group_for_includes_dependency_closure():
    st = TransferStaging([_led(), _blink(), _buzzer()], [])
    assert st.group_for("f2", "ia") == ["f1", "f2"]     # provider first
    assert st.group_for("f1", "ia") == ["f1"]           # provider alone
    assert st.group_for("f3", "ia") == ["f3"]


def test_transfer_carries_dependencies_source_untouched():
    st = TransferStaging([_led(), _blink()], [])
    st.transfer("f2", "ia", "stable", 0)
    assert [f.id for f in st.stable] == ["f1", "f2"]    # provider above
    assert [f.id for f in st.ia] == ["f1", "f2"]        # copy, not move


def test_transfer_updates_twin_in_place():
    old = _led()                       # same id + prompt, older content
    old.loop_lines = ["digitalWrite(PIN_LED, LOW);"]
    st = TransferStaging([_led(), _buzzer()], [_buzzer(), old])
    st.transfer("f1", "ia", "stable", 0)
    assert [f.id for f in st.stable] == ["f3", "f1"]    # position kept
    assert st.stable[1].loop_lines == ["digitalWrite(PIN_LED, HIGH);"]


def test_twin_matches_across_prompt_evolution_both_ways():
    # The IA copy evolved (Modify/regen appended to the prompt history) while
    # stable holds the older version: they are STILL the same lineage ->
    # dragging either way must REPLACE, never duplicate (bug 2026-07-06:
    # full_prompt identity piled up copies after any modification).
    evolved = _led()
    evolved.prompts = ["allume la led", "clignote plus vite"]
    evolved.loop_lines = ["digitalWrite(PIN_LED, HIGH);", "delay(100);"]
    # stable -> IA (revert): the IA evolved copy is replaced by stable's.
    st = TransferStaging([evolved], [_led()])
    st.transfer("f1", "stable", "ia", 0)
    assert [f.id for f in st.ia] == ["f1"]              # no duplicate
    assert st.ia[0].loop_lines == ["digitalWrite(PIN_LED, HIGH);"]
    # IA -> stable (push the corrected version).
    st2 = TransferStaging([evolved], [_led()])
    st2.transfer("f1", "ia", "stable", 0)
    assert [f.id for f in st2.stable] == ["f1"]
    assert st2.stable[0].loop_lines == [
        "digitalWrite(PIN_LED, HIGH);", "delay(100);"]


def test_twin_matched_by_lineage_across_different_ids():
    # Poisoned project (pre-fix re-id copies): the same lineage lives in the
    # destination under ANOTHER id (f4). Dragging f1 must REPLACE f4 in
    # place (keeping f4's id), not insert yet another copy.
    poisoned = _led(fid="f4")                   # same origin prompt, id f4
    poisoned.loop_lines = ["digitalWrite(PIN_LED, LOW);"]
    st = TransferStaging([_led()], [_buzzer(), poisoned])
    st.transfer("f1", "ia", "stable", 0)
    assert [f.id for f in st.stable] == ["f3", "f4"]     # no insertion
    assert st.stable[1].loop_lines == ["digitalWrite(PIN_LED, HIGH);"]
    # Whitespace/case variations of the origin prompt still match.
    variant = _led(fid="f9", prompt="  Allume   la LED ")
    st2 = TransferStaging([_led()], [variant])
    st2.transfer("f1", "ia", "stable", 0)
    assert [f.id for f in st2.stable] == ["f9"], [f.id for f in st2.stable]


def test_transfer_collision_gets_new_id():
    other = Feature(id="f1", prompt="un servo qui balaie",
                    global_lines=["#include <Servo.h>"])
    st = TransferStaging([_led()], [other])
    st.transfer("f1", "ia", "stable", 1)
    ids = [f.id for f in st.stable]
    assert ids[0] == "f1", ids                          # original intact
    assert len(ids) == 2 and ids[1] != "f1", ids        # copy re-idded
    assert st.stable[0].prompt == "un servo qui balaie"


def test_toggle_delete_marks_and_restores():
    st = TransferStaging([_led(), _buzzer()], [])
    st.toggle_delete("f1", "ia")
    assert st.is_deleted("f1", "ia")
    ia, _stable, removed = st.result()
    assert [f.id for f in ia] == ["f3"]
    assert removed == {"f1"}
    st.toggle_delete("f1", "ia")                        # restore
    assert not st.is_deleted("f1", "ia")
    ia, _stable, removed = st.result()
    assert [f.id for f in ia] == ["f1", "f3"] and removed == set()


def test_transfer_lifts_delete_mark_on_target():
    st = TransferStaging([_led(), _blink()], [_led()])
    st.toggle_delete("f1", "stable")
    st.transfer("f2", "ia", "stable", 1)                # group f1+f2 travels
    assert not st.is_deleted("f1", "stable")            # lifted: it travels
    _ia, stable, _removed = st.result()
    assert [f.id for f in stable] == ["f1", "f2"]


def test_reorder_moves_and_flags():
    st = TransferStaging([_led(), _blink(), _buzzer()], [])
    st.reorder("f3", 0, "ia")
    assert [f.id for f in st.ia] == ["f3", "f1", "f2"]
    assert st.recap().reordered_ia
    # Constraint: f2 depends on f1 -> dropping f2 at 0 pulls f1 above it.
    st2 = TransferStaging([_led(), _blink(), _buzzer()], [])
    st2.reorder("f2", 0, "ia")
    assert [f.id for f in st2.ia] == ["f1", "f2", "f3"]


def test_recap_counts_and_has_changes():
    st = TransferStaging([_led(), _blink()], [])
    r = st.recap()
    assert (r.transfers, r.deletions) == (0, 0)
    assert not r.reordered_ia and not r.reordered_stable
    assert not st.has_changes()
    st.transfer("f2", "ia", "stable", 0)                # carries f1 -> 2
    st.toggle_delete("f2", "ia")
    r = st.recap()
    assert r.transfers == 2, r.transfers
    assert r.deletions == 1
    assert st.has_changes()


def test_recap_warns_on_deleted_provider():
    st = TransferStaging([_led(), _blink()], [])
    st.toggle_delete("f1", "ia")                        # provider of f2
    warns = st.recap().warnings
    assert ("ia", "f2", "f1") in warns, warns


def test_transfer_all_snapshots_ia():
    st = TransferStaging([_led(), _blink()], [_buzzer()])
    st.toggle_delete("f3", "stable")
    st.transfer_all()
    assert [f.id for f in st.stable] == ["f1", "f2"]
    assert not st.is_deleted("f3", "stable")            # marks cleared
    assert st.has_changes()
    st.stable[0].loop_lines.append("x;")                # still a deep copy
    assert st.ia[0].loop_lines == ["digitalWrite(PIN_LED, HIGH);"]


def test_transfer_all_back_snapshots_stable():
    # stable → IA: IA becomes a full snapshot of stable (delete marks cleared,
    # deep copies, recap counts the arrivals).
    st = TransferStaging([_led()], [_buzzer(), _blink()])
    st.toggle_delete("f1", "ia")
    st.transfer_all("stable", "ia")
    assert [f.id for f in st.ia] == ["f3", "f2"]
    assert not st.is_deleted("f1", "ia")                # marks cleared
    assert st.recap().transfers == 2
    st.ia[0].loop_lines.append("x;")                    # still a deep copy
    assert st.stable[0].loop_lines == ["tone(PIN_BUZZER, 440);"]


def test_recap_transfer_all_frozen_at_gesture_and_dedup():
    # Revue 2026-07-29 #10 : le recap comptait le contenu COURANT des colonnes
    # destinataires -> un aller-retour « tout transférer » annonçait le DOUBLE,
    # et les drags individuels étaient écrasés du décompte. Désormais : features
    # UNIQUES enregistrées AU MOMENT du geste (dédup par fid, tous sens).
    st = TransferStaging([_led(), _blink()], [_buzzer()])
    st.transfer_all()                       # ia -> stable : f1, f2
    st.transfer_all()                       # re-clic : dédup
    assert st.recap().transfers == 2, st.recap().transfers
    st.toggle_delete("f1", "stable")        # suppression APRÈS transfert
    assert st.recap().transfers == 2        # décompte figé au geste
    st.transfer_all("stable", "ia")         # aller-RETOUR : mêmes features
    r = st.recap()
    assert r.transfers == 2, r.transfers    # 2 features uniques, pas 4


TESTS = [
    test_init_deep_copies_sources,
    test_group_for_includes_dependency_closure,
    test_transfer_carries_dependencies_source_untouched,
    test_transfer_updates_twin_in_place,
    test_twin_matches_across_prompt_evolution_both_ways,
    test_twin_matched_by_lineage_across_different_ids,
    test_transfer_collision_gets_new_id,
    test_toggle_delete_marks_and_restores,
    test_transfer_lifts_delete_mark_on_target,
    test_reorder_moves_and_flags,
    test_recap_counts_and_has_changes,
    test_recap_warns_on_deleted_provider,
    test_transfer_all_snapshots_ia,
    test_transfer_all_back_snapshots_stable,
    test_recap_transfer_all_frozen_at_gesture_and_dedup,
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
