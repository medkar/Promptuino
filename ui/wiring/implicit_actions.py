"""Level 3 of the interactive schematic: per-component actions on implicit
assemblies (servo external power, LED series R value, BTN/DHT pullup,
buzzer series R, ...).

Qt-free module, testable in isolation. Mutates the netlist in place via
`apply_action`.

Two families of actions:
- Toggle (servo, BTN, DHT): `apply_action(comp, action_id, netlist)`
  switches between 2 states. `value` ignored.
- Selector (LED R, Buzzer R): `apply_action(comp, action_id, netlist,
  value=...)` sets the target value. A non-None `choices` signals the
  presence of a selector.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from .netlist import Component, Pin

if TYPE_CHECKING:
    from .netlist import Netlist


# ─── Public models ───────────────────────────────────────────────────────
@dataclass
class ImplicitAction:
    """An action available on a component.

    - `id` stable (used for persistence and dispatch in `apply_action`).
    - `label` localized for the UI.
    - `is_active`: for a toggle, True = override active (the non-default
      option is applied). For a selector, indicates whether the current
      value differs from the default.
    - `value`: current value. bool for toggle, str/int for selector.
      This is the value we persist to replay the action on
      regeneration.
    - `choices`: None for a toggle; a list for a selector (form:
      list of (value, human_label) or a plain list of values).
    """
    id: str
    label: str
    is_active: bool
    value: Any = None
    choices: list[Any] | None = None


# ─── Public API ──────────────────────────────────────────────────────────
def available_actions(component: "Component",
                       netlist: "Netlist") -> list[ImplicitAction]:
    """Returns the list of implicit actions available for `component`
    in the current state of the netlist. Empty if none.
    """
    out: list[ImplicitAction] = []
    t = component.type
    if t == "servo":
        out.append(_servo_external_power_action(component))
    elif t == "led":
        act = _led_series_value_action(component, netlist)
        if act is not None:
            out.append(act)
    elif t == "button":
        out.append(_btn_pullup_action(component, netlist))
    elif t in ("dht11", "dht22"):
        out.append(_dht_pullup_action(component, netlist))
    elif t == "ds18b20":
        out.append(_ds18b20_pullup_action(component, netlist))
    elif t == "buzzer":
        out.append(_buzzer_series_action(component, netlist))
    elif t == "a4988":
        out.append(_a4988_microstepping_action(component))
    return out


def apply_action(component: "Component", action_id: str,
                  netlist: "Netlist", *, value: Any = None) -> None:
    """Applies action `action_id` on `component`. Mutates `netlist` in
    place.

    - Toggle: `value` ignored, switches between 2 states.
    - Selector: `value` required (str/int), sets the target value.
    """
    if action_id == "servo_external_power":
        _toggle_servo_external_power(component, netlist)
        return
    if action_id == "led_series_value":
        if value is None:
            raise ValueError("led_series_value : value requis (selecteur)")
        _set_led_series_value(component, netlist, str(value))
        return
    if action_id == "btn_pullup_external":
        _toggle_btn_pullup_external(component, netlist)
        return
    if action_id == "dht_data_pullup":
        _toggle_dht_pullup(component, netlist)
        return
    if action_id == "buzzer_series_value":
        if value is None:
            raise ValueError("buzzer_series_value : value requis (selecteur)")
        _set_buzzer_series_value(component, netlist, str(value))
        return
    if action_id == "ds18b20_pullup_value":
        if value is None:
            raise ValueError("ds18b20_pullup_value : value requis (selecteur)")
        _set_ds18b20_pullup_value(component, netlist, str(value))
        return
    if action_id == "a4988_microstepping":
        if value is None:
            raise ValueError("a4988_microstepping : value requis (selecteur)")
        _set_a4988_microstepping(component, netlist, str(value))
        return
    raise ValueError(f"unknown implicit action id: {action_id!r}")


# ─── Servo: external power (BAT_5V) vs Arduino 5V ────────────────────────
def _servo_external_power_action(servo: "Component") -> ImplicitAction:
    vcc = servo.pin("VCC")
    is_external = vcc is not None and vcc.net.startswith("BAT_")
    return ImplicitAction(
        id="servo_external_power",
        label=(
            "Repasser sur le 5V Arduino"
            if is_external
            else "Alimenter par batterie externe"
        ),
        is_active=is_external,
        value=is_external,
        choices=None,
    )


def _toggle_servo_external_power(servo: "Component",
                                  netlist: "Netlist") -> None:
    """Switches the servo VCC power between Arduino 5V and BAT_5V.

    - 5V -> BAT_5V: adds a battery_external if not already present.
    - BAT_5V -> 5V: removes the battery_external if there is no other
      consumer of BAT_5V left.
    """
    vcc = servo.pin("VCC")
    if vcc is None:
        return
    if vcc.net.startswith("BAT_"):
        vcc.net = "5V"
        _maybe_remove_battery(netlist, "BAT_5V")
    else:
        vcc.net = "BAT_5V"
        _ensure_battery(netlist, plus_net="BAT_5V")


def _maybe_remove_battery(netlist: "Netlist", plus_net: str) -> None:
    """Removes the battery_external whose '+' pin is on `plus_net`
    when no other (non-battery) component draws from that net."""
    consumers = [
        c for c in netlist.components
        if c.type != "battery_external"
        and any(p.net == plus_net for p in c.pins)
    ]
    if consumers:
        return
    to_remove = [
        c for c in netlist.components
        if c.type == "battery_external"
        and any(p.net == plus_net for p in c.pins)
    ]
    for c in to_remove:
        netlist.components.remove(c)


def _ensure_battery(netlist: "Netlist", plus_net: str) -> None:
    """Adds a battery_external (V+, V-) if not already present on
    `plus_net`."""
    has_bat = any(
        c.type == "battery_external"
        and any(p.net == plus_net for p in c.pins)
        for c in netlist.components
    )
    if has_bat:
        return
    ref = netlist.next_ref("BAT")
    netlist.components.append(Component(
        ref=ref, type="battery_external", fn_id="", inferred=True,
        pins=[Pin("+", plus_net), Pin("-", "GND")],
    ))


# ─── LED: series R value (selector) ──────────────────────────────────────
LED_SERIES_CHOICES = ["0", "100", "220", "330", "470", "1000"]
LED_SERIES_DEFAULT = "220"
# "0" = equivalent to a short circuit (no R). Placed first to clearly signal
# the pedagogical option even though it is discouraged (the modal explains
# why via Ohm's law applied to the LED).


def _find_led_series_resistor(led: "Component",
                                netlist: "Netlist") -> "Component | None":
    """Finds the series R linked to the LED. Strategy:
    1. Looks for a resistor role=series that touches one of the LED's
       internal nets (pin A is bridged to an internal net NET_X by
       inference, and the series R sits between that NET_X and the Arduino pin).
    2. Otherwise, looks for a resistor with params.led_ref == led.ref in
       the report (but we don't have the report here).
    """
    led_nets = {p.net for p in led.pins}
    for c in netlist.components:
        if c.type != "resistor":
            continue
        if (c.attributes.get("role") or "").lower() != "series":
            continue
        if any(p.net in led_nets for p in c.pins):
            return c
    return None


def _led_series_value_action(led: "Component",
                              netlist: "Netlist") -> ImplicitAction | None:
    """Selector action on the LED series R value. If no R is present
    (case "None" chosen by the user), still returns an action with
    value="0" -- to let the user go back to a value > 0 via the gear."""
    r = _find_led_series_resistor(led, netlist)
    if r is None:
        # LED without series R: "None" mode. We still expose the action
        # so an R can be re-added via the modal.
        return ImplicitAction(
            id="led_series_value",
            label="Resistance serie : aucune (0 Ω)",
            is_active=True,   # = non-default state, gear active
            value="0",
            choices=list(LED_SERIES_CHOICES),
        )
    value = str(r.attributes.get("value") or LED_SERIES_DEFAULT)
    return ImplicitAction(
        id="led_series_value",
        label=f"Resistance serie : {value} Ω",
        is_active=(value != LED_SERIES_DEFAULT),
        value=value,
        choices=list(LED_SERIES_CHOICES),
    )


def _set_led_series_value(led: "Component", netlist: "Netlist",
                           value: str) -> None:
    """Sets the value of the series R linked to the LED. `value` is an
    ohms string ("220", "330", "1000", ...).

    Special case "0": physically removes the R from the netlist (not just
    a visible 0 Ω R). The LED is then reconnected directly to the Arduino
    pin. Explicit user choice (pedagogical: the modal explains why it is
    dangerous).

    If the user goes from a removed R to a value > 0, we RECREATE the R
    via the same logic as inference (`_apply_led_resistors`)."""
    from .netlist import Component as _C, Pin as _P
    from .inference import _next_internal_net

    r = _find_led_series_resistor(led, netlist)

    if str(value) == "0":
        # Removes the R and reconnects the LED directly to the Arduino.
        if r is None:
            return   # already no R
        r_a = r.pin("A")   # Arduino side (= original_net D6/D7/...)
        r_b = r.pin("B")   # LED side (= bridge_net NET_X)
        if r_a is None or r_b is None:
            return
        original_net = r_a.net
        bridge_net = r_b.net
        # All pins that pointed to bridge_net switch to original_net
        # (= the LED.A and any other internal dependency).
        for c in netlist.components:
            for p in c.pins:
                if p.net == bridge_net:
                    p.net = original_net
        netlist.components.remove(r)
        # Cleans up the led_series_resistor warnings linked to this R.
        netlist.warnings = [
            w for w in netlist.warnings
            if not (w.code == "led_series_resistor"
                    and w.params.get("resistor_ref") == r.ref)
        ]
        return

    if r is not None:
        # Existing R, just modify the value.
        r.attributes["value"] = str(value)
        return

    # No existing R (= LED was set to "None" earlier) and the user now
    # requests a value > 0 -> we recreate it.
    a_pin = led.pin("A")
    if a_pin is None or _is_power_or_ground(a_pin.net):
        return
    original_net = a_pin.net
    bridge_net = _next_internal_net(netlist)
    a_pin.net = bridge_net
    new_ref = netlist.next_ref("R")
    netlist.add_component(_C(
        ref=new_ref, type="resistor", fn_id=led.fn_id, inferred=True,
        pins=[_P("A", original_net), _P("B", bridge_net)],
        attributes={"value": str(value), "role": "series"},
    ))


def _is_power_or_ground(net: str) -> bool:
    """True if the net is a power or ground rail (not an Arduino pin)."""
    if not net:
        return True
    upper = net.upper()
    return upper in ("GND", "VCC", "5V", "3V3", "3.3V") or upper.startswith("BAT_")


# ─── BTN: internal pullup (INPUT_PULLUP) vs external (R 10k) ─────────────
BTN_PULLUP_VALUE = "10k"


def _find_btn_pullup(btn: "Component",
                      netlist: "Netlist") -> "Component | None":
    """Finds a pullup R connected to the button's signal (pin named
    'SIG' or the non-GND non-VCC pin). Strategy: iterate over the
    role=pullup resistors and match a net."""
    btn_nets = {p.net for p in btn.pins}
    for c in netlist.components:
        if c.type != "resistor":
            continue
        if (c.attributes.get("role") or "").lower() != "pullup":
            continue
        if any(p.net in btn_nets for p in c.pins):
            return c
    return None


def _btn_pullup_action(btn: "Component",
                        netlist: "Netlist") -> ImplicitAction:
    """Toggle: external pullup R present vs absent (INPUT_PULLUP on the
    code side). `is_active=True` when the external R is present."""
    r = _find_btn_pullup(btn, netlist)
    is_external = r is not None
    return ImplicitAction(
        id="btn_pullup_external",
        label=(
            "Passer en INPUT_PULLUP interne"
            if is_external
            else "Utiliser une R pullup externe (10k)"
        ),
        is_active=is_external,
        value=is_external,
        choices=None,
    )


def _toggle_btn_pullup_external(btn: "Component",
                                 netlist: "Netlist") -> None:
    """Switches between an external pullup R (10k between SIG and 5V) and
    internal INPUT_PULLUP (no R)."""
    r = _find_btn_pullup(btn, netlist)
    if r is not None:
        netlist.components.remove(r)
        return
    sig_net = _btn_signal_net(btn)
    if sig_net is None:
        return
    ref = netlist.next_ref("R")
    netlist.components.append(Component(
        ref=ref, type="resistor", fn_id=btn.fn_id, inferred=True,
        pins=[Pin("A", "5V"), Pin("B", sig_net)],
        attributes={"value": BTN_PULLUP_VALUE, "role": "pullup"},
    ))


def _btn_signal_net(btn: "Component") -> str | None:
    """Returns the button's signal net (pin SIG or equivalent, excluding
    GND and 5V)."""
    for name in ("SIG", "S", "OUT", "DATA"):
        p = btn.pin(name)
        if p is not None and p.net not in ("GND", "5V"):
            return p.net
    for p in btn.pins:
        if p.net not in ("GND", "5V") and not p.net.startswith("BAT_"):
            return p.net
    return None


# ─── DHT: data pullup R (toggle) ─────────────────────────────────────────
DHT_PULLUP_VALUE = "4.7k"


def _find_dht_pullup(dht: "Component",
                      netlist: "Netlist") -> "Component | None":
    """Finds a pullup R connected to the DHT's data."""
    data_net = _dht_data_net(dht)
    if data_net is None:
        return None
    for c in netlist.components:
        if c.type != "resistor":
            continue
        if (c.attributes.get("role") or "").lower() != "pullup":
            continue
        if any(p.net == data_net for p in c.pins):
            return c
    return None


def _dht_data_net(dht: "Component") -> str | None:
    """Returns the net of the DHT's DATA pin (or the first non-power
    signal pin)."""
    for name in ("DATA", "OUT", "SIG", "S"):
        p = dht.pin(name)
        if p is not None and p.net not in ("GND", "5V", "3V3"):
            return p.net
    for p in dht.pins:
        if p.net not in ("GND", "5V", "3V3") and not p.net.startswith("BAT_"):
            return p.net
    return None


def _dht_pullup_action(dht: "Component",
                        netlist: "Netlist") -> ImplicitAction:
    """Toggle: pullup R 4.7k present vs absent."""
    r = _find_dht_pullup(dht, netlist)
    has_pullup = r is not None
    return ImplicitAction(
        id="dht_data_pullup",
        label=(
            "Retirer la R pullup (deconseille)"
            if has_pullup
            else "Ajouter une R pullup 4.7k"
        ),
        is_active=has_pullup,
        value=has_pullup,
        choices=None,
    )


def _toggle_dht_pullup(dht: "Component", netlist: "Netlist") -> None:
    r = _find_dht_pullup(dht, netlist)
    if r is not None:
        netlist.components.remove(r)
        return
    data_net = _dht_data_net(dht)
    if data_net is None:
        return
    ref = netlist.next_ref("R")
    netlist.components.append(Component(
        ref=ref, type="resistor", fn_id=dht.fn_id, inferred=True,
        pins=[Pin("A", "5V"), Pin("B", data_net)],
        attributes={"value": DHT_PULLUP_VALUE, "role": "pullup"},
    ))


# ─── Buzzer: series R (selector with 'none' option) ──────────────────────
BUZZER_SERIES_CHOICES = ["none", "100", "220"]
BUZZER_SERIES_DEFAULT = "100"


def _find_buzzer_series_resistor(buz: "Component",
                                   netlist: "Netlist") -> "Component | None":
    """Finds the buzzer series R (role=series on one of the buzzer's nets)."""
    buz_nets = {p.net for p in buz.pins}
    for c in netlist.components:
        if c.type != "resistor":
            continue
        if (c.attributes.get("role") or "").lower() != "series":
            continue
        if any(p.net in buz_nets for p in c.pins):
            return c
    return None


def _buzzer_series_action(buz: "Component",
                            netlist: "Netlist") -> ImplicitAction:
    """Selector: series R value, or 'none' if absent."""
    r = _find_buzzer_series_resistor(buz, netlist)
    if r is None:
        current = "none"
    else:
        current = str(r.attributes.get("value") or BUZZER_SERIES_DEFAULT)
    return ImplicitAction(
        id="buzzer_series_value",
        label=(
            "Sans resistance serie"
            if current == "none"
            else f"Resistance serie : {current} Ω"
        ),
        is_active=(current != BUZZER_SERIES_DEFAULT),
        value=current,
        choices=list(BUZZER_SERIES_CHOICES),
    )


def _set_buzzer_series_value(buz: "Component", netlist: "Netlist",
                              value: str) -> None:
    """Sets the buzzer series R to the target value. `value` can be 'none'
    to remove the R (the buzzer's + pin then takes back the direct Arduino
    net). If an R must be created, we insert an intermediate net NET_X
    just like `inference._apply_buzzer_series_resistors` does.
    """
    r = _find_buzzer_series_resistor(buz, netlist)
    plus_pin = buz.pin("+") or _first_signal_pin(buz)
    if plus_pin is None:
        return
    if value == "none":
        if r is None:
            return
        # The buzzer's + pin is on the bridge_net (R side), the R's other
        # pin is on the direct Arduino pin. We move plus_pin back to the
        # Arduino pin, then remove the R.
        bridge_net = plus_pin.net
        original_net = next(
            (p.net for p in r.pins if p.net != bridge_net), None,
        )
        if original_net is not None:
            plus_pin.net = original_net
        netlist.components.remove(r)
        return
    if r is not None:
        r.attributes["value"] = str(value)
        return
    # No existing R: we insert bridge_net between plus_pin and the
    # Arduino pin.
    from . import inference as _inf
    original_net = plus_pin.net
    bridge_net = _inf._next_internal_net(netlist)
    plus_pin.net = bridge_net
    ref = netlist.next_ref("R")
    netlist.components.append(Component(
        ref=ref, type="resistor", fn_id=buz.fn_id, inferred=True,
        pins=[Pin("A", original_net), Pin("B", bridge_net)],
        attributes={"value": str(value), "role": "series"},
    ))


def _first_signal_pin(c: "Component") -> "Pin | None":
    """Returns the first signal pin (excluding GND/5V/3V3/BAT_)."""
    for p in c.pins:
        if (p.net not in ("GND", "5V", "3V3")
                and not p.net.startswith("BAT_")):
            return p
    return None


# ─── DS18B20: DATA pullup R (selector 2.2k / 4.7k / 10k / none) ──────────
# Unlike the DHT (toggle 4.7k yes/no), the DS18B20 pullup value depends on
# the length of the OneWire bus: 10k for a short and clean bus, 4.7k
# standard (datasheet), 2.2k for a long or capacitive bus.
DS18B20_PULLUP_CHOICES = ["none", "2.2k", "4.7k", "10k"]
DS18B20_PULLUP_DEFAULT = "4.7k"


def _find_ds18b20_pullup(sensor: "Component",
                          netlist: "Netlist") -> "Component | None":
    """Finds a pullup R connected to the DS18B20's DATA."""
    data_net = _ds18b20_data_net(sensor)
    if data_net is None:
        return None
    for c in netlist.components:
        if c.type != "resistor":
            continue
        if (c.attributes.get("role") or "").lower() != "pullup":
            continue
        if any(p.net == data_net for p in c.pins):
            return c
    return None


def _ds18b20_data_net(sensor: "Component") -> str | None:
    """Returns the net of the DS18B20's DATA pin (or first non-power
    signal pin)."""
    for name in ("DATA", "DQ", "OUT", "SIG", "S"):
        p = sensor.pin(name)
        if p is not None and p.net not in ("GND", "5V", "3V3"):
            return p.net
    for p in sensor.pins:
        if p.net not in ("GND", "5V", "3V3") and not p.net.startswith("BAT_"):
            return p.net
    return None


def _ds18b20_pullup_action(sensor: "Component",
                             netlist: "Netlist") -> ImplicitAction:
    """Selector: DATA pullup value, or 'none' if absent."""
    r = _find_ds18b20_pullup(sensor, netlist)
    if r is None:
        current = "none"
    else:
        current = str(r.attributes.get("value") or DS18B20_PULLUP_DEFAULT)
    return ImplicitAction(
        id="ds18b20_pullup_value",
        label=(
            "Sans pullup (deconseille)"
            if current == "none"
            else f"Pullup DATA : {current} Ω"
        ),
        is_active=(current != DS18B20_PULLUP_DEFAULT),
        value=current,
        choices=list(DS18B20_PULLUP_CHOICES),
    )


def _set_ds18b20_pullup_value(sensor: "Component", netlist: "Netlist",
                                value: str) -> None:
    """Sets the DS18B20's DATA pullup to the target value. `value='none'`
    removes the R. Otherwise creates/modifies an R between 5V and the
    DATA net."""
    r = _find_ds18b20_pullup(sensor, netlist)
    if value == "none":
        if r is not None:
            netlist.components.remove(r)
        return
    if r is not None:
        r.attributes["value"] = str(value)
        return
    data_net = _ds18b20_data_net(sensor)
    if data_net is None:
        return
    ref = netlist.next_ref("R")
    netlist.components.append(Component(
        ref=ref, type="resistor", fn_id=sensor.fn_id, inferred=True,
        pins=[Pin("A", "5V"), Pin("B", data_net)],
        attributes={"value": str(value), "role": "pullup"},
    ))


# ─── A4988: microstepping (MS1/MS2/MS3 -> GND or 5V) ─────────────────────
A4988_MICROSTEP_DEFAULT = "full"
# List of (value, human_label). The order = display order of the radios.
A4988_MICROSTEP_CHOICES: list[tuple[str, str]] = [
    ("full", "Pas complet"),
    ("1/2",  "1/2 pas"),
    ("1/4",  "1/4 pas"),
    ("1/8",  "1/8 pas"),
    ("1/16", "1/16 pas"),
]
# Truth table Allegro A4988 : (MS1, MS2, MS3) -- 0 = GND, 1 = 5V.
A4988_MICROSTEP_TABLE: dict[str, tuple[int, int, int]] = {
    "full": (0, 0, 0),
    "1/2":  (1, 0, 0),
    "1/4":  (0, 1, 0),
    "1/8":  (1, 1, 0),
    "1/16": (1, 1, 1),
}
_A4988_MS_PINS: tuple[str, str, str] = ("MS1", "MS2", "MS3")


def _a4988_pin_bit(drv: "Component", name: str) -> int:
    """Returns 1 if the driver's <name> pin is wired to 5V (or a high
    alias), 0 otherwise (GND, empty or unknown case = full step
    safe-default)."""
    p = drv.pin(name)
    if p is None:
        return 0
    net_up = (p.net or "").upper()
    if net_up in ("5V", "VCC", "3V3", "3.3V"):
        return 1
    return 0


def _a4988_microstepping_action(drv: "Component") -> ImplicitAction:
    """Selector action on the A4988's microstepping mode. Reads the
    current state via the nets of the MS1/MS2/MS3 pins (= equivalent to
    physical jumpers)."""
    bits = tuple(_a4988_pin_bit(drv, name) for name in _A4988_MS_PINS)
    current = A4988_MICROSTEP_DEFAULT
    for mode, expected in A4988_MICROSTEP_TABLE.items():
        if bits == expected:
            current = mode
            break
    label_map = dict(A4988_MICROSTEP_CHOICES)
    return ImplicitAction(
        id="a4988_microstepping",
        label=f"Microstepping : {label_map.get(current, current)}",
        is_active=(current != A4988_MICROSTEP_DEFAULT),
        value=current,
        choices=list(A4988_MICROSTEP_CHOICES),
    )


def _set_a4988_microstepping(drv: "Component", netlist: "Netlist",
                              value: str) -> None:
    """Wires (or rewires) the A4988's MS1/MS2/MS3 pins to GND or 5V
    according to the truth table. Mutates the netlist in place. If an MS
    pin is missing (legacy case: project from before the MS were added by
    default), it is created."""
    del netlist  # uniform signature with the other set_*, not used
    bits = A4988_MICROSTEP_TABLE.get(str(value))
    if bits is None:
        return
    for name, bit in zip(_A4988_MS_PINS, bits):
        target = "5V" if bit else "GND"
        p = drv.pin(name)
        if p is None:
            drv.pins.append(Pin(name, target))
        else:
            p.net = target
