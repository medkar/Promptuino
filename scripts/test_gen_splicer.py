"""Tests for the content-anchor splicer (ui/generation/splicer.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.splicer import splice_add, splice_replace, SpliceError
from ui.generation.feature_model import Feature, FeatureFunction
from ui.generation.brace_utils import find_function_body

EXISTING = """const int LED = 13;

void setup() {
  pinMode(LED, OUTPUT);
}

void loop() {
  blink();
}

void blink() {
  digitalWrite(LED, HIGH);
}
"""


def _buzzer():
    return Feature(
        id="f2", prompt="buzzer",
        includes=["#include <B.h>"], global_lines=["const int BUZ = 8;"],
        setup_lines=["pinMode(BUZ, OUTPUT);"], loop_lines=["buzz();"],
        functions=[FeatureFunction(name="buzz", code="void buzz() {\n  tone(BUZ, 440);\n}")],
    )


def test_add_preserves_existing_code_verbatim():
    out = splice_add(EXISTING, _buzzer())
    assert "void blink()" in out
    assert "digitalWrite(LED, HIGH);" in out   # existant intact


def test_add_inserts_setup_line():
    out = splice_add(EXISTING, _buzzer())
    sp = find_function_body(out, "setup")
    body = out[sp[1]:sp[2]]
    assert "pinMode(LED, OUTPUT);" in body
    assert "pinMode(BUZ, OUTPUT);" in body


def test_add_inserts_loop_line_and_function():
    out = splice_add(EXISTING, _buzzer())
    lp = find_function_body(out, "loop")
    assert "buzz();" in out[lp[1]:lp[2]]
    assert find_function_body(out, "buzz") is not None


def test_add_includes_go_to_top():
    out = splice_add(EXISTING, _buzzer())
    assert out.lstrip().startswith("#include <B.h>")


def test_add_raises_without_setup():
    try:
        splice_add("int x = 1;", _buzzer())
        assert False, "devait lever SpliceError"
    except SpliceError:
        pass


def test_replace_swaps_target_function():
    old = _buzzer()
    base = splice_add(EXISTING, old)
    new = Feature(
        id="f2", prompt="buzzer corrigé",
        setup_lines=["pinMode(BUZ, INPUT);"], loop_lines=["buzz();"],
        functions=[FeatureFunction(name="buzz", code="void buzz() {\n  noTone(BUZ);\n}")],
    )
    out = splice_replace(base, old, new)
    assert "noTone(BUZ);" in out
    assert "tone(BUZ, 440);" not in out           # old body removed
    assert "digitalWrite(LED, HIGH);" in out       # other feature intact


def test_replace_raises_when_anchor_missing():
    old = _buzzer()
    try:
        splice_replace(EXISTING, old, old)        # buzz absent de EXISTING
        assert False, "devait lever SpliceError"
    except SpliceError:
        pass


def test_add_skips_duplicate_global_and_function():
    # The feature re-emits LED (name already declared) + blink (function already present),
    # and adds a genuinely new global + a genuinely new function.
    feat = Feature(
        id="f2", prompt="dup",
        global_lines=["const int LED = 99;", "const int BUZ = 8;"],
        functions=[FeatureFunction(name="blink", code="void blink(){/*dup*/}"),
                   FeatureFunction(name="buzz", code="void buzz(){ tone(BUZ, 440); }")],
    )
    out = splice_add(EXISTING, feat)
    assert "const int LED = 13;" in out and "LED = 99" not in out  # duplicate ignored
    assert "const int BUZ = 8;" in out            # new global inserted
    assert out.count("void blink(") == 1          # blink function not reinserted
    assert "void buzz(" in out                    # new function added


def test_add_skips_duplicate_init_setup_line():
    # The feature re-emits pinMode(LED, OUTPUT) already present (idempotent init)
    # + its own new init. Only the duplicate init is dropped.
    feat = Feature(id="f2", prompt="dup-init",
                   setup_lines=["pinMode(LED, OUTPUT);", "pinMode(BUZ, OUTPUT);"])
    out = splice_add(EXISTING, feat)
    sp = find_function_body(out, "setup")
    body = out[sp[1]:sp[2]]
    assert body.count("pinMode(LED, OUTPUT);") == 1   # duplicate init not reinserted
    assert body.count("pinMode(BUZ, OUTPUT);") == 1   # new init inserted


def test_add_keeps_repeated_non_init_loop_line():
    # 'blink();' already in loop: NON-init line -> never deduplicated (the guard
    # only touches idempotent inits, like assembler).
    feat = Feature(id="f2", prompt="x", loop_lines=["blink();"])
    out = splice_add(EXISTING, feat)
    lp = find_function_body(out, "loop")
    body = out[lp[1]:lp[2]]
    assert body.count("blink();") == 2


def test_add_skips_init_despite_inline_comment():
    # The existing init has an inline comment, the re-emitted one is bare:
    # deduplication must match despite the comment.
    existing = ("void setup() {\n  Serial.begin(9600); // série\n}\n\n"
                "void loop() {\n}\n")
    feat = Feature(id="f2", prompt="x",
                   setup_lines=["Serial.begin(9600);", "pinMode(BUZ, OUTPUT);"])
    out = splice_add(existing, feat)
    sp = find_function_body(out, "setup")
    body = out[sp[1]:sp[2]]
    assert body.count("Serial.begin(9600)") == 1
    assert "pinMode(BUZ, OUTPUT);" in body


TESTS = [
    test_add_preserves_existing_code_verbatim, test_add_inserts_setup_line,
    test_add_inserts_loop_line_and_function, test_add_includes_go_to_top,
    test_add_raises_without_setup, test_replace_swaps_target_function,
    test_replace_raises_when_anchor_missing,
    test_add_skips_duplicate_global_and_function,
    test_add_skips_duplicate_init_setup_line,
    test_add_keeps_repeated_non_init_loop_line,
    test_add_skips_init_despite_inline_comment,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
