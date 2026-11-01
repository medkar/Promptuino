"""Tests unitaires manual_zones_json : load JSON + apply a OccupancyGrid."""
from __future__ import annotations

import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.routing.grid import OccupancyGrid
from ui.wiring.routing.manual_zones_json import apply_manual_zones_json


def _make_json(tmp: Path, **overrides) -> Path:
    # Defaut : bb_anchor (0, 0) pour eviter offset dans la majorite des
    # tests (= comportement "old-school" sans alignement). Les tests qui
    # exercent l'offset le redefinissent explicitement.
    data = {
        "version": 1,
        "cell_size": 8,
        "bb_anchor": {"x": 0, "y": 0},
        "bb_svg": "assets/wiring/breadboards/mini.svg",
        "cost_value": 60,
        "cells": {
            "forbid": [[10, 20]],
            "cost":   [[5, 5]],
            "allow":  [[0, 0]],
        },
    }
    data.update(overrides)
    path = tmp / "manual.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_noop_when_file_missing():
    grid = OccupancyGrid(canvas_w=200, canvas_h=200, cell_size=8)
    counts = apply_manual_zones_json(grid, Path("/tmp/does_not_exist_xyz.json"))
    assert counts == {"forbid": 0, "cost": 0, "allow": 0}


def test_apply_forbid():
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_json(Path(tmp), cells={"forbid": [[5, 7]], "cost": [], "allow": []})
        grid = OccupancyGrid(canvas_w=200, canvas_h=200, cell_size=8)
        counts = apply_manual_zones_json(grid, path)
        assert counts["forbid"] == 1
        # Cell (5, 7) at cell_size=8 -> canvas (40, 56), 1 cell wide.
        # blit_body marque body_mask[row=7, col=5] = 1
        assert grid.body_mask[7, 5] == 1


def test_apply_cost():
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_json(
            Path(tmp),
            cost_value=80,
            cells={"forbid": [], "cost": [[3, 3]], "allow": []},
        )
        grid = OccupancyGrid(canvas_w=200, canvas_h=200, cell_size=8)
        counts = apply_manual_zones_json(grid, path)
        assert counts["cost"] == 1
        assert grid.cost_map[3, 3] == 80


def test_apply_allow_overrides_forbid():
    """allow ecrit body_mask=0 par-dessus une cellule pre-existante."""
    grid = OccupancyGrid(canvas_w=200, canvas_h=200, cell_size=8)
    # Marque manuellement body[5,5] = 1
    grid.body_mask[5, 5] = 1
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_json(
            Path(tmp),
            cells={"forbid": [], "cost": [], "allow": [[5, 5]]},
        )
        counts = apply_manual_zones_json(grid, path)
        assert counts["allow"] == 1
        assert grid.body_mask[5, 5] == 0


def test_apply_with_bb_translate():
    """Les cellules JSON sont relatives a bb_translate ; la grille
    doit etre marquee a bb_translate + cell."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_json(
            Path(tmp),
            cells={"forbid": [[2, 3]], "cost": [], "allow": []},
        )
        # cell_size=8, bb_translate=(40, 80) -> canvas (40 + 2*8, 80 + 3*8) = (56, 104)
        # -> row 13, col 7
        grid = OccupancyGrid(canvas_w=500, canvas_h=500, cell_size=8)
        apply_manual_zones_json(grid, path, bb_translate=(40, 80))
        assert grid.body_mask[13, 7] == 1
        # Pas touche ailleurs
        assert grid.body_mask[3, 2] == 0


def test_cell_size_mismatch_allowed():
    """cell_size editor peut differer de grid.cell_size : la grille routing
    fait son propre rounding via blit_body. 1 cellule editor 4x4 peinte
    marque 1+ cellule(s) OG 8x8."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_json(
            Path(tmp),
            cell_size=4,
            cells={"forbid": [[6, 8]], "cost": [], "allow": []},
        )
        grid = OccupancyGrid(canvas_w=200, canvas_h=200, cell_size=8)
        counts = apply_manual_zones_json(grid, path)
        assert counts["forbid"] == 1
        # cell editor (6, 8) cs=4 -> canvas rect (24, 32, 4, 4)
        # OG cs=8 -> col 3 (24/8=3), row 4 (32/8=4)
        assert grid.body_mask[4, 3] == 1


def test_bb_anchor_offset_applied():
    """Avec bb_anchor (30, 30) et cs=8, offset = 2. Cell (3, 3) editor
    -> canvas rect (2 + 24, 2 + 24, 8, 8) = (26, 26, 8, 8).
    OG cs=8 -> marque cols 3-4 et rows 3-4 (4 cellules)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_json(
            Path(tmp),
            bb_anchor={"x": 30, "y": 30},
            cells={"forbid": [[3, 3]], "cost": [], "allow": []},
        )
        grid = OccupancyGrid(canvas_w=200, canvas_h=200, cell_size=8)
        apply_manual_zones_json(grid, path)
        # Centre de la cellule editor est a canvas (30, 30) = premier trou BB
        # 4 cells OG touchees (rect chevauche frontiere de cellules OG)
        assert grid.body_mask[3, 3] == 1
        assert grid.body_mask[3, 4] == 1
        assert grid.body_mask[4, 3] == 1
        assert grid.body_mask[4, 4] == 1


def test_malformed_entries_ignored():
    """Une entree mal formee (pas une liste de 2) est ignoree, pas raise."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_json(
            Path(tmp),
            cells={
                "forbid": [[1, 1], "garbage", [2]],
                "cost": [],
                "allow": [],
            },
        )
        grid = OccupancyGrid(canvas_w=200, canvas_h=200, cell_size=8)
        counts = apply_manual_zones_json(grid, path)
        assert counts["forbid"] == 1  # seul [1, 1] passe


def main() -> int:
    tests = [
        test_noop_when_file_missing,
        test_apply_forbid,
        test_apply_cost,
        test_apply_allow_overrides_forbid,
        test_apply_with_bb_translate,
        test_cell_size_mismatch_allowed,
        test_bb_anchor_offset_applied,
        test_malformed_entries_ignored,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  [OK]   {fn.__name__}")
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERR]  {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
