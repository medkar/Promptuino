"""Smoke test Phase 4 : off-BB complexes (drivers, motors, battery).

Critere de succes (cf .planning/wiring_routing_design.md) :
  v3 sur scene complexe (smoke_test_wiring_layout_motors.py) sans pire que v2 partout.

Rejoue les 6 scenes motors et produit cote-a-cote pour comparaison visuelle :
  scripts/wiring_routing_test_output/phase4_<scene>_v2.svg
  scripts/wiring_routing_test_output/phase4_<scene>_v3.svg

Ne fait PAS un assert byte-exact (v3 ne cherche pas a reproduire v2). Imprime
juste les compteurs de fils par net pour repere rapide. La validation finale
reste visuelle.
"""
from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.layout.layout import place_scene
from ui.wiring.layout.routing import route_wires as route_wires_v2
from ui.wiring.layout.renderer import SceneRenderer
from ui.wiring.routing import route_wires, FEATURE_FLAG_ENV
from ui.wiring.routing.manual_zones_json import DEFAULT_JSON_PATH, FALLBACK_JSON_PATH
import json as _json

# Reutilise les netlists du smoke v2 motors.
from scripts.smoke_test_wiring_layout_motors import (
    DC_MOTOR_NETLIST,
    DC_MOTOR_L293D_MOD_NETLIST,
    STEPPER_NETLIST,
    DC_MOTOR_TB6612_NETLIST,
    DC_MOTOR_DRV8833_NETLIST,
    NEMA17_A4988_NETLIST,
)


BOARD_SVG = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
OUT = ROOT / "scripts" / "wiring_routing_test_output"


SCENES = [
    ("dc_l298n",        "DC + L298N",         DC_MOTOR_NETLIST),
    ("dc_l293d_module", "DC + L293D module",  DC_MOTOR_L293D_MOD_NETLIST),
    ("stepper_uln2003", "Stepper + ULN2003",  STEPPER_NETLIST),
    ("dc_tb6612",       "DC + TB6612FNG",     DC_MOTOR_TB6612_NETLIST),
    ("dc_drv8833",      "DC + DRV8833",       DC_MOTOR_DRV8833_NETLIST),
    ("nema17_a4988",    "NEMA17 + A4988",     NEMA17_A4988_NETLIST),
]


_ZONE_FILL = {
    "forbid": "rgba(214, 39, 40, 0.30)",
    "cost":   "rgba(240, 192, 0, 0.22)",
    "allow":  "rgba(40, 167, 69, 0.25)",
}


def _zones_overlay(scene) -> str:
    """Genere un <g> SVG superposant les cellules manual_zones sur la
    scene. Renvoie '' si aucun fichier de zones trouve. Coords coherentes
    avec apply_manual_zones_json (bb_translate + offset + col*cs)."""
    json_path = DEFAULT_JSON_PATH if DEFAULT_JSON_PATH.exists() else FALLBACK_JSON_PATH
    if not json_path.exists() or not scene.breadboard_translates:
        return ""
    data = _json.loads(json_path.read_text(encoding="utf-8"))
    cs_e = float(data.get("cell_size", 7))
    anchor = data.get("bb_anchor") or {}
    ax = float(anchor.get("x", 30.0))
    ay = float(anchor.get("y", 30.0))
    ox = (ax - cs_e / 2.0) % cs_e
    oy = (ay - cs_e / 2.0) % cs_e
    tx, ty = scene.breadboard_translates[0]
    rects: list[str] = []
    for color, fill in _ZONE_FILL.items():
        for entry in data.get("cells", {}).get(color, []):
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            col, row = int(entry[0]), int(entry[1])
            x = tx + ox + col * cs_e
            y = ty + oy + row * cs_e
            rects.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{cs_e}" '
                f'height="{cs_e}" fill="{fill}" stroke="none"/>'
            )
    return (f'<g id="manual-zones-overlay" data-source="{json_path.name}">'
            f'{"".join(rects)}</g>')


def _inject_overlay(svg: str, overlay: str) -> str:
    """Insere l'overlay juste avant </svg> pour qu'il soit AU-DESSUS de
    tout le reste (BB, composants, wires)."""
    if not overlay:
        return svg
    return svg.replace("</svg>", overlay + "</svg>")


def _render(routing_fn, scene, netlist, out_path: Path,
             with_zones_overlay: bool = False):
    t0 = time.perf_counter()
    wires = routing_fn(scene, netlist)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    svg = SceneRenderer(scene, wires).render()
    if with_zones_overlay:
        svg = _inject_overlay(svg, _zones_overlay(scene))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    return wires, elapsed_ms


def _counters(wires) -> dict[str, int]:
    by_net: dict[str, int] = {}
    for w in wires:
        by_net[w.net] = by_net.get(w.net, 0) + 1
    return by_net


def main() -> int:
    print("[smoke_test_wiring_routing_phase4 — off-BB complexes vs v2]\n")
    summary: list[tuple[str, int, int, float, float]] = []
    for slug, label, netlist in SCENES:
        print(f"=== {label} ===")
        scene = place_scene(netlist, BOARD_SVG)
        print(f"  canvas={scene.canvas_size}, {len(scene.placed_components)} composants")

        # v2 (flag desactive)
        os.environ.pop(FEATURE_FLAG_ENV, None)
        wires_v2, ms_v2 = _render(
            route_wires_v2, scene, netlist,
            OUT / f"phase4_{slug}_v2.svg",
        )

        # v3 (flag actif). partial=True : skip wires impossibles au lieu
        # de fallback global, pour visualiser le travail en cours.
        os.environ[FEATURE_FLAG_ENV] = "v3"
        def _v3_partial(scene, netlist):
            return route_wires(scene, netlist, partial=True)
        wires_v3, ms_v3 = _render(
            _v3_partial, scene, netlist,
            OUT / f"phase4_{slug}_v3.svg",
            with_zones_overlay=True,
        )
        os.environ.pop(FEATURE_FLAG_ENV, None)

        c_v2 = _counters(wires_v2)
        c_v3 = _counters(wires_v3)
        all_nets = sorted(set(c_v2.keys()) | set(c_v3.keys()))
        print(f"  v2 : {len(wires_v2):2d} wires ({ms_v2:5.1f} ms)"
              f"   v3 : {len(wires_v3):2d} wires ({ms_v3:5.1f} ms)")
        diffs = []
        for net in all_nets:
            n2 = c_v2.get(net, 0)
            n3 = c_v3.get(net, 0)
            flag = "  " if n2 == n3 else "!="
            line = f"    {flag} {net:12s} v2={n2:2d}  v3={n3:2d}"
            print(line)
            if n2 != n3:
                diffs.append((net, n2, n3))
        if not diffs:
            print("    -> v3 et v2 ont le meme nb de fils par net")
        print()
        summary.append((label, len(wires_v2), len(wires_v3), ms_v2, ms_v3))

    print("=== Resume ===")
    for label, n2, n3, ms2, ms3 in summary:
        status = "ok " if n2 == n3 else "DIFF"
        print(f"  {status} {label:24s} v2={n2:2d}  v3={n3:2d}"
              f"   ({ms2:5.1f} ms vs {ms3:5.1f} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
