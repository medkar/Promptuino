"""Détection du bundle LED matrix (MAX7219 / LedControl)."""
from __future__ import annotations
import os, sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.markers import extract_netlist  # noqa: E402


def _led_matrix(netlist):
    return [c for c in netlist.components if c.type == "led_matrix"]


def _nets(comp):
    return {p.name: p.net for p in comp.pins}


def test_detect_literals():
    code = (
        "#include <LedControl.h>\n"
        "LedControl lc(12, 11, 10, 1);\n"
        "void setup(){ lc.shutdown(0,false); }\n"
        "void loop(){ lc.setLed(0,0,0,true); }\n"
    )
    nl = extract_netlist(code, board_id="uno")
    mats = _led_matrix(nl)
    assert len(mats) == 1, f"attendu 1 led_matrix, obtenu {len(mats)}"
    nets = _nets(mats[0])
    assert nets.get("DIN") == "D12", nets
    assert nets.get("CLK") == "D11", nets
    assert nets.get("CS") == "D10", nets
    assert nets.get("VCC") == "5V" and nets.get("GND") == "GND", nets
    print("  OK — détection littéraux DIN/CLK/CS")


def test_detect_constants():
    code = (
        "#include <LedControl.h>\n"
        "#define DIN 7\n#define CLK 6\n#define CS 5\n"
        "LedControl lc(DIN, CLK, CS, 1);\n"
        "void setup(){} void loop(){}\n"
    )
    nl = extract_netlist(code, board_id="uno")
    mats = _led_matrix(nl)
    assert len(mats) == 1, f"attendu 1, obtenu {len(mats)}"
    nets = _nets(mats[0])
    assert nets.get("DIN") == "D7", nets
    assert nets.get("CLK") == "D6", nets
    assert nets.get("CS") == "D5", nets
    print("  OK — détection #define + ordre CLK/CS")


def test_no_placeholder_for_ledcontrol():
    """Le header LedControl est réclamé : pas de placeholder 'ledcontrol'."""
    code = ("#include <LedControl.h>\nLedControl lc(12,11,10,1);\n"
            "void setup(){} void loop(){}\n")
    nl = extract_netlist(code, board_id="uno")
    placeholders = [c for c in nl.components
                    if c.attributes.get("unrecognized")]
    assert not placeholders, f"placeholder inattendu: {[c.type for c in placeholders]}"
    print("  OK — aucun placeholder ledcontrol")


def test_catalog_and_label():
    from ui.wiring.layout.component_catalog import CATALOG
    from ui.wiring.instructions import _label
    assert "led_matrix" in CATALOG, "entrée catalogue manquante"
    entry = CATALOG["led_matrix"]
    assert entry.pin_count == 5, entry.pin_count
    labels = set(entry.pin_labels.values())
    assert {"VCC", "GND", "DIN", "CLK", "CS"} == labels, labels
    assert _label("led_matrix", "fr") != "led_matrix", "label FR manquant"
    print("  OK — catalogue 5 broches + label FR")


TESTS = [test_detect_literals, test_detect_constants, test_no_placeholder_for_ledcontrol,
         test_catalog_and_label]


def main():
    passed = failed = 0
    for t in TESTS:
        try:
            t(); print(f"PASS  {t.__name__}"); passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
