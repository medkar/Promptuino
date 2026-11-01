"""Smoke test wiring v3 : 2 DC motors empiles + tous les drivers DC.

Couvre les 5 drivers DC du catalogue. Avec 2 motors DC :
  - Layout : motors empiles verticalement au-dessus de la BB (M_0 en bas /
    M_1 au-dessus, X = centre BB commun), QUEL QUE SOIT le driver. Plus
    de placement flanking exception.
  - Inference : 1 SEUL driver partage pour 2 motors (dual H-bridge), pour
    tous les drivers DC (off-BB ET on-BB DIP). Cf
    `_DUAL_PAIR_CAPABLE_DRIVERS` dans inference.py.

Tous les netlists ici simulent ce que produit l'inference real :
  - `_paired_motor` attribut sur le driver (CSV "M1,M2")
  - 4 sorties cablees sur les 2 motors (OUT1/OUT2 -> M1, OUT3/OUT4 -> M2)

Sortie : scripts/wiring_routing_test_output/scene_v3_2motors_*.svg.
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
from ui.wiring.routing import route_wires
from ui.wiring.layout.renderer import SceneRenderer


def _bat() -> dict:
    return {"ref": "BAT1", "type": "battery_external",
            "pins": [{"name": "+", "net": "BAT_5V"},
                     {"name": "-", "net": "GND"}]}


def _motors() -> list[dict]:
    return [
        {"ref": "M1", "type": "dc_motor",
         "pins": [{"name": "M+", "net": "NET_A"},
                  {"name": "M-", "net": "NET_B"}]},
        {"ref": "M2", "type": "dc_motor",
         "pins": [{"name": "M+", "net": "NET_C"},
                  {"name": "M-", "net": "NET_D"}]},
    ]


# 2 DC motors + 1 L298N partage (off-BB).
TWO_MOTORS_L298N = _motors() + [
    {"ref": "U1", "type": "l298n",
     "pins": [
         {"name": "ENA",  "net": "5V"},
         {"name": "IN1",  "net": "D6"},
         {"name": "IN2",  "net": "D7"},
         {"name": "ENB",  "net": "5V"},
         {"name": "IN3",  "net": "D9"},
         {"name": "IN4",  "net": "D10"},
         {"name": "VCC",  "net": "5V"},
         {"name": "VS",   "net": "BAT_5V"},
         {"name": "GND",  "net": "GND"},
         {"name": "OUT1", "net": "NET_A"},
         {"name": "OUT2", "net": "NET_B"},
         {"name": "OUT3", "net": "NET_C"},
         {"name": "OUT4", "net": "NET_D"},
     ],
     "attributes": {"_paired_motor": "M1,M2"}},
    _bat(),
]


# 2 DC motors + 1 L293D module partage (off-BB).
TWO_MOTORS_L293D_MODULE = _motors() + [
    {"ref": "U1", "type": "l293d_module",
     "pins": [
         {"name": "ENA",  "net": "5V"},
         {"name": "IN1",  "net": "D6"},
         {"name": "IN2",  "net": "D7"},
         {"name": "ENB",  "net": "5V"},
         {"name": "IN3",  "net": "D9"},
         {"name": "IN4",  "net": "D10"},
         {"name": "VCC",  "net": "5V"},
         {"name": "VS",   "net": "BAT_5V"},
         {"name": "GND",  "net": "GND"},
         {"name": "OUT1", "net": "NET_A"},
         {"name": "OUT2", "net": "NET_B"},
         {"name": "OUT3", "net": "NET_C"},
         {"name": "OUT4", "net": "NET_D"},
     ],
     "attributes": {"_paired_motor": "M1,M2"}},
    _bat(),
]


# 2 DC motors + 1 L293D DIP partage (on-BB DIP-16).
TWO_MOTORS_L293D_DIP = _motors() + [
    {"ref": "U1", "type": "l293d",
     "pins": [
         {"name": "ENA",  "net": "5V"},
         {"name": "IN1",  "net": "D6"},
         {"name": "IN2",  "net": "D7"},
         {"name": "ENB",  "net": "5V"},
         {"name": "IN3",  "net": "D9"},
         {"name": "IN4",  "net": "D10"},
         {"name": "OUT1", "net": "NET_A"},
         {"name": "OUT2", "net": "NET_B"},
         {"name": "OUT3", "net": "NET_C"},
         {"name": "OUT4", "net": "NET_D"},
         {"name": "VSS",  "net": "5V"},
         {"name": "VS",   "net": "BAT_5V"},
         {"name": "GND",  "net": "GND"},
     ],
     "attributes": {"_paired_motor": "M1,M2"}},
    _bat(),
]


# 2 DC motors + 1 TB6612FNG partage (on-BB DIP-16).
TWO_MOTORS_TB6612 = _motors() + [
    {"ref": "U1", "type": "tb6612fng",
     "pins": [
         {"name": "VM",   "net": "BAT_5V"},
         {"name": "VCC",  "net": "5V"},
         {"name": "GND",  "net": "GND"},
         {"name": "AO1",  "net": "NET_A"},
         {"name": "AO2",  "net": "NET_B"},
         {"name": "BO1",  "net": "NET_C"},
         {"name": "BO2",  "net": "NET_D"},
         {"name": "STBY", "net": "5V"},
         {"name": "AIN1", "net": "D6"},
         {"name": "AIN2", "net": "D7"},
         {"name": "PWMA", "net": "D8"},
         {"name": "BIN1", "net": "D9"},
         {"name": "BIN2", "net": "D10"},
         {"name": "PWMB", "net": "D11"},
     ],
     "attributes": {"_paired_motor": "M1,M2"}},
    _bat(),
]


# 2 DC motors + 1 DRV8833 partage (on-BB DIP-12).
TWO_MOTORS_DRV8833 = _motors() + [
    {"ref": "U1", "type": "drv8833",
     "pins": [
         {"name": "SLEEP", "net": "5V"},
         {"name": "OUT1",  "net": "NET_A"},
         {"name": "OUT2",  "net": "NET_B"},
         {"name": "OUT3",  "net": "NET_C"},
         {"name": "OUT4",  "net": "NET_D"},
         {"name": "IN1",   "net": "D6"},
         {"name": "IN2",   "net": "D7"},
         {"name": "IN3",   "net": "D9"},
         {"name": "IN4",   "net": "D10"},
         {"name": "VCC",   "net": "BAT_5V"},
         {"name": "GND",   "net": "GND"},
     ],
     "attributes": {"_paired_motor": "M1,M2"}},
    _bat(),
]


def _render(label: str, netlist: list[dict], out_path: Path) -> None:
    board_svg = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
    scene = place_scene(netlist, board_svg)
    wires = route_wires(scene, netlist)
    svg = SceneRenderer(scene, wires).render()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    motor_positions = [(pc.component_ref, pc.translate)
                       for pc in scene.placed_components
                       if pc.component_type == "dc_motor"]
    print(f"  {label:35s}: canvas {scene.canvas_size}, "
          f"{len(scene.placed_components)} composants, {len(wires)} fils")
    for ref, pos in motor_positions:
        print(f"    {ref} translate=({pos[0]:.1f}, {pos[1]:.1f})")
    print(f"    -> {out_path.relative_to(ROOT)}")


def main() -> int:
    OUT = ROOT / "scripts" / "wiring_routing_test_output"
    print("[smoke v3 2-motors — 1 driver partage pour tous les drivers DC]\n")
    _render("2x dc_motor + 1x L298N",
            TWO_MOTORS_L298N,
            OUT / "scene_v3_2motors_l298n.svg")
    _render("2x dc_motor + 1x L293D module",
            TWO_MOTORS_L293D_MODULE,
            OUT / "scene_v3_2motors_l293d_module.svg")
    _render("2x dc_motor + 1x L293D DIP",
            TWO_MOTORS_L293D_DIP,
            OUT / "scene_v3_2motors_l293d_dip.svg")
    _render("2x dc_motor + 1x TB6612FNG",
            TWO_MOTORS_TB6612,
            OUT / "scene_v3_2motors_tb6612.svg")
    _render("2x dc_motor + 1x DRV8833",
            TWO_MOTORS_DRV8833,
            OUT / "scene_v3_2motors_drv8833.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
