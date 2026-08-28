"""Smoke test Phase 3 : scenes multi-consommateurs power (rail BB).

Produit cote-a-cote :
  - 2 LEDs partageant GND (= GND multi-consumer = rail tap obligatoire)
  - 1 LED + R sur 5V (= 5V single consumer, mais rail tap quand meme par
    convention v2)

A valider visuellement :
  - Arduino V5V/GND a UN SEUL fil sortant (vers le rail)
  - Chaque consommateur est connecte au rail par un jumper court
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.layout.layout import place_scene
from ui.wiring.layout.routing import route_wires as route_wires_v2
from ui.wiring.layout.renderer import SceneRenderer
from ui.wiring.routing import route_wires, FEATURE_FLAG_ENV


BOARD_SVG = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"

# 2 LEDs sur D12 et D13, K commune sur GND, chacune avec sa R
NETLIST_2LEDS = [
    {"ref": "D1", "type": "led",
     "pins": [{"name": "A", "net": "NET_L1R1"},
              {"name": "K", "net": "GND"}]},
    {"ref": "R1", "type": "resistor",
     "pins": [{"name": "A", "net": "D13"},
              {"name": "B", "net": "NET_L1R1"}]},
    {"ref": "D2", "type": "led",
     "pins": [{"name": "A", "net": "NET_L2R2"},
              {"name": "K", "net": "GND"}]},
    {"ref": "R2", "type": "resistor",
     "pins": [{"name": "A", "net": "D12"},
              {"name": "B", "net": "NET_L2R2"}]},
]


def render(routing_fn, label, scene, netlist, out_path):
    wires = routing_fn(scene, netlist)
    svg = SceneRenderer(scene, wires).render()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    by_net: dict[str, int] = {}
    for w in wires:
        by_net[w.net] = by_net.get(w.net, 0) + 1
    print(f"  {label}: {len(wires)} wires -> {out_path.relative_to(ROOT)}")
    for net, count in sorted(by_net.items()):
        print(f"    {net:8s} : {count} wire(s)")


def main() -> int:
    out_dir = ROOT / "scripts" / "wiring_routing_test_output"
    print("[smoke_test_wiring_routing_phase3] 2 LEDs partageant GND\n")

    scene = place_scene(NETLIST_2LEDS, BOARD_SVG)
    print(f"  canvas={scene.canvas_size}, placed={len(scene.placed_components)} comp\n")

    os.environ.pop(FEATURE_FLAG_ENV, None)
    render(route_wires_v2, "v2 directe", scene, NETLIST_2LEDS,
            out_dir / "phase3_v2.svg")
    print()

    os.environ[FEATURE_FLAG_ENV] = "v3"
    render(route_wires, "v3 grille  ", scene, NETLIST_2LEDS,
            out_dir / "phase3_v3.svg")
    os.environ.pop(FEATURE_FLAG_ENV, None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
