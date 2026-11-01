"""Smoke test wiring v2 : drivers off-BB + moteurs + batterie.

Verifie le routing des composants off-BB / on-BB pour la famille moteur :

  Off-BB <-> Off-BB :
    - DC motor + L298N (module breakout vert)
    - DC motor + L293D module (PCB bleu)
    - Stepper 28BYJ-48 + ULN2003 (JST)

  Off-BB <-> On-BB (DIP sur breadboard) :
    - DC motor + TB6612FNG (DIP-16, SparkFun breakout)
    - DC motor + DRV8833    (DIP-12)
    - NEMA17    + A4988     (DIP-16, Pololu)

Toutes les scenes incluent un bouton sur BB (assure un consommateur on-BB
du rail GND) et une battery_external (alim moteur separee de l'Arduino).

Sortie : scripts/wiring_layout_test_output/scene_v2_*.svg
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
from ui.wiring.layout.routing import route_wires
from ui.wiring.layout.renderer import SceneRenderer


# ─── Scene 1 : DC motor + L298N + battery + button ──────────────────────
DC_MOTOR_NETLIST = [
    # Bouton on-BB (assure que GND a un consommateur on-BB → rail GND
    # accessible) avec pullup interne.
# Moteur DC off-BB : 2 pins connectees aux sorties du driver.
    {"ref": "M1", "type": "dc_motor",
     "pins": [{"name": "M+", "net": "NET_A"}, {"name": "M-", "net": "NET_B"}]},
    # L298N off-BB : ENA (jumper 5V), IN1=PWM, IN2=GND, VCC=5V (logic),
    # VS=batterie, GND, OUT1/OUT2 vers le moteur.
    {"ref": "U1", "type": "l298n",
     "pins": [
         {"name": "ENA",  "net": "5V"},
         {"name": "IN1",  "net": "D6"},
         {"name": "IN2",  "net": "GND"},
         {"name": "VCC",  "net": "5V"},
         {"name": "VS",   "net": "BAT_5V"},
         {"name": "GND",  "net": "GND"},
         {"name": "OUT1", "net": "NET_A"},
         {"name": "OUT2", "net": "NET_B"},
     ]},
    # Batterie externe : alimente le L298N (motor side).
    {"ref": "BAT1", "type": "battery_external",
     "pins": [{"name": "+", "net": "BAT_5V"},
              {"name": "-", "net": "GND"}]},
]


# ─── Scene 2 : Stepper 28BYJ-48 + ULN2003 + battery + button ────────────
STEPPER_NETLIST = [
# Stepper off-BB : 5 fils, tous via le JST du driver (4 phases + COM).
# Aucun fil externe vers la BB pour le stepper -- physiquement c'est un
# bus 5-pins entre stepper et driver. L'alim moteur passe en interne
# sur le PCB du module ULN2003 (VCC == JST_PWR electriquement) mais on
# represente JST_PWR comme un net interne distinct dans le netlist.
    {"ref": "M1", "type": "stepper_motor",
     "pins": [
         {"name": "COM", "net": "NET_E"},
         {"name": "A",   "net": "NET_A"},
         {"name": "B",   "net": "NET_B"},
         {"name": "C",   "net": "NET_C"},
         {"name": "D",   "net": "NET_D"},
     ]},
    # ULN2003 off-BB : VCC (batterie via BB), GND, IN1-4 (Arduino),
    # OUT1-4 (stepper via JST), JST_PWR = 5e trou JST (stepper.COM).
    {"ref": "U1", "type": "uln2003",
     "pins": [
         {"name": "VCC",     "net": "BAT_5V"},
         {"name": "GND",     "net": "GND"},
         {"name": "IN1",     "net": "D8"},
         {"name": "IN2",     "net": "D9"},
         {"name": "IN3",     "net": "D10"},
         {"name": "IN4",     "net": "D11"},
         {"name": "OUT1",    "net": "NET_A"},
         {"name": "OUT2",    "net": "NET_B"},
         {"name": "OUT3",    "net": "NET_C"},
         {"name": "OUT4",    "net": "NET_D"},
         {"name": "JST_PWR", "net": "NET_E"},
     ]},
    {"ref": "BAT1", "type": "battery_external",
     "pins": [{"name": "+", "net": "BAT_5V"},
              {"name": "-", "net": "GND"}]},
]


# ─── Scene 3 : DC motor + L293D module + battery + button ───────────────
# L293D module : PCB bleu off-BB, 13 pins. Cote "Arduino" : VCC, GND, IN1-4,
# ENA, ENB. Cote "moteur" : OUT1-4, VS (motor +). On utilise le canal A
# (ENA/IN1/IN2 -> OUT1/OUT2) pour piloter 1 DC motor.
DC_MOTOR_L293D_MOD_NETLIST = [
{"ref": "M1", "type": "dc_motor",
     "pins": [{"name": "M+", "net": "NET_A"}, {"name": "M-", "net": "NET_B"}]},
    {"ref": "U1", "type": "l293d_module",
     "pins": [
         {"name": "ENA",  "net": "5V"},
         {"name": "IN1",  "net": "D6"},
         {"name": "IN2",  "net": "D7"},
         {"name": "VCC",  "net": "5V"},
         {"name": "VS",   "net": "BAT_5V"},
         {"name": "GND",  "net": "GND"},
         {"name": "OUT1", "net": "NET_A"},
         {"name": "OUT2", "net": "NET_B"},
     ]},
    {"ref": "BAT1", "type": "battery_external",
     "pins": [{"name": "+", "net": "BAT_5V"},
              {"name": "-", "net": "GND"}]},
]


# ─── Scene 4 : DC motor + TB6612FNG (DIP-16 on-BB) + battery + button ───
# TB6612FNG : breakout DIP-16 pose sur breadboard (on-BB). Successeur
# moderne du L298N. Canal A utilise : AIN1/AIN2 (direction), PWMA (vitesse),
# AO1/AO2 (moteur). VM (motor power) -> battery, VCC (logic) -> 5V Arduino.
# STBY HIGH (5V) = active. 3 pins GND dans le SVG mais on n'en reference
# qu'une seule (cf. TODO #2 multi-position pins).
DC_MOTOR_TB6612_NETLIST = [
{"ref": "M1", "type": "dc_motor",
     "pins": [{"name": "M+", "net": "NET_A"}, {"name": "M-", "net": "NET_B"}]},
    {"ref": "U1", "type": "tb6612fng",
     "pins": [
         {"name": "VM",   "net": "BAT_5V"},
         {"name": "VCC",  "net": "5V"},
         {"name": "GND",  "net": "GND"},
         {"name": "AO1",  "net": "NET_A"},
         {"name": "AO2",  "net": "NET_B"},
         {"name": "STBY", "net": "5V"},
         {"name": "AIN1", "net": "D6"},
         {"name": "AIN2", "net": "D7"},
         {"name": "PWMA", "net": "D9"},
     ]},
    {"ref": "BAT1", "type": "battery_external",
     "pins": [{"name": "+", "net": "BAT_5V"},
              {"name": "-", "net": "GND"}]},
]


# ─── Scene 5 : DC motor + DRV8833 (DIP-12 on-BB) + battery + button ─────
# DRV8833 : DIP-12 pose sur breadboard (on-BB). Pas de PWM dedie : on PWM
# les IN directement. VCC unifie logique+moteur (2.7-10.8V) -> ici BAT_5V.
# Canal A utilise : IN1/IN2 (PWM direction) -> OUT1/OUT2 (moteur). SLEEP
# HIGH pour activer.
DC_MOTOR_DRV8833_NETLIST = [
{"ref": "M1", "type": "dc_motor",
     "pins": [{"name": "M+", "net": "NET_A"}, {"name": "M-", "net": "NET_B"}]},
    {"ref": "U1", "type": "drv8833",
     "pins": [
         {"name": "SLEEP", "net": "5V"},
         {"name": "OUT1",  "net": "NET_A"},
         {"name": "OUT2",  "net": "NET_B"},
         {"name": "IN1",   "net": "D6"},
         {"name": "IN2",   "net": "D7"},
         {"name": "VCC",   "net": "BAT_5V"},
         {"name": "GND",   "net": "GND"},
     ]},
    {"ref": "BAT1", "type": "battery_external",
     "pins": [{"name": "+", "net": "BAT_5V"},
              {"name": "-", "net": "GND"}]},
]


# ─── Scene 6 : NEMA17 + A4988 (DIP-16 on-BB) + battery + button ─────────
# A4988 : breakout DIP-16 pose sur breadboard (on-BB). Driver micropas
# pour stepper bipolar. Cote Arduino : STEP, DIR (commande), VDD (logic
# 5V), GND. Cote moteur : VMOT (alim batterie), 1A/1B (coil A), 2A/2B
# (coil B). RST tied a SLP pour activer (typique en mode non-microstep).
# 2 pins GND dans le SVG (9 et 15) ; on reference uniquement la premiere.
NEMA17_A4988_NETLIST = [
{"ref": "M1", "type": "nema17",
     "pins": [
         {"name": "1A", "net": "COIL_A_POS"},
         {"name": "1B", "net": "COIL_A_NEG"},
         {"name": "2A", "net": "COIL_B_POS"},
         {"name": "2B", "net": "COIL_B_NEG"},
     ]},
    {"ref": "U1", "type": "a4988",
     "pins": [
         {"name": "STEP", "net": "D7"},
         {"name": "DIR",  "net": "D8"},
         {"name": "VDD",  "net": "5V"},
         {"name": "GND",  "net": "GND"},
         {"name": "VMOT", "net": "BAT_5V"},
         {"name": "1A",   "net": "COIL_A_POS"},
         {"name": "1B",   "net": "COIL_A_NEG"},
         {"name": "2A",   "net": "COIL_B_POS"},
         {"name": "2B",   "net": "COIL_B_NEG"},
     ]},
    {"ref": "BAT1", "type": "battery_external",
     "pins": [{"name": "+", "net": "BAT_5V"},
              {"name": "-", "net": "GND"}]},
]


def _render(label: str, netlist: list[dict], out_path: Path) -> None:
    board_svg = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
    scene = place_scene(netlist, board_svg)
    wires = route_wires(scene, netlist)
    svg = SceneRenderer(scene, wires).render()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    print(f"  {label:20s}: canvas {scene.canvas_size}, "
          f"{len(scene.placed_components)} composants, {len(wires)} fils "
          f"-> {out_path.relative_to(ROOT)}")


def main() -> int:
    OUT = ROOT / "scripts" / "wiring_layout_test_output"
    print("[smoke v2 motors — drivers off-BB et on-BB]\n")
    # Off-BB <-> Off-BB
    _render("dc_motor + L298N",        DC_MOTOR_NETLIST,             OUT / "scene_v2_dc_motor.svg")
    _render("dc_motor + L293D module", DC_MOTOR_L293D_MOD_NETLIST,   OUT / "scene_v2_dc_l293d_module.svg")
    _render("stepper + ULN2003",       STEPPER_NETLIST,              OUT / "scene_v2_stepper.svg")
    # Off-BB <-> On-BB (DIP)
    _render("dc_motor + TB6612FNG",    DC_MOTOR_TB6612_NETLIST,      OUT / "scene_v2_dc_tb6612.svg")
    _render("dc_motor + DRV8833",      DC_MOTOR_DRV8833_NETLIST,     OUT / "scene_v2_dc_drv8833.svg")
    _render("NEMA17 + A4988",          NEMA17_A4988_NETLIST,         OUT / "scene_v2_nema17_a4988.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
