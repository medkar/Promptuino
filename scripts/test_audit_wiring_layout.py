"""Audit 2026-11-06 -- zone wiring/layout : plage de tension, paire (main, R),
bus I2C selon la carte, plage None.

Run: python scripts/test_audit_wiring_layout.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.layout import layout as L  # noqa: E402
from ui.wiring.layout.renderer import SceneRenderer  # noqa: E402


def _stepper_netlist(driver_type: str, vpin: str) -> list[dict]:
    return [
        {"ref": "BAT1", "type": "battery_external",
         "pins": [{"name": "+", "net": "BAT_5V"}, {"name": "-", "net": "GND"}]},
        {"ref": "U1", "type": driver_type,
         "pins": [{"name": vpin, "net": "BAT_5V"},
                  {"name": "STEP", "net": "D2"},
                  {"name": "1A", "net": "NET_M1"}]},
        {"ref": "M1", "type": "nema17",
         "pins": [{"name": "A+", "net": "NET_M1"}]},
    ]


def test_every_stepdir_driver_gets_its_battery_range():
    """Constat 1 : DRV8825 / TMC2209 / STSPIN220 etaient inconnus de
    DRIVER_TYPES (et VMOTOR de BATTERY_POWER_PINS) : plage None, donc la
    batterie affichait la plage d'un servo."""
    for dtype, vpin in (("a4988", "VMOT"), ("drv8825", "VMOT"),
                        ("tmc2209", "VMOTOR"), ("stspin220", "VMOTOR")):
        rng = L.compute_battery_voltage_range(
            _stepper_netlist(dtype, vpin), "BAT1")
        assert rng == (8.0, 35.0), (dtype, rng)


def test_the_resistor_row_follows_the_catalog_not_the_netlist_order():
    """Constat 2 : markers emet le DS18B20 en [VCC, DATA, GND], le catalogue
    le range [VCC, GND, DATA]. La pull-up doit tomber sur la rangee de DATA."""
    from ui.wiring.layout.component_catalog import lookup
    entry = lookup("ds18b20")
    labels = entry.pin_labels
    data_idx = next(i for i, n in labels.items() if n == "DATA")
    typed = [("U1", "ds18b20", entry)]
    pins = {
        "U1": [{"name": "VCC", "net": "5V"}, {"name": "DATA", "net": "D2"},
               {"name": "GND", "net": "GND"}],
        "R1": [{"name": "A", "net": "5V"}, {"name": "B", "net": "D2"}],
    }
    typed.append(("R1", "resistor", lookup("resistor")))
    _m2r, _r2m, idx = L._identify_pairs(typed, pins)
    assert idx.get("U1") == data_idx, (idx, labels)


def test_unknown_pin_name_falls_back_to_netlist_position():
    """Le repli (nom absent du catalogue) garde l'ancien comportement."""
    from ui.wiring.layout.component_catalog import lookup
    typed = [("B1", "button", lookup("button")),
             ("R1", "resistor", lookup("resistor"))]
    pins = {
        "B1": [{"name": "ZZ", "net": "D2"}, {"name": "YY", "net": "GND"}],
        "R1": [{"name": "A", "net": "5V"}, {"name": "B", "net": "D2"}],
    }
    _m2r, _r2m, idx = L._identify_pairs(typed, pins)
    assert idx.get("B1") == 1, idx


def test_an_empty_range_does_not_leave_the_servo_label():
    """Constat 4 : plage None (charges incompatibles) -> le « 4.8 – 6 V »
    code en dur du SVG restait affiche comme une recommandation."""
    from ui.wiring.layout.layout import place_scene
    from ui.wiring.layout.routing import route_wires
    from ui.wiring.layout.renderer import SceneRenderer
    board = (Path(__file__).resolve().parents[1] / "assets" / "wiring"
             / "boards" / "arduino" / "uno_r3.svg")
    nl = _stepper_netlist("a4988", "VMOT")
    nl.append({"ref": "S1", "type": "servo",
               "pins": [{"name": "VCC", "net": "BAT_5V"},
                        {"name": "SIG", "net": "D9"},
                        {"name": "GND", "net": "GND"}]})
    assert L.compute_battery_voltage_range(nl, "BAT1") is None
    scene = place_scene(nl, board)
    svg = SceneRenderer(scene, route_wires(scene, nl)).render()
    assert "4.8 – 6 V" not in svg, "plage de servo affichee a tort"
    assert "?" in svg


def test_a4_a5_are_the_i2c_bus_only_on_boards_where_they_are():
    """Constat 3 : A4/A5 recopies sur toutes les cartes ; sur Mega (D20/D21) et
    Leonardo (D2/D3) le 2e module etait cable sur une entree analogique."""
    from ui.wiring.layout.svg_board_loader import BoardSVGLoader
    from ui.wiring.layout import routing as old
    from ui.wiring.routing import router as new
    root = Path(__file__).resolve().parents[1] / "assets" / "wiring" / "boards" / "arduino"
    for mod in (old, new):
        for stem, want in (("uno_r3", ["SDA", "A4"]), ("uno_r4", ["SDA", "A4"]),
                           ("mega_2560", ["SDA", "D20"]), ("leonardo", ["SDA", "D2"])):
            ld = BoardSVGLoader(root / f"{stem}.svg")
            got = mod._i2c_physical_pins(ld, "SDA")
            assert got == want, (mod.__name__, stem, got)
        ld = BoardSVGLoader(root / "mega_2560.svg")
        assert mod._i2c_physical_pins(ld, "SCL") == ["SCL", "D21"]


TESTS = [
    test_a4_a5_are_the_i2c_bus_only_on_boards_where_they_are,
    test_an_empty_range_does_not_leave_the_servo_label,
    test_every_stepdir_driver_gets_its_battery_range,
    test_the_resistor_row_follows_the_catalog_not_the_netlist_order,
    test_unknown_pin_name_falls_back_to_netlist_position,
]


def main() -> None:
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc!r}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
