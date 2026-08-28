"""Test standalone de ui.wiring.implicit_actions.

Run : python scripts/test_implicit_actions.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.netlist import Component, Netlist, Pin
from ui.wiring.implicit_actions import (
    available_actions, apply_action,
    LED_SERIES_CHOICES, LED_SERIES_DEFAULT,
    BUZZER_SERIES_CHOICES, BUZZER_SERIES_DEFAULT,
)


# ─── Helpers : netlists de test ──────────────────────────────────────────
def _build_servo_5v_netlist() -> Netlist:
    return Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="SV1", type="servo", pins=[
            Pin("VCC", "5V"),
            Pin("GND", "GND"),
            Pin("SIG", "D9"),
        ]),
    ])


def _build_servo_bat_netlist() -> Netlist:
    return Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="SV1", type="servo", pins=[
            Pin("VCC", "BAT_5V"),
            Pin("GND", "GND"),
            Pin("SIG", "D9"),
        ]),
        Component(ref="BAT1", type="battery_external", inferred=True, pins=[
            Pin("+", "BAT_5V"),
            Pin("-", "GND"),
        ]),
    ])


def _build_led_with_r_netlist(r_value: str = "220") -> Netlist:
    """LED + R serie 220 entre D5 et NET_A (cas typique apres inference)."""
    return Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="D1", type="led", pins=[
            Pin("A", "NET_A"),
            Pin("K", "GND"),
        ]),
        Component(ref="R1", type="resistor", inferred=True, pins=[
            Pin("A", "D5"),
            Pin("B", "NET_A"),
        ], attributes={"value": r_value, "role": "series"}),
    ])


def _build_btn_with_pullup_netlist() -> Netlist:
    """BTN sur D2 avec R pullup externe 10k."""
    return Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="BTN1", type="button", pins=[
            Pin("A", "D2"),
            Pin("B", "GND"),
        ]),
        Component(ref="R1", type="resistor", inferred=True, pins=[
            Pin("A", "5V"),
            Pin("B", "D2"),
        ], attributes={"value": "10k", "role": "pullup"}),
    ])


def _build_btn_internal_pullup_netlist() -> Netlist:
    """BTN sur D2 sans R externe (INPUT_PULLUP cote code)."""
    return Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="BTN1", type="button",
                  attributes={"pull": "internal"}, pins=[
            Pin("A", "D2"),
            Pin("B", "GND"),
        ]),
    ])


def _build_dht_with_pullup_netlist() -> Netlist:
    return Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="DHT1", type="dht22", pins=[
            Pin("VCC", "5V"),
            Pin("DATA", "D7"),
            Pin("GND", "GND"),
        ]),
        Component(ref="R1", type="resistor", inferred=True, pins=[
            Pin("A", "5V"),
            Pin("B", "D7"),
        ], attributes={"value": "4.7k", "role": "pullup"}),
    ])


def _build_buzzer_with_r_netlist(r_value: str = "100") -> Netlist:
    """Buzzer + R serie entre D6 et NET_A."""
    return Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="BUZ1", type="buzzer", pins=[
            Pin("+", "NET_A"),
            Pin("-", "GND"),
        ]),
        Component(ref="R1", type="resistor", inferred=True, pins=[
            Pin("A", "D6"),
            Pin("B", "NET_A"),
        ], attributes={"value": r_value, "role": "series"}),
    ])


# ─── Tests servo (regression de l'existant) ──────────────────────────────
def test_available_actions_servo():
    nl = _build_servo_5v_netlist()
    sv = nl.components[0]
    acts = available_actions(sv, nl)
    assert len(acts) == 1
    assert acts[0].id == "servo_external_power"
    assert acts[0].is_active is False
    assert acts[0].choices is None   # toggle
    assert "batterie" in acts[0].label.lower()


def test_available_actions_servo_already_external():
    nl = _build_servo_bat_netlist()
    sv = nl.components[0]
    acts = available_actions(sv, nl)
    assert len(acts) == 1
    assert acts[0].is_active is True
    assert acts[0].value is True
    assert "5v arduino" in acts[0].label.lower()


def test_apply_toggle_servo_to_external():
    nl = _build_servo_5v_netlist()
    sv = nl.components[0]
    apply_action(sv, "servo_external_power", nl)
    assert sv.pin("VCC").net == "BAT_5V"
    bats = [c for c in nl.components if c.type == "battery_external"]
    assert len(bats) == 1


def test_apply_toggle_servo_back_to_5v_removes_battery():
    nl = _build_servo_bat_netlist()
    sv = nl.components[0]
    apply_action(sv, "servo_external_power", nl)
    assert sv.pin("VCC").net == "5V"
    assert not any(c.type == "battery_external" for c in nl.components)


def test_apply_toggle_servo_back_keeps_battery_if_other_consumer():
    nl = _build_servo_bat_netlist()
    nl.components.append(Component(
        ref="M1", type="dc_motor",
        pins=[Pin("M+", "BAT_5V"), Pin("M-", "GND")],
    ))
    sv = nl.components[0]
    apply_action(sv, "servo_external_power", nl)
    bats = [c for c in nl.components if c.type == "battery_external"]
    assert len(bats) == 1


def test_apply_action_idempotent_via_toggle():
    nl = _build_servo_5v_netlist()
    sv = nl.components[0]
    apply_action(sv, "servo_external_power", nl)
    apply_action(sv, "servo_external_power", nl)
    assert sv.pin("VCC").net == "5V"
    assert not any(c.type == "battery_external" for c in nl.components)


def test_apply_action_unknown_raises():
    nl = _build_servo_5v_netlist()
    sv = nl.components[0]
    try:
        apply_action(sv, "bogus", nl)
    except ValueError:
        return
    raise AssertionError("ValueError attendue")


def test_available_actions_non_handled_empty():
    """Composant inconnu (pas servo/led/btn/dht/buzzer) -> []."""
    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="X1", type="custom_thing",
                  pins=[Pin("A", "D5")]),
    ])
    assert available_actions(nl.components[0], nl) == []


# ─── Tests LED R serie (selecteur) ───────────────────────────────────────
def test_led_action_present_with_choices():
    nl = _build_led_with_r_netlist("220")
    led = nl.components[0]
    acts = available_actions(led, nl)
    assert len(acts) == 1
    a = acts[0]
    assert a.id == "led_series_value"
    assert a.value == "220"
    assert a.choices == list(LED_SERIES_CHOICES)
    assert a.is_active is False   # 220 = defaut
    assert "220" in a.label


def test_led_action_non_default_active():
    nl = _build_led_with_r_netlist("470")
    led = nl.components[0]
    a = available_actions(led, nl)[0]
    assert a.value == "470"
    assert a.is_active is True


def test_led_set_value():
    nl = _build_led_with_r_netlist("220")
    led = nl.components[0]
    r = nl.components[1]
    apply_action(led, "led_series_value", nl, value="330")
    assert r.attributes["value"] == "330"
    # Lecture re-roundtrip via available_actions
    a = available_actions(led, nl)[0]
    assert a.value == "330"


def test_led_set_value_requires_value():
    nl = _build_led_with_r_netlist("220")
    led = nl.components[0]
    try:
        apply_action(led, "led_series_value", nl)
    except ValueError:
        return
    raise AssertionError("ValueError attendue (selecteur sans value)")


def test_led_action_missing_resistor_exposes_none_mode():
    """LED sans R serie -> expose quand meme l'action en mode 'Aucune' (value='0').
    Permet a l'user de reactiver une R via la modale Niveau 3."""
    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="D1", type="led", pins=[Pin("A", "D5"), Pin("K", "GND")]),
    ])
    led = nl.components[0]
    acts = available_actions(led, nl)
    assert len(acts) == 1 and acts[0].id == "led_series_value"
    assert acts[0].value == "0"
    assert acts[0].is_active is True   # = etat non-defaut


def test_led_set_value_none_removes_resistor():
    """Mettre value='0' supprime physiquement la R serie et reconnecte la LED."""
    nl = _build_led_with_r_netlist("220")
    led = nl.components[0]
    apply_action(led, "led_series_value", nl, value="0")
    # R doit etre supprimee.
    resistors = [c for c in nl.components if c.type == "resistor"]
    assert resistors == [], f"R devait etre supprimee, restantes={resistors}"
    # LED.A reconnectee directement sur le pin Arduino.
    a_pin = led.pin("A")
    assert a_pin is not None and not a_pin.net.startswith("NET_"), \
        f"LED.A doit pointer sur un pin Arduino, got {a_pin.net if a_pin else None}"


def test_led_set_value_recreates_resistor_from_none():
    """Apres value='0', repasser a une valeur > 0 recree la R serie."""
    nl = _build_led_with_r_netlist("220")
    led = nl.components[0]
    apply_action(led, "led_series_value", nl, value="0")
    assert [c for c in nl.components if c.type == "resistor"] == []
    apply_action(led, "led_series_value", nl, value="470")
    resistors = [c for c in nl.components if c.type == "resistor"]
    assert len(resistors) == 1
    assert resistors[0].attributes.get("value") == "470"
    # LED.A repointee sur un net interne (bridge_net).
    assert led.pin("A").net.startswith("NET_")


# ─── Tests BTN pullup (toggle) ───────────────────────────────────────────
def test_btn_action_external_active():
    nl = _build_btn_with_pullup_netlist()
    btn = nl.components[0]
    a = available_actions(btn, nl)[0]
    assert a.id == "btn_pullup_external"
    assert a.is_active is True
    assert a.value is True
    assert "internal" in a.label.lower() or "input_pullup" in a.label.lower()


def test_btn_action_internal_inactive():
    nl = _build_btn_internal_pullup_netlist()
    btn = nl.components[0]
    a = available_actions(btn, nl)[0]
    assert a.is_active is False
    assert a.value is False
    assert "externe" in a.label.lower() or "10k" in a.label


def test_btn_toggle_remove_external():
    nl = _build_btn_with_pullup_netlist()
    btn = nl.components[0]
    apply_action(btn, "btn_pullup_external", nl)
    assert not any(c.type == "resistor" and
                   (c.attributes.get("role") or "").lower() == "pullup"
                   for c in nl.components)


def test_btn_toggle_add_external():
    nl = _build_btn_internal_pullup_netlist()
    btn = nl.components[0]
    apply_action(btn, "btn_pullup_external", nl)
    r = next((c for c in nl.components if c.type == "resistor"), None)
    assert r is not None
    assert r.attributes["value"] == "10k"
    assert r.attributes["role"] == "pullup"
    nets = {p.net for p in r.pins}
    assert "5V" in nets and "D2" in nets


def test_btn_toggle_idempotent():
    nl = _build_btn_with_pullup_netlist()
    btn = nl.components[0]
    apply_action(btn, "btn_pullup_external", nl)   # retire
    apply_action(btn, "btn_pullup_external", nl)   # remet
    rs = [c for c in nl.components if c.type == "resistor"]
    assert len(rs) == 1


# ─── Tests DHT pullup (toggle) ───────────────────────────────────────────
def test_dht_action_pullup_active():
    nl = _build_dht_with_pullup_netlist()
    dht = nl.components[0]
    a = available_actions(dht, nl)[0]
    assert a.id == "dht_data_pullup"
    assert a.is_active is True


def test_dht_toggle_remove_pullup():
    nl = _build_dht_with_pullup_netlist()
    dht = nl.components[0]
    apply_action(dht, "dht_data_pullup", nl)
    assert not any(c.type == "resistor" for c in nl.components)


def test_dht_toggle_add_pullup():
    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="DHT1", type="dht22", pins=[
            Pin("VCC", "5V"), Pin("DATA", "D7"), Pin("GND", "GND"),
        ]),
    ])
    dht = nl.components[0]
    apply_action(dht, "dht_data_pullup", nl)
    r = next((c for c in nl.components if c.type == "resistor"), None)
    assert r is not None
    assert r.attributes["value"] == "4.7k"
    assert r.attributes["role"] == "pullup"


# ─── Tests Buzzer R serie (selecteur avec 'none') ────────────────────────
def test_buzzer_action_with_r():
    nl = _build_buzzer_with_r_netlist("100")
    buz = nl.components[0]
    a = available_actions(buz, nl)[0]
    assert a.id == "buzzer_series_value"
    assert a.value == "100"
    assert a.choices == list(BUZZER_SERIES_CHOICES)
    assert a.is_active is False   # 100 = defaut


def test_buzzer_action_without_r():
    """Buzzer sans R : value='none', is_active=True."""
    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="BUZ1", type="buzzer", pins=[
            Pin("+", "D6"),
            Pin("-", "GND"),
        ]),
    ])
    buz = nl.components[0]
    a = available_actions(buz, nl)[0]
    assert a.value == "none"
    assert a.is_active is True


def test_buzzer_change_value():
    nl = _build_buzzer_with_r_netlist("100")
    buz = nl.components[0]
    r = nl.components[1]
    apply_action(buz, "buzzer_series_value", nl, value="220")
    assert r.attributes["value"] == "220"


def test_buzzer_remove_r():
    """Selecteur 'none' : retire la R et remet le pin + sur le net Arduino."""
    nl = _build_buzzer_with_r_netlist("100")
    buz = nl.components[0]
    apply_action(buz, "buzzer_series_value", nl, value="none")
    assert not any(c.type == "resistor" for c in nl.components)
    # Le pin + du buzzer doit etre revenu sur D6 (le net arduino direct)
    assert buz.pin("+").net == "D6"


def test_buzzer_add_r_creates_bridge():
    """Selecteur depuis 'none' : ajoute R + insere bridge_net."""
    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="BUZ1", type="buzzer", pins=[
            Pin("+", "D6"),
            Pin("-", "GND"),
        ]),
    ])
    buz = nl.components[0]
    apply_action(buz, "buzzer_series_value", nl, value="220")
    r = next((c for c in nl.components if c.type == "resistor"), None)
    assert r is not None
    assert r.attributes["value"] == "220"
    nets = {p.net for p in r.pins}
    # D6 + un net interne NET_X
    assert "D6" in nets
    internal = nets - {"D6"}
    assert len(internal) == 1 and next(iter(internal)).startswith("NET_")
    # Le pin + du buzzer est passe sur le bridge_net
    assert buz.pin("+").net.startswith("NET_")


# ─── Suite ───────────────────────────────────────────────────────────────
TESTS = [
    # servo (regression)
    test_available_actions_servo,
    test_available_actions_servo_already_external,
    test_apply_toggle_servo_to_external,
    test_apply_toggle_servo_back_to_5v_removes_battery,
    test_apply_toggle_servo_back_keeps_battery_if_other_consumer,
    test_apply_action_idempotent_via_toggle,
    test_apply_action_unknown_raises,
    test_available_actions_non_handled_empty,
    # LED
    test_led_action_present_with_choices,
    test_led_action_non_default_active,
    test_led_set_value,
    test_led_set_value_requires_value,
    test_led_action_missing_resistor_exposes_none_mode,
    test_led_set_value_none_removes_resistor,
    test_led_set_value_recreates_resistor_from_none,
    # BTN
    test_btn_action_external_active,
    test_btn_action_internal_inactive,
    test_btn_toggle_remove_external,
    test_btn_toggle_add_external,
    test_btn_toggle_idempotent,
    # DHT
    test_dht_action_pullup_active,
    test_dht_toggle_remove_pullup,
    test_dht_toggle_add_pullup,
    # Buzzer
    test_buzzer_action_with_r,
    test_buzzer_action_without_r,
    test_buzzer_change_value,
    test_buzzer_remove_r,
    test_buzzer_add_r_creates_bridge,
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
