"""Tests Phase 2 : build_occupancy_grid sur scenes reelles + A* end-to-end.

Strategie : on construit une grille a partir d'une scene v2 placee (LED
+ resistance), puis on verifie :
  1. La grille a la bonne taille
  2. Les pins Arduino sont marquees
  3. Les pins composants sont marquees
  4. Le corps Arduino est bloque
  5. A* trouve un chemin pour un net signal (Arduino D13 -> consumer)
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.layout.layout import place_scene
from ui.wiring.routing.grid import OccupancyGrid
from ui.wiring.routing.astar import astar, compress_collinear
from ui.wiring.routing.occupancy import (
    build_occupancy_grid, extract_net_endpoints,
    _NET_TO_BOARD_PIN,
)


BOARD_SVG = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"

# Netlist LED + R en serie : 3 nets (D13, NET_LR junction, GND)
# Labels conformes au catalog : LED = A/K, resistor = A/B
NETLIST_LED = [
    {"ref": "D1", "type": "led",
     "pins": [{"name": "A", "net": "NET_LR"},
              {"name": "K", "net": "GND"}]},
    {"ref": "R1", "type": "resistor",
     "pins": [{"name": "A", "net": "D13"},
              {"name": "B", "net": "NET_LR"}]},
]


def test_grid_basic_structure():
    scene = place_scene(NETLIST_LED, BOARD_SVG)
    grid, net_to_id = build_occupancy_grid(scene, NETLIST_LED, cell_size=6)
    # Dimensions: canvas / cell_size, ceil
    expected_cols = int(scene.canvas_size[0] // 6) + (1 if scene.canvas_size[0] % 6 else 0)
    expected_rows = int(scene.canvas_size[1] // 6) + (1 if scene.canvas_size[1] % 6 else 0)
    assert grid.cols == expected_cols, (grid.cols, expected_cols)
    assert grid.rows == expected_rows, (grid.rows, expected_rows)
    # 3 nets alloues
    assert set(net_to_id.keys()) == {"NET_LR", "D13", "GND"}
    # ids dans [1, 3]
    assert sorted(net_to_id.values()) == [1, 2, 3]
    print(f"  [OK] grid {grid.cols}x{grid.rows} cells, 3 nets")


def test_arduino_body_blocked():
    scene = place_scene(NETLIST_LED, BOARD_SVG)
    grid, _ = build_occupancy_grid(scene, NETLIST_LED, cell_size=6)
    # Centre du board Arduino : doit etre body_mask=1
    bx_min, by_min, bx_max, by_max = scene.board_loader.body_bbox(
        translate=scene.board_translate
    )
    cx = (bx_min + bx_max) / 2
    cy = (by_min + by_max) / 2
    col, row = grid.canvas_to_cell(cx, cy)
    assert grid.body_mask[row, col] == 1, \
        f"centre Arduino ({col},{row}) devrait etre bloque"
    # Distance: cellule a 100px du centre, sur le canvas
    col2, row2 = grid.canvas_to_cell(cx + 200, cy)
    # Ces cellules peuvent etre soit BB-cost, soit completement libres
    # On verifie juste qu'elles ne sont PAS bloquees comme corps
    assert grid.body_mask[row2, col2] == 0
    print("  [OK] Arduino body block")


def test_arduino_pins_marked():
    scene = place_scene(NETLIST_LED, BOARD_SVG)
    grid, net_to_id = build_occupancy_grid(scene, NETLIST_LED, cell_size=6)
    # D13, GND : doivent etre pin_owner = leur net_id sur la cellule de pin board
    for net, expected_fn in [("D13", "D13"), ("GND", _NET_TO_BOARD_PIN["GND"])]:
        if not scene.board_loader.has_pin(expected_fn):
            continue
        bxy = scene.board_loader.pin_position(expected_fn, translate=scene.board_translate)
        col, row = grid.canvas_to_cell(*bxy)
        assert grid.pin_owner[row, col] == net_to_id[net], \
            f"{net} pin board ({col},{row}) attendu owner {net_to_id[net]}, recu {grid.pin_owner[row, col]}"
    print("  [OK] Arduino pins (D13, GND) marquees")


def test_arduino_pin_line_band_R2():
    """Regle R2 : la bande juste a l'EXTERIEUR du corps Arduino, le long des
    rangees de broches, recoit un cout (cost_map > 0) pour empecher un fil de
    longer le bord de la carte au ras des broches voisines.

    On verifie 3 choses :
      1. Bande presente : dans l'anneau de cellules immediatement a l'exterieur
         de la bbox du corps Arduino, le nombre de cellules a cout > 0 est au
         moins egal au nombre de broches de la carte (= chaque broche depose
         au moins 1 cellule de bande devant elle).
      2. Bande SOUPLE, pas un mur : ces cellules restent traversables
         (body_mask == 0) pour qu'un fil puisse sortir de SA broche en
         perpendiculaire.
      3. Non-regression endpoints : une broche UTILISEE (D13) reste un endpoint
         valide (pin_owner == net_id, body_mask == 0) malgre R2.
    """
    scene = place_scene(NETLIST_LED, BOARD_SVG)
    grid, net_to_id = build_occupancy_grid(scene, NETLIST_LED, cell_size=6)

    bx_min, by_min, bx_max, by_max = scene.board_loader.body_bbox(
        translate=scene.board_translate
    )
    bc_lo, br_lo = grid.canvas_to_cell(bx_min, by_min)
    bc_hi, br_hi = grid.canvas_to_cell(bx_max, by_max)

    # Anneau de cellules juste a l'exterieur de la bbox board (epaisseur 1).
    ring: set[tuple[int, int]] = set()
    for col in range(bc_lo, bc_hi + 1):
        ring.add((col, br_lo - 1))   # bord haut
        ring.add((col, br_hi + 1))   # bord bas
    for row in range(br_lo, br_hi + 1):
        ring.add((bc_lo - 1, row))   # bord gauche
        ring.add((bc_hi + 1, row))   # bord droit

    band_cells = [
        (c, r) for (c, r) in ring
        if 0 <= r < grid.rows and 0 <= c < grid.cols
        and int(grid.cost_map[r, c]) > 0
    ]
    pin_count = scene.board_loader.pin_count
    assert len(band_cells) >= pin_count, (
        f"bande R2 trop fine : {len(band_cells)} cellules a cout>0 dans "
        f"l'anneau exterieur, attendu >= {pin_count} (nb broches)"
    )
    # 2. Bande souple : aucune des cellules de bande n'est hard-bloquee.
    for c, r in band_cells:
        assert int(grid.body_mask[r, c]) == 0, (
            f"cellule de bande R2 ({c},{r}) hard-bloquee (body_mask=1) : la "
            f"bande doit rester traversable en perpendiculaire"
        )

    # 3. D13 (broche utilisee) reste un endpoint valide.
    d13_xy = scene.board_loader.pin_position("D13", translate=scene.board_translate)
    dc, dr = grid.canvas_to_cell(*d13_xy)
    assert int(grid.pin_owner[dr, dc]) == net_to_id["D13"], \
        "R2 a casse l'endpoint D13 (pin_owner perdu)"
    assert int(grid.body_mask[dr, dc]) == 0, \
        "R2 a re-bloque la broche utilisee D13 (body_mask=1)"
    print(f"  [OK] R2 bande broches : {len(band_cells)} cellules (>= {pin_count} broches)")


def test_component_pins_marked():
    """Verifie que les WIRE_ENTRY holes (Regle 4) sont marquees comme
    pin_owner, pas les trous des pins composants eux-memes."""
    from ui.wiring.routing.occupancy import _component_wire_entry_canvas
    scene = place_scene(NETLIST_LED, BOARD_SVG)
    grid, net_to_id = build_occupancy_grid(scene, NETLIST_LED, cell_size=6)
    found = 0
    for placed in scene.placed_components:
        if not placed.pin_to_hole:
            continue
        for pin_idx in placed.pin_to_hole:
            entry_xy = _component_wire_entry_canvas(scene, placed, pin_idx)
            if entry_xy is None:
                continue
            col, r = grid.canvas_to_cell(*entry_xy)
            owner = int(grid.pin_owner[r, col])
            assert owner in net_to_id.values(), \
                f"wire_entry {placed.component_ref}.{pin_idx} : owner {owner} pas dans net_to_id"
            found += 1
    assert found > 0, "aucun wire_entry trouve"
    print(f"  [OK] {found} wire_entry composants marquees")


def test_endpoints_extracted():
    scene = place_scene(NETLIST_LED, BOARD_SVG)
    grid, net_to_id = build_occupancy_grid(scene, NETLIST_LED, cell_size=6)
    endpoints = extract_net_endpoints(scene, NETLIST_LED, grid, net_to_id)
    # D13 a une pin Arduino + 1 pin R -> source Arduino, target R
    assert "D13" in endpoints, f"D13 manquant : {list(endpoints)}"
    d13 = endpoints["D13"]
    assert len(d13.sources) == 1
    assert len(d13.targets) == 1
    # GND : pin Arduino + pin LED.C -> source Arduino, target LED.C
    assert "GND" in endpoints
    gnd = endpoints["GND"]
    assert len(gnd.sources) == 1
    assert len(gnd.targets) == 1
    # NET_LR : jonction LED.A <-> R.B. La LED et sa resistance serie sont
    # posees sur le MEME tie-strip de la breadboard, donc la jonction est
    # faite par la breadboard elle-meme : apres dedup tie-strip il ne reste
    # qu'1 endpoint unique -> net orphelin -> ABSENT des endpoints (aucun fil
    # a tirer). C'est le comportement correct, pas un manque.
    assert "NET_LR" not in endpoints, (
        "NET_LR ne devrait PAS avoir de fil : LED + R serie sur le meme "
        f"tie-strip (jonction via breadboard). Endpoints : {list(endpoints)}"
    )
    print(f"  [OK] endpoints D13/GND extraits, NET_LR dedup tie-strip (0 fil)")


def test_astar_routes_d13_to_consumer():
    """Test integration : A* trouve un chemin D13 (Arduino) -> R1.1 (BB)."""
    scene = place_scene(NETLIST_LED, BOARD_SVG)
    grid, net_to_id = build_occupancy_grid(scene, NETLIST_LED, cell_size=6)
    endpoints = extract_net_endpoints(scene, NETLIST_LED, grid, net_to_id)
    ne = endpoints["D13"]
    path = astar(grid, sources=ne.sources, targets=ne.targets,
                 net_id=ne.net_id, turn_penalty=8)
    assert path is not None, "A* a echoue sur D13"
    # Path doit contenir au moins le source et le target (= 2 cellules minimum)
    assert len(path) >= 2
    assert path[0] in ne.sources
    assert path[-1] in ne.targets
    # Compression : nb de coins doit etre raisonnable (< 10 pour scene simple)
    compressed = compress_collinear(path)
    assert len(compressed) <= 10, \
        f"trop de coins : {len(compressed)} - path mal route ?"
    print(f"  [OK] A* D13->R1.1 : {len(path)} cellules, {len(compressed)} coins")


def test_astar_routes_all_nets():
    """Tous les nets du LED scene doivent etre routables."""
    scene = place_scene(NETLIST_LED, BOARD_SVG)
    grid, net_to_id = build_occupancy_grid(scene, NETLIST_LED, cell_size=6)
    endpoints = extract_net_endpoints(scene, NETLIST_LED, grid, net_to_id)
    routed = []
    failed = []
    for net, ne in endpoints.items():
        path = astar(grid, ne.sources, ne.targets, ne.net_id, turn_penalty=8)
        if path is None:
            failed.append(net)
        else:
            routed.append((net, len(path), len(compress_collinear(path))))
            # Marque le wire dans la grille pour les nets suivants
            grid.mark_wire(path, ne.net_id)
    assert not failed, f"nets non routes : {failed}"
    print(f"  [OK] {len(routed)} nets routes :")
    for net, n_cells, n_coins in routed:
        print(f"        {net:8s} : {n_cells:3d} cellules, {n_coins} coins")


def main() -> int:
    print("[test_wiring_routing_occupancy]\n")
    tests = [
        test_grid_basic_structure,
        test_arduino_body_blocked,
        test_arduino_pins_marked,
        test_arduino_pin_line_band_R2,
        test_component_pins_marked,
        test_endpoints_extracted,
        test_astar_routes_d13_to_consumer,
        test_astar_routes_all_nets,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERR ] {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
