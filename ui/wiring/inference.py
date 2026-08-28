"""Netlist inference rules (adding implicit components).

MVP1 — two rules + a conflict detection pass:

  R1  (led_series_resistor)  : any LED without a series resistor gets
                               a current-limiting resistor (220R / 330R).
  R2  (button_external_pullup) : any button whose `pull` attribute is
                               not `internal` gets a 10k pull-up resistor.

The rules modify the netlist in place and mark added components
as `inferred=True`. A `detect_conflicts()` pass produces
warnings without mutating the netlist.
"""
from __future__ import annotations

from .netlist import (
    Component, Netlist, Pin,
    SEVERITY_ERROR, SEVERITY_WARNING,
)


# LED color -> recommended value (Lucide-friendly values = common in
# educational kits). Unknown colors fall back to 220R.
LED_COLOR_TO_R: dict[str, str] = {
    "red":    "220",
    "green":  "220",
    "yellow": "220",
    "orange": "220",
    "blue":   "330",
    "white":  "330",
}

PULLUP_VALUE = "10k"
DHT_PULLUP_VALUE = "4.7k"
BUZZER_SERIES_VALUE = "100"


def apply_rules(netlist: Netlist) -> Netlist:
    """Apply the rules in place. Returns the same netlist (chainable)."""
    _apply_led_resistors(netlist)
    _apply_button_pullups(netlist)
    _apply_dht_data_pullups(netlist)
    _apply_ds18b20_pullups(netlist)
    _apply_buzzer_series_resistors(netlist)
    _apply_motor_drivers_and_battery(netlist)
    _split_battery_for_voltage_compat(netlist)
    return netlist


# ── Motor rule: driver + external power supply ───────────────────────────
# Motors (DC, stepper) are NEVER wired directly to the Arduino:
# - DC motor: needs an H-bridge (L298N) to handle direction and
#   current. Created by the ambiguity modal with an internal attribute
#   `_control_pin`. The rule adds the wired L298N + a battery_external.
# - Stepper 28BYJ-48: detected by the fingerprint with VCC=BAT_5V already.
#   The rule just makes sure a battery_external exists.
def _apply_motor_drivers_and_battery(netlist: Netlist) -> None:
    needs_battery = False

    # Step 1: remove motors marked _skip_wiring=True from the netlist.
    # These motors were recognized as dc_motor by the detector or the
    # ambiguity modal but the user (or the editorial limit) decided
    # NOT to wire them. We preserve them in metadata so that
    # instructions.render_instructions shows a dedicated section
    # ("Detected but not wired"), but they leave the active netlist
    # so that layout/routing don't try to place them.
    skipped: list[dict] = []
    keep: list[Component] = []
    for c in netlist.components:
        if (c.type == "dc_motor"
                and c.attributes.get("_skip_wiring") is True):
            skipped.append({
                "ref": c.ref,
                "control_pin": c.attributes.get("_control_pin", ""),
                "aux_dir_pins": list(c.attributes.get("_aux_dir_pins") or []),
            })
        else:
            keep.append(c)
    if skipped:
        netlist.components[:] = keep
        netlist.metadata["_skipped_motors"] = skipped

    # Editorial limit: 2 DC motors max. All catalogued DC drivers
    # are dual H-bridges (1 chip = 2 motors physically). Beyond that,
    # you'd need a shield (cf TODO 1) or to parallelize on the same
    # outputs (not very educational). Defense in depth: if we get here
    # with >2 motors after skip, we still report it (modal safeguard
    # escape case). In normal flow this branch doesn't trigger.
    dc_motors_with_ctrl = [
        c for c in netlist.components
        if c.type == "dc_motor" and c.attributes.get("_control_pin")
    ]
    if len(dc_motors_with_ctrl) > 2:
        netlist.add_warning(
            code="too_many_dc_motors",
            severity=SEVERITY_WARNING,
            message=f"{len(dc_motors_with_ctrl)} moteurs DC detectes. "
                    f"PromptuinoUI se limite a 2 moteurs DC max.",
            refs=[m.ref for m in dc_motors_with_ctrl],
            params={"count": len(dc_motors_with_ctrl), "max_supported": 2},
        )

    # Global DC driver (Phase A): from user prompt/doc only
    # (cf markers._detect_suggested_dc_driver). L298N fallback when no
    # driver name is mentioned -- historical behavior preserved.
    suggested_dc_driver = (
        netlist.metadata.get("_suggested_dc_driver") or "l298n"
    )

    # DC motors -> create one H-bridge driver per pair of motors sharing
    # the same driver_type (all catalogued DC drivers are dual
    # H-bridges: 1 chip = 2 motors). Typical cases:
    #  - 1 DC motor -> 1 driver (side A only, side B not wired)
    #  - 2 DC motors same driver_type -> 1 shared driver (A + B)
    #  - 3+ DC motors same driver_type -> floor(n/2) drivers + 1 if odd
    #  - 2 DC motors different types (rare case) -> 2 distinct drivers
    # Per-motor convention: "PWM on 1 Arduino pin (control_pin) + other
    # direction pins fixed by 5V/GND jumper" (fixed direction, variable speed)
    # or bidirectional if markers._group_dc_motor_pins grouped N pins.
    motors_to_drive: list[tuple[Component, str]] = []
    for motor in [c for c in list(netlist.components) if c.type == "dc_motor"]:
        if not motor.attributes.get("_control_pin"):
            continue
        if _has_dc_driver_for(netlist, motor.ref):
            continue
        chosen = motor.attributes.get("_chosen_driver")
        dt = chosen or suggested_dc_driver
        motors_to_drive.append((motor, dt))

    # Group by driver_type for the dual H-bridge pairing.
    # Since 2026-05-19: all catalogued DC drivers are dual
    # H-bridges (= 1 chip = 2 motors physically) and sharing is
    # active for ALL, off-BB as well as on-BB DIP. The vertical stacking
    # of the 2 motors above-BB (cf layout/layout.py) eliminates the routing
    # conflict that existed before for on-BB DIPs.
    # Remaining limitation: EXACTLY 2 DC motors in the scene
    # (3+: fallback 1-driver-per-motor, multi-motor layout not resolved).
    _DUAL_PAIR_CAPABLE_DRIVERS = {
        "l298n", "l293d_module",     # off-BB
        "l293d", "tb6612fng", "drv8833",  # on-BB DIPs
    }
    motors_by_type: dict[str, list[list[Component]]] = {}
    if len(motors_to_drive) == 2:
        groups: dict[str, list[Component]] = {}
        for motor, dt in motors_to_drive:
            groups.setdefault(dt, []).append(motor)
        for dt, lst in groups.items():
            # Pair if: 2 motors same type AND dual-pair capable driver.
            if len(lst) == 2 and dt in _DUAL_PAIR_CAPABLE_DRIVERS:
                motors_by_type[dt] = [lst]
            else:
                motors_by_type[dt] = [[m] for m in lst]
    else:
        # 0, 1 or 3+ motors: no sharing.
        for motor, dt in motors_to_drive:
            motors_by_type.setdefault(dt, []).append([motor])

    def _extract_motor_info(motor: Component) -> dict:
        """Allocate 2 internal nets for M+/M- and return the dict expected
        by _build_dc_driver_pins. Pop the motor's internal attributes.

        Important: we allocate then ASSIGN each net before generating
        the next one -- otherwise `_next_internal_net` returns the same NET_A
        twice (it scans assigned pins to find the first
        free name).
        """
        n_out1 = _next_internal_net(netlist)
        m_plus = motor.pin("M+")
        if m_plus is not None:
            m_plus.net = n_out1
        n_out2 = _next_internal_net(netlist)
        m_minus = motor.pin("M-")
        if m_minus is not None:
            m_minus.net = n_out2
        # Pop _chosen_driver (already read into dt) so it doesn't linger
        # in the final netlist.
        motor.attributes.pop("_chosen_driver", None)
        return {
            "control_pin": motor.attributes.pop("_control_pin"),
            "n_out1": n_out1,
            "n_out2": n_out2,
            "aux_dir_pins": motor.attributes.pop("_aux_dir_pins", None),
        }

    for dt, groups in motors_by_type.items():
        for group in groups:
            motor_a = group[0]
            motor_b = group[1] if len(group) >= 2 else None
            info_a = _extract_motor_info(motor_a)
            info_b = _extract_motor_info(motor_b) if motor_b else None
            ref = netlist.next_ref("U")
            paired = (motor_a.ref if motor_b is None
                      else f"{motor_a.ref},{motor_b.ref}")
            netlist.add_component(Component(
                ref=ref, type=dt, fn_id=motor_a.fn_id, inferred=True,
                pins=_build_dc_driver_pins(dt, info_a, info_b),
                attributes={"_paired_motor": paired},
            ))
            needs_battery = True

    # ULN2003 drivers -> add the 28BYJ-48 motor off-BB connected via
    # 5 wires (COM + 4 phases A/B/C/D), all via internal nets SHARED
    # with the driver's 5 JST holes -- so the router draws 5 visible
    # wires between driver and motor, and NO external wire to the BB
    # for the stepper. The motor power passes internally through the module's
    # PCB (driver.VCC = electrically = driver.JST_PWR), but we
    # represent it as 2 distinct nets in the netlist (BAT_5V for
    # VCC, internal bus for JST_PWR + stepper.COM).
    for drv in [c for c in list(netlist.components) if c.type == "uln2003"]:
        if _has_stepper_for(netlist, drv.ref):
            continue   # idempotent
        ref = netlist.next_ref("M")
        stepper = Component(
            ref=ref, type="stepper_motor", fn_id=drv.fn_id, inferred=True,
            pins=[Pin("COM", ""),
                  Pin("A", ""), Pin("B", ""),
                  Pin("C", ""), Pin("D", "")],
            attributes={"_paired_driver": drv.ref},
        )
        netlist.add_component(stepper)
        # Allocate 5 internal nets: 4 phases (stepper {A..D} <-> drv OUT1..4)
        # + 1 motor power bus (stepper.COM <-> drv.JST_PWR).
        for stepper_name, drv_name in (("A", "OUT1"), ("B", "OUT2"),
                                         ("C", "OUT3"), ("D", "OUT4"),
                                         ("COM", "JST_PWR")):
            net = _next_internal_net(netlist)
            sp = stepper.pin(stepper_name)
            if sp is not None:
                sp.net = net
            dp = drv.pin(drv_name)
            if dp is None:
                # Pin not in the driver's netlist: we add it so
                # it's visible in SVG and used by the router.
                drv.pins.append(Pin(drv_name, net))
            else:
                dp.net = net
        needs_battery = True

    # A4988 drivers -> add a NEMA17 off-BB connected via 4 wires to the
    # coils. The motor's 4 terminals (1A/1B/2A/2B) share internal
    # nets with the driver's coil pins. The driver's VMOT is already on
    # BAT_5V (cf markers.py), VDD on Arduino 5V. battery_external added
    # below if needed.
    for drv in [c for c in list(netlist.components) if c.type == "a4988"]:
        if _has_nema17_for(netlist, drv.ref):
            continue   # idempotent
        ref = netlist.next_ref("M")
        nema = Component(
            ref=ref, type="nema17", fn_id=drv.fn_id, inferred=True,
            pins=[Pin("1A", ""), Pin("1B", ""),
                  Pin("2A", ""), Pin("2B", "")],
            attributes={"_paired_driver": drv.ref},
        )
        netlist.add_component(nema)
        # Allocate 4 internal nets: 1 per coil terminal.
        for coil_name in ("1A", "1B", "2A", "2B"):
            net = _next_internal_net(netlist)
            np = nema.pin(coil_name)
            if np is not None:
                np.net = net
            dp = drv.pin(coil_name)
            if dp is None:
                drv.pins.append(Pin(coil_name, net))
            else:
                dp.net = net
        needs_battery = True

    # Add battery_external only once if needed (a single
    # battery_external is enough to power all motors sharing
    # the BAT_5V rail).
    if needs_battery and not any(c.type == "battery_external"
                                  for c in netlist.components):
        ref = netlist.next_ref("BAT")
        netlist.add_component(Component(
            ref=ref, type="battery_external", fn_id="", inferred=True,
            pins=[Pin("+", "BAT_5V"), Pin("-", "GND")],
            attributes={},
        ))


# ── Voltage rule: split the battery if loads are incompatible ────────────
# When a single battery_external powers several components whose
# voltage ranges don't overlap (e.g. servo 4.8-6 V + NEMA17 8-35 V),
# we split into 2 distinct batteries with different BAT_5V nets.
# Each voltage-compatible group gets its own battery.
#
# Strategy: greedy first-fit. We iterate over the loads in order, placing
# them into the first group whose intersection stays non-empty; otherwise
# we create a new group. 2 groups in practice for typical cases.
_BATTERY_POWER_PIN_NAMES = {"VS", "VCC", "VM", "VMOT", "VDD"}


def _load_voltage_range(load_type: str, driver_type: str | None
                         ) -> tuple[float, float] | None:
    """Voltage range of a load (motor_type, driver_type) or (servo, None).
    Deferred import to avoid coupling `ui/wiring/` (orchestration) to
    `ui/wiring/layout/` (catalog) at the module level."""
    from .layout.component_catalog import BATTERY_VOLTAGE_RANGES
    return BATTERY_VOLTAGE_RANGES.get((load_type, driver_type))


def _split_battery_for_voltage_compat(netlist: Netlist) -> None:
    # 1. Only one existing battery? otherwise no-op (already split manually
    #    or no battery to split).
    bats = [c for c in netlist.components if c.type == "battery_external"]
    if len(bats) != 1:
        return
    bat = bats[0]
    plus_pin = bat.pin("+")
    if plus_pin is None or not plus_pin.net:
        return
    plus_net = plus_pin.net

    # 2. Identify the loads on this plus_net.
    # Drivers (DC/stepper): VS/VM/VMOT/VCC pin on plus_net.
    # For each driver, find the associated motors via the output
    # nets (OUT*/1A-2B/...) shared with the motor's pins (M+/M-/A-D/
    # COIL_*).
    motors = [c for c in netlist.components
              if c.type in ("dc_motor", "stepper_motor", "nema17")]
    drivers = [c for c in netlist.components if c.type in (
        "l298n", "l293d", "l293d_module", "uln2003",
        "a4988", "tb6612fng", "drv8833"
    )]

    def _driver_powers_from_bat(d: Component) -> bool:
        return any(p.name in _BATTERY_POWER_PIN_NAMES and p.net == plus_net
                    for p in d.pins)

    def _motors_of_driver(d: Component) -> list[Component]:
        d_nets = {p.net for p in d.pins if p.net}
        return [m for m in motors
                if d_nets & {p.net for p in m.pins if p.net}]

    # List of loads: (main_load_ref, range, associated_refs_to_repoint)
    # main_load_ref is just for tracing; associated_refs_to_repoint
    # contains the components whose pin on plus_net must be renamed
    # when switching groups.
    loads: list[tuple[str, tuple[float, float], list[str]]] = []

    for d in drivers:
        if not _driver_powers_from_bat(d):
            continue
        attached = _motors_of_driver(d)
        if not attached:
            continue
        for m in attached:
            rng = _load_voltage_range(m.type, d.type)
            if rng is None:
                continue
            loads.append((m.ref, rng, [d.ref]))

    # Servos powered directly (VCC on plus_net).
    for c in netlist.components:
        if c.type != "servo":
            continue
        vcc = c.pin("VCC")
        if vcc is None or vcc.net != plus_net:
            continue
        rng = _load_voltage_range("servo", None)
        if rng is None:
            continue
        loads.append((c.ref, rng, [c.ref]))

    if len(loads) < 2:
        return   # nothing to split

    # 3. Greedy first-fit into voltage-compatible groups.
    groups: list[tuple[list[str], list[str], tuple[float, float]]] = []
    # each group: (load_refs, repoint_refs, (vmin, vmax))
    for load_ref, rng, repoint_refs in loads:
        placed_into = -1
        for i, (lrefs, rrefs, (gmin, gmax)) in enumerate(groups):
            new_min = max(gmin, rng[0])
            new_max = min(gmax, rng[1])
            if new_min <= new_max:
                groups[i] = (lrefs + [load_ref],
                              rrefs + repoint_refs,
                              (new_min, new_max))
                placed_into = i
                break
        if placed_into < 0:
            groups.append(([load_ref], list(repoint_refs), rng))

    if len(groups) < 2:
        return   # everything compatible with a single battery

    # 4. For each group beyond the first, create a new battery +
    #    new net BAT_5V_<i>. The first group keeps plus_net + the original
    #    battery.
    for i, (_lrefs, repoint_refs, _rng) in enumerate(groups[1:], start=2):
        new_net = f"{plus_net}_{i}"
        # Rename the power pin of each repointed component.
        seen: set[str] = set()
        for ref in repoint_refs:
            if ref in seen:
                continue
            seen.add(ref)
            c = netlist.by_ref(ref)
            if c is None:
                continue
            for p in c.pins:
                if p.net == plus_net and p.name in _BATTERY_POWER_PIN_NAMES:
                    p.net = new_net
        # Add the associated battery.
        new_ref = netlist.next_ref("BAT")
        netlist.add_component(Component(
            ref=new_ref, type="battery_external", fn_id="", inferred=True,
            pins=[Pin("+", new_net), Pin("-", "GND")],
            attributes={},
        ))


def _has_dc_driver_for(netlist: Netlist, motor_ref: str) -> bool:
    """True if a DC H-bridge driver is already paired with this motor
    (idempotence). We look at `_paired_motor` rather than c.type to
    accept any DC driver (L298N, TB6612FNG, DRV8833, ...).
    `_paired_motor` is a comma-separated list of refs (e.g.
    "M1,M2") when 2 motors share the same dual H-bridge driver."""
    for c in netlist.components:
        paired = c.attributes.get("_paired_motor")
        if not paired:
            continue
        if motor_ref in [r.strip() for r in paired.split(",")]:
            return True
    return False


# Standard pinout per driver, depending on what the AI generated:
# - a single OUTPUT pin (mode "fixed direction, variable speed"): control_pin =
#   PWM, other pins fixed by 5V/GND jumpers.
# - 1 PWM + 1-2 direction pins (mode "dynamic speed + direction"):
#   control_pin = PWM (on ENA / PWMA depending on driver), aux_dir_pins =
#   the pins driven by digitalWrite for direction (on IN1/IN2 or
#   AIN1/AIN2). This 2nd mode happens when markers._group_dc_motor_pins
#   groups N ambiguous LEDs into 1 bidirectional DC motor candidate.
#
# All catalogued DC drivers (L298N, L293D, L293D module, TB6612FNG,
# DRV8833) are **dual H-bridges**: 1 driver can drive 2 DC
# motors. When 2 DC motors share the same driver_type, we pair them on
# a single driver via the optional 2nd argument `motor_b`.
def _build_dc_driver_pins(
    driver_type: str,
    motor_a: dict,
    motor_b: dict | None = None,
) -> list[Pin]:
    """`motor_a` / `motor_b`: dict with keys `control_pin`, `n_out1`,
    `n_out2`, `aux_dir_pins` (optional). `motor_b=None` -> 1-motor mode
    (side A only), the ENB/IN3/IN4/OUT3/OUT4 pins (or B equivalents)
    are not added to the netlist."""
    a_ctrl = motor_a["control_pin"]
    a_out1 = motor_a["n_out1"]
    a_out2 = motor_a["n_out2"]
    a_aux  = motor_a.get("aux_dir_pins") or []

    b_ctrl = motor_b["control_pin"] if motor_b else None
    b_out1 = motor_b["n_out1"]      if motor_b else None
    b_out2 = motor_b["n_out2"]      if motor_b else None
    b_aux  = (motor_b.get("aux_dir_pins") if motor_b else []) or []

    if driver_type == "tb6612fng":
        # Motor A: AO1/AO2, PWMA, AIN1/AIN2
        a_ain1 = a_aux[0] if len(a_aux) >= 1 else "5V"
        a_ain2 = a_aux[1] if len(a_aux) >= 2 else "GND"
        pins = [
            Pin("VM",   "BAT_5V"),
            Pin("VCC",  "5V"),
            Pin("GND",  "GND"),
            Pin("AO1",  a_out1),
            Pin("AO2",  a_out2),
            Pin("STBY", "5V"),
            Pin("AIN1", a_ain1),
            Pin("AIN2", a_ain2),
            Pin("PWMA", a_ctrl),
        ]
        if motor_b is not None:
            b_bin1 = b_aux[0] if len(b_aux) >= 1 else "5V"
            b_bin2 = b_aux[1] if len(b_aux) >= 2 else "GND"
            pins += [
                Pin("BO1",  b_out1),
                Pin("BO2",  b_out2),
                Pin("BIN1", b_bin1),
                Pin("BIN2", b_bin2),
                Pin("PWMB", b_ctrl),
            ]
        return pins

    if driver_type == "drv8833":
        a_in2 = a_aux[0] if len(a_aux) >= 1 else "GND"
        pins = [
            Pin("SLEEP", "5V"),
            Pin("OUT1",  a_out1),
            Pin("OUT2",  a_out2),
            Pin("IN1",   a_ctrl),
            Pin("IN2",   a_in2),
            Pin("VCC",   "BAT_5V"),
            Pin("GND",   "GND"),
        ]
        if motor_b is not None:
            b_in4 = b_aux[0] if len(b_aux) >= 1 else "GND"
            pins += [
                Pin("OUT3", b_out1),
                Pin("OUT4", b_out2),
                Pin("IN3",  b_ctrl),
                Pin("IN4",  b_in4),
            ]
        return pins

    # l298n / l293d / l293d_module: same canonical pinout.
    if len(a_aux) >= 1:
        a_ena = a_ctrl
        a_in1 = a_aux[0]
        a_in2 = a_aux[1] if len(a_aux) >= 2 else "GND"
    else:
        a_ena = "5V"
        a_in1 = a_ctrl
        a_in2 = "GND"
    pins = [
        Pin("ENA",  a_ena),
        Pin("IN1",  a_in1),
        Pin("IN2",  a_in2),
        Pin("VCC",  "5V"),
        Pin("VS",   "BAT_5V"),
        Pin("GND",  "GND"),
        Pin("OUT1", a_out1),
        Pin("OUT2", a_out2),
    ]
    if motor_b is not None:
        if len(b_aux) >= 1:
            b_enb = b_ctrl
            b_in3 = b_aux[0]
            b_in4 = b_aux[1] if len(b_aux) >= 2 else "GND"
        else:
            b_enb = "5V"
            b_in3 = b_ctrl
            b_in4 = "GND"
        pins += [
            Pin("ENB",  b_enb),
            Pin("IN3",  b_in3),
            Pin("IN4",  b_in4),
            Pin("OUT3", b_out1),
            Pin("OUT4", b_out2),
        ]
    return pins


def _has_stepper_for(netlist: Netlist, driver_ref: str) -> bool:
    """True if a stepper_motor is already paired with this driver."""
    for c in netlist.components:
        if c.type == "stepper_motor" and c.attributes.get("_paired_driver") == driver_ref:
            return True
    return False


def _has_nema17_for(netlist: Netlist, driver_ref: str) -> bool:
    """True if a nema17 is already paired with this driver."""
    for c in netlist.components:
        if c.type == "nema17" and c.attributes.get("_paired_driver") == driver_ref:
            return True
    return False


# ── Rule 1: series resistor for LEDs ──────────────────────────────────────
def _apply_led_resistors(netlist: Netlist) -> None:
    leds = [c for c in list(netlist.components) if c.type == "led"]
    for led in leds:
        a_pin = led.pin("A")
        if a_pin is None or _is_power_or_ground(a_pin.net):
            # LED wired oddly: no anode or anode on GND. We
            # don't touch it (the AI maybe knew something).
            continue
        if _has_series_resistor_on(netlist, a_pin.net, led.ref):
            continue
        # Insert an intermediate net between the micro pin and the anode.
        original_net = a_pin.net
        bridge_net = _next_internal_net(netlist)
        a_pin.net  = bridge_net   # the LED now sees the bridge

        color = (led.attributes.get("color") or "").lower()
        value = LED_COLOR_TO_R.get(color, "220")
        ref = netlist.next_ref("R")
        netlist.add_component(Component(
            ref=ref, type="resistor", fn_id=led.fn_id, inferred=True,
            pins=[Pin("A", original_net), Pin("B", bridge_net)],
            attributes={"value": value, "role": "series"},
        ))
        netlist.add_warning(
            code="led_series_resistor",
            severity=SEVERITY_WARNING,
            message=f"Resistance de limitation {value}Ω ajoutee "
                    f"automatiquement pour la LED {led.ref}.",
            refs=[led.ref, ref],
            params={"led_ref": led.ref, "resistor_ref": ref, "value": value},
        )


# ── Rule 2: external pull-up for buttons ──────────────────────────────────
def _apply_button_pullups(netlist: Netlist) -> None:
    buttons = [c for c in list(netlist.components) if c.type == "button"]
    for btn in buttons:
        pull = (btn.attributes.get("pull") or "").lower()
        if pull == "internal":
            continue   # INPUT_PULLUP on the code side -> no external R.
        # Identify the signal pin (the first of the two, by convention).
        sig = btn.pin("A")
        if sig is None or _is_power_or_ground(sig.net):
            continue
        if _has_pullup_on(netlist, sig.net):
            continue
        ref = netlist.next_ref("R")
        netlist.add_component(Component(
            ref=ref, type="resistor", fn_id=btn.fn_id, inferred=True,
            pins=[Pin("A", "5V"), Pin("B", sig.net)],
            attributes={"value": PULLUP_VALUE, "role": "pullup"},
        ))
        netlist.add_warning(
            code="button_external_pullup",
            severity=SEVERITY_WARNING,
            message=f"Pull-up externe {PULLUP_VALUE}Ω ajoutee pour "
                    f"le bouton {btn.ref}.",
            refs=[btn.ref, ref],
            params={"button_ref": btn.ref, "resistor_ref": ref,
                    "value": PULLUP_VALUE},
        )


# ── Rule 3: DATA pull-up for DHT11/DHT22 ─────────────────────────────────
def _apply_dht_data_pullups(netlist: Netlist) -> None:
    dhts = [c for c in list(netlist.components) if c.type in ("dht11", "dht22")]
    for dht in dhts:
        data_pin = dht.pin("DATA")
        if data_pin is None or _is_power_or_ground(data_pin.net):
            continue
        if _has_pullup_on(netlist, data_pin.net):
            continue
        ref = netlist.next_ref("R")
        netlist.add_component(Component(
            ref=ref, type="resistor", fn_id=dht.fn_id, inferred=True,
            pins=[Pin("A", "5V"), Pin("B", data_pin.net)],
            attributes={"value": DHT_PULLUP_VALUE, "role": "pullup"},
        ))
        netlist.add_warning(
            code="dht_data_pullup",
            severity=SEVERITY_WARNING,
            message=f"Pull-up {DHT_PULLUP_VALUE}Ω ajoutee sur DATA du {dht.ref}.",
            refs=[dht.ref, ref],
            params={"dht_ref": dht.ref, "resistor_ref": ref,
                    "value": DHT_PULLUP_VALUE},
        )


# ── Rule 3b: 4.7k pull-up for DS18B20 (DATA pin) ─────────────────────────
# Practically identical to the DHT22 pull-up, just a different value.
def _apply_ds18b20_pullups(netlist: Netlist) -> None:
    sensors = [c for c in list(netlist.components) if c.type == "ds18b20"]
    for s in sensors:
        data_pin = s.pin("DATA")
        if data_pin is None or _is_power_or_ground(data_pin.net):
            continue
        if _has_pullup_on(netlist, data_pin.net):
            continue
        ref = netlist.next_ref("R")
        netlist.add_component(Component(
            ref=ref, type="resistor", fn_id=s.fn_id, inferred=True,
            pins=[Pin("A", "5V"), Pin("B", data_pin.net)],
            attributes={"value": DHT_PULLUP_VALUE, "role": "pullup"},
        ))
        netlist.add_warning(
            code="ds18b20_data_pullup",
            severity=SEVERITY_WARNING,
            message=f"Pull-up {DHT_PULLUP_VALUE}Ω ajoutee sur DATA du {s.ref}.",
            refs=[s.ref, ref],
            params={"sensor_ref": s.ref, "resistor_ref": ref,
                    "value": DHT_PULLUP_VALUE},
        )


# ── Rule 4: series resistor for buzzers ──────────────────────────────────
def _apply_buzzer_series_resistors(netlist: Netlist) -> None:
    buzzers = [c for c in list(netlist.components) if c.type == "buzzer"]
    for buz in buzzers:
        plus_pin = buz.pin("+")
        if plus_pin is None or _is_power_or_ground(plus_pin.net):
            continue
        if _has_series_resistor_on(netlist, plus_pin.net, buz.ref):
            continue
        # Insert an intermediate net between the micro pin and the buzzer's +.
        original_net = plus_pin.net
        bridge_net = _next_internal_net(netlist)
        plus_pin.net = bridge_net

        ref = netlist.next_ref("R")
        netlist.add_component(Component(
            ref=ref, type="resistor", fn_id=buz.fn_id, inferred=True,
            pins=[Pin("A", original_net), Pin("B", bridge_net)],
            attributes={"value": BUZZER_SERIES_VALUE, "role": "series"},
        ))
        netlist.add_warning(
            code="buzzer_series_resistor",
            severity=SEVERITY_WARNING,
            message=f"Resistance serie {BUZZER_SERIES_VALUE}Ω ajoutee pour "
                    f"le buzzer {buz.ref}.",
            refs=[buz.ref, ref],
            params={"buzzer_ref": buz.ref, "resistor_ref": ref,
                    "value": BUZZER_SERIES_VALUE},
        )


# ── Conflict detection (warnings only) ────────────────────────────────────
def detect_conflicts(netlist: Netlist) -> None:
    """Add warnings to the netlist without modifying it."""
    _detect_pin_double_use(netlist)


def _detect_pin_double_use(netlist: Netlist) -> None:
    # For each signal pin (Dn / An), list the non-passive components
    # attached to it. > 1 => potential conflict.
    by_pin: dict[str, list[str]] = {}
    for c in netlist.components:
        if c.type == "resistor":
            continue   # a resistor can share a pin with its companion
        for p in c.pins:
            if _is_signal_net(p.net):
                by_pin.setdefault(p.net, []).append(c.ref)
    for net, refs in by_pin.items():
        # Deux broches NON CABLEES du meme composant partagent le net vide et
        # se denoncaient l'une l'autre : « Pin  utilisee par plusieurs
        # composants : U1, U1. » — nom de broche vide, meme composant deux
        # fois, en severite ERREUR. Un INA219 ou un INA226 le declenchait par
        # ses seuls terminaux de mesure VIN+/VIN-, qui n'ont legitimement pas
        # de net. Un avertissement qui ne dit rien de vrai apprend a ignorer
        # les avertissements (trouve pendant #47, 2026-08-10).
        if len(set(refs)) > 1:
            netlist.add_warning(
                code="pin_double_use",
                severity=SEVERITY_ERROR,
                message=f"Pin {net} utilisee par plusieurs composants : "
                        f"{', '.join(refs)}.",
                refs=list(refs),
                params={"pin": net, "refs_csv": ", ".join(refs)},
            )


# ── Helpers ───────────────────────────────────────────────────────────────
_POWER_NETS = {"5V", "3V3", "GND", "VIN"}


def _is_power_or_ground(net: str) -> bool:
    return net in _POWER_NETS


def _is_signal_net(net: str) -> bool:
    if net in _POWER_NETS:
        return False
    if net.startswith("NET_"):
        return False
    return True


def _has_series_resistor_on(netlist: Netlist, net: str, exclude_ref: str) -> bool:
    """True if a role=series resistor is already connected to `net`.

    We ignore `exclude_ref` (the LED itself doesn't count).
    """
    for c in netlist.components:
        if c.type != "resistor":
            continue
        if c.ref == exclude_ref:
            continue
        if (c.attributes.get("role") or "").lower() != "series":
            continue
        if any(p.net == net for p in c.pins):
            return True
    return False


def _has_pullup_on(netlist: Netlist, net: str) -> bool:
    for c in netlist.components:
        if c.type != "resistor":
            continue
        if (c.attributes.get("role") or "").lower() != "pullup":
            continue
        if any(p.net == net for p in c.pins):
            return True
    return False


def _next_internal_net(netlist: Netlist) -> str:
    """Generate a stable and unique intermediate net name: NET_A, NET_B, ..."""
    used: set[str] = set()
    for c in netlist.components:
        for p in c.pins:
            if p.net.startswith("NET_"):
                used.add(p.net)
    i = 0
    while True:
        # NET_A, NET_B, ..., NET_Z, NET_AA, NET_AB, ...
        name = "NET_" + _to_letters(i)
        if name not in used:
            return name
        i += 1


def _to_letters(n: int) -> str:
    out = ""
    n += 1
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(ord("A") + r) + out
    return out
