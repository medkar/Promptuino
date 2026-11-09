"""Audit 2026-11-06 : defauts de detection du cablage (lot wiring-detection).

Run : python scripts/test_audit_wiring_detection.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.wiring_pipeline import generate_wiring  # noqa: E402
from ui.wiring.implicit_actions import apply_action  # noqa: E402


NL = chr(10)


def _gen(code: str, prompt: str = ""):
    return generate_wiring(code, "arduino_uno_r3", prompt=prompt)


def _by_type(nl, t):
    return [c for c in nl.components if c.type == t]


# 1 ─ servo sur batterie externe + NEMA17 : deux piles
def test_servo_external_power_splits_from_stepper_battery():
    code = (
        "#include <AccelStepper.h>\n#include <Servo.h>\n"
        "AccelStepper stepper(AccelStepper::DRIVER, 3, 4);\nServo s;\n"
        "void setup(){ s.attach(9); }\nvoid loop(){ stepper.run(); }\n")
    nl = _gen(code)
    sv = _by_type(nl, "servo")[0]
    apply_action(sv, "servo_external_power", nl)
    sv = _by_type(nl, "servo")[0]
    drv = [c for c in nl.components if c.type == "a4988"][0]
    sv_net = sv.pin("VCC").net
    vm_net = [p.net for p in drv.pins if p.name == "VMOT"][0]
    assert sv_net.startswith("BAT_") and vm_net.startswith("BAT_"), (sv_net, vm_net)
    assert sv_net != vm_net, f"servo et NEMA17 sur la meme pile : {sv_net}"
    assert len(_by_type(nl, "battery_external")) == 2


# 2 ─ LED variable + LED digitale confirmees : aucune ne disparait
def _led_pins(nl) -> set[str]:
    out = set()
    for c in _by_type(nl, "led"):
        for p in c.pins:
            if p.name == "A":
                out.add(p.net)
    return out


def _arduino_nets_of_leds(nl) -> set[str]:
    """Broches Arduino finales (D9, D7) atteintes par une LED, en
    remontant le pont de la resistance serie."""
    nets = set()
    for c in nl.components:
        if c.type == "resistor":
            for p in c.pins:
                if p.net.startswith("D") and p.net[1:].isdigit():
                    nets.add(p.net)
        elif c.type == "led":
            for p in c.pins:
                if p.net.startswith("D") and p.net[1:].isdigit():
                    nets.add(p.net)
    return nets


def test_grouped_motor_candidate_confirmed_led_keeps_both_leds():
    code = (
        "const int ledRouge = 9;" + NL + "const int ledVerte = 7;" + NL +
        "void setup(){ pinMode(ledRouge, OUTPUT); pinMode(ledVerte, OUTPUT); }" + NL +
        "void loop(){ for(int i=0;i<255;i++){ analogWrite(ledRouge, i); }" + NL +
        " digitalWrite(ledVerte, HIGH); delay(500); digitalWrite(ledVerte, LOW); }" + NL)
    nl = _gen(code, "une LED rouge qui varie en intensite et une LED verte qui clignote")
    nets = _arduino_nets_of_leds(nl)
    assert {"D9", "D7"} <= nets, f"une LED a disparu : {nets}"


def test_grouped_motor_candidate_with_medium_identifier_keeps_both():
    code = (
        "const int LED_FADE = 9;" + NL + "const int ledVerte = 7;" + NL +
        "void setup(){ pinMode(LED_FADE, OUTPUT); pinMode(ledVerte, OUTPUT); }" + NL +
        "void loop(){ analogWrite(LED_FADE, 100); digitalWrite(ledVerte, HIGH); }" + NL)
    nl = _gen(code, "une LED qui varie et une autre qui clignote")
    nets = _arduino_nets_of_leds(nl)
    assert {"D9", "D7"} <= nets, f"une LED a disparu : {nets}"


# 3 ─ un bus partage n'est pas une collision
def _double_use(nl):
    return [w for w in nl.warnings if w.code == "pin_double_use"]


def test_shared_i2c_bus_is_not_a_pin_conflict():
    code = (
        "#include <Wire.h>" + NL + "#include <LiquidCrystal_I2C.h>" + NL
        + "#include <Adafruit_BME280.h>" + NL
        + "LiquidCrystal_I2C lcd(0x27, 16, 2);" + NL
        + "Adafruit_BME280 bme;" + NL
        + "void setup(){ lcd.init(); bme.begin(0x76); }" + NL
        + "void loop(){ lcd.print(bme.readTemperature()); }" + NL)
    nl = _gen(code)
    kinds = sorted(c.type for c in nl.components if c.type in ("lcd_i2c", "bme280"))
    assert len(kinds) == 2, kinds
    assert not _double_use(nl), [w.message for w in _double_use(nl)]


def test_real_pin_collision_is_still_reported():
    from ui.wiring.netlist import Component, Netlist, Pin
    from ui.wiring.inference import _detect_pin_double_use
    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="D1", type="led", pins=[Pin("A", "D5"), Pin("K", "GND")]),
        Component(ref="SV1", type="servo", pins=[
            Pin("VCC", "5V"), Pin("GND", "GND"), Pin("SIG", "D5")]),
    ])
    _detect_pin_double_use(nl)
    assert len(_double_use(nl)) == 1


# 4 ─ clavier : ecritures alternatives du tableau de broches
def _keypad_code(decl_rows: str, decl_cols: str, rn: str, cn: str) -> str:
    return (
        "#include <Keypad.h>" + NL + "#include <Servo.h>" + NL
        + "const byte ROWS = 4; const byte COLS = 4;" + NL
        + "char keys[ROWS][COLS] = {{'1','2','3','A'},{'4','5','6','B'},"
          "{'7','8','9','C'},{'*','0','#','D'}};" + NL
        + decl_rows + NL + decl_cols + NL
        + f"Keypad kp = Keypad(makeKeymap(keys), {rn}, {cn}, ROWS, COLS);" + NL
        + "Servo s;" + NL + "void setup(){ s.attach(10); }" + NL
        + "void loop(){ kp.getKey(); }" + NL)


def test_keypad_detected_with_uint8_t_and_custom_names():
    for rows, cols, rn, cn in (
        ("uint8_t rowPins[ROWS] = {9,8,7,6};", "uint8_t colPins[COLS] = {5,4,3,2};",
         "rowPins", "colPins"),
        ("byte pin_rows[ROWS] = {9,8,7,6};", "byte pin_cols[COLS] = {5,4,3,2};",
         "pin_rows", "pin_cols"),
    ):
        nl = _gen(_keypad_code(rows, cols, rn, cn))
        kp = _by_type(nl, "keypad")
        assert len(kp) == 1, (rows, [c.type for c in nl.components])
        assert len(kp[0].pins) == 8


# 5 ─ INPUT_PULLUP via une constante : pull-up interne reconnu
def test_input_pullup_through_const_or_define_is_internal():
    for decl in ("const int BOUTON = 2;", "#define BOUTON 2"):
        code = (decl + NL + "void setup(){ pinMode(BOUTON, INPUT_PULLUP); }" + NL
                + "void loop(){ digitalRead(BOUTON); }" + NL)
        nl = _gen(code)
        btn = _by_type(nl, "button")
        assert len(btn) == 1, decl
        assert btn[0].attributes.get("pull") == "internal", (decl, btn[0].attributes)
        assert not _by_type(nl, "resistor"), f"resistance inutile avec {decl}"
        assert not [w for w in nl.warnings if w.code == "button_external_pullup"]


# 6 ─ « del » (preposition ES/IT) n'est pas une LED
def _bare_output(prompt: str):
    code = ("void setup(){ pinMode(7, OUTPUT); }" + NL
            + "void loop(){ digitalWrite(7, HIGH); delay(1000); "
              "digitalWrite(7, LOW); delay(1000); }" + NL)
    nl = _gen(code, prompt)
    return nl, [c for c in nl.components if c.pin("A") is not None
                or c.type in ("buzzer", "relay")]


def test_spanish_del_does_not_make_an_led():
    nl, _ = _bare_output("Haz sonar el zumbador conectado al pin 7 del Arduino")
    assert _by_type(nl, "buzzer"), [c.type for c in nl.components]
    nl, _ = _bare_output("Activa el rele del ventilador en el pin 7")
    leds = _by_type(nl, "led")
    assert not leds or leds[0].attributes.get("_confidence") == "low", leds


def test_italian_del_does_not_confirm_an_led():
    nl, _ = _bare_output("Accendi la pompa del giardino ogni due secondi")
    leds = _by_type(nl, "led")
    assert leds and leds[0].attributes.get("_confidence") == "low",         [(c.type, c.attributes) for c in nl.components]


# 7 ─ interrupteurs requalifies : l'entree ne flotte pas
def _switch_code(mode: str) -> str:
    return ("void setup(){ pinMode(4, " + mode + "); }" + NL
            + "void loop(){ digitalRead(4); }" + NL)


def test_switch_subtypes_keep_the_external_pullup():
    for phrase, ctype in (
        ("un interrupteur reed sur la broche 4", "reed_switch"),
        ("un interrupteur a bille (tilt) sur la broche 4", "tilt_switch"),
        ("un interrupteur a glissiere sur la broche 4", "slide_switch"),
    ):
        nl = _gen(_switch_code("INPUT"), phrase)
        assert _by_type(nl, ctype), (phrase, [c.type for c in nl.components])
        pullups = [c for c in _by_type(nl, "resistor")
                   if c.attributes.get("role") == "pullup"]
        assert len(pullups) == 1, (ctype, "entree flottante")


def test_switch_subtypes_with_input_pullup_get_no_resistor():
    nl = _gen(_switch_code("INPUT_PULLUP"), "un interrupteur reed sur la broche 4")
    assert _by_type(nl, "reed_switch")
    assert not _by_type(nl, "resistor")


def test_plain_button_pullup_unchanged():
    nl = _gen(_switch_code("INPUT"), "un bouton sur la broche 4")
    assert len(_by_type(nl, "resistor")) == 1


TESTS = [
    test_servo_external_power_splits_from_stepper_battery,
    test_grouped_motor_candidate_confirmed_led_keeps_both_leds,
    test_grouped_motor_candidate_with_medium_identifier_keeps_both,
    test_shared_i2c_bus_is_not_a_pin_conflict,
    test_real_pin_collision_is_still_reported,
    test_keypad_detected_with_uint8_t_and_custom_names,
    test_input_pullup_through_const_or_define_is_internal,
    test_spanish_del_does_not_make_an_led,
    test_italian_del_does_not_confirm_an_led,
    test_switch_subtypes_keep_the_external_pullup,
    test_switch_subtypes_with_input_pullup_get_no_resistor,
    test_plain_button_pullup_unchanged,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
