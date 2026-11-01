"""Generalise les cellules peintes d'un manual_zones.json sur le reste
de la BB via 2 modes : `tile` (replique verticalement la bbox peinte)
et `mirror` (place une copie miroir symetrique autour de l'axe horizontal
central de la BB).

Cas d'usage :
- `mirror` : la 1ere rangee de holes BB a un pattern special. La derniere
  rangee est identique mais miroir. Tu peins le pattern autour de la 1ere
  rangee + au-dessus, ce script genere automatiquement le pattern
  symetrique en bas de la BB.
- `tile` : tu peins quelques rangees representatives du milieu de la BB
  et tu replique vers le bas par pas de period.

Usage :
    python scripts/generalize_manual_zones.py --mode mirror
    python scripts/generalize_manual_zones.py --mode tile --bb-rows 1
    python scripts/generalize_manual_zones.py --mode both --bb-rows 1
    python scripts/generalize_manual_zones.py --source x.json --output y.json

Le script :
  1. Lit le source JSON
  2. Selon --mode :
     - mirror : symetrise les cellules peintes autour de l'axe horizontal
       central de la BB (= mid-row entre la 1ere et la derniere rangee
       de holes).
     - tile : replique la bbox des cellules peintes vers le bas par pas
       de period jusqu'a max_row.
     - both : mirror d'abord, puis tile.
  3. Saute toute cellule deja peinte au point cible (preserve les
     overrides manuels). Pas d'ecrasement.
  4. Ecrit le resultat dans --output puis affiche la commande pour
     previsualiser dans l'editeur.

Defaults :
  --source        assets/wiring/manual_zones.json
  --output        assets/wiring/manual_zones_generalized.json
  --mode          tile
  --period        auto (snap au multiple de pitch BB le plus proche)
  --bb-rows       alternative : period = bb_rows * (pitch / cell_size)
  --max-row       auto depuis la hauteur du BB SVG
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.wiring.routing.zone_editor.zone_store import COLORS, ZoneStore

DEFAULT_SOURCE = ROOT / "assets" / "wiring" / "manual_zones.json"
DEFAULT_OUTPUT = ROOT / "assets" / "wiring" / "manual_zones_generalized.json"
BB_PITCH_PX = 28  # entre 2 rows de holes BB

NS = {"svg": "http://www.w3.org/2000/svg"}


def get_bb_height(svg_path: Path) -> float:
    """Lit la hauteur (px) du BB SVG depuis le viewBox ou l'attribut height."""
    if not svg_path.exists():
        return 508.0  # mini.svg fallback
    try:
        root = ET.parse(svg_path).getroot()
    except ET.ParseError:
        return 508.0
    h = root.get("height")
    if h:
        return float(h.rstrip("px"))
    vb = root.get("viewBox")
    if vb:
        return float(vb.split()[3])
    return 508.0


def detect_bounds(store: ZoneStore) -> tuple[int, int] | None:
    """Retourne (row_min, row_max) sur l'ensemble des cellules peintes,
    None si aucune cellule."""
    all_rows: list[int] = []
    for color in COLORS:
        all_rows.extend(r for _c, r in store.cells[color])
    if not all_rows:
        return None
    return min(all_rows), max(all_rows)


def compute_max_row(store: ZoneStore, bb_h: float) -> int:
    """Derniere row editor au moins partiellement dans la BB.

    Pour mini.svg (bb_h=508) avec cs=7 et oy=5.5 : max_row = 71 (cellule
    spans [502.5, 509.5], dont 502.5..508 dans la BB). Pour permettre le
    mirror des cellules peintes au-dessus de la BB (row -1, -2) vers le
    bas, on prend cette borne inclusive.
    """
    cs = float(store.cell_size)
    anchor_y = float(store.bb_anchor[1])
    oy = (anchor_y - cs / 2.0) % cs
    return int((bb_h - oy) // cs)


def tile_vertically(store: ZoneStore, period: int, max_row: int,
                    source_row_range: tuple[int, int] | None = None) -> int:
    """Replique chaque cellule peinte vers le bas par pas de `period`,
    jusqu'a max_row.

    Si `source_row_range` est specifie (row_from, row_to inclusive), ne
    tile QUE les cellules dont la row appartient a cet intervalle. Sert
    a designer une "bande source" precise (ex : "tile rows 5..8 du
    pattern peint"). Sinon, tile depuis toutes les cellules peintes.

    Ne touche PAS une cellule deja peinte (preserve les overrides
    manuels). Retourne le nombre de cellules ajoutees.
    """
    added = 0
    rf, rt = (None, None) if source_row_range is None else source_row_range
    for color in COLORS:
        # Snapshot du source AVANT toute mutation (sinon les nouvelles
        # cellules tilees s'auto-replicent).
        if rf is None:
            original = list(store.cells[color])
        else:
            original = [(c, r) for (c, r) in store.cells[color] if rf <= r <= rt]
        for col, row in original:
            k = 1
            while True:
                new_row = row + k * period
                if new_row > max_row:
                    break
                cell = (col, new_row)
                # Skip si deja peinte (n'importe quelle couleur)
                if any(cell in store.cells[c] for c in COLORS):
                    k += 1
                    continue
                store.cells[color].add(cell)
                added += 1
                k += 1
    return added


def compute_bb_axis_row(store: ZoneStore, bb_h: float) -> tuple[float, int]:
    """Position editor-row de l'axe horizontal central de la BB.

    L'axe central est entre la cellule editor contenant la 1ere rangee
    de holes (canvas y = anchor_y) et la cellule contenant la derniere
    (canvas y = anchor_y + (N-1)*pitch).

    Renvoie (axis_row, n_rows). axis_row peut etre x.5 si N pair.
    """
    cs = float(store.cell_size)
    anchor_y = float(store.bb_anchor[1])
    oy = (anchor_y - cs / 2.0) % cs
    # Cell row contenant la 1ere rangee de holes (= floor)
    first_hole_row = int((anchor_y - oy) // cs)
    # Nombre de rangees BB : 1ere a y=anchor_y, derniere a y telle que
    # body est symetrique (= bb_h - anchor_y du bas)
    n_rows = int((bb_h - 2 * anchor_y) / BB_PITCH_PX) + 1
    last_hole_y = anchor_y + (n_rows - 1) * BB_PITCH_PX
    last_hole_row = int((last_hole_y - oy) // cs)
    axis_row = (first_hole_row + last_hole_row) / 2.0
    return axis_row, n_rows


def mirror_vertically(store: ZoneStore, axis_row: float,
                      max_row: int) -> tuple[int, int]:
    """Symetrise les cellules peintes autour de l'axe horizontal `axis_row`.

    Pour chaque cellule peinte (col, row), calcule mirror_row = 2*axis - row
    et ajoute (col, round(mirror_row)) avec la meme couleur, si la
    cellule cible n'est pas deja peinte et qu'elle reste dans [0, max_row].

    Retourne (added, skipped_outside) ou skipped_outside compte les
    cellules dont le mirror tombe hors de la BB.
    """
    added = 0
    skipped_outside = 0
    for color in COLORS:
        original = list(store.cells[color])  # snapshot
        for col, row in original:
            mirror_row_f = 2.0 * axis_row - row
            mirror_row = int(round(mirror_row_f))
            if mirror_row < 0 or mirror_row > max_row:
                skipped_outside += 1
                continue
            cell = (col, mirror_row)
            if any(cell in store.cells[c] for c in COLORS):
                continue
            store.cells[color].add(cell)
            added += 1
    return added, skipped_outside


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help=f"JSON source (default {DEFAULT_SOURCE})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"JSON destination (default {DEFAULT_OUTPUT})")
    parser.add_argument("--mode", choices=("tile", "mirror", "both"),
                        default="tile",
                        help="Strategie de generalisation (default tile)")
    parser.add_argument("--period", type=int, default=None,
                        help="Period tile en editor-cells (default auto)")
    parser.add_argument("--bb-rows", type=int, default=None,
                        help="Tile : period = bb_rows * (28 / cell_size)")
    parser.add_argument("--tile-from", type=int, default=None,
                        help="Tile : 1ere row source (limite la bande source)")
    parser.add_argument("--tile-to", type=int, default=None,
                        help="Tile : derniere row source (incluse)")
    parser.add_argument("--max-row", type=int, default=None,
                        help="Derniere row editor a remplir (default auto)")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"ERREUR : {args.source} introuvable.")
        return 1

    store = ZoneStore.load(args.source)
    bb_svg_path = ROOT / store.bb_svg
    bb_h = get_bb_height(bb_svg_path)

    bounds = detect_bounds(store)
    if bounds is None:
        print("Aucune cellule peinte. Rien a tiler.")
        return 1
    row_min, row_max = bounds
    band_height = row_max - row_min + 1

    # Sous-bande source pour le tile : --tile-from/--tile-to override la bbox
    if args.tile_from is not None and args.tile_to is not None:
        tile_src_range = (args.tile_from, args.tile_to)
        tile_src_height = args.tile_to - args.tile_from + 1
    else:
        tile_src_range = None
        tile_src_height = band_height

    cs = store.cell_size
    bb_row_in_editor_cells = BB_PITCH_PX / cs  # nombre d'editor-rows par pitch BB
    # Estimation entiere : combien de rows BB couvre la bande peinte
    estimated_bb_rows = round(band_height / bb_row_in_editor_cells)

    # Determine period
    if args.bb_rows is not None:
        period = int(args.bb_rows * bb_row_in_editor_cells)
        period_src = f"--bb-rows={args.bb_rows} (= {period} editor-cells)"
    elif args.period is not None:
        period = args.period
        period_src = f"--period={args.period}"
    else:
        # Auto : snap au plus proche multiple de bb_row_in_editor_cells
        # pour garantir l'alignement des tiles successifs sur les rangees
        # BB. Si --tile-from/--tile-to specifies, on utilise la hauteur de
        # la sous-bande source directement (l'utilisateur a choisi pile).
        snap = int(round(bb_row_in_editor_cells))
        if tile_src_range is not None:
            period = tile_src_height
            period_src = (f"auto = hauteur sous-bande source ({period})")
        elif snap <= 0:
            period = band_height
            period_src = f"auto = bbox height ({band_height})"
        else:
            # On prefere snap DOWN pour densite + couverture (vs gap)
            period = max(snap, (band_height // snap) * snap)
            if period == band_height:
                period_src = f"auto = bbox height ({band_height})"
            else:
                period_src = (f"auto = floor({band_height}/{snap})*{snap} = "
                              f"{period} (snap multiple BB pitch)")

    if period <= 0:
        print(f"ERREUR : period invalide ({period}).")
        return 1

    max_row = args.max_row if args.max_row is not None else compute_max_row(store, bb_h)

    axis_row, bb_n_rows = compute_bb_axis_row(store, bb_h)

    # ── Display the layout ──────────────────────────────────────────────
    print(f"Source       : {args.source}")
    print(f"  cell_size  : {cs}")
    print(f"  bb_svg     : {store.bb_svg}  (hauteur {bb_h:.0f} px, ~{bb_n_rows} rangees holes)")
    print(f"  pitch BB   : {BB_PITCH_PX} px = {bb_row_in_editor_cells:.1f} editor-cells")
    print(f"  axe horiz. : editor row {axis_row:.1f} (mid entre 1ere et derniere rangee holes)")
    print(f"  cellules peintes :")
    for color in COLORS:
        print(f"    {color:>6} : {len(store.cells[color])}")
    print(f"  rows peintes : {row_min} .. {row_max} (bande {band_height} editor-cells)")
    print(f"  cette bande couvre ~{estimated_bb_rows} rangee(s) BB")
    print()
    print(f"Mode : {args.mode}")

    total_added = 0

    if args.mode in ("mirror", "both"):
        print(f"  mirror   : axe row {axis_row:.1f}")
        added_m, skipped = mirror_vertically(store, axis_row, max_row)
        print(f"    + {added_m} cellules ajoutees (skip {skipped} hors BB)")
        total_added += added_m

    if args.mode in ("tile", "both"):
        src_str = (f"sous-bande rows {tile_src_range[0]}..{tile_src_range[1]}"
                    if tile_src_range else "bbox complete")
        print(f"  tile     : source = {src_str}")
        print(f"             period {period_src}, max row {max_row}")
        added_t = tile_vertically(store, period=period, max_row=max_row,
                                   source_row_range=tile_src_range)
        print(f"    + {added_t} cellules ajoutees (skip si deja peintes)")
        total_added += added_t

    print(f"\nTotal ajoute : {total_added} cellules")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    store.save(args.output)
    print(f"\nResultat ecrit : {args.output}")
    print(f"\nPour previsualiser dans l'editeur :")
    print(f"  python scripts/cell_zone_editor.py --json \"{args.output}\"")
    print(f"\nSi le rendu te plait, remplace le source :")
    print(f"  copy \"{args.output}\" \"{args.source}\"  (Windows)")
    print(f"  mv \"{args.output}\" \"{args.source}\"    (Unix)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
