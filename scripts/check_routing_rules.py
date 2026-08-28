"""Verifie automatiquement que les wires generes par le routeur v3
respectent les regles documentees dans `feedback_wiring_routing_rules.md`.

Regles verifiees :
  - R1   : aucun fil ne traverse un hole BB (tie-strip ou rail), sauf
           a son endpoint.
  - R1b  : aucun fil ne passe dans le body bbox d'un composant on-BB
           (DIP ou single-row), sauf a son endpoint.
  - R5   : aucune superposition de 2 fils (= meme segment partage par
           2 wires, sur le meme axe). Crossings perpendiculaires OK.
  - R7-1 STRICT : un fil qui tap row 1 ou row N d'un rail BB doit
           arriver verticalement (segment adjacent partage x avec
           l'endpoint).
  - R7-2 STRICT : un fil qui tap une row mid (2..N-1) sur un OUTER
           rail (V+_left ou GND_right en convention v2) doit arriver
           horizontalement.

Si une violation est detectee : exit code 1 + dump des wires en cause.
Sinon : exit 0.

Usage :
    python scripts/check_routing_rules.py

Tourne sur les 8 scenes des smoke tests v3.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.layout.layout import place_scene
from ui.wiring.routing import route_wires as _route_wires_impl, FEATURE_FLAG_ENV

os.environ[FEATURE_FLAG_ENV] = "v3"


def route_wires(scene, netlist):
    """Wrapper v3 (partial=True : skip wires impossibles)."""
    return _route_wires_impl(scene, netlist, partial=True)


from scripts.smoke_test_wiring_layout_motors import (
    DC_MOTOR_NETLIST,
    DC_MOTOR_L293D_MOD_NETLIST,
    STEPPER_NETLIST,
    DC_MOTOR_TB6612_NETLIST,
    DC_MOTOR_DRV8833_NETLIST,
    NEMA17_A4988_NETLIST,
)
from scripts.smoke_test_wiring_servo_nema_split import SERVO_NEMA_SPLIT_NETLIST
from scripts.smoke_test_wiring_layout import NETLIST as I2C_SMOKE_NETLIST


BOARD_SVG = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"

SCENES = [
    ("dc_l298n",            DC_MOTOR_NETLIST),
    ("dc_l293d_module",     DC_MOTOR_L293D_MOD_NETLIST),
    ("stepper_uln2003",     STEPPER_NETLIST),
    ("dc_tb6612",           DC_MOTOR_TB6612_NETLIST),
    ("dc_drv8833",          DC_MOTOR_DRV8833_NETLIST),
    ("nema17_a4988",        NEMA17_A4988_NETLIST),
    ("servo_nema_split",    SERVO_NEMA_SPLIT_NETLIST),
    ("smoke_i2c",           I2C_SMOKE_NETLIST),
]

RAIL_IDS = ("V+_left", "GND_left", "V+_right", "GND_right")
TIESTRIP_LETTERS = ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j")
EPS = 0.5          # tolerance match canvas coord
HOLE_TOL = 3.0     # un fil passe sur un trou si distance < HOLE_TOL


def _all_hole_canvas(scene) -> list[tuple[float, float, str]]:
    """Liste (canvas_x, canvas_y, label) pour TOUS les trous de toutes
    les BBs. `label` = 'rail_RAILID_ROW' ou 'tie_COL_ROW'."""
    out = []
    for bb_idx, bb in enumerate(scene.breadboards):
        tx, ty = scene.breadboard_translates[bb_idx]
        for rail_id in RAIL_IDS:
            for row in range(1, bb.rows + 1):
                cx, cy = bb.hole_position(rail_id, row)
                out.append((cx + tx, cy + ty,
                              f"BB{bb_idx}_{rail_id}_r{row}"))
        for col in TIESTRIP_LETTERS:
            for row in range(1, bb.rows + 1):
                cx, cy = bb.hole_position(col, row)
                out.append((cx + tx, cy + ty,
                              f"BB{bb_idx}_{col}_r{row}"))
    return out


def _rail_endpoints(scene) -> list[tuple[float, float, str, int, int, int]]:
    """Liste de (canvas_x, canvas_y, rail_id, row, bb_idx, rows)."""
    out = []
    for bb_idx, bb in enumerate(scene.breadboards):
        tx, ty = scene.breadboard_translates[bb_idx]
        for rail_id in RAIL_IDS:
            for row in range(1, bb.rows + 1):
                cx, cy = bb.hole_position(rail_id, row)
                out.append((cx + tx, cy + ty, rail_id, row, bb_idx,
                              bb.rows))
    return out


def _match_rail_endpoint(x, y, rail_table):
    for cx, cy, rail_id, row, bb_idx, rows in rail_table:
        if abs(cx - x) < EPS and abs(cy - y) < EPS:
            return (rail_id, row, bb_idx, rows)
    return None


def _is_vertical(p1, p2) -> bool:
    return abs(p1[0] - p2[0]) < EPS


def _is_horizontal(p1, p2) -> bool:
    return abs(p1[1] - p2[1]) < EPS


def _seg_axis(p1, p2) -> str | None:
    """'H', 'V' ou None (degenere/diagonal)."""
    if _is_vertical(p1, p2) and not _is_horizontal(p1, p2):
        return "V"
    if _is_horizontal(p1, p2) and not _is_vertical(p1, p2):
        return "H"
    return None


def _segments(wire) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return [(wire.path[i], wire.path[i + 1])
            for i in range(len(wire.path) - 1)]


# ─── R1 : pas de fil sur trou (hors endpoint) ────────────────────────────
def check_r1(scene, wires) -> list[str]:
    holes = _all_hole_canvas(scene)
    errors = []
    for i, w in enumerate(wires):
        if len(w.path) < 2:
            continue
        endpoints = (w.path[0], w.path[-1])
        for seg_idx, (p1, p2) in enumerate(_segments(w)):
            ax = _seg_axis(p1, p2)
            if ax is None:
                continue
            for hx, hy, label in holes:
                # Skip si le trou est un endpoint legal du wire
                if any(abs(hx - ep[0]) < EPS and abs(hy - ep[1]) < EPS
                          for ep in endpoints):
                    continue
                # H : y constant, x varie. Le trou est sur le segment ssi
                # |hy - p1.y| < tol ET hx entre p1.x et p2.x.
                if ax == "H":
                    if abs(hy - p1[1]) < HOLE_TOL and (
                        min(p1[0], p2[0]) - HOLE_TOL < hx
                        < max(p1[0], p2[0]) + HOLE_TOL):
                        errors.append(
                            f"  wire #{i} (net={w.net}) seg {seg_idx} "
                            f"{p1}->{p2} (H) passe sur trou {label} "
                            f"@({hx:.1f},{hy:.1f})")
                else:   # V
                    if abs(hx - p1[0]) < HOLE_TOL and (
                        min(p1[1], p2[1]) - HOLE_TOL < hy
                        < max(p1[1], p2[1]) + HOLE_TOL):
                        errors.append(
                            f"  wire #{i} (net={w.net}) seg {seg_idx} "
                            f"{p1}->{p2} (V) passe sur trou {label} "
                            f"@({hx:.1f},{hy:.1f})")
    return errors


# ─── R1b : pas de fil sous un body on-BB ────────────────────────────────
def _body_bboxes_on_bb(scene) -> list[tuple[float, float, float, float, str]]:
    """Liste (xmin, ymin, xmax, ymax, ref) des bbox du body de chaque
    composant on-BB (DIP + single-row). Meme calcul que
    occupancy.build_occupancy_grid step 4b."""
    out = []
    for placed in scene.placed_components:
        if placed.breadboard_idx < 0 or not placed.pin_to_hole:
            continue
        bb = scene.breadboards[placed.breadboard_idx]
        bb_tx, bb_ty = scene.breadboard_translates[placed.breadboard_idx]
        xs = []
        ys = []
        for pin_idx, (col_id, row) in placed.pin_to_hole.items():
            try:
                cx, cy = bb.hole_position(col_id, row)
            except (KeyError, ValueError):
                continue
            xs.append(cx + bb_tx)
            ys.append(cy + bb_ty)
        if not xs:
            continue
        if placed.catalog_entry.is_dip:
            cb_min_x = min(xs) - 3.0
            cb_max_x = max(xs) + 3.0
        else:
            # Single-row : body d'un cote du pin col. On reproduit la
            # meme logique que occupancy step 4b (via entry vs pin x).
            from ui.wiring.routing.occupancy import (_endpoint_canvas,
                                                  _component_pin_canvas)
            first_pin_idx = next(iter(placed.pin_to_hole.keys()))
            pin_xy = _component_pin_canvas(scene, placed, first_pin_idx)
            entry_xy = _endpoint_canvas(scene, placed, first_pin_idx)
            if pin_xy is None or entry_xy is None:
                continue
            pin_x = pin_xy[0]
            BODY_W = 28.0
            if entry_xy[0] < pin_x:
                cb_min_x = pin_x + 3.0
                cb_max_x = pin_x + BODY_W
            else:
                cb_min_x = pin_x - BODY_W
                cb_max_x = pin_x - 3.0
        cb_min_y = min(ys) - 28.0
        cb_max_y = max(ys) + 28.0
        out.append((cb_min_x, cb_min_y, cb_max_x, cb_max_y,
                      placed.component_ref))
    return out


def check_r1b(scene, wires) -> list[str]:
    bboxes = _body_bboxes_on_bb(scene)
    errors = []
    for i, w in enumerate(wires):
        if len(w.path) < 2:
            continue
        for seg_idx, (p1, p2) in enumerate(_segments(w)):
            ax = _seg_axis(p1, p2)
            if ax is None:
                continue
            for xmin, ymin, xmax, ymax, ref in bboxes:
                # Test si le segment intersecte le bbox.
                if ax == "H":
                    if (ymin <= p1[1] <= ymax and
                        max(min(p1[0], p2[0]), xmin)
                        <= min(max(p1[0], p2[0]), xmax)):
                        # Segment passe dans bbox.
                        errors.append(
                            f"  wire #{i} (net={w.net}) seg {seg_idx} "
                            f"{p1}->{p2} (H) passe sous body {ref}")
                else:   # V
                    if (xmin <= p1[0] <= xmax and
                        max(min(p1[1], p2[1]), ymin)
                        <= min(max(p1[1], p2[1]), ymax)):
                        errors.append(
                            f"  wire #{i} (net={w.net}) seg {seg_idx} "
                            f"{p1}->{p2} (V) passe sous body {ref}")
    return errors


# ─── R5 : pas de superposition ────────────────────────────────────────────
def _seg_normalized(p1, p2):
    """Retourne (axis, fixed, lo, hi) ou None si degenere."""
    ax = _seg_axis(p1, p2)
    if ax == "H":
        return ("H", p1[1], min(p1[0], p2[0]), max(p1[0], p2[0]))
    if ax == "V":
        return ("V", p1[0], min(p1[1], p2[1]), max(p1[1], p2[1]))
    return None


def check_r5(scene, wires) -> list[str]:
    # Liste de tous segments avec leur wire_idx
    all_segs = []
    for i, w in enumerate(wires):
        for s in _segments(w):
            n = _seg_normalized(*s)
            if n is None:
                continue
            all_segs.append((i, w.net, n))
    errors = []
    seen_pairs: set[tuple[int, int]] = set()
    for j, (i1, net1, n1) in enumerate(all_segs):
        for k in range(j + 1, len(all_segs)):
            i2, net2, n2 = all_segs[k]
            if i1 == i2:
                continue
            if n1[0] != n2[0]:
                continue   # different axes -> peuvent crossing
            # Meme axe : superposition si fixed coord identique ET les
            # plages [lo, hi] se chevauchent sur plus d'un point.
            if abs(n1[1] - n2[1]) > EPS:
                continue
            overlap_lo = max(n1[2], n2[2])
            overlap_hi = min(n1[3], n2[3])
            if overlap_hi - overlap_lo > EPS:
                key = (i1, i2) if i1 < i2 else (i2, i1)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                errors.append(
                    f"  wires #{i1} (net={net1}) et #{i2} (net={net2}) "
                    f"se superposent sur axe {n1[0]} (fixed={n1[1]:.1f}, "
                    f"overlap=[{overlap_lo:.1f}, {overlap_hi:.1f}])")
    return errors


# ─── R7-1 STRICT : row 1/N -> vertical ───────────────────────────────────
def check_r7_1(scene, wires) -> list[str]:
    rail_table = _rail_endpoints(scene)
    errors = []
    for i, w in enumerate(wires):
        if len(w.path) < 2:
            continue
        for endpoint_idx, seg_other_idx, label in (
            (0, 1, "start"),
            (-1, -2, "end"),
        ):
            p_endpoint = w.path[endpoint_idx]
            p_neighbor = w.path[seg_other_idx]
            match = _match_rail_endpoint(p_endpoint[0], p_endpoint[1],
                                            rail_table)
            if match is None:
                continue
            rail_id, row, bb_idx, rows = match
            if row not in (1, rows):
                continue
            if not _is_vertical(p_endpoint, p_neighbor):
                pos = "row1" if row == 1 else "rowN"
                errors.append(
                    f"  wire #{i} (net={w.net}) {label}={p_endpoint} "
                    f"taps {rail_id} {pos}(={row}) of BB{bb_idx} but "
                    f"adjacent segment ends at {p_neighbor} -> not vertical.")
    return errors


# ─── R7-2 STRICT : outer rail mid-row -> horizontal ──────────────────────
# Outer rails : V+_left (col 0 BB) et GND_right (col -1 BB) = rails au
# bord externe. Pour les non-outer (GND_left, V+_right), arrivee
# horizontale est interdite (les wires les croiseraient).
_OUTER_RAILS = {"V+_left", "GND_right"}


def check_r7_2(scene, wires) -> list[str]:
    rail_table = _rail_endpoints(scene)
    errors = []
    for i, w in enumerate(wires):
        if len(w.path) < 2:
            continue
        for endpoint_idx, seg_other_idx, label in (
            (0, 1, "start"),
            (-1, -2, "end"),
        ):
            p_endpoint = w.path[endpoint_idx]
            p_neighbor = w.path[seg_other_idx]
            match = _match_rail_endpoint(p_endpoint[0], p_endpoint[1],
                                            rail_table)
            if match is None:
                continue
            rail_id, row, bb_idx, rows = match
            if row in (1, rows):
                continue   # corner -> R7-1
            if rail_id not in _OUTER_RAILS:
                continue
            if not _is_horizontal(p_endpoint, p_neighbor):
                errors.append(
                    f"  wire #{i} (net={w.net}) {label}={p_endpoint} "
                    f"taps {rail_id} row={row} (mid-row outer rail) of "
                    f"BB{bb_idx} but adjacent segment ends at {p_neighbor}"
                    f" -> not horizontal.")
    return errors


_CHECKERS = [
    ("R1   ",   check_r1),
    ("R1b  ",   check_r1b),
    ("R5   ",   check_r5),
    ("R7-1 ",   check_r7_1),
    ("R7-2 ",   check_r7_2),
]


def main() -> int:
    print("[check_routing_rules]\n")
    total_errors = 0
    for slug, netlist in SCENES:
        print(f"=== {slug} ===")
        scene = place_scene(netlist, BOARD_SVG)
        wires = route_wires(scene, netlist)
        scene_errors = 0
        for name, fn in _CHECKERS:
            errs = fn(scene, wires)
            if errs:
                print(f"  FAIL {name} ({len(errs)}):")
                for e in errs:
                    print(e)
                scene_errors += len(errs)
            else:
                print(f"  OK   {name} ({len(wires)} wires)")
        total_errors += scene_errors

    print()
    if total_errors:
        print(f"FAIL : {total_errors} violations total")
        return 1
    print("OK : all rules pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
