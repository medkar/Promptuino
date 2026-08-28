"""sync_features_from_editor: rebuild feature contributions from editor+owners."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.generation.feature_model import Feature, FeatureFunction
from ui.generation.assembler import assemble, assemble_with_map
from ui.generation.line_attribution import transfer_map, match_contributions, normalize
from ui.generation.feature_resync import sync_features_from_editor


def _norm(code):
    return "\n".join(normalize(l) for l in code.split("\n") if l.strip())


def _led(fid="f1"):
    return Feature(id=fid, prompt="led", summary="LED",
                   global_lines=["const int PIN_LED = 5;"],
                   setup_lines=["pinMode(PIN_LED, OUTPUT);"],
                   loop_lines=["digitalWrite(PIN_LED, HIGH);", "delay(500);"])


def _buzzer(fid="f2"):
    return Feature(id=fid, prompt="buzzer", summary="Buzzer",
                   global_lines=["const int PIN_BUZZER = 9;"],
                   setup_lines=["pinMode(PIN_BUZZER, OUTPUT);"],
                   loop_lines=["tone(PIN_BUZZER, 440);"])


def _with_helper(fid="f3"):
    return Feature(id=fid, prompt="fade",
                   global_lines=["int level = 0;"],
                   loop_lines=["fade();"],
                   functions=[FeatureFunction(
                       name="fade",
                       code="void fade() {\n  level = (level + 1) % 256;\n}")])


def test_roundtrip_unchanged_code():
    # No edit: resync must reproduce the exact same assembled code, and each
    # feature must keep its own contributions (right buckets).
    feats = [_led(), _buzzer(), _with_helper()]
    code, owners = assemble_with_map(feats)
    out = sync_features_from_editor(feats, code, owners)
    assert _norm(assemble(out)) == _norm(code)
    by = {f.id: f for f in out}
    assert by["f1"].global_lines == ["const int PIN_LED = 5;"]
    assert by["f1"].setup_lines == ["pinMode(PIN_LED, OUTPUT);"]
    assert by["f2"].loop_lines == ["tone(PIN_BUZZER, 440);"]
    assert [fn.name for fn in by["f3"].functions] == ["fade"]
    assert "level = (level + 1) % 256;" in by["f3"].functions[0].code


def test_repair_removed_line_is_dropped_from_model():
    # A redundant GLOBAL declared in f2 with a name that assemble's dedup does
    # NOT catch (setup/loop body dedup is by exact signature): the redundant
    # line reaches the assembled code (the transfer bug). After a repair
    # removes it in the editor, the resynced model must drop it too.
    f1 = _led()
    f2 = _buzzer()
    # f2 redundantly re-drives PIN_LED in its loop with slightly different text
    # (setup/loop dedup is exact -> not merged): this line reaches assemble.
    f2.loop_lines = ["digitalWrite( PIN_LED , HIGH );", "tone(PIN_BUZZER, 440);"]
    feats = [f1, f2]
    code0, map0 = assemble_with_map(feats)
    assert "digitalWrite( PIN_LED , HIGH )" in code0        # redundant present
    # Repair removes the redundant variant line.
    lines0 = code0.split("\n")
    lines1 = [l for l in lines0 if "digitalWrite( PIN_LED , HIGH )" not in l]
    code1 = "\n".join(lines1)
    base = transfer_map(lines0, map0, lines1)
    owners1 = match_contributions(lines1, feats, base)
    out = sync_features_from_editor(feats, code1, owners1)
    assert _norm(assemble(out)) == _norm(code1)
    assert "digitalWrite( PIN_LED , HIGH )" not in assemble(out)


def test_orphan_line_not_lost():
    # A repaired/added body line the owner map couldn't attribute (None) must
    # still survive the resync (attached to a neighbor) -> assemble keeps it.
    feats = [_led(), _buzzer()]
    code, owners = assemble_with_map(feats)
    lines = code.split("\n")
    # Insert a new loop line right after f1's first loop line, owner unknown.
    idx = next(i for i, l in enumerate(lines) if "digitalWrite(PIN_LED, HIGH)" in l)
    lines.insert(idx + 1, "  Serial.println(1);")
    owners = owners[:idx + 1] + [None] + owners[idx + 1:]
    code2 = "\n".join(lines)
    out = sync_features_from_editor(feats, code2, owners)
    assert "Serial.println(1);" in assemble(out)


def test_empty_features_returns_empty():
    assert sync_features_from_editor([], "void setup(){}\nvoid loop(){}\n", [None, None]) == []


TESTS = [
    test_roundtrip_unchanged_code,
    test_repair_removed_line_is_dropped_from_model,
    test_orphan_line_not_lost,
    test_empty_features_returns_empty,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1
        except Exception as e:
            import traceback
            print(f"FAIL {t.__name__}: {e}")
            traceback.print_exc()
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
