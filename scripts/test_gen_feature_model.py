"""Tests for the feature data model (ui/generation/feature_model.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.feature_model import (
    Feature, FeatureFunction, next_feature_id, used_names, used_global_names,
    declared_name, feature_mentions_pin, serialize_features, deserialize_features,
    resolve_feature_pins, guess_correction_target,
)


def _sample():
    return Feature(
        id="f1", prompt="clignote LED sur D13",
        includes=["#include <X.h>"], global_lines=["const int LED = 13;"],
        setup_lines=["pinMode(LED, OUTPUT);"], loop_lines=["blink();"],
        functions=[FeatureFunction(name="blink", code="void blink() { }")],
    )


def test_next_feature_id_empty():
    assert next_feature_id([]) == "f1"


def test_next_feature_id_increments():
    feats = [Feature(id="f1", prompt="a"), Feature(id="f2", prompt="b")]
    assert next_feature_id(feats) == "f3"


def test_used_names_collects_function_names():
    assert used_names([_sample()]) == {"blink"}


def test_feature_mentions_pin_digital():
    assert feature_mentions_pin(_sample(), "D13") is True


def test_feature_mentions_pin_absent():
    assert feature_mentions_pin(_sample(), "D7") is False


def test_serialize_roundtrip():
    feats = [_sample()]
    restored = deserialize_features(serialize_features(feats))
    assert restored == feats


def test_deserialize_tolerates_missing_keys():
    restored = deserialize_features([{"id": "f1", "prompt": "x"}])
    assert restored[0].id == "f1"
    assert restored[0].setup_lines == []
    assert restored[0].functions == []


def test_used_global_names_extracts_var_names():
    feats = [Feature(id="f1", prompt="led",
                     global_lines=["const int PIN_LED = 5;", "Servo myServo;"])]
    names = used_global_names(feats)
    assert "PIN_LED" in names
    assert "myServo" in names
    assert "const" not in names and "int" not in names   # keywords excluded


def test_summary_serialize_roundtrip():
    f = Feature(id="f1", prompt="p", summary="LED clignote")
    assert deserialize_features(serialize_features([f]))[0].summary == "LED clignote"


def test_declared_name_variants():
    assert declared_name("const int PIN_SERVO = 5;") == "PIN_SERVO"
    assert declared_name("Servo monServo;") == "monServo"
    assert declared_name("#define PIN_SERVO_2 11") == "PIN_SERVO_2"
    assert declared_name("  262, 294, 330") is None          # continuation line
    assert declared_name("// commentaire") is None


# ── resolve_feature_pins : names/constants/arrays -> pin numbers ──

def test_resolve_pins_const_int():
    f = Feature(id="f1", prompt="led",
                global_lines=["const int LED = 13;"],
                setup_lines=["pinMode(LED, OUTPUT);"])
    assert resolve_feature_pins(f) == ["D13"]


def test_resolve_pins_define():
    f = Feature(id="f1", prompt="btn",
                global_lines=["#define BTN 7"],
                setup_lines=["pinMode(BTN, INPUT);"])
    assert resolve_feature_pins(f) == ["D7"]


def test_resolve_pins_literal_digit():
    f = Feature(id="f1", prompt="led",
                loop_lines=["digitalWrite(5, HIGH);"])
    assert resolve_feature_pins(f) == ["D5"]


def test_resolve_pins_analog():
    f = Feature(id="f1", prompt="ldr",
                loop_lines=["int v = analogRead(A0);"])
    assert resolve_feature_pins(f) == ["A0"]


def test_resolve_pins_array_ten_leds():
    f = Feature(id="f1", prompt="10 leds",
                global_lines=["const int LEDS[] = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11};"],
                setup_lines=["for (int i=0;i<10;i++) pinMode(LEDS[i], OUTPUT);"])
    assert resolve_feature_pins(f) == [
        "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11"]


def test_resolve_pins_fallback_name_when_unresolved():
    # Pin used without a resolvable local declaration -> keep the name as-is.
    f = Feature(id="f1", prompt="x",
                setup_lines=["pinMode(mysteryPin, OUTPUT);"])
    assert resolve_feature_pins(f) == ["mysteryPin"]


def test_resolve_pins_sorted_and_deduped():
    f = Feature(id="f1", prompt="x",
                loop_lines=["digitalWrite(9, HIGH);", "digitalWrite(2, LOW);",
                            "digitalWrite(9, LOW);"])
    assert resolve_feature_pins(f) == ["D2", "D9"]   # sorted, deduplicated


def test_resolve_pins_servo_attach_const():
    f = Feature(id="f1", prompt="servo",
                global_lines=["const int SERVO_PIN = 9;", "Servo s;"],
                setup_lines=["s.attach(SERVO_PIN);"])
    assert resolve_feature_pins(f) == ["D9"]


# ── guess_correction_target : case-insensitive pre-selection (fix B) ──

def _led5():
    return Feature(id="f1", prompt="led",
                   global_lines=["const int LED = 5;"],
                   setup_lines=["pinMode(LED, OUTPUT);"])


def test_guess_target_lowercase_pin():
    # "d5" lowercase must match (the fix: case-insensitive).
    assert guess_correction_target([_led5()],
        "CORRECTION modifie la led en d5") == "f1"


def test_guess_target_uppercase_pin():
    assert guess_correction_target([_led5()],
        "CORRECTION mets la LED sur D5") == "f1"


def test_guess_target_from_to_prefers_existing():
    # "de d5 vers d2": d2 doesn't exist on any feature -> target the feature on d5.
    assert guess_correction_target([_led5()],
        "CORRECTION modifie le pin de la led en d5 pour la mettre en d2") == "f1"


def test_guess_target_bare_number():
    assert guess_correction_target([_led5()],
        "CORRECTION change la broche 5") == "f1"


def test_guess_target_none_when_no_match():
    assert guess_correction_target([_led5()],
        "CORRECTION change la couleur") is None


TESTS = [
    test_next_feature_id_empty, test_next_feature_id_increments,
    test_used_names_collects_function_names, test_feature_mentions_pin_digital,
    test_feature_mentions_pin_absent, test_serialize_roundtrip,
    test_deserialize_tolerates_missing_keys,
    test_used_global_names_extracts_var_names, test_summary_serialize_roundtrip,
    test_declared_name_variants,
    # resolve_feature_pins
    test_resolve_pins_const_int, test_resolve_pins_define,
    test_resolve_pins_literal_digit, test_resolve_pins_analog,
    test_resolve_pins_array_ten_leds, test_resolve_pins_fallback_name_when_unresolved,
    test_resolve_pins_sorted_and_deduped, test_resolve_pins_servo_attach_const,
    # guess_correction_target (fix B)
    test_guess_target_lowercase_pin, test_guess_target_uppercase_pin,
    test_guess_target_from_to_prefers_existing, test_guess_target_bare_number,
    test_guess_target_none_when_no_match,
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
