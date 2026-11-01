"""Pure logic for the Level 1 highlight of the interactive schematic.

No Qt dependency. Reentrant functions, testable in isolation via
scripts/test_highlight_logic.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .netlist import Component, Netlist
    from .layout.routing import Wire


_POWER_NET_EXACT = {"GND", "5V", "3V3", "VCC", "VIN"}
_POWER_NET_PREFIXES = ("BAT_",)


def is_power_net(net: str) -> bool:
    """True if the net is a power rail (GND, 5V, 3V3, BAT_*, VCC)."""
    if not net:
        return False
    if net in _POWER_NET_EXACT:
        return True
    return net.startswith(_POWER_NET_PREFIXES)


def compute_highlight_sets(
    component: "Component",
    netlist: "Netlist",
    wires: list["Wire"],
    board_pin_nets: dict[str, str] | None = None,
    pin_positions: dict[tuple[str, str], tuple[float, float]] | None = None,
    rail_strips: list[tuple[float, float, float]] | None = None,
    source_bboxes: list[tuple[float, float, float, float]] | None = None,
) -> tuple[set[str], set[int]]:
    """Returns (hi_component_refs, hi_wire_indices) on click of `component`.

    Algorithm: BFS over the netlist graph from `component`. Cascades
    through signal nets (two components sharing a signal net are
    electrically connected, so we highlight them together).
    For power nets (GND/5V/3V3/VIN/BAT_*), we do NOT cascade
    (otherwise clicking a LED highlights all GND consumers). Instead,
    `trace_to_source` is called to trace only the local cluster + the
    rail-to-source extension (Arduino/battery).

    `board_pin_nets`: mapping {pin_label: net} for the Arduino board
    pins. Used to know whether a net reaches the board.

    `pin_positions`: mapping {(ref, pin_name): (x, y)} of the canvas
    coords of the pins of ALL components. Used by trace_to_source to
    seed the BFS on the right cluster (multi-cluster power nets).

    `rail_strips`: list of BB rails as (x_canvas, y_top, y_bot).
    Enables the rail-aware extension in `trace_to_source`.

    `source_bboxes`: list of source bboxes (Arduino + external
    batteries) as (x_min, y_min, x_max, y_max). Limits the rail-aware
    extension to wires that go toward a source.
    """
    hi_components: set[str] = {component.ref}
    hi_wires: set[int] = set()
    board_pin_nets = board_pin_nets or {}
    pin_positions = pin_positions or {}
    queue: list["Component"] = [component]

    while queue:
        c = queue.pop(0)
        for pin in c.pins:
            net = pin.net
            if not net or net == "?":
                continue

            if is_power_net(net):
                seed_xy = pin_positions.get((c.ref, pin.name))
                chain, source_ref = trace_to_source(
                    net, netlist, wires, board_pin_nets,
                    seed_xy=seed_xy,
                    rail_strips=rail_strips,
                    source_bboxes=source_bboxes,
                )
                hi_wires.update(chain)
                if source_ref == "board":
                    hi_components.add("board")
                elif source_ref is not None:
                    hi_components.add(source_ref)
                # No cascade through a power net.
            else:
                # Signal: all wires of the net + cascade to consumers.
                for k, w in enumerate(wires):
                    if w.net == net:
                        hi_wires.add(k)
                if net in board_pin_nets.values():
                    hi_components.add("board")
                for other in netlist.components:
                    if other.ref in hi_components:
                        continue
                    if any(p.net == net for p in other.pins):
                        hi_components.add(other.ref)
                        queue.append(other)

    return hi_components, hi_wires


def trace_to_source(
    net: str,
    netlist: "Netlist",
    wires: list["Wire"],
    board_pin_nets: dict[str, str] | None = None,
    seed_xy: tuple[float, float] | None = None,
    rail_strips: list[tuple[float, float, float]] | None = None,
    source_bboxes: list[tuple[float, float, float, float]] | None = None,
) -> tuple[set[int], str | None]:
    """Geometric flood-fill over the wires sharing `net`.

    Returns (visited_wires, source_ref). source_ref is:
      - "board" if `net` is in `board_pin_nets.values()`;
      - otherwise the ref of a component of type `battery_external`
        with a pin on this net;
      - otherwise None.

    The flood-fill starts from the seed wire and extends to wires of the
    same net having at least one endpoint close (< EPSILON) to an
    already-visited endpoint. The seed is chosen:
      - if `seed_xy` is provided, the wire whose endpoint is closest
        to `seed_xy`;
      - otherwise `same_net_idxs[0]` (legacy heuristic).

    Rail-aware extension (optional): when `rail_strips` and
    `source_bboxes` are provided, we add to the cluster the wires of the
    same net having one endpoint on a rail touched by the current
    cluster AND the other endpoint inside a source bbox. Allows tracing
    "GND rail -> Arduino" (or "BAT_5V rail -> battery") without adding
    the wires of the other consumers of the rail.
    """
    board_pin_nets = board_pin_nets or {}
    EPSILON = 0.5

    same_net_idxs = [k for k, w in enumerate(wires) if w.net == net]
    if not same_net_idxs:
        return set(), None

    # Identify the possible source: board (if net in board_pin_nets)
    # or battery_external (if a pin matches the net).
    source_ref: str | None = None
    if net in board_pin_nets.values():
        source_ref = "board"
    else:
        for c in netlist.components:
            if c.type == "battery_external":
                if any(p.net == net for p in c.pins):
                    source_ref = c.ref
                    break

    def _endpoints(w: "Wire") -> list[tuple[float, float]]:
        if not w.path:
            return []
        return [w.path[0], w.path[-1]]

    def _close(p1: tuple[float, float], p2: tuple[float, float]) -> bool:
        return abs(p1[0] - p2[0]) < EPSILON and abs(p1[1] - p2[1]) < EPSILON

    # Seed choice: if seed_xy is provided, take the wire (among those of
    # the net) whose endpoint is closest. Otherwise, the 1st wire of the net.
    if seed_xy is not None:
        def _dist2(p: tuple[float, float]) -> float:
            return (p[0] - seed_xy[0]) ** 2 + (p[1] - seed_xy[1]) ** 2
        seed_idx = min(
            same_net_idxs,
            key=lambda k: min((_dist2(p) for p in _endpoints(wires[k])),
                              default=float("inf")),
        )
    else:
        seed_idx = same_net_idxs[0]

    # Heuristic: we consider that ALL wires of the net that are
    # connected by their endpoints form 1 cluster. We start with the
    # seed and extend.
    visited: set[int] = {seed_idx}
    frontier_endpoints: list[tuple[float, float]] = list(
        _endpoints(wires[seed_idx])
    )
    changed = True
    while changed:
        changed = False
        for k in same_net_idxs:
            if k in visited:
                continue
            w_endpoints = _endpoints(wires[k])
            for we in w_endpoints:
                if any(_close(we, fe) for fe in frontier_endpoints):
                    visited.add(k)
                    frontier_endpoints.extend(w_endpoints)
                    changed = True
                    break

    # Rail-aware extension toward the sources.
    if rail_strips and source_bboxes:
        EPS_RAIL_X = 1.0
        EPS_RAIL_Y = 1.0

        def _on_strip(p: tuple[float, float],
                      strip: tuple[float, float, float]) -> bool:
            x_s, y_top, y_bot = strip
            return (abs(p[0] - x_s) < EPS_RAIL_X
                    and y_top - EPS_RAIL_Y <= p[1] <= y_bot + EPS_RAIL_Y)

        def _in_bbox(p: tuple[float, float],
                     bbox: tuple[float, float, float, float]) -> bool:
            x_min, y_min, x_max, y_max = bbox
            return x_min <= p[0] <= x_max and y_min <= p[1] <= y_max

        ext_changed = True
        while ext_changed:
            ext_changed = False
            # Identify the rails touched by the current cluster.
            touched_strips: list[tuple[float, float, float]] = []
            for k in visited:
                for ep in _endpoints(wires[k]):
                    for strip in rail_strips:
                        if _on_strip(ep, strip) and strip not in touched_strips:
                            touched_strips.append(strip)

            for k in same_net_idxs:
                if k in visited:
                    continue
                ends = _endpoints(wires[k])
                if not ends:
                    continue
                on_touched = [
                    any(_on_strip(ep, s) for s in touched_strips)
                    for ep in ends
                ]
                if not any(on_touched):
                    continue
                # 2 cases for adding:
                #  (a) rail-to-rail bridge: both endpoints are on a
                #      rail (so the wire extends the bus, e.g. jumper
                #      GND_left <-> GND_right between the 2 BB sides);
                #  (b) toward source: the other endpoint is in a source
                #      bbox (Arduino PCB or battery).
                on_any_rail = [
                    any(_on_strip(ep, s) for s in rail_strips)
                    for ep in ends
                ]
                if all(on_any_rail):
                    visited.add(k)
                    ext_changed = True
                    continue
                other_idx = 0 if not on_touched[0] else 1
                if any(_in_bbox(ends[other_idx], b) for b in source_bboxes):
                    visited.add(k)
                    ext_changed = True

    return visited, source_ref
