"""Detection for batch 3 bundles."""
from __future__ import annotations
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui.wiring.markers import extract_netlist  # noqa: E402


def _of(nl, t): return [c for c in nl.components if c.type == t]
def _nets(c): return {p.name: p.net for p in c.pins}


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


def test_vl53l0x():
    _check_i2c("vl53l0x", "#include <Adafruit_VL53L0X.h>\nAdafruit_VL53L0X lox;\n"
               "void setup(){ lox.begin(); } void loop(){}\n")
    print("  OK — vl53l0x")


def test_max30102():
    _check_i2c("max30102", "#include <MAX30105.h>\nMAX30105 sensor;\n"
               "void setup(){ sensor.begin(); } void loop(){}\n")
    print("  OK — max30102")


def test_tcs34725():
    _check_i2c("tcs34725", "#include <Adafruit_TCS34725.h>\nAdafruit_TCS34725 tcs;\n"
               "void setup(){ tcs.begin(); } void loop(){}\n")
    print("  OK — tcs34725")


def test_bh1750():
    _check_i2c("bh1750", "#include <BH1750.h>\nBH1750 lightMeter;\n"
               "void setup(){ lightMeter.begin(); } void loop(){}\n")
    print("  OK — bh1750")


def test_ads1115():
    _check_i2c("ads1115", "#include <Adafruit_ADS1X15.h>\nAdafruit_ADS1115 ads;\n"
               "void setup(){ ads.begin(); } void loop(){ ads.readADC_SingleEnded(0); }\n")
    print("  OK — ads1115")


def test_pca9685():
    _check_i2c("pca9685", "#include <Adafruit_PWMServoDriver.h>\n"
               "Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();\n"
               "void setup(){ pwm.begin(); pwm.setPWMFreq(50); } void loop(){}\n")
    print("  OK — pca9685")


def test_sh1106():
    _check_i2c("sh1106", "#include <Adafruit_SH110X.h>\n"
               "Adafruit_SH1106G display(128, 64, &Wire);\n"
               "void setup(){ display.begin(0x3C, true); } void loop(){}\n")
    print("  OK — sh1106")


def test_aht20():
    _check_i2c("aht20", "#include <Adafruit_AHTX0.h>\nAdafruit_AHTX0 aht;\n"
               "void setup(){ aht.begin(); } void loop(){}\n")
    print("  OK — aht20")


def test_st7735():
    code = ("#include <Adafruit_ST7735.h>\nAdafruit_ST7735 tft = Adafruit_ST7735(10, 9, 8);\n"
            "void setup(){ tft.initR(); } void loop(){}\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "st7735")[0])
    assert n.get("CS") == "D10" and n.get("DC") == "D9" and n.get("RST") == "D8", n
    assert n.get("SCK") == "D13" and n.get("MOSI") == "D11", n  # MOSI (ex-label "SDA" corrige 2026-06-18)
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    print("  OK — st7735 CS/DC/RST + SPI")


def test_st7789():
    code = ("#include <Adafruit_ST7789.h>\nAdafruit_ST7789 tft = Adafruit_ST7789(10, 9, 8);\n"
            "void setup(){ tft.init(240,240); } void loop(){}\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "st7789")[0])
    assert n.get("CS") == "D10" and n.get("DC") == "D9" and n.get("RST") == "D8", n
    print("  OK — st7789")


def test_max31855():
    code = ("#include <Adafruit_MAX31855.h>\nAdafruit_MAX31855 thermo(5, 6, 7);\n"
            "void setup(){} void loop(){ thermo.readCelsius(); }\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "max31855")[0])
    assert n.get("SCLK") == "D5" and n.get("CS") == "D6" and n.get("MISO") == "D7", n
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    print("  OK — max31855")


def test_hx711():
    code = ("#include <HX711.h>\nHX711 scale;\n"
            "void setup(){ scale.begin(3, 2); } void loop(){}\n")
    n = _nets(_of(extract_netlist(code, board_id="uno"), "hx711")[0])
    assert n.get("DT") == "D3" and n.get("SCK") == "D2", n
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    print("  OK — hx711 DT/SCK depuis begin()")


def test_dfplayer():
    code = ("#include <DFRobotDFPlayerMini.h>\n#include <SoftwareSerial.h>\n"
            "SoftwareSerial mySerial(10, 11);\nDFRobotDFPlayerMini player;\n"
            "void setup(){ player.begin(mySerial); } void loop(){}\n")
    nl = extract_netlist(code, board_id="uno")
    cs = _of(nl, "dfplayer")
    assert len(cs) == 1, f"attendu 1 dfplayer, {[c.type for c in nl.components]}"
    assert not _of(nl, "uart_module"), "uart_module doublon"
    n = _nets(cs[0])
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    assert {"RX", "TX"} <= set(n.keys()), n
    print("  OK — dfplayer (pas de uart_module)")


def test_rag_retrieval_batch3():
    """Every batch3 bundle is returned by retrieval for a descriptive prompt (FR)."""
    from ui.rag import retrieve_libs
    probes = [
        ("capteur de distance laser", "vl53l0x"),
        ("capteur de frequence cardiaque", "max30102"),
        ("capteur de couleur", "adafruit-tcs34725"),  # pre-existing corpus entry
        ("capteur de luminosite lux", "bh1750"),
        ("convertisseur analogique numerique i2c", "ads1115"),
        ("driver 16 servos", "pca9685"),
        ("ecran oled sh1106", "sh1106"),
        ("capteur temperature humidite aht20", "aht20"),
        ("ecran tft couleur", "st7735"),
        ("ecran tft 240", "st7789"),
        ("thermocouple type k", "max31855"),
        ("cellule de charge balance", "hx711"),
        ("module mp3", "dfplayer"),
    ]
    for q, expected in probes:
        r = retrieve_libs(q, k=5)
        ids = [(x.get("id") if isinstance(x, dict) else x) for x in r]
        assert expected in ids, f"{q!r} -> {ids} (attendu {expected})"
    print("  OK — retrieval batch3 (13 probes)")


TESTS = [test_vl53l0x, test_max30102, test_tcs34725, test_bh1750,
         test_ads1115, test_pca9685, test_sh1106, test_aht20,
         test_st7735, test_st7789, test_max31855,
         test_hx711, test_dfplayer,
         test_rag_retrieval_batch3]


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
