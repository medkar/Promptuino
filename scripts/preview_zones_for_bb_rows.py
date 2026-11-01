"""Genere une BB a N rangees, copie la source manual_zones.json peinte
sur la BB 17 rangees standard, et applique la generalisation (mirror +
tile rows 5..8). Produit un JSON pretvisualiser dans l'editeur.

Usage :
    python scripts/preview_zones_for_bb_rows.py --rows 18
    python scripts/preview_zones_for_bb_rows.py --rows 30
    python scripts/preview_zones_for_bb_rows.py --rows 18 --tile-from 5 --tile-to 8
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.wiring.layout.breadboard_generator import Breadboard
from ui.wiring.routing.zone_editor.zone_store import (
    COLORS, ZoneStore, grid_origin_offset,
)
# Import internes du script generalize via execfile-style — simple, evite
# de bouger ces fonctions dans un module proper. C'est un outil dev.
from scripts.generalize_manual_zones import (
    compute_bb_axis_row,
    compute_max_row,
    get_bb_height,
    mirror_vertically,
    tile_vertically,
)

SOURCE_JSON = ROOT / "assets" / "wiring" / "manual_zones.json"

# Couleurs SVG (avec alpha) pour le rendu statique
COLOR_FILL = {
    "forbid": "rgba(214, 39, 40, 0.55)",
    "cost":   "rgba(240, 192, 0, 0.45)",
    "allow":  "rgba(40, 167, 69, 0.50)",
}


def render_static_preview(store: ZoneStore, bb_svg_path: Path,
                           bb_w: float, bb_h: float, out_path: Path) -> None:
    """Genere un SVG statique avec la BB en fond (opacity 0.55) et les
    cellules peintes superposees en couleur. Lisible dans n'importe
    quel navigateur, pas besoin de Qt."""
    cs = float(store.cell_size)
    ox, oy = grid_origin_offset(store.bb_anchor, store.cell_size)

    rects: list[str] = []
    for color in COLORS:
        fill = COLOR_FILL[color]
        for (col, row) in sorted(store.cells[color]):
            x = ox + col * cs
            y = oy + row * cs
            rects.append(
                f'  <rect x="{x:.3f}" y="{y:.3f}" '
                f'width="{cs}" height="{cs}" fill="{fill}" stroke="none"/>'
            )

    bb_content = bb_svg_path.read_text(encoding="utf-8")
    # On extrait l'interieur du <svg> pour le re-embedded
    import re
    m = re.search(r"<svg[^>]*>(.*)</svg>", bb_content, re.DOTALL)
    bb_inner = m.group(1) if m else ""

    svg = f'''<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{bb_w}" height="{bb_h}" viewBox="0 0 {bb_w} {bb_h}">
  <rect x="0" y="0" width="{bb_w}" height="{bb_h}" fill="#fafafa"/>
  <g id="bb-bg" opacity="0.55">{bb_inner}</g>
  <g id="zones">
{chr(10).join(rects)}
  </g>
</svg>
'''
    out_path.write_text(svg, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", type=int, default=18,
                        help="Nombre de rangees de la BB cible (default 18)")
    parser.add_argument("--tile-from", type=int, default=5,
                        help="1ere row source pour tile (default 5)")
    parser.add_argument("--tile-to", type=int, default=8,
                        help="Derniere row source pour tile (default 8)")
    parser.add_argument("--source", type=Path, default=SOURCE_JSON,
                        help=f"JSON source peinte (default {SOURCE_JSON})")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"ERREUR : {args.source} introuvable.")
        return 1

    # 1. Genere la BB SVG a N rangees
    bb_svg_path = ROOT / "assets" / "wiring" / "breadboards" / f"mini_{args.rows}rows.svg"
    bb_svg_path.parent.mkdir(parents=True, exist_ok=True)
    bb = Breadboard(rows=args.rows)
    bb_svg_path.write_text(bb.render(), encoding="utf-8")
    print(f"BB SVG genere   : {bb_svg_path} ({bb.size[0]}x{bb.size[1]})")

    # 2. Charge la source peinte, retarge le bb_svg
    store = ZoneStore.load(args.source)
    relative_bb = bb_svg_path.relative_to(ROOT).as_posix()
    store.bb_svg = relative_bb
    print(f"Cellules source : forbid={len(store.cells['forbid'])} "
          f"cost={len(store.cells['cost'])} allow={len(store.cells['allow'])}")

    # 3. Applique mirror + tile dans le contexte de la nouvelle BB
    bb_h = float(bb.size[1])
    axis_row, n_rows = compute_bb_axis_row(store, bb_h)
    max_row = compute_max_row(store, bb_h)
    print(f"BB cible        : {args.rows} rangees, height {bb_h:.0f} px, "
          f"axe row {axis_row}, max_row {max_row}")

    added_m, skipped = mirror_vertically(store, axis_row, max_row)
    print(f"mirror          : +{added_m} cellules (skip {skipped})")

    tile_range = (args.tile_from, args.tile_to)
    period = args.tile_to - args.tile_from + 1
    added_t = tile_vertically(store, period=period, max_row=max_row,
                               source_row_range=tile_range)
    print(f"tile            : rows {args.tile_from}..{args.tile_to} (period {period}), "
          f"+{added_t} cellules")

    # 4. Sauve le JSON
    out_json = ROOT / "assets" / "wiring" / f"manual_zones_{args.rows}rows.json"
    store.save(out_json)
    print(f"\nJSON ecrit      : {out_json}")

    # 5. Genere un SVG de preview statique (visualisable directement)
    out_svg = ROOT / "scripts" / "wiring_routing_test_output" / f"preview_zones_{args.rows}rows.svg"
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    render_static_preview(store, bb_svg_path, bb.size[0], bb.size[1], out_svg)
    print(f"SVG preview     : {out_svg}")
    print(f"\nOuvre l'un OU l'autre :")
    print(f"  static SVG : {out_svg}")
    print(f'  editeur Qt : python scripts/cell_zone_editor.py --json "{out_json}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
