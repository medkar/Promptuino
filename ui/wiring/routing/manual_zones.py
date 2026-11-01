"""Parses an annotated SVG containing layers for manual editing of
occupancy zones, and applies the overrides to an OccupancyGrid.

Layers expected in the SVG:
  - manual-forbid    : <rect> -> force body_mask = 1
  - manual-allow     : <rect> -> force body_mask = 0 (override allowed)
  - manual-cost      : <rect data-cost="N"> -> set_max_cost(N) on the zone
  - manual-pin-owner : <rect data-net="GND"> -> pin_owner = corresponding net_id

Convention: the <rect> in these layers have x, y, width, height in canvas
pixels (= same coordinates as the generated SVG). No transform/rotation
to keep it simple (Inkscape by default produces rects without transform
if drawn with the basic Rectangle tool).

Typical usage:
    grid, net_to_id = build_occupancy_grid(scene, netlist, cell_size=8)
    apply_manual_zones(grid, net_to_id, Path("path/to/manual_zones.svg"))
    # Continue with extract_net_endpoints + route_wires...
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .grid import OccupancyGrid

NS = {"svg": "http://www.w3.org/2000/svg"}

# Recognized layers with their action on the grid
_LAYER_IDS = ("manual-forbid", "manual-allow", "manual-cost", "manual-pin-owner")


def _parse_rect(rect: ET.Element) -> tuple[float, float, float, float] | None:
    """Extracts (x, y, w, h) from a <rect> element. Returns None if invalid."""
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


def parse_manual_zones(svg_path: Path) -> dict[str, list[dict]]:
    """Parses the SVG and returns a dict {layer_id: [{rect, attrs}, ...]}.

    For each <rect> in a recognized layer, captures (x, y, w, h) + the
    `data-*` attributes (= metadata passed by the user, e.g.
    data-cost="60", data-net="GND").
    """
    if not svg_path.exists():
        return {lid: [] for lid in _LAYER_IDS}
    tree = ET.parse(svg_path)
    root = tree.getroot()
    result: dict[str, list[dict]] = {lid: [] for lid in _LAYER_IDS}
    for layer_id in _LAYER_IDS:
        # We accept the direct id OR the Inkscape label (inkscape:label)
        g = root.find(f".//svg:g[@id='{layer_id}']", NS)
        if g is None:
            continue
        for rect in g.findall("svg:rect", NS):
            parsed = _parse_rect(rect)
            if parsed is None:
                continue
            x, y, w, h = parsed
            attrs: dict[str, str] = {}
            for k, v in rect.attrib.items():
                if k.startswith("data-"):
                    attrs[k] = v
            result[layer_id].append({"rect": (x, y, w, h), "attrs": attrs})
    return result


def apply_manual_zones(grid: OccupancyGrid,
                        net_to_id: dict[str, int],
                        svg_path: Path) -> dict[str, int]:
    """Applies the overrides of the annotated SVG to the grid.

    Returns a dict {layer_id: count} indicating how many zones were
    applied per layer (for log/debug).
    """
    zones = parse_manual_zones(svg_path)
    counts: dict[str, int] = {lid: 0 for lid in _LAYER_IDS}

    # manual-forbid: body_mask = 1 on the zone
    for entry in zones["manual-forbid"]:
        x, y, w, h = entry["rect"]
        grid.blit_body(x, y, w, h, value=1)
        counts["manual-forbid"] += 1

    # manual-allow: body_mask = 0 on the zone (hard-block override).
    # blit_body with value=0 writes 0, but we want to explicitly *clear*
    # whatever the current value is. blit_body does `[sl] = value`
    # so value=0 works.
    for entry in zones["manual-allow"]:
        x, y, w, h = entry["rect"]
        grid.blit_body(x, y, w, h, value=0)
        counts["manual-allow"] += 1

    # manual-cost: set_max_cost with data-cost (default 60)
    for entry in zones["manual-cost"]:
        x, y, w, h = entry["rect"]
        try:
            cost = int(entry["attrs"].get("data-cost", "60"))
        except ValueError:
            cost = 60
        grid.set_max_cost(x, y, w, h, cost)
        counts["manual-cost"] += 1

    # manual-pin-owner: marks the cells of the zone with pin_owner=net_id
    # (lookup via data-net="GND" -> net_to_id["GND"])
    for entry in zones["manual-pin-owner"]:
        x, y, w, h = entry["rect"]
        net_name = entry["attrs"].get("data-net", "")
        net_id = net_to_id.get(net_name)
        if net_id is None:
            # Unknown net: skip but log
            print(f"[manual_zones] skip pin-owner rect ({x},{y},{w},{h}) : "
                  f"net '{net_name}' absent du netlist")
            continue
        # We use blit_body(value=0) to clear body_mask, then set
        # pin_owner cell-by-cell. (set_pin has no rect API;
        # we inline the slicing to avoid touching grid.py.)
        sl = grid._canvas_rect_to_cell_slice(x, y, w, h)
        if sl is None:
            continue
        row_slice, col_slice = sl
        grid.body_mask[row_slice, col_slice] = 0
        grid.pin_owner[row_slice, col_slice] = net_id
        counts["manual-pin-owner"] += 1

    return counts
