#!/usr/bin/env python3
"""Generateur procedural des SVG DIP (composants 2 cotes poses sur breadboard).

Produit assets/wiring/components/dip/{n}pins.svg pour n pair de 4 a 40.

Geometrie alignee sur la grille breadboard (cf breadboard_generator.py) :
  - pitch vertical = PITCH (28) entre 2 broches d'un meme cote
  - ecart horizontal entre les 2 colonnes = CHANNEL_SPAN (140 = d->g = 5 pas)

Le renderer n'ancre le SVG que sur pin-1 ; la geometrie INTERNE doit donc
matcher la grille pour que TOUTES les broches tombent sur les trous.

Convention d'ids (exigee par svg_component_loader.py) :
  <g id="component"> ; <rect id="component-body"> ; <text id="component-name">
  <circle id="pin-N-pos"> ; <text id="pin-N-label">

Numerotation (coherente avec layout._build_pin_to_hole_main) :
  pin 1..half   -> colonne gauche, de haut en bas
  pin half+1..N -> colonne droite, de bas en haut
"""
from __future__ import annotations

from pathlib import Path

PITCH = 28
CHANNEL_SPAN = 140           # d->g = 5 pas (corps large pour les noms ; Fritzing = taille reelle)
PIN_R = 2
LEFT_PIN_CX = 3
RIGHT_PIN_CX = LEFT_PIN_CX + CHANNEL_SPAN     # 143
STUB = 8                     # longueur du stub body->pin
TOP_PIN_CY = 33              # cy de pin-1 (espace au-dessus pour le nom)
BODY_TOP_Y = 1.5
BOTTOM_PAD = 16.5            # espace sous la derniere broche

BODY_X = LEFT_PIN_CX + STUB                    # 11
BODY_W = CHANNEL_SPAN - 2 * STUB               # 124

STROKE = "#000083"
BODY_FILL = "#ffffff"

ASSETS_DIR = (Path(__file__).resolve().parents[1]
              / "assets" / "wiring" / "components" / "dip")


def _pin_positions(n: int) -> dict[int, tuple[float, float]]:
    half = n // 2
    pos: dict[int, tuple[float, float]] = {}
    for i in range(1, half + 1):                       # gauche, haut->bas
        pos[i] = (LEFT_PIN_CX, TOP_PIN_CY + (i - 1) * PITCH)
    for k in range(1, half + 1):                       # droite, bas->haut
        pos[half + k] = (RIGHT_PIN_CX, TOP_PIN_CY + (half - k) * PITCH)
    return pos


def dip_svg(n: int) -> str:
    if n < 4 or n % 2 != 0:
        raise ValueError(f"n={n} doit etre pair et >= 4")
    half = n // 2
    pos = _pin_positions(n)
    last_cy = TOP_PIN_CY + (half - 1) * PITCH
    body_h = last_cy + BOTTOM_PAD - BODY_TOP_Y
    vb_w = RIGHT_PIN_CX + PIN_R + 1
    vb_h = BODY_TOP_Y + body_h + 1.5
    name_cx = BODY_X + BODY_W / 2

    L: list[str] = []
    L.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
    L.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{vb_w}" '
             f'height="{vb_h}" viewBox="0 0 {vb_w} {vb_h}" version="1.1">')
    L.append('  <g id="component">')
    L.append(f'    <rect id="component-body" x="{BODY_X}" y="{BODY_TOP_Y}" '
             f'width="{BODY_W}" height="{body_h}" ry="10" '
             f'style="fill:{BODY_FILL};stroke:{STROKE};stroke-width:2"/>')
    L.append(f'    <text id="component-name" x="{name_cx}" y="11.5" '
             f'style="font-size:8px;font-weight:bold;text-anchor:middle;fill:{STROKE}">'
             f'<tspan x="{name_cx}" y="11.5">Composant</tspan></text>')
    for idx in range(1, n + 1):
        cx, cy = pos[idx]
        if cx == LEFT_PIN_CX:
            stub_x1, stub_x2 = BODY_X, cx
            label_x, anchor = BODY_X + 6, "start"
        else:
            stub_x1, stub_x2 = BODY_X + BODY_W, cx
            label_x, anchor = BODY_X + BODY_W - 6, "end"
        L.append(f'    <path d="M {stub_x1},{cy} H {stub_x2}" '
                 f'style="fill:none;stroke:{STROKE};stroke-width:2;'
                 f'stroke-linecap:round"/>')
        L.append(f'    <circle id="pin-{idx}-pos" cx="{cx}" cy="{cy}" '
                 f'r="{PIN_R}" style="fill:{STROKE};stroke:{STROKE}"/>')
        L.append(f'    <text id="pin-{idx}-label" x="{label_x}" y="{cy + 2.5}" '
                 f'style="font-size:8px;text-anchor:{anchor};fill:{STROKE}">'
                 f'<tspan x="{label_x}" y="{cy + 2.5}">pin{idx}</tspan></text>')
    L.append('  </g>')
    L.append('</svg>')
    return "\n".join(L) + "\n"


def main() -> int:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for n in range(4, 41, 2):
        (ASSETS_DIR / f"{n}pins.svg").write_text(dip_svg(n), encoding="utf-8")
        print(f"  wrote {n}pins.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
