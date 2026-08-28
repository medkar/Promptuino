"""Tests unitaires A* sur OccupancyGrid (Phase 1 squelette)."""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.routing.grid import OccupancyGrid
from ui.wiring.routing.astar import astar, compress_collinear


def test_astar_trivial_same_cell():
    g = OccupancyGrid(40, 40, cell_size=4)
    path = astar(g, sources=[(5, 5)], targets=[(5, 5)], net_id=1)
    assert path == [(5, 5)]
    print("  [OK] trivial same-cell")


def test_astar_straight_line_no_obstacle():
    g = OccupancyGrid(40, 40, cell_size=4)
    path = astar(g, sources=[(0, 5)], targets=[(9, 5)], net_id=1)
    assert path is not None
    assert path[0] == (0, 5)
    assert path[-1] == (9, 5)
    # Le chemin doit etre horizontal (10 cellules en ligne)
    assert len(path) == 10
    # Tous a row=5
    assert all(r == 5 for _, r in path)
    print(f"  [OK] ligne droite ({len(path)} cellules)")


def test_astar_prefers_straight_over_zigzag():
    """Avec un cout virage eleve, A* doit prendre la L-shape min."""
    g = OccupancyGrid(40, 40, cell_size=4)
    path = astar(g, sources=[(0, 0)], targets=[(9, 9)], net_id=1, turn_penalty=8)
    assert path is not None
    # Doit etre une L (2 segments droits) = 1 seul virage
    compressed = compress_collinear(path)
    # 3 points pour une L : start, corner, end
    assert len(compressed) == 3, f"path attendu en L (3 pts), recu {len(compressed)} pts: {compressed}"
    print(f"  [OK] prefer straight (compressed {len(compressed)} pts)")


def test_astar_avoids_blocked_body():
    """Obstacle partiel sur la ligne directe : A* doit contourner par-dessus."""
    g = OccupancyGrid(80, 40, cell_size=4)
    # Bloque col=10 sur les rows 3..7 (laisse rows 0..2 et 8..9 libres)
    for r in range(3, 8):
        g.body_mask[r, 10] = 1
    # Source et target a row=5 (au milieu du mur) : doit contourner
    path = astar(g, sources=[(5, 5)], targets=[(15, 5)], net_id=1)
    assert path is not None
    # Aucune cellule du path n'est dans la zone bloquee
    for c, r in path:
        assert g.body_mask[r, c] != 1, f"path traverse une cellule bloquee : ({c},{r})"
    # Path doit passer par row<3 ou row>7 (au moins une cellule)
    rows_visited = {r for _, r in path}
    assert any(r < 3 or r > 7 for r in rows_visited), \
        f"contour attendu mais path reste dans la zone bloquee : rows={sorted(rows_visited)}"
    print(f"  [OK] avoid blocked column ({len(path)} cellules)")


def test_astar_passes_through_target_pin():
    """Target a pin_owner = autre net : doit etre traversable comme endpoint."""
    g = OccupancyGrid(40, 40, cell_size=4)
    # Target marque comme pin du net 5
    g.set_pin(20, 20, net_id=5)
    # On route le net 5 jusqu'au target
    path = astar(g, sources=[(0, 5)], targets=[(5, 5)], net_id=5)
    assert path is not None
    assert path[-1] == (5, 5)
    print("  [OK] pin endpoint accepted as target")


def test_astar_blocks_by_other_net_pin():
    """Une cellule pin_owner=autre_net doit etre infranchissable."""
    g = OccupancyGrid(40, 40, cell_size=4)
    # Bloque la cellule (5, 5) avec un pin du net 99
    g.pin_owner[5, 5] = 99
    # Net 1 tente de passer par dessus en allant tout droit
    path = astar(g, sources=[(0, 5)], targets=[(9, 5)], net_id=1)
    assert path is not None
    # Doit contourner (5, 5) -> path ne contient pas (5, 5)
    assert (5, 5) not in path
    print(f"  [OK] blocked by other-net pin ({len(path)} cellules)")


def test_astar_returns_none_if_isolated():
    """Target totalement isole par des bodies : pas de chemin."""
    g = OccupancyGrid(40, 40, cell_size=4)
    # Encadre la cellule (5, 5) par des bodies sur les 4 voisines
    for c, r in [(4, 5), (6, 5), (5, 4), (5, 6)]:
        g.body_mask[r, c] = 1
    path = astar(g, sources=[(0, 0)], targets=[(5, 5)], net_id=1, max_expansions=10000)
    assert path is None
    print("  [OK] none if isolated")


def test_compress_collinear():
    # 5 points en ligne -> 2 points (debut, fin)
    p = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]
    c = compress_collinear(p)
    assert c == [(0, 0), (4, 0)]
    # L-shape : 3 points (start, corner, end)
    p = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]
    c = compress_collinear(p)
    assert c == [(0, 0), (2, 0), (2, 2)]
    print("  [OK] compress_collinear")


def main() -> int:
    print("[test_wiring_routing_astar]\n")
    tests = [
        test_astar_trivial_same_cell,
        test_astar_straight_line_no_obstacle,
        test_astar_prefers_straight_over_zigzag,
        test_astar_avoids_blocked_body,
        test_astar_passes_through_target_pin,
        test_astar_blocks_by_other_net_pin,
        test_astar_returns_none_if_isolated,
        test_compress_collinear,
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
