"""Tests de l'assembleur features -> sketch (ui/generation/assembler.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.assembler import assemble, clean_feature_contributions
from ui.generation.feature_model import (
    Feature, FeatureFunction, declared_name, resolve_feature_pins,
)
from ui.generation.brace_utils import find_function_body


def _led():
    return Feature(
        id="f1", prompt="led",
        includes=["#include <A.h>"], global_lines=["const int LED = 13;"],
        setup_lines=["pinMode(LED, OUTPUT);"], loop_lines=["blink();"],
        functions=[FeatureFunction(name="blink", code="void blink() {\n  digitalWrite(LED, HIGH);\n}")],
    )


def _buzzer():
    return Feature(
        id="f2", prompt="buzzer",
        includes=["#include <A.h>"],  # doublon volontaire
        global_lines=["const int BUZ = 8;"],
        setup_lines=["pinMode(BUZ, OUTPUT);"], loop_lines=["buzz();"],
        functions=[FeatureFunction(name="buzz", code="void buzz() {\n  tone(BUZ, 440);\n}")],
    )


def test_assemble_has_setup_and_loop():
    code = assemble([_led()])
    assert find_function_body(code, "setup") is not None
    assert find_function_body(code, "loop") is not None


def test_assemble_includes_deduplicated():
    code = assemble([_led(), _buzzer()])
    assert code.count("#include <A.h>") == 1


def test_assemble_merges_setup_lines_in_order():
    code = assemble([_led(), _buzzer()])
    sp = find_function_body(code, "setup")
    body = code[sp[1]:sp[2]]
    assert body.index("pinMode(LED, OUTPUT);") < body.index("pinMode(BUZ, OUTPUT);")


def test_assemble_appends_all_functions():
    code = assemble([_led(), _buzzer()])
    assert find_function_body(code, "blink") is not None
    assert find_function_body(code, "buzz") is not None


def test_assemble_empty_features_still_valid():
    code = assemble([])
    assert find_function_body(code, "setup") is not None
    assert find_function_body(code, "loop") is not None


def test_assemble_dedups_duplicate_globals_and_functions():
    # f2 re-emits monServo + PIN_SERVO (model duplication) and adds a 2nd servo.
    f1 = Feature(id="f1", prompt="servo",
                 global_lines=["Servo monServo;", "const int PIN_SERVO = 5;"],
                 setup_lines=["monServo.attach(PIN_SERVO);"],
                 functions=[FeatureFunction(name="moveServo", code="void moveServo(){}")])
    f2 = Feature(id="f2", prompt="servo2",
                 global_lines=["Servo monServo;", "const int PIN_SERVO = 9;",
                               "Servo servoDeux;", "const int PIN_SERVO_2 = 11;"],
                 setup_lines=["servoDeux.attach(PIN_SERVO_2);"],
                 functions=[FeatureFunction(name="moveServo", code="void moveServo(){/*dup*/}")])
    code = assemble([f1, f2])
    assert code.count("Servo monServo;") == 1            # plus de doublon
    assert "PIN_SERVO = 5" in code and "PIN_SERVO = 9" not in code  # garde le 1er
    assert "Servo servoDeux;" in code                    # le nouveau survit
    assert "PIN_SERVO_2" in code
    assert code.count("void moveServo(") == 1            # function deduplicated


def test_assemble_dedups_duplicate_init_setup_across_features():
    # f2 (add) re-emits f1's init lines (SLM bug) + its own init.
    f1 = Feature(id="f1", prompt="led",
                 setup_lines=["Serial.begin(9600);", "pinMode(LED_PIN, OUTPUT);"])
    f2 = Feature(id="f2", prompt="servo",
                 setup_lines=["Serial.begin(9600);", "pinMode(LED_PIN, OUTPUT);",
                              "servo.attach(SERVO_PIN);"])
    code = assemble([f1, f2])
    sp = find_function_body(code, "setup")
    body = code[sp[1]:sp[2]]
    assert body.count("Serial.begin(9600);") == 1       # init deduplicated
    assert body.count("pinMode(LED_PIN, OUTPUT);") == 1  # init deduplicated
    assert body.count("servo.attach(SERVO_PIN);") == 1   # new init preserved


def test_assemble_keeps_legit_repeated_non_init_loop_lines():
    # delay() is NOT an idempotent init -> two identical delays from two
    # distinct features are legitimate and preserved (no merging).
    f1 = Feature(id="f1", prompt="a", loop_lines=["doA();", "delay(1000);"])
    f2 = Feature(id="f2", prompt="b", loop_lines=["doB();", "delay(1000);"])
    code = assemble([f1, f2])
    lp = find_function_body(code, "loop")
    body = code[lp[1]:lp[2]]
    assert body.count("delay(1000);") == 2


def test_assemble_keeps_within_feature_duplicate_init():
    # INTER-feature dedup only: a duplicate init within ONE single
    # feature (coherent model block) is preserved as-is.
    f1 = Feature(id="f1", prompt="x",
                 setup_lines=["pinMode(LED_PIN, OUTPUT);",
                              "pinMode(LED_PIN, OUTPUT);"])
    code = assemble([f1])
    sp = find_function_body(code, "setup")
    body = code[sp[1]:sp[2]]
    assert body.count("pinMode(LED_PIN, OUTPUT);") == 2


def test_assemble_dedups_dot_begin_across_features():
    f1 = Feature(id="f1", prompt="lcd", setup_lines=["lcd.begin(16, 2);"])
    f2 = Feature(id="f2", prompt="dht",
                 setup_lines=["lcd.begin(16, 2);", "dht.begin();"])
    code = assemble([f1, f2])
    sp = find_function_body(code, "setup")
    body = code[sp[1]:sp[2]]
    assert body.count("lcd.begin(16, 2);") == 1   # .begin() deduplicated
    assert body.count("dht.begin();") == 1         # new .begin() preserved


def test_assemble_init_dedup_ignores_whitespace():
    # The 2nd init line is identical modulo whitespace -> removed.
    f1 = Feature(id="f1", prompt="a", setup_lines=["Serial.begin(9600);"])
    f2 = Feature(id="f2", prompt="b", setup_lines=["Serial.begin( 9600 );"])
    code = assemble([f1, f2])
    sp = find_function_body(code, "setup")
    body = code[sp[1]:sp[2]]
    assert body.count("Serial.begin") == 1


def test_assemble_dedups_init_despite_inline_comments():
    # Real case: f1 carries inline comments, f2 re-emits bare inits
    # (+ header comments). Dedup must match despite the comments.
    f1 = Feature(id="f1", prompt="led",
                 setup_lines=["Serial.begin(9600); // init série",
                              "pinMode(LED_PIN, OUTPUT); // led en sortie"])
    f2 = Feature(id="f2", prompt="servo",
                 setup_lines=["// Initialisation série.",
                              "Serial.begin(9600);",
                              "// LED en sortie.",
                              "pinMode(LED_PIN, OUTPUT);",
                              "monServo.attach(SERVO_PIN);"])
    code = assemble([f1, f2])
    sp = find_function_body(code, "setup")
    body = code[sp[1]:sp[2]]
    assert body.count("Serial.begin(9600)") == 1
    assert body.count("pinMode(LED_PIN, OUTPUT)") == 1
    assert "monServo.attach(SERVO_PIN);" in body
    # orphan comments from the re-emitted block removed
    assert "Initialisation série." not in body
    assert "LED en sortie." not in body


def test_assemble_drops_reemitted_loop_block():
    led_loop = ['digitalWrite(LED_PIN, HIGH);', 'Serial.println("on");',
                "delay(1000);", "digitalWrite(LED_PIN, LOW);",
                'Serial.println("off");', "delay(1000);"]
    f1 = Feature(id="f1", prompt="led", loop_lines=list(led_loop))
    # f2 re-emits the ENTIRE LED block (with header comment) + adds the servo.
    f2 = Feature(id="f2", prompt="servo",
                 loop_lines=["// Gestion du cycle LED."] + list(led_loop)
                            + ["monServo.write(90);"])
    code = assemble([f1, f2])
    lp = find_function_body(code, "loop")
    body = code[lp[1]:lp[2]]
    assert body.count("digitalWrite(LED_PIN, HIGH);") == 1   # re-emitted block removed
    assert body.count("delay(1000);") == 2          # only f1's 2 delays remain
    assert "Gestion du cycle LED." not in body       # orphan header comment removed
    assert "monServo.write(90);" in body              # new content preserved


def test_assemble_keeps_distinct_feature_blink_with_shared_delay():
    # Two blinks from DISTINCT features share delay(1000) (isolated lines,
    # not a re-emitted block) -> nothing is removed.
    f1 = Feature(id="f1", prompt="led1",
                 loop_lines=["digitalWrite(LED1, HIGH);", "delay(1000);",
                             "digitalWrite(LED1, LOW);", "delay(1000);"])
    f2 = Feature(id="f2", prompt="led2",
                 loop_lines=["digitalWrite(LED2, HIGH);", "delay(1000);",
                             "digitalWrite(LED2, LOW);", "delay(1000);"])
    code = assemble([f1, f2])
    lp = find_function_body(code, "loop")
    body = code[lp[1]:lp[2]]
    assert body.count("digitalWrite(LED2, HIGH);") == 1
    assert body.count("delay(1000);") == 4


def _brace_balance(code: str) -> bool:
    return code.count("{") == code.count("}")


def test_assemble_never_drops_a_closing_brace_partial_run():
    # Regression (bug 2026-07-06): a bare "}" carries the trivial signature
    # "}"; once an earlier feature put "}" in `seen`, a later feature whose
    # UNIQUE block re-emits one shared body line then closes had its [dup, "}"]
    # run (>=2) dropped -> the opening "{" was left dangling => broken sketch.
    # Dedup must only drop BRACE-BALANCED runs.
    f1 = Feature(id="f1", prompt="a",
                 setup_lines=["for (int i = 0; i < 3; i++) {", "step(i);", "}"])
    f2 = Feature(id="f2", prompt="b",
                 setup_lines=["if (flag) {", "step(i);", "}"])
    code = assemble([f1, f2])
    assert _brace_balance(code), code
    sp = find_function_body(code, "setup")
    body = code[sp[1]:sp[2]]
    assert "if (flag) {" in body and body.count("if (flag)") == 1
    # f2's own block is preserved intact (its "}" survived).
    assert _brace_balance(body)


def test_assemble_still_drops_reemitted_balanced_block():
    # The guard must NOT weaken the real dedup: an EXACT re-emission of a
    # balanced block (open + body + close) is still removed as a whole.
    blk = ["for (int i = 0; i < 3; i++) {", "step(i);", "}"]
    f1 = Feature(id="f1", prompt="a", setup_lines=list(blk))
    f2 = Feature(id="f2", prompt="b", setup_lines=list(blk) + ["extra();"])
    code = assemble([f1, f2])
    sp = find_function_body(code, "setup")
    body = code[sp[1]:sp[2]]
    assert body.count("step(i);") == 1        # re-emitted block dropped
    assert body.count("for (int i") == 1
    assert "extra();" in body
    assert _brace_balance(code)


def _led_feature():
    return Feature(id="f1", prompt="led",
                   includes=["#include <Arduino.h>"],
                   global_lines=["const int PIN_LED = 7;"],
                   setup_lines=["pinMode(PIN_LED, OUTPUT);"],
                   loop_lines=["digitalWrite(PIN_LED, HIGH);", "delay(500);",
                               "digitalWrite(PIN_LED, LOW);", "delay(500);"])


def test_clean_feature_drops_reemitted_keeps_own():
    # The servo re-emitted the LED code (global + setup + loop block) + its own code.
    servo = Feature(id="f2", prompt="servo",
        includes=["#include <Arduino.h>", "#include <Servo.h>"],
        global_lines=["const int PIN_LED = 7;",          # foreign global re-emitted
                      "const int PIN_SERVO = 7;", "Servo monServo;"],
        setup_lines=["pinMode(PIN_LED, OUTPUT);",         # foreign init re-emitted
                     "monServo.attach(PIN_SERVO);"],
        loop_lines=["digitalWrite(PIN_LED, HIGH);", "delay(500);",   # re-emitted block
                    "digitalWrite(PIN_LED, LOW);", "delay(500);",
                    "monServo.write(90);"])
    cleaned = clean_feature_contributions(servo, [_led_feature()])
    # foreign global removed, own preserved
    assert all(declared_name(g) != "PIN_LED" for g in cleaned.global_lines)
    assert any(declared_name(g) == "PIN_SERVO" for g in cleaned.global_lines)
    assert "#include <Servo.h>" in cleaned.includes        # new include kept
    assert cleaned.includes.count("#include <Arduino.h>") == 0  # already present -> removed
    # setup: foreign pinMode removed, attach kept
    assert "pinMode(PIN_LED, OUTPUT);" not in cleaned.setup_lines
    assert "monServo.attach(PIN_SERVO);" in cleaned.setup_lines
    # loop: re-emitted LED block removed, servo movement kept
    assert "digitalWrite(PIN_LED, HIGH);" not in cleaned.loop_lines
    assert "monServo.write(90);" in cleaned.loop_lines


def test_clean_feature_resolves_only_own_pins():
    # Real case: the servo re-emitted the full LED block (>=2 lines) -> removed during
    # cleanup -> resolve_feature_pins no longer "owns" pin PIN_LED
    # (which was showing as an unresolved name in the "Modify" label).
    servo = Feature(id="f2", prompt="servo",
        global_lines=["const int PIN_SERVO = 2;", "Servo monServo;"],
        setup_lines=["pinMode(PIN_LED, OUTPUT);", "monServo.attach(PIN_SERVO);"],
        loop_lines=["digitalWrite(PIN_LED, HIGH);", "delay(500);",
                    "digitalWrite(PIN_LED, LOW);", "delay(500);",
                    "monServo.write(90);"])
    cleaned = clean_feature_contributions(servo, [_led_feature()])
    assert resolve_feature_pins(cleaned) == ["D2"]   # plus de « PIN_LED »


TESTS = [
    test_assemble_has_setup_and_loop, test_assemble_includes_deduplicated,
    test_assemble_merges_setup_lines_in_order, test_assemble_appends_all_functions,
    test_assemble_empty_features_still_valid,
    test_assemble_dedups_duplicate_globals_and_functions,
    test_assemble_dedups_duplicate_init_setup_across_features,
    test_assemble_keeps_legit_repeated_non_init_loop_lines,
    test_assemble_keeps_within_feature_duplicate_init,
    test_assemble_dedups_dot_begin_across_features,
    test_assemble_init_dedup_ignores_whitespace,
    test_assemble_dedups_init_despite_inline_comments,
    test_assemble_drops_reemitted_loop_block,
    test_assemble_never_drops_a_closing_brace_partial_run,
    test_assemble_still_drops_reemitted_balanced_block,
    test_assemble_keeps_distinct_feature_blink_with_shared_delay,
    test_clean_feature_drops_reemitted_keeps_own,
    test_clean_feature_resolves_only_own_pins,
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
