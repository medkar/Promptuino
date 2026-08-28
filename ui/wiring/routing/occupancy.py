"""Builds the OccupancyGrid + A* endpoints from a PlacedScene.

This is the bridge between placement (`..layout.place_scene`) and the router:
  scene (placement) -> grid (blocked/free space) + endpoints (sources/targets per net)
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from ..layout.layout import (
    PlacedComponent, PlacedScene,
    _OFF_BB_DIMS, _OFF_BB_DEFAULT_DIM,
)
from ..layout.svg_component_loader import ComponentSVGLoader, NS as _SVG_NS

from .grid import OccupancyGrid


@lru_cache(maxsize=None)
def _svg_body_bbox_local(asset_path_str: str) -> tuple[float, float, float, float] | None:
    """Reads the SVG's `<rect id="component-body">` and returns its local bbox
    `(x, y, w, h)`. Cached by path (SVGs are read-only). Returns None
    if the asset has no body rect or is not parsable.
    """
    try:
        tree = ET.parse(asset_path_str)
    except (ET.ParseError, FileNotFoundError, OSError):
        return None
    root = tree.getroot()
    component = root.find(".//svg:g[@id='component']", _SVG_NS)
    if component is None:
        return None
    rect = component.find(".//svg:rect[@id='component-body']", _SVG_NS)
    if rect is None:
        return None
    try:
        x = float(rect.get("x", "0"))
        y = float(rect.get("y", "0"))
        w = float(rect.get("width", "0"))
        h = float(rect.get("height", "0"))
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


# ─── Constants ──────────────────────────────────────────────────────────
# Margins (px) around bodies to block them in the grid.
# ARDUINO_BODY_MARGIN: must stay at 0 otherwise the margin blocks the exit of
# the carve_channel of the Arduino pins. Rule 2 is applied differently
# (see add_cost on the Arduino pin bands below).
ARDUINO_BODY_MARGIN = 0
OFF_BB_BODY_MARGIN = 4
# Additional cost per cell on the BB body (penalizes without forbidding).
BB_BODY_COST = 5
# Radius in cells around the pins (Manhattan disk) for the endpoint.
# Off-BB components: 0 (= pin cell only). On DIP drivers the
# pins are spaced ~8 px apart (= 2 cells); a radius >=1 would make the disks
# of neighboring pins overlap each other and A* could no longer reach the
# target because pin_owner[target_cell] would hold that of the neighboring pin.
# Arduino board: pins spaced 16 px apart (= 4 cells); radius=2 OK.
PIN_RADIUS_CELLS_OFF_BB = 0
# cell_size=8 -> 1 cell = 8 px (= Arduino pin pitch / 2). Radius 1 keeps
# the disk at 8 px max (= pitch / 2) without touching the neighboring pins.
PIN_RADIUS_CELLS_ARDUINO = 1

# Rule 1: margin (px) around the BB hole rows/columns. A band of
# +/- HOLE_LINE_MARGIN_PX around each Y (row) and each X (column)
# containing a hole receives a high cost (`HOLE_LINE_COST`) to discourage
# wires from passing through. We use cost_map rather than body_mask=1 because the
# endpoint pin itself is INSIDE a band (= necessarily crossed to land on it).
# A* chooses the corridors between bands (free) except entering/exiting a pin.
HOLE_LINE_MARGIN_PX = 4
HOLE_LINE_COST = 60  # kept for possible future use (unused since R1 hard-block)

# Rule 2: same idea but for the Arduino pins. The pin cells
# themselves are ALREADY hard-blocked (they fall inside the Arduino body
# bbox, body_mask=1 at step 2). What was missing is the SOFT-COST on the
# band just OUTSIDE the body, along the pin rows: without
# it, a wire exiting a pin can run along the board edge flush with the
# neighboring pins (unreadable). So we lay a cost on this band so that
# A* prefers to step away one cell before running parallel to the edge.
# The band stays SOFT (cost_map, not body_mask) because the endpoint pin
# itself is INSIDE the band (the wire must necessarily cross it to exit).
ARDUINO_PIN_LINE_MARGIN_PX = 6        # depth (px) of the band toward the outside
ARDUINO_PIN_LINE_HALF_SPAN_PX = 9     # half-width (px) along the edge, per pin
                                      # (~ pitch/2 + margin -> contiguous neighboring bands)
ARDUINO_PIN_LINE_COST = HOLE_LINE_COST  # same cost as the BB hole bands (R1)


# Net Arduino mapping (taken verbatim from v2.layout.routing._NET_TO_BOARD_PIN
# to avoid creating an import coupling).
_NET_TO_BOARD_PIN: dict[str, str] = {
    "5V":  "V5V",
    "3V3": "V3V3",
    "GND": "GND2",
    "VIN": "VIN",
}

# Power net -> rail kind mapping on the BB (taken from v2._NET_TO_RAIL).
# Phase 3: for these nets, the routing does Arduino -> BB rail (1 wire) then
# rail -> each consumer (1 jumper per consumer). Visually cleaner
# than N direct wires from the Arduino pin when >=2 consumers.
_NET_TO_RAIL: dict[str, str] = {
    "5V":  "V+",
    "VIN": "V+",
    "3V3": "V+",
    "GND": "GND",
}


@dataclass
class NetEndpoints:
    """A* endpoints of a net in the grid."""
    net: str
    net_id: int
    sources: list[tuple[int, int]] = field(default_factory=list)
    targets: list[tuple[int, int]] = field(default_factory=list)


# ─── Internal helpers ────────────────────────────────────────────────────
def _resolve_board_pin(board_loader, net: str) -> str | None:
    """Returns the fn of the Arduino pin a net connects to, or None."""
    if net in _NET_TO_BOARD_PIN:
        return _NET_TO_BOARD_PIN[net]
    if board_loader.has_pin(net):
        return net
    return None


def power_rail_for_net(scene: PlacedScene, net: str
                        ) -> tuple[int, str] | None:
    """(bb_idx, rail_id) for a power net, or None if not a rail net.

    Heuristic: primary BB = BB closest to the board. Rail side =
    side of the BB facing the board (= "right" if BB is left of the board, otherwise
    "left"). Identical to the v2.layout.routing 1a/1c logic.
    """
    rail_kind = _NET_TO_RAIL.get(net)
    if rail_kind is None:
        return None
    # Primary BB choice: the 1st (BB 0) is enough for Phase 3 mono-BB.
    # For multi-BB we would take the one with the most consumers.
    primary_bb_idx = 0
    bb_x = scene.breadboard_translates[primary_bb_idx][0]
    board_x = scene.board_translate[0]
    rail_side = "left" if bb_x > board_x else "right"
    return (primary_bb_idx, f"{rail_kind}_{rail_side}")


def _component_pin_canvas(scene: PlacedScene, placed: PlacedComponent,
                          pin_idx: int) -> tuple[float, float] | None:
    """Canvas position of pin (pin_idx) of a placed component."""
    if placed.breadboard_idx < 0:
        # Off-BB: load the SVG asset and read the local position
        scale = getattr(placed.catalog_entry, "render_scale", 1.0)
        loader = ComponentSVGLoader(placed.catalog_entry.asset_path, scale=scale)
        pin_local = loader.pin_positions().get(pin_idx)
        if pin_local is None:
            return None
        return (placed.translate[0] + pin_local[0],
                placed.translate[1] + pin_local[1])
    # On-BB: position of the tie-strip hole
    hole = placed.pin_to_hole.get(pin_idx)
    if hole is None:
        return None
    col_id, row = hole
    bb = scene.breadboards[placed.breadboard_idx]
    cx, cy = bb.hole_position(col_id, row)
    tx, ty = scene.breadboard_translates[placed.breadboard_idx]
    return (cx + tx, cy + ty)


_TIESTRIP_LEFT_HALF = "abcde"
_TIESTRIP_RIGHT_HALF = "fghij"


def _component_wire_entry_canvas(scene: PlacedScene, placed: PlacedComponent,
                                   pin_idx: int) -> tuple[float, float] | None:
    """Canvas position of the hole WHERE THE WIRE lands (Rule 4).

    Rule 4: the wire connects to the FIRST free hole ADJACENT to the pin,
    on the side OPPOSITE the component body. The logic changes by type:

      - DIP (catalog_entry.is_dip): body on the e/f gap, so:
          * pin on tie-strip LEFT (cols a-e) -> exit on LEFT (col-1, ...)
          * pin on tie-strip RIGHT (cols f-j) -> exit on RIGHT (col+1, ...)
        (independent of mirrored: the gap stays centered in both cases)

      - Single-line: body extends on one side of the pin, in the same half.
        v2 placement convention:
          * BB1 non-mirrored (single-line col 'b'): body on LEFT -> exit RIGHT
          * BB2 mirrored (single-line col 'i'): body on RIGHT -> exit LEFT

    If the pin is at the edge of a half (a/e/f/j) or the candidate hole is
    occupied by another pin of the same component: we look for the next free one in
    the direction. If everything is occupied, we stay on the pin (degraded).

    Off-BB or pin placed on a rail: returns the position of the pin itself.
    """
    if placed.breadboard_idx < 0:
        return _component_pin_canvas(scene, placed, pin_idx)
    hole = placed.pin_to_hole.get(pin_idx)
    if hole is None:
        return None
    col_id, row = hole

    if placed.paired_with_pullup:
        entry_col = "d" if placed.mirrored else "g"
    elif col_id not in _TIESTRIP_LEFT_HALF and col_id not in _TIESTRIP_RIGHT_HALF:
        # Placed on a rail (V+/GND): no relocation
        return _component_pin_canvas(scene, placed, pin_idx)
    else:
        is_dip = getattr(placed.catalog_entry, "is_dip", False)
        in_left = col_id in _TIESTRIP_LEFT_HALF
        tie_half = _TIESTRIP_LEFT_HALF if in_left else _TIESTRIP_RIGHT_HALF
        idx = tie_half.index(col_id)

        is_horizontal = getattr(placed.catalog_entry, "is_horizontal", False)
        if is_horizontal:
            # Paired horizontal R: 2 pins on the SAME row, OPPOSITE
            # HALVES, body at the CENTER of the groove. Entry = END of the
            # half (= v2 rule). When pin-2 (main side) is already at
            # the end (col 'e' BB2-mirror or 'f' BB1-non-mirror), entry
            # = col of the pin → 0-length wire with the paired main (LED-A at
            # 'd'/'g' adjacent, same strip).
            if placed.mirrored:
                entry_col = "e" if in_left else "j"
            else:
                entry_col = "a" if in_left else "f"
        else:
            if is_dip:
                # DIP: body in the central groove between the 2 pins.
                # Exit toward the outside (a/j), NEVER toward e/f.
                direction = -1 if in_left else +1
            else:
                # Single-line: the body extends on the side OPPOSITE the pin per
                # mirrored. mirrored=True applies scale(-1,1) to the internal
                # geometry → body on the LEFT of the pin → exit on the RIGHT (+1).
                # mirrored=False → body on the RIGHT → exit on the LEFT (-1).
                direction = +1 if placed.mirrored else -1

            # Cols occupied by other pins of the same component on the row
            occupied_on_row = {
                c for (c, r) in placed.pin_to_hole.values() if r == row
            }
            # Look for the 1st free hole in the direction, clamp to bounds
            new_idx = idx
            for delta in range(1, len(tie_half)):
                candidate_idx = idx + delta * direction
                if not (0 <= candidate_idx < len(tie_half)):
                    break
                if tie_half[candidate_idx] not in occupied_on_row:
                    new_idx = candidate_idx
                    break
            entry_col = tie_half[new_idx]

    bb = scene.breadboards[placed.breadboard_idx]
    cx, cy = bb.hole_position(entry_col, row)
    tx, ty = scene.breadboard_translates[placed.breadboard_idx]
    return (cx + tx, cy + ty)


def _endpoint_canvas(scene: PlacedScene, placed: PlacedComponent,
                     pin_idx: int) -> tuple[float, float] | None:
    """Returns the canvas position to use as the A* endpoint for this pin.

    For on-BB components: entry hole (Rule 4) different from the component's
    pin. For off-BB: the component's pin directly.
    """
    return _component_wire_entry_canvas(scene, placed, pin_idx)


def _name_to_pin_index(catalog_entry, pin_name: str) -> int | None:
    for idx, label in catalog_entry.pin_labels.items():
        if label == pin_name:
            return idx
    return None


def _pin_alignment(placed: PlacedComponent,
                    pin_x: float, pin_y: float,
                    tol: float = 1.0) -> tuple[bool, bool]:
    """Determines whether the current pin is part of a group of pins aligned
    horizontally (= same cy with >=1 other pin) or vertically
    (= same cx with >=1 other pin).

    Returns (align_horiz, align_vert). Both can be False if the
    pin is isolated or if all pins are at the same point (degenerate).
    Used by `_carve_off_bb_pin_channel` to choose an exit direction
    consistent among the pins of the same group (= same physical visual
    connector) and avoid creating a common bottleneck corridor.
    """
    scale = getattr(placed.catalog_entry, "render_scale", 1.0)
    loader = ComponentSVGLoader(placed.catalog_entry.asset_path, scale=scale)
    all_pins = loader.pin_positions(translate=placed.translate)
    # Look for at least 1 other pin sharing cx or cy with the current pin
    align_horiz = False
    align_vert = False
    for (px, py) in all_pins.values():
        if abs(px - pin_x) < tol and abs(py - pin_y) < tol:
            continue   # this is the current pin itself
        if abs(py - pin_y) < tol:
            align_horiz = True
        if abs(px - pin_x) < tol:
            align_vert = True
        if align_horiz and align_vert:
            break
    return align_horiz, align_vert


def _mark_carve_pin_owner(grid: OccupancyGrid,
                           x0: float, y0: float, x1: float, y1: float,
                           net_id: int) -> None:
    """Marks pin_owner=net_id on the cells along the canvas line
    (x0, y0)->(x1, y1), without perpendicular extension.

    Used after `carve_channel(half_width=1)` to reserve the channel for the
    pin's net, preventing other nets from using the channel as a
    transverse corridor. The perpendicular overrun of half_width=1 stays free
    (pin_owner=0) for the pin itself.
    """
    c0, r0 = grid.canvas_to_cell(x0, y0)
    c1, r1 = grid.canvas_to_cell(x1, y1)
    dx = abs(c1 - c0)
    dy = abs(r1 - r0)
    sx = 1 if c0 < c1 else -1
    sy = 1 if r0 < r1 else -1
    err = dx - dy
    col, row = c0, r0
    while True:
        if 0 <= row < grid.rows and 0 <= col < grid.cols:
            if int(grid.pin_owner[row, col]) == 0:
                grid.pin_owner[row, col] = net_id
        if col == c1 and row == r1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            col += sx
        if e2 < dx:
            err += dx
            row += sy


def _carve_off_bb_pin_channel(grid: OccupancyGrid, placed: PlacedComponent,
                                pin_xy: tuple[float, float], net_id: int
                                ) -> None:
    """For an off-BB component pin, carves a channel from the pin to the
    nearest body edge and marks the cells as the net's pin_owner.

    Essential for pins INSIDE the body bbox (e.g. L298N pin 1 ENA
    at cy=158 in a 240x170 body, ULN2003 OUT at cy=44 in 240x200): without
    a channel, A* is trapped in the 13-cell bubble of set_pin(radius=2)
    because the adjacent cells are body_mask=1.

    For pins outside the body (tail that sticks out, e.g. DC motor pin at
    Y > body bottom), no carve needed — the pin is already in
    a free zone adjacent to the body.
    """
    w, h = _OFF_BB_DIMS.get(placed.component_type, _OFF_BB_DEFAULT_DIM)
    px, py = placed.translate
    bx_min, by_min, bx_max, by_max = px, py, px + w, py + h
    pin_x, pin_y = pin_xy

    d_left = pin_x - bx_min
    d_right = bx_max - pin_x
    d_top = pin_y - by_min
    d_bottom = by_max - pin_y

    # Pin already outside the body: no carve needed
    if d_left < 0 or d_right < 0 or d_top < 0 or d_bottom < 0:
        return

    # The channel must emerge BEYOND the zone blocked by the margin,
    # otherwise it ends in body_mask=1 and A* stays trapped. We aim for margin + 2.
    m = OFF_BB_BODY_MARGIN
    # Exit direction: detects the placement pattern of the component's
    # pins to choose intelligently.
    #  - If several pins share the SAME cx (= aligned vertically,
    #    column connector, ULN2003 OUT/IN case, L298N side pins,
    #    5-pin JST stepper) -> HORIZONTAL exit: each pin exits on
    #    its own row, no common bottleneck corridor.
    #  - If several pins share the SAME cy (= aligned horizontally,
    #    inline connector, NEMA17 4-pin at bottom case, dc_motor terminals
    #    side by side) -> VERTICAL exit: each pin exits on its own col.
    #  - Otherwise (isolated pin or mixed layout) -> exit per min(d_left, ...,
    #    d_bottom) = nearest body edge, historical fallback.
    align_horiz, align_vert = _pin_alignment(placed, pin_x, pin_y)
    if align_vert:
        # Pins in a column -> horizontal exit per the sign of the pin's dx
        # relative to the body center (side opposite the center = toward
        # the outside).
        cx_center = (bx_min + bx_max) / 2.0
        if pin_x <= cx_center:
            exit_x, exit_y = bx_min - m - 2, pin_y
        else:
            exit_x, exit_y = bx_max + m + 2, pin_y
    elif align_horiz:
        # Pins in a row -> vertical exit per the sign of dy.
        cy_center = (by_min + by_max) / 2.0
        if pin_y <= cy_center:
            exit_x, exit_y = pin_x, by_min - m - 2
        else:
            exit_x, exit_y = pin_x, by_max + m + 2
    else:
        # Isolated pin: fallback min(d).
        d_min = min(d_left, d_right, d_top, d_bottom)
        if d_min == d_left:
            exit_x, exit_y = bx_min - m - 2, pin_y
        elif d_min == d_right:
            exit_x, exit_y = bx_max + m + 2, pin_y
        elif d_min == d_top:
            exit_x, exit_y = pin_x, by_min - m - 2
        else:
            exit_x, exit_y = pin_x, by_max + m + 2

    # half_width=1: carve widened to 3 perpendicular cells. Lets
    # A* enter the carve cell from 3 sides (otherwise, for the
    # pins where the carve exit cell falls on the body+margin boundary,
    # the 2 perpendicular cells stay body_mask=1 and the pin
    # is accessible from only 1 side).
    grid.carve_channel(pin_x, pin_y, exit_x, exit_y, half_width=1)
    # Reserve the carved cells for the pin's net: otherwise, when several
    # pins of the same component are aligned with a small spacing
    # (5-pin stepper, ULN2003 OUT pins), the adjacent carves abut
    # and form a free CORRIDOR in the body. A* would use it as a
    # vertical/horizontal bridge for third-party nets, and the wire would pass
    # visually over the body (visible with the off-BB z-index
    # before the wires). By marking pin_owner on the carve cells,
    # only the pin's net can cross them. Pins of the same component
    # have no conflict because they are on distinct rows and their
    # carves do not overlap (except the half_width=1 overrun over 1 px
    # which stays allowed for the current pin_owner net).
    _mark_carve_pin_owner(grid, pin_x, pin_y, exit_x, exit_y, net_id)
    # Force the wire to arrive IN THE DIRECTION OF THE CARVE: re-block the
    # 2 cells perpendicular TO THE PIN (not along the carve). Without this
    # blocking, half_width=1 leaves the cells perpendicular to the pin
    # accessible -> A* can enter the pin from the perpendicular side
    # (= last segment perpendicular to the carve, e.g. a wire exiting
    # vertically from a DC motor pin placed side by side when we want
    # a horizontal exit). We block only the cells perpendicular
    # TO THE PIN, not along the carve, so the exit cell stays reachable.
    pin_col, pin_row = grid.canvas_to_cell(pin_x, pin_y)
    carve_is_horizontal = abs(exit_x - pin_x) > abs(exit_y - pin_y)
    if carve_is_horizontal:
        # Block the cells above and below the pin
        for dr in (-1, 1):
            rr = pin_row + dr
            if 0 <= rr < grid.rows and 0 <= pin_col < grid.cols:
                grid.body_mask[rr, pin_col] = 1
    else:
        # Block the cells to the left and right of the pin
        for dc in (-1, 1):
            cc = pin_col + dc
            if 0 <= pin_row < grid.rows and 0 <= cc < grid.cols:
                grid.body_mask[pin_row, cc] = 1

    # The channel just clears body_mask=0; we do NOT mark pin_owner on the
    # intermediate cells: 2 pins of the same component exiting on the
    # same side (e.g. DC motor M+/M- on the right) have their channels overlapping
    # each other, which isolates one of the pins. The pin cell itself
    # stays pin_owner=net_id (set by set_pin before the call) which is enough
    # to prevent another net from connecting to it by mistake.
    col_pin, row_pin = grid.canvas_to_cell(pin_x, pin_y)
    if 0 <= row_pin < grid.rows and 0 <= col_pin < grid.cols:
        grid.pin_owner[row_pin, col_pin] = net_id


# ─── API publique ────────────────────────────────────────────────────────
def build_occupancy_grid(scene: PlacedScene, netlist: list[dict],
                          cell_size: int = 4
                          ) -> tuple[OccupancyGrid, dict[str, int]]:
    """Builds the occupancy grid from a placed v2 scene.

    Steps:
      1. Allocate a net_id per netlist net (1..N, 0 = none)
      2. Block the Arduino body (body_mask = 1, margin ARDUINO_BODY_MARGIN)
      3. Reduced cost on the BB bodies (cost_map += BB_BODY_COST)
      4. Block the off-BB bodies (body_mask = 1, margin OFF_BB_BODY_MARGIN)
      5. Mark the component pins as pin_owner (with PIN_RADIUS_CELLS)
      6. Mark the Arduino pins corresponding to the used nets

    Note: the on-BB bodies are NOT blocked (the pins generally suffice
    to prevent crossings, and blocking the zone is complicated without an
    explicit bbox per component). To revisit if needed.

    Returns: (grid, net_to_id)
    """
    canvas_w, canvas_h = scene.canvas_size
    grid = OccupancyGrid(canvas_w, canvas_h, cell_size)

    # 1. net_id allocation
    net_to_id: dict[str, int] = {}
    next_id = 1
    for comp in netlist:
        for pin in comp.get("pins", []):
            net = pin.get("net", "")
            if net and net not in net_to_id:
                net_to_id[net] = next_id
                next_id += 1

    # 2. Block Arduino body
    bx_min, by_min, bx_max, by_max = scene.board_loader.body_bbox(
        translate=scene.board_translate
    )
    m = ARDUINO_BODY_MARGIN
    grid.blit_body(bx_min - m, by_min - m,
                   (bx_max - bx_min) + 2 * m,
                   (by_max - by_min) + 2 * m, value=1)

    # 2b. Rule 2: SOFT-COST on the band just outside the body,
    #     along the pin rows. For each board pin (used
    #     OR NOT), we lay a cost on the outer strip of the nearest
    #     edge (= the edge through which the pin exits, same d_min convention
    #     as the carve_channel of step 6). Since the pins of the same edge are
    #     spaced a pitch of ~16 px apart and the half-width is ~9 px, the
    #     bands join into a continuous band along the row.
    #     set_max_cost (not add_cost): the overlaps do not add
    #     up (otherwise corners at 2x/3x the cost -> absurd detours, cf R1-3b).
    #     Soft (cost_map): the endpoint pin is in the band, the wire
    #     must be able to cross it perpendicularly to exit.
    pm = ARDUINO_PIN_LINE_MARGIN_PX
    hs = ARDUINO_PIN_LINE_HALF_SPAN_PX
    for _fn, (px, py) in scene.board_loader.pin_positions(
            translate=scene.board_translate).items():
        d_left = px - bx_min
        d_right = bx_max - px
        d_top = py - by_min
        d_bottom = by_max - py
        d_min = min(d_left, d_right, d_top, d_bottom)
        if d_min == d_top:
            grid.set_max_cost(px - hs, by_min - pm, 2 * hs, pm,
                              ARDUINO_PIN_LINE_COST)
        elif d_min == d_bottom:
            grid.set_max_cost(px - hs, by_max, 2 * hs, pm,
                              ARDUINO_PIN_LINE_COST)
        elif d_min == d_left:
            grid.set_max_cost(bx_min - pm, py - hs, pm, 2 * hs,
                              ARDUINO_PIN_LINE_COST)
        else:  # d_right
            grid.set_max_cost(bx_max, py - hs, pm, 2 * hs,
                              ARDUINO_PIN_LINE_COST)

    # 3. Rule 1 (STRICT): double protection against passing over holes:
    #
    #    3a. HARD-BLOCK: each cell containing a BB hole is body_mask=1.
    #        A wire can PHYSICALLY not land on it unless declared an endpoint
    #        via set_pin (steps 5/5b/6 which clear body_mask=0).
    #
    #    3b. SOFT-COST: the hole Y rows and X columns receive
    #        cost_map = HOLE_LINE_COST over their band width
    #        (HOLE_LINE_MARGIN_PX = 4 px). Discourages A* from taking the
    #        hole-axes even in the inter-hole cells (which are
    #        technically crossable but visually adjacent to the
    #        holes). Without this soft-cost, A* would use for example the
    #        clean rail as a transit corridor.
    for i, bb in enumerate(scene.breadboards):
        bb_x, bb_y = scene.breadboard_translates[i]
        bb_w, bb_h = bb.size
        all_holes = {**bb.all_tiestrip_holes(), **bb.all_rail_holes()}
        # 3a. Hard-block hole cells
        for (cx, cy) in all_holes.values():
            hx = cx + bb_x
            hy = cy + bb_y
            col, row = grid.canvas_to_cell(hx, hy)
            if 0 <= col < grid.cols and 0 <= row < grid.rows:
                grid.body_mask[row, col] = 1
        # 3b. Soft-cost row/col bands (full BB extent)
        hole_ys: set[float] = {cy + bb_y for (cx, cy) in all_holes.values()}
        hole_xs: set[float] = {cx + bb_x for (cx, cy) in all_holes.values()}
        m = HOLE_LINE_MARGIN_PX
        for y in hole_ys:
            grid.set_max_cost(bb_x, y - m, bb_w, 2 * m, HOLE_LINE_COST)
        for x in hole_xs:
            grid.set_max_cost(x - m, bb_y, 2 * m, bb_h, HOLE_LINE_COST)

    # 4. Block off-BB bodies (motors, off-BB drivers, battery)
    for placed in scene.placed_components:
        if placed.breadboard_idx >= 0:
            continue
        w, h = _OFF_BB_DIMS.get(placed.component_type, _OFF_BB_DEFAULT_DIM)
        px, py = placed.translate
        m = OFF_BB_BODY_MARGIN
        grid.blit_body(px - m, py - m, w + 2 * m, h + 2 * m, value=1)

    # 4b. Block on-BB bodies (DIP, single-row placed on the BB). Without this
    #     blocking, A* uses the inter-hole cells UNDER the component
    #     as a corridor (R1 strict blocks the holes but not the space
    #     between, so the body was not a barrier).
    #     bbox computation = extent of the component's pin holes on the BB,
    #     plus a margin. For a DIP, this covers the gap zone + 1 col on
    #     each side. For a single-row, this covers the pin col +
    #     margin (the visual body extends laterally beyond the pins).
    #     set_pin (step 5) then clears body_mask for the ENDPOINTS,
    #     which are the adjacent holes per R4, located OUTSIDE this
    #     bbox.
    # For DIP: body extends between the 2 pin cols (= visual body
    # zone) BUT NOT over the cols of the pins themselves (otherwise the pin
    # cells become inaccessible from the outside). We TIGHTEN
    # the bbox: remove 1 col on each side to leave the pin cols
    # as access corridors.
    # For single-row: R1b MUST apply too (the wires under the body
    # stay visually unreadable even if the body is thin). The body
    # extends on 1 side of the pin col (side opposite the R4 entry hole).
    # We block this side over ~1 pitch wide, without touching the col of the
    # pins (otherwise the pins themselves become inaccessible).
    for placed in scene.placed_components:
        if placed.breadboard_idx < 0:
            continue
        if not placed.pin_to_hole:
            continue
        bb = scene.breadboards[placed.breadboard_idx]
        bb_tx, bb_ty = scene.breadboard_translates[placed.breadboard_idx]
        bb_w = bb.size[0]
        xs: list[float] = []
        ys: list[float] = []
        for pin_idx, (col_id, row) in placed.pin_to_hole.items():
            try:
                cx, cy = bb.hole_position(col_id, row)
            except (KeyError, ValueError):
                continue
            xs.append(cx + bb_tx)
            ys.append(cy + bb_ty)
        if not xs:
            continue
        # WARNING: use local variables (not bx_min/bx_max)
        # because step 6 (Arduino channel) reads bx_min/bx_max from step 2. If we
        # overwrite them here, the Arduino channel uses the wrong bbox.
        if placed.catalog_entry.is_dip:
            # DIP: body extends between the 2 pin cols (visual body
            # zone) BUT NOT over the cols of the pins themselves (otherwise the
            # pin cells become inaccessible from the outside). We
            # TIGHTEN the bbox: remove 1 col on each side to leave
            # the pin cols as access corridors.
            cb_min_x, cb_max_x = min(xs), max(xs)
            cb_min_y, cb_max_y = min(ys), max(ys)
            cb_min_x -= 3.0
            cb_max_x += 3.0
        else:
            # Single-row: all the pins share the same x. The body
            # extends on a single side of the pin col (= side opposite the R4
            # entry hole). The width is read from the SVG (rect
            # `id="component-body"`) then transformed to canvas coords by
            # applying `render_scale` and `mirrored`. We extend the block
            # up to and including the pin col (also covers the stub line between
            # pin and body) so that no wire passes visually through
            # the pin col or under the stub. The entry col (R4, side
            # opposite the body) stays accessible. Fallback: 28 px (legacy)
            # if the SVG does not expose the body rect.
            first_pin_idx = next(iter(placed.pin_to_hole.keys()))
            pin_canvas_xy = _component_pin_canvas(scene, placed, first_pin_idx)
            entry_canvas_xy = _endpoint_canvas(scene, placed, first_pin_idx)
            if (pin_canvas_xy is None or entry_canvas_xy is None):
                continue
            pin_x = pin_canvas_xy[0]
            entry_x = entry_canvas_xy[0]
            scale = getattr(placed.catalog_entry, "render_scale", 1.0)
            bbox_local = _svg_body_bbox_local(
                str(placed.catalog_entry.asset_path)
            )
            raw_loader = ComponentSVGLoader(
                placed.catalog_entry.asset_path, scale=1.0
            )
            pin_local = raw_loader.pin_positions().get(first_pin_idx)
            if bbox_local is not None and pin_local is not None:
                bx, _by, bw, _bh = bbox_local
                pin_x_local = pin_local[0]
                # Signed body→pin offset in local. dx_min < 0 if body is on the
                # left of the pin, dx_max > 0 if body is on the right of the pin.
                dx_min_local = (bx - pin_x_local) * scale
                dx_max_local = (bx + bw - pin_x_local) * scale
                if placed.mirrored:
                    # scale(-1, 1) flips the x axis around pin_x_canvas
                    body_min = pin_x - dx_max_local
                    body_max = pin_x - dx_min_local
                else:
                    body_min = pin_x + dx_min_local
                    body_max = pin_x + dx_max_local
                # Extend the block up to the pin itself (includes pin col +
                # stub line). The R4 entry col (opposite side) stays
                # always outside because the body is entirely on one side.
                cb_min_x = min(body_min, pin_x)
                cb_max_x = max(body_max, pin_x)
            else:
                # Fallback: SVG without a parsable body rect. Keeps the old
                # 1-pitch heuristic (28 px), extended to the pin col.
                BODY_W_PX = 28.0
                if entry_x < pin_x:
                    cb_min_x = pin_x
                    cb_max_x = pin_x + BODY_W_PX
                else:
                    cb_min_x = pin_x - BODY_W_PX
                    cb_max_x = pin_x
            cb_min_y = min(ys)
            cb_max_y = max(ys)
        # Vertical: extend by 28 px (= 1 BB pitch) above/below to
        # cover the SVG silhouette of the body that extends past the
        # outermost pin rows. Without this extension, wires can cross
        # the top/bottom of the body visually.
        cb_min_y -= 28.0
        cb_max_y += 28.0
        if cb_min_x >= cb_max_x or cb_min_y >= cb_max_y:
            continue
        grid.blit_body(cb_min_x, cb_min_y,
                       cb_max_x - cb_min_x, cb_max_y - cb_min_y, value=1)

    # 5. Mark the ENDPOINTS for A*:
    #    - on-BB: the entry hole (Rule 4), not the component hole
    #    - off-BB: the position of the component pin + carve channel toward
    #      the outside of the body to make the pin reachable (otherwise
    #      trapped in the set_pin radius=2 bubble surrounded by body_mask=1).
    #    set_pin clears body_mask to make the hole reachable despite
    #    Rule 1 (blocked hole rows/cols).
    netlist_by_ref = {c["ref"]: c for c in netlist}
    for placed in scene.placed_components:
        comp = netlist_by_ref.get(placed.component_ref)
        if comp is None:
            continue
        for pin in comp.get("pins", []):
            net = pin.get("net", "")
            net_id = net_to_id.get(net)
            if net_id is None:
                continue
            pin_idx = _name_to_pin_index(placed.catalog_entry, pin["name"])
            if pin_idx is None:
                continue
            endpoint_xy = _endpoint_canvas(scene, placed, pin_idx)
            if endpoint_xy is None:
                continue
            # Off-BB: radius=0 (tight pins, overlap of neighboring disks
            # forbidden); on-BB: radius=0 too because the entry hole is
            # already on a BB hole row, a widened set_pin could
            # collide with the pins of a neighboring component.
            radius = (PIN_RADIUS_CELLS_OFF_BB if placed.breadboard_idx < 0
                       else PIN_RADIUS_CELLS_OFF_BB)
            grid.set_pin(endpoint_xy[0], endpoint_xy[1], net_id,
                         radius_cells=radius)
            if placed.breadboard_idx < 0:
                _carve_off_bb_pin_channel(grid, placed, endpoint_xy, net_id)

    # 5b. Phase 3: mark all the cells of the BB rails as pin_owner
    #     of the power net. A* can thus target any cell of the
    #     rail as an endpoint (= "any rail hole works"), and reciprocally
    #     the consumers can source from the rail.
    rails_to_pin: list[tuple[int, str, int]] = []  # (bb_idx, rail_id, net_id)
    # For each power net (5V, GND, ...), set_pin ALL the BBs having
    # on-BB consumers of the net on their arduino-side rail (not just
    # the primary BB). Lets the consumers of a secondary BB tap
    # their local rail instead of cross-BB every time.
    placed_by_ref_rails = {pc.component_ref: pc for pc in scene.placed_components}
    consumer_bbs_by_net: dict[str, set[int]] = {}
    for c in netlist:
        if c.get("type") == "battery_external":
            continue
        ref = c.get("ref")
        placed = placed_by_ref_rails.get(ref) if ref else None
        if placed is None or placed.breadboard_idx < 0:
            continue
        for p in c.get("pins", []):
            net = p.get("net")
            if net:
                consumer_bbs_by_net.setdefault(net, set()).add(
                    placed.breadboard_idx)
    board_x_rails = (scene.board_translate[0] if scene.breadboards else 0)
    for net, net_id in net_to_id.items():
        rail_info = power_rail_for_net(scene, net)
        if rail_info is None:
            continue
        bb_idx, rail_id = rail_info
        rails_to_pin.append((bb_idx, rail_id, net_id))
        # Extend to the secondary BBs (= on-BB consumers of the net outside
        # the primary BB). Rail = arduino-side of that BB.
        rail_kind = _NET_TO_RAIL.get(net)
        if rail_kind is None:
            continue
        for other_bb in consumer_bbs_by_net.get(net, set()):
            if other_bb == bb_idx:
                continue
            other_x = scene.breadboard_translates[other_bb][0]
            other_arduino_side = ("left" if other_x > board_x_rails
                                    else "right")
            rails_to_pin.append((other_bb, f"{rail_kind}_{other_arduino_side}",
                                   net_id))

    # R8-4/R8-5: for EACH battery_external of the netlist, declare the
    # V+_<bat_side> rail as pin_owner of the net + of this battery
    # (BAT_5V, BAT_5V_2, ...) and the GND_<bat_side> rail as pin_owner
    # of the GND net. The host BB is computed per battery (= 1st BB with
    # an on-BB consumer of the + net, otherwise BB 0). Without this set_pin, the
    # bat-side rail cells stay body_mask=1 (hard-blocked hole cells)
    # and A* cannot use them.
    if scene.breadboards:
        consumers_by_net: dict[str, set[int]] = {}
        placed_by_ref = {pc.component_ref: pc for pc in scene.placed_components}
        for c in netlist:
            ref = c.get("ref")
            placed = placed_by_ref.get(ref) if ref else None
            if placed is None or placed.breadboard_idx < 0:
                continue
            for p in c.get("pins", []):
                net = p.get("net")
                if net:
                    consumers_by_net.setdefault(net, set()).add(
                        placed.breadboard_idx)
        board_x = scene.board_translate[0]
        for c in netlist:
            if c.get("type") != "battery_external":
                continue
            plus_net = None
            for p in c.get("pins", []):
                if p.get("name") == "+":
                    plus_net = p.get("net")
                    break
            if not plus_net or plus_net not in net_to_id:
                continue
            bbs_used = sorted(consumers_by_net.get(plus_net, set()))
            if not bbs_used:
                bbs_used = sorted(consumers_by_net.get("GND", set()))
            host_bb_idx = bbs_used[0] if bbs_used else 0
            bb_x = scene.breadboard_translates[host_bb_idx][0]
            arduino_side = "left" if bb_x > board_x else "right"
            bat_side = "right" if arduino_side == "left" else "left"
            rails_to_pin.append((host_bb_idx, f"V+_{bat_side}",
                                  net_to_id[plus_net]))
            if "GND" in net_to_id:
                rails_to_pin.append((host_bb_idx, f"GND_{bat_side}",
                                      net_to_id["GND"]))

    for bb_idx, rail_id, net_id in rails_to_pin:
        bb = scene.breadboards[bb_idx]
        bb_tx, bb_ty = scene.breadboard_translates[bb_idx]
        for row in range(1, bb.rows + 1):
            try:
                cx, cy = bb.hole_position(rail_id, row)
            except (KeyError, ValueError):
                continue
            grid.set_pin(cx + bb_tx, cy + bb_ty, net_id,
                          radius_cells=1)

    # 6. Mark the Arduino board pins for the nets concerned.
    #    The SVG markers of the Arduino pins are INSIDE the body bbox
    #    (at the center of the pin header holes). So that A* can exit them,
    #    we carve a channel toward the NEAREST body edge — same
    #    convention as v2 (`_path_around_board` exits laterally when
    #    the pins are on the LEFT/RIGHT flanks of the board, vertically
    #    otherwise). The channel is marked pin_owner of the net (= reserved for this net,
    #    prevents another wire from taking the same channel).
    board_cx = (bx_min + bx_max) / 2.0
    board_cy = (by_min + by_max) / 2.0
    arduino_nets_marked: set[str] = set()
    for net in net_to_id:
        if net in arduino_nets_marked:
            continue
        board_fn = _resolve_board_pin(scene.board_loader, net)
        if board_fn is None:
            continue
        net_id = net_to_id[net]
        board_xy = scene.board_loader.pin_position(
            board_fn, translate=scene.board_translate
        )
        px, py = board_xy
        grid.set_pin(px, py, net_id, radius_cells=PIN_RADIUS_CELLS_ARDUINO)

        # Distance to each body edge: we exit by the nearest one
        d_left = px - bx_min
        d_right = bx_max - px
        d_top = py - by_min
        d_bottom = by_max - py
        d_min = min(d_left, d_right, d_top, d_bottom)
        if d_min == d_left:
            exit_x, exit_y = bx_min - 2, py            # left
            channel_axis = "horizontal"
        elif d_min == d_right:
            exit_x, exit_y = bx_max + 2, py            # right
            channel_axis = "horizontal"
        elif d_min == d_top:
            exit_x, exit_y = px, by_min - 2            # top
            channel_axis = "vertical"
        else:
            exit_x, exit_y = px, by_max + 2            # bottom
            channel_axis = "vertical"

        grid.carve_channel(px, py, exit_x, exit_y, half_width=0)
        # Mark all the cells of the channel as pin_owner of the net
        # (otherwise another net could take it)
        col_pin, row_pin = grid.canvas_to_cell(px, py)
        col_exit, row_exit = grid.canvas_to_cell(exit_x, exit_y)
        if channel_axis == "vertical":
            r_lo, r_hi = min(row_pin, row_exit), max(row_pin, row_exit)
            for r in range(r_lo, r_hi + 1):
                if 0 <= r < grid.rows:
                    grid.pin_owner[r, col_pin] = net_id
        else:
            c_lo, c_hi = min(col_pin, col_exit), max(col_pin, col_exit)
            for c in range(c_lo, c_hi + 1):
                if 0 <= c < grid.cols:
                    grid.pin_owner[row_pin, c] = net_id
        arduino_nets_marked.add(net)

    # Snapshot body_mask AFTER step 5+5b+6 (= after ALL the endpoint
    # clearing: component pins, wire_entry, rails, Arduino pins,
    # carve_channels). Cells:
    #   - BB holes: body_mask=1 (step 3a, never cleared)
    #   - off-BB bodies: body_mask=1 (step 4), except carve channels (0)
    #   - on-BB DIP bodies: body_mask=1 (step 4b extended)
    #   - endpoints, channels, Arduino pins: body_mask=0
    # Used for the restore in step 7 to undo the `allow`s that would have
    # incorrectly cleared body_mask=0 in the bodies/holes zones.
    body_snapshot = grid.body_mask.copy()

    # Manual overrides from assets/wiring/manual_zones.json (no-op if absent).
    # Applied last so that the user can force body_mask=1
    # (forbid) on zones that the previous steps left free,
    # or clear (allow) a body_mask=1 if needed. Translated onto the first BB.
    if scene.breadboard_translates:
        from .manual_zones_json import apply_manual_zones_json
        bb_t = scene.breadboard_translates[0]
        apply_manual_zones_json(grid, bb_translate=(bb_t[0], bb_t[1]))

    # 7. Restore the cells originally body_mask=1 (snapshot).
    #    The allow zones of manual_zones can wrongly clear body_mask
    #    in the bodies zones (DIP chip silhouette, off-BB body) or
    #    BB holes. The restore via max(current, snapshot) preserves
    #    the carve channels (snapshot=0) and the endpoints (snapshot=0)
    #    while re-blocking the bodies/holes (snapshot=1).
    grid.body_mask = np.maximum(grid.body_mask, body_snapshot)

    return grid, net_to_id


_TIESTRIP_LEFT = set("abcde")
_TIESTRIP_RIGHT = set("fghij")


def _tiestrip_key(placed: PlacedComponent, pin_idx: int
                   ) -> tuple[int, str, int] | None:
    """Electrical equivalence key for an on-BB pin placed on a tie-strip.

    2 pins on the SAME key (= same BB + same L/R half + same row) are
    electrically equivalent via the BB tie-strip: a single wire
    suffices to connect them all. Returns None for off-BB pins or
    pins placed on a V+/GND rail (not in cols a-j).

    Taken from the v2 dedup in `layout.routing.py` (cf section "Dedup by
    tie-strip").
    """
    if placed.breadboard_idx < 0:
        return None
    hole = placed.pin_to_hole.get(pin_idx)
    if hole is None:
        return None
    col_id, row = hole
    if col_id in _TIESTRIP_LEFT:
        return (placed.breadboard_idx, "L", row)
    if col_id in _TIESTRIP_RIGHT:
        return (placed.breadboard_idx, "R", row)
    return None


def extract_net_endpoints(scene: PlacedScene, netlist: list[dict],
                           grid: OccupancyGrid,
                           net_to_id: dict[str, int]
                           ) -> dict[str, NetEndpoints]:
    """For each net, extracts the source and target cells in the grid.

    Convention:
      - If the net has an Arduino board pin: source = Arduino cell,
        targets = all the other pins of the net (components)
      - Otherwise (internal net between components): source = first pin,
        targets = other pins
      - Nets with a single pin (orphan): skip

    Tie-strip dedup: 2 on-BB pins on the same tie-strip (= same BB,
    same L/R half, same row) are electrically equivalent via the
    BB itself. We keep only 1 target per tie-strip (otherwise
    we would draw a redundant wire that brings no electrical
    connection and violates R5 by superposition at the T point). Behavior
    taken from v2 `layout.routing.py`.
    """
    netlist_by_ref = {c["ref"]: c for c in netlist}
    # For each net: list of (canvas_xy, tiestrip_key) — the key is
    # None for off-BB or rail pins.
    net_pins: dict[str, list[tuple[tuple[float, float],
                                     tuple[int, str, int] | None]]] = {}

    # 1. Collect the endpoint canvas positions per net (components).
    #    On-BB: entry hole (Rule 4). Off-BB: component pin.
    for placed in scene.placed_components:
        comp = netlist_by_ref.get(placed.component_ref)
        if comp is None:
            continue
        for pin in comp.get("pins", []):
            net = pin.get("net", "")
            if not net or net not in net_to_id:
                continue
            pin_idx = _name_to_pin_index(placed.catalog_entry, pin["name"])
            if pin_idx is None:
                continue
            endpoint_xy = _endpoint_canvas(scene, placed, pin_idx)
            if endpoint_xy is None:
                continue
            ts_key = _tiestrip_key(placed, pin_idx)
            net_pins.setdefault(net, []).append((endpoint_xy, ts_key))

    # 2. For each net, determine whether an Arduino pin exists
    arduino_pin_per_net: dict[str, tuple[float, float]] = {}
    for net in net_to_id:
        board_fn = _resolve_board_pin(scene.board_loader, net)
        if board_fn is None:
            continue
        arduino_pin_per_net[net] = scene.board_loader.pin_position(
            board_fn, translate=scene.board_translate
        )

    # 3. Build NetEndpoints by deduping per tie-strip.
    endpoints: dict[str, NetEndpoints] = {}
    for net, pins_with_keys in net_pins.items():
        net_id = net_to_id[net]
        # Dedup: keep the 1st pin per tie-strip key (the pins with
        # key=None are all kept, = no dedup for off-BB/rail).
        seen_keys: set[tuple[int, str, int]] = set()
        deduped: list[tuple[float, float]] = []
        for xy, key in pins_with_keys:
            if key is not None and key in seen_keys:
                continue
            if key is not None:
                seen_keys.add(key)
            deduped.append(xy)
        ne = NetEndpoints(net=net, net_id=net_id)
        arduino_xy = arduino_pin_per_net.get(net)
        if arduino_xy is not None:
            ne.sources = [grid.canvas_to_cell(*arduino_xy)]
            ne.targets = [grid.canvas_to_cell(*p) for p in deduped]
        else:
            if len(deduped) >= 2:
                ne.sources = [grid.canvas_to_cell(*deduped[0])]
                ne.targets = [grid.canvas_to_cell(*p) for p in deduped[1:]]
            else:
                # orphan pin, skip
                continue
        if ne.sources and ne.targets:
            endpoints[net] = ne

    return endpoints
