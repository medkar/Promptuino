"""Test standalone de ui.wiring.highlight_logic.

Run : python scripts/test_highlight_logic.py
Sortie : 'OK : N tests' ou raise AssertionError au 1er echec.
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

from ui.wiring.highlight_logic import is_power_net
from ui.wiring.netlist import Component, Netlist, Pin
from ui.wiring.layout.routing import Wire
from ui.wiring.highlight_logic import compute_highlight_sets


def test_is_power_net_basic():
    assert is_power_net("GND") is True
    assert is_power_net("5V") is True
    assert is_power_net("3V3") is True
    assert is_power_net("VCC") is True
    assert is_power_net("VIN") is True
    assert is_power_net("BAT_5V") is True
    assert is_power_net("BAT_12V") is True
    assert is_power_net("D5") is False
    assert is_power_net("NET_A") is False
    assert is_power_net("") is False


def _build_simple_led_netlist():
    """LED D1 (A=NET_LR, K=GND), R1 (A=D5, B=NET_LR)."""
    d1 = Component(ref="D1", type="led",
                   pins=[Pin("A", "NET_LR"), Pin("K", "GND")])
    r1 = Component(ref="R1", type="resistor",
                   pins=[Pin("A", "D5"), Pin("B", "NET_LR")])
    nl = Netlist(board_id="arduino_uno_r3", components=[d1, r1])
    wires = [
        Wire(net="NET_LR", color="#ff0000",
             path=[(100.0, 50.0), (120.0, 60.0)]),    # idx 0 : D1.A -> R1.B
        Wire(net="GND",     color="#000000",
             path=[(100.0, 80.0), (50.0, 90.0)]),     # idx 1 : D1.K -> board
        Wire(net="D5",      color="#ffaa00",
             path=[(140.0, 60.0), (60.0, 70.0)]),     # idx 2 : R1.A -> board
    ]
    return nl, wires


def test_compute_signal_net_includes_both_endpoints():
    nl, wires = _build_simple_led_netlist()
    d1 = nl.components[0]
    board_pins = {"D5": "D5", "GND": "GND", "5V": "5V"}
    refs, wire_idxs = compute_highlight_sets(d1, nl, wires,
                                              board_pin_nets=board_pins)
    assert "D1" in refs
    assert "R1" in refs
    assert 0 in wire_idxs


def test_compute_signal_net_cascades_through_components():
    """Clic sur LED -> BFS doit visiter R1 -> R1.A est sur D5 (signal) ->
    le wire R1-Arduino (idx 2, D5) doit etre highlight via la cascade.
    Sans cette cascade, on louperait le 'chemin complet' du composant
    a l'Arduino.
    """
    nl, wires = _build_simple_led_netlist()
    d1 = nl.components[0]
    board_pins = {"D5": "D5", "GND": "GND", "5V": "5V"}
    refs, wire_idxs = compute_highlight_sets(d1, nl, wires,
                                              board_pin_nets=board_pins)
    assert "D1" in refs
    assert "R1" in refs
    assert "board" in refs, f"board manquant dans refs={refs}"
    assert 0 in wire_idxs   # NET_LR
    assert 2 in wire_idxs, f"D5 wire manquant via cascade R1: {wire_idxs}"


def test_compute_signal_net_tags_board_as_endpoint():
    """R1 (A=D5, B=NET_LR) : clic sur R1 -> 'board' doit etre dans refs
    parce que D5 est une pin Arduino. Permet au board de glow sur les
    nets signal aussi (pas seulement power)."""
    nl, wires = _build_simple_led_netlist()
    r1 = nl.components[1]
    board_pins = {"D5": "D5", "GND": "GND", "5V": "5V"}
    refs, _wire_idxs = compute_highlight_sets(r1, nl, wires,
                                                board_pin_nets=board_pins)
    assert "R1" in refs
    assert "D1" in refs   # partage NET_LR avec R1.B
    assert "board" in refs, f"board manquant dans refs={refs}"


def test_compute_power_net_traces_to_board():
    """D1 (K=GND). Wire idx 1 va de D1.K vers board.GND.
    Au clic sur D1 : doit highlight wire 1 + ajouter 'board' aux refs.
    Et ne PAS highlight d'autres composants tapant GND."""
    nl, wires = _build_simple_led_netlist()
    extra = Component(ref="D2", type="led",
                      pins=[Pin("A", "D6"), Pin("K", "GND")])
    nl.components.append(extra)
    wires.append(Wire(net="GND", color="#000000",
                      path=[(200.0, 80.0), (210.0, 90.0)]))  # idx 3

    d1 = nl.components[0]
    refs, wire_idxs = compute_highlight_sets(
        d1, nl, wires,
        board_pin_nets={"GND": "GND", "5V": "5V", "D5": "D5"},
    )
    assert "D1" in refs
    assert "board" in refs, f"refs={refs}"
    assert "D2" not in refs
    assert 1 in wire_idxs
    assert 3 not in wire_idxs


def test_trace_to_source_seed_picks_correct_cluster():
    """2 clusters GND disjoints : LED (cluster A) + R (cluster B, sur D6
    branche via une autre R en pullup tapant aussi GND). Sans seed_xy,
    le 1er wire du net est utilise (potentiellement le mauvais cluster).
    Avec seed_xy proche du wire LED, on doit obtenir UNIQUEMENT le wire
    LED. Avec seed_xy proche du wire R, UNIQUEMENT celui de R.
    """
    from ui.wiring.highlight_logic import trace_to_source

    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="D1", type="led",
                  pins=[Pin("A", "D5"), Pin("K", "GND")]),
        Component(ref="R1", type="resistor",
                  pins=[Pin("A", "D6"), Pin("B", "GND")]),
    ])
    # 2 clusters GND geometriquement disjoints
    wires = [
        Wire(net="GND", color="#000000",
             path=[(10.0, 10.0), (20.0, 10.0)]),    # idx 0 : cluster A (LED)
        Wire(net="GND", color="#000000",
             path=[(500.0, 500.0), (510.0, 500.0)]),  # idx 1 : cluster B (R)
    ]
    board_pins = {"GND": "GND", "5V": "5V"}

    # Seed proche cluster A
    chain_a, source_a = trace_to_source("GND", nl, wires, board_pins,
                                         seed_xy=(15.0, 10.0))
    assert chain_a == {0}, f"cluster A attendu, got {chain_a}"
    assert source_a == "board"

    # Seed proche cluster B
    chain_b, source_b = trace_to_source("GND", nl, wires, board_pins,
                                         seed_xy=(505.0, 500.0))
    assert chain_b == {1}, f"cluster B attendu, got {chain_b}"
    assert source_b == "board"


def test_compute_highlight_sets_falls_back_without_pin_positions():
    """Sans pin_positions, compute_highlight_sets doit toujours fonctionner
    (rétrocompat avec l'appelant qui ne fournit pas encore la map).
    """
    nl, wires = _build_simple_led_netlist()
    d1 = nl.components[0]
    board_pins = {"D5": "D5", "GND": "GND", "5V": "5V"}

    # Sans pin_positions (None) → fallback comportement legacy
    refs, wire_idxs = compute_highlight_sets(
        d1, nl, wires, board_pin_nets=board_pins, pin_positions=None,
    )
    assert "D1" in refs
    assert "R1" in refs
    # Wire NET_LR (idx 0) toujours highlight (signal net, pas trace)
    assert 0 in wire_idxs


def test_trace_to_source_rail_aware_extends_to_arduino():
    """2 wires GND geometriquement disjoints mais relies par le meme rail
    BB (V+/GND vertical strip). Avec rail_strips + source_bboxes Arduino,
    le cluster s'etend du wire LED a Arduino-rail-wire, parce que les 2
    endpoints sont sur le meme rail strip ET l'autre endpoint d'Arduino
    est dans la bbox PCB.
    """
    from ui.wiring.highlight_logic import trace_to_source

    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="D1", type="led",
                  pins=[Pin("A", "D5"), Pin("K", "GND")]),
    ])
    wires = [
        # LED.K -> rail GND at (rail_x=300, y=100)
        Wire(net="GND", color="#000000",
             path=[(280.0, 100.0), (300.0, 100.0)]),  # idx 0
        # Arduino GND -> rail GND at (rail_x=300, y=400). Arduino body
        # est a x<100. Endpoint Arduino : (50, 400).
        Wire(net="GND", color="#000000",
             path=[(50.0, 400.0), (300.0, 400.0)]),  # idx 1
    ]
    # 1 rail strip a x=300, y de 0 a 500
    rail_strips = [(300.0, 0.0, 500.0)]
    # Arduino bbox a gauche
    source_bboxes = [(0.0, 0.0, 100.0, 600.0)]

    chain, source = trace_to_source(
        "GND", nl, wires,
        board_pin_nets={"GND": "GND"},
        seed_xy=(280.0, 100.0),
        rail_strips=rail_strips,
        source_bboxes=source_bboxes,
    )
    assert 0 in chain, f"wire LED manquant: {chain}"
    assert 1 in chain, f"rail->Arduino wire manquant via ext rail-aware: {chain}"
    assert source == "board"


def test_trace_to_source_rail_aware_extends_via_rail_bridge():
    """Cas batterie : V- -> rail gauche, jumper rail gauche -> rail droit,
    rail droit -> Arduino. Le jumper inter-rail a ses 2 endpoints sur
    rails (aucun dans une source bbox) et doit etre ajoute par le cas
    'rail bridge'. Permet ensuite de propager au wire rail->Arduino.
    """
    from ui.wiring.highlight_logic import trace_to_source

    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="BAT1", type="battery_external",
                  pins=[Pin("+", "BAT_5V"), Pin("-", "GND")]),
    ])
    # rail gauche x=200, rail droit x=400, batterie a droite >400
    wires = [
        # BAT V- -> rail gauche
        Wire(net="GND", color="#000000",
             path=[(600.0, 250.0), (200.0, 250.0)]),  # idx 0
        # Jumper rail gauche -> rail droit
        Wire(net="GND", color="#000000",
             path=[(200.0, 100.0), (400.0, 100.0)]),  # idx 1
        # Rail droit -> Arduino GND
        Wire(net="GND", color="#000000",
             path=[(400.0, 350.0), (50.0, 350.0)]),   # idx 2
    ]
    rail_strips = [
        (200.0, 0.0, 500.0),   # rail gauche
        (400.0, 0.0, 500.0),   # rail droit
    ]
    source_bboxes = [
        (0.0, 0.0, 100.0, 600.0),    # Arduino a gauche
        (550.0, 200.0, 700.0, 300.0),  # Batterie a droite
    ]

    chain, source = trace_to_source(
        "GND", nl, wires,
        board_pin_nets={"GND": "GND"},
        seed_xy=(600.0, 250.0),  # batterie
        rail_strips=rail_strips,
        source_bboxes=source_bboxes,
    )
    assert 0 in chain   # bat -> rail gauche (seed cluster)
    assert 1 in chain, f"jumper rail-rail manquant: {chain}"
    assert 2 in chain, f"rail-droit -> Arduino manquant: {chain}"
    assert source == "board"


def test_trace_to_source_rail_aware_skips_other_consumers():
    """Sur le meme rail GND, un autre wire de consommateur (LED2.K -> rail)
    ne doit PAS etre ajoute par l'extension rail-aware, parce que son
    autre endpoint n'est PAS dans une bbox source. Permet de ne pas
    cascader a travers le rail GND aux autres consommateurs.
    """
    from ui.wiring.highlight_logic import trace_to_source

    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="D1", type="led",
                  pins=[Pin("A", "D5"), Pin("K", "GND")]),
        Component(ref="D2", type="led",
                  pins=[Pin("A", "D6"), Pin("K", "GND")]),
    ])
    wires = [
        Wire(net="GND", color="#000000",
             path=[(280.0, 100.0), (300.0, 100.0)]),  # idx 0 : D1
        Wire(net="GND", color="#000000",
             path=[(50.0, 400.0), (300.0, 400.0)]),   # idx 1 : Arduino (source)
        Wire(net="GND", color="#000000",
             path=[(280.0, 300.0), (300.0, 300.0)]),  # idx 2 : D2 (autre conso)
    ]
    rail_strips = [(300.0, 0.0, 500.0)]
    source_bboxes = [(0.0, 0.0, 100.0, 600.0)]  # Arduino seulement

    chain, _src = trace_to_source(
        "GND", nl, wires,
        board_pin_nets={"GND": "GND"},
        seed_xy=(280.0, 100.0),  # near D1
        rail_strips=rail_strips,
        source_bboxes=source_bboxes,
    )
    assert 0 in chain
    assert 1 in chain  # Arduino (source) ajoute
    assert 2 not in chain, f"D2 wire ne doit PAS etre dans le cluster: {chain}"


TESTS = [
    test_is_power_net_basic,
    test_compute_signal_net_includes_both_endpoints,
    test_compute_signal_net_cascades_through_components,
    test_compute_signal_net_tags_board_as_endpoint,
    test_compute_power_net_traces_to_board,
    test_trace_to_source_seed_picks_correct_cluster,
    test_compute_highlight_sets_falls_back_without_pin_positions,
    test_trace_to_source_rail_aware_extends_to_arduino,
    test_trace_to_source_rail_aware_extends_via_rail_bridge,
    test_trace_to_source_rail_aware_skips_other_consumers,
]


def main() -> int:
    for t in TESTS:
        t()
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
