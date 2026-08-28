"""Détection + retrieval des bundles batch 5 (8 capteurs I2C-fixe)."""
from __future__ import annotations
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui.wiring.markers import extract_netlist  # noqa: E402


def _of(nl, t): return [c for c in nl.components if c.type == t]
def _nets(c): return {p.name: p.net for p in c.pins}


def test_rag_retrieval_batch5():
    from ui.rag import retrieve_libs
    probes = [
        ("capteur de temperature de precision", "mcp9808"),
        ("capteur de temperature et humidite si7021", "si7021"),
        ("accelerometre 3 axes", "adxl345"),
        ("magnetometre boussole numerique", "hmc5883l"),
        ("convertisseur numerique analogique dac", "mcp4725"),
        ("mesure de courant et de tension", "ina260"),
        ("capteur d'angle magnetique rotatif", "as5600"),
        ("capteur uv indice ultraviolet", "veml6075"),
    ]
    for q, expected in probes:
        ids = [(x.get("id") if isinstance(x, dict) else x) for x in retrieve_libs(q, k=5)]
        assert expected in ids, f"{q!r} -> {ids} (attendu {expected})"
    print("  OK — retrieval batch5 (8 probes)")


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


def test_mcp9808():
    _check_i2c("mcp9808", "#include <Adafruit_MCP9808.h>\nAdafruit_MCP9808 t = Adafruit_MCP9808();\n"
               "void setup(){ t.begin(0x18); } void loop(){}\n"); print("  OK — mcp9808")


def test_si7021():
    _check_i2c("si7021", "#include <Adafruit_Si7021.h>\nAdafruit_Si7021 s = Adafruit_Si7021();\n"
               "void setup(){ s.begin(); } void loop(){}\n"); print("  OK — si7021")


def test_adxl345():
    _check_i2c("adxl345", "#include <Adafruit_ADXL345_U.h>\n"
               "Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);\n"
               "void setup(){ accel.begin(); } void loop(){}\n"); print("  OK — adxl345")


def test_hmc5883l():
    _check_i2c("hmc5883l", "#include <Adafruit_HMC5883_U.h>\n"
               "Adafruit_HMC5883_Unified mag = Adafruit_HMC5883_Unified(12345);\n"
               "void setup(){ mag.begin(); } void loop(){}\n"); print("  OK — hmc5883l")


def test_mcp4725():
    _check_i2c("mcp4725", "#include <Adafruit_MCP4725.h>\nAdafruit_MCP4725 dac;\n"
               "void setup(){ dac.begin(0x62); } void loop(){}\n"); print("  OK — mcp4725")


def test_ina260():
    _check_i2c("ina260", "#include <Adafruit_INA260.h>\nAdafruit_INA260 ina = Adafruit_INA260();\n"
               "void setup(){ ina.begin(); } void loop(){}\n"); print("  OK — ina260")


def test_as5600():
    _check_i2c("as5600", "#include <AS5600.h>\nAS5600 enc;\n"
               "void setup(){ enc.begin(); } void loop(){}\n"); print("  OK — as5600")


def test_veml6075():
    _check_i2c("veml6075", "#include <Adafruit_VEML6075.h>\nAdafruit_VEML6075 uv = Adafruit_VEML6075();\n"
               "void setup(){ uv.begin(); } void loop(){}\n"); print("  OK — veml6075")


TESTS = [
    test_rag_retrieval_batch5,
    test_mcp9808, test_si7021, test_adxl345, test_hmc5883l,
    test_mcp4725, test_ina260, test_as5600, test_veml6075,
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
