"""Tests unitaires OccupancyGrid (Phase 1 squelette)."""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Ensure ui is importable as a package
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.routing.grid import OccupancyGrid


def test_grid_shape_and_conversions():
    g = OccupancyGrid(canvas_w=200, canvas_h=100, cell_size=4)
    assert g.cols == 50 and g.rows == 25, (g.cols, g.rows)
    # Cell (0, 0) center
    x, y = g.cell_to_canvas(0, 0)
    assert (x, y) == (2.0, 2.0)
    # Roundtrip canvas -> cell
    c, r = g.canvas_to_cell(50, 30)
    assert (c, r) == (12, 7)
    # Clamp negatif et over
    assert g.canvas_to_cell(-10, -10) == (0, 0)
    assert g.canvas_to_cell(1000, 1000) == (49, 24)
    print("  [OK] shape + conversions")


def test_blit_body_marks_cells():
    g = OccupancyGrid(100, 100, cell_size=4)
    # Blit un carre 20x20 a (40, 40) -> cellules (10..14, 10..14)
    g.blit_body(40, 40, 20, 20, value=1)
    assert g.body_mask[10, 10] == 1
    assert g.body_mask[14, 14] == 1
    # Hors region : 0
    assert g.body_mask[9, 10] == 0
    assert g.body_mask[15, 15] == 0
    print("  [OK] blit_body mark")


def test_blit_body_clamps_to_grid():
    g = OccupancyGrid(100, 100, cell_size=4)
    # Region partiellement hors grille
    g.blit_body(-20, 80, 40, 40, value=1)
    # Doit avoir touche les cellules valides sans crasher
    assert g.body_mask[20:25, 0:5].sum() > 0
    print("  [OK] blit_body clamp")


def test_set_pin_radius():
    g = OccupancyGrid(100, 100, cell_size=4)
    # Pin a (40, 40) cellule (10, 10) avec radius 2 -> diamant Manhattan
    g.set_pin(40, 40, net_id=42, radius_cells=2)
    # Centre
    assert g.pin_owner[10, 10] == 42
    # Distance Manhattan = 1
    assert g.pin_owner[9, 10] == 42
    assert g.pin_owner[10, 9] == 42
    # Distance Manhattan = 2
    assert g.pin_owner[8, 10] == 42
    # Distance Manhattan = 3 (hors radius)
    assert g.pin_owner[7, 10] == 0
    print("  [OK] set_pin radius")


def test_cost_map_clamps_uint8():
    g = OccupancyGrid(100, 100, cell_size=4)
    g.add_cost(40, 40, 8, 8, 200)
    g.add_cost(40, 40, 8, 8, 200)
    # Doit etre clampe a 255
    assert g.cost_map[10, 10] == 255
    print("  [OK] add_cost clamp uint8")


def test_is_blocked_logic():
    g = OccupancyGrid(40, 40, cell_size=4)
    # Cellule libre
    assert not g.is_blocked(5, 5, net_id=1)
    # Hors grille
    assert g.is_blocked(-1, 5, net_id=1)
    assert g.is_blocked(5, 100, net_id=1)
    # Body bloque
    g.blit_body(20, 20, 4, 4, value=1)
    assert g.is_blocked(5, 5, net_id=1)
    # Pin appartient net 2 -> bloque pour net 1, libre pour net 2
    g2 = OccupancyGrid(40, 40, cell_size=4)
    g2.set_pin(20, 20, net_id=2)
    assert g2.is_blocked(5, 5, net_id=1)
    assert not g2.is_blocked(5, 5, net_id=2)
    print("  [OK] is_blocked")


def test_wire_marking_and_unmarking():
    g = OccupancyGrid(40, 40, cell_size=4)
    cells = [(2, 2), (3, 2), (4, 2)]
    g.mark_wire(cells, net_id=7)
    for c, r in cells:
        assert g.wire_owner[r, c] == 7
    # Le contrat a evolue depuis l'ecriture du test : is_blocked prend un AXE.
    # Regle actuelle (docstring de is_blocked) « les fils se croisent mais ne
    # se superposent pas » :
    #   - meme axe (H ici, le segment est horizontal) -> bloque, SANS exception,
    #     meme pour un fil du MEME net (critere visuel, pas electrique) ;
    #   - axe perpendiculaire -> libre (croisement en « + » propre) ;
    #   - axis=None -> le test de fil est volontairement SAUTE (sources A*).
    assert g.is_blocked(2, 2, net_id=99, axis="H")
    assert g.is_blocked(2, 2, net_id=7, axis="H")
    assert not g.is_blocked(2, 2, net_id=99, axis="V")
    assert not g.is_blocked(2, 2, net_id=7)
    # Unmark
    g.unmark_wire(cells, net_id=7)
    for c, r in cells:
        assert g.wire_owner[r, c] == 0
    print("  [OK] mark/unmark wire")


def test_carve_channel_clears_body():
    g = OccupancyGrid(80, 40, cell_size=4)
    # Bloque tout
    g.blit_body(0, 0, 80, 40, value=1)
    assert g.body_mask[5, 5] == 1
    # Creuse un canal horizontal a y=20
    g.carve_channel(0, 20, 80, 20, half_width=0)
    # La ligne row=5 (y=20) doit etre degagee
    assert g.body_mask[5, 5] == 0
    # Lignes adjacentes restent bloquees
    assert g.body_mask[4, 5] == 1
    print("  [OK] carve_channel")


def test_stats():
    g = OccupancyGrid(40, 40, cell_size=4)
    g.blit_body(0, 0, 8, 8, value=1)
    g.set_pin(20, 20, net_id=3)
    g.mark_wire([(5, 5)], net_id=3)
    s = g.stats()
    assert s.cols == 10 and s.rows == 10
    assert s.blocked_cells == 4  # 2x2 cellules
    assert s.pinned_cells == 1
    assert s.wired_cells == 1
    assert s.free_ratio < 1.0
    print(f"  [OK] stats (free_ratio={s.free_ratio:.3f})")


def main() -> int:
    print("[test_wiring_routing_grid]\n")
    tests = [
        test_grid_shape_and_conversions,
        test_blit_body_marks_cells,
        test_blit_body_clamps_to_grid,
        test_set_pin_radius,
        test_cost_map_clamps_uint8,
        test_is_blocked_logic,
        test_wire_marking_and_unmarking,
        test_carve_channel_clears_body,
        test_stats,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
