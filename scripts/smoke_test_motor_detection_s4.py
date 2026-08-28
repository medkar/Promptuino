"""Smoke test pour la Strategie 4 du detecteur moteur DC (hardware fallback).

Verifie que S4 :
  - Cas A : code 'fragile' (indirection array opaque) + prompt motor+chip
            -> active, classe les pins via boards.json capabilities, groupe
            en 2 moteurs corrects.
  - Cas B : meme code, prompt SANS keyword moteur ou SANS chip
            -> inactive, 6 LEDs ambigues separees (comportement actuel).
  - Cas C : code 'normal' S1 (analogWrite literal direct) + prompt
            -> S4 ne perturbe pas (S1 a deja rempli pwm_nets).

Hardware-agnostique : marche pour n'importe quelle carte du catalogue
qui expose `Board.pwm_capable_pins()`. Le test cible Uno R3 par defaut.
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

from ui.wiring.markers import extract_netlist


BOARD_ID = "arduino_uno_r3"


# Code "fragile" : 6 pins OUTPUT (3 par moteur), mais ecritures via
# indirection `motorPins[i]` -> S1 ne peut pas normaliser, S2 et S3
# ratent aussi (pas de helper params=pins, pas de dispatch local).
FRAGILE_CODE = """
int motorPins[] = {5, 4, 7, 6, 8, 2};

void setup() {
  pinMode(5, OUTPUT);
  pinMode(4, OUTPUT);
  pinMode(7, OUTPUT);
  pinMode(6, OUTPUT);
  pinMode(8, OUTPUT);
  pinMode(2, OUTPUT);
}

void loop() {
  analogWrite(motorPins[0], 200);
  digitalWrite(motorPins[1], HIGH);
  digitalWrite(motorPins[2], LOW);
  analogWrite(motorPins[3], 150);
  digitalWrite(motorPins[4], HIGH);
  digitalWrite(motorPins[5], LOW);
}
"""

# Code "normal" S1 : analogWrite direct sur literal pin.
NORMAL_CODE = """
void setup() {
  pinMode(5, OUTPUT);
  pinMode(4, OUTPUT);
  pinMode(7, OUTPUT);
}

void loop() {
  analogWrite(5, 200);
  digitalWrite(4, HIGH);
  digitalWrite(7, LOW);
}
"""


def _count_grouped_motors(nl) -> tuple[int, int]:
    """Retourne (n_motors_groupes, n_leds_ambigues_orphelines)."""
    n_grouped = 0
    n_orphan = 0
    for c in nl.components:
        if c.type != "led":
            continue
        if c.attributes.get("_grouped_pwm_pin"):
            n_grouped += 1
        elif c.attributes.get("_confidence") == "low":
            n_orphan += 1
    return n_grouped, n_orphan


def _summarize(nl) -> str:
    parts = []
    for c in nl.components:
        if c.type != "led":
            continue
        pwm = c.attributes.get("_grouped_pwm_pin")
        dirs = c.attributes.get("_grouped_dir_pins")
        amb = c.attributes.get("_confidence") == "low"
        sig = c.pin("A")
        net = sig.net if sig else "?"
        if pwm:
            parts.append(f"motor[{pwm}|dirs={dirs}]")
        elif amb:
            parts.append(f"led_amb[{net}]")
    return ", ".join(parts) if parts else "(rien)"


def _run_case(label: str, code: str, prompt: str,
              expected_motors: int, expected_orphans: int) -> bool:
    nl = extract_netlist(code, BOARD_ID, prompt=prompt)
    n_grouped, n_orphan = _count_grouped_motors(nl)
    ok = (n_grouped == expected_motors and n_orphan == expected_orphans)
    status = "OK  " if ok else "FAIL"
    print(f"  [{status}] {label}")
    print(f"         -> motors_groupes={n_grouped} (attendu {expected_motors})"
          f" / orphan_leds={n_orphan} (attendu {expected_orphans})")
    print(f"         -> {_summarize(nl)}")
    return ok


def main() -> int:
    print("=== Smoke test Strategie 4 (hardware-fallback) ===\n")
    results: list[bool] = []

    print("CAS A : code fragile + prompt '2 moteurs DC L298N'")
    print("        attendu : S4 active, classe via boards.json, 2 motors")
    results.append(_run_case(
        "A-1 fragile + prompt complet",
        FRAGILE_CODE,
        prompt="Pilote 2 moteurs DC avec un L298N",
        expected_motors=2, expected_orphans=0,
    ))
    print()

    print("CAS B : code fragile, prompt vide ou incomplet")
    print("        attendu : S4 inactive (garde-fou), 6 LEDs ambigues")
    results.append(_run_case(
        "B-1 fragile + prompt vide",
        FRAGILE_CODE, prompt="",
        expected_motors=0, expected_orphans=6,
    ))
    results.append(_run_case(
        "B-2 fragile + prompt 'moteur' sans chip",
        FRAGILE_CODE, prompt="Pilote 2 moteurs",
        expected_motors=0, expected_orphans=6,
    ))
    results.append(_run_case(
        "B-3 fragile + prompt 'L298N' sans 'moteur'",
        FRAGILE_CODE, prompt="Cable un L298N",
        expected_motors=0, expected_orphans=6,
    ))
    print()

    print("CAS C : code normal S1 + prompt 'moteur DC'")
    print("        attendu : S1 a la main, S4 ne perturbe pas (1 motor)")
    results.append(_run_case(
        "C-1 normal + prompt",
        NORMAL_CODE, prompt="Pilote 1 moteur DC avec un L298N",
        expected_motors=1, expected_orphans=0,
    ))
    results.append(_run_case(
        "C-2 normal sans prompt (S4 inactif de toute facon)",
        NORMAL_CODE, prompt="",
        expected_motors=1, expected_orphans=0,
    ))
    print()

    n_ok = sum(results)
    n_total = len(results)
    print(f"=== Resume : {n_ok}/{n_total} cas OK ===")
    return 0 if n_ok == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
