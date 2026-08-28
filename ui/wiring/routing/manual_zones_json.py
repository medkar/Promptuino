"""Loads a manual_zones.json produced by the zone editor and applies
the overrides to an OccupancyGrid.

JSON format: see `ui/wiring/routing/zone_editor/zone_store.py`.

Typical usage (after build_occupancy_grid):

    from ui.wiring.routing.manual_zones_json import apply_manual_zones_json
    apply_manual_zones_json(grid, json_path, bb_translate=scene.breadboard_translates[0])

The file is entirely optional: if absent, the call is a silent no-op.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

import numpy as np

from .grid import OccupancyGrid

_ASSETS_WIRING = Path(__file__).resolve().parents[3] / "assets" / "wiring"
# Priority: generalized version if present (= produced by
# scripts/generalize_manual_zones.py after editing the source), otherwise
# source version as-is (= what is painted in the editor).
DEFAULT_JSON_PATH = _ASSETS_WIRING / "manual_zones_generalized.json"
FALLBACK_JSON_PATH = _ASSETS_WIRING / "manual_zones.json"


def apply_manual_zones_json(
    grid: OccupancyGrid,
    json_path: Optional[Path] = None,
    bb_translate: tuple[float, float] = (0.0, 0.0),
) -> dict[str, int]:
    """Reads the JSON and applies the overrides to the grid.

    Returns a dict {"forbid": N, "cost": M, "allow": K} (counters per
    layer). Silent no-op if the file does not exist.

    `bb_translate`: canvas translation of the BB in the scene (= top-left
    of the BB SVG). The JSON cell coords are relative to this origin.
    """
    if json_path is None:
        # Generalized preferred, otherwise raw source
        if DEFAULT_JSON_PATH.exists():
            json_path = DEFAULT_JSON_PATH
        else:
            json_path = FALLBACK_JSON_PATH
    json_path = Path(json_path)
    counts = {"forbid": 0, "cost": 0, "allow": 0}
    if not json_path.exists():
        return counts

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[manual_zones_json] erreur lecture {json_path} : {exc}")
        return counts

    # Trace one-time per process for debug
    global _LOGGED_PATH  # type: ignore[name-defined]
    if "_LOGGED_PATH" not in globals() or _LOGGED_PATH != json_path:
        n = {k: len(v) for k, v in data.get("cells", {}).items()}
        print(f"[manual_zones_json] applique {json_path.name} "
              f"(forbid={n.get('forbid',0)}, cost={n.get('cost',0)}, "
              f"allow={n.get('allow',0)})")
        _LOGGED_PATH = json_path  # type: ignore[name-defined]

    cs_json = int(data.get("cell_size", grid.cell_size))

    # bb_anchor: canvas position (BB-local) of the first hole. Used to align
    # the editor cells (cs_json px) on the centers of the BB holes. The
    # editor grid is shifted by offset = (anchor - cs/2) mod cs.
    # Default = (30, 30) (mini.svg standard).
    anchor_in = data.get("bb_anchor") or {}
    anchor_x = float(anchor_in.get("x", 30.0))
    anchor_y = float(anchor_in.get("y", 30.0))
    cs_e = float(cs_json)
    ox = (anchor_x - cs_e / 2.0) % cs_e
    oy = (anchor_y - cs_e / 2.0) % cs_e

    cost_value = int(data.get("cost_value", 60))
    cells = data.get("cells", {})
    tx, ty = float(bb_translate[0]), float(bb_translate[1])

    def _rect_for(col: int, row: int) -> tuple[float, float, float, float]:
        # Editor cell (col, row) -> canvas rect with BB-anchor offset.
        # NB: the editor cell size (cs_e) may differ from
        # grid.cell_size; blit_body and set_max_cost handle it via
        # _canvas_rect_to_cell_slice (rounding cleared cells of the
        # OccupancyGrid touched by the rect).
        return (tx + ox + col * cs_e, ty + oy + row * cs_e, cs_e, cs_e)

    def _slice_for(x: float, y: float, w: float, h: float):
        """Converts canvas-rect -> (row_slice, col_slice) clamped to the
        grid. Local copy of the OccupancyGrid logic in order to be able to
        apply conditional operations (preserve pin_owner)."""
        if w <= 0 or h <= 0:
            return None
        col_lo = max(0, int(math.floor(x / grid.cell_size)))
        row_lo = max(0, int(math.floor(y / grid.cell_size)))
        col_hi = min(grid.cols, int(math.ceil((x + w) / grid.cell_size)))
        row_hi = min(grid.rows, int(math.ceil((y + h) / grid.cell_size)))
        if col_hi <= col_lo or row_hi <= row_lo:
            return None
        return slice(row_lo, row_hi), slice(col_lo, col_hi)

    # IMPORTANT: cells with pin_owner != 0 are routing endpoints
    # (rails, component pins, Arduino pins). The manual_zones must
    # NOT block them (otherwise the wire can no longer terminate on them).
    # We therefore apply forbid/cost with a "where pin_owner == 0" mask.
    # allow authorizes everything (clear body_mask).
    #
    # APPLICATION ORDER: cost -> allow -> forbid (= forbid wins).
    # Reason for the overlap: editor cells (cs_e=7) can
    # cover 2 adjacent grid cells (cs=6). So 2 neighboring editor
    # entries of different colors can affect the same grid
    # cell. The intuitive rule: red (forbid) > green (allow) > yellow
    # (cost).

    for entry in cells.get("cost", []):
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        x, y, w, h = _rect_for(int(entry[0]), int(entry[1]))
        sl = _slice_for(x, y, w, h)
        if sl is None:
            continue
        row_sl, col_sl = sl
        # Cost ONLY the non-pin cells (the pins keep their current
        # cost to stay accessible at lower cost)
        pin_mask = (grid.pin_owner[row_sl, col_sl] == 0)
        region = grid.cost_map[row_sl, col_sl].copy()
        target = np.maximum(region, np.uint8(cost_value))
        region[pin_mask] = target[pin_mask]
        grid.cost_map[row_sl, col_sl] = region
        counts["cost"] += 1

    # allow: clear body_mask (unblock) AND cost_map (= preferred path).
    # Without clearing cost, A* prefers off-BB detours (cost 0) over the
    # allow channels that kept the R1 cost band (60 per cell).
    for entry in cells.get("allow", []):
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        x, y, w, h = _rect_for(int(entry[0]), int(entry[1]))
        sl = _slice_for(x, y, w, h)
        if sl is None:
            continue
        row_sl, col_sl = sl
        grid.body_mask[row_sl, col_sl] = 0
        grid.cost_map[row_sl, col_sl] = 0
        counts["allow"] += 1

    # forbid LAST: red wins on any editor/grid overlap.
    for entry in cells.get("forbid", []):
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        x, y, w, h = _rect_for(int(entry[0]), int(entry[1]))
        sl = _slice_for(x, y, w, h)
        if sl is None:
            continue
        row_sl, col_sl = sl
        # Forbid ONLY the non-pin cells
        pin_mask = (grid.pin_owner[row_sl, col_sl] == 0)
        region = grid.body_mask[row_sl, col_sl]
        region[pin_mask] = 1
        grid.body_mask[row_sl, col_sl] = region
        counts["forbid"] += 1

    return counts
