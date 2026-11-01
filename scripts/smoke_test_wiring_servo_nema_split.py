"""Smoke test : servo + NEMA17/A4988 sur 2 batteries (voltage split).

Netlist deja split (apres inference) :
  - Servo S1 alimente par BAT1 (BAT_5V, 4.8-6V)
  - NEMA17 + A4988 alimentes par BAT2 (BAT_5V_2, 8-35V)

Layout : 2-BB miroir (servo+BAT1 a droite, A4988+BAT2 a gauche).

Sortie :
  scripts/wiring_routing_test_output/servo_nema17_split_v2.svg  (route_wires v2)
  scripts/wiring_routing_test_output/servo_nema17_split_v3.svg  (route_wires v3, partial)
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
OUT = ROOT / "scripts" / "wiring_routing_test_output"


SERVO_NEMA_SPLIT_NETLIST = [
    # Servo : VCC sur BAT_5V (BAT1, 4.8-6V), signal sur D9.
    {"ref": "S1", "type": "servo",
     "pins": [
         {"name": "VCC",    "net": "BAT_5V"},
         {"name": "GND",    "net": "GND"},
         {"name": "SIG", "net": "D9"},
     ]},
    # NEMA17 : 4 fils bobines.
    {"ref": "M1", "type": "nema17",
     "pins": [
         {"name": "1A", "net": "COIL_A_POS"},
         {"name": "1B", "net": "COIL_A_NEG"},
         {"name": "2A", "net": "COIL_B_POS"},
         {"name": "2B", "net": "COIL_B_NEG"},
     ]},
    # A4988 : VMOT sur BAT_5V_2 (BAT2, 8-35V), VDD sur 5V, GND/STEP/DIR.
    {"ref": "U1", "type": "a4988",
     "pins": [
         {"name": "STEP", "net": "D7"},
         {"name": "DIR",  "net": "D8"},
         {"name": "VDD",  "net": "5V"},
         {"name": "GND",  "net": "GND"},
         {"name": "VMOT", "net": "BAT_5V_2"},
         {"name": "1A",   "net": "COIL_A_POS"},
         {"name": "1B",   "net": "COIL_A_NEG"},
         {"name": "2A",   "net": "COIL_B_POS"},
         {"name": "2B",   "net": "COIL_B_NEG"},
     ]},
    # BAT1 (servo, 4.8-6V).
    {"ref": "BAT1", "type": "battery_external",
     "pins": [{"name": "+", "net": "BAT_5V"},
              {"name": "-", "net": "GND"}]},
    # BAT2 (NEMA17, 8-35V).
    {"ref": "BAT2", "type": "battery_external",
     "pins": [{"name": "+", "net": "BAT_5V_2"},
              {"name": "-", "net": "GND"}]},
]


def _render(routing_fn, scene, netlist, out_path: Path):
    wires = routing_fn(scene, netlist)
    svg = SceneRenderer(scene, wires).render()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    return wires


def main() -> int:
    print("[smoke_test_wiring_servo_nema_split]\n")
    scene = place_scene(SERVO_NEMA_SPLIT_NETLIST, BOARD_SVG)
    print(f"  canvas={scene.canvas_size}, {len(scene.placed_components)} composants")
    print(f"  breadboards={len(scene.breadboards)}")

    # v2
    os.environ.pop(FEATURE_FLAG_ENV, None)
    wires_v2 = _render(
        route_wires_v2, scene, SERVO_NEMA_SPLIT_NETLIST,
        OUT / "servo_nema17_split_v2.svg",
    )
    print(f"  v2 : {len(wires_v2)} wires")

    # v3 partial
    os.environ[FEATURE_FLAG_ENV] = "v3"
    def _v3_partial(scene, netlist):
        return route_wires(scene, netlist, partial=True)
    wires_v3 = _render(
        _v3_partial, scene, SERVO_NEMA_SPLIT_NETLIST,
        OUT / "servo_nema17_split_v3.svg",
    )
    os.environ.pop(FEATURE_FLAG_ENV, None)
    print(f"  v3 : {len(wires_v3)} wires")

    return 0


if __name__ == "__main__":
    sys.exit(main())
