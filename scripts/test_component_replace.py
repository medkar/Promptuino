import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules.setdefault("ui", ui_pkg)

from ui.wiring.netlist import Component, Pin, Netlist
from ui.wiring import component_replace as cr


def _led_netlist():
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D5"), Pin("K", "GND")],
                    attributes={"category": "single_output",
                                "signature_detected": False})
    return Netlist(board_id="", components=[led])


def test_same_category_swap_preserves_signal_net():
    nl = _led_netlist()
    res = cr.replace_component(nl, "D1", "buzzer")
    assert res.ok
    comp = next(c for c in res.netlist.components if c.ref == "D1")
    assert comp.type == "buzzer"
    sig = comp.pins[0]
    assert sig.net == "D5"
    assert comp.pins[1].net == "GND"
    assert comp.ref == "D1"


def test_cross_category_rejected():
    nl = _led_netlist()
    res = cr.replace_component(nl, "D1", "potentiometer")
    assert not res.ok
    assert "catégorie" in res.reason.lower() or "category" in res.reason.lower()
    comp = next(c for c in nl.components if c.ref == "D1")
    assert comp.type == "led"


def test_divergence_flag_set_when_source_signature_detected():
    nl = _led_netlist()
    nl.components[0].attributes["signature_detected"] = True
    res = cr.replace_component(nl, "D1", "buzzer")
    assert res.ok and res.divergence is True


def test_no_divergence_for_generic_source():
    nl = _led_netlist()
    res = cr.replace_component(nl, "D1", "buzzer")
    assert res.ok and res.divergence is False


def test_unknown_ref_returns_not_ok():
    nl = _led_netlist()
    res = cr.replace_component(nl, "ZZ", "buzzer")
    assert not res.ok


def test_sibling_removal_scoped_to_signal_net_not_gnd():
    # LED with series R: R1(D5->NET_X) + LED(NET_X->GND). An inferred battery
    # shares GND but must NOT be removed; the series R (shares NET_X) must be;
    # the resulting buzzer must be traced back to D5 (not NET_X).
    r = Component(ref="R1", type="resistor",
                  pins=[Pin("A", "D5"), Pin("B", "NET_X")],
                  attributes={}, inferred=True)
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "NET_X"), Pin("K", "GND")],
                    attributes={"category": "single_output",
                                "signature_detected": False})
    bat = Component(ref="BT1", type="battery_external",
                    pins=[Pin("+", "5V"), Pin("-", "GND")],
                    attributes={}, inferred=True)
    nl = Netlist(board_id="", components=[r, led, bat])
    res = cr.replace_component(nl, "D1", "buzzer")
    assert res.ok
    refs = {c.ref for c in res.netlist.components}
    assert "R1" not in refs and "R1" in res.removed_refs   # series sibling removed
    assert "BT1" in refs                                    # battery preserved (GND only)
    buz = next(c for c in res.netlist.components if c.ref == "D1")
    assert buz.pins[0].net == "D5"                          # traced back through NET_X bridge


def test_replace_to_non_cataloged_type_keeps_pins():
    # 'hall_sensor' is categorized as analog_in (via the replacement_catalog
    # merge) but absent from the static CATALOG (rendered generic).
    # Replacement must preserve pins, not yield 0-pin. (Used to be checked
    # with 'relay', which joined the catalogue with TODO #41 part 2 -- no
    # single_output type is left outside it. Then with 'microphone', which
    # joined analog_in too in the 2026-08-19 Fritzing batch, TODO #57 -- by
    # then EVERY prior candidate in this category had a catalog entry except
    # 'hall_sensor' and 'mq135'. Picking a category member is not enough on
    # its own: it must ALSO be absent from CATALOG, and that combination is
    # what makes this test mean something -- verify both before reusing a
    # type here again.)
    pot = Component(ref="P1", type="potentiometer",
                    pins=[Pin("A", "5V"), Pin("W", "A0"), Pin("B", "GND")],
                    attributes={"category": "analog_in",
                                "signature_detected": False})
    nl = Netlist(board_id="", components=[pot])
    res = cr.replace_component(nl, "P1", "hall_sensor")
    assert res.ok
    comp = next(c for c in res.netlist.components if c.ref == "P1")
    assert comp.type == "hall_sensor"
    assert len(comp.pins) == 3
    assert "A0" in {p.net for p in comp.pins}


def test_replace_to_a_catalogued_type_matches_the_detector():
    # 'relay' has a catalogue entry (added 2026-08-08, KEPT when the glyphs
    # were removed on 2026-08-10), so the gear now builds
    # its REAL 3-pin pinout instead of a 2-pin approximation. The property that
    # matters is parity: replacing a LED by a relay must produce exactly what
    # `markers` produces for a relay on the same pin -- otherwise the schematic
    # would depend on HOW the component got there.
    from ui.wiring.markers import extract_netlist
    nl = _led_netlist()                       # LED on D5
    res = cr.replace_component(nl, "D1", "relay")
    assert res.ok
    comp = next(c for c in res.netlist.components if c.ref == "D1")
    got = [(p.name, p.net) for p in comp.pins]

    detected = extract_netlist(
        "void setup(){pinMode(5, OUTPUT);}\nvoid loop(){digitalWrite(5, HIGH);}",
        "uno", prompt="pilote un relais sur la broche 5")
    relay = next(c for c in detected.components if c.type == "relay")
    expected = [(p.name, p.net) for p in relay.pins]

    assert got == expected, f"engrenage {got} != detecteur {expected}"


def test_inference_regenerates_correct_sibling_after_swap():
    from ui.wiring.inference import apply_rules
    # buzzer (no series R) replaced by led (series R required)
    buz = Component(ref="U1", type="buzzer",
                    pins=[Pin("+", "D3"), Pin("-", "GND")],
                    attributes={"category": "single_output",
                                "signature_detected": False})
    nl = Netlist(board_id="", components=[buz])
    res = cr.replace_component(nl, "U1", "led")
    assert res.ok
    out = apply_rules(res.netlist)
    assert any(c.type == "resistor" for c in out.components), \
        "apply_rules doit recréer la R série de la LED"


def test_replace_non_cataloged_traces_through_removed_resistor():
    # Series R: R1(D5->NET_A) + LED(NET_A->GND). Replacing with a relay must
    # keep the signal on D5 (traced BEFORE removing R1), not a dangling NET_A.
    # Asserts the PROPERTY (D5 is among the nets), not the pin position -- which
    # is why it survived the relay gaining a catalogue entry with TODO #41.
    r = Component(ref="R1", type="resistor", pins=[Pin("A","D5"),Pin("B","NET_A")],
                  attributes={}, inferred=True)
    led = Component(ref="D1", type="led", pins=[Pin("A","NET_A"),Pin("K","GND")],
                    attributes={"category":"single_output","signature_detected":False})
    nl = Netlist(board_id="", components=[r, led])
    res = cr.replace_component(nl, "D1", "relay")
    assert res.ok
    relay = next(c for c in res.netlist.components if c.ref=="D1")
    assert relay.type == "relay"
    nets = {p.net for p in relay.pins}
    assert "D5" in nets, f"signal doit être D5, nets={nets}"
    assert "R1" in res.removed_refs


def test_replace_bus_to_generic_no_gnd_collapse():
    # OLED (all bus pins) -> module_generic (2 generic pins):
    # the 2 pins must NOT all collapse to GND (positional fallback).
    oled = Component(ref="U1", type="oled_ssd1306",
                     pins=[Pin("VCC","5V"),Pin("GND","GND"),Pin("SDA","A4"),Pin("SCL","A5")],
                     attributes={"category":"i2c","signature_detected":True})
    nl = Netlist(board_id="", components=[oled])
    res = cr.replace_component(nl, "U1", "module_generic")
    assert res.ok
    mod = next(c for c in res.netlist.components if c.ref=="U1")
    nets = [p.net for p in mod.pins]
    assert len(set(nets)) >= 2, f"broches ne doivent pas toutes être identiques: {nets}"


TESTS = [
    test_same_category_swap_preserves_signal_net,
    test_cross_category_rejected,
    test_divergence_flag_set_when_source_signature_detected,
    test_no_divergence_for_generic_source,
    test_unknown_ref_returns_not_ok,
    test_sibling_removal_scoped_to_signal_net_not_gnd,
    test_replace_to_non_cataloged_type_keeps_pins,
    test_replace_to_a_catalogued_type_matches_the_detector,
    test_inference_regenerates_correct_sibling_after_swap,
    test_replace_non_cataloged_traces_through_removed_resistor,
    test_replace_bus_to_generic_no_gnd_collapse,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
