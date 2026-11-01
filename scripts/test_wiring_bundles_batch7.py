"""Détection + retrieval des bundles batch 7 (fingerprint, drv2605, tm1638, pcd8544, ssd1351)."""
from __future__ import annotations
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui.wiring.markers import extract_netlist  # noqa: E402


def _of(nl, t): return [c for c in nl.components if c.type == t]
def _nets(c): return {p.name: p.net for p in c.pins}


def test_rag_retrieval_batch7():
    from ui.rag import retrieve_libs
    probes = [
        ("capteur d'empreinte digitale biometrique", "fingerprint"),
        ("driver de vibration haptique", "drv2605"),
        ("module afficheur 7 segments avec boutons", "tm1638"),
        ("ecran lcd nokia 5110", "pcd8544"),
        ("ecran oled couleur rgb", "ssd1351"),
    ]
    for q, expected in probes:
        ids = [(x.get("id") if isinstance(x, dict) else x) for x in retrieve_libs(q, k=5)]
        assert expected in ids, f"{q!r} -> {ids} (attendu {expected})"
    print("  OK — retrieval batch7 (5 probes)")


def _check_i2c(type_id, code):
    nl = extract_netlist(code, board_id="uno")
    cs = _of(nl, type_id)
    assert len(cs) == 1, f"{type_id}: attendu 1, {len(cs)}"
    n = _nets(cs[0])
    assert n.get("SDA") == "A4" and n.get("SCL") == "A5", (type_id, n)
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", (type_id, n)
    assert not _of(nl, "module_generic"), f"{type_id}: module_generic parasite"
    assert not [c for c in nl.components if c.attributes.get("unrecognized")], \
        f"{type_id}: placeholder parasite"


def test_fingerprint():
    code = ("#include <Adafruit_Fingerprint.h>\n#include <SoftwareSerial.h>\n"
            "SoftwareSerial mySerial(2, 3);\n"
            "Adafruit_Fingerprint finger = Adafruit_Fingerprint(&mySerial);\n"
            "void setup(){ finger.begin(57600); } void loop(){}\n")
    nl = extract_netlist(code, board_id="uno")
    cs = _of(nl, "fingerprint")
    assert len(cs) == 1, [c.type for c in nl.components]
    assert not _of(nl, "uart_module"), "uart_module doublon"
    n = _nets(cs[0])
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    assert {"RX", "TX"} <= set(n.keys()), n
    print("  OK — fingerprint (pas de uart_module)")


def test_drv2605():
    _check_i2c("drv2605", "#include <Adafruit_DRV2605.h>\nAdafruit_DRV2605 drv;\n"
               "void setup(){ drv.begin(); } void loop(){}\n"); print("  OK — drv2605")


def test_tm1638():
    code = ("#include <TM1638plus.h>\nTM1638plus tm(7, 9, 8);\n"
            "void setup(){ tm.displayBegin(); } void loop(){}\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "tm1638")[0])
    assert n.get("STB") == "D7" and n.get("CLK") == "D9" and n.get("DIO") == "D8", n
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    print("  OK — tm1638 STB/CLK/DIO")


def test_pcd8544():
    code = ("#include <Adafruit_PCD8544.h>\n"
            "Adafruit_PCD8544 display = Adafruit_PCD8544(7, 6, 5, 4, 3);\n"
            "void setup(){ display.begin(); } void loop(){}\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "pcd8544")[0])
    assert n.get("CLK") == "D7" and n.get("DIN") == "D6" and n.get("DC") == "D5", n
    assert n.get("CS") == "D4" and n.get("RST") == "D3", n
    assert n.get("VCC") == "3V3" and n.get("GND") == "GND", n
    print("  OK — pcd8544 (Nokia 5110, 3V3)")


def test_ssd1351():
    code = ("#include <Adafruit_SSD1351.h>\n"
            "Adafruit_SSD1351 tft = Adafruit_SSD1351(128, 128, &SPI, 10, 9, 8);\n"
            "void setup(){ tft.begin(); } void loop(){}\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "ssd1351")[0])
    assert n.get("CS") == "D10" and n.get("DC") == "D9" and n.get("RST") == "D8", n
    assert n.get("SCK") == "D13" and n.get("MOSI") == "D11", n
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    print("  OK — ssd1351 CS/DC/RST + SPI")


TESTS = [
    test_rag_retrieval_batch7,
    test_fingerprint, test_drv2605, test_tm1638,
    test_pcd8544, test_ssd1351,
]


def main():
    passed = failed = 0
    for t in TESTS:
        try:
            t(); print(f"PASS  {t.__name__}"); passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.stdout.flush(); os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
