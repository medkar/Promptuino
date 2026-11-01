"""Tests for conflicting pin reassignment. Standalone runner:
python scripts/test_gen_pin_reassign.py
"""
from __future__ import annotations
import sys, types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ui_pkg = types.ModuleType("ui"); ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.generation.feature_model import Feature
from ui.generation.pin_reassign import (
    _constant_pins, _feature_tokens, _value_to_token, _free_pin,
    reassign_conflicting_pins, format_reassign_notice, PinMove,
)
from ui.wiring.boards import load_board


def _feat(gid, globals_, body=""):
    return Feature(id=gid, prompt="", global_lines=globals_,
                   loop_lines=[body] if body else [])


def test_value_to_token():
    assert _value_to_token("9") == "D9"
    assert _value_to_token("A0") == "A0"
    print("  [OK] _value_to_token")


def test_constant_pins_kinds():
    f = _feat("f1",
              ["#define PIN_LED 9", "const int PIN_POT = A0;",
               "#define PIN_FAN 5"],
              "analogWrite(PIN_FAN, 100); analogRead(PIN_POT); digitalWrite(PIN_LED, HIGH);")
    cp = _constant_pins(f)
    assert cp["PIN_LED"] == ("D9", "digital"), cp
    assert cp["PIN_FAN"] == ("D5", "pwm"), cp
    assert cp["PIN_POT"] == ("A0", "analog"), cp
    print("  [OK] _constant_pins : digital/pwm/analog")


def test_feature_tokens_resolves_ax_const():
    f = _feat("f1", ["const int PIN_POT = A0;"], "analogRead(PIN_POT);")
    assert "A0" in _feature_tokens(f)
    print("  [OK] _feature_tokens résout les constantes Ax")


def test_free_pin_digital_skips_bus_and_used():
    b = load_board("arduino_uno_r3")
    assert _free_pin(b, "digital", used=set()) == "D2"
    assert _free_pin(b, "digital", used={"D2", "D3"}) == "D4"
    print("  [OK] _free_pin digital saute bus + occupées")


def test_free_pin_pwm_excludes_spi():
    b = load_board("arduino_uno_r3")
    assert _free_pin(b, "pwm", used={"D3", "D5"}) == "D6"
    assert _free_pin(b, "pwm", used={"D3", "D5", "D6", "D9"}) is None
    print("  [OK] _free_pin pwm exclut SPI (D10/D11)")


def test_free_pin_analog_excludes_i2c():
    b = load_board("arduino_uno_r3")
    assert _free_pin(b, "analog", used={"A0"}) == "A1"
    assert _free_pin(b, "analog", used={"A0", "A1", "A2", "A3"}) is None
    print("  [OK] _free_pin analog exclut I2C (A4/A5)")


def _board():
    return load_board("arduino_uno_r3")


def test_conflict_digital_reassigned():
    existing = [_feat("f1", ["#define PIN_LED 9"], "digitalWrite(PIN_LED, HIGH);")]
    new = _feat("f2", ["#define PIN_BTN 9"], "digitalRead(PIN_BTN);")
    r = reassign_conflicting_pins(new, existing, _board())
    assert len(r.moves) == 1
    mv = r.moves[0]
    assert mv.old_pin == "D9" and mv.new_pin == "D2" and mv.kind == "digital"
    joined = "\n".join(r.feature.global_lines)
    assert "PIN_BTN 2" in joined and "déplacé D9→D2" in joined
    assert existing[0].global_lines == ["#define PIN_LED 9"]
    print("  [OK] conflit digital réassigné + commentaire + existant intact")


def test_conflict_pwm_stays_pwm():
    existing = [_feat("f1", ["#define PIN_A 9"], "analogWrite(PIN_A, 100);")]
    new = _feat("f2", ["#define PIN_B 9"], "analogWrite(PIN_B, 50);")
    r = reassign_conflicting_pins(new, existing, _board())
    assert r.moves[0].new_pin in ("D3", "D5", "D6")
    assert r.moves[0].kind == "pwm"
    print("  [OK] conflit PWM -> broche pwm")


def test_conflict_analog():
    existing = [_feat("f1", ["const int P1 = A0;"], "analogRead(P1);")]
    new = _feat("f2", ["const int P2 = A0;"], "analogRead(P2);")
    r = reassign_conflicting_pins(new, existing, _board())
    assert r.moves[0].old_pin == "A0" and r.moves[0].new_pin == "A1"
    assert "P2 = A1" in "\n".join(r.feature.global_lines)
    print("  [OK] conflit analogique -> A1")


def test_no_conflict_noop():
    existing = [_feat("f1", ["#define PIN_LED 9"], "digitalWrite(PIN_LED, HIGH);")]
    new = _feat("f2", ["#define PIN_LED2 8"], "digitalWrite(PIN_LED2, HIGH);")
    r = reassign_conflicting_pins(new, existing, _board())
    assert r.moves == [] and r.feature.global_lines == new.global_lines
    print("  [OK] pas de conflit -> no-op")


def test_bus_pin_not_reassigned():
    existing = [_feat("f1", ["const int S1 = A4;"], "Wire.begin();")]
    new = _feat("f2", ["const int S2 = A4;"], "Wire.beginTransmission(1);")
    r = reassign_conflicting_pins(new, existing, _board())
    assert r.moves == [] and any("bus" in w.lower() for w in r.warnings)
    print("  [OK] broche de bus non réaffectée + warning")


def test_no_free_pin_warns():
    existing = [_feat("f1", [f"#define P{n} {n}" for n in range(2, 10)],
                      " ".join(f"digitalWrite(P{n}, HIGH);" for n in range(2, 10)))]
    new = _feat("f2", ["#define PX 2"], "digitalWrite(PX, HIGH);")
    r = reassign_conflicting_pins(new, existing, _board())
    assert r.moves == [] and any("libre" in w for w in r.warnings)
    print("  [OK] plus de broche libre -> warning")


def test_bare_literal_warns():
    existing = [_feat("f1", ["#define PIN_LED 9"], "digitalWrite(PIN_LED, HIGH);")]
    new = _feat("f2", [], "digitalWrite(9, HIGH);")
    r = reassign_conflicting_pins(new, existing, _board())
    assert r.moves == [] and any("littéral" in w for w in r.warnings)
    print("  [OK] littéral nu -> warning")


def test_determinism():
    existing = [_feat("f1", ["#define PIN_LED 9"], "digitalWrite(PIN_LED, HIGH);")]
    new = _feat("f2", ["#define PIN_BTN 9"], "digitalRead(PIN_BTN);")
    r1 = reassign_conflicting_pins(new, existing, _board())
    r2 = reassign_conflicting_pins(new, existing, _board())
    assert [m.new_pin for m in r1.moves] == [m.new_pin for m in r2.moves]
    print("  [OK] déterministe")


def test_multi_conflict_no_self_collision():
    existing = [_feat("f1", ["#define A 2", "#define B 3"],
                      "digitalWrite(A,1); digitalWrite(B,1);")]
    new = _feat("f2", ["#define C 2", "#define D 3"],
                "digitalWrite(C,1); digitalWrite(D,1);")
    r = reassign_conflicting_pins(new, existing, _board())
    news = sorted(m.new_pin for m in r.moves)
    assert len(news) == 2 and len(set(news)) == 2
    print("  [OK] multi-conflits sans collision interne")


def test_no_board_noop():
    existing = [_feat("f1", ["#define PIN_LED 9"], "digitalWrite(PIN_LED, HIGH);")]
    new = _feat("f2", ["#define PIN_BTN 9"], "digitalRead(PIN_BTN);")
    r = reassign_conflicting_pins(new, existing, None)
    assert r.moves == [] and r.feature.global_lines == new.global_lines
    print("  [OK] carte None -> no-op sûr")


def test_reassign_rewrites_summary_pin_token():
    # Servo requested on D7 (SLM summary "... on D7"), reassigned because D7 is taken.
    existing = [_feat("f1", ["#define PIN_LED 7"], "digitalWrite(PIN_LED, HIGH);")]
    servo = Feature(id="f2", prompt="servo sur d7",
                    summary="Contrôle du Servo sur D7",
                    global_lines=["const int PIN_SERVO = 7;"],
                    setup_lines=["monServo.attach(PIN_SERVO);"])
    r = reassign_conflicting_pins(servo, existing, _board())
    assert r.moves and r.moves[0].old_pin == "D7"
    new = r.moves[0].new_pin
    assert "D7" not in r.feature.summary           # stale token removed
    assert new in r.feature.summary                # replaced with the new pin
    print("  [OK] résumé : token de broche réécrit après réaffectation")


def test_format_notice():
    moves = [PinMove("PIN_SERVO_2", "pwm", "D9", "D6")]
    txt = format_reassign_notice(moves, ["A4 partagé (bus I2C/SPI/UART) — non réaffecté."])
    assert "D9" in txt and "D6" in txt and "PIN_SERVO_2" in txt
    assert "A4" in txt
    assert format_reassign_notice([], []) == ""
    print("  [OK] format_reassign_notice")


def main() -> int:
    tests = [test_value_to_token, test_constant_pins_kinds,
             test_feature_tokens_resolves_ax_const,
             test_free_pin_digital_skips_bus_and_used,
             test_free_pin_pwm_excludes_spi,
             test_free_pin_analog_excludes_i2c,
             test_conflict_digital_reassigned,
             test_conflict_pwm_stays_pwm,
             test_conflict_analog,
             test_no_conflict_noop,
             test_bus_pin_not_reassigned,
             test_no_free_pin_warns,
             test_bare_literal_warns,
             test_determinism,
             test_multi_conflict_no_self_collision,
             test_no_board_noop,
             test_reassign_rewrites_summary_pin_token,
             test_format_notice]
    print("[test_gen_pin_reassign]\n")
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as e:
            print(f"  [FAIL] {fn.__name__}: {e}"); failed += 1
    print(f"\n{len(tests)-failed}/{len(tests)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
