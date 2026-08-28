"""Lit le SVG annote `debug_grid_generic.svg`, applique les overrides
manuels a une occupancy grid neuve, et re-rend le visuel avec les zones
appliquees pour verification.

Usage :
  1. Edite scripts/wiring_routing_test_output/debug_grid_generic.svg dans
     Inkscape :
       - Active les layers manual-forbid / manual-allow / manual-cost /
         manual-pin-owner via Layer > Layer (Ctrl+L).
       - Dessine des <rect> dans le layer souhaite (outil R).
       - Pour manual-cost : ajoute manuellement l'attribut data-cost="N"
         via Object Properties (Object > Object Properties, champ
         "More properties..." dans Inkscape recent).
       - Pour manual-pin-owner : data-net="5V" / "GND" / etc.
       - Sauvegarde (Plain SVG de preference).

  2. Lance python scripts/apply_manual_zones.py pour generer
     scripts/wiring_routing_test_output/debug_grid_after_manual.svg qui
     reflete la grille apres application des overrides.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.smoke_test_wiring_routing_phase4 import DC_MOTOR_TB6612_NETLIST, BOARD_SVG
from ui.wiring.layout.layout import place_scene
from ui.wiring.routing.occupancy import build_occupancy_grid
from ui.wiring.routing.manual_zones import apply_manual_zones, parse_manual_zones

OUT = Path(__file__).resolve().parent / "wiring_routing_test_output"
INPUT_SVG = OUT / "debug_grid_generic.svg"
OUTPUT_SVG = OUT / "debug_grid_after_manual.svg"


def main() -> int:
    if not INPUT_SVG.exists():
        print(f"ERROR : {INPUT_SVG} introuvable. Lance d'abord "
              f"python scripts/debug_wiring_routing_grid_generic.py")
        return 1

    # 1. Reconstruit la scene + grille generique (sans composants)
    scene = place_scene(DC_MOTOR_TB6612_NETLIST, BOARD_SVG)
    scene.placed_components = []
    grid, net_to_id = build_occupancy_grid(scene, DC_MOTOR_TB6612_NETLIST,
                                             cell_size=8)

    # 2. Applique les zones manuelles depuis le SVG annote
    counts = apply_manual_zones(grid, net_to_id, INPUT_SVG)
    print(f"Zones manuelles appliquees : {counts}")
    if all(v == 0 for v in counts.values()):
        print("  (aucun rect detecte dans les layers manual-*)")
        print(f"  edite {INPUT_SVG} dans Inkscape pour ajouter des zones.")

    # 3. Re-rend le visuel avec la grille mise a jour
    import xml.etree.ElementTree as ET
    NS = {"svg": "http://www.w3.org/2000/svg"}

    def _extract_inner(svg_str: str, group_id: str) -> str:
        root = ET.fromstring(svg_str)
        g = root.find(f".//svg:g[@id='{group_id}']", NS)
        return ET.tostring(g, encoding="unicode") if g is not None else ""

    canvas_w, canvas_h = scene.canvas_size
    cs = grid.cell_size
    cell_rects: list[str] = []
    for r in range(grid.rows):
        for c in range(grid.cols):
            x = c * cs
            y = r * cs
            body = int(grid.body_mask[r, c])
            pin = int(grid.pin_owner[r, c])
            cost = int(grid.cost_map[r, c])
            if body == 1:
                color = "rgba(255,0,0,0.45)"
            elif pin != 0:
                color = "rgba(0,100,255,0.50)"
            elif cost > 0:
                color = "rgba(255,200,0,0.35)"
            else:
                color = "rgba(0,200,0,0.20)"
            cell_rects.append(
                f'<rect x="{x}" y="{y}" width="{cs}" height="{cs}" '
                f'fill="{color}" stroke="none"/>'
            )

    bb_fragments = []
    for i, bb in enumerate(scene.breadboards):
        bb_tx, bb_ty = scene.breadboard_translates[i]
        inner = _extract_inner(bb.render(), "breadboard")
        bb_fragments.append(
            f'<g transform="translate({bb_tx},{bb_ty})">{inner}</g>'
        )
    board_svg = scene.board_loader.render(
        translate=scene.board_translate, instance_id="board-instance",
    )

    svg = f'''<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}">
  <rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="#fafafa"/>
  <g id="bb-arduino-base" opacity="0.35">
    {chr(10).join(bb_fragments)}
    {board_svg}
  </g>
  <g id="grid-overlay" opacity="0.85">
    {chr(10).join(cell_rects)}
  </g>
</svg>
'''
    OUTPUT_SVG.write_text(svg, encoding="utf-8")
    print(f"Wrote {OUTPUT_SVG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
