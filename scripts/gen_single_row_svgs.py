#!/usr/bin/env python3
"""Generateur procedural des SVG single-row (composants col unique sur breadboard).

Produit assets/wiring/components/single-row/{n}pins.svg pour n de 2 a 8,
plus les impairs 9, 11 et 13 (TODO #58, 2026-08-20).

Geometrie alignee sur la grille breadboard (cf breadboard_generator.py) :
  - pitch vertical = PITCH (28) entre 2 broches consecutives
  - premiere pin cy = TOP_PIN_CY (33) => espace en haut pour le nom
  - toutes les pins a cx = PIN_CX (3) — colonne unique a gauche
  - corps s'etend a DROITE de la pin sur BODY_W px => plus de place pour les noms

Convention d'ids (exigee par svg_component_loader.py) :
  <g id="component"> ; <rect id="component-body"> ; <text id="component-name">
  <circle id="pin-N-pos"> ; <text id="pin-N-label">
"""
from __future__ import annotations

from pathlib import Path

PITCH = 28
PIN_CX = 3
TOP_PIN_CY = 33           # cy de pin-1 — espace en haut pour le nom
STUB_END = 21             # x du bord gauche du corps (stub pin->corps = 18px)
BODY_TOP_Y = 1.5          # y du bord haut du corps
BODY_W = 112              # largeur du corps (4 pas) — nettement plus large qu'avant (78)
BOTTOM_PAD = 19           # espace sous la derniere pin jusqu'au bord bas du corps

PIN_R = 2
STROKE = "#000083"
BODY_FILL = "#ffffff"

ASSETS_DIR = (Path(__file__).resolve().parents[1]
              / "assets" / "wiring" / "components" / "single-row")

# Highest pin count this family draws. The geometry below is purely linear,
# so it holds for any n -- this bound is a SCOPE decision, not a constraint:
# even counts >= 10 are drawn as DIP instead (half as tall on the breadboard),
# and nothing above 13 has been needed (TODO #58, 2026-08-20).
MAX_PINS = 13


def single_row_svg(n: int) -> str:
    if n < 2 or n > MAX_PINS:
        raise ValueError(f"n={n} hors limites [2, {MAX_PINS}]")

    last_cy = TOP_PIN_CY + (n - 1) * PITCH
    body_h = last_cy + BOTTOM_PAD - BODY_TOP_Y
    vb_w = STUB_END + BODY_W + 2
    vb_h = BODY_TOP_Y + body_h + 1.5
    name_cx = STUB_END + BODY_W / 2
    name_y = 11.5
    label_x = STUB_END + 6

    L: list[str] = []
    L.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
    L.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{vb_w}" '
             f'height="{vb_h}" viewBox="0 0 {vb_w} {vb_h}" version="1.1">')
    L.append('  <g id="component">')
    L.append(f'    <rect id="component-body" x="{STUB_END}" y="{BODY_TOP_Y}" '
             f'width="{BODY_W}" height="{body_h:.1f}" ry="10" '
             f'style="fill:{BODY_FILL};stroke:{STROKE};stroke-width:2"/>')
    L.append(f'    <text id="component-name" x="{name_cx}" y="{name_y}" '
             f'style="font-size:8px;font-weight:bold;text-anchor:middle;fill:{STROKE}">'
             f'<tspan x="{name_cx}" y="{name_y}">Composant</tspan></text>')
    for idx in range(1, n + 1):
        cy = TOP_PIN_CY + (idx - 1) * PITCH
        L.append(f'    <path d="M {STUB_END},{cy} H {PIN_CX}" '
                 f'style="fill:none;stroke:{STROKE};stroke-width:2;stroke-linecap:round"/>')
        L.append(f'    <circle id="pin-{idx}-pos" cx="{PIN_CX}" cy="{cy}" '
                 f'r="{PIN_R}" style="fill:{STROKE};stroke:{STROKE}"/>')
        L.append(f'    <text id="pin-{idx}-label" x="{label_x}" y="{cy + 2.5}" '
                 f'style="font-size:8px;text-anchor:start;fill:{STROKE}">'
                 f'<tspan x="{label_x}" y="{cy + 2.5}">pin{idx}</tspan></text>')
    L.append('  </g>')
    L.append('</svg>')
    return "\n".join(L) + "\n"


def main() -> int:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    # 2-8 : la famille historique. 9/11/13 : les impairs ajoutes par #58 --
    # les comptes PAIRS >= 10 restent en DIP, deux fois moins hauts.
    for n in [*range(2, 9), 9, 11, 13]:
        (ASSETS_DIR / f"{n}pins.svg").write_text(single_row_svg(n), encoding="utf-8")
        print(f"  wrote {n}pins.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
