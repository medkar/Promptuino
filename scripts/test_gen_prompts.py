"""Tests for the pure prompt builders (ui/generation/gen_prompts.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.gen_prompts import (
    build_context_summary, build_feature_instruction, build_modify_instruction,
    build_regen_instruction,
    extract_feature_summary, feature_label,
    compact_pin_label, feature_combo_label, feature_combo_tooltip,
)
from ui.generation.feature_model import Feature, FeatureFunction


def _feat():
    return Feature(
        id="f1", prompt="led",
        setup_lines=["pinMode(13, OUTPUT);"],
        functions=[FeatureFunction(name="blink", code="void blink(){}")],
    )


def test_context_summary_empty_when_no_features():
    assert build_context_summary([]) == ""


def test_context_summary_lists_pins_and_names():
    summary = build_context_summary([_feat()])
    assert "13" in summary
    assert "blink" in summary


def test_feature_instruction_is_english_and_mentions_feature_only():
    instr = build_feature_instruction(
        "add a buzzer on D8", board_hint="Arduino Uno",
        existing_code="const int LED = 13;\nvoid setup(){}\nvoid loop(){}",
        used_summary="PINS already used: 13")
    low = instr.lower()
    assert "only" in low                          # write only the new feature
    assert "add a buzzer on D8" in instr           # the user request
    assert "const int LED = 13;" in instr          # existing sketch is provided
    assert "13" in instr                           # already-used pin recalled


def test_feature_instruction_warns_against_resetup_lines():
    # Explicit instruction: do not re-emit existing setup/loop lines
    # (Serial.begin / pinMode / .begin already set by another feature).
    instr = build_feature_instruction(
        "add a servo", board_hint="Arduino Uno",
        existing_code="void setup(){ Serial.begin(9600); }")
    low = instr.lower()
    assert "setup()" in low and "loop()" in low
    assert "serial.begin" in low and "pinmode" in low


def test_feature_instruction_without_context():
    instr = build_feature_instruction("add a buzzer", board_hint="Arduino Uno")
    assert "add a buzzer" in instr


def test_feature_instruction_requests_summary_line():
    instr = build_feature_instruction("add a buzzer", board_hint="Arduino Uno")
    assert "// FEATURE:" in instr


def test_extract_summary_present():
    assert extract_feature_summary("// FEATURE: Clignote la LED\nvoid loop(){}") \
        == "Clignote la LED"


def test_extract_summary_absent_is_empty():
    assert extract_feature_summary("void loop(){}") == ""


def test_feature_label_prefers_summary():
    f = Feature(id="f1", prompt="un très long prompt", summary="LED clignotante")
    assert feature_label(f) == "LED clignotante"


def test_feature_label_falls_back_to_prompt_and_truncates():
    f = Feature(id="f1", prompt="x" * 200, summary="")
    label = feature_label(f, max_len=20)
    assert label.startswith("x") and len(label) <= 20 and label.endswith("…")


def test_context_summary_includes_global_var_names():
    feats = [Feature(id="f1", prompt="led",
                     global_lines=["const int PIN_LED = 5;"])]
    summary = build_context_summary(feats)
    assert "PIN_LED" in summary          # the model is warned about the already-used name


def test_modify_instruction_includes_current_code_and_keep_rule():
    instr = build_modify_instruction(
        "void loop(){ blink10Hz(); }", "mets la LED sur D6", "",
        board_hint="Arduino Uno")
    assert "blink10Hz()" in instr                 # current code is provided
    assert "mets la LED sur D6" in instr          # the modification request
    assert "ONLY the" in instr and "KEEP" in instr  # change-only-this instruction


# ── build_regen_instruction : ↻ régénère depuis le prompt, PAS le code actuel ──

def test_regen_instruction_omits_current_code():
    # The whole point of the fix: a genuine regeneration must NOT feed the
    # feature's current code (otherwise the model returns the same sketch).
    current = "void loop(){ blink10Hz(); }"
    instr = build_regen_instruction(
        "fais clignoter la LED", build_context_summary([]),
        board_hint="Arduino Uno")
    assert current not in instr                    # current code is NOT provided
    assert "blink10Hz" not in instr
    assert "fais clignoter la LED" in instr        # the request drives generation


def test_regen_instruction_frames_fresh_generation():
    instr = build_regen_instruction("un buzzer", "", board_hint="Arduino Uno")
    low = instr.lower()
    assert "fresh" in low or "from scratch" in low   # explicitly a new attempt
    assert "// FEATURE:" in instr                     # still asks for the summary


def test_regen_instruction_shares_other_features_context():
    # Others' pins/names are shared read-only so the fresh code avoids collisions.
    context = build_context_summary([_feat()])       # uses pin 13 + name "blink"
    instr = build_regen_instruction("un servo", context, board_hint="Arduino Uno")
    assert "13" in instr and "blink" in instr        # collision context present
    assert "collide" in instr.lower()                # explicit avoid-collision rule


def test_regen_instruction_without_context():
    instr = build_regen_instruction("un buzzer", "", board_hint="Arduino Uno")
    assert "un buzzer" in instr                       # works with no other feature


# ── compact_pin_label : forme compacte des broches pour le label modale ──

def test_compact_pins_empty():
    assert compact_pin_label([]) == ""


def test_compact_pins_one():
    assert compact_pin_label(["D5"]) == "D5"


def test_compact_pins_two():
    assert compact_pin_label(["D5", "D6"]) == "D5, D6"


def test_compact_pins_contiguous_range():
    pins = ["D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11"]
    assert compact_pin_label(pins) == "D2–D11"   # D2–D11 (en dash)


def test_compact_pins_three_contiguous():
    assert compact_pin_label(["D2", "D3", "D4"]) == "D2–D4"


def test_compact_pins_scattered_overflow():
    # 3+ non-contiguous -> first 2 + overflow counter.
    assert compact_pin_label(["D5", "D9", "A0"]) == "D5, D9 +1"


# ── feature_combo_label / feature_combo_tooltip : label + selector hover text ──

def _led_on(pin_decl, pin_use, summary="Clignote la LED"):
    return Feature(id="f1", prompt="led", summary=summary,
                   global_lines=[pin_decl], setup_lines=[pin_use])


def test_combo_label_appends_compact_pins():
    f = _led_on("const int LED = 5;", "pinMode(LED, OUTPUT);")
    assert feature_combo_label(f) == "Clignote la LED — D5"   # — (em dash)


def test_combo_label_no_pins_is_summary_only():
    f = Feature(id="f1", prompt="x", summary="Juste un message série")
    assert feature_combo_label(f) == "Juste un message série"


def test_combo_tooltip_full_summary_and_all_pins():
    f = Feature(id="f1", prompt="10 leds", summary="Clignote 10 LEDs",
                global_lines=["const int LEDS[] = {2,3,4,5,6,7,8,9,10,11};"],
                setup_lines=["for(int i=0;i<10;i++) pinMode(LEDS[i], OUTPUT);"])
    tip = feature_combo_tooltip(f)
    assert tip.startswith("Clignote 10 LEDs")
    assert "D2, D3, D4, D5, D6, D7, D8, D9, D10, D11" in tip


def test_combo_tooltip_no_pins_is_summary_only():
    f = Feature(id="f1", prompt="x", summary="Juste un message")
    assert feature_combo_tooltip(f) == "Juste un message"


TESTS = [
    test_context_summary_empty_when_no_features,
    test_context_summary_lists_pins_and_names,
    test_feature_instruction_is_english_and_mentions_feature_only,
    test_feature_instruction_warns_against_resetup_lines,
    test_feature_instruction_without_context,
    test_feature_instruction_requests_summary_line,
    test_extract_summary_present,
    test_extract_summary_absent_is_empty,
    test_feature_label_prefers_summary,
    test_feature_label_falls_back_to_prompt_and_truncates,
    test_context_summary_includes_global_var_names,
    test_modify_instruction_includes_current_code_and_keep_rule,
    # build_regen_instruction (↻ fresh regeneration)
    test_regen_instruction_omits_current_code,
    test_regen_instruction_frames_fresh_generation,
    test_regen_instruction_shares_other_features_context,
    test_regen_instruction_without_context,
    # compact_pin_label
    test_compact_pins_empty, test_compact_pins_one, test_compact_pins_two,
    test_compact_pins_contiguous_range, test_compact_pins_three_contiguous,
    test_compact_pins_scattered_overflow,
    # feature_combo_label / feature_combo_tooltip
    test_combo_label_appends_compact_pins, test_combo_label_no_pins_is_summary_only,
    test_combo_tooltip_full_summary_and_all_pins,
    test_combo_tooltip_no_pins_is_summary_only,
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
