"""Batterie #82 : quels prompts moteur SANS puce nommee injectent une lib
liee a une puce de driver ?

La regle en cours d'etude : une lib rattachee a un composant
`function="motor_driver"` du registre ne doit s'injecter que si le prompt (ou
l'indice projet, deja concatene par `_build_lib_context`) nomme la puce. Le
code moteur a une forme SANS lib (PWM + broches de direction), et le choix du
driver appartient a la modale de cablage -- s'engager sur une puce a la
generation, c'est decider a la place de la modale.

⚠️ Ce banc mesure la couche qui DECIDE (`retrieve_libs`, aux parametres de
l'app via `build_lib_context`), pas un ersatz. Il sert avant/apres : le
lancer AVANT le filtre etablit l'etendue du defaut, le relancer APRES prouve
la correction et l'absence de degat collateral (bandes temoins).

Run : python scripts/bench_motor_agnostic.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import rag  # noqa: E402


def _driver_docs() -> frozenset:
    from ui.component_registry import REGISTRY
    comps = REGISTRY.values() if isinstance(REGISTRY, dict) else REGISTRY
    return frozenset(d for c in comps if c.function == "motor_driver"
                     for d in c.documents)


# ── Bande 1 : moteur, AUCUNE puce nommee → aucune lib de driver ─────────
GENERIQUES = [
    ("fr", "deux moteurs DC"),
    ("fr", "fais tourner un moteur"),
    ("fr", "contrôle la vitesse d'un moteur avec un potentiomètre"),
    ("fr", "un robot à deux roues qui avance et recule"),
    ("fr", "faire tourner un moteur dans les deux sens"),
    ("fr", "un moteur qui accélère progressivement"),
    ("fr", "fais bouger trois servos"),
    ("fr", "un moteur pas à pas qui fait un tour complet"),
    ("fr", "fais vibrer un petit moteur vibrant"),
    ("en", "two DC motors forward and backward"),
    ("en", "spin a DC motor"),
    ("en", "control a DC motor speed with a potentiometer"),
    ("en", "a stepper motor doing one revolution"),
    ("en", "move three servos"),
    ("es", "dos motores DC"),
    ("es", "controlar la velocidad de un motor"),
    ("it", "due motori DC"),
    ("it", "far girare un motore passo passo"),
]

# ── Bande 2 : la puce EST nommee → sa lib doit RESTER injectable ────────
NOMMES = [
    ("fr", "2 moteurs DC avec un L298N", "l298n"),
    ("fr", "un moteur avec un TB6612", "sparkfun-tb6612"),
    ("fr", "un moteur pas à pas avec un DRV8825", "drv8825"),
    ("fr", "trois servos avec un PCA9685", "pca9685"),
    ("en", "a stepper with a TMC2209 driver", "tmc2209"),
    ("fr", "deux moteurs avec le Grove I2C motor driver", "grove-i2c-motor-driver"),
]

# ── Bande 3 : l'indice PROJET nomme la puce (#64) → passe aussi ─────────
# `_build_lib_context` concatene le hint au prompt avant `retrieve_libs` ;
# on reproduit exactement cette forme.
AVEC_HINT = [
    ("fr", "augmente la vitesse du moteur", "l298n"),
    ("fr", "inverse le sens de rotation", "drv8825"),
]

# ── Bande 4 : temoins HORS moteur → strictement inchanges ───────────────
TEMOINS = [
    ("fr", "affiche la température sur un écran OLED"),
    ("fr", "mesure la température et affiche-la"),
    ("fr", "scanner i2c"),
    ("en", "read a distance with an ultrasonic sensor"),
]


def _libs(prompt: str) -> list[tuple[str, float]]:
    """Ce que l'app injecterait : memes parametres que `_build_lib_context`
    (k=3, plancher `_CODEGEN_MIN_SCORE`)."""
    out = rag.retrieve_libs(prompt, k=3, threshold=rag._CODEGEN_MIN_SCORE)
    return [(e.get("id", "?"), round(e.get("_score", 0.0), 3)) for e in out]


def main() -> None:
    if not rag._load():
        print("MODELE ONNX INDISPONIBLE -- mesure impossible, on refuse de "
              "conclure.")
        sys.exit(2)
    drivers = _driver_docs()
    print(f"docs de drivers (registre, function=motor_driver) : "
          f"{len(drivers)}\n  {sorted(drivers)}\n")

    fautes = 0
    print("=== BANDE 1 : generique, AUCUNE puce nommee ===")
    for lang, p in GENERIQUES:
        libs = _libs(p)
        mauvaises = [i for i, _ in libs if i in drivers]
        marque = "  ❌ DRIVER INJECTE" if mauvaises else ""
        if mauvaises:
            fautes += 1
        print(f"  [{lang}] {p!r:58} -> {libs}{marque}")

    manques = 0
    print("\n=== BANDE 2 : puce NOMMEE (doit rester injectable) ===")
    for lang, p, attendu in NOMMES:
        libs = _libs(p)
        ok = any(i == attendu for i, _ in libs)
        if not ok:
            manques += 1
        print(f"  [{lang}] {p!r:58} -> {libs}"
              f"{'' if ok else f'  ❌ {attendu} ABSENT'}")

    print("\n=== BANDE 3 : indice PROJET (#64, hint concatene) ===")
    for lang, p, hint in AVEC_HINT:
        libs = _libs(p + "\n" + hint)
        ok = any(i == hint for i, _ in libs)
        if not ok:
            manques += 1
        print(f"  [{lang}] {p!r:40} +hint={hint!r:12} -> {libs}"
              f"{'' if ok else f'  ❌ {hint} ABSENT'}")

    print("\n=== BANDE 4 : temoins hors moteur ===")
    for lang, p in TEMOINS:
        print(f"  [{lang}] {p!r:58} -> {_libs(p)}")

    print(f"\nBILAN : {fautes}/{len(GENERIQUES)} prompts generiques injectent "
          f"une lib de driver ; {manques} nommes/hints perdus.")
    sys.exit(0)


if __name__ == "__main__":
    main()
