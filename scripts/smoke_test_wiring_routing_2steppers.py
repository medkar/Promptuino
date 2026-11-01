"""Smoke test wiring v3 : 2 steppers empiles + leurs drivers.

Couvre les 2 paires stepper+driver du catalogue. Pas de partage dual
H-bridge possible (chaque driver pilote 1 stepper) -> 2 drivers, mais
les 2 steppers sont empiles verticalement comme les DC motors.

  - 2x NEMA17    + 2x A4988    (DIP-16 on-BB, bipolar microstepping)
  - 2x 28BYJ-48  + 2x ULN2003  (off-BB, unipolar via JST)

Sortie : scripts/wiring_routing_test_output/scene_v3_2steppers_*.svg.
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


# 2x NEMA17 + 2x A4988 (DIP-16 on-BB). 1 driver par stepper bipolar.
# Chaque NEMA17 a `_paired_driver` -> son A4988 respectif (cf
# inference._has_nema17_for). Le layout place chaque motor au-dessus
# de son driver sur la BB.
TWO_NEMA17_A4988 = [
    {"ref": "M1", "type": "nema17",
     "pins": [
         {"name": "1A", "net": "COIL_A1_POS"},
         {"name": "1B", "net": "COIL_A1_NEG"},
         {"name": "2A", "net": "COIL_B1_POS"},
         {"name": "2B", "net": "COIL_B1_NEG"},
     ],
     "attributes": {"_paired_driver": "U1"}},
    {"ref": "M2", "type": "nema17",
     "pins": [
         {"name": "1A", "net": "COIL_A2_POS"},
         {"name": "1B", "net": "COIL_A2_NEG"},
         {"name": "2A", "net": "COIL_B2_POS"},
         {"name": "2B", "net": "COIL_B2_NEG"},
     ],
     "attributes": {"_paired_driver": "U2"}},
    {"ref": "U1", "type": "a4988",
     "pins": [
         {"name": "STEP", "net": "D7"},
         {"name": "DIR",  "net": "D8"},
         {"name": "VDD",  "net": "5V"},
         {"name": "GND",  "net": "GND"},
         {"name": "VMOT", "net": "BAT_5V"},
         {"name": "1A",   "net": "COIL_A1_POS"},
         {"name": "1B",   "net": "COIL_A1_NEG"},
         {"name": "2A",   "net": "COIL_B1_POS"},
         {"name": "2B",   "net": "COIL_B1_NEG"},
     ]},
    {"ref": "U2", "type": "a4988",
     "pins": [
         {"name": "STEP", "net": "D9"},
         {"name": "DIR",  "net": "D10"},
         {"name": "VDD",  "net": "5V"},
         {"name": "GND",  "net": "GND"},
         {"name": "VMOT", "net": "BAT_5V"},
         {"name": "1A",   "net": "COIL_A2_POS"},
         {"name": "1B",   "net": "COIL_A2_NEG"},
         {"name": "2A",   "net": "COIL_B2_POS"},
         {"name": "2B",   "net": "COIL_B2_NEG"},
     ]},
    _bat(),
]


# 2x 28BYJ-48 + 2x ULN2003 (off-BB). 1 driver par stepper unipolar.
# Le stepper se connecte au driver via JST 5-pins (COM + 4 phases) ; les
# nets internes NET_* representent le bus 5-fils.
TWO_28BYJ48_ULN2003 = [
    {"ref": "M1", "type": "stepper_motor",
     "pins": [
         {"name": "COM", "net": "NET_E1"},
         {"name": "A",   "net": "NET_A1"},
         {"name": "B",   "net": "NET_B1"},
         {"name": "C",   "net": "NET_C1"},
         {"name": "D",   "net": "NET_D1"},
     ],
     "attributes": {"_paired_driver": "U1"}},
    {"ref": "M2", "type": "stepper_motor",
     "pins": [
         {"name": "COM", "net": "NET_E2"},
         {"name": "A",   "net": "NET_A2"},
         {"name": "B",   "net": "NET_B2"},
         {"name": "C",   "net": "NET_C2"},
         {"name": "D",   "net": "NET_D2"},
     ],
     "attributes": {"_paired_driver": "U2"}},
    {"ref": "U1", "type": "uln2003",
     "pins": [
         {"name": "VCC",     "net": "BAT_5V"},
         {"name": "GND",     "net": "GND"},
         {"name": "IN1",     "net": "D4"},
         {"name": "IN2",     "net": "D5"},
         {"name": "IN3",     "net": "D6"},
         {"name": "IN4",     "net": "D7"},
         {"name": "OUT1",    "net": "NET_A1"},
         {"name": "OUT2",    "net": "NET_B1"},
         {"name": "OUT3",    "net": "NET_C1"},
         {"name": "OUT4",    "net": "NET_D1"},
         {"name": "JST_PWR", "net": "NET_E1"},
     ]},
    {"ref": "U2", "type": "uln2003",
     "pins": [
         {"name": "VCC",     "net": "BAT_5V"},
         {"name": "GND",     "net": "GND"},
         {"name": "IN1",     "net": "D8"},
         {"name": "IN2",     "net": "D9"},
         {"name": "IN3",     "net": "D10"},
         {"name": "IN4",     "net": "D11"},
         {"name": "OUT1",    "net": "NET_A2"},
         {"name": "OUT2",    "net": "NET_B2"},
         {"name": "OUT3",    "net": "NET_C2"},
         {"name": "OUT4",    "net": "NET_D2"},
         {"name": "JST_PWR", "net": "NET_E2"},
     ]},
    _bat(),
]


def _render(label: str, netlist: list[dict], out_path: Path) -> None:
    board_svg = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
    scene = place_scene(netlist, board_svg)
    wires = route_wires(scene, netlist)
    svg = SceneRenderer(scene, wires).render()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    interesting = [(pc.component_ref, pc.translate, pc.component_type)
                    for pc in scene.placed_components
                    if pc.component_type in ("nema17", "stepper_motor",
                                              "uln2003", "a4988",
                                              "battery_external")]
    print(f"  {label:35s}: canvas {scene.canvas_size}, "
          f"{len(scene.placed_components)} composants, {len(wires)} fils")
    for ref, pos, ctype in interesting:
        print(f"    {ref} ({ctype}) translate=({pos[0]:.1f}, {pos[1]:.1f})")
    print(f"    -> {out_path.relative_to(ROOT)}")


def main() -> int:
    OUT = ROOT / "scripts" / "wiring_routing_test_output"
    print("[smoke v3 2-steppers — empilage vertical]\n")
    _render("2x NEMA17 + 2x A4988",
            TWO_NEMA17_A4988,
            OUT / "scene_v3_2steppers_nema17_a4988.svg")
    _render("2x 28BYJ-48 + 2x ULN2003",
            TWO_28BYJ48_ULN2003,
            OUT / "scene_v3_2steppers_28byj48_uln2003.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
