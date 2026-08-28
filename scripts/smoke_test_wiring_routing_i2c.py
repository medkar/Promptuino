"""Smoke test v3 multi-I2C : OLED + OLED + LCD partageant A4/A5.

Verifie que `_preroute_i2c_buses` (strategy B = tie-strip bus virtuel
pour >2 devices) genere les bonnes connexions Arduino → bus →
consumers.

Sortie : scripts/wiring_routing_test_output/smoke_i2c_v2.svg + _v3.svg
(cote-a-cote pour comparaison visuelle).
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
from scripts.smoke_test_wiring_layout import NETLIST as SMOKE_NETLIST


BOARD_SVG = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
OUT = ROOT / "scripts" / "wiring_routing_test_output"


def _render(routing_fn, scene, netlist, out_path: Path):
    wires = routing_fn(scene, netlist)
    svg = SceneRenderer(scene, wires).render()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    return wires


def main() -> int:
    print("[smoke_test_wiring_routing_i2c]\n")
    scene = place_scene(SMOKE_NETLIST, BOARD_SVG)
    print(f"  canvas={scene.canvas_size}, {len(scene.placed_components)} composants")
    print(f"  breadboards={len(scene.breadboards)}")

    os.environ.pop(FEATURE_FLAG_ENV, None)
    wv2 = _render(route_wires_v2, scene, SMOKE_NETLIST,
                  OUT / "smoke_i2c_v2.svg")
    print(f"  v2 : {len(wv2)} wires")

    os.environ[FEATURE_FLAG_ENV] = "v3"
    def _v3_partial(scene, netlist):
        return route_wires(scene, netlist, partial=True)
    wv3 = _render(_v3_partial, scene, SMOKE_NETLIST,
                  OUT / "smoke_i2c_v3.svg")
    os.environ.pop(FEATURE_FLAG_ENV, None)
    print(f"  v3 : {len(wv3)} wires")

    from collections import Counter
    c2 = Counter(w.net for w in wv2)
    c3 = Counter(w.net for w in wv3)
    print()
    for n in sorted(set(c2) | set(c3)):
        flag = "  " if c2.get(n, 0) == c3.get(n, 0) else "!="
        print(f"  {flag} {n:15s} v2={c2.get(n, 0):2d} v3={c3.get(n, 0):2d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
