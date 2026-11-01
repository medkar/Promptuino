"""Router v2: traces the wires between the board, the power rails and the components.

Revised strategy (Phase 3.5):

1. Lateral bypass: each wire leaving an Arduino pin first takes a
   horizontal step to exit the PCB, avoiding overlap with other pins.

2. Power rails: for power nets (5V/3V3/GND/VIN), we route:
   - Arduino pin -> matching rail (V+/GND) of the nearest BB (1 wire)
   - Rail -> each consumer component (1 short jumper per consumer,
     between rail row and col 'a' on the same row)

3. Signal nets: for D0/D7/A3/etc., a direct wire Arduino -> col 'a' of the BB
   (on the same row as the component pin, the tie-strip makes the connection).

4. Manhattan routing that avoids the Arduino PCB: the wires do not cross the
   board rectangle. If the source pin is on the left side of the Arduino
   (power/analog) and the target on the BB to the right, we go around the bottom.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .breadboard_generator import Breadboard
from .layout import (
    PlacedComponent, PlacedScene,
    WIRE_ENTRY_COL_LEFT, WIRE_ENTRY_COL_RIGHT,
    _OFF_BB_DIMS, _OFF_BB_DEFAULT_DIM,
)

# ─── Colors ────────────────────────────────────────────────────────────
_NET_PALETTE: list[str] = [
    "#1f77b4",  # blue
    "#2ca02c",  # green
    "#9467bd",  # purple
    "#17becf",  # cyan
    "#e377c2",  # pink
    "#8c564b",  # brown
    "#bcbd22",  # olive
    "#7f7f7f",  # gray
    "#1abc9c",  # turquoise
    "#5d3a9b",  # indigo
    "#e91e63",  # magenta
    "#00897b",  # dark teal
]

_NET_POWER_COLORS: dict[str, str] = {
    "5V":  "#d62728",
    "VIN": "#d62728",
    "3V3": "#ff7f0e",
    "GND": "#222222",
}

# Color of the + of the external battery: dark red rgb(127, 23, 23),
# distinct from the Arduino #d62728 so the user identifies
# the external power source immediately.
_BATTERY_PLUS_COLOR = "#7f1717"

_POWER_NETS = set(_NET_POWER_COLORS)

# Component pins that belong to the I2C bus (consumer side).
_I2C_PIN_NAMES = {"SDA", "SCL"}

# For each I2C bus, the physical board pins electrically
# connected to it (often 2 pins exposed on the PCB for the same silicon node).
# Order = order of preference when there are few consumers (Strategy A).
_I2C_PHYSICAL_PINS_FOR_BUS: dict[str, list[str]] = {
    "SDA": ["SDA", "A4"],
    "SCL": ["SCL", "A5"],
}

# Mapping net name (from the netlist) -> board pin id (in the SVG boards)
_NET_TO_BOARD_PIN: dict[str, str] = {
    "5V":  "V5V",
    "3V3": "V3V3",
    "GND": "GND2",
    "VIN": "VIN",
}

# Mapping net power -> rail id on the BB
_NET_TO_RAIL: dict[str, str] = {
    "5V":  "V+",
    "VIN": "V+",
    "3V3": "V+",   # by default we share the V+ rail (BB has no dedicated rail)
    "GND": "GND",
}

# Routing constants
BYPASS_LATERAL_SOURCE = 5   # px: gap PCB edge <-> 1st wire = STAGGER_STEP (uniform)
BYPASS_LATERAL_TARGET = 8   # px: gap vs target hole (track 0). Smaller = wire closer to col 'a',
                             # thus farther from the blue band on the channel side.
LANE_Y_BASE_TOP = 70        # px: y of the lowest TOP lane (corridor above the BB)
LANE_Y_BASE_BOT_OFFSET = 10 # px: from the bottom edge of the canvas for the 1st BOTTOM lane
LANE_Y_STEP = 5             # px: gap between lanes of consecutive tracks
STAGGER_STEP = 5             # px: offset per track on the bypasses (anti-overlap)
RAIL_CONNECTION_ROW = 1     # row where Arduino connects to the rail (1st row)
# Off-BB lateral bypasses: margins differentiated by pin type.
#   - signal (IN/OUT/EN/PWM/STEP/DIR/...): clear detour for readability
#   - power  (VCC/VS/GND/VIN/...): discreet detour, the wire stays close to the body
# Separate track counters (ref, edge, kind) → the 2 families don't
# mix in the routing order.
OFF_BB_BYPASS_MARGIN_SIGNAL  = 30
OFF_BB_BYPASS_STAGGER_SIGNAL = 10
OFF_BB_BYPASS_MARGIN_POWER   = 10
OFF_BB_BYPASS_STAGGER_POWER  = 5


@dataclass
class Wire:
    net: str
    color: str
    path: list[tuple[float, float]]
    fn_id: str = ""


# ─── Color resolution ────────────────────────────────────────────────────
def _net_color(net: str, signal_idx: int) -> str:
    if net in _NET_POWER_COLORS:
        return _NET_POWER_COLORS[net]
    return _NET_PALETTE[signal_idx % len(_NET_PALETTE)]


def _resolve_board_pin(loader, net_name: str) -> str | None:
    candidate = _NET_TO_BOARD_PIN.get(net_name, net_name)
    if loader.has_pin(candidate):
        return candidate
    if loader.has_pin(net_name):
        return net_name
    return None


# ─── Lookup canvas positions ─────────────────────────────────────────────
def _component_pin_canvas(scene: PlacedScene,
                          placed: PlacedComponent,
                          pin_index: int,
                          ) -> tuple[float, float] | None:
    # Off-BB components (battery_external): pin canvas = translate + local
    # pin from the SVG asset (multiplied by catalog_entry.render_scale
    # when the component is rendered at a reduced scale — e.g. NEMA17).
    if placed.breadboard_idx < 0:
        from .svg_component_loader import ComponentSVGLoader
        scale = getattr(placed.catalog_entry, "render_scale", 1.0)
        loader = ComponentSVGLoader(placed.catalog_entry.asset_path, scale=scale)
        pin_local = loader.pin_positions().get(pin_index)
        if pin_local is None:
            return None
        return (placed.translate[0] + pin_local[0],
                placed.translate[1] + pin_local[1])
    hole = placed.pin_to_hole.get(pin_index)
    if hole is None:
        return None
    col_id, row = hole
    bb = scene.breadboards[placed.breadboard_idx]
    cx, cy = bb.hole_position(col_id, row)
    tx, ty = scene.breadboard_translates[placed.breadboard_idx]
    return (cx + tx, cy + ty)


def _component_wire_entry(scene: PlacedScene,
                          placed: PlacedComponent,
                          pin_index: int,
                          ) -> tuple[float, float] | None:
    """Canvas coords of the hole WHERE THE WIRE arrives (col 'a' same row, not the pin itself).

    Lets the routing avoid landing on the same hole as the component pin.
    The breadboard tie-strip electrically connects the 5 holes of the row.
    """
    hole = placed.pin_to_hole.get(pin_index)
    if hole is None:
        return None
    col_id, row = hole
    bb = scene.breadboards[placed.breadboard_idx]
    # The entry col is always on the component tie-strip. Special cases
    # for the PULLUP pairs (main on col 'b' BB0 / 'i' BB1): the Arduino wire
    # arrives right next to the main (col 'c'/'h'), not at the end of the tie-strip,
    # so it passes between the horizontal R and the main.
    # Otherwise: entry on the col closest to the rails (board side):
    # - non-mirror BB (board on the left): ts-left → 'a', ts-right → 'f' (channel).
    # - mirror BB (board on the right)    : ts-left → 'e' (channel), ts-right → 'j'.
    if placed.paired_with_pullup:
        # Pullup-pair: wire entry between the main and the R (= between the
        # main and R.B cols on the main tie-strip).
        # BB0 mirror: main col 'c', R.B col 'e' → entry 'd'
        # BB1 non-mirror: main col 'h', R.B col 'f' → entry 'g'
        entry_col = "d" if placed.mirrored else "g"
    elif col_id in ("a", "b", "c", "d", "e"):
        # For DIPs: entry on the FIRST free col adjacent to the body
        # on the side opposite the body (= first hole outside the body on the pin
        # tie strip). Body BB1: 'd'-'h', body BB2: 'c'-'g'.
        #  - BB1 non-mirror, pin at 'd' (= left edge of body) → entry 'c'
        #  - BB2 mirror,     pin at 'c' (= right edge of body) → entry 'b'
        if placed.catalog_entry.is_dip:
            entry_col = "b" if placed.mirrored else "c"
        else:
            entry_col = "e" if placed.mirrored else "a"
    elif col_id in ("f", "g", "h", "i", "j"):
        # Same on the right side of the body:
        #  - BB1 non-mirror, pin at 'h' (= right edge of body) → entry 'i'
        #  - BB2 mirror,     pin at 'g' (= left edge of body) → entry 'h'
        if placed.catalog_entry.is_dip:
            entry_col = "h" if placed.mirrored else "i"
        else:
            entry_col = "j" if placed.mirrored else "f"
    else:
        # Component placed on a rail (rare)
        return _component_pin_canvas(scene, placed, pin_index)
    cx, cy = bb.hole_position(entry_col, row)
    tx, ty = scene.breadboard_translates[placed.breadboard_idx]
    return (cx + tx, cy + ty)


def _board_pin_canvas(scene: PlacedScene, fn: str) -> tuple[float, float]:
    return scene.board_loader.pin_position(fn, translate=scene.board_translate)


def _board_bbox(scene: PlacedScene) -> tuple[float, float, float, float]:
    """Canvas BBox of the Arduino PCB body (without viewBox margins): (x_min, y_min, x_max, y_max).

    Uses the real bbox of the `board-body` rect, not the SVG viewBox, so that
    the outgoing wires are as close as possible to the visible edge of the PCB.
    """
    return scene.board_loader.body_bbox(translate=scene.board_translate)


def _board_pin_side(scene: PlacedScene, board_pin_xy: tuple[float, float]) -> str:
    """Returns 'left' or 'right' depending on whether the pin is on the left or right side of the PCB."""
    x_min, _, x_max, _ = _board_bbox(scene)
    center_x = (x_min + x_max) / 2
    return "left" if board_pin_xy[0] < center_x else "right"


def _name_to_pin_index(catalog_entry, pin_name: str) -> int | None:
    for idx, label in catalog_entry.pin_labels.items():
        if label == pin_name:
            return idx
    return None


def pin_canvas_position_by_name(scene: PlacedScene,
                                ref: str,
                                pin_name: str,
                                ) -> tuple[float, float] | None:
    """Canvas coords (x, y) of the pin named `pin_name` of the component `ref`.

    Public API for external consumers (e.g. interactive schematic) that
    need to locate a pin without knowing the internal pin_index.
    Returns None if the component or the pin don't exist in the scene.
    """
    placed = next(
        (pc for pc in scene.placed_components if pc.component_ref == ref),
        None,
    )
    if placed is None:
        return None
    pin_idx = _name_to_pin_index(placed.catalog_entry, pin_name)
    if pin_idx is None:
        return None
    return _component_pin_canvas(scene, placed, pin_idx)


def _off_bb_body_bbox(placed: PlacedComponent) -> tuple[float, float, float, float]:
    """(x_min, y_min, x_max, y_max) of the body of an off-BB component on the canvas."""
    cx, cy = placed.translate
    w, h = _OFF_BB_DIMS.get(placed.component_type, _OFF_BB_DEFAULT_DIM)
    return (cx, cy, cx + w, cy + h)


def _off_bb_pin_edge(placed: PlacedComponent,
                      pin_xy: tuple[float, float]) -> str:
    """Returns 'left', 'right', 'top' or 'bottom' depending on the edge closest
    to the pin on the off-BB body. Used to decide whether the wire approach
    should be lateral (LEFT/RIGHT) or vertical (TOP/BOTTOM).

    If the pin is OUTSIDE the body (wire tail for a cylindrical motor
    e.g., or external pad), we return the crossed edge directly
    => natural approach in the direction of the tail (no artificial
    lateral bypass on a body the pin has already passed).
    """
    x_min, y_min, x_max, y_max = _off_bb_body_bbox(placed)
    px, py = pin_xy
    # Pin outside the body: descent in the direction of the tail.
    if py > y_max:
        return "bottom"
    if py < y_min:
        return "top"
    if px < x_min:
        return "left"
    if px > x_max:
        return "right"
    # Pin inside the body: closest edge.
    dists = {
        "left":   px - x_min,
        "right":  x_max - px,
        "top":    py - y_min,
        "bottom": y_max - py,
    }
    return min(dists, key=lambda k: dists[k])


def _off_bb_lateral_bypass_x(placed: PlacedComponent,
                              edge: str, track: int,
                              kind: str = "signal") -> float | None:
    """X of the lateral bypass for a LEFT/RIGHT pin of an off-BB.

    `kind`:
      - 'signal': large detour (margin 30, stagger 10) — control pins
        IN*, OUT*, EN*, PWM*, STEP, DIR, etc.
      - 'power' : small detour (margin 10, stagger 5)  — power/ground pins
        VCC, VS, GND, VIN, etc.

    Returns None if the edge is TOP/BOTTOM (direct vertical descent).
    """
    x_min, _, x_max, _ = _off_bb_body_bbox(placed)
    if kind == "power":
        margin = OFF_BB_BYPASS_MARGIN_POWER + track * OFF_BB_BYPASS_STAGGER_POWER
    else:
        margin = OFF_BB_BYPASS_MARGIN_SIGNAL + track * OFF_BB_BYPASS_STAGGER_SIGNAL
    if edge == "left":
        return x_min - margin
    if edge == "right":
        return x_max + margin
    return None


# Pin names considered as power/ground on an off-BB driver. These pins
# keep a vertical descent at the pin X (no lateral bypass): their
# path is conceptually different — direct power supply vs control/output
# signal that benefits from a visible detour for readability.
_OFF_BB_POWER_PIN_NAMES: set[str] = {
    "VCC", "VS", "VM", "VMOT", "VDD",   # power supply logic side / motor
    "GND",                              # ground
    "5V", "3V3", "VIN",                 # Arduino nets used as labels
    "V+", "V-",                          # generic rails
    "+", "-",                            # batteries (filtered earlier but defensive)
}


def _is_off_bb_power_pin(placed: PlacedComponent, pin_idx: int) -> bool:
    """True if the pin (by its label in the catalog) is a power/ground pin."""
    name = placed.catalog_entry.pin_labels.get(pin_idx, "")
    return name.upper() in _OFF_BB_POWER_PIN_NAMES


# ─── Routing helpers ─────────────────────────────────────────────────────
def _path_around_board(start: tuple[float, float],
                       end: tuple[float, float],
                       scene: PlacedScene,
                       source_side: str,         # 'left' or 'right'
                       lane_track: int = 0,      # index in the corridor (top OR bottom), for unique lane_y
                       side_track: int = 0,      # track PER SIDE (source bypass positioning)
                       target_track: int = 0,    # track PER BB (bypass_x_target positioning in safe zone)
                       descent_at_target: bool = False,
                       corridor: str = "top",    # 'top' or 'bottom'
                       bypass_x_target_override: float | None = None,
                       same_side: bool = False,
                       ) -> list[tuple[float, float]]:
    """Traces a Manhattan path from `start` to `end` via a TOP or BOTTOM corridor.

    `corridor='top'`    : lane_y above all elements (decreasing).
    `corridor='bottom'` : lane_y below all elements (increasing).

    `bypass_x_target_override`: if provided, forces the X of the bypass on the target side
        (used for the LEFT/RIGHT pins of an off-BB driver: lateral
        approach outside the body, final horizontal segment toward the pin).

    `same_side=True`: indicates that source and target are on the same side
        (e.g.: Arduino-pin RIGHT toward off-BB pin RIGHT). In this case we
        short-circuit the lane (no detour toward the opposite edge):
        the wire descends directly to the X of the target bypass. Requires
        `bypass_x_target_override` to be provided.
    """
    sx, sy = start
    ex, ey = end
    bx_min, by_min, bx_max, by_max = _board_bbox(scene)

    # Lane y according to the chosen corridor
    if corridor == "top":
        lane_y = scene.lane_y_top_base -lane_track * LANE_Y_STEP
    else:  # bottom
        canvas_h = scene.canvas_size[1]
        lane_y = canvas_h - LANE_Y_BASE_TOP + lane_track * LANE_Y_STEP

    # Source bypass: OUTSIDE the Arduino PCB (beyond the edge)
    if source_side == "right":
        bypass_x_source = bx_max + BYPASS_LATERAL_SOURCE + side_track * STAGGER_STEP
    else:
        bypass_x_source = bx_min - BYPASS_LATERAL_SOURCE - side_track * STAGGER_STEP

    # Same-side: simplified path (3 segments, 2 elbows). We go directly
    # to the X of the target bypass (outside the off-BB body on the right side), we
    # go straight up/down, we reach the pin horizontally.
    if same_side and bypass_x_target_override is not None:
        return [
            start,
            (bypass_x_target_override, sy),
            (bypass_x_target_override, ey),
            end,
        ]

    # Override mode: forced lateral approach (off-BB driver, pin LEFT/RIGHT).
    # The final segment is horizontal (from bypass_x → pin), not vertical.
    if bypass_x_target_override is not None:
        return [
            start,
            (bypass_x_source, sy),
            (bypass_x_source, lane_y),
            (bypass_x_target_override, lane_y),
            (bypass_x_target_override, ey),
            end,
        ]

    if descent_at_target:
        return [
            start,
            (bypass_x_source, sy),
            (bypass_x_source, lane_y),
            (ex, lane_y),
            end,
        ]

    # Target bypass ALTERNATES: even tracks descend to the LEFT of the target,
    # odd tracks to the RIGHT. Uses target_track (per-BB) to limit
    # the travel within the safe zone (close to the target, not beyond).
    half_track = target_track // 2
    offset_target = half_track * STAGGER_STEP
    if target_track % 2 == 0:
        bypass_x_target = ex - BYPASS_LATERAL_TARGET - offset_target
    else:
        bypass_x_target = ex + BYPASS_LATERAL_TARGET + offset_target

    return [
        start,
        (bypass_x_source, sy),
        (bypass_x_source, lane_y),
        (bypass_x_target, lane_y),
        (bypass_x_target, ey),
        end,
    ]


def _choose_corridor(target_row: int, bb_rows: int) -> str:
    """Chooses the corridor (top/bottom) according to the position of the target row."""
    return "top" if target_row <= bb_rows / 2 else "bottom"


def _i2c_physical_pins(board_loader, bus: str) -> list[str]:
    """List of the physical board pins wired to the I2C bus `bus`,
    in order of preference (filters out the non-existent ones)."""
    return [p for p in _I2C_PHYSICAL_PINS_FOR_BUS.get(bus, [])
            if board_loader.has_pin(p)]


# Cols used for the tie-strip → consumer jumpers. A distinct col
# per jumper to respect "1 wire per hole" on the BB. Capped at 4 (= 5 holes
# per tie-strip - 1 for col 'a'/'j' reserved for the Arduino arrival).
_I2C_JUMPER_START_COLS_NON_MIRROR = ["b", "c", "d", "e"]
_I2C_JUMPER_START_COLS_MIRROR     = ["i", "h", "g", "f"]
_I2C_BB_HALF_PITCH = 14   # BB half-pitch (= PITCH/2) to pass between the holes


def _i2c_jumper_path(scene: PlacedScene,
                     bb_idx: int,
                     jumper_idx: int,
                     bus_row: int,
                     consumer_row: int,
                     mirrored: bool,
                     bus: str = "SDA",
                     ) -> list[tuple[float, float]]:
    """Manhattan path of an I2C jumper: bus tie-strip → component-side
    tie-strip, passing through the central channel of the BB so as to never
    fly over a hole.

    Assumption: I2C components placed on the alternate col (g for non-mirror,
    d for mirror), and bus on the other tie-strip (cols a-e or f-j).

    `jumper_idx` (0..3) determines the distinct start col on the bus
    tie-strip (rule "1 wire per hole").

    Col layout:
    - Non-mirror: bus on cols a-e (col 'a' = Arduino, b/c/d/e = jumpers),
                   components on col 'g' (body covers h/i/j), end col = 'f'
                   (only free col on the right side, electrically tied to 'g').
    - Mirror    : bus on cols f-j (col 'j' = Arduino, i/h/g/f = jumpers),
                   components on col 'd' (body covers a/b/c), end col = 'e'.
    """
    bb = scene.breadboards[bb_idx]
    tx, ty = scene.breadboard_translates[bb_idx]

    cols = (_I2C_JUMPER_START_COLS_MIRROR if mirrored
            else _I2C_JUMPER_START_COLS_NON_MIRROR)
    if jumper_idx >= len(cols):
        raise RuntimeError(
            f"Trop de consommateurs I2C sur la BB ({jumper_idx + 1} > {len(cols)})"
        )
    start_col = cols[jumper_idx]
    end_col = "e" if mirrored else "f"

    sx_local, sy_local = bb.hole_position(start_col, bus_row)
    sx, sy = sx_local + tx, sy_local + ty
    ex_local, ey_local = bb.hole_position(end_col, consumer_row)
    ex, ey = ex_local + tx, ey_local + ty

    # Staggered channel x: SDA in the LEFT half of the channel, SCL in the
    # RIGHT half, with a gap reserved in the middle to visually separate
    # the 2 buses (otherwise SDA[0] and SCL[0] almost touch). Stagger by
    # jumper_idx in each half so that SDA[i] != SDA[j] != SCL[i].
    cx_e_local = bb.hole_position("e", 1)[0]
    cx_f_local = bb.hole_position("f", 1)[0]
    channel_mid = (cx_e_local + cx_f_local) / 2 + tx
    # Channel width ~14 px, half-width 7. We reserve 2 px on each side
    # of the middle (visible gap of 4 px between SDA[0] and SCL[0]) and we spread
    # 4 lanes over the remaining 5 px per side.
    bus_halfgap = 2.0
    n_max_per_bus = 4
    slot = (7.0 - bus_halfgap) / n_max_per_bus    # 1.25 px per lane
    bus_offset = bus_halfgap + (jumper_idx + 0.5) * slot
    channel_x = channel_mid + (-bus_offset if bus == "SDA" else +bus_offset)

    # sy_gap / ey_gap staggered in the row gap to separate the horizontal
    # segments of the different jumpers of the same bus (otherwise they
    # overlap when 2+ jumpers share the same row gap).
    base = 7              # minimal offset from the hole (leaves some air)
    step = 4              # gap between 2 jumpers
    offset = base + jumper_idx * step

    if bus_row > consumer_row:        # going up: exit bus at the top, approach consumer from the bottom
        sy_gap = sy - offset
        ey_gap = ey + offset
    elif bus_row < consumer_row:      # going down: exit bus at the bottom, approach consumer from the top
        sy_gap = sy + offset
        ey_gap = ey - offset
    else:
        sy_gap = sy
        ey_gap = ey

    return [
        (sx, sy),               # 1. start hole (start_col, bus_row)
        (sx, sy_gap),           # 2. vertical exit toward row gap
        (channel_x, sy_gap),    # 3. lateral hop toward the central channel
        (channel_x, ey_gap),    # 4. vertical crossing within the channel
        (ex, ey_gap),           # 5. lateral hop toward end_col
        (ex, ey),               # 6. entry into the hole (end_col, consumer_row)
    ]


def _i2c_bus_rows(host_bb_idx: int,
                  i2c_components: list,
                  ) -> tuple[int, int]:
    """Rows of the 2 tie-strips of the I2C bus (SDA, SCL), centered on the rows
    occupied by the I2C components of the BB. SDA takes the lower row,
    SCL the next one.
    """
    all_rows: list[int] = []
    seen: set[str] = set()
    for placed in i2c_components:
        if placed.component_ref in seen:
            continue
        seen.add(placed.component_ref)
        for _, r in placed.pin_to_hole.values():
            all_rows.append(r)
    if not all_rows:
        return (1, 2)
    center = (min(all_rows) + max(all_rows)) // 2
    return (center, center + 1)


def _bb_hole_canvas(scene: PlacedScene,
                    bb_idx: int,
                    col_id: str,
                    row: int,
                    ) -> tuple[float, float]:
    """Canvas coord of a hole (col, row) of a breadboard."""
    bb = scene.breadboards[bb_idx]
    cx, cy = bb.hole_position(col_id, row)
    tx, ty = scene.breadboard_translates[bb_idx]
    return (cx + tx, cy + ty)


def _bb_rail_canvas(scene: PlacedScene,
                    bb_idx: int,
                    rail_kind: str,    # 'V+' or 'GND'
                    side: str,         # 'left' or 'right'
                    row: int,
                    ) -> tuple[float, float]:
    """Canvas coord of a hole on a rail of breadboard `bb_idx`."""
    bb = scene.breadboards[bb_idx]
    rail_id = f"{rail_kind}_{side}"   # 'V+_left', 'GND_left', etc.
    cx, cy = bb.hole_position(rail_id, row)
    tx, ty = scene.breadboard_translates[bb_idx]
    return (cx + tx, cy + ty)


def _bb_to_bb_bridge_path(start: tuple[float, float],
                          end: tuple[float, float],
                          scene: PlacedScene,
                          lane_track: int = 0,
                          corridor: str = "bottom",
                          ) -> list[tuple[float, float]]:
    """Bridge between 2 holes of different BBs via a lateral corridor.

    Used to daisy-chain the power supply between BBs: the Arduino powers
    only the 1st BB (from the top, row 1), then this BB passes the power
    to the next one from the bottom (row N) via the BOTTOM corridor. Reproduces the
    real physical wiring where a single wire leaves the Arduino V5/GND pin.
    """
    sx, sy = start
    ex, ey = end
    canvas_h = scene.canvas_size[1]
    if corridor == "top":
        lane_y = scene.lane_y_top_base -lane_track * LANE_Y_STEP
    else:
        lane_y = canvas_h - LANE_Y_BASE_TOP + lane_track * LANE_Y_STEP
    return [
        (sx, sy),
        (sx, lane_y),
        (ex, lane_y),
        (ex, ey),
    ]


def _jumper_path(rail_xy: tuple[float, float],
                 target_xy: tuple[float, float],
                 rail_kind: str,
                 rail_side: str,
                 row: int,
                 ) -> list[tuple[float, float]]:
    """Path of a rail -> col 'a'/'j' jumper.

    For OUTER rails (V+_left, GND_right), the jumper would cross the INNER rail
    (GND_left, V+_right) on the way. We then deviate OVER THE TOP to
    pass between 2 rows (above the blocking hole).
    """
    rx, ry = rail_xy
    tx, ty = target_xy
    distance = abs(tx - rx)

    # Deviation required as soon as at least 1 intermediate col/rail is between
    # start and end on the row (otherwise the wire crosses holes).
    # Heuristic: distance > 1.5 * PITCH (= 42 px) covers:
    #   - V+ outer crossing GND inner (old case)
    #   - GND_left → col 'j' of the I2C alt layout (long inter-tie-strip path)
    #   - GND_right → col 'a' (mirror equivalent)
    if distance <= 42:
        return [rail_xy, target_xy]   # short path, no intermediate hole

    # Deviation: passes through the row gap BELOW the row (between row N and
    # N+1) — visually more sober than the deviation above, and always
    # in a hole-free zone.
    deviation_y = ry + 14
    delta = 8                         # lateral offset before/after the deviation
    dir_x = 1 if tx > rx else -1
    return [
        rail_xy,
        (rx + dir_x * delta, ry),
        (rx + dir_x * delta, deviation_y),
        (tx - dir_x * delta, deviation_y),
        (tx - dir_x * delta, ty),
        target_xy,
    ]


# ─── Main API ──────────────────────────────────────────────────────
def route_wires(scene: PlacedScene, netlist_components: list[dict]) -> list[Wire]:
    """Computes the wires for the wired scene.

    - Signal nets: 1 wire per consumer (Arduino -> col 'a' of the component)
    - Power nets : 1 wire Arduino -> rail + 1 jumper rail -> each consumer
    """
    placed_by_ref: dict[str, PlacedComponent] = {
        pc.component_ref: pc for pc in scene.placed_components
    }

    # Identifies THE external batteries (off-BB). Several if the inference
    # split the netlist due to incompatible voltages (cf
    # _split_battery_for_voltage_compat).
    batteries = [pc for pc in scene.placed_components
                  if pc.component_type == "battery_external"]
    battery = batteries[0] if batteries else None

    # Collects consumers by net (ON-BB components only; the
    # OFF-BB ones like the battery are handled separately).
    consumers: dict[str, list[tuple[PlacedComponent, int]]] = {}
    for comp in netlist_components:
        ref = comp["ref"]
        placed = placed_by_ref.get(ref)
        if placed is None or placed.breadboard_idx < 0:
            continue
        for pin in comp.get("pins", []):
            pin_name = pin["name"]
            net = pin["net"]
            pin_idx = _name_to_pin_index(placed.catalog_entry, pin_name)
            if pin_idx is None:
                continue
            consumers.setdefault(net, []).append((placed, pin_idx))

    # Total count of consumers per net (on-BB + off-BB excluding battery).
    # Used to decide whether a power net should go through the BB rail:
    # more than 1 consumer on a power net → single wire Arduino→rail + 1
    # jumper rail→pin per consumer (clean wiring convention).
    netlist_by_ref = {c["ref"]: c for c in netlist_components}
    total_consumers_per_net: dict[str, int] = {}
    for comp in netlist_components:
        if comp.get("type") == "battery_external":
            continue
        for pin in comp.get("pins", []):
            net = pin.get("net", "")
            if not net:
                continue
            total_consumers_per_net[net] = total_consumers_per_net.get(net, 0) + 1

    # Track counter per (component_ref, edge, kind) — to stagger
    # the lateral bypasses when several wires land on the same
    # face of the same off-BB driver. Separate power/signal counters to
    # avoid crossings between the 2 families. Declared here because shared
    # between the off-BB rail block (below) and the final off-BB routing block.
    off_bb_target_tracks: dict[tuple[str, str, str], int] = {}

    # Off-BB pins that must be routed via the BB rail (instead of a
    # direct wire Arduino → off-BB): power net AND total consumers >= 2.
    off_bb_rail_routed: set[tuple[str, int]] = set()
    off_bb_via_rail_by_net: dict[str, list[tuple[PlacedComponent, int]]] = {}
    for placed_off in scene.placed_components:
        if placed_off.breadboard_idx >= 0:
            continue
        if placed_off.component_type == "battery_external":
            continue
        comp_off = netlist_by_ref.get(placed_off.component_ref)
        if comp_off is None:
            continue
        for pin in comp_off.get("pins", []):
            net = pin.get("net", "")
            if net not in _POWER_NETS:
                continue
            if total_consumers_per_net.get(net, 0) < 2:
                continue
            pin_idx = _name_to_pin_index(placed_off.catalog_entry, pin["name"])
            if pin_idx is None:
                continue
            off_bb_rail_routed.add((placed_off.component_ref, pin_idx))
            off_bb_via_rail_by_net.setdefault(net, []).append((placed_off, pin_idx))

    # Colors: we pre-allocate for all used nets (on-BB consumers
    # AND off-BB pins), otherwise the purely off-BB internal nets (e.g.
    # NET_A between L298N and dc_motor, both off-BB) would be absent from
    # net_colors and would fall back to _net_color(net, 0) = palette[0] = blue.
    signal_idx = 0
    net_colors: dict[str, str] = {}

    def _allocate_color(net: str) -> str:
        nonlocal signal_idx
        if net in net_colors:
            return net_colors[net]
        if net in _POWER_NETS:
            net_colors[net] = _NET_POWER_COLORS[net]
        else:
            net_colors[net] = _net_color(net, signal_idx)
            signal_idx += 1
        return net_colors[net]

    for net in consumers:
        _allocate_color(net)
    # Adds the nets of the off-BB pins (drivers, motors) so they have
    # a distinct color. Stable order = order of the placed components.
    for placed_off in scene.placed_components:
        if placed_off.breadboard_idx >= 0:
            continue
        comp_off = next(
            (c for c in netlist_components
             if c["ref"] == placed_off.component_ref),
            None,
        )
        if comp_off is None:
            continue
        for pin in comp_off.get("pins", []):
            net = pin.get("net", "")
            if net:
                _allocate_color(net)

    wires: list[Wire] = []
    # Distinct tracks:
    # - lane_track[corridor]            : lane_y index, unique per corridor (top/bot)
    # - side_track[side]                : source bypass index, per side (left/right Arduino)
    # - target_track[(bb_idx, corridor)] : target bypass index, per BB+corridor (safe zone near the target)
    lane_track_top = 0
    lane_track_bot = 0
    side_track_left = 0
    side_track_right = 0
    target_track_table: dict[tuple[int, str], int] = {}

    def _next_lane_track(corridor: str) -> int:
        nonlocal lane_track_top, lane_track_bot
        if corridor == "top":
            t = lane_track_top
            lane_track_top += 1
            return t
        t = lane_track_bot
        lane_track_bot += 1
        return t

    def _next_side_track(side: str) -> int:
        nonlocal side_track_left, side_track_right
        if side == "right":
            t = side_track_right
            side_track_right += 1
            return t
        t = side_track_left
        side_track_left += 1
        return t

    def _next_target_track(bb_idx: int, corridor: str) -> int:
        key = (bb_idx, corridor)
        t = target_track_table.get(key, 0)
        target_track_table[key] = t + 1
        return t

    # 0) Battery-supplied power nets (alt scheme: battery_external component
    #    present off-BB, e.g. above the Arduino). The battery powers
    #    some consumers (typically the servos) via the OUTER V+ rail
    #    (opposite the Arduino one) of the host BB. Mark these consumers
    #    to exclude them from the Arduino power routing.
    battery_handled: set[tuple[str, int]] = set()
    # Battery variables hoisted to the function scope for reuse
    # by the off-BB pass below (L298N/ULN2003 drivers powered by BAT_5V).
    # In case of several batteries (= incompatible voltage split), we keep
    # a net+ → battery info map for the later off-BB routing.
    bat_plus_xy: tuple[float, float] | None = None
    bat_minus_xy: tuple[float, float] | None = None
    bat_plus_net: str | None = None
    bat_minus_net: str | None = None
    bbs_used_bat: list[int] = []
    bat_info_by_plus_net: dict[str, dict] = {}
    # BBs where a battery has its '-' on the GND_bat-side rail → we will add
    # below an intra-BB jumper GND_bat-side ↔ GND_arduino-side to
    # ensure electrical continuity with the Arduino GND.
    bbs_needing_gnd_bridge: set[int] = set()
    for battery in batteries:
        bat_plus_pin_idx = next(
            (idx for idx, lab in battery.catalog_entry.pin_labels.items() if lab == "+"),
            1,
        )
        bat_minus_pin_idx = next(
            (idx for idx, lab in battery.catalog_entry.pin_labels.items() if lab == "-"),
            2,
        )
        bat_plus_xy = _component_pin_canvas(scene, battery, bat_plus_pin_idx)
        bat_minus_xy = _component_pin_canvas(scene, battery, bat_minus_pin_idx)

        # Net names from netlist for battery + and -
        for c in netlist_components:
            if c["ref"] == battery.component_ref:
                for pin in c.get("pins", []):
                    if pin["name"] == "+":
                        bat_plus_net = pin["net"]
                    elif pin["name"] == "-":
                        bat_minus_net = pin["net"]
                break

        board_x = scene.board_translate[0]
        # Override the color of the battery + net to clearly distinguish it from
        # the Arduino 5V. We also write it into net_colors so the
        # rail→consumer jumpers (using net_colors[bat_plus_net]) inherit
        # this color.
        bat_color = _BATTERY_PLUS_COLOR
        if bat_plus_net:
            net_colors[bat_plus_net] = bat_color

        # Process battery + power net : route battery+ → outer V+ rail
        #                                 → consumers on those BBs.
        if bat_plus_net and bat_plus_net in consumers and bat_plus_xy is not None:
            conn_list_bat = consumers[bat_plus_net]
            bbs_used_bat = sorted({pc.breadboard_idx for pc, _ in conn_list_bat
                                     if pc.breadboard_idx >= 0})
            for bb_idx in bbs_used_bat:
                bb_translate_x = scene.breadboard_translates[bb_idx][0]
                arduino_side = "left" if bb_translate_x > board_x else "right"
                bat_side = "right" if arduino_side == "left" else "left"

                # battery + → outer V+ rail at row 1, via the top lane
                # corridor (above the BB body) to avoid crossing the BB.
                rail_top_xy = _bb_rail_canvas(scene, bb_idx, "V+", bat_side,
                                              RAIL_CONNECTION_ROW)
                lane_y_plus = scene.lane_y_top_base -_next_lane_track("top") * LANE_Y_STEP
                wires.append(Wire(
                    net=bat_plus_net, color=bat_color,
                    path=[bat_plus_xy, (bat_plus_xy[0], lane_y_plus),
                          (rail_top_xy[0], lane_y_plus), rail_top_xy],
                ))

                # Jumpers outer V+ rail → each consumer
                for placed, pin_idx in conn_list_bat:
                    if placed.breadboard_idx != bb_idx:
                        continue
                    battery_handled.add((placed.component_ref, pin_idx))
                    wire_entry_xy = _component_wire_entry(scene, placed, pin_idx)
                    if wire_entry_xy is None:
                        continue
                    _, hole_row = placed.pin_to_hole[pin_idx]
                    rail_jump_xy = _bb_rail_canvas(scene, bb_idx, "V+",
                                                    bat_side, hole_row)
                    wires.append(Wire(
                        net=bat_plus_net, color=bat_color,
                        path=_jumper_path(rail_jump_xy, wire_entry_xy,
                                          "V+", bat_side, hole_row),
                    ))

        # Fallback: if the bat+ has no on-BB consumer (typical case
        # when all consumers are off-BB, e.g. L298N driver
        # powered by battery), bbs_used_bat is empty and the bat- would not
        # be traced. We fall back to the BBs of the on-BB GND consumers
        # (typically a button or other component using the ground) to
        # guarantee that a common battery/Arduino GND rail exists.
        if not bbs_used_bat and "GND" in consumers:
            bbs_used_bat = sorted({pc.breadboard_idx for pc, _ in consumers["GND"]
                                    if pc.breadboard_idx >= 0})

        # Battery - → rail GND_<bat_side> row 1 of the host BB. R7-1 STRICT:
        # first row = mandatory vertical arrival (descent on
        # rail_col). The electrical continuity with the Arduino GND is
        # ensured by the intra-BB jumper GND_bat-side ↔ GND_arduino-side
        # added below (cf block 1e).
        if bat_minus_xy is not None and bbs_used_bat:
            target_bb = bbs_used_bat[0]
            bb_translate_x = scene.breadboard_translates[target_bb][0]
            arduino_side = "left" if bb_translate_x > board_x else "right"
            bat_side = "right" if arduino_side == "left" else "left"
            bat_minus_row = 1
            rail_xy = _bb_rail_canvas(scene, target_bb, "GND", bat_side,
                                      bat_minus_row)
            lane_y_minus = scene.lane_y_top_base -_next_lane_track("top") * LANE_Y_STEP
            wires.append(Wire(
                net=bat_minus_net or "GND",
                color=_NET_POWER_COLORS.get("GND", "#222222"),
                path=[bat_minus_xy,
                      (bat_minus_xy[0], lane_y_minus),
                      (rail_xy[0], lane_y_minus),
                      rail_xy],
            ))
            bbs_needing_gnd_bridge.add(target_bb)

        # Memorizes the battery info for the later off-BB routing
        # (final pass, wire bat+ → off-BB pin direct via lane).
        if bat_plus_net and bat_plus_xy is not None:
            bat_info_by_plus_net[bat_plus_net] = {
                "battery_pc": battery,
                "bat_plus_xy": bat_plus_xy,
                "bat_minus_xy": bat_minus_xy,
                "bat_plus_net": bat_plus_net,
                "color": bat_color,
            }

    # 1) Power nets: Arduino -> primary BB rail (top, row 1)
    #                 + bridge primary BB -> other BBs (bottom, row N) — reproduces
    #                   the physical wiring: a single wire leaves the Arduino pin,
    #                   the following BBs are daisy-chained from the 1st.
    #                 + jumpers rail -> each consumer on its own BB.
    for net, conn_list in consumers.items():
        if net not in _POWER_NETS:
            continue

        board_fn = _resolve_board_pin(scene.board_loader, net)
        if board_fn is None:
            continue

        rail_kind = _NET_TO_RAIL[net]
        bbs_used = sorted({pc.breadboard_idx for pc, _ in conn_list})
        board_xy = _board_pin_canvas(scene, board_fn)
        side = _board_pin_side(scene, board_xy)
        board_x = scene.board_translate[0]

        # 1a) Arduino -> primary BB rail (1st BB of bbs_used)
        primary_bb = bbs_used[0]
        primary_x = scene.breadboard_translates[primary_bb][0]
        primary_rail_side = "left" if primary_x > board_x else "right"
        primary_rail_top_xy = _bb_rail_canvas(
            scene, primary_bb, rail_kind, primary_rail_side, RAIL_CONNECTION_ROW
        )
        wires.append(Wire(
            net=net, color=net_colors[net],
            path=_path_around_board(board_xy, primary_rail_top_xy, scene, side,
                                     lane_track=_next_lane_track("top"),
                                     side_track=_next_side_track(side),
                                     descent_at_target=True,
                                     corridor="top"),
        ))

        # 1b) Bridge primary BB -> other BBs (from the bottom to the bottom)
        if len(bbs_used) > 1:
            primary_rows = scene.breadboards[primary_bb].rows
            # Second-to-last row: avoids the last one (often obstructed
            # by the SVG edge and harder to read visually).
            primary_bridge_row = primary_rows - 1
            primary_rail_bottom_xy = _bb_rail_canvas(
                scene, primary_bb, rail_kind, primary_rail_side, primary_bridge_row
            )
            canvas_h = scene.canvas_size[1]
            for other_bb in bbs_used[1:]:
                other_x = scene.breadboard_translates[other_bb][0]
                other_rail_side = "left" if other_x > board_x else "right"
                other_rows = scene.breadboards[other_bb].rows
                other_bridge_row = other_rows - 1
                other_rail_bottom_xy = _bb_rail_canvas(
                    scene, other_bb, rail_kind, other_rail_side, other_bridge_row
                )
                # Lateral exit (8 px) before the descent: avoids
                # overlap at the rail's plumb point with other
                # wires of the same net (intra-BB GND bridge etc.).
                sx, sy = primary_rail_bottom_xy
                ex, ey = other_rail_bottom_xy
                dx_start = 8 if ex > sx else -8
                dx_end = -dx_start
                lane_y = canvas_h - LANE_Y_BASE_TOP + _next_lane_track("bottom") * LANE_Y_STEP
                wires.append(Wire(
                    net=net, color=net_colors[net],
                    path=[
                        primary_rail_bottom_xy,
                        (sx + dx_start, sy),
                        (sx + dx_start, lane_y),
                        (ex + dx_end, lane_y),
                        (ex + dx_end, ey),
                        other_rail_bottom_xy,
                    ],
                ))

        # 1c) Jumpers rail -> each consumer on its own BB
        for bb_idx in bbs_used:
            bb_translate_x = scene.breadboard_translates[bb_idx][0]
            rail_side = "left" if bb_translate_x > board_x else "right"
            for placed, pin_idx in conn_list:
                if placed.breadboard_idx != bb_idx:
                    continue
                wire_entry_xy = _component_wire_entry(scene, placed, pin_idx)
                if wire_entry_xy is None:
                    continue
                _, hole_row = placed.pin_to_hole[pin_idx]
                rail_jump_xy = _bb_rail_canvas(scene, bb_idx, rail_kind, rail_side, hole_row)
                wires.append(Wire(
                    net=net, color=net_colors[net],
                    path=_jumper_path(rail_jump_xy, wire_entry_xy, rail_kind, rail_side, hole_row),
                ))

    # 1d) Multi-consumer power nets: route the OFF-BB pins via the BB
    #     rail rather than via direct wires Arduino → off-BB. Clean
    #     wiring convention: a single wire leaves the Arduino pin toward the rail,
    #     each consumer (on-BB or off-BB) taps the rail as close as possible.
    #     If the net has no on-BB consumer, we also create the Arduino → rail
    #     injector manually (otherwise the previous block already did it).
    for net, off_pins in off_bb_via_rail_by_net.items():
        if net not in _POWER_NETS:
            continue
        rail_kind = _NET_TO_RAIL[net]
        board_fn = _resolve_board_pin(scene.board_loader, net)
        if board_fn is None:
            continue

        # Primary BB choice: same logic as the on-BB block if applicable,
        # otherwise BB 0 by default.
        on_bb_consumers = consumers.get(net, [])
        if on_bb_consumers:
            primary_bb = sorted({pc.breadboard_idx for pc, _ in on_bb_consumers})[0]
        else:
            primary_bb = 0
        primary_x_bb = scene.breadboard_translates[primary_bb][0]
        board_x = scene.board_translate[0]
        primary_rail_side = "left" if primary_x_bb > board_x else "right"

        # Stagger of the lateral exit/arrival X on this rail: each wire
        # (injector + jumpers) takes a progressive offset (8, 13, 18, ...)
        # to prevent their vertical segments above the rail from
        # overlapping.
        rail_lateral_track = 0

        def _next_rail_lateral_delta() -> float:
            nonlocal rail_lateral_track
            d = 8 + rail_lateral_track * 5
            rail_lateral_track += 1
            return d

        # Arduino → rail injector if not already created by the on-BB block.
        # LATERAL approach to the rail hole (BB convention: no direct
        # vertical descent into a hole). bypass_x_target_override forces
        # the final horizontal segment.
        if not on_bb_consumers:
            board_xy = _board_pin_canvas(scene, board_fn)
            side = _board_pin_side(scene, board_xy)
            primary_rail_top_xy = _bb_rail_canvas(
                scene, primary_bb, rail_kind, primary_rail_side, RAIL_CONNECTION_ROW
            )
            # Approach from the board side (= opposite rail_side)
            inj_dir = 1 if scene.board_translate[0] > primary_rail_top_xy[0] else -1
            inj_arrival_x = primary_rail_top_xy[0] + inj_dir * _next_rail_lateral_delta()
            wires.append(Wire(
                net=net, color=net_colors[net],
                path=_path_around_board(
                    board_xy, primary_rail_top_xy, scene, side,
                    lane_track=_next_lane_track("top"),
                    side_track=_next_side_track(side),
                    descent_at_target=False,
                    corridor="top",
                    bypass_x_target_override=inj_arrival_x,
                ),
            ))

        # For each off-BB consumer: 1 jumper rail → off-BB pin.
        # LATERAL exit from the rail hole (staggered) then vertical climb toward
        # the lane corridor, then approach to the off-BB pin (lateral if LEFT/RIGHT).
        # Rail row allocated incrementally (RAIL_CONNECTION_ROW reserved for
        # the Arduino injector).
        next_rail_row = RAIL_CONNECTION_ROW + 1
        for placed_off, pin_idx in off_pins:
            off_pin_xy = _component_pin_canvas(scene, placed_off, pin_idx)
            if off_pin_xy is None:
                continue
            rail_xy = _bb_rail_canvas(
                scene, primary_bb, rail_kind, primary_rail_side, next_rail_row
            )
            next_rail_row += 1

            lane_y = scene.lane_y_top_base - _next_lane_track("top") * LANE_Y_STEP
            # Staggered lateral exit from the rail toward the off-BB driver side.
            exit_dir = 1 if off_pin_xy[0] > rail_xy[0] else -1
            rail_exit_x = rail_xy[0] + exit_dir * _next_rail_lateral_delta()
            # Lateral bypass for off-BB driver pin (LEFT/RIGHT). Power pin
            # by construction (filter off_bb_rail_routed) → small detour.
            tgt_edge = _off_bb_pin_edge(placed_off, off_pin_xy)
            tgt_bypass_x: float | None = None
            if tgt_edge in ("left", "right"):
                key = (placed_off.component_ref, tgt_edge, "power")
                track = off_bb_target_tracks.get(key, 0)
                off_bb_target_tracks[key] = track + 1
                tgt_bypass_x = _off_bb_lateral_bypass_x(
                    placed_off, tgt_edge, track, kind="power"
                )

            if tgt_bypass_x is not None:
                path = [rail_xy,
                        (rail_exit_x, rail_xy[1]),
                        (rail_exit_x, lane_y),
                        (tgt_bypass_x, lane_y),
                        (tgt_bypass_x, off_pin_xy[1]),
                        off_pin_xy]
            else:
                path = [rail_xy,
                        (rail_exit_x, rail_xy[1]),
                        (rail_exit_x, lane_y),
                        (off_pin_xy[0], lane_y),
                        off_pin_xy]
            wires.append(Wire(net=net, color=net_colors[net], path=path))

    # 1e) Intra-BB jumper GND_bat-side ↔ GND_arduino-side, for each BB
    #     where a battery has its '-' on the bat-side rail. Ensures the
    #     electrical continuity with the Arduino GND (which lands on
    #     arduino-side) via a short wire at the bottom of the BB.
    #     R7-1 STRICT (first/last row of the rail = mandatory vertical
    #     arrival): tap on row N (= last row) → pure vertical
    #     descent on rail_col at both ends.
    canvas_h = scene.canvas_size[1]
    for bb_idx in sorted(bbs_needing_gnd_bridge):
        bb_translate_x = scene.breadboard_translates[bb_idx][0]
        arduino_side = "left" if bb_translate_x > board_x else "right"
        bat_side = "right" if arduino_side == "left" else "left"
        rows = scene.breadboards[bb_idx].rows
        bridge_row = rows
        start_xy = _bb_rail_canvas(scene, bb_idx, "GND", bat_side, bridge_row)
        end_xy = _bb_rail_canvas(scene, bb_idx, "GND", arduino_side, bridge_row)
        lane_y = canvas_h - LANE_Y_BASE_TOP + _next_lane_track("bottom") * LANE_Y_STEP
        sx, sy = start_xy
        ex, ey = end_xy
        wires.append(Wire(
            net="GND",
            color=_NET_POWER_COLORS.get("GND", "#222222"),
            path=[
                start_xy,
                (sx, lane_y),
                (ex, lane_y),
                end_xy,
            ],
        ))

    # 2) I2C bus: we identify the consumers by their component pin
    #    (SDA or SCL), separated by bus. Depending on the number of consumers
    #    and the number of physical pins available on the board:
    #    - Strategy A (n ≤ available pins): 1 dedicated wire per consumer
    #      toward a distinct pin (uses SDA and A4 for example on UNO).
    #    - Strategy B (n > available pins): "virtual rail" tie-strip on
    #      the host BB — Arduino → tie-strip (1 wire) then tie-strip →
    #      each consumer (short jumper per device).
    i2c_by_bus: dict[str, list[tuple[PlacedComponent, int, str]]] = {}
    for net, conn_list in consumers.items():
        if net in _POWER_NETS:
            continue
        for placed, pin_idx in conn_list:
            pin_name = placed.catalog_entry.pin_labels.get(pin_idx, "")
            if pin_name in _I2C_PIN_NAMES:
                i2c_by_bus.setdefault(pin_name, []).append((placed, pin_idx, net))

    # Track of the consumers already handled in I2C to exclude them from the
    # standard signal routing.
    i2c_handled: set[tuple[str, int]] = set()

    for bus, items in i2c_by_bus.items():
        physical_pins = _i2c_physical_pins(scene.board_loader, bus)
        if not physical_pins:
            continue
        n = len(items)
        primary_net = items[0][2]
        bus_color = net_colors.get(primary_net, "#888888")

        if n <= len(physical_pins):
            # Strategy A: 1 dedicated wire per consumer, distinct physical pin
            for (placed, pin_idx, net), pin_name in zip(items, physical_pins):
                i2c_handled.add((placed.component_ref, pin_idx))
                board_xy = scene.board_loader.pin_position(
                    pin_name, scene.board_translate
                )
                wire_entry_xy = _component_wire_entry(scene, placed, pin_idx)
                if wire_entry_xy is None:
                    continue
                _, target_row = placed.pin_to_hole[pin_idx]
                bb = scene.breadboards[placed.breadboard_idx]
                corridor = _choose_corridor(target_row, bb.rows)
                board_pin_side = _board_pin_side(scene, board_xy)
                wires.append(Wire(
                    net=net, color=bus_color,
                    path=_path_around_board(
                        board_xy, wire_entry_xy, scene, board_pin_side,
                        lane_track=_next_lane_track(corridor),
                        side_track=_next_side_track(board_pin_side),
                        target_track=_next_target_track(placed.breadboard_idx, corridor),
                        corridor=corridor),
                ))
        else:
            # Strategy B: tie-strip rail on the host BB, using the
            # tie-strip opposite the one where the I2C components are placed
            # (components on col 'g' BB1 or col 'd' BB0 — cf I2C alt layout).
            bb_counts: dict[int, int] = {}
            for placed, _, _ in items:
                bb_counts[placed.breadboard_idx] = bb_counts.get(placed.breadboard_idx, 0) + 1
            host_bb_idx = max(bb_counts, key=bb_counts.get)
            bb = scene.breadboards[host_bb_idx]
            host_x = scene.breadboard_translates[host_bb_idx][0]
            is_left_bb = host_x < scene.board_translate[0]
            # Bus entry col for Arduino: on the tie-strip opposite the components.
            # Non-mirror: components on col 'g' (right ts), bus on cols a-e ⇒ entry 'a'.
            # Mirror    : components on col 'd' (left ts), bus on cols f-j ⇒ entry 'j'.
            entry_col = "j" if is_left_bb else "a"

            # Bus rows centered on the I2C components: SDA takes the
            # median row, SCL the next one (the 2 are on distinct tie-strips).
            host_components = [p for p, _, _ in items if p.breadboard_idx == host_bb_idx]
            sda_row, scl_row = _i2c_bus_rows(host_bb_idx, host_components)
            bus_row = sda_row if bus == "SDA" else scl_row

            # 1) Arduino → bus tie-strip (1 single wire for the whole bus)
            first_pin = physical_pins[0]
            board_xy = scene.board_loader.pin_position(
                first_pin, scene.board_translate
            )
            bus_xy = _bb_hole_canvas(scene, host_bb_idx, entry_col, bus_row)
            board_pin_side = _board_pin_side(scene, board_xy)
            corridor = _choose_corridor(bus_row, bb.rows)
            wires.append(Wire(
                net=primary_net, color=bus_color,
                path=_path_around_board(
                    board_xy, bus_xy, scene, board_pin_side,
                    lane_track=_next_lane_track(corridor),
                    side_track=_next_side_track(board_pin_side),
                    target_track=_next_target_track(host_bb_idx, corridor),
                    corridor=corridor),
            ))

            # 2) Bus tie-strip → each consumer via the central channel.
            jumper_idx = 0
            for placed, pin_idx, net in items:
                i2c_handled.add((placed.component_ref, pin_idx))
                if placed.breadboard_idx != host_bb_idx:
                    continue
                _, consumer_row = placed.pin_to_hole[pin_idx]
                wires.append(Wire(
                    net=net, color=bus_color,
                    path=_i2c_jumper_path(
                        scene, host_bb_idx, jumper_idx,
                        bus_row, consumer_row, mirrored=is_left_bb,
                        bus=bus,
                    ),
                ))
                jumper_idx += 1

    # 3) Standard signal nets: Arduino → col 'a' of the component (except I2C already handled).
    # Dedup per tie-strip: if several consumers share the same tie-strip
    # (= same bb_idx + same left/right side + same row), a single wire suffices
    # to connect them electrically (typical case: Btn.A and R.B pullup
    # sharing the D11 net on cols 'c' and 'd' of the same row).
    def _tiestrip_key(placed_, pin_idx_):
        col_, row_ = placed_.pin_to_hole[pin_idx_]
        if col_ in ("a", "b", "c", "d", "e"):
            return (placed_.breadboard_idx, "L", row_)
        if col_ in ("f", "g", "h", "i", "j"):
            return (placed_.breadboard_idx, "R", row_)
        return (placed_.breadboard_idx, col_, row_)   # rail = no dedup

    for net, conn_list in consumers.items():
        if net in _POWER_NETS:
            continue
        board_fn = _resolve_board_pin(scene.board_loader, net)
        if board_fn is None:
            continue
        board_xy = _board_pin_canvas(scene, board_fn)
        side = _board_pin_side(scene, board_xy)

        seen_tiestrips: set = set()
        for placed, pin_idx in conn_list:
            if (placed.component_ref, pin_idx) in i2c_handled:
                continue
            ts_key = _tiestrip_key(placed, pin_idx)
            if ts_key in seen_tiestrips:
                continue   # tie-strip already served by another consumer
            seen_tiestrips.add(ts_key)
            wire_entry_xy = _component_wire_entry(scene, placed, pin_idx)
            if wire_entry_xy is None:
                continue
            _, target_row = placed.pin_to_hole[pin_idx]
            bb = scene.breadboards[placed.breadboard_idx]
            corridor = _choose_corridor(target_row, bb.rows)
            wires.append(Wire(
                net=net, color=net_colors[net],
                path=_path_around_board(board_xy, wire_entry_xy, scene, side,
                                         lane_track=_next_lane_track(corridor),
                                         side_track=_next_side_track(side),
                                         target_track=_next_target_track(placed.breadboard_idx, corridor),
                                         corridor=corridor),
            ))

    # ─── Routing of the OFF-BB pins (drivers, motors, battery) ─────────────
    # With the drivers (L298N, ULN2003) now placed off-BB like the
    # motors and the battery, their pins are not in `consumers` (which
    # only collects the on-BB pins). We route them here by classifying
    # each pin according to its net:
    #   1) Arduino net (5V/GND/D6/A0/...): route Arduino board pin → off-BB
    #   2) BAT_5V net (carried by battery+): route battery+ → off-BB
    #   3) Internal net (NET_X): find the other endpoint (off-BB or on-BB)
    #      and route between the two via the upper lane corridor
    # (netlist_by_ref is computed above, during the pre-pass)

    # List of the off-BB pins (excluding battery) with ref/pin_idx/net.
    off_bb_pins: list[tuple[PlacedComponent, int, str]] = []
    for placed_off in scene.placed_components:
        if placed_off.breadboard_idx >= 0:
            continue
        if placed_off.component_type == "battery_external":
            continue
        comp = netlist_by_ref.get(placed_off.component_ref)
        if comp is None:
            continue
        for pin in comp.get("pins", []):
            net = pin.get("net", "")
            if not net:
                continue
            pin_idx = _name_to_pin_index(placed_off.catalog_entry, pin["name"])
            if pin_idx is None:
                continue
            off_bb_pins.append((placed_off, pin_idx, net))

    # Tracker to avoid tracing the same internal net twice between
    # two off-BB pins (1 wire suffices, not one per direction).
    off_to_off_done: set[tuple[str, str]] = set()

    def _claim_bypass_x(placed: PlacedComponent,
                        pin_idx: int,
                        pin_xy: tuple[float, float]) -> float | None:
        """If the pin is LEFT/RIGHT, reserves a track and returns the lateral
        bypass X outside the body. The power pins (VCC/GND/VIN/...) receive
        a small detour; the signal pins (IN/OUT/EN/...) a large detour.
        Separate counters per kind to avoid crossings. Returns None
        for the TOP/BOTTOM pins (vertical descent at the pin X)."""
        edge = _off_bb_pin_edge(placed, pin_xy)
        if edge not in ("left", "right"):
            return None
        kind = "power" if _is_off_bb_power_pin(placed, pin_idx) else "signal"
        key = (placed.component_ref, edge, kind)
        track = off_bb_target_tracks.get(key, 0)
        off_bb_target_tracks[key] = track + 1
        return _off_bb_lateral_bypass_x(placed, edge, track, kind=kind)

    for placed_off, pin_idx, net in off_bb_pins:
        off_pin_xy = _component_pin_canvas(scene, placed_off, pin_idx)
        if off_pin_xy is None:
            continue

        # 1) Net carried by an Arduino pin (power 5V/GND/3V3/VIN or
        #    signal D0-D13/A0-A5): source = Arduino pin, route via lane
        #    corridor. For a LEFT/RIGHT pin of an off-BB driver, lateral
        #    approach (bypass outside the body); otherwise vertical descent.
        board_fn = _resolve_board_pin(scene.board_loader, net)
        if board_fn is not None:
            # If this pin is already routed via the BB rail (multi-consumer
            # power net), we skip the direct route Arduino → off-BB.
            if (placed_off.component_ref, pin_idx) in off_bb_rail_routed:
                continue
            board_xy = _board_pin_canvas(scene, board_fn)
            side = _board_pin_side(scene, board_xy)
            color = net_colors[net]
            tgt_bypass_x = _claim_bypass_x(placed_off, pin_idx, off_pin_xy)
            # Same-side: Arduino pin and off-BB pin on the same side (left/left or
            # right/right) → we skip the lane and the source bypass, direct
            # descent to the X of the target bypass.
            tgt_edge = _off_bb_pin_edge(placed_off, off_pin_xy)
            is_same_side = (tgt_bypass_x is not None
                            and tgt_edge in ("left", "right")
                            and tgt_edge == side)
            wires.append(Wire(
                net=net, color=color,
                path=_path_around_board(
                    board_xy, off_pin_xy, scene, side,
                    lane_track=(0 if is_same_side else _next_lane_track("top")),
                    side_track=_next_side_track(side),
                    target_track=0,
                    descent_at_target=(tgt_bypass_x is None),
                    corridor="top",
                    bypass_x_target_override=tgt_bypass_x,
                    same_side=is_same_side,
                ),
            ))
            continue

        # 2) Net = bat+ of a battery (typically BAT_5V / BAT_5V_2):
        #    source = + pin of this battery. Lateral approach if the target
        #    pin is LEFT/RIGHT.
        if net in bat_info_by_plus_net:
            info = bat_info_by_plus_net[net]
            bat_plus_xy_local = info["bat_plus_xy"]
            lane_y = scene.lane_y_top_base -_next_lane_track("top") * LANE_Y_STEP
            color = net_colors.get(net) or info["color"]
            tgt_bypass_x = _claim_bypass_x(placed_off, pin_idx, off_pin_xy)
            if tgt_bypass_x is not None:
                path = [bat_plus_xy_local,
                        (bat_plus_xy_local[0], lane_y),
                        (tgt_bypass_x, lane_y),
                        (tgt_bypass_x, off_pin_xy[1]),
                        off_pin_xy]
            else:
                path = [bat_plus_xy_local,
                        (bat_plus_xy_local[0], lane_y),
                        (off_pin_xy[0], lane_y),
                        off_pin_xy]
            wires.append(Wire(net=net, color=color, path=path))
            continue

        # 3) Internal net (NET_X) or other non-Arduino net: find the other
        #    endpoint. Priority to another off-BB pin (driver→motor); by
        #    default an on-BB pin (driver→component on BB).
        target_off = None
        for o2_placed, o2_pin_idx, o2_net in off_bb_pins:
            if o2_net != net:
                continue
            if (o2_placed.component_ref == placed_off.component_ref
                    and o2_pin_idx == pin_idx):
                continue
            target_off = (o2_placed, o2_pin_idx)
            break

        if target_off is not None:
            # Off-BB ↔ Off-BB. Dedupe: a single pair of refs per net.
            o2_placed, o2_pin_idx = target_off
            pair_key = (net, "|".join(sorted(
                [placed_off.component_ref, o2_placed.component_ref]
            )))
            if pair_key in off_to_off_done:
                continue
            off_to_off_done.add(pair_key)
            target_xy = _component_pin_canvas(scene, o2_placed, o2_pin_idx)
            if target_xy is None:
                continue
            lane_y = scene.lane_y_top_base -_next_lane_track("top") * LANE_Y_STEP
            color = net_colors[net]
            # Lateral bypass if source and/or target pin is LEFT/RIGHT (and signal).
            src_bypass_x = _claim_bypass_x(placed_off, pin_idx, off_pin_xy)
            tgt_bypass_x = _claim_bypass_x(o2_placed, o2_pin_idx, target_xy)
            src_x = src_bypass_x if src_bypass_x is not None else off_pin_xy[0]
            tgt_x = tgt_bypass_x if tgt_bypass_x is not None else target_xy[0]
            path = [off_pin_xy]
            if src_bypass_x is not None:
                path.append((src_x, off_pin_xy[1]))
            path.append((src_x, lane_y))
            path.append((tgt_x, lane_y))
            if tgt_bypass_x is not None:
                path.append((tgt_x, target_xy[1]))
            path.append(target_xy)
            wires.append(Wire(net=net, color=color, path=path))
            continue

        # Fallback: on-BB endpoint on the same net (e.g.: OUT pin of the
        # off-BB driver → on-BB component). Prior existing behavior.
        target_placed = None
        target_pin_idx = None
        for c2 in netlist_components:
            if c2["ref"] == placed_off.component_ref:
                continue
            placed2 = placed_by_ref.get(c2["ref"])
            if placed2 is None or placed2.breadboard_idx < 0:
                continue
            for p2 in c2.get("pins", []):
                if p2.get("net") == net:
                    target_placed = placed2
                    target_pin_idx = _name_to_pin_index(
                        placed2.catalog_entry, p2["name"]
                    )
                    break
            if target_placed is not None:
                break
        if target_placed is None or target_pin_idx is None:
            continue
        entry_xy = _component_wire_entry(scene, target_placed, target_pin_idx)
        if entry_xy is None:
            continue
        lane_y = scene.lane_y_top_base -_next_lane_track("top") * LANE_Y_STEP
        t = _next_target_track(target_placed.breadboard_idx, "top")
        half_track = t // 2
        offset = half_track * STAGGER_STEP
        if t % 2 == 0:
            bypass_x = entry_xy[0] - BYPASS_LATERAL_TARGET - offset
        else:
            bypass_x = entry_xy[0] + BYPASS_LATERAL_TARGET + offset
        color = net_colors.get(net) or _net_color(net, 0)
        net_colors.setdefault(net, color)
        wires.append(Wire(
            net=net, color=color,
            path=[off_pin_xy,
                  (off_pin_xy[0], lane_y),
                  (bypass_x, lane_y),
                  (bypass_x, entry_xy[1]),
                  entry_xy],
        ))

    return wires
