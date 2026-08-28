"""Placer: positions board + breadboard(s) + components in vertical orientation.

Strategy (cf. memory `project_wiring_breadboard_strategy.md` and
`project_wiring_layout_plan.md`):
- 1 BB by default, to the right of the board
- 2 BB if rows_needed > 63: 2nd BB to the left of the board
- Board in the center

Component placement algorithm on the breadboard:
- Single-row: all pins on column 'a' (left tie-strip), consecutive
  rows, 1 pin per row
- DIP (Δ=140 = pin-left at col 'd', pin-right at col 'g'): pin-1 at
  top-left (d, row), goes down, crosses at the bottom (g, row+N/2-1), goes back up
  to pin-N (g, row). Wide body (5 steps) for the readability of names
  on our generic assets; the real 0.3" footprint (e/f) will come with
  Fritzing (#4)
- Leaves an empty row between two components for readability
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .breadboard_generator import Breadboard, ROWS_MIN, ROWS_MAX
from .component_catalog import CatalogEntry, lookup
from .svg_board_loader import BoardSVGLoader

# ─── Layout constants ───────────────────────────────────────────────────
GAP_BOARD_BB = 40        # canvas space between the board and each breadboard
GAP_TOP = 80             # top margin (lane corridor TOP)
GAP_BOTTOM = 80          # bottom margin (lane corridor BOTTOM)
GAP_LEFT = 30            # left margin (for lateral bypass of LEFT pins)
GAP_RIGHT = 30           # right margin

MAX_COMPONENTS_PER_BB = 8    # strict limit per breadboard (8 = 6 main + 2 auxiliary passives)
MAX_COMPONENTS_TOTAL = 16    # strict project limit (= 2 BB max x 8)
                              # Series/pullup resistors inferred or
                              # explicitly declared count as
                              # components in v2 — hence the headroom beyond
                              # the 12 "user components".
MAX_SERVOS = 6               # strict limit: max 6 servos per project

# Cols used for default placement
# BB1 (right of Arduino): pins on col 'c' (left tie-strip), wires arrive col 'a'
# BB2 (left of Arduino, mirror): pins on col 'h' (right tie-strip), wires arrive col 'j'
SINGLE_ROW_COL_BB1 = "b"   # base components on right BB (non-mirror)
SINGLE_ROW_COL_BB2 = "i"   # base components on left BB (mirror)
DIP_LEFT_COL_BB1  = "d"   # straddle 5 steps (wide body = readable names; Fritzing = real e/f size)
DIP_RIGHT_COL_BB1 = "g"
DIP_LEFT_COL_BB2  = "g"   # mirror (pin 1..half)
DIP_RIGHT_COL_BB2 = "d"   # mirror (pin half+1..N)

# Alternative cols for I2C components when 3+ I2C on the BB:
# the component is shifted to the other tie-strip to free cols a-e (BB1)
# or cols f-j (BB0) which then serve as the I2C bus.
I2C_ALT_SR_COL_BB1 = "g"   # right BB (non-mirror): I2C on col 'g' (right tie-strip)
I2C_ALT_SR_COL_BB2 = "d"   # left BB (mirror): I2C on col 'd' (left tie-strip)
I2C_PIN_NAMES = ("SDA", "SCL")
I2C_THRESHOLD_FOR_ALT_COL = 3   # 3+ I2C consumers ⇒ switch to the alternative col

# Cols for paired components.
# - SERIES (LED+series R, buzzer+series R): R electrically between Arduino and
#   the main, the main is connected to the RAIL (GND/5V) on the opposite side. The main is
#   placed far from the trench (col 'h' BB1 / 'c' BB0); the Arduino wire arrives
#   directly on the R via col 'a'/'j'.
# - PULLUP (Btn+pullup R, DHT+pullup R): R in parallel between 5V and the
#   main's signal. The main is placed closer to the trench (col 'i' BB1 /
#   'b' BB0) to leave a free col on the rails side where the Arduino wire lands
#   (col 'h'/'c').
# Paired mains: series (LED, buzzer) and pullup (BTN, DHT) on DIFFERENT
# cols so they can coexist on the same BB without visual conflict.
# - series: LED/buzzer col 'd' (BB0 mirror) or 'g' (BB1 non-mirror)
# - pullup: BTN/DHT col 'c' (BB0) or 'h' (BB1)
PAIRED_MAIN_COL_BB1 = "g"           # series (LED, buzzer) BB1 non-mirror
PAIRED_MAIN_COL_BB2 = "d"           # series BB0 mirror
PULLUP_MAIN_COL_BB1 = "h"           # pullup (BTN, DHT) BB1 non-mirror
PULLUP_MAIN_COL_BB2 = "c"           # pullup BB0 mirror

# Horizontal R (common to series + pullup). Spans the central trench (e<->f,
# 84 px = 3 steps): pins on the 2 cols bordering the channel, body above.
# BB1 non-mirror: pin Arduino-side col 'e' (left ts), pin main-side col 'f' (right ts)
# BB0 mirror    : pin main-side col 'e' (left ts),  pin Arduino-side col 'f' (right ts)
PAIRED_R_COL_LEFT_BB1  = "e"
PAIRED_R_COL_RIGHT_BB1 = "f"
PAIRED_R_COL_LEFT_BB2  = "e"
PAIRED_R_COL_RIGHT_BB2 = "f"

# Wire entry col for pullup-paired mains: the col between the main and the
# R (= between main and its R.B-side, on the main's tie-strip).
# BB1 non-mirror: main col 'h', R.B col 'f' → entry 'g'
# BB0 mirror    : main col 'c', R.B col 'e' → entry 'd'
PULLUP_WIRE_ENTRY_BB1 = "g"
PULLUP_WIRE_ENTRY_BB2 = "d"
PAIRED_MAIN_TYPES = {"led", "button", "dht11", "dht22", "buzzer", "ds18b20"}
POWER_NETS = {"5V", "3V3", "GND", "VIN"}

# Component types placed OFF the BB — placed separately after the
# canvas computation, with a direct canvas translate (no pin_to_hole on a BB).
OFF_BB_COMPONENT_TYPES = {"battery_external", "stepper_motor", "dc_motor",
                           "l298n", "uln2003", "l293d_module", "nema17"}
OFF_BB_BREADBOARD_IDX = -1   # marker in PlacedComponent.breadboard_idx

# Motor / driver taxonomy — used to identify the groups
# (driver -> [motors]) that structure the off-BB placement into columns.
MOTOR_TYPES = {"dc_motor", "stepper_motor", "nema17"}
DRIVER_TYPES_OFF_BB = {"l298n", "uln2003", "l293d_module"}
DRIVER_TYPES_ON_BB = {"a4988", "tb6612fng", "drv8833", "l293d"}
DRIVER_TYPES = DRIVER_TYPES_OFF_BB | DRIVER_TYPES_ON_BB
# Motor power pins (battery side) — used to attach a
# battery_external to its target driver(s).
BATTERY_POWER_PINS = {"VS", "VCC", "VM", "VMOT", "VDD"}

# Off-BB layout in 2 anchored rows:
#   - TOP row: batteries (centered on Arduino, or fixed X for rail-aligned)
#   - MID row: motors (above the BBs) + off-BB drivers (above the board)
#     => same Y baseline for motors and drivers.
OFF_BB_PADDING_TOP = 20
OFF_BB_PADDING_BOTTOM = 20
OFF_BB_ROW_GAP = 30        # vertical gap between the TOP row (battery) and MID (motor+driver)
OFF_BB_INTRA_COL_GAP = 16  # horizontal gap between adjacent items (motors / drivers / batteries)
# Vertical gap between 2 motors stacked above the same BB. Vertical
# stacking (vs side-by-side) prevents the OUT-net wires from crossing
# in the v3 routing (cf TODO 1 CLAUDE.md).
MOTOR_STACK_VERTICAL_GAP = 20
# Extra vertical margin between the bottom of the off-BB zone and the top
# of the BB. With an off-BB driver (large), the motors are already far from the
# BB thanks to the driver's height. With an on-BB DIP driver, mid_h = motor_h
# alone so the motors are flush with the BB — this margin guarantees a
# minimum visual space.
BB_TO_OFF_BB_MARGIN = 30

# Known dimensions (w, h) of off-BB components. Read from the viewBox
# of each SVG asset. Used to compute the grid (column widths,
# row heights) BEFORE actual placement. Fallback (110, 54) for an
# unknown type (average size, avoids a crash).
_OFF_BB_DIMS: dict[str, tuple[float, float]] = {
    "battery_external": (110, 54),
    # stepper_motor: SVG rotated 90° CCW (body on the left, connector on the
    # right, pins on the right edge). Dimensions swapped vs portrait.
    "stepper_motor":    (144, 127),
    # dc_motor: SVG rotated 90° CCW (side view) -> bbox 92x60 instead
    # of 60x92. Rotor on the left, M+/M- terminals on the right. Allows
    # vertical stacking of the motor with the battery (= same off-BB
    # column, the motor's horizontal orientation frees up space).
    "dc_motor":         (92, 60),
    "l298n":            (240, 170),
    "uln2003":          (240, 200),
    "l293d_module":     (240, 170),
    # NEMA17: original SVG 153x241 but render_scale=0.6 (cf catalog) →
    # effective dimensions 92x145.
    "nema17":           (92, 145),
}
_OFF_BB_DEFAULT_DIM: tuple[float, float] = (110, 54)

# Routing lane corridor TOP: default base (= legacy behavior
# when there is no off-BB). In the presence of off-BB, the base is
# pushed down so that the off-BB → BB wires do not cross
# the bodies of the off-BB components.
LANE_Y_BASE_TOP_DEFAULT = 70.0
LANE_Y_TOP_BASE_OFFSET = 10.0   # gap between gap_top_eff and lane_y_top_base

WIRE_ENTRY_COL_LEFT = "a"
WIRE_ENTRY_COL_RIGHT = "j"

ROW_GAP = 2              # minimal gap between 2 components (used as lower bound
                          # when the BB is tight and there is no space to distribute).
                          # 2 = 1 free hole row between components (more
                          # airy visual; otherwise adjacent terminals touch).


# ─── Models ─────────────────────────────────────────────────────────────
@dataclass
class PlacedComponent:
    """A component placed on a breadboard."""
    component_ref: str                          # ref in the netlist (e.g. 'D1')
    component_type: str                         # type ('led', 'dht22', ...)
    catalog_entry: CatalogEntry                 # SVG asset + metadata
    breadboard_idx: int                         # 0 or 1
    pin_to_hole: dict[int, tuple[str, int]]     # {pin_idx: (col_id, row)}
    mirrored: bool = False                      # True if BB2 (horizontal mirror component)
    translate: tuple[float, float] = (0.0, 0.0)
    # True for paired Rs whose other pin is on an internal NET (LED series
    # R, buzzer series R): the wire color on the Arduino side must propagate via the
    # R to the main's pins (e.g. LED.A in column d). False for pullup Rs
    # (Btn/DHT) because the 2 sides of the R are on electrically
    # distinct nets (5V vs signal) with their own wires.
    propagate_color_through: bool = False
    # True for paired mains with a pullup R (BTN, DHT): allows the
    # routing to choose the specific wire entry col (between the main and the
    # R) instead of the standard entry col.
    paired_with_pullup: bool = False
    # Component attributes transferred from the netlist (e.g. {"value": "220",
    # "role": "series"} for a resistor). Used by the loader to
    # adjust the rendering (e.g. coloring the bands according to the value).
    attributes: dict = field(default_factory=dict)


@dataclass
class PlacedScene:
    """Complete scene: board + 1 or 2 breadboards + placed components."""
    board_loader: BoardSVGLoader
    board_translate: tuple[float, float]

    breadboards: list[Breadboard]                       # 1 or 2
    breadboard_translates: list[tuple[float, float]]    # same length

    placed_components: list[PlacedComponent] = field(default_factory=list)
    canvas_size: tuple[float, float] = (0.0, 0.0)
    # y of the lowest TOP lane (corridor above the BBs). Dynamic:
    # pushed
    # down when off-BB components occupy the upper zone,
    # to prevent the off-BB → BB wires from crossing the bodies. By default
    # = LANE_Y_BASE_TOP_DEFAULT (legacy 70).
    lane_y_top_base: float = LANE_Y_BASE_TOP_DEFAULT
    # Original netlist kept for contextual renders (battery voltage
    # range, etc.). List of dicts [{"ref":..., "type":..., "pins":[...]}].
    netlist_components: list[dict] = field(default_factory=list)


# ─── Row estimation ──────────────────────────────────────────────
def _rows_for_component(entry: CatalogEntry) -> int:
    """Number of rows occupied by a component."""
    if entry.is_dip:
        # DIP: N/2 rows (pin-1 at top, pin-N/2 at bottom, mirror on the right)
        return max(2, entry.pin_count // 2)
    else:
        # Single-row: 1 row per pin
        return max(2, entry.pin_count)


def _total_rows_needed(components: list[CatalogEntry]) -> int:
    """Minimal rows required: margins + components + ROW_GAP between each.

    Any extra space (case of a BB widened to align
    with the other) is distributed uniformly between all the components at
    placement time (cf `_largest_uniform_rows`).
    """
    if not components:
        return ROWS_MIN
    n = len(components)
    rows = sum(_rows_for_component(c) for c in components) + (n - 1) * ROW_GAP + 2
    return max(ROWS_MIN, rows)


# ─── Pair detection (main, R) ────────────────────────────────────
def _identify_pairs(typed_entries: list,
                    pins_by_ref: dict[str, list]
                    ) -> tuple[dict[str, str], dict[str, str], dict[str, int]]:
    """Detect the (main, R) pairs in the netlist.

    For each 'main' component (LED, button, dht11/22, buzzer) that shares
    a non-power net with a resistor, the pair is recorded. The R is
    then considered auxiliary to this main (horizontal placement
    co-located with the main at render time).

    Returns:
      main_to_r       : ref_main → ref_r
      r_to_main       : ref_r → ref_main
      main_pin_with_r : ref_main → 1-based index of the main's pin shared with R
                        (used to align the R on the correct row)
    """
    main_to_r: dict[str, str] = {}
    r_to_main: dict[str, str] = {}
    main_pin_with_r: dict[str, int] = {}

    resistor_refs = [(ref, type_id, e) for (ref, type_id, e) in typed_entries
                     if type_id == "resistor"]

    for ref, type_id, _entry in typed_entries:
        if type_id not in PAIRED_MAIN_TYPES:
            continue
        main_pins = pins_by_ref.get(ref, [])
        for r_ref, _r_type, _r_entry in resistor_refs:
            if r_ref in r_to_main:
                continue   # this R is already paired
            r_pins = pins_by_ref.get(r_ref, [])
            r_nets = {p["net"] for p in r_pins}
            for i, p in enumerate(main_pins, start=1):
                if p["net"] in POWER_NETS:
                    continue
                if p["net"] in r_nets:
                    main_to_r[ref] = r_ref
                    r_to_main[r_ref] = ref
                    main_pin_with_r[ref] = i
                    break
            if ref in main_to_r:
                break
    return main_to_r, r_to_main, main_pin_with_r


# ─── Motor ↔ driver ↔ battery group detection ─────────────────
def _identify_motor_groups(
    netlist_components: list[dict],
) -> tuple[list[tuple[str, list[str]]],
           dict[str, str],
           dict[str, list[str]]]:
    """Detect the (driver_ref, [motor_refs]) groups and the drivers
    powered by each external battery.

    A motor is attached to the driver of which at least one pin shares a net
    with one of the motor's pins (typically OUT*, 1A/1B/2A/2B, etc.).
    A battery is attached to the drivers of which a motor power pin
    (VS/VCC/VM/VMOT/VDD) is on the same net as the battery's `+`.

    Returns:
        ordered_groups : list [(driver_ref, [motor_refs])] in the order
            of appearance of the drivers in the netlist (stable).
        motor_to_driver: {motor_ref: driver_ref}
        battery_targets: {battery_ref: [driver_ref, ...]}
    """
    motors = [c for c in netlist_components
              if c.get("type") in MOTOR_TYPES]
    drivers = [c for c in netlist_components
               if c.get("type") in DRIVER_TYPES]
    batteries = [c for c in netlist_components
                 if c.get("type") == "battery_external"]

    motor_to_driver: dict[str, str] = {}
    groups_by_driver: dict[str, list[str]] = {}
    for m in motors:
        m_nets = {p.get("net") for p in m.get("pins", [])}
        for d in drivers:
            d_nets = {p.get("net") for p in d.get("pins", [])}
            if m_nets & d_nets:
                motor_to_driver[m["ref"]] = d["ref"]
                groups_by_driver.setdefault(d["ref"], []).append(m["ref"])
                break

    # Stable order: order of the drivers in the netlist
    ordered_groups: list[tuple[str, list[str]]] = []
    for d in drivers:
        if d["ref"] in groups_by_driver:
            ordered_groups.append((d["ref"], groups_by_driver[d["ref"]]))

    # Battery -> powered drivers
    battery_targets: dict[str, list[str]] = {}
    for bat in batteries:
        plus_net = None
        for p in bat.get("pins", []):
            if p.get("name") == "+":
                plus_net = p.get("net")
                break
        targets: list[str] = []
        if plus_net:
            for d in drivers:
                for p in d.get("pins", []):
                    if (p.get("name") in BATTERY_POWER_PINS
                            and p.get("net") == plus_net):
                        targets.append(d["ref"])
                        break
        battery_targets[bat["ref"]] = targets

    return ordered_groups, motor_to_driver, battery_targets


def _allocate_by_battery_groups(
    typed_entries: list,
    netlist_components: list[dict],
    r_to_main: dict[str, str],
    main_to_r: dict[str, str],
) -> list[list]:
    """2-BB mode triggered by voltage split: assigns each on-BB
    component to the BB of its power battery.

    Convention (servo + motor case):
      - servo + its battery → BB[1] (right, non-mirror)
      - motor driver + its battery → BB[0] (left, mirror)
    The side is chosen based on the nature of the load, not the netlist order.

    Fallback (2 batteries of the same type): 1st battery -> right, 2nd -> left.

    Components without battery power: fill BB[1] first, BB[0]
    otherwise. Paired Rs follow their main.

    Returns [bb_left_entries, bb_right_entries].
    """
    batteries = [c for c in netlist_components
                 if c.get("type") == "battery_external"]
    bat_plus_nets: list[str] = []
    for b in batteries:
        for p in b.get("pins", []):
            if p.get("name") == "+":
                bat_plus_nets.append(p.get("net", ""))
                break
    netlist_by_ref = {c["ref"]: c for c in netlist_components}

    # Categorize each battery+ net according to the nature of its load:
    # - "servo": powers at least one servo directly (VCC on this net)
    # - "motor": powers at least one motor driver (VS/VM/... on this net)
    # - "other": any other case (rare; fallback netlist order)
    net_kind: dict[str, str] = {}
    for c in netlist_components:
        ctype = c.get("type", "")
        if ctype == "servo":
            for p in c.get("pins", []):
                if p.get("name") == "VCC" and p.get("net") in bat_plus_nets:
                    net_kind.setdefault(p["net"], "servo")
        elif ctype in DRIVER_TYPES:
            for p in c.get("pins", []):
                if (p.get("name") in BATTERY_POWER_PINS
                        and p.get("net") in bat_plus_nets):
                    # "motor" takes precedence over "servo" if same net (rare)
                    net_kind[p["net"]] = "motor"

    # Map net+ → target BB (0 = left, 1 = right).
    net_to_bb: dict[str, int] = {}
    for i, net in enumerate(bat_plus_nets):
        kind = net_kind.get(net, "other")
        if kind == "servo":
            net_to_bb[net] = 1   # right
        elif kind == "motor":
            net_to_bb[net] = 0   # left
        else:
            # Fallback netlist order: 1st on the right, 2nd on the left
            net_to_bb[net] = 1 if i == 0 else 0

    def _component_target_bb(ref: str) -> int | None:
        """Target BB (0/1) according to the battery that powers this component."""
        c = netlist_by_ref.get(ref)
        if c is None:
            return None
        for p in c.get("pins", []):
            if p.get("name") in BATTERY_POWER_PINS:
                net = p.get("net", "")
                if net in net_to_bb:
                    return net_to_bb[net]
        return None

    bb_left: list = []    # BB[0]
    bb_right: list = []   # BB[1]
    free: list = []

    for entry in typed_entries:
        ref = entry[0]
        if ref in r_to_main:
            continue
        bb_idx = _component_target_bb(ref)
        if bb_idx == 0:
            bb_left.append(entry)
        elif bb_idx == 1:
            bb_right.append(entry)
        else:
            free.append(entry)

    def _slots(entries: list) -> int:
        return sum(1 for (r, _, _) in entries if r not in r_to_main)

    # Free components: BB[1] (right) first, BB[0] (left) next.
    for entry in free:
        if _slots(bb_right) < MAX_COMPONENTS_PER_BB:
            bb_right.append(entry)
        elif _slots(bb_left) < MAX_COMPONENTS_PER_BB:
            bb_left.append(entry)
        else:
            raise RuntimeError(
                f"Allocation 2-BB battery split : trop de composants libres "
                f"({entry[0]} ne tient sur aucune BB)"
            )

    # Re-place the paired Rs to follow their main.
    right_refs = {r for (r, _, _) in bb_right}
    left_refs = {r for (r, _, _) in bb_left}
    for entry in typed_entries:
        ref = entry[0]
        if ref not in r_to_main:
            continue
        main_ref = r_to_main[ref]
        if main_ref in right_refs:
            bb_right.append(entry)
        elif main_ref in left_refs:
            bb_left.append(entry)

    return [bb_left, bb_right]


def compute_battery_voltage_range(
    netlist_components: list[dict],
    battery_ref: str,
) -> tuple[float, float] | None:
    """Compute the voltage range (Vmin, Vmax) that a battery must supply
    according to the components it powers.

    Looks for all the components (drivers via motor_to_driver + servos
    directly) connected to the battery's `+` net, and intersects the
    ranges (motor_type, driver_type) from `BATTERY_VOLTAGE_RANGES`.

    Returns None if:
      - no powered component found
      - no entry in the table (undocumented component)
      - empty intersection (incompatibility, should not happen in practice)
    """
    from .component_catalog import voltage_range_for_load

    battery = next((c for c in netlist_components
                     if c.get("ref") == battery_ref), None)
    if battery is None:
        return None
    plus_net = None
    for p in battery.get("pins", []):
        if p.get("name") == "+":
            plus_net = p.get("net")
            break
    if not plus_net:
        return None

    # 1. Drivers powered by this battery (= of which a VS/VM/VCC pin is
    #    on plus_net). For each driver, get the motors attached
    #    via the shared nets (motor_to_driver).
    _groups, motor_to_driver, _bat_targets = _identify_motor_groups(
        netlist_components)
    driver_to_motors: dict[str, list[str]] = {}
    for motor_ref, drv_ref in motor_to_driver.items():
        driver_to_motors.setdefault(drv_ref, []).append(motor_ref)

    netlist_by_ref = {c["ref"]: c for c in netlist_components}

    loads: list[tuple[str, str | None]] = []   # [(motor_type, driver_type|None)]
    for drv_ref, motor_refs in driver_to_motors.items():
        drv = netlist_by_ref.get(drv_ref)
        if drv is None:
            continue
        # Check that the driver is indeed powered by this battery
        powered = any(
            p.get("name") in BATTERY_POWER_PINS and p.get("net") == plus_net
            for p in drv.get("pins", [])
        )
        if not powered:
            continue
        drv_type = drv.get("type", "")
        for m_ref in motor_refs:
            m = netlist_by_ref.get(m_ref)
            if m is None:
                continue
            loads.append((m.get("type", ""), drv_type))

    # 2. Servos powered directly (= VCC on plus_net, no driver)
    for c in netlist_components:
        if c.get("type") != "servo":
            continue
        for p in c.get("pins", []):
            if p.get("name") == "VCC" and p.get("net") == plus_net:
                loads.append(("servo", None))
                break

    if not loads:
        return None

    # 3. Intersection of the ranges
    vmin, vmax = float("-inf"), float("inf")
    found = False
    for motor_type, drv_type in loads:
        rng = voltage_range_for_load(motor_type, drv_type)
        if rng is None:
            continue
        vmin = max(vmin, rng[0])
        vmax = min(vmax, rng[1])
        found = True
    if not found or vmin > vmax:
        return None
    return (vmin, vmax)


def _off_bb_dim(type_id: str) -> tuple[float, float]:
    return _OFF_BB_DIMS.get(type_id, _OFF_BB_DEFAULT_DIM)


def _resolve_battery_rail_targets(
    netlist_components: list[dict],
    placed_components: list[PlacedComponent],
    breadboards: list[Breadboard],
    bb_translates_x: list[float],
    board_x: float,
) -> dict[str, tuple[int, str, float]]:
    """Determine for each battery_external its target V+ rail (host BB +
    side + rail canvas x). Reproduces the router's logic:
      - V+ extra: "outer" rail (= side opposite the Arduino)
      - host BB: 1st BB having an on-BB consumer of bat+; otherwise
        fallback on the on-BB consumers of GND; otherwise no rail.

    Returns {battery_ref: (target_bb_idx, bat_side, rail_canvas_x)}.
    A battery omitted from the dict keeps its standard grid placement.
    """
    placed_by_ref = {pc.component_ref: pc for pc in placed_components}

    consumers_by_net: dict[str, list[tuple[PlacedComponent, int]]] = {}
    for c in netlist_components:
        pc = placed_by_ref.get(c.get("ref", ""))
        if pc is None:
            continue
        for i, p in enumerate(c.get("pins", []), start=1):
            net = p.get("net")
            if net:
                consumers_by_net.setdefault(net, []).append((pc, i))

    rail_targets: dict[str, tuple[int, str, float]] = {}
    for c in netlist_components:
        if c.get("type") != "battery_external":
            continue
        bat_plus_net = None
        for p in c.get("pins", []):
            if p.get("name") == "+":
                bat_plus_net = p.get("net")
                break
        if not bat_plus_net:
            continue
        # First look for the on-BB consumers of the bat+ net
        bbs_used = sorted({
            pc.breadboard_idx for pc, _ in consumers_by_net.get(bat_plus_net, [])
            if pc.breadboard_idx >= 0
        })
        if not bbs_used:
            # Fallback: on-BB consumers of GND (typical case of an off-BB
            # driver powered by a battery but with GND shared with a DIP).
            bbs_used = sorted({
                pc.breadboard_idx for pc, _ in consumers_by_net.get("GND", [])
                if pc.breadboard_idx >= 0
            })
        # If no on-BB consumer: rail-align on
        # BB[0] anyway. The battery is always placed on the power strip, even
        # when the driver is off-BB (BAT_5V then transits via the
        # rail then to the off-BB driver via a horizontal wire).
        target_bb = bbs_used[0] if bbs_used else 0
        bb_translate_x = bb_translates_x[target_bb]
        arduino_side = "left" if bb_translate_x > board_x else "right"
        bat_side = "right" if arduino_side == "left" else "left"
        # Center the battery on the segment between V+_<bat_side> row 1 and
        # GND_<bat_side> row 1 (= the first 2 power holes bat-side).
        vplus_local_x, _ = breadboards[target_bb].hole_position(
            f"V+_{bat_side}", 1)
        gnd_local_x, _ = breadboards[target_bb].hole_position(
            f"GND_{bat_side}", 1)
        rail_canvas_x = bb_translate_x + (vplus_local_x + gnd_local_x) / 2.0
        rail_targets[c["ref"]] = (target_bb, bat_side, rail_canvas_x)
    return rail_targets


# local cx of the '+' pin in battery.svg (cf. assets/wiring/components/external/battery.svg)
BATTERY_PLUS_LOCAL_CX = 22.0


def _compute_off_bb_grid(
    off_bb_entries: list[tuple[str, str, CatalogEntry, dict]],
    netlist_components: list[dict],
    rail_aligned_batteries: set[str] | None = None,
    nb_breadboards: int = 1,
) -> tuple[dict, float, float, float]:
    """Build the off-BB layout in 2 anchored rows.

    Layout:
      - TOP row: batteries (rail-aligned + non-rail).
      - MID row: motors (above the BBs, distributed) + off-BB drivers
                  (above the Arduino, centered).
        => motors and drivers have the same Y baseline.

    The netlist's driver↔motors groups no longer structure the placement:
    motors and drivers are positioned independently by anchoring
    (BB centers for the motors, board center for the drivers).

    Returns:
        layout : dict with keys
            'motors'             : list[ref]  (all motors, netlist order)
            'drivers_off_bb'     : list[ref]  (off-BB drivers, netlist order)
            'non_rail_batteries' : list[ref]  (non rail-aligned batteries)
            'orphans'            : list[ref]  (off-BB non-motor/driver/battery)
        top_h  : height of the TOP row (= bat_h if batteries present, otherwise 0)
        mid_h  : height of the MID row (= max(motor_h, driver_h))
        zone_h : total height (padding + top_h + row_gap + mid_h + padding)
    """
    rail_aligned = rail_aligned_batteries or set()

    if not off_bb_entries:
        return {}, 0.0, 0.0, 0.0

    type_by_ref: dict[str, str] = {ref: t for (ref, t, _, _) in off_bb_entries}

    # Classification — netlist order preserved.
    motors: list[str] = []
    drivers_off_bb: list[str] = []
    batteries_all: list[str] = []
    orphans: list[str] = []
    for (ref, t, _, _) in off_bb_entries:
        if t in MOTOR_TYPES:
            motors.append(ref)
        elif t in DRIVER_TYPES_OFF_BB:
            drivers_off_bb.append(ref)
        elif t == "battery_external":
            batteries_all.append(ref)
        else:
            orphans.append(ref)

    non_rail_batteries = [b for b in batteries_all if b not in rail_aligned]

    # dc_motor stacking (DISABLED): reserved for future reactivation.
    stacked_dc_motors: list[str] = []
    stack_inner_gap = 10.0

    # Row heights — no more separate TOP row for the batteries.
    # The (rail-aligned) battery is positioned vertically WITHIN the
    # MID row, centered on the motor (which is itself vertically centered
    # on the off-BB driver if present). zone_h therefore reserves only a
    # single "row" that must accommodate motors, drivers and batteries.
    bat_h = _off_bb_dim("battery_external")[1]
    has_battery = bool(batteries_all)
    top_h = 0.0

    mid_h = 0.0
    for ref in motors:
        mid_h = max(mid_h, _off_bb_dim(type_by_ref[ref])[1])
    for ref in drivers_off_bb:
        mid_h = max(mid_h, _off_bb_dim(type_by_ref[ref])[1])
    for ref in orphans:
        mid_h = max(mid_h, _off_bb_dim(type_by_ref[ref])[1])
    if has_battery:
        mid_h = max(mid_h, bat_h)

    # When 2+ motors WITHOUT `_paired_driver` are present, they are stacked
    # vertically above the BB (cf TODO 1 CLAUDE.md). We extend
    # mid_h to reserve the necessary height. Motors WITH
    # `_paired_driver` (NEMA17, stepper) are placed side-by-side
    # horizontally, so mid_h stays just = max(motor_h) without a stack.
    attrs_by_ref_local: dict[str, dict] = {
        ref: a for (ref, _, _, a) in off_bb_entries}
    stackable_motors = [m for m in motors
                         if not attrs_by_ref_local.get(m, {}).get("_paired_driver")]
    if len(stackable_motors) >= 2:
        # Upper bound: motors stacked per BB (round-robin over the BBs).
        import math
        stack_count = max(1, math.ceil(len(stackable_motors)
                                        / max(1, nb_breadboards)))
        if stack_count >= 2:
            max_motor_h = max(_off_bb_dim(type_by_ref[m])[1]
                                for m in stackable_motors)
            stack_h = (stack_count * max_motor_h
                        + (stack_count - 1) * MOTOR_STACK_VERTICAL_GAP)
            mid_h = max(mid_h, stack_h)

    row_gap_eff = 0.0  # only one row now, no more gap between rows
    zone_h = (OFF_BB_PADDING_TOP + top_h + row_gap_eff + mid_h
              + OFF_BB_PADDING_BOTTOM)

    layout = {
        "motors": motors,
        "drivers_off_bb": drivers_off_bb,
        "non_rail_batteries": non_rail_batteries,
        "orphans": orphans,
        "stacked_dc_motors": stacked_dc_motors,
        "stack_inner_gap": stack_inner_gap,
    }
    return layout, top_h, mid_h, zone_h


def _grow_canvas_for_off_bb(canvas_w: float,
                              placed_components: list[PlacedComponent]
                              ) -> float:
    """Extend canvas_w to encompass any off-BB component whose right
    edge would overflow. Keep the same GAP_RIGHT as the minimal margin
    after the right edge of the rightmost component. Returns the new
    canvas_w (>= old)."""
    max_right = canvas_w
    for pc in placed_components:
        if pc.breadboard_idx != OFF_BB_BREADBOARD_IDX:
            continue
        w, _h = _off_bb_dim(pc.component_type)
        right_edge = pc.translate[0] + w + GAP_RIGHT
        if right_edge > max_right:
            max_right = right_edge
    return max_right


def _place_off_bb_from_grid(
    layout: dict,
    off_bb_entries: list[tuple[str, str, CatalogEntry, dict]],
    board_x: float,
    board_w: float,
    bb_translates_x: list[float],
    bb_widths: list[float],
    top_h: float,
    mid_h: float,
) -> list[PlacedComponent]:
    """Place the off-BB components according to the anchored 2-row layout.

    y conventions:
      - top_y = OFF_BB_PADDING_TOP                   (batteries row)
      - mid_y = top_y + top_h + OFF_BB_ROW_GAP       (motors + off-BB drivers row)
        => same Y baseline for motors and drivers.

    x conventions (anchoring):
      - Motors: distributed between the BBs (1 per BB if possible), centered
                 horizontally on the center of their BB. For a group
                 of motors on the same BB, they are side-by-side and centered.
      - Off-BB drivers: side-by-side, centered on the Arduino's center.
      - Non rail-aligned batteries: side-by-side, centered on the Arduino.
      - Orphans (off-BB non-motor/driver/battery): treated like
        drivers (above the board, MID row).
    """
    by_ref: dict[str, tuple[str, str, CatalogEntry, dict]] = {
        ref: (ref, t, e, attrs) for (ref, t, e, attrs) in off_bb_entries
    }
    type_by_ref: dict[str, str] = {ref: t for (ref, t, _, _) in off_bb_entries}

    placed: list[PlacedComponent] = []
    if not layout or not off_bb_entries:
        return placed

    top_y = OFF_BB_PADDING_TOP
    row_gap_eff = OFF_BB_ROW_GAP if (top_h > 0 and mid_h > 0) else 0.0
    mid_y = top_y + top_h + row_gap_eff

    def _emit(ref: str, x: float, y: float) -> None:
        entry_tuple = by_ref.get(ref)
        if entry_tuple is None:
            return
        ref_, type_id, cat_entry, attrs = entry_tuple
        placed.append(PlacedComponent(
            component_ref=ref_,
            component_type=type_id,
            catalog_entry=cat_entry,
            breadboard_idx=OFF_BB_BREADBOARD_IDX,
            pin_to_hole={},
            mirrored=False,
            translate=(x, y),
            attributes=dict(attrs),
        ))

    def _place_centered_row(refs: list[str], center_x: float, y: float) -> None:
        """Place a sequence of components side-by-side, centered on center_x, baseline y."""
        if not refs:
            return
        widths = [_off_bb_dim(type_by_ref[r])[0] for r in refs]
        total_w = sum(widths) + OFF_BB_INTRA_COL_GAP * (len(refs) - 1)
        cur_x = center_x - total_w / 2.0
        for ref, w in zip(refs, widths):
            _emit(ref, cur_x, y)
            cur_x += w + OFF_BB_INTRA_COL_GAP

    # ─── 1. Off-BB drivers + orphans: centered on the Arduino, baseline mid_y ─
    drivers_and_orphans = (list(layout.get("drivers_off_bb", []))
                           + list(layout.get("orphans", [])))
    if drivers_and_orphans:
        board_cx = board_x + board_w / 2.0
        _place_centered_row(drivers_and_orphans, board_cx, mid_y)

    # ─── 2. Motors: vertically centered on the off-BB driver (if it exists), ─
    # otherwise baseline mid_y as before. Horizontal center: distributed between
    # the BBs (1 per BB if possible).
    drivers_off_bb_list = list(layout.get("drivers_off_bb", []))
    if drivers_off_bb_list:
        # We use the FIRST off-BB driver as the vertical reference
        # (standard case: 1 driver + 1 motor per group). driver_h = max h
        # among the off-BB drivers to stay robust if there are several.
        driver_h_ref = max(_off_bb_dim(type_by_ref[r])[1]
                            for r in drivers_off_bb_list)
    else:
        driver_h_ref = 0.0

    motors = list(layout.get("motors", []))
    nb_bbs = len(bb_translates_x)
    attrs_by_ref: dict[str, dict] = {ref: a for (ref, _, _, a) in off_bb_entries}

    if motors and nb_bbs > 0:
        # "1 per BB if possible": round-robin alternation over the BBs.
        motors_per_bb: list[list[str]] = [[] for _ in range(nb_bbs)]
        for i, m_ref in enumerate(motors):
            motors_per_bb[i % nb_bbs].append(m_ref)
        for bb_idx, motor_refs in enumerate(motors_per_bb):
            if not motor_refs:
                continue
            bb_cx = bb_translates_x[bb_idx] + bb_widths[bb_idx] / 2.0
            # Decide: vertical stacking (DC dual H-bridge, 1 driver shared
            # for 2 motors, motors do NOT have `_paired_driver`) or
            # horizontal side-by-side (each motor has its own driver,
            # `_paired_driver` set on the motor: NEMA17, 28BYJ-48, etc.).
            #   - Stacked: motors centered on bb_cx (common X), Y differs.
            #     Good for DC because the shared driver is between the 2 motors.
            #   - Side-by-side: motors spread out horizontally around
            #     bb_cx. Necessary when the drivers are different (on
            #     the BB or off-BB) because each motor must reach its own.
            any_paired_driver = any(
                attrs_by_ref.get(r, {}).get("_paired_driver")
                for r in motor_refs)
            if len(motor_refs) == 1 or any_paired_driver:
                # Side-by-side (or single motor): horizontal placement.
                widths = [_off_bb_dim(type_by_ref[r])[0] for r in motor_refs]
                total_w = (sum(widths)
                            + OFF_BB_INTRA_COL_GAP * (len(motor_refs) - 1))
                cur_x = bb_cx - total_w / 2.0
                for m_ref, m_w in zip(motor_refs, widths):
                    motor_h = _off_bb_dim(type_by_ref[m_ref])[1]
                    if driver_h_ref > 0:
                        m_y = mid_y + (driver_h_ref - motor_h) / 2.0
                    else:
                        m_y = mid_y
                    _emit(m_ref, cur_x, m_y)
                    cur_x += m_w + OFF_BB_INTRA_COL_GAP
            else:
                # VERTICAL stacking: M_0 (1st ref) at the BOTTOM (close to the
                # shared driver), the following ones above. X = common BB center.
                # Avoids the v3 routing bug when 2 above-BB motors side-by-side
                # must reach distant holes on the same BB
                # (cf TODO 1 CLAUDE.md).
                heights = [_off_bb_dim(type_by_ref[r])[1] for r in motor_refs]
                total_h = (sum(heights)
                            + (len(motor_refs) - 1) * MOTOR_STACK_VERTICAL_GAP)
                # bottom of the MID zone = mid_y + total_h. M_0 is flush with this bottom.
                y_bottom = mid_y + total_h
                for m_ref, m_h in zip(motor_refs, heights):
                    motor_w = _off_bb_dim(type_by_ref[m_ref])[0]
                    m_y = y_bottom - m_h
                    _emit(m_ref, bb_cx - motor_w / 2.0, m_y)
                    y_bottom = m_y - MOTOR_STACK_VERTICAL_GAP

    # ─── 3. Non rail-aligned batteries: centered on the Arduino, baseline mid_y ─
    batteries = list(layout.get("non_rail_batteries", []))
    if batteries:
        board_cx = board_x + board_w / 2.0
        _place_centered_row(batteries, board_cx, mid_y)

    return placed


# ─── Placement ───────────────────────────────────────────────────────────
def place_components_on_breadboard(
    bb: Breadboard,
    bb_idx: int,
    entries: list[tuple[str, str, CatalogEntry]],
    mirrored: bool = False,
    main_to_r: dict[str, str] | None = None,
    r_to_main: dict[str, str] | None = None,
    main_pin_with_r: dict[str, int] | None = None,
    pins_by_ref: dict[str, list] | None = None,
    attrs_by_ref: dict[str, dict] | None = None,
) -> list[PlacedComponent]:
    """Place the components in a uniform distribution over the full height of the BB.

    Placement strategies (in priority order per component):
      1. **Paired main** (LED/button/dht/buzzer with a paired R) →
         placed on col 'h' (BB1) or 'c' (BB0). Its paired R is placed
         horizontally between cols 'd' and 'g' at the row of the main's "with R"
         pin, without consuming an extra row.
      2. **I2C with ≥ 3 consumers on the BB** → placed on col 'g'
         (BB1) or 'd' (BB0) to free the other tie-strip as the I2C bus.
      3. **Standard** → col 'c' (BB1) or 'h' (BB0).

    The free space (bb.rows - sum of the rows) is distributed uniformly
    between the n+1 spaces; the remainder goes to the margins (top ≤ bottom).

    `mirrored=True` for the left BB: components flipped via scale(-1,1).
    """
    if not entries:
        return []

    main_to_r = main_to_r or {}
    r_to_main = r_to_main or {}
    main_pin_with_r = main_pin_with_r or {}
    pins_by_ref = pins_by_ref or {}
    attrs_by_ref = attrs_by_ref or {}

    if mirrored:
        sr_col = SINGLE_ROW_COL_BB2
        dip_left_col = DIP_LEFT_COL_BB2
        dip_right_col = DIP_RIGHT_COL_BB2
        i2c_alt_col = I2C_ALT_SR_COL_BB2
        paired_main_col_series = PAIRED_MAIN_COL_BB2
        paired_main_col_pullup = PULLUP_MAIN_COL_BB2
        # Horizontal R (mirror): pin 1 (Arduino/rail) col 'h', pin 2 (main) col 'e'
        paired_r_pin1_col = PAIRED_R_COL_RIGHT_BB2
        paired_r_pin2_col = PAIRED_R_COL_LEFT_BB2
    else:
        sr_col = SINGLE_ROW_COL_BB1
        dip_left_col = DIP_LEFT_COL_BB1
        dip_right_col = DIP_RIGHT_COL_BB1
        i2c_alt_col = I2C_ALT_SR_COL_BB1
        paired_main_col_series = PAIRED_MAIN_COL_BB1
        paired_main_col_pullup = PULLUP_MAIN_COL_BB1
        # Horizontal R (non-mirror): pin 1 col 'e' (Arduino), pin 2 col 'f' (main)
        paired_r_pin1_col = PAIRED_R_COL_LEFT_BB1
        paired_r_pin2_col = PAIRED_R_COL_RIGHT_BB1

    def _r_propagates(r_ref: str) -> bool:
        """True iff the paired R has an internal NET_* net on the other side
        (= series R). False for pullup Rs (Btn/DHT) with 2 distinct nets."""
        return any(
            p.get("net", "").startswith("NET_")
            for p in pins_by_ref.get(r_ref, [])
        )

    def _is_i2c(entry: CatalogEntry) -> bool:
        return any(p in I2C_PIN_NAMES for p in entry.pin_labels.values())

    # Filter out the paired Rs: they will be placed co-located with their
    # main, without consuming their own row in the distribution.
    main_entries = [(r, t, e) for (r, t, e) in entries if r not in r_to_main]

    n_i2c = sum(1 for r, _, e in main_entries
                if _is_i2c(e) and r not in main_to_r)
    use_i2c_alt_col = n_i2c >= I2C_THRESHOLD_FOR_ALT_COL

    def _col_for_main(ref: str, entry: CatalogEntry) -> str:
        """Choose the main's col: offset (paired) > i2c-alt > standard.
        For pairs: col 'h'/'c' if series R (propagation), col 'i'/'b'
        if pullup R (the Arduino wire arrives next to the main, not via the R)."""
        if ref in main_to_r:
            r_ref = main_to_r[ref]
            return (paired_main_col_series if _r_propagates(r_ref)
                    else paired_main_col_pullup)
        if use_i2c_alt_col and _is_i2c(entry):
            return i2c_alt_col
        return sr_col

    def _build_pin_to_hole_main(ref: str, entry: CatalogEntry, start_row: int
                                ) -> dict[int, tuple[str, int]]:
        pin_to_hole: dict[int, tuple[str, int]] = {}
        if entry.is_dip:
            half = entry.pin_count // 2
            for i in range(half):
                pin_to_hole[i + 1] = (dip_left_col, start_row + i)
            for i in range(half):
                pin_to_hole[half + 1 + i] = (dip_right_col, start_row + (half - 1 - i))
        else:
            col = _col_for_main(ref, entry)
            for i in range(entry.pin_count):
                pin_to_hole[i + 1] = (col, start_row + i)
        return pin_to_hole

    def _build_pin_to_hole_paired_r(start_row: int, is_pullup: bool
                                    ) -> dict[int, tuple[str, int]]:
        """Pin to hole for a paired horizontal R: 2 pins on the same
        row. Common cols for series and pullup (the mains are on
        different cols — d/g for series, c/h for pullup — so no
        visual conflict even if the R is on the same cols)."""
        return {
            1: (paired_r_pin1_col, start_row),
            2: (paired_r_pin2_col, start_row),
        }

    # Uniform distribution over the BB
    n = len(main_entries)
    comp_rows = [_rows_for_component(e) for _, _, e in main_entries]
    total_used = sum(comp_rows)
    n_spaces = n + 1
    free_rows = max(0, bb.rows - total_used)
    inner_gap = free_rows // n_spaces if n_spaces > 0 else 0
    # Lower bound at ROW_GAP: 1 FREE hole row between 2 adjacent
    # components. The uniform distribution favors a large inner_gap if the
    # BB allows it; we just guarantee a visual minimum. If there is not enough
    # space for ROW_GAP between all + at least 0 margin, we degrade
    # (= falls back to the original uniform computation).
    if n >= 2:
        min_total_inner = ROW_GAP * (n - 1)
        if free_rows >= min_total_inner:
            inner_gap = max(inner_gap, ROW_GAP)
    margin_total = free_rows - inner_gap * max(0, n - 1)
    top_margin = margin_total // 2
    bottom_margin = margin_total - top_margin
    spaces = [top_margin] + [inner_gap] * max(0, n - 1) + [bottom_margin]

    # Index to find an entry by ref (useful for placing the paired R)
    entries_by_ref = {r: (r, t, e) for (r, t, e) in entries}

    placed: list[PlacedComponent] = []
    current = spaces[0] + 1
    for i, ((ref, type_id, entry), rows_used) in enumerate(zip(main_entries, comp_rows)):
        if current + rows_used - 1 > bb.rows:
            raise RuntimeError(
                f"Composant {ref} ({entry.name}) ne tient pas sur BB de "
                f"{bb.rows} rangees a partir de la rangee {current}"
            )
        # Determine whether the main is paired with a pullup R (BTN, DHT case)
        # or series (LED, buzzer) — for the routing's wire entry col.
        is_pullup_paired = (
            ref in main_to_r
            and not any(p.get("net", "").startswith("NET_")
                          for p in pins_by_ref.get(main_to_r[ref], []))
        )
        # Place the main
        placed.append(PlacedComponent(
            component_ref=ref,
            component_type=type_id,
            catalog_entry=entry,
            breadboard_idx=bb_idx,
            pin_to_hole=_build_pin_to_hole_main(ref, entry, current),
            mirrored=mirrored,
            paired_with_pullup=is_pullup_paired,
            attributes=dict(attrs_by_ref.get(ref, {})),
        ))
        # If paired main, also place its R horizontally co-located
        if ref in main_to_r:
            r_ref = main_to_r[ref]
            r_entry_tuple = entries_by_ref.get(r_ref)
            if r_entry_tuple is not None:
                _, r_type, r_cat = r_entry_tuple
                pin_idx = main_pin_with_r.get(ref, 1)
                r_row = current + (pin_idx - 1)
                # Color propagation via R: True iff the R's other pin
                # is on an internal NET_* net (series R case for LED/buzzer).
                # False for pullup R (Btn/DHT) where both sides have their own wires.
                r_pins = pins_by_ref.get(r_ref, [])
                propagate = any(
                    p.get("net", "").startswith("NET_") for p in r_pins
                )
                placed.append(PlacedComponent(
                    component_ref=r_ref,
                    component_type=r_type,
                    catalog_entry=r_cat,
                    breadboard_idx=bb_idx,
                    pin_to_hole=_build_pin_to_hole_paired_r(r_row, is_pullup=not propagate),
                    mirrored=mirrored,
                    propagate_color_through=propagate,
                    attributes=dict(attrs_by_ref.get(r_ref, {})),
                ))
        current += rows_used
        if i < n - 1:
            current += spaces[i + 1]

    return placed


# ─── Main API ──────────────────────────────────────────────────────
def place_scene(
    netlist_components: list[dict],   # [{'ref': str, 'type': str}, ...] minimal
    board_svg_path: Path,
) -> PlacedScene:
    """Compute the complete placement: board in the center + 1 or 2 BB + components.

    Args:
        netlist_components : minimal list [{'ref':..., 'type':...}, ...]
        board_svg_path     : path to the board SVG (e.g. uno_r3.svg)
    Returns:
        Complete PlacedScene, ready for the router (Phase 3) then the
        renderer (Phase 4).
    """
    # 1. Catalog: map the types to the catalog entries. The off-BB
    # components (battery_external e.g.) are set aside — placed separately
    # after the canvas computation. If the type is not in CATALOG, we
    # fallback on `resolve_generic` which chooses the SVG by pin_count
    # (single-row for 2-8 pins, plus the odd 9/11/13 added by TODO #58
    # 2026-08-20; DIP for 10-40 even). Allows rendering any component that
    # the Python detector might emit later, without having to add it to the
    # explicit CATALOG.
    from .component_catalog import RESISTOR_HORIZONTAL, resolve_generic
    typed_entries: list[tuple[str, str, CatalogEntry]] = []
    off_bb_entries: list[tuple[str, str, CatalogEntry, dict]] = []
    for c in netlist_components:
        entry = lookup(c["type"])
        if entry is None:
            entry = resolve_generic(c["type"], c.get("pins", []))
        if entry is None:
            continue   # truly unsupported (no SVG asset for this pin count)
        if c["type"] in OFF_BB_COMPONENT_TYPES:
            off_bb_entries.append((c["ref"], c["type"], entry, c.get("attributes", {})))
        else:
            typed_entries.append((c["ref"], c["type"], entry))

    # 2. Pair detection (main, R) — for the horizontal placement of the R
    # and the offset of the main to col 'h'/'c'.
    pins_by_ref = {c["ref"]: c.get("pins", []) for c in netlist_components}
    attrs_by_ref = {c["ref"]: c.get("attributes", {}) for c in netlist_components}
    main_to_r, r_to_main, main_pin_with_r = _identify_pairs(typed_entries, pins_by_ref)
    # Substitute the catalog of the paired Rs with RESISTOR_HORIZONTAL — they
    # will be placed across the trench (cols 'd'↔'g').
    typed_entries = [
        (ref, t, RESISTOR_HORIZONTAL if ref in r_to_main else e)
        for (ref, t, e) in typed_entries
    ]

    # Categorization by group: servos (max 6, all same BB), I2C (all
    # same BB), others. The paired Rs follow their main (so placed
    # with it by bb_assignments).
    def _is_i2c_main(entry: CatalogEntry) -> bool:
        return any(p in I2C_PIN_NAMES for p in entry.pin_labels.values())

    servo_entries = [(r, t, e) for (r, t, e) in typed_entries if t == "servo"]
    if len(servo_entries) > MAX_SERVOS:
        raise RuntimeError(
            f"Trop de servos : {len(servo_entries)} > {MAX_SERVOS}"
        )

    # For the row computation AND for the per-BB limit, we exclude the
    # paired Rs: they share the row of their main (horizontal
    # placement across the trench), so they do not consume a physical
    # slot. The MAX_COMPONENTS_PER_BB limit counts "row-slots"
    # (= main components + standalone non-paired Rs), not
    # components of all categories combined.
    def _row_significant_entries(entries: list) -> list:
        return [(r, t, e) for (r, t, e) in entries if r not in r_to_main]

    # 3. Strict limit on the total number of row slots + max servos
    n_slots = len(_row_significant_entries(typed_entries))
    if n_slots > MAX_COMPONENTS_TOTAL:
        raise RuntimeError(
            f"Projet trop grand : {n_slots} slots > limite {MAX_COMPONENTS_TOTAL}"
        )

    # 4. Decision 1 or 2 BB according to the number of row-significant slots.
    # Additional trigger: 2+ batteries in the netlist (= voltage split
    # from inference, cf _split_battery_for_voltage_compat). We force the
    # switch to 2 BBs to be able to place each battery on the external rail
    # of ITS BB (= side opposite the Arduino, mirror).
    n_batteries_netlist = sum(
        1 for c in netlist_components if c.get("type") == "battery_external"
    )
    force_2bb_battery_split = n_batteries_netlist >= 2

    if n_slots <= MAX_COMPONENTS_PER_BB and not force_2bb_battery_split:
        rows_needed = _total_rows_needed(
            [e for _, _, e in _row_significant_entries(typed_entries)]
        )
        bb1 = Breadboard(rows=max(ROWS_MIN, min(ROWS_MAX, rows_needed)))
        breadboards = [bb1]
        bb_assignments = [typed_entries]
    elif force_2bb_battery_split:
        # Allocation by voltage group: each on-BB load (driver, servo)
        # goes on the BB of its battery. BB[0] (left, mirror) receives the
        # components of the 2nd battery (BAT2/BAT_5V_2/...); BB[1] (right,
        # non-mirror) those of the 1st (BAT1/BAT_5V). The free components
        # (LED, BTN, without battery power) fill BB[1] first.
        bb_assignments = _allocate_by_battery_groups(
            typed_entries, netlist_components, r_to_main, main_to_r,
        )
        bb1_entries, bb2_entries = bb_assignments[0], bb_assignments[1]
        bb1_rows = max(ROWS_MIN, min(ROWS_MAX,
            _total_rows_needed([e for _, _, e in _row_significant_entries(bb1_entries)])))
        bb2_rows = max(ROWS_MIN, min(ROWS_MAX,
            _total_rows_needed([e for _, _, e in _row_significant_entries(bb2_entries)])))
        unified_rows = max(bb1_rows, bb2_rows)
        breadboards = [Breadboard(rows=unified_rows), Breadboard(rows=unified_rows)]
    else:
        # 2 BBs: we group the servos and the I2C on distinct BBs
        # (servos on BB0, I2C on BB1) to respect the rules "all the
        # servos same BB" and "all the I2C same BB". The paired Rs
        # accompany their main. The other components fill the
        # remaining capacity: BB0 first (= 1st BB), then BB1.
        i2c_main_entries = [(r, t, e) for (r, t, e) in typed_entries
                             if _is_i2c_main(e)]
        i2c_refs = {r for r, _, _ in i2c_main_entries}
        servo_refs = {r for r, _, _ in servo_entries}
        # Paired Rs linked to a servo or I2C: travel with their main
        servo_paired_rs = [(r, t, e) for (r, t, e) in typed_entries
                            if r in r_to_main and r_to_main[r] in servo_refs]
        i2c_paired_rs = [(r, t, e) for (r, t, e) in typed_entries
                          if r in r_to_main and r_to_main[r] in i2c_refs]
        other_entries = [(r, t, e) for (r, t, e) in typed_entries
                          if r not in servo_refs and r not in i2c_refs
                          and not (r in r_to_main
                                    and r_to_main[r] in servo_refs | i2c_refs)]

        # Initial allocations
        bb0_required = list(servo_entries) + list(servo_paired_rs)
        bb1_required = list(i2c_main_entries) + list(i2c_paired_rs)

        # If no servos, put the I2C on BB0 (1st BB)
        if not servo_entries and i2c_main_entries:
            bb0_required = list(i2c_main_entries) + list(i2c_paired_rs)
            bb1_required = []

        # Slot counter: a slot = 1 main component (= 1 row of the BB).
        # The paired Rs (r in r_to_main) accompany their main and do not
        # consume a slot.
        def _slots(entries: list) -> int:
            return sum(1 for e in entries if e[0] not in r_to_main)

        cap0 = MAX_COMPONENTS_PER_BB - _slots(bb0_required)
        cap1 = MAX_COMPONENTS_PER_BB - _slots(bb1_required)
        other_slots = _slots(other_entries)
        if cap0 < 0 or cap1 < 0 or other_slots > cap0 + cap1:
            raise RuntimeError(
                f"Allocation impossible : servos={len(servo_entries)} "
                f"I2C={len(i2c_main_entries)} autres={other_slots} slots "
                f"depasse {MAX_COMPONENTS_PER_BB} par BB"
            )

        # Build pair-aware "groups": each (main, paired R) is
        # an inseparable block. The series/pullup R must be on the same
        # BB as its main so it can be placed across the trench.
        # Otherwise the placer would skip it silently and the component
        # would be unwired (signal pin without a path to the intermediate R).
        groups: list[list] = []
        seen_refs: set[str] = set()
        for entry in other_entries:
            r_ref = entry[0]
            if r_ref in seen_refs:
                continue
            group = [entry]
            seen_refs.add(r_ref)
            # If it's a main with a paired R, we attach it
            if r_ref in main_to_r:
                paired_r_ref = main_to_r[r_ref]
                for e in other_entries:
                    if e[0] == paired_r_ref and e[0] not in seen_refs:
                        group.append(e)
                        seen_refs.add(e[0])
                        break
            # If it's a paired R whose main has not yet been
            # seen, we pull the main in front
            elif r_ref in r_to_main:
                main_ref = r_to_main[r_ref]
                if main_ref not in seen_refs:
                    for e in other_entries:
                        if e[0] == main_ref:
                            group.insert(0, e)
                            seen_refs.add(main_ref)
                            break
            groups.append(group)

        # Distribute the groups: try BB0 first (up to the cap), then
        # BB1. A group cannot be split between 2 BBs. The capacity
        # is in SLOTS (= mains and standalone Rs, paired Rs ride along).
        bb0_extras: list = []
        bb1_extras: list = []
        cap0_used = 0
        cap1_used = 0
        for group in groups:
            slots_needed = sum(1 for e in group if e[0] not in r_to_main)
            if cap0 - cap0_used >= slots_needed:
                bb0_extras.extend(group)
                cap0_used += slots_needed
            elif cap1 - cap1_used >= slots_needed:
                bb1_extras.extend(group)
                cap1_used += slots_needed
            else:
                raise RuntimeError(
                    f"Allocation impossible : groupe {[e[0] for e in group]} "
                    f"({slots_needed} slots) ne tient ni sur BB0 "
                    f"(restant {cap0 - cap0_used}) ni sur BB1 "
                    f"(restant {cap1 - cap1_used})"
                )

        bb1_entries = bb0_required + bb0_extras
        bb2_entries = bb1_required + bb1_extras

        bb1_rows = max(ROWS_MIN, min(ROWS_MAX,
            _total_rows_needed([e for _, _, e in _row_significant_entries(bb1_entries)])))
        bb2_rows = max(ROWS_MIN, min(ROWS_MAX,
            _total_rows_needed([e for _, _, e in _row_significant_entries(bb2_entries)])))
        unified_rows = max(bb1_rows, bb2_rows)
        breadboards = [Breadboard(rows=unified_rows), Breadboard(rows=unified_rows)]
        bb_assignments = [bb1_entries, bb2_entries]

    # 5. Place the components: BB[0] is the LEFT (mirror), BB[1] the RIGHT.
    placed_components: list[PlacedComponent] = []
    for bb_idx, (bb, entries) in enumerate(zip(breadboards, bb_assignments)):
        is_mirrored = (bb_idx == 0)
        placed_components.extend(
            place_components_on_breadboard(
                bb, bb_idx, entries, mirrored=is_mirrored,
                main_to_r=main_to_r, r_to_main=r_to_main,
                main_pin_with_r=main_pin_with_r,
                pins_by_ref=pins_by_ref,
                attrs_by_ref=attrs_by_ref,
            )
        )

    # 4. Load the board and compute the translates
    board_loader = BoardSVGLoader(board_svg_path)
    board_w, board_h = board_loader.size

    # Horizontal layout: [BB_LEFT(=BB[0])] [BOARD] [BB_RIGHT(=BB[1])?]
    # 1 BB  : BB on the left, board on the right (the 1st BB is always the left one).
    # 2 BB : BB[0] on the left, board in the center, BB[1] on the right.
    bb_left = breadboards[0]
    bb_left_w, bb_left_h = bb_left.size

    # Pre-computation of the x: depends only on the widths (board, BBs) and the
    # fixed gaps. Independent of the canvas height. Used to
    # resolve the rail targets of the batteries BEFORE building the grid.
    bb_left_x = GAP_LEFT
    board_x = bb_left_x + bb_left_w + GAP_BOARD_BB
    if len(breadboards) == 1:
        bb_translates_x = [bb_left_x]
    else:
        bb_right_x = board_x + board_w + GAP_BOARD_BB
        bb_translates_x = [bb_left_x, bb_right_x]

    # Resolution of the rail targets: batteries whose `+` ends at an
    # on-BB consumer → alignment on the outer V+ rail of this BB.
    battery_rail_targets = _resolve_battery_rail_targets(
        netlist_components, placed_components, breadboards,
        bb_translates_x, board_x,
    )
    rail_aligned_bats = set(battery_rail_targets.keys())

    # Compute the off-BB 2-row layout (TOP=batteries, MID=motors+drivers).
    # The rail-aligned batteries are SKIPPED from the main layout and
    # placed separately (fixed X on the V+ rail, same Y = TOP).
    grid_layout, off_bb_top_h, off_bb_mid_h, off_bb_zone_h = \
        _compute_off_bb_grid(off_bb_entries, netlist_components,
                             rail_aligned_batteries=rail_aligned_bats,
                             nb_breadboards=len(breadboards))

    # Effective GAP_TOP: the max between the default and the height required by
    # the off-BB zone + BB margin. If the zone is empty, we keep GAP_TOP.
    gap_top_eff = (max(GAP_TOP, off_bb_zone_h + BB_TO_OFF_BB_MARGIN)
                    if off_bb_entries else GAP_TOP)

    # y of the TOP row (batteries) — also used for the rail-aligned
    # batteries, outside the main layout.
    off_bb_top_y = OFF_BB_PADDING_TOP

    # Breadboard widths (used to anchor the motors to the BB centers).
    bb_widths = [bb.size[0] for bb in breadboards]

    def _place_rail_aligned_batteries(
        grid_placements: list[PlacedComponent],
    ) -> list[PlacedComponent]:
        """Place the rail-aligned batteries. Y = vertically centered on the
        motor (= same central axis as the motor, which is itself centered
        on the off-BB driver if present, otherwise at mid_y). If no motor
        is present, fallback: Y = mid_y (= top of the off-BB zone).
        """
        results: list[PlacedComponent] = []
        bat_by_ref = {ref: (ref, t, e, a)
                      for (ref, t, e, a) in off_bb_entries}
        # Y_center of the reference motor: average of the Y_centers of the motors
        # placed in the grid (typically only 1 motor per scene).
        motor_placements = [pc for pc in grid_placements
                              if pc.component_type in MOTOR_TYPES]
        if motor_placements:
            motor_y_centers = [pc.translate[1]
                                + _off_bb_dim(pc.component_type)[1] / 2.0
                                for pc in motor_placements]
            motor_y_center_ref = sum(motor_y_centers) / len(motor_y_centers)
        else:
            # Fallback: vertical center of the MID zone
            motor_y_center_ref = off_bb_top_y + off_bb_mid_h / 2.0
        for bat_ref, (_, _, rail_canvas_x) in battery_rail_targets.items():
            tpl = bat_by_ref.get(bat_ref)
            if tpl is None:
                continue
            ref_, type_id, cat_entry, attrs = tpl
            # rail_canvas_x = midpoint of the 2 bat-side rails (V+ + GND row 1).
            # We center the battery body (width = _off_bb_dim()) on
            # this midpoint so that the '+' and '-' pins symmetrically
            # frame the 2 power holes.
            bat_w = _off_bb_dim(type_id)[0]
            bat_h_loc = _off_bb_dim(type_id)[1]
            bat_y = motor_y_center_ref - bat_h_loc / 2.0
            results.append(PlacedComponent(
                component_ref=ref_,
                component_type=type_id,
                catalog_entry=cat_entry,
                breadboard_idx=OFF_BB_BREADBOARD_IDX,
                pin_to_hole={},
                mirrored=False,
                translate=(rail_canvas_x - bat_w / 2.0, bat_y),
                attributes=dict(attrs),
            ))
        return results

    def _place_stacked_dc_motors(
        battery_placements: list[PlacedComponent],
        non_rail_battery_placements: list[PlacedComponent],
    ) -> list[PlacedComponent]:
        """Place the dc_motors marked 'stacked' under a battery (= same
        off-BB column, just below). Associates 1:1 in the order of the
        netlist: 1st dc_motor under the 1st battery, etc. Rail-aligned
        batteries are preferred (more visually stable); we
        fall back on the non-rail ones if necessary.
        """
        results: list[PlacedComponent] = []
        stacked_refs = list(grid_layout.get("stacked_dc_motors", []))
        if not stacked_refs:
            return results
        stack_gap = grid_layout.get("stack_inner_gap", 10.0)
        # Concatenate rail-aligned (priority) then non-rail-aligned.
        all_bats = list(battery_placements) + list(non_rail_battery_placements)
        if not all_bats:
            return results
        by_ref = {ref: (ref, t, e, a) for (ref, t, e, a) in off_bb_entries}
        for i, motor_ref in enumerate(stacked_refs):
            bat = all_bats[i % len(all_bats)]
            tpl = by_ref.get(motor_ref)
            if tpl is None:
                continue
            ref_, type_id, cat_entry, attrs = tpl
            bat_type = bat.component_type
            bat_w = _off_bb_dim(bat_type)[0]
            bat_h_loc = _off_bb_dim(bat_type)[1]
            motor_w = _off_bb_dim(type_id)[0]
            # Center the motor on the battery (= same vertical axis).
            motor_x = bat.translate[0] + (bat_w - motor_w) / 2.0
            motor_y = bat.translate[1] + bat_h_loc + stack_gap
            results.append(PlacedComponent(
                component_ref=ref_,
                component_type=type_id,
                catalog_entry=cat_entry,
                breadboard_idx=OFF_BB_BREADBOARD_IDX,
                pin_to_hole={},
                mirrored=False,
                translate=(motor_x, motor_y),
                attributes=dict(attrs),
            ))
        return results

    def _apply_uln_stepper_inline_override(
            placed: list[PlacedComponent]) -> float | None:
        """Special layout for 2x stepper_motor + 2x uln2003 + 1 battery:
        in-line sequence BAT, M1, U1, M2, U2 (cf user 2026-05-19). The
        battery keeps its already-computed rail-aligned position; the 4
        other components are aligned to the right with widened gaps to
        let the power and JST wires through. The board is pushed to the
        right of the sequence (returned via the return value).

        Returns the new board_x if the case applies, otherwise None.
        """
        steppers = [c for c in netlist_components
                     if c.get("type") == "stepper_motor"]
        drivers = [c for c in netlist_components if c.get("type") == "uln2003"]
        bats = [c for c in netlist_components
                 if c.get("type") == "battery_external"]
        if len(steppers) != 2 or len(drivers) != 2 or len(bats) != 1:
            return None
        driver_refs = {d.get("ref") for d in drivers}
        pairs: list[tuple[str, str]] = []
        for m in steppers:
            paired = m.get("attributes", {}).get("_paired_driver")
            if paired in driver_refs:
                pairs.append((m.get("ref"), paired))
        if len(pairs) != 2:
            return None

        bat_ref = bats[0].get("ref")
        sequence = [r for pair in pairs for r in pair]   # [M1, U1, M2, U2]
        placed_by_ref = {pc.component_ref: pc for pc in placed}
        bat_pc = placed_by_ref.get(bat_ref)
        seq_pcs = [placed_by_ref.get(r) for r in sequence]
        if bat_pc is None or any(pc is None for pc in seq_pcs):
            return None

        # Widened gaps (vs default 16) to let the wires through:
        #   - BAT <-> M1: wide enough for the 2 bat power wires (BAT_5V
        #     and GND) that go down toward the BB
        #   - M <-> its driver U: 5 JST wires + power
        #   - U1 <-> M2 (inter-pair): even larger, U1's power wires
        #     (BAT_5V, GND) must go down + 4 wires D8-D11 toward
        #     U2 must cross
        GAP_BAT_M = 50
        GAP_INTRA = 50
        GAP_INTER = 100
        gaps_after = {0: GAP_INTRA, 1: GAP_INTER, 2: GAP_INTRA, 3: 0}

        widths = [_off_bb_dim(pc.component_type)[0] for pc in seq_pcs]
        heights = [_off_bb_dim(pc.component_type)[1] for pc in seq_pcs]
        max_h = max(heights)
        mid_y_local = OFF_BB_PADDING_TOP + off_bb_top_h + (
            OFF_BB_ROW_GAP if off_bb_top_h > 0 and off_bb_mid_h > 0 else 0)

        # Specific vertical alignment for the stepper: its JST pins
        # must be aligned on the center of the rect50 (white JST
        # connector) of the neighboring ULN2003. The ULN2003 SVG has a 180°
        # rotation around (119.87, 100.61) on the main group -> local
        # rect50 (y=36, h=80) appears VISUALLY at y=85.22..165.22.
        # Constants:
        #   - uln2003 rect50 visual center Y = 125.22
        #   - stepper_motor pins local center Y = ~55.39
        ULN_RECT50_CENTER_Y = 125.22
        STEPPER_PINS_CENTER_Y = 55.39
        STEPPER_ALIGN_OFFSET = ULN_RECT50_CENTER_Y - STEPPER_PINS_CENTER_Y

        # Starting point = right edge of the battery (rail-aligned).
        bat_w = _off_bb_dim(bat_pc.component_type)[0]
        cur_x = bat_pc.translate[0] + bat_w + GAP_BAT_M
        # Y of all the ULN2003 drivers (they are all in the top row of the
        # MID zone, so all at the same y).
        uln_y = mid_y_local  # uln2003 is the tallest -> top of MID row
        for i, (pc, w, h) in enumerate(zip(seq_pcs, widths, heights)):
            if pc.component_type == "stepper_motor":
                y = uln_y + STEPPER_ALIGN_OFFSET
            else:
                # ULN2003 = top of MID. All the others vertically centered.
                y = mid_y_local + (max_h - h) / 2.0
            pc.translate = (cur_x, y)
            cur_x += w + gaps_after.get(i, 0)
        # The board stays at its original position (close to the BB). The
        # sequence overflows above the Arduino on the right, but the
        # v3 routing knows how to pass above the board body via the TOP lane
        # (y < board_y).
        return None

    if len(breadboards) == 1:
        canvas_w = GAP_LEFT + bb_left_w + GAP_BOARD_BB + board_w + GAP_RIGHT
        canvas_h = max(board_h, bb_left_h) + gap_top_eff + GAP_BOTTOM
        board_y = gap_top_eff + (canvas_h - gap_top_eff - GAP_BOTTOM - board_h) / 2
        bb_left_y = gap_top_eff + (canvas_h - gap_top_eff - GAP_BOTTOM - bb_left_h) / 2

        grid_placements = _place_off_bb_from_grid(
            grid_layout, off_bb_entries,
            board_x=board_x, board_w=board_w,
            bb_translates_x=bb_translates_x,
            bb_widths=bb_widths,
            top_h=off_bb_top_h, mid_h=off_bb_mid_h,
        )
        placed_components.extend(grid_placements)
        rail_bat_placements = _place_rail_aligned_batteries(grid_placements)
        placed_components.extend(rail_bat_placements)
        non_rail_bat_placements = [pc for pc in grid_placements
                                    if pc.component_type == "battery_external"]
        placed_components.extend(_place_stacked_dc_motors(
            rail_bat_placements, non_rail_bat_placements))
        new_board_x = _apply_uln_stepper_inline_override(placed_components)
        if new_board_x is not None and new_board_x != board_x:
            board_x = new_board_x
            # canvas_w must accommodate the board at its new position.
            canvas_w = max(canvas_w, board_x + board_w + GAP_RIGHT)
        # TOP lane: just above the board top (between the bottom of the
        # off-BB zone and the upper edge of the board+BBs).
        lane_y_top_base = max(LANE_Y_BASE_TOP_DEFAULT,
                              gap_top_eff - LANE_Y_TOP_BASE_OFFSET)
        # Extend the canvas to encompass all the off-BB components that
        # would overflow on the right. We keep the same GAP_RIGHT as the
        # minimal margin.
        canvas_w = _grow_canvas_for_off_bb(canvas_w, placed_components)
        return PlacedScene(
            board_loader=board_loader,
            board_translate=(board_x, board_y),
            breadboards=breadboards,
            breadboard_translates=[(bb_left_x, bb_left_y)],
            placed_components=placed_components,
            canvas_size=(canvas_w, canvas_h),
            lane_y_top_base=lane_y_top_base,
            netlist_components=list(netlist_components),
        )

    else:
        bb_right = breadboards[1]
        bb_right_w, bb_right_h = bb_right.size
        canvas_w_init = GAP_LEFT + bb_left_w + GAP_BOARD_BB + board_w + GAP_BOARD_BB + bb_right_w + GAP_RIGHT
        canvas_w = canvas_w_init
        canvas_h = max(board_h, bb_left_h, bb_right_h) + gap_top_eff + GAP_BOTTOM

        bb_left_y = gap_top_eff + (canvas_h - gap_top_eff - GAP_BOTTOM - bb_left_h) / 2
        board_y = gap_top_eff + (canvas_h - gap_top_eff - GAP_BOTTOM - board_h) / 2
        bb_right_y = gap_top_eff + (canvas_h - gap_top_eff - GAP_BOTTOM - bb_right_h) / 2

        grid_placements = _place_off_bb_from_grid(
            grid_layout, off_bb_entries,
            board_x=board_x, board_w=board_w,
            bb_translates_x=bb_translates_x,
            bb_widths=bb_widths,
            top_h=off_bb_top_h, mid_h=off_bb_mid_h,
        )
        placed_components.extend(grid_placements)
        rail_bat_placements = _place_rail_aligned_batteries(grid_placements)
        placed_components.extend(rail_bat_placements)
        non_rail_bat_placements = [pc for pc in grid_placements
                                    if pc.component_type == "battery_external"]
        placed_components.extend(_place_stacked_dc_motors(
            rail_bat_placements, non_rail_bat_placements))
        new_board_x = _apply_uln_stepper_inline_override(placed_components)
        if new_board_x is not None and new_board_x != board_x:
            board_x = new_board_x
            # canvas_w must accommodate the board at its new position.
            canvas_w = max(canvas_w, board_x + board_w + GAP_RIGHT)
        lane_y_top_base = max(LANE_Y_BASE_TOP_DEFAULT,
                              gap_top_eff - LANE_Y_TOP_BASE_OFFSET)
        canvas_w = _grow_canvas_for_off_bb(canvas_w, placed_components)
        return PlacedScene(
            board_loader=board_loader,
            board_translate=(board_x, board_y),
            breadboards=breadboards,
            breadboard_translates=[(bb_left_x, bb_left_y), (bb_right_x, bb_right_y)],
            placed_components=placed_components,
            canvas_size=(canvas_w, canvas_h),
            lane_y_top_base=lane_y_top_base,
            netlist_components=list(netlist_components),
        )
