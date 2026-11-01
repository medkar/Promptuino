"""Smoke test : 3 scenes minimales pour verifier les paires (main, R) :
  - pair_button : Btn + R pullup 10k
  - pair_dht    : DHT22 + R pullup 4.7k (DATA)
  - pair_buzzer : Buzzer + R serie 100 (NET interne)

Chaque scene contient le main, sa R inferee, plus 1-2 composants neutres pour
visualiser le contexte (LED + sa R serie pour reference). Sortie dans
scripts/wiring_layout_test_output/.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.layout.layout import place_scene
from ui.wiring.layout.routing import route_wires
from ui.wiring.layout.renderer import SceneRenderer

BOARD = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
OUTDIR = ROOT / "scripts" / "wiring_layout_test_output"


# ── Scene 1 : Button + R pullup ────────────────────────────────────────────
NETLIST_BUTTON = [
    {"ref": "BTN1", "type": "button",
     "pins": [{"name": "A", "net": "D2"}, {"name": "B", "net": "GND"}],
     "attributes": {"pull": "external"}},
    {"ref": "RP1",  "type": "resistor",
     "pins": [{"name": "A", "net": "5V"}, {"name": "B", "net": "D2"}],
     "attributes": {"value": "10k", "role": "pullup"}},
]

# ── Scene 2 : DHT22 + R pullup sur DATA ────────────────────────────────────
NETLIST_DHT = [
    {"ref": "T1", "type": "dht22",
     "pins": [{"name": "VCC", "net": "5V"},
              {"name": "DATA", "net": "D7"},
              {"name": "GND", "net": "GND"}]},
    {"ref": "RP2", "type": "resistor",
     "pins": [{"name": "A", "net": "5V"}, {"name": "B", "net": "D7"}],
     "attributes": {"value": "4.7k", "role": "pullup"}},
]

# ── Scene 3 : Buzzer + R serie ────────────────────────────────────────────
NETLIST_BUZZER = [
    {"ref": "BZ1", "type": "buzzer",
     "pins": [{"name": "+", "net": "NET_A"}, {"name": "-", "net": "GND"}]},
    {"ref": "RS2", "type": "resistor",
     "pins": [{"name": "A", "net": "D10"}, {"name": "B", "net": "NET_A"}],
     "attributes": {"value": "100", "role": "series"}},
]


def _render(name: str, netlist: list[dict]) -> None:
    scene = place_scene(netlist, BOARD)
    wires = route_wires(scene, netlist)
    svg = SceneRenderer(scene, wires).render()
    out = OUTDIR / f"pair_{name}.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"  pair_{name:7s} : {len(scene.placed_components)} composants, "
          f"{len(wires)} fils -> {out.relative_to(ROOT)}")
    for pc in scene.placed_components:
        cols = sorted({c for c, _ in pc.pin_to_hole.values()})
        rows = sorted({r for _, r in pc.pin_to_hole.values()})
        prop = " (propagate)" if pc.propagate_color_through else ""
        print(f"    BB{pc.breadboard_idx} {pc.component_ref:5s} "
              f"({pc.catalog_entry.name:5s}) cols={cols} rows={rows}{prop}")


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    _render("button", NETLIST_BUTTON)
    print()
    _render("dht",    NETLIST_DHT)
    print()
    _render("buzzer", NETLIST_BUZZER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
