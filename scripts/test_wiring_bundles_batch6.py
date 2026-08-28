"""Détection + retrieval des bundles batch 6 (5 capteurs I2C-fixe + nRF24L01 SPI)."""
from __future__ import annotations
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui.wiring.markers import extract_netlist  # noqa: E402


def _of(nl, t): return [c for c in nl.components if c.type == t]
def _nets(c): return {p.name: p.net for p in c.pins}


def test_rag_retrieval_batch6():
    from ui.rag import retrieve_libs
    probes = [
        ("module radio 2.4 ghz sans fil", "nrf24l01"),
        ("centrale inertielle 9 axes orientation absolue", "bno055"),
        ("amplificateur de thermocouple i2c", "mcp9600"),
        ("jauge de batterie lipo niveau de charge", "max17043"),
        ("camera thermique 8x8 infrarouge", "amg8833"),
        ("capteur de particules fines pm2.5", "pm25"),
    ]
    for q, expected in probes:
        ids = [(x.get("id") if isinstance(x, dict) else x) for x in retrieve_libs(q, k=5)]
        assert expected in ids, f"{q!r} -> {ids} (attendu {expected})"
    print("  OK — retrieval batch6 (6 probes)")


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


def test_bno055():
    _check_i2c("bno055", "#include <Adafruit_BNO055.h>\n"
               "Adafruit_BNO055 bno = Adafruit_BNO055(55, 0x28);\n"
               "void setup(){ bno.begin(); } void loop(){}\n"); print("  OK — bno055")


def test_mcp9600():
    _check_i2c("mcp9600", "#include <Adafruit_MCP9600.h>\nAdafruit_MCP9600 mcp;\n"
               "void setup(){ mcp.begin(0x67); } void loop(){}\n"); print("  OK — mcp9600")


def test_max17043():
    _check_i2c("max17043", "#include <Adafruit_MAX1704X.h>\nAdafruit_MAX17048 maxlipo;\n"
               "void setup(){ maxlipo.begin(); } void loop(){}\n"); print("  OK — max17043")


def test_amg8833():
    _check_i2c("amg8833", "#include <Adafruit_AMG88xx.h>\nAdafruit_AMG88xx amg;\n"
               "void setup(){ amg.begin(); } void loop(){}\n"); print("  OK — amg8833")


def test_pm25():
    _check_i2c("pm25", "#include <Adafruit_PM25AQI.h>\nAdafruit_PM25AQI aqi = Adafruit_PM25AQI();\n"
               "void setup(){ aqi.begin_I2C(); } void loop(){}\n"); print("  OK — pm25")


def test_nrf24l01():
    code = ("#include <RF24.h>\nRF24 radio(7, 8);\n"
            "void setup(){ radio.begin(); } void loop(){}\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "nrf24l01")[0])
    assert n.get("CE") == "D7" and n.get("CSN") == "D8", n
    assert n.get("SCK") == "D13" and n.get("MOSI") == "D11" and n.get("MISO") == "D12", n
    assert n.get("VCC") == "3V3" and n.get("GND") == "GND", n
    print("  OK — nrf24l01 (CE/CSN + SPI matériel + 3V3)")


TESTS = [
    test_rag_retrieval_batch6,
    test_bno055, test_mcp9600, test_max17043,
    test_amg8833, test_pm25, test_nrf24l01,
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
