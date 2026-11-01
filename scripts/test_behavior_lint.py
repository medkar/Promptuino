"""behavior_lint: deterministic behavioral pitfalls (pure, no Qt, no model)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.generation.behavior_lint import lint_behavior


def _rules(code):
    return {f.rule for f in lint_behavior(code)}


def _find(code, rule):
    return [f for f in lint_behavior(code) if f.rule == rule]


# ── pinmode_missing ──────────────────────────────────────────────

def test_pinmode_missing_on_digitalwrite():
    code = ("const int PIN_LED = 13;\n"
            "void setup(){}\n"
            "void loop(){ digitalWrite(PIN_LED, HIGH); }\n")
    hits = _find(code, "pinmode_missing")
    assert hits and hits[0].line == 3, hits


def test_pinmode_present_no_finding():
    code = ("const int PIN_LED = 13;\n"
            "void setup(){ pinMode(PIN_LED, OUTPUT); }\n"
            "void loop(){ digitalWrite(PIN_LED, HIGH); }\n")
    assert "pinmode_missing" not in _rules(code)


def test_pinmode_missing_ignores_string_and_comment():
    code = ('void setup(){}\n'
            'void loop(){\n'
            '  // digitalWrite(99, HIGH);\n'
            '  Serial.println("digitalWrite(88, HIGH)");\n'
            '}\n')
    assert "pinmode_missing" not in _rules(code)


def test_pinmode_missing_ignores_loop_variable():
    # digitalWrite(i, ...) with i a loop index (not a declared pin) -> no false
    # positive (only pin-like tokens: literals, A-pins, declared consts).
    code = ("void setup(){}\n"
            "void loop(){ for (int i=0;i<3;i++) digitalWrite(i, HIGH); }\n")
    assert "pinmode_missing" not in _rules(code)


# ── button_no_pullup ─────────────────────────────────────────────

def test_button_input_without_pullup():
    code = ("const int BTN = 2;\n"
            "void setup(){ pinMode(BTN, INPUT); }\n"
            "void loop(){ int s = digitalRead(BTN); }\n")
    assert "button_no_pullup" in _rules(code)


def test_button_input_pullup_ok():
    code = ("const int BTN = 2;\n"
            "void setup(){ pinMode(BTN, INPUT_PULLUP); }\n"
            "void loop(){ int s = digitalRead(BTN); }\n")
    assert "button_no_pullup" not in _rules(code)


# ── millis_into_int ──────────────────────────────────────────────

def test_millis_into_int_declaration():
    code = "void loop(){ int t = millis(); }\n"
    hits = _find(code, "millis_into_int")
    assert hits, hits


def test_millis_into_unsigned_long_ok():
    code = "void loop(){ unsigned long t = millis(); }\n"
    assert "millis_into_int" not in _rules(code)


def test_micros_into_int_assignment_of_declared_var():
    code = ("int t;\n"
            "void loop(){ t = micros(); }\n")
    assert "millis_into_int" in _rules(code)


# ── blocking_delay_with_input ────────────────────────────────────

def test_blocking_delay_with_input():
    code = ("const int BTN = 2;\n"
            "void setup(){ pinMode(BTN, INPUT_PULLUP); }\n"
            "void loop(){ int s = digitalRead(BTN); delay(1000); }\n")
    assert "blocking_delay_with_input" in _rules(code)


def test_short_delay_no_input_ok():
    code = ("void setup(){}\n"
            "void loop(){ digitalWrite(13, HIGH); delay(50); }\n")
    assert "blocking_delay_with_input" not in _rules(code)


# ── clean code ───────────────────────────────────────────────────

def test_clean_code_zero_findings():
    code = ("const int PIN_LED = 13;\n"
            "unsigned long last = 0;\n"
            "void setup(){ pinMode(PIN_LED, OUTPUT); }\n"
            "void loop(){\n"
            "  if (millis() - last > 500) { last = millis();\n"
            "    digitalWrite(PIN_LED, !digitalRead(PIN_LED)); }\n"
            "}\n")
    assert lint_behavior(code) == []


TESTS = [
    test_pinmode_missing_on_digitalwrite,
    test_pinmode_present_no_finding,
    test_pinmode_missing_ignores_string_and_comment,
    test_pinmode_missing_ignores_loop_variable,
    test_button_input_without_pullup,
    test_button_input_pullup_ok,
    test_millis_into_int_declaration,
    test_millis_into_unsigned_long_ok,
    test_micros_into_int_assignment_of_declared_var,
    test_blocking_delay_with_input,
    test_short_delay_no_input_ok,
    test_clean_code_zero_findings,
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
