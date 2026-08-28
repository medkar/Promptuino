"""Router v3 — scene -> Wire list orchestrator via A* on grid.

Phase 2: routes SIMPLE scenes (1 BB, no off-BB, no battery) via A* on grid.
For any other scene, fallback v2.

Internal pipeline (simple scenes):
  1. build_occupancy_grid(scene, netlist)
  2. extract_net_endpoints(...)
  3. allocate_colors(...)
  4. Net order: power first, then signals
  5. For each net, for each (source, target) -> A* + Wire
  6. mark_wire in the grid after each placement (for same-net sharing
     and inter-net blocking)
  7. If a net fails -> global v2 fallback (Phase 2; rip-up arrives Phase 5)
"""
from __future__ import annotations

import numpy as np

from ..layout.routing import (
    Wire, _NET_PALETTE, _NET_POWER_COLORS, _net_color, _POWER_NETS,
)

from .astar import astar, compress_collinear
from .grid import OccupancyGrid
from .occupancy import (
    build_occupancy_grid, extract_net_endpoints, power_rail_for_net,
)


DEFAULT_CELL_SIZE = 6
# Strong per-turn penalty: avoids the staircases and down-right-up detours
# that A* took to pass through low-cost cells (allow zones). 2000 (vs 50
# initially) guarantees that a turn costs more than a long straight segment
# through hole_line_cost (60/cell), so A* prefers direct paths with few
# turns.
DEFAULT_TURN_PENALTY = 2000
# Expansion limit per A* call. Beyond it we consider the routing failed and
# fall back to v2 (or during phase 5 we'll do rip-up). Chosen so a standard
# canvas (~200x200 cells) finishes in < 2s on interpreted Python.
DEFAULT_MAX_EXPANSIONS = 2_000_000


_I2C_PIN_NAMES = {"SDA", "SCL"}
_I2C_PHYSICAL_PINS_FOR_BUS: dict[str, list[str]] = {
    "SDA": ["SDA", "A4"],
    "SCL": ["SCL", "A5"],
}


def _i2c_physical_pins(board_loader, bus: str) -> list[str]:
    """Physical board pins for the requested I2C bus, ordered by preference.
    Filters out pins that don't exist on the board."""
    return [p for p in _I2C_PHYSICAL_PINS_FOR_BUS.get(bus, [])
            if board_loader.has_pin(p)]


def _i2c_bus_rows(host_consumers, default=(1, 2)) -> tuple[int, int]:
    """Rows of the 2 I2C bus tie-strips (SDA then SCL), centered on the rows
    occupied by the host BB's I2C consumers. Direct port of
    `layout.routing._i2c_bus_rows`."""
    all_rows: list[int] = []
    seen: set[str] = set()
    for placed in host_consumers:
        if placed.component_ref in seen:
            continue
        seen.add(placed.component_ref)
        for _, r in placed.pin_to_hole.values():
            all_rows.append(r)
    if not all_rows:
        return default
    center = (min(all_rows) + max(all_rows)) // 2
    return (center, center + 1)


def _is_simple_scene(scene) -> bool:
    """True (always).

    v3 handles all scenes. The v2 fallback is FORBIDDEN (cf
    feedback_no_v2_fallback). Multi-BB included — when v3 can't route a
    net, it logs the failure and skips, but never falls back to v2.
    """
    return True


def _identify_resistor_color_aliases(netlist_components) -> dict[str, str]:
    """Detects series R to propagate color through them.

    For each resistor with 2 pins:
      - if one pin is on an "outer" net (appears nowhere else in the
        netlist = lone Arduino signal, e.g. D13) and the other on an
        "inner" net (shared with a main component, e.g. LED.A via NET_LR)
      - then the inner net inherits the color of the outer net
        (= electrically the R doesn't break the signal color)

    Returns: {inner_net: outer_net} for propagation.
    """
    net_to_comps: dict[str, set[str]] = {}
    for c in netlist_components:
        for pin in c.get("pins", []):
            net = pin.get("net", "")
            if net:
                net_to_comps.setdefault(net, set()).add(c["ref"])

    alias: dict[str, str] = {}
    for c in netlist_components:
        if c.get("type") != "resistor":
            continue
        pins = c.get("pins", [])
        if len(pins) != 2:
            continue
        net_a = pins[0].get("net", "")
        net_b = pins[1].get("net", "")
        if not net_a or not net_b:
            continue
        comps_a = net_to_comps.get(net_a, set())
        comps_b = net_to_comps.get(net_b, set())
        # Outer = present only on this R. Inner = shared with another comp.
        # Skip if outer is a power net (5V/GND/...): it's a pullup (or
        # pulldown) R, not a series R. Propagating the power color to the
        # signal would give a red/black signal wire instead of a distinct
        # signal color.
        if comps_a == {c["ref"]} and len(comps_b) > 1 and net_a not in _POWER_NETS:
            alias[net_b] = net_a
        elif comps_b == {c["ref"]} and len(comps_a) > 1 and net_b not in _POWER_NETS:
            alias[net_a] = net_b
    return alias


def _allocate_colors(netlist_components) -> dict[str, str]:
    """Allocates one color per net. Reuses the v2 logic:
       - power nets (5V/3V3/GND/VIN) -> fixed colors
       - other nets -> cyclic signal palette
       - series R: propagates the outer net color to the inner net
    """
    aliases = _identify_resistor_color_aliases(netlist_components)
    colors: dict[str, str] = {}
    signal_idx = 0
    # First pass: native colors for the NON-aliased nets (= outer or power or
    # independent). Aliased (inner) nets are skipped to avoid consuming a
    # useless signal_idx.
    for comp in netlist_components:
        for pin in comp.get("pins", []):
            net = pin.get("net", "")
            if not net or net in colors:
                continue
            if net in aliases:
                continue   # handled in 2nd pass
            if net in _NET_POWER_COLORS:
                colors[net] = _NET_POWER_COLORS[net]
            else:
                colors[net] = _net_color(net, signal_idx)
                signal_idx += 1
    # Second pass: propagate the outer net color to the inner ones.
    for inner_net, outer_net in aliases.items():
        if outer_net in colors:
            colors[inner_net] = colors[outer_net]
    return colors


def _remove_u_turns(cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Removes A-B-A (U-turn) patterns from a list of cells.

    A U-turn appears at the JUNCTION points between A* and a fixed descent
    (R6: A* + descent to row 1; R7 corner: descent + A*). If A* approaches
    the junction point from the same direction the descent exits, we get
    A* ending with (col, r+1)->(col, r) and descent restarting with
    (col, r+1): a wasted visit of (col, r) that would be rendered as a
    weird corner + diagonal segment (the renderer assumes axis-aligned
    segments, which isn't true after compressing a U-turn).

    The algorithm: detect cells[i] == cells[i+2] (= U-turn with apex
    cells[i+1]), remove cells[i+1] AND cells[i+2] (the return cell).
    Iterate until stable.
    """
    out = list(cells)
    changed = True
    while changed:
        changed = False
        for i in range(len(out) - 2):
            if out[i] == out[i + 2]:
                del out[i + 1:i + 3]
                changed = True
                break
    return out


def _cells_to_canvas_path(cells: list[tuple[int, int]],
                          grid: OccupancyGrid,
                          start_canvas: tuple[float, float] | None = None,
                          end_canvas: tuple[float, float] | None = None,
                          ) -> list[tuple[float, float]]:
    """Converts an A* path (cells) into a Wire path (canvas).

    Compresses the collinear segments then replaces the first and last
    point with the exact pin canvas coords (if provided).

    Anti-diagonal: when the snap moves path[0] (exact pin canvas) out of
    alignment with path[1]'s cell center, the segment becomes diagonal.
    We fix this by SHIFTING path[1] (the first corner) on the axis
    perpendicular to the first segment, so it aligns with path[0]. That
    way the first segment stays straight. The second segment has its
    length adjusted by ±1-2 px (no visual impact).

    This approach avoids inserting 1-2 px MICRO-SEGMENTS that create
    rounding artifacts at render time (arc radius > segment length).
    """
    if not cells:
        return []
    compressed = compress_collinear(cells)
    path: list[tuple[float, float]] = [
        grid.cell_to_canvas(c, r) for c, r in compressed
    ]

    # Snap start with orthogonal alignment
    if start_canvas is not None and len(path) >= 1:
        path[0] = start_canvas
        if len(compressed) >= 2:
            c0, r0 = compressed[0]
            c1, r1 = compressed[1]
            if r0 == r1:
                # First segment H (equal rows) -> shift path[1]'s Y to path[0]'s Y
                path[1] = (path[1][0], path[0][1])
            elif c0 == c1:
                # First segment V -> shift path[1]'s X to path[0]'s X
                path[1] = (path[0][0], path[1][1])

    # Snap end with orthogonal alignment
    if end_canvas is not None and len(path) >= 1:
        path[-1] = end_canvas
        if len(compressed) >= 2:
            cN, rN = compressed[-1]
            cP, rP = compressed[-2]
            if rN == rP:
                # Last segment H -> shift path[-2]'s Y to path[-1]'s Y
                path[-2] = (path[-2][0], path[-1][1])
            elif cN == cP:
                # Last segment V -> shift path[-2]'s X to path[-1]'s X
                path[-2] = (path[-1][0], path[-2][1])

    return path


# Lateral stub (px) inserted at the exit/entry of a BB endpoint to enforce
# Rule 3: a wire doesn't plunge straight down into a hole, it first makes a
# small horizontal corner.
HORIZONTAL_STUB_PX = 8.0


def _rail_cells_for_rail_id(scene, grid: OccupancyGrid, bb_idx: int,
                              rail_id: str,
                              rows: range | None = None
                              ) -> list[tuple[tuple[int, int], tuple[float, float]]]:
    """Returns [(cell, canvas), ...] for all the holes of an explicit BB
    rail (for example 'GND_left'). Generalization of `_rail_cells_for_net`
    when a non-default rail is needed (cf. R8: battery-side GND rail,
    opposite the Arduino-side rail).
    """
    bb = scene.breadboards[bb_idx]
    bb_tx, bb_ty = scene.breadboard_translates[bb_idx]
    out: list[tuple[tuple[int, int], tuple[float, float]]] = []
    iter_rows = rows if rows is not None else range(1, bb.rows + 1)
    for row in iter_rows:
        try:
            cx, cy = bb.hole_position(rail_id, row)
        except (KeyError, ValueError):
            continue
        canvas_xy = (cx + bb_tx, cy + bb_ty)
        cell = grid.canvas_to_cell(*canvas_xy)
        out.append((cell, canvas_xy))
    return out


def _rail_cells_for_net(scene, grid: OccupancyGrid, net: str,
                          rows: range | None = None
                          ) -> list[tuple[tuple[int, int], tuple[float, float]]]:
    """Returns [(cell, canvas), ...] for all the holes of the BB rail
    assigned to `net`. Empty list if non-rail net. Used by the Phase 3
    rail-tap routing.

    `rows`: restricts to a subset of rows. None = all (1..bb.rows).
    """
    info = power_rail_for_net(scene, net)
    if info is None:
        return []
    bb_idx, rail_id = info
    return _rail_cells_for_rail_id(scene, grid, bb_idx, rail_id, rows=rows)


def _wire_owner_cells(grid: OccupancyGrid, net_id: int
                        ) -> list[tuple[int, int]]:
    """All cells already occupied by a wire of the net (col, row)."""
    rows, cols = np.where(grid.wire_owner == net_id)
    return list(zip(cols.tolist(), rows.tolist()))


def _is_bb_endpoint(scene, canvas_xy: tuple[float, float],
                    tolerance_px: float = 4.0) -> bool:
    """True if the canvas position is inside (or flush against) a BB."""
    cx, cy = canvas_xy
    for i, bb in enumerate(scene.breadboards):
        bb_x, bb_y = scene.breadboard_translates[i]
        bb_w, bb_h = bb.size
        if (bb_x - tolerance_px <= cx <= bb_x + bb_w + tolerance_px
                and bb_y - tolerance_px <= cy <= bb_y + bb_h + tolerance_px):
            return True
    return False


def _insert_horizontal_stubs(path: list[tuple[float, float]],
                              scene,
                              grid: OccupancyGrid | None = None,
                              net_id: int = 0,
                              stub_px: float = HORIZONTAL_STUB_PX
                              ) -> list[tuple[float, float]]:
    """Inserts a small horizontal corner at the exit/entry of BB endpoints
    if the first/last segment of the path is purely vertical.

    Rule 3: a wire exiting/entering a BB hole must do so laterally (= not
    plunge straight in). This function doesn't touch non-BB endpoints
    (Arduino, off-BB) which exit naturally through a vertical channel
    (carve_channel for Arduino, tail for DC motor).

    If `grid` is provided, we check that the stub corner cell isn't blocked
    (body_mask=1 or pin_owner != net_id). If the suggested direction is
    blocked, we try the opposite; if both are blocked, we skip the stub
    (= no alternative R3 violation).
    """
    if len(path) < 2:
        return path
    out = list(path)

    def _stub_blocked(x_endpoint: float, stub_x: float,
                        y_endpoint: float) -> bool:
        """True if one of the cells between (x_endpoint, y_endpoint) and
        (stub_x, y_endpoint) (= horizontal segment of the stub) is
        body_mask=1 without being an endpoint of the current net."""
        if grid is None:
            return False
        lo_x, hi_x = sorted((x_endpoint, stub_x))
        _, row = grid.canvas_to_cell(stub_x, y_endpoint)
        if not (0 <= row < grid.rows):
            return True
        col_lo, _ = grid.canvas_to_cell(lo_x, y_endpoint)
        col_hi, _ = grid.canvas_to_cell(hi_x, y_endpoint)
        for col in range(col_lo, col_hi + 1):
            if not (0 <= col < grid.cols):
                return True
            if grid.body_mask[row, col] == 1:
                po = int(grid.pin_owner[row, col])
                if po == 0 or po != net_id:
                    return True
        return False

    def _pick_stub_dir(x_endpoint: float, y_endpoint: float,
                        prefer_dir: int) -> int | None:
        """Chooses the stub direction. We try ONLY prefer_dir (= the
        direction of the incoming wire). If blocked, we skip the stub
        (= vertical entry accepted) rather than create a detour through the
        opposite side (= visual "hook" reversed relative to the wire
        direction)."""
        stub_x = x_endpoint + prefer_dir * stub_px
        if _stub_blocked(x_endpoint, stub_x, y_endpoint):
            return None
        return prefer_dir

    # ── Start stub ──
    if _is_bb_endpoint(scene, out[0]):
        x0, y0 = out[0]
        x1, y1 = out[1]
        if x0 == x1 and y0 != y1:
            # Preferred direction: follows the next point non-collinear in X
            prefer = 1
            for i in range(2, len(out)):
                if out[i][0] != x0:
                    prefer = 1 if out[i][0] > x0 else -1
                    break
            stub_dir = _pick_stub_dir(x0, y0, prefer)
            if stub_dir is not None:
                stub_x = x0 + stub_dir * stub_px
                out[1] = (stub_x, y1)
                out.insert(1, (stub_x, y0))

    # ── End stub (symmetric) ──
    if _is_bb_endpoint(scene, out[-1]):
        xE, yE = out[-1]
        xP, yP = out[-2]
        if xE == xP and yE != yP:
            prefer = 1
            for i in range(len(out) - 3, -1, -1):
                if out[i][0] != xE:
                    prefer = 1 if out[i][0] > xE else -1
                    break
            stub_dir = _pick_stub_dir(xE, yE, prefer)
            if stub_dir is not None:
                stub_x = xE + stub_dir * stub_px
                out[-2] = (stub_x, yP)
                out.insert(-1, (stub_x, yE))

    return out


# ─── R8: External battery + GND rail bridge ────────────────────────────
# When a `battery_external` is present, R8-2 requires the '-' pin to be
# routed onto the GND rail OPPOSITE the Arduino (= same side as the battery
# V+). R8-3 requires an extra wire connecting the 2 GND rails along the
# bottom of the BB, on the last row. These helpers prepare the needed info
# and build the bridge wire.

def _external_batteries_info(scene, netlist_components, grid: OccupancyGrid):
    """Multi-battery: for each `battery_external` in the netlist, computes
    its routing info (host BB + bat_side + endpoints + rail cells).

    Returns `dict[plus_net, info]`. Each info contains:
      - battery_ref
      - bat_plus_cell, bat_plus_canvas, bat_minus_cell, bat_minus_canvas
      - arduino_side, bat_side (relative to the host BB)
      - bb_idx: host BB (= BB with on-BB consumers of `plus_net`, else BB
        of the GND consumers, else BB 0)
      - bat_plus_rail_id, bat_plus_rail_cells_with_canvas (V+_<bat_side>)
      - bat_gnd_rail_id, bat_gnd_rail_cells_with_canvas (GND_<bat_side>)
      - plus_net: name of the battery '+' net

    Filters out batteries with no '+' pin, no existing bat-side rail, etc.
    """
    from .occupancy import _endpoint_canvas, _name_to_pin_index

    # consumers_by_net: net → set(bb_idx) of the on-BB components that consume
    # this net. Lets us determine each battery's host BB from its '+'.
    consumers_by_net: dict[str, set[int]] = {}
    placed_by_ref = {pc.component_ref: pc for pc in scene.placed_components}
    for c in netlist_components:
        ref = c.get("ref")
        placed = placed_by_ref.get(ref) if ref else None
        if placed is None or placed.breadboard_idx < 0:
            continue
        for p in c.get("pins", []):
            net = p.get("net")
            if net:
                consumers_by_net.setdefault(net, set()).add(placed.breadboard_idx)

    board_x = scene.board_translate[0]
    infos: dict[str, dict] = {}

    for c in netlist_components:
        if c.get("type") != "battery_external":
            continue
        bat_ref = c.get("ref")
        plus_net = None
        for p in c.get("pins", []):
            if p.get("name") == "+":
                plus_net = p.get("net")
                break
        if not plus_net:
            continue
        bat_placed = placed_by_ref.get(bat_ref) if bat_ref else None
        if bat_placed is None:
            continue
        plus_idx = _name_to_pin_index(bat_placed.catalog_entry, "+")
        minus_idx = _name_to_pin_index(bat_placed.catalog_entry, "-")
        if plus_idx is None or minus_idx is None:
            continue
        plus_xy = _endpoint_canvas(scene, bat_placed, plus_idx)
        minus_xy = _endpoint_canvas(scene, bat_placed, minus_idx)
        if plus_xy is None or minus_xy is None:
            continue

        # Host BB: 1st BB with an on-BB consumer of `+`, else GND, else 0.
        bbs_used = sorted(consumers_by_net.get(plus_net, set()))
        if not bbs_used:
            bbs_used = sorted(consumers_by_net.get("GND", set()))
        host_bb_idx = bbs_used[0] if bbs_used else 0

        bb_x = scene.breadboard_translates[host_bb_idx][0]
        arduino_side = "left" if bb_x > board_x else "right"
        bat_side = "right" if arduino_side == "left" else "left"

        bat_plus_rail_id = f"V+_{bat_side}"
        bat_gnd_rail_id = f"GND_{bat_side}"
        plus_rail_cells = _rail_cells_for_rail_id(scene, grid, host_bb_idx,
                                                    bat_plus_rail_id)
        gnd_rail_cells = _rail_cells_for_rail_id(scene, grid, host_bb_idx,
                                                   bat_gnd_rail_id)
        if not plus_rail_cells or not gnd_rail_cells:
            continue

        infos[plus_net] = {
            "battery_ref": bat_ref,
            "bat_plus_cell": grid.canvas_to_cell(*plus_xy),
            "bat_plus_canvas": plus_xy,
            "bat_minus_cell": grid.canvas_to_cell(*minus_xy),
            "bat_minus_canvas": minus_xy,
            "arduino_side": arduino_side,
            "bat_side": bat_side,
            "bb_idx": host_bb_idx,
            "bat_plus_rail_id": bat_plus_rail_id,
            "bat_plus_rail_cells_with_canvas": plus_rail_cells,
            "bat_gnd_rail_id": bat_gnd_rail_id,
            "bat_gnd_rail_cells_with_canvas": gnd_rail_cells,
            "plus_net": plus_net,
        }

    return infos


def _external_battery_plus_info(scene, netlist_components, grid: OccupancyGrid):
    """If a `battery_external` is in the netlist + its '+' pin has a usable
    canvas position, returns a dict with:
      - bat_plus_cell, bat_plus_canvas: A* endpoint of the '+' pin
      - arduino_side, bat_side: 'left'/'right'
      - bb_idx: host BB
      - bat_plus_rail_id: 'V+_<bat_side>'
      - bat_plus_rail_cells_with_canvas: holes of the battery-side V+ rail

    Returns None if no battery_external, no resolvable '+' pin, or no
    bat-side V+ rail. Cf. R8-4/R8-5.
    """
    from .occupancy import _endpoint_canvas, _name_to_pin_index
    bat_comp = None
    for c in netlist_components:
        if c.get("type") == "battery_external":
            bat_comp = c
            break
    if bat_comp is None:
        return None
    bat_placed = None
    for pc in scene.placed_components:
        if pc.component_ref == bat_comp["ref"]:
            bat_placed = pc
            break
    if bat_placed is None:
        return None
    plus_pin_idx = _name_to_pin_index(bat_placed.catalog_entry, "+")
    if plus_pin_idx is None:
        return None
    plus_xy = _endpoint_canvas(scene, bat_placed, plus_pin_idx)
    if plus_xy is None:
        return None
    plus_cell = grid.canvas_to_cell(*plus_xy)
    primary_bb_idx = 0
    bb_x = scene.breadboard_translates[primary_bb_idx][0]
    board_x = scene.board_translate[0]
    arduino_side = "left" if bb_x > board_x else "right"
    bat_side = "right" if arduino_side == "left" else "left"
    bat_plus_rail_id = f"V+_{bat_side}"
    bat_plus_rail_cells = _rail_cells_for_rail_id(scene, grid, primary_bb_idx,
                                                    bat_plus_rail_id)
    if not bat_plus_rail_cells:
        return None
    return {
        "bat_plus_cell": plus_cell,
        "bat_plus_canvas": plus_xy,
        "arduino_side": arduino_side,
        "bat_side": bat_side,
        "bb_idx": primary_bb_idx,
        "bat_plus_rail_id": bat_plus_rail_id,
        "bat_plus_rail_cells_with_canvas": bat_plus_rail_cells,
    }


def _external_battery_gnd_info(scene, netlist_components, grid: OccupancyGrid):
    """If a `battery_external` is in the netlist + its '-' pin has a usable
    canvas position, returns a dict with:
      - bat_minus_cell, bat_minus_canvas: A* endpoint of the '-' pin
      - arduino_side, bat_side: 'left'/'right'
      - bb_idx: host BB
      - bat_rail_cells_with_canvas: holes of the battery-side GND rail
        (= rail opposite the Arduino, same format as _rail_cells_for_net)

    Returns None if no battery_external, no resolvable '-' pin, or no
    bat-side rail on the BB.
    """
    from .occupancy import _endpoint_canvas, _name_to_pin_index
    bat_comp = None
    for c in netlist_components:
        if c.get("type") == "battery_external":
            bat_comp = c
            break
    if bat_comp is None:
        return None

    # Locate the PlacedComponent + '-' pin
    bat_placed = None
    for pc in scene.placed_components:
        if pc.component_ref == bat_comp["ref"]:
            bat_placed = pc
            break
    if bat_placed is None:
        return None
    minus_pin_idx = _name_to_pin_index(bat_placed.catalog_entry, "-")
    if minus_pin_idx is None:
        return None
    minus_xy = _endpoint_canvas(scene, bat_placed, minus_pin_idx)
    if minus_xy is None:
        return None
    minus_cell = grid.canvas_to_cell(*minus_xy)

    # Determine sides (cf. power_rail_for_net): Arduino-side rail = side of
    # the BB facing the board. bat_side = opposite.
    primary_bb_idx = 0
    bb_x = scene.breadboard_translates[primary_bb_idx][0]
    board_x = scene.board_translate[0]
    arduino_side = "left" if bb_x > board_x else "right"
    bat_side = "right" if arduino_side == "left" else "left"
    bat_rail_id = f"GND_{bat_side}"

    bat_rail_cells = _rail_cells_for_rail_id(scene, grid, primary_bb_idx,
                                              bat_rail_id)
    if not bat_rail_cells:
        return None

    return {
        "bat_minus_cell": minus_cell,
        "bat_minus_canvas": minus_xy,
        "arduino_side": arduino_side,
        "bat_side": bat_side,
        "bb_idx": primary_bb_idx,
        "bat_rail_id": bat_rail_id,
        "bat_rail_cells_with_canvas": bat_rail_cells,
    }


def _build_gnd_bridge_wire(scene, grid: OccupancyGrid, net_id: int,
                             color: str,
                             arduino_rail_row_n: tuple[tuple[int, int], tuple[float, float]],
                             bat_rail_row_n: tuple[tuple[int, int], tuple[float, float]],
                             bb_idx: int,
                             turn_penalty: int,
                             ):
    """R8-3: builds the bridge wire GND_<arduino_side> row N <->
    GND_<bat_side> row N, passing UNDER the BB.

    Deterministic geometry:
      1) vertical descent on arduino_rail_col, from the row N hole to a row
         ~12 px below the BB (R7-1 row N exception: no hole below)
      2) horizontal A* between the 2 columns (= crosses under the BB)
      3) vertical ascent on bat_rail_col, up to the bat-side row N hole

    Returns (Wire, full_cells) or None if A* fails.
    """
    arduino_cell, arduino_canvas = arduino_rail_row_n
    bat_cell, bat_canvas = bat_rail_row_n
    bb = scene.breadboards[bb_idx]
    _bb_tx, bb_ty = scene.breadboard_translates[bb_idx]
    bb_h = bb.size[1]

    arduino_col = arduino_cell[0]
    bat_col = bat_cell[0]
    row_n = arduino_cell[1]  # same as bat_cell[1] (same row N)

    # "Below the BB" cell on the Arduino-side rail column.
    below_canvas_y = bb_ty + bb_h + 12.0
    arduino_below_cell = grid.canvas_to_cell(arduino_canvas[0], below_canvas_y)
    bat_below_cell = grid.canvas_to_cell(bat_canvas[0], below_canvas_y)
    # A* must be able to start/end on free cells. If the descent passes
    # through row > row_n, we build the descent cells by hand (= inverted
    # R7-1).
    descent_cells: list[tuple[int, int]] = []
    for r in range(row_n + 1, arduino_below_cell[1] + 1):
        descent_cells.append((arduino_col, r))
    ascent_cells: list[tuple[int, int]] = []
    for r in range(bat_below_cell[1] - 1, row_n, -1):
        ascent_cells.append((bat_col, r))

    # A* between the 2 below-cells (free, under the BB)
    cells_mid = astar(grid, [arduino_below_cell], [bat_below_cell], net_id,
                      turn_penalty=turn_penalty,
                      max_expansions=DEFAULT_MAX_EXPANSIONS)
    if cells_mid is None:
        return None

    full_cells = _remove_u_turns(
        [arduino_cell] + descent_cells + cells_mid[1:-1] + [bat_below_cell] + ascent_cells + [bat_cell]
    )
    path = _cells_to_canvas_path(full_cells, grid,
                                   start_canvas=arduino_canvas,
                                   end_canvas=bat_canvas)
    # No _insert_horizontal_stubs: the path starts and ends with a vertical
    # segment (descent row N -> under BB / ascent under BB -> row N).
    # R7-1 row N: direct descent on rail_col allowed.
    return Wire(net="GND", color=color, path=path), full_cells


def _build_cross_bb_power_bridge_wire(scene, grid: OccupancyGrid,
                                       net_id: int, net: str, color: str,
                                       primary_rail_cell_canvas,
                                       primary_bb_idx: int,
                                       other_rail_cell_canvas,
                                       other_bb_idx: int,
                                       turn_penalty: int,
                                       stagger_primary: bool = False,
                                       stagger_other: bool = False,
                                       ):
    """Inter-BB bridge for a power net (5V, GND) with consumers on several
    BBs. Connects the arduino-side rail of the primary BB to the
    arduino-side rail of the other BB, passing UNDER the BBs.

    R7-1 STRICT: the descent under the BB is done vertically PLUMB with
    rail_col (no stagger) when the tap is on row N or row 1 (last/first
    row). The 1-cell stagger is applied ONLY on the BB side where the tap
    row is mid-row (N-1) AND where another vertical descent on the same
    rail_col (typically intra-BB R8-3 on row N) would cause an overlap.

    `stagger_primary`/`stagger_other`: True if the corresponding BB has an
    intra-BB descent on the same col that occupies the rows below the tap
    (= battery-on-this-BB case).

    Returns (Wire, full_cells) or None if the horizontal A* fails.
    """
    pcell, pcanvas = primary_rail_cell_canvas
    ocell, ocanvas = other_rail_cell_canvas
    pbb = scene.breadboards[primary_bb_idx]
    obb = scene.breadboards[other_bb_idx]
    _pt, p_ty = scene.breadboard_translates[primary_bb_idx]
    _ot, o_ty = scene.breadboard_translates[other_bb_idx]
    p_h = pbb.size[1]
    o_h = obb.size[1]
    below_canvas_y = max(p_ty + p_h, o_ty + o_h) + 12.0

    p_col = pcell[0]
    o_col = ocell[0]
    p_row = pcell[1]
    o_row = ocell[1]

    dx_p = (1 if o_col > p_col else -1) if stagger_primary else 0
    dx_o = (-1 if o_col > p_col else 1) if stagger_other else 0
    p_lateral_col = p_col + dx_p
    o_lateral_col = o_col + dx_o

    p_lateral_x = grid.cell_to_canvas(p_lateral_col, 0)[0]
    o_lateral_x = grid.cell_to_canvas(o_lateral_col, 0)[0]
    p_below_cell = grid.canvas_to_cell(p_lateral_x, below_canvas_y)
    o_below_cell = grid.canvas_to_cell(o_lateral_x, below_canvas_y)

    # Deterministic builds:
    #   pcell -> (p_lateral_col, p_row): lateral 1 cell
    #   (p_lateral_col, p_row) -> (p_lateral_col, below): vertical descent
    p_lateral_cell = (p_lateral_col, p_row)
    descent_p: list[tuple[int, int]] = []
    for r in range(p_row + 1, p_below_cell[1] + 1):
        descent_p.append((p_lateral_col, r))
    o_lateral_cell = (o_lateral_col, o_row)
    ascent_o: list[tuple[int, int]] = []
    for r in range(o_below_cell[1] - 1, o_row - 1, -1):
        ascent_o.append((o_lateral_col, r))

    # Horizontal A* between the 2 below cells (under the BBs, free lane).
    cells_mid = astar(grid, [p_below_cell], [o_below_cell], net_id,
                      turn_penalty=turn_penalty,
                      max_expansions=DEFAULT_MAX_EXPANSIONS)
    if cells_mid is None:
        return None

    raw_cells = (
        [pcell, p_lateral_cell] + descent_p
        + cells_mid[1:-1]
        + [o_below_cell] + ascent_o + [o_lateral_cell, ocell]
    )
    # Dedup consecutive (= stagger=False case or p_lateral_cell == pcell)
    deduped: list[tuple[int, int]] = []
    for c in raw_cells:
        if not deduped or deduped[-1] != c:
            deduped.append(c)
    full_cells = _remove_u_turns(deduped)
    path = _cells_to_canvas_path(full_cells, grid,
                                   start_canvas=pcanvas, end_canvas=ocanvas)
    return Wire(net=net, color=color, path=path), full_cells


def _preroute_i2c_buses(scene, netlist_components, grid: OccupancyGrid,
                          net_to_id, colors, turn_penalty: int):
    """Pre-routes the I2C buses (SDA, SCL) in strategy A or B.

    Strategy A (n consumers <= len(physical_pins)): 1 wire per consumer
    from a distinct physical board pin (SDA + A4 for SDA, SCL + A5 for
    SCL).

    Strategy B (n > len(physical_pins)): "virtual bus" on a tie-strip of
    the host BB. All cells of the bus row are marked pin_owner of the net
    (tie-strip = electrically equivalent). Arduino → 1 entry cell, then
    1 jumper per consumer from a distinct cell of the same row.

    Returns (wires, handled_targets, handled_nets):
      - wires: generated wires
      - handled_targets: set of (net, target_cell) already routed, to be
        skipped in the signal main loop
      - handled_nets: set of fully handled nets (to skip in the main loop,
        avoids double-emitting an Arduino→pin wire)
    """
    from .occupancy import _name_to_pin_index, _endpoint_canvas
    from collections import Counter

    # Build i2c_by_bus from the on-BB components
    i2c_by_bus: dict[str, list[tuple]] = {}
    netlist_by_ref = {c["ref"]: c for c in netlist_components if "ref" in c}
    for placed in scene.placed_components:
        if placed.breadboard_idx < 0:
            continue
        comp = netlist_by_ref.get(placed.component_ref)
        if comp is None:
            continue
        for pin_idx, label in placed.catalog_entry.pin_labels.items():
            if label not in _I2C_PIN_NAMES:
                continue
            pin_data = next((p for p in comp.get("pins", [])
                              if p.get("name") == label), None)
            if pin_data is None:
                continue
            net = pin_data.get("net", "")
            if not net:
                continue
            i2c_by_bus.setdefault(label, []).append((placed, pin_idx, net))

    wires: list[Wire] = []
    handled_targets: set[tuple[str, tuple[int, int]]] = set()
    handled_nets: set[str] = set()

    board_x = scene.board_translate[0]
    bx_min, by_min, bx_max, by_max = scene.board_loader.body_bbox(
        translate=scene.board_translate)

    for bus, items in i2c_by_bus.items():
        phys_pins = _i2c_physical_pins(scene.board_loader, bus)
        if not phys_pins:
            continue
        n = len(items)
        primary_net = items[0][2]
        bus_color = colors.get(primary_net, "#888")
        net_id = net_to_id.get(primary_net, 0)
        if net_id == 0:
            continue

        # Setup: occupancy step 6 has already set_pin + carved the Arduino
        # pin of `primary_net` (= e.g. "A4" for the SDA bus). But the OTHER
        # phys pins (e.g. "SDA" for the SDA bus) aren't set_pin'd →
        # body_mask=1 blocks an A* that would want to source there. We
        # set_pin + carve a channel toward the edge of the Arduino body for
        # each.
        for phys_pin in phys_pins:
            board_xy = scene.board_loader.pin_position(
                phys_pin, scene.board_translate)
            if board_xy is None:
                continue
            px, py = board_xy
            grid.set_pin(px, py, net_id, radius_cells=1)
            # Carve a channel toward the nearest edge of the Arduino body
            d_left = px - bx_min
            d_right = bx_max - px
            d_top = py - by_min
            d_bottom = by_max - py
            d_min = min(d_left, d_right, d_top, d_bottom)
            if d_min == d_left:
                exit_x, exit_y = bx_min - 2, py
            elif d_min == d_right:
                exit_x, exit_y = bx_max + 2, py
            elif d_min == d_top:
                exit_x, exit_y = px, by_min - 2
            else:
                exit_x, exit_y = px, by_max + 2
            grid.carve_channel(px, py, exit_x, exit_y, half_width=0)
            col_pin, row_pin = grid.canvas_to_cell(px, py)
            col_exit, row_exit = grid.canvas_to_cell(exit_x, exit_y)
            if abs(col_pin - col_exit) > abs(row_pin - row_exit):
                r_keep = row_pin
                c_lo, c_hi = min(col_pin, col_exit), max(col_pin, col_exit)
                for c in range(c_lo, c_hi + 1):
                    if 0 <= c < grid.cols and 0 <= r_keep < grid.rows:
                        grid.pin_owner[r_keep, c] = net_id
            else:
                c_keep = col_pin
                r_lo, r_hi = min(row_pin, row_exit), max(row_pin, row_exit)
                for r in range(r_lo, r_hi + 1):
                    if 0 <= c_keep < grid.cols and 0 <= r < grid.rows:
                        grid.pin_owner[r, c_keep] = net_id

        if n <= len(phys_pins):
            # Strategy A: 1 dedicated wire per consumer via a distinct phys pin.
            for (placed, pin_idx, net), pin_name in zip(items, phys_pins):
                target_xy = _endpoint_canvas(scene, placed, pin_idx)
                if target_xy is None:
                    continue
                target_cell = grid.canvas_to_cell(*target_xy)
                board_xy = scene.board_loader.pin_position(
                    pin_name, scene.board_translate)
                if board_xy is None:
                    continue
                src_cell = grid.canvas_to_cell(*board_xy)
                cells = astar(grid, [src_cell], [target_cell], net_id,
                                turn_penalty=turn_penalty,
                                max_expansions=DEFAULT_MAX_EXPANSIONS)
                if cells is None:
                    print(f"[v3 FAIL] I2C-A {bus}: {pin_name} -> "
                          f"target_cell={target_cell}")
                    continue
                path = _cells_to_canvas_path(cells, grid,
                                              start_canvas=board_xy,
                                              end_canvas=target_xy)
                path = _insert_horizontal_stubs(path, scene, grid=grid,
                                                  net_id=net_id)
                wires.append(Wire(net=net, color=bus_color, path=path))
                grid.mark_wire(cells, net_id)
                handled_targets.add((net, target_cell))
            handled_nets.add(primary_net)
        else:
            # Strategy B: bus tie-strip on the host BB.
            bb_counts = Counter(p.breadboard_idx for p, _, _ in items
                                  if p.breadboard_idx >= 0)
            if not bb_counts:
                continue
            host_bb_idx = bb_counts.most_common(1)[0][0]
            host_bb = scene.breadboards[host_bb_idx]
            host_tx, host_ty = scene.breadboard_translates[host_bb_idx]
            is_left_bb = host_tx < board_x

            # Bus tie-strip cols (= side opposite the consumers).
            # Non-mirror BB1 → consumers on right tie-strip (f-j) → bus on
            # left tie-strip (a-e). Mirror BB0 → reversed.
            # First col = Arduino entry (outermost col).
            if is_left_bb:
                bus_side_cols = ["j", "i", "h", "g", "f"]
            else:
                bus_side_cols = ["a", "b", "c", "d", "e"]

            # Bus row = centered on the consumers
            host_consumers = [p for p, _, _ in items
                                if p.breadboard_idx == host_bb_idx]
            sda_row, scl_row = _i2c_bus_rows(host_consumers,
                                                default=(1, 2))
            bus_row = sda_row if bus == "SDA" else scl_row

            # Pre-mark ONLY the cells actually used (entry + 1 per
            # consumer) on the bus tie-strip row. The OTHER cells (other
            # cols of the tie-strip at the same row) stay body_mask=1 →
            # A* can't cross them by going horizontally, which would force
            # the visual crossing of the tie-strip holes. With body_mask=1
            # on the unused cells, A* must EXIT vertically from the source
            # cell (= R3: short corner) then cross via a hole-free row.
            host_consumer_count = sum(
                1 for p, _, _ in items
                if p.breadboard_idx == host_bb_idx)
            n_needed = 1 + host_consumer_count
            if n_needed > len(bus_side_cols):
                print(f"[v3 FAIL] I2C-B {bus}: trop de consumers "
                      f"({host_consumer_count}) pour un seul tie-strip "
                      f"({len(bus_side_cols) - 1} jumpers max)")
                continue
            bus_cells: list[tuple[tuple[int, int], tuple[float, float]]] = []
            for col_id in bus_side_cols[:n_needed]:
                try:
                    cx_local, cy_local = host_bb.hole_position(col_id, bus_row)
                except (KeyError, ValueError):
                    continue
                cx_canvas = cx_local + host_tx
                cy_canvas = cy_local + host_ty
                grid.set_pin(cx_canvas, cy_canvas, net_id, radius_cells=0)
                bus_cells.append((grid.canvas_to_cell(cx_canvas, cy_canvas),
                                    (cx_canvas, cy_canvas)))

            if not bus_cells:
                continue

            # 1) Arduino phys pin → bus entry (1st col of the tie-strip)
            entry_cell, entry_xy = bus_cells[0]
            board_xy = scene.board_loader.pin_position(
                phys_pins[0], scene.board_translate)
            if board_xy is None:
                continue
            src_cell = grid.canvas_to_cell(*board_xy)
            cells = astar(grid, [src_cell], [entry_cell], net_id,
                            turn_penalty=turn_penalty,
                            max_expansions=DEFAULT_MAX_EXPANSIONS)
            if cells is None:
                print(f"[v3 FAIL] I2C-B {bus}: arduino "
                      f"{phys_pins[0]} -> bus entry {entry_cell}")
                continue
            path = _cells_to_canvas_path(cells, grid,
                                          start_canvas=board_xy,
                                          end_canvas=entry_xy)
            path = _insert_horizontal_stubs(path, scene, grid=grid,
                                              net_id=net_id)
            wires.append(Wire(net=primary_net, color=bus_color, path=path))
            grid.mark_wire(cells, net_id)

            # 2) For each consumer: bus_cells[i+1] → consumer
            jumper_cells = list(bus_cells[1:])
            for placed, pin_idx, net in items:
                if placed.breadboard_idx != host_bb_idx:
                    print(f"[v3 FAIL] I2C-B {bus}: consumer "
                          f"{placed.component_ref} on BB{placed.breadboard_idx} "
                          f"!= host BB{host_bb_idx}")
                    continue
                if not jumper_cells:
                    print(f"[v3 FAIL] I2C-B {bus}: plus de jumper cells "
                          f"libres pour {placed.component_ref}")
                    continue
                jumper_cell, jumper_xy = jumper_cells.pop(0)
                target_xy = _endpoint_canvas(scene, placed, pin_idx)
                if target_xy is None:
                    continue
                target_cell = grid.canvas_to_cell(*target_xy)
                cells = astar(grid, [jumper_cell], [target_cell], net_id,
                                turn_penalty=turn_penalty,
                                max_expansions=DEFAULT_MAX_EXPANSIONS)
                if cells is None:
                    print(f"[v3 FAIL] I2C-B {bus}: bus {jumper_cell} -> "
                          f"target_cell={target_cell}")
                    continue
                path = _cells_to_canvas_path(cells, grid,
                                              start_canvas=jumper_xy,
                                              end_canvas=target_xy)
                path = _insert_horizontal_stubs(path, scene, grid=grid,
                                                  net_id=net_id)
                wires.append(Wire(net=net, color=bus_color, path=path))
                grid.mark_wire(cells, net_id)
                handled_targets.add((net, target_cell))
            handled_nets.add(primary_net)

    return wires, handled_targets, handled_nets


def route_wires(scene, netlist_components,
                   cell_size: int = DEFAULT_CELL_SIZE,
                   turn_penalty: int = DEFAULT_TURN_PENALTY,
                   partial: bool = False):
    """Routes the wires of a scene via the v3 router.

    No more v2 fallback -- the migration of the prod pipeline to v3 is
    settled (cf feedback_no_v2_fallback). If A* fails on a net, we log the
    failure and skip the wire (to keep the partial render visible and not
    masked by a silent v2 re-route).

    `partial` is kept for API but no longer has any effect (the behavior is
    always "skip + log").

    Signature identical to `layout.routing.route_wires`.
    """
    # ─── Pipeline v3 ──────────────────────────────────────────────────────
    grid, net_to_id = build_occupancy_grid(
        scene, netlist_components, cell_size=cell_size
    )
    endpoints = extract_net_endpoints(scene, netlist_components, grid, net_to_id)
    colors = _allocate_colors(netlist_components)

    # Order: BAT_5V first (R8-4: otherwise the 5V wires occupy the lane
    # above the BB that BAT_5V must cross to reach V+_bat_side), then the
    # other power nets (5V, GND, etc.), then the signals.
    # All in stable alphabetical order at equal priority.
    def _sort_key(net: str) -> tuple[int, str]:
        # All bat+ nets (BAT_5V, BAT_5V_2, ...) before the other power
        # nets (cf R8-4: otherwise 5V/GND occupy the above-BB lane that
        # bat+ must cross to reach V+_bat_side).
        if net.startswith("BAT_"):
            return (0, net)
        if net in _POWER_NETS:
            return (1, net)
        return (2, net)
    nets_ordered = sorted(endpoints.keys(), key=_sort_key)

    wires: list[Wire] = []

    # Pre-route I2C buses (strategy A or B depending on consumer count)
    # BEFORE the main loop: otherwise the I2C nets would go to direct
    # routing (1 Arduino source, N targets) → N wires sharing the same
    # Arduino pin.
    i2c_wires, i2c_handled_targets, i2c_handled_nets = _preroute_i2c_buses(
        scene, netlist_components, grid, net_to_id, colors, turn_penalty)
    wires.extend(i2c_wires)

    # Cache of pin canvas for endpoint snapping
    source_canvas_per_net = _build_source_canvas_cache(scene, netlist_components,
                                                        endpoints)
    target_canvas_per_net_cell = _build_target_canvas_cache(scene, netlist_components,
                                                              endpoints, grid)

    # R8-4/R8-5: info to route each BAT_X+ onto its V+_<bat_side>
    # (host BB computed per battery). Pre-computed once.
    bat_infos_by_plus_net = _external_batteries_info(scene, netlist_components,
                                                       grid)

    # Counter to stagger the waypoint of the Arduino -> rail wires: each
    # wire (5V, GND, etc.) uses a unique vertical col and a unique
    # horizontal above-BB row to avoid overlap. The offset is in cells
    # (= cell_size px).
    arduino_rail_wire_idx = 0

    for net in nets_ordered:
        if net in i2c_handled_nets:
            continue   # I2C pre-route already done
        ne = endpoints[net]
        color = colors.get(net, "#888")

        # R8-4/R8-5: if net is a BAT_X+ + battery_external, we switch the
        # net onto the V+_<bat_side> rail of this battery's host BB + we
        # override the source so it's the battery's '+' pin (not the 1st
        # consumer found in the netlist). All the R6/R7 logic of the
        # rail-route block below then works.
        bat_plus_info_current = bat_infos_by_plus_net.get(net)
        is_bat_plus = bat_plus_info_current is not None
        if is_bat_plus:
            from .occupancy import NetEndpoints
            from ..layout.routing import _BATTERY_PLUS_COLOR
            rail_cells_with_canvas = bat_plus_info_current[
                "bat_plus_rail_cells_with_canvas"]
            rail_info_for_net = (bat_plus_info_current["bb_idx"],
                                  bat_plus_info_current["bat_plus_rail_id"])
            bat_plus_cell = bat_plus_info_current["bat_plus_cell"]
            all_pin_cells = list(ne.sources) + list(ne.targets)
            new_targets = [c for c in all_pin_cells if c != bat_plus_cell]
            ne = NetEndpoints(net=ne.net, net_id=ne.net_id,
                               sources=[bat_plus_cell], targets=new_targets)
            source_canvas_per_net[net] = bat_plus_info_current["bat_plus_canvas"]
            color = _BATTERY_PLUS_COLOR
        else:
            rail_cells_with_canvas = _rail_cells_for_net(scene, grid, net)
            rail_info_for_net = power_rail_for_net(scene, net)
        # Phase 3: for the power nets (= having an assigned rail), we route
        # Arduino -> rail tap (1 wire) then each consumer -> rail/wire
        # (1 jumper per consumer). Matches v2.layout.routing power block.
        use_rail = bool(rail_cells_with_canvas)

        if use_rail:
            rail_cells = [c for (c, _xy) in rail_cells_with_canvas]
            rail_canvas_by_cell = {c: xy for (c, xy) in rail_cells_with_canvas}
            # Set of cells of ALL rails of the same net (= cells with
            # pin_owner=net_id on the power strip). Used to prevent A* from
            # transiting mid-rail (cf. "come from above"): we pass
            # `extra_blocked = all_rail_cells - {desired_endpoint}` to each
            # A* that must enter/exit the rail. A* then forces the path to
            # detour through the free above/below BB lane.
            all_rail_cells_set = set(rail_cells)

            # 1) Arduino -> rail tap: the rule requires arriving at ROW 1
            # with a vertical descent from the top of the BB.
            # R7-1 exception: for row 1 (and row N), the rail column
            # CONTAINS NO OTHER HOLE ABOVE (row 1 = first hole). So
            # descending DIRECTLY on rail_col to the endpoint doesn't
            # violate R1 (no other hole crossed). This avoids the final
            # 1-cell horizontal corner that was placed on mid-row arrival.
            # row 1 = first element of rail_cells_with_canvas (always
            # iterate by increasing rows in _rail_cells_for_rail_id).
            row1_cell, row1_canvas = rail_cells_with_canvas[0]
            bb_idx_for_rail = rail_info_for_net[0]
            bb_tx, bb_ty = scene.breadboard_translates[bb_idx_for_rail]
            rail_col = row1_cell[0]
            # A* target = above the BB directly ON rail_col. No
            # parallel_col, no final jump.
            rail_canvas_x = grid.cell_to_canvas(rail_col, 0)[0]
            # Stagger above-BB row per wire (= 1 cell higher per following
            # wire) to avoid the overlap of the above-BB horizontals of 2
            # consecutive Arduino->rail wires.
            above_canvas = (rail_canvas_x,
                              bb_ty - 12.0 - arduino_rail_wire_idx * grid.cell_size)
            above_cell = grid.canvas_to_cell(*above_canvas)
            # Forced waypoint: Arduino exits HORIZONTALLY short (= just long
            # enough to clear the Arduino body, end of carve_channel) then
            # GOES UP VERTICALLY to above-BB. A* only does the HORIZONTAL
            # segment above the BB between waypoint and above_cell. Prevents
            # A* (with high turn_penalty) from preferring a long horizontal
            # in the Arduino-pin row through the BB cost zones.
            #
            # STAGGER: exit_x moves back 1 cell per following wire so that
            # no 2 Arduino->rail wires share their vertical col or their
            # above-BB horizontal row. 9 cells of gap are enough for 5V,
            # GND, BAT_5V (3 wires).
            arduino_pin_xy = source_canvas_per_net.get(net)
            waypoint_cells_pre: list[tuple[int, int]] = []
            astar_source_cells: list[tuple[int, int]] = list(ne.sources)
            if arduino_pin_xy is not None:
                from .occupancy import _resolve_board_pin
                bx_min, by_min, bx_max, by_max = scene.board_loader.body_bbox(
                    translate=scene.board_translate)
                board_fn = _resolve_board_pin(scene.board_loader, net)
                if board_fn is not None:
                    ax, ay = arduino_pin_xy
                    # Base margin: 8 px (~ 1 cell) between the Arduino body
                    # and the wire's vertical segment, so the exit
                    # horizontal is visually distinct (not flush against the
                    # body as in v2).
                    stagger_px = arduino_rail_wire_idx * grid.cell_size
                    base_margin_px = 8.0
                    # Horizontal exit: toward the BB (= opposite side from the Arduino)
                    bb_for_side_test = scene.breadboards[bb_idx_for_rail]
                    if ax > bb_tx + bb_for_side_test.size[0] / 2:
                        # Arduino on the right, exit toward the left, stagger
                        # progressively further left.
                        exit_x = bx_min - base_margin_px - stagger_px
                    else:
                        # Arduino on the left, exit toward the right, stagger
                        # progressively further right.
                        exit_x = bx_max + base_margin_px + stagger_px
                    waypoint_canvas = (exit_x, above_canvas[1])
                    waypoint_cell = grid.canvas_to_cell(*waypoint_canvas)
                    src_cell = grid.canvas_to_cell(ax, ay)
                    exit_cell = grid.canvas_to_cell(exit_x, ay)
                    # 1. Horizontal Arduino pin -> exit_cell (via carve channel
                    #    + free BB-Arduino gap)
                    step_h = 1 if exit_cell[0] > src_cell[0] else -1
                    horiz = [(c, src_cell[1])
                              for c in range(src_cell[0],
                                              exit_cell[0] + step_h, step_h)]
                    # 2. Vertical exit_cell -> waypoint_cell (free ascent)
                    step_v = 1 if waypoint_cell[1] > exit_cell[1] else -1
                    vert = [(exit_cell[0], r)
                             for r in range(exit_cell[1] + step_v,
                                             waypoint_cell[1] + step_v, step_v)]
                    waypoint_cells_pre = horiz + vert
                    astar_source_cells = [waypoint_cell]
                    arduino_rail_wire_idx += 1
            # extra_blocked: all rail cells except row 1 (= final endpoint,
            # reached via manual descent_cells right after). Forces A* to
            # detour around the rails through the free lane.
            cells = astar(grid, astar_source_cells, [above_cell], ne.net_id,
                          turn_penalty=turn_penalty,
                          max_expansions=DEFAULT_MAX_EXPANSIONS,
                          extra_blocked=all_rail_cells_set - {row1_cell})
            if cells is None:
                print(f"[v3 FAIL] {net}: Arduino -> above-BB col (row1 vertical)")
                continue
            # Vertical descent on rail_col, directly to the row 1 hole. No
            # intermediate hole on rail_col between above_cell and
            # row1_cell, so R1 is respected.
            descent_cells: list[tuple[int, int]] = []
            for r in range(above_cell[1] + 1, row1_cell[1] + 1):
                descent_cells.append((rail_col, r))
            # Concat manual waypoint + A* (cells_top starts at the waypoint
            # = last cell of waypoint_cells_pre, so we skip its 1st element
            # to avoid the duplicate). Then descent.
            if waypoint_cells_pre:
                full_cells = _remove_u_turns(
                    waypoint_cells_pre + cells[1:] + descent_cells)
            else:
                full_cells = _remove_u_turns(cells + descent_cells)
            start_xy = source_canvas_per_net.get(net)
            path = _cells_to_canvas_path(full_cells, grid,
                                          start_canvas=start_xy,
                                          end_canvas=row1_canvas)
            # NB: do NOT call _insert_horizontal_stubs here. The rule
            # "vertical arrival from the top of the BB" is the opposite of
            # Rule 3 (horizontal corner at the entry). The path is already
            # well-formed: a descending vertical segment ends on the row 1
            # hole.
            wires.append(Wire(net=net, color=color, path=path))
            grid.mark_wire(full_cells, ne.net_id)
            # Track the rail cells already used by this net: each consumer
            # wire must take a DIFFERENT hole (otherwise several wires
            # converge on the same hole, hard to read).
            used_rail_cells: set[tuple[int, int]] = {row1_cell}

            # 2) Each consumer -> rail
            # Strategy:
            # (a) PRE-PICK the rail cell closest (Manhattan) to the target
            #     among the available ones. Guarantees we don't use the
            #     farthest hole just because its path is cheaper in
            #     cost_map.
            # (b) If this rail cell is a CORNER (row 1 or row N), force the
            #     vertical exit (above/below BB) as for Arduino -> rail
            #     row 1. Otherwise horizontal exit OK (non-corner outer
            #     rail = Rule 2).
            bb = scene.breadboards[bb_idx_for_rail]
            bb_h = bb.size[1]
            # row N = last element of rail_cells_with_canvas
            row_n_cell, row_n_canvas = rail_cells_with_canvas[-1]

            # R8: for each battery_external + GND net, we prepare the
            # intra-BB rail-to-rail bridge along the bottom (R8-3) + we
            # reserve row 1 of the bat-side rail for the BAT- wire (R8-2).
            # Multi-battery: iterate over bat_infos_by_plus_net.
            extra_rail_cells_with_canvas: list[
                tuple[tuple[int, int], tuple[float, float]]] = []
            # List of dicts per battery (host BB + reserved rail cells).
            gnd_batteries_info: list[dict] = []
            all_bat_minus_cells: set[tuple[int, int]] = set()
            if net == "GND":
                for plus_net, info in bat_infos_by_plus_net.items():
                    bat_rail_with_canvas = info["bat_gnd_rail_cells_with_canvas"]
                    if not bat_rail_with_canvas:
                        continue
                    bat_row1_cell = bat_rail_with_canvas[0][0]
                    bat_row_n_cell = bat_rail_with_canvas[-1][0]
                    bat_row_n_canvas = bat_rail_with_canvas[-1][1]
                    # Pre-reserve bat-side corners: row 1 for R8-2
                    # (bat '-' wire), row N for R8-3 (bridge endpoint).
                    used_rail_cells.add(bat_row1_cell)
                    used_rail_cells.add(bat_row_n_cell)
                    # R8-6: the other bat-side rail cells become candidates
                    # for the ordinary consumers (= closest GND rail in
                    # Manhattan), since the R8-3 bridge makes them
                    # electrically equivalent.
                    extra_rail_cells_with_canvas.extend(bat_rail_with_canvas)
                    # Extends all_rail_cells_set for the upcoming A*.
                    all_rail_cells_set = all_rail_cells_set | {
                        c for (c, _) in bat_rail_with_canvas}
                    all_bat_minus_cells.add(info["bat_minus_cell"])
                    gnd_batteries_info.append({
                        "bb_idx": info["bb_idx"],
                        "bat_side": info["bat_side"],
                        "bat_rail_id": info["bat_gnd_rail_id"],
                        "bat_rail_cells_with_canvas": bat_rail_with_canvas,
                        "bat_minus_cell": info["bat_minus_cell"],
                        "bat_minus_canvas": info["bat_minus_canvas"],
                        "bat_row1_cell": bat_row1_cell,
                        "bat_row_n_cell": bat_row_n_cell,
                        "bat_row_n_canvas": bat_row_n_canvas,
                    })
                # If at least 1 GND battery: we also reserve row N of the
                # Arduino-side rail (= endpoint of the R8-3 bridge on the
                # Arduino side).
                if gnd_batteries_info and row_n_cell is not None:
                    used_rail_cells.add(row_n_cell)
                # We exclude all bat-minus from the ordinary consumer loop:
                # each will be routed separately on its bat-side rail
                # (R8-2).

            # Multi-BB: for each BB with on-BB consumers of this power net
            # (other than the primary BB), add its arduino-side rail to the
            # consumer pool. That way a consumer on BB1 taps the local BB1
            # rail (R8-6 generalized) instead of making a long detour to
            # BB0. Reserve row N-1 (= cross-BB bridge tap that will be added
            # after the consumer loop).
            from .occupancy import _NET_TO_RAIL as _NET_TO_RAIL_MAP
            rail_kind_pwr = _NET_TO_RAIL_MAP.get(net)
            if rail_kind_pwr is not None and not is_bat_plus:
                placed_by_ref_mb = {pc.component_ref: pc
                                     for pc in scene.placed_components}
                consumer_bbs_pool: set[int] = set()
                for cnet in netlist_components:
                    if cnet.get("type") == "battery_external":
                        continue
                    placed_c = placed_by_ref_mb.get(cnet.get("ref"))
                    if placed_c is None or placed_c.breadboard_idx < 0:
                        continue
                    for p in cnet.get("pins", []):
                        if p.get("net") == net:
                            consumer_bbs_pool.add(placed_c.breadboard_idx)
                            break
                board_x_mb = scene.board_translate[0]
                # BBs hosting a GND battery (= intra-BB bridge uses row N →
                # cross-BB bridge must then take row N-1).
                bbs_with_gnd_battery = {bg["bb_idx"]
                                          for bg in gnd_batteries_info}
                for other_bb in sorted(consumer_bbs_pool - {bb_idx_for_rail}):
                    other_x = scene.breadboard_translates[other_bb][0]
                    other_arduino_side = ("left" if other_x > board_x_mb
                                            else "right")
                    other_rail_id = f"{rail_kind_pwr}_{other_arduino_side}"
                    other_rail_can = _rail_cells_for_rail_id(
                        scene, grid, other_bb, other_rail_id)
                    if not other_rail_can or len(other_rail_can) < 2:
                        continue
                    # Reserve the cross-BB tap row: row N if free, else
                    # row N-1 (BB-with-battery case: row N is reserved by
                    # the R8-3 intra-BB bridge).
                    if other_bb in bbs_with_gnd_battery:
                        cross_reserved_idx = -2  # row N-1
                    else:
                        cross_reserved_idx = -1  # row N (free)
                    used_rail_cells.add(other_rail_can[cross_reserved_idx][0])
                    extra_rail_cells_with_canvas.extend(other_rail_can)
                    all_rail_cells_set = all_rail_cells_set | {
                        c for (c, _) in other_rail_can}

            consumer_rail_cells_with_canvas = (
                list(rail_cells_with_canvas) + extra_rail_cells_with_canvas)
            consumer_rail_cells = [c for (c, _xy)
                                    in consumer_rail_cells_with_canvas]
            consumer_rail_canvas_by_cell = {
                c: xy for (c, xy) in consumer_rail_cells_with_canvas}

            for target_cell in ne.targets:
                # R8-2: skip bat '-' pins (all batteries), routed lower to
                # their respective bat-side rail.
                if target_cell in all_bat_minus_cells:
                    continue
                available = [c for c in consumer_rail_cells
                              if c not in used_rail_cells]
                if not available:
                    print(f"[v3 FAIL] {net}: plus de rail libre pour target_cell={target_cell}")
                    continue
                # Pick the rail cell closest to the target. R8-6: may be on
                # arduino-side OR bat-side depending on Manhattan.
                chosen = min(available,
                              key=lambda c: abs(c[0] - target_cell[0])
                                           + abs(c[1] - target_cell[1]))
                # Detect corner (row 1 or row N) on the primary rail or on
                # any bat-side rail (multi-battery).
                bat_row1_cells_set = {bg["bat_row1_cell"]
                                       for bg in gnd_batteries_info
                                       if bg["bat_row1_cell"] is not None}
                bat_row_n_cells_set = {bg["bat_row_n_cell"]
                                        for bg in gnd_batteries_info
                                        if bg["bat_row_n_cell"] is not None}
                is_corner_row1 = (chosen == row1_cell
                                   or chosen in bat_row1_cells_set)
                is_corner_rown = ((row_n_cell is not None
                                    and chosen == row_n_cell)
                                   or chosen in bat_row_n_cells_set)
                if is_corner_row1 or is_corner_rown:
                    # Vertical exit (rule 3: corner -> vertical)
                    # R7-1 exception: on row 1 (and row N), the rail column
                    # has no other hole above (resp. below) the endpoint. We
                    # descend/ascend DIRECTLY on rail_col, without a final
                    # horizontal jump.
                    corner_col = chosen[0]  # = rail_col of the chosen rail cell
                    rail_canvas_x_corner = grid.cell_to_canvas(corner_col, 0)[0]
                    if is_corner_row1:
                        outside_canvas = (rail_canvas_x_corner, bb_ty - 12.0)
                    else:
                        outside_canvas = (rail_canvas_x_corner, bb_ty + bb_h + 12.0)
                    outside_cell = grid.canvas_to_cell(*outside_canvas)
                    cells = astar(grid, [outside_cell], [target_cell], ne.net_id,
                                   turn_penalty=turn_penalty,
                                   max_expansions=DEFAULT_MAX_EXPANSIONS,
                                   extra_blocked=all_rail_cells_set - {chosen})
                    if cells is None:
                        print(f"[v3 FAIL] {net}: outside-BB -> target_cell={target_cell} (corner)")
                        continue
                    # Prepend: chosen (rail row 1/N hole) -> vertical
                    # descent/ascent on rail_col up to outside_cell exclusive.
                    prepend: list[tuple[int, int]] = [chosen]
                    if is_corner_row1:
                        # descend from the chosen row toward above (row decreases)
                        for r in range(chosen[1] - 1, outside_cell[1], -1):
                            prepend.append((corner_col, r))
                    else:
                        # ascend from the chosen row toward below (row increases)
                        for r in range(chosen[1] + 1, outside_cell[1]):
                            prepend.append((corner_col, r))
                    cells = _remove_u_turns(prepend + cells)
                else:
                    # Horizontal exit (Rule 2: non-corner outer rail)
                    cells = astar(grid, [chosen], [target_cell], ne.net_id,
                                   turn_penalty=turn_penalty,
                                   max_expansions=DEFAULT_MAX_EXPANSIONS,
                                   extra_blocked=all_rail_cells_set - {chosen})
                    if cells is None:
                        print(f"[v3 FAIL] {net}: rail -> target_cell={target_cell}")
                        continue
                used_rail_cells.add(chosen)
                start_canvas_xy = consumer_rail_canvas_by_cell.get(cells[0])
                if start_canvas_xy is None:
                    start_canvas_xy = grid.cell_to_canvas(*cells[0])
                end_xy = target_canvas_per_net_cell.get((net, target_cell))
                path = _cells_to_canvas_path(cells, grid,
                                              start_canvas=start_canvas_xy,
                                              end_canvas=end_xy)
                # For corner sources (row 1 / row N): the path already
                # starts with a vertical segment (exit above/below the BB).
                # _insert_horizontal_stubs would add a spurious horizontal
                # corner -> we skip.
                if not (is_corner_row1 or is_corner_rown):
                    path = _insert_horizontal_stubs(path, scene, grid=grid,
                                                      net_id=ne.net_id)
                wires.append(Wire(net=net, color=color, path=path))
                grid.mark_wire(cells, ne.net_id)

            # R8-2 + R8-3: for EACH battery_external (GND only):
            # - route the '-' pin to its GND_<bat_side> rail (R8-2, corner
            #   R7-1 vertical on bat_rail_col)
            # - build the intra-BB bridge row N arduino-side <-> row N
            #   bat-side passing UNDER the BB (R8-3)
            for bg in gnd_batteries_info:
                host_bb_idx = bg["bb_idx"]
                host_bb = scene.breadboards[host_bb_idx]
                _host_tx, host_ty = scene.breadboard_translates[host_bb_idx]
                host_bb_h = host_bb.size[1]
                arduino_side_for_host = (
                    "right" if bg["bat_side"] == "left" else "left")
                # Compute arduino-side rail row N for this host BB (may
                # differ from row_n_cell of the primary BB block).
                arduino_rail_id = f"GND_{arduino_side_for_host}"
                arduino_rail_cells_can = _rail_cells_for_rail_id(
                    scene, grid, host_bb_idx, arduino_rail_id)
                if not arduino_rail_cells_can:
                    print(f"[v3 FAIL] GND R8-3 bridge: arduino-side rail "
                          f"introuvable pour BB{host_bb_idx}")
                    continue
                arduino_row_n_cell, arduino_row_n_canvas = arduino_rail_cells_can[-1]
                # row N arduino-side reserved for the bridge.
                used_rail_cells.add(arduino_row_n_cell)

                bat_rail_cells_can = bg["bat_rail_cells_with_canvas"]
                bat_rail_cells = [c for (c, _xy) in bat_rail_cells_can]
                bat_rail_canvas_by_cell = {c: xy for (c, xy) in bat_rail_cells_can}
                bat_minus_cell = bg["bat_minus_cell"]
                bat_minus_canvas = bg["bat_minus_canvas"]
                bg_row1_cell = bg["bat_row1_cell"]
                bg_row_n_cell = bg["bat_row_n_cell"]
                bg_row_n_canvas = bg["bat_row_n_canvas"]

                # R8-2: bat- → bat-side rail (corner R7-1 if row 1 or N).
                bat_available = [c for c in bat_rail_cells
                                  if c != bg_row_n_cell]
                if bat_available:
                    bat_chosen = min(bat_available,
                                      key=lambda c, m=bat_minus_cell:
                                      abs(c[0] - m[0]) + abs(c[1] - m[1]))
                    bat_is_row1 = bat_chosen == bg_row1_cell
                    bat_is_rown = (bg_row_n_cell is not None
                                    and bat_chosen == bg_row_n_cell)
                    if bat_is_row1 or bat_is_rown:
                        bat_corner_col = bat_chosen[0]
                        bat_rail_canvas_x = grid.cell_to_canvas(bat_corner_col, 0)[0]
                        if bat_is_row1:
                            bat_outside_canvas = (bat_rail_canvas_x,
                                                   host_ty - 12.0)
                        else:
                            bat_outside_canvas = (bat_rail_canvas_x,
                                                   host_ty + host_bb_h + 12.0)
                        bat_outside_cell = grid.canvas_to_cell(*bat_outside_canvas)
                        cells_bat = astar(grid, [bat_outside_cell],
                                           [bat_minus_cell], ne.net_id,
                                           turn_penalty=turn_penalty,
                                           max_expansions=DEFAULT_MAX_EXPANSIONS,
                                           extra_blocked=all_rail_cells_set - {bat_chosen})
                        if cells_bat is None:
                            print(f"[v3 FAIL] GND: outside-BB -> bat '-' "
                                  f"target_cell={bat_minus_cell} (R8-2 corner)")
                        else:
                            prepend_bat: list[tuple[int, int]] = [bat_chosen]
                            if bat_is_row1:
                                for r in range(bat_chosen[1] - 1,
                                                bat_outside_cell[1], -1):
                                    prepend_bat.append((bat_corner_col, r))
                            else:
                                for r in range(bat_chosen[1] + 1,
                                                bat_outside_cell[1]):
                                    prepend_bat.append((bat_corner_col, r))
                            cells_bat = _remove_u_turns(prepend_bat + cells_bat)
                            start_canvas_bat = bat_rail_canvas_by_cell.get(cells_bat[0])
                            if start_canvas_bat is None:
                                start_canvas_bat = grid.cell_to_canvas(*cells_bat[0])
                            end_xy_bat = target_canvas_per_net_cell.get(
                                ("GND", bat_minus_cell)) or bat_minus_canvas
                            path_bat = _cells_to_canvas_path(
                                cells_bat, grid,
                                start_canvas=start_canvas_bat,
                                end_canvas=end_xy_bat)
                            wires.append(Wire(net="GND", color=color,
                                              path=path_bat))
                            grid.mark_wire(cells_bat, ne.net_id)
                    else:
                        cells_bat = astar(grid, [bat_chosen], [bat_minus_cell],
                                           ne.net_id,
                                           turn_penalty=turn_penalty,
                                           max_expansions=DEFAULT_MAX_EXPANSIONS,
                                           extra_blocked=all_rail_cells_set - {bat_chosen})
                        if cells_bat is None:
                            print(f"[v3 FAIL] GND: bat-rail -> bat '-' "
                                  f"target_cell={bat_minus_cell} (R8-2 mid-row)")
                        else:
                            start_canvas_bat = bat_rail_canvas_by_cell.get(cells_bat[0])
                            if start_canvas_bat is None:
                                start_canvas_bat = grid.cell_to_canvas(*cells_bat[0])
                            end_xy_bat = target_canvas_per_net_cell.get(
                                ("GND", bat_minus_cell)) or bat_minus_canvas
                            path_bat = _cells_to_canvas_path(
                                cells_bat, grid,
                                start_canvas=start_canvas_bat,
                                end_canvas=end_xy_bat)
                            path_bat = _insert_horizontal_stubs(
                                path_bat, scene, grid=grid,
                                net_id=ne.net_id)
                            wires.append(Wire(net="GND", color=color,
                                              path=path_bat))
                            grid.mark_wire(cells_bat, ne.net_id)

                # R8-3: intra-BB bridge GND_arduino_side row N <-> row N
                # GND_bat_side, passing UNDER the host BB.
                if (arduino_row_n_cell is not None
                        and arduino_row_n_canvas is not None
                        and bg_row_n_cell is not None
                        and bg_row_n_canvas is not None):
                    bridge_result = _build_gnd_bridge_wire(
                        scene, grid, ne.net_id, color,
                        arduino_rail_row_n=(arduino_row_n_cell,
                                              arduino_row_n_canvas),
                        bat_rail_row_n=(bg_row_n_cell, bg_row_n_canvas),
                        bb_idx=host_bb_idx,
                        turn_penalty=turn_penalty,
                    )
                    if bridge_result is None:
                        print(f"[v3 FAIL] GND R8-3 bridge BB{host_bb_idx}: "
                              "A* below-BB arduino-side -> bat-side")
                    else:
                        bridge_wire, bridge_cells = bridge_result
                        wires.append(bridge_wire)
                        grid.mark_wire(bridge_cells, ne.net_id)

            # Cross-BB inter-BB bridge for a power net with consumers on
            # several BBs (typically GND when servo BB1 + driver BB0). Tap
            # row N-1 (second-to-last row) with 8 px lateral stagger on the
            # rail side, vertical descent on the adjacent col.
            if not is_bat_plus:  # bat+ nets are local to 1 BB
                placed_by_ref_pwr = {pc.component_ref: pc
                                      for pc in scene.placed_components}
                consumer_bbs: set[int] = set()
                for cnet in netlist_components:
                    if cnet.get("type") == "battery_external":
                        continue
                    placed_c = placed_by_ref_pwr.get(cnet.get("ref"))
                    if placed_c is None or placed_c.breadboard_idx < 0:
                        continue
                    for p in cnet.get("pins", []):
                        if p.get("net") == net:
                            consumer_bbs.add(placed_c.breadboard_idx)
                            break
                if len(consumer_bbs) >= 2:
                    from .occupancy import _NET_TO_RAIL
                    primary_cb = bb_idx_for_rail
                    rail_kind = _NET_TO_RAIL.get(net)
                    if rail_kind is None:
                        continue
                    primary_rail_id = f"{rail_kind}_{ 'left' if scene.breadboard_translates[primary_cb][0] > scene.board_translate[0] else 'right'}"
                    primary_rail_can = _rail_cells_for_rail_id(
                        scene, grid, primary_cb, primary_rail_id)
                    if primary_rail_can and len(primary_rail_can) >= 2:
                        # Tap row choice: row N if free, else N-1.
                        # Row N free <=> no battery hosted on the BB
                        # reserves row N for its intra-BB bridge (R8-3).
                        # For GND, that's gnd_batteries_info. For
                        # 5V/VIN/etc, never reserved.
                        bbs_with_battery = {bg["bb_idx"]
                                              for bg in gnd_batteries_info
                                              } if net == "GND" else set()
                        primary_has_bat = primary_cb in bbs_with_battery
                        primary_idx = -2 if primary_has_bat else -1
                        primary_rn1_cell, primary_rn1_canvas = primary_rail_can[primary_idx]
                        for other_cb in sorted(consumer_bbs - {primary_cb}):
                            other_x = scene.breadboard_translates[other_cb][0]
                            board_x_pwr = scene.board_translate[0]
                            other_arduino_side = ("left" if other_x > board_x_pwr
                                                    else "right")
                            other_rail_id = f"{rail_kind}_{other_arduino_side}"
                            other_rail_can = _rail_cells_for_rail_id(
                                scene, grid, other_cb, other_rail_id)
                            if not other_rail_can or len(other_rail_can) < 2:
                                continue
                            other_has_bat = other_cb in bbs_with_battery
                            other_idx = -2 if other_has_bat else -1
                            other_rn1_cell, other_rn1_canvas = other_rail_can[other_idx]
                            br = _build_cross_bb_power_bridge_wire(
                                scene, grid, ne.net_id, net, color,
                                primary_rail_cell_canvas=(primary_rn1_cell,
                                                            primary_rn1_canvas),
                                primary_bb_idx=primary_cb,
                                other_rail_cell_canvas=(other_rn1_cell,
                                                          other_rn1_canvas),
                                other_bb_idx=other_cb,
                                turn_penalty=turn_penalty,
                                stagger_primary=primary_has_bat,
                                stagger_other=other_has_bat,
                            )
                            if br is None:
                                print(f"[v3 FAIL] {net} cross-BB bridge "
                                      f"BB{primary_cb}<->BB{other_cb}")
                            else:
                                bridge_wire, bridge_cells = br
                                wires.append(bridge_wire)
                                grid.mark_wire(bridge_cells, ne.net_id)

        else:
            # Phase 2: signal nets and internal nets, direct routing
            for target_cell in ne.targets:
                cells = astar(grid, ne.sources, [target_cell],
                              ne.net_id, turn_penalty=turn_penalty,
                              max_expansions=DEFAULT_MAX_EXPANSIONS)
                if cells is None:
                    print(f"[v3 FAIL] {net}: src -> target_cell={target_cell}")
                    continue
                start_xy = source_canvas_per_net.get(net)
                end_xy = target_canvas_per_net_cell.get((net, target_cell))
                path = _cells_to_canvas_path(cells, grid,
                                              start_canvas=start_xy,
                                              end_canvas=end_xy)
                path = _insert_horizontal_stubs(path, scene, grid=grid,
                                                  net_id=ne.net_id)
                wires.append(Wire(net=net, color=color, path=path))
                grid.mark_wire(cells, ne.net_id)

    return wires


# ─── Canvas <-> pin caches for endpoint snapping ─────────────────────
def _build_source_canvas_cache(scene, netlist_components, endpoints):
    """net -> canvas (x, y) of the source pin (Arduino first, else 1st
    component pin). Used for the final snap in Wire.path.

    On-BB: uses _endpoint_canvas (= entry hole, Rule 4) NOT the pin itself
    — otherwise the wire snaps onto the terminal occupied by the component.
    Off-BB: _endpoint_canvas already returns the pin position.
    """
    from .occupancy import _resolve_board_pin, _endpoint_canvas, _name_to_pin_index
    out: dict[str, tuple[float, float]] = {}
    netlist_by_ref = {c["ref"]: c for c in netlist_components}
    for net, ne in endpoints.items():
        board_fn = _resolve_board_pin(scene.board_loader, net)
        if board_fn is not None:
            out[net] = scene.board_loader.pin_position(
                board_fn, translate=scene.board_translate
            )
            continue
        for placed in scene.placed_components:
            comp = netlist_by_ref.get(placed.component_ref)
            if comp is None:
                continue
            for pin in comp.get("pins", []):
                if pin.get("net") == net:
                    pin_idx = _name_to_pin_index(placed.catalog_entry, pin["name"])
                    if pin_idx is None:
                        continue
                    xy = _endpoint_canvas(scene, placed, pin_idx)
                    if xy is not None:
                        out[net] = xy
                        break
            if net in out:
                break
    return out


def _build_target_canvas_cache(scene, netlist_components, endpoints, grid):
    """(net, target_cell) -> exact canvas (x, y) of the wire_entry hole.

    Indexed by target_cell. We use _endpoint_canvas (= wire_entry for
    on-BB, pin for off-BB), consistent with extract_net_endpoints,
    otherwise the last point of Wire.path would be at the cell center
    (±2px offset due to snap-to-grid) instead of the exact target hole
    position.
    """
    from .occupancy import _endpoint_canvas, _name_to_pin_index
    out: dict[tuple[str, tuple[int, int]], tuple[float, float]] = {}
    netlist_by_ref = {c["ref"]: c for c in netlist_components}
    for net in endpoints:
        for placed in scene.placed_components:
            comp = netlist_by_ref.get(placed.component_ref)
            if comp is None:
                continue
            for pin in comp.get("pins", []):
                if pin.get("net") != net:
                    continue
                pin_idx = _name_to_pin_index(placed.catalog_entry, pin["name"])
                if pin_idx is None:
                    continue
                xy = _endpoint_canvas(scene, placed, pin_idx)
                if xy is None:
                    continue
                cell = grid.canvas_to_cell(*xy)
                out[(net, cell)] = xy
    return out
