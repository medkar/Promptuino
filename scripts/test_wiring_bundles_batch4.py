"""Detection + retrieval for batch 4 bundles."""
from __future__ import annotations
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui.wiring.markers import extract_netlist  # noqa: E402


def _of(nl, t): return [c for c in nl.components if c.type == t]
def _nets(c): return {p.name: p.net for p in c.pins}


def test_rag_retrieval_batch4():
    """Every batch4 bundle is returned by retrieval for a descriptive prompt (FR)."""
    from ui.rag import retrieve_libs
    probes = [
        ("capteur de pression barometrique", "bmp280"),
        ("capteur de geste de la main", "apds9960"),
        ("thermometre infrarouge sans contact", "mlx90614"),
        ("capteur de qualite de l'air cov", "sgp30"),
        ("capteur de co2", "scd30"),
        ("lecteur nfc rfid", "pn532"),
        ("expandeur d'entrees sorties i2c", "pcf8574"),
        ("expandeur 16 broches i2c", "mcp23017"),
        ("thermocouple type k", "max6675"),
    ]
    for q, expected in probes:
        r = retrieve_libs(q, k=5)
        ids = [(x.get("id") if isinstance(x, dict) else x) for x in r]
        assert expected in ids, f"{q!r} -> {ids} (attendu {expected})"
    print("  OK — retrieval batch4 (9 probes)")


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


def test_bmp280():
    _check_i2c("bmp280", "#include <Adafruit_BMP280.h>\nAdafruit_BMP280 bmp;\n"
               "void setup(){ bmp.begin(0x76); } void loop(){}\n")
    print("  OK — bmp280")


def test_apds9960():
    _check_i2c("apds9960", "#include <Adafruit_APDS9960.h>\nAdafruit_APDS9960 apds;\n"
               "void setup(){ apds.begin(); } void loop(){}\n")
    print("  OK — apds9960")


def test_mlx90614():
    _check_i2c("mlx90614", "#include <Adafruit_MLX90614.h>\n"
               "Adafruit_MLX90614 mlx = Adafruit_MLX90614();\n"
               "void setup(){ mlx.begin(); } void loop(){}\n")
    print("  OK — mlx90614")


def test_sgp30():
    _check_i2c("sgp30", "#include <Adafruit_SGP30.h>\nAdafruit_SGP30 sgp;\n"
               "void setup(){ sgp.begin(); } void loop(){}\n")
    print("  OK — sgp30")


def test_scd30():
    _check_i2c("scd30", "#include <Adafruit_SCD30.h>\nAdafruit_SCD30 scd30;\n"
               "void setup(){ scd30.begin(); } void loop(){}\n")
    print("  OK — scd30")


def test_pn532_literals():
    code = ("#include <Adafruit_PN532.h>\nAdafruit_PN532 nfc(2, 3);\n"
            "void setup(){ nfc.begin(); nfc.SAMConfig(); } void loop(){}\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "pn532")[0])
    assert n.get("SDA") == "A4" and n.get("SCL") == "A5", n
    assert n.get("IRQ") == "D2" and n.get("RST") == "D3", n
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    print("  OK — pn532 (IRQ/RST littéraux + SDA/SCL)")


def test_pn532_defines():
    code = ("#include <Adafruit_PN532.h>\n#define PN532_IRQ 2\n#define PN532_RESET 3\n"
            "Adafruit_PN532 nfc(PN532_IRQ, PN532_RESET);\n"
            "void setup(){ nfc.begin(); } void loop(){}\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "pn532")[0])
    assert n.get("IRQ") == "D2" and n.get("RST") == "D3", n
    print("  OK — pn532 (#define résolus)")


def test_pcf8574():
    code = ("#include <PCF8574.h>\nPCF8574 pcf(0x20);\n"
            "void setup(){ pcf.begin(); } void loop(){}\n")
    nl = extract_netlist(code, board_id="uno")
    c = _of(nl, "pcf8574")[0]
    n = _nets(c)
    assert n.get("SDA") == "A4" and n.get("SCL") == "A5", n
    assert c.attributes.get("unwired_pins") == ["P0","P1","P2","P3","P4","P5","P6","P7"], \
        c.attributes.get("unwired_pins")
    w = [x for x in nl.warnings if x.code == "unwired_component_pins"]
    assert w, "warning unwired_component_pins absent"
    print("  OK — pcf8574 (unwired P0..P7 + warning)")


def test_mcp23017():
    code = ("#include <Adafruit_MCP23X17.h>\nAdafruit_MCP23X17 mcp;\n"
            "void setup(){ mcp.begin_I2C(); } void loop(){}\n")
    nl = extract_netlist(code, board_id="uno")
    c = _of(nl, "mcp23017")[0]
    n = _nets(c)
    assert n.get("SDA") == "A4" and n.get("SCL") == "A5", n
    up = c.attributes.get("unwired_pins")
    assert up == [f"A{i}" for i in range(8)] + [f"B{i}" for i in range(8)], up
    print("  OK — mcp23017 (unwired A0..A7,B0..B7)")


def test_max6675():
    code = ("#include <max6675.h>\nMAX6675 thermocouple(6, 5, 4);\n"
            "void setup(){} void loop(){ thermocouple.readCelsius(); }\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "max6675")[0])
    assert n.get("SCK") == "D6" and n.get("CS") == "D5" and n.get("SO") == "D4", n
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    print("  OK — max6675 SCK/CS/SO")


def test_expander_output_pins_rendered():
    """Regression: output pins of expanders must be DRAWN (catalog entry DIP
    listing P0..P7 / A0..B7), not just present in `unwired_pins`. Otherwise the
    component has only 4 legs visually and the user cannot see where to wire
    its outputs."""
    from ui.wiring.layout.pipeline import render_complete
    svg, _ = render_complete(
        "#include <PCF8574.h>\nPCF8574 pcf(0x20);\n"
        "void setup(){ pcf.begin(); } void loop(){}\n", "arduino_uno_r3")
    assert svg, "render pcf8574 vide"
    for lbl in [f"P{i}" for i in range(8)] + ["SDA", "SCL"]:
        assert lbl in svg, f"pcf8574: label {lbl} absent du rendu"
    svg2, _ = render_complete(
        "#include <Adafruit_MCP23X17.h>\nAdafruit_MCP23X17 mcp;\n"
        "void setup(){ mcp.begin_I2C(); } void loop(){}\n", "arduino_uno_r3")
    assert svg2, "render mcp23017 vide"
    for lbl in [f"A{i}" for i in range(8)] + [f"B{i}" for i in range(8)] + ["SDA", "SCL"]:
        assert lbl in svg2, f"mcp23017: label {lbl} absent du rendu"
    print("  OK — expander output pins rendered (pcf8574 P0-P7, mcp23017 A0-B7)")


TESTS = [
    test_rag_retrieval_batch4,
    test_bmp280, test_apds9960, test_mlx90614, test_sgp30, test_scd30,
    test_pn532_literals, test_pn532_defines,
    test_pcf8574, test_mcp23017, test_max6675,
    test_expander_output_pins_rendered,
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
