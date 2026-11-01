"""Smoke test Phase 2 visuel : compare v2 vs v3 sur scene LED simple.

Produit 2 SVG cote a cote dans scripts/wiring_routing_test_output/ :
  - led_v2.svg : routeur v2 actuel
  - led_v3.svg : routeur v3 (force via PROMPTUINO_ROUTER=v3)

A inspecter manuellement pour valider que v3 produit un visuel raisonnable.
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
from ui.wiring.layout.routing import route_wires as route_wires_v2
from ui.wiring.layout.renderer import SceneRenderer
from ui.wiring.routing import route_wires, FEATURE_FLAG_ENV


BOARD_SVG = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"

NETLIST_LED = [
    {"ref": "D1", "type": "led",
     "pins": [{"name": "A", "net": "NET_LR"},
              {"name": "K", "net": "GND"}]},
    {"ref": "R1", "type": "resistor",
     "pins": [{"name": "A", "net": "D13"},
              {"name": "B", "net": "NET_LR"}]},
]


def render_with(routing_fn, label, scene, netlist, out_path):
    wires = routing_fn(scene, netlist)
    svg = SceneRenderer(scene, wires).render()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    print(f"  {label}: {len(wires)} wires -> {out_path.relative_to(ROOT)}")
    return wires


def main() -> int:
    out_dir = ROOT / "scripts" / "wiring_routing_test_output"
    print("[smoke_test_wiring_routing_led] LED + R Arduino\n")

    scene = place_scene(NETLIST_LED, BOARD_SVG)
    print(f"  canvas={scene.canvas_size}, placed={len(scene.placed_components)} comp\n")

    # v2
    os.environ.pop(FEATURE_FLAG_ENV, None)
    wires_v2 = render_with(route_wires_v2, "v2 routeur direct ", scene, NETLIST_LED,
                            out_dir / "led_v2.svg")

    # v3 (force flag)
    os.environ[FEATURE_FLAG_ENV] = "v3"
    wires_v3 = render_with(route_wires, "v3 routeur grille ", scene, NETLIST_LED,
                            out_dir / "led_v3.svg")
    os.environ.pop(FEATURE_FLAG_ENV, None)

    print()
    print("  --- diff resume ---")
    print(f"  v2: {len(wires_v2)} wires, total path points = "
          f"{sum(len(w.path) for w in wires_v2)}")
    print(f"  v3: {len(wires_v3)} wires, total path points = "
          f"{sum(len(w.path) for w in wires_v3)}")
    for wv2, wv3 in zip(sorted(wires_v2, key=lambda w: w.net),
                          sorted(wires_v3, key=lambda w: w.net)):
        if wv2.net == wv3.net:
            print(f"    {wv2.net:10s} : v2 {len(wv2.path):2d} pts  vs  "
                  f"v3 {len(wv3.path):2d} pts")

    # ─── Verification render_netlist_with_meta (Task 3 du plan Niveau 1) ─
    from ui.wiring.layout.pipeline import render_netlist_with_meta
    from ui.wiring.netlist import Netlist as _Netlist, Component as _Component, Pin as _Pin

    nl_v1 = _Netlist(
        board_id="arduino_uno_r3",
        components=[
            _Component(ref="D1", type="led",
                       pins=[_Pin("A", "D13"), _Pin("K", "GND")]),
        ],
    )
    svg, md, scene, wires = render_netlist_with_meta(
        nl_v1, "arduino_uno_r3", theme="light", mode="simple", lang="fr"
    )
    assert svg, "render_netlist_with_meta : svg empty"
    assert scene is not None, "render_netlist_with_meta : scene None"
    assert isinstance(wires, list), "render_netlist_with_meta : wires not a list"
    print(f"  render_netlist_with_meta OK : scene={len(scene.placed_components)} comp, wires={len(wires)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
