"""Smoke test wiring v2 : genere une scene SVG full-load (12 composants, 6 par BB).

Exerce :
- placement avec split top/bottom (3+3 par BB)
- routage avec corridors top/bottom selon position des composants
- rendu via SceneRenderer + ComponentSVGLoader refactore (geometrie mirroirée
  via inner-group, textes en frame non-scalee).

Usage : `python scripts/smoke_test_wiring_layout.py`
Sortie : scripts/wiring_layout_test_output/scene_v2_smoke.svg
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Stub ui package pour eviter l'import lourd de ui/__init__.py (numpy, etc.)
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.layout.layout import place_scene
from ui.wiring.layout.routing import route_wires
from ui.wiring.layout.renderer import SceneRenderer


# ─── Netlist 12 composants ────────────────────────────────────────────────
# BB[0] (cote gauche, mirror) : 6 premiers composants — LED, R, BTN, BUZ, POT, MOD
# BB[1] (cote droit Arduino) : 6 suivants — dont 3 I2C (LCD + 2 OLED) pour
# tester la strategy B (tie-strip rail) du routage I2C.
NETLIST = [
    # BB[0] (gauche) — D1+RS1 forme une paire LED+R serie (pour tester
    # le placement deporte LED col 'c' + R horizontale entre cols 'd' et 'g').
    {"ref": "D1",    "type": "led",       "pins": [{"name": "A", "net": "NET_A"}, {"name": "K", "net": "GND"}]},
    {"ref": "RS1",   "type": "resistor",  "pins": [{"name": "A", "net": "D13"}, {"name": "B", "net": "NET_A"}],
     "attributes": {"value": "220", "role": "series"}},
    {"ref": "BTN1",  "type": "button",    "pins": [{"name": "A", "net": "D11"}, {"name": "B", "net": "GND"}],
     "attributes": {"pull": "external"}},
    {"ref": "RP1",   "type": "resistor",  "pins": [{"name": "A", "net": "5V"}, {"name": "B", "net": "D11"}],
     "attributes": {"value": "10k", "role": "pullup"}},
    {"ref": "BZ1",   "type": "buzzer",    "pins": [{"name": "+", "net": "D10"}, {"name": "-", "net": "GND"}]},
    {"ref": "POT1",  "type": "potentiometer", "pins": [{"name": "A", "net": "5V"}, {"name": "W", "net": "A0"}, {"name": "B", "net": "GND"}]},
    {"ref": "MOD1",  "type": "module_generic", "pins": [{"name": "1", "net": "D9"}, {"name": "2", "net": "GND"}]},
    # BB[1] (droite) — 3 composants I2C (LCD + 2 OLED) sur les meme nets A4/A5
    {"ref": "SRV1",  "type": "servo",     "pins": [{"name": "VCC", "net": "5V"}, {"name": "GND", "net": "GND"}, {"name": "SIG", "net": "D8"}]},
    {"ref": "DH1",   "type": "dht11",     "pins": [{"name": "VCC", "net": "5V"}, {"name": "DATA", "net": "D7"}, {"name": "GND", "net": "GND"}]},
    {"ref": "T1",    "type": "dht22",     "pins": [{"name": "VCC", "net": "5V"}, {"name": "DATA", "net": "D6"}, {"name": "GND", "net": "GND"}]},
    {"ref": "OLED2", "type": "oled_ssd1306", "pins": [{"name": "GND", "net": "GND"}, {"name": "VCC", "net": "5V"}, {"name": "SCL", "net": "A5"}, {"name": "SDA", "net": "A4"}]},
    {"ref": "LCD1",  "type": "lcd_i2c",   "pins": [{"name": "GND", "net": "GND"}, {"name": "VCC", "net": "5V"}, {"name": "SDA", "net": "A4"}, {"name": "SCL", "net": "A5"}]},
    {"ref": "OLED1", "type": "oled_ssd1306", "pins": [{"name": "GND", "net": "GND"}, {"name": "VCC", "net": "5V"}, {"name": "SCL", "net": "A5"}, {"name": "SDA", "net": "A4"}]},
]


def make_battery_variant(netlist: list[dict]) -> list[dict]:
    """Variante alim externe pour les servos : remplace leur net VCC ('5V')
    par 'BAT_5V' et ajoute un composant battery_external avec + sur 'BAT_5V'
    et - sur 'GND' (commun avec Arduino)."""
    new_netlist: list[dict] = []
    has_servo = False
    for c in netlist:
        if c["type"] == "servo":
            new_pins = []
            for p in c.get("pins", []):
                if p["name"] == "VCC":
                    new_pins.append({**p, "net": "BAT_5V"})
                    has_servo = True
                else:
                    new_pins.append(p)
            new_netlist.append({**c, "pins": new_pins})
        else:
            new_netlist.append(c)
    if has_servo:
        new_netlist.append({
            "ref": "BAT1", "type": "battery_external",
            "pins": [
                {"name": "+", "net": "BAT_5V"},
                {"name": "-", "net": "GND"},
            ],
        })
    return new_netlist


def _render(label: str, netlist: list[dict], out_path: "Path") -> None:
    board_svg = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
    scene = place_scene(netlist, board_svg)
    wires = route_wires(scene, netlist)
    svg = SceneRenderer(scene, wires).render()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    print(f"  {label:18s}: canvas {scene.canvas_size}, "
          f"{len(scene.placed_components)} composants, {len(wires)} fils "
          f"-> {out_path.relative_to(ROOT)}")


def main() -> int:
    OUT = ROOT / "scripts" / "wiring_layout_test_output"
    print("[smoke v2 — 2 schemas alim servo]\n")
    _render("alim Arduino",  NETLIST,                          OUT / "scene_v2_smoke.svg")
    _render("alim batterie", make_battery_variant(NETLIST),    OUT / "scene_v2_smoke_battery.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
