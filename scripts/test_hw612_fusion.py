"""Détection MPU9250/BMP280 + fusion module HW-612 (ui/wiring)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.markers import extract_netlist

_CODE_HW612 = (
    "#include <MPU9250.h>\n"
    "#include <Adafruit_BMP280.h>\n"
    "MPU9250 mpu;\n"
    "Adafruit_BMP280 bmp;\n"
    "void setup() {\n"
    "  Wire.begin();\n"
    "  mpu.setup(0x68);\n"
    "  bmp.begin(0x76);\n"
    "}\n"
    "void loop() {\n"
    "  mpu.update();\n"
    "  bmp.readPressure();\n"
    "}\n"
)


def test_detects_mpu9250_and_bmp280():
    nl = extract_netlist(_CODE_HW612, "arduino_uno_r3", prompt="", context="")
    types = {c.type for c in nl.components}
    assert "mpu9250" in types, types
    assert "bmp280" in types, types


def test_fusion_when_module_named():
    nl = extract_netlist(_CODE_HW612, "arduino_uno_r3",
                         prompt="lis mon HW-612", context="")
    types = [c.type for c in nl.components]
    assert types.count("hw-612") == 1, types
    assert "mpu9250" not in types and "bmp280" not in types, types
    box = next(c for c in nl.components if c.type == "hw-612")
    nets = {p.net for p in box.pins}
    assert nets == {"5V", "GND", "A4", "A5"}, nets


def test_no_fusion_without_module_name():
    # memes 2 puces, mais le prompt ne nomme PAS le module -> 2 boites separees
    nl = extract_netlist(_CODE_HW612, "arduino_uno_r3",
                         prompt="lis l'accelerometre et la pression", context="")
    types = {c.type for c in nl.components}
    assert "hw-612" not in types, types
    assert "mpu9250" in types and "bmp280" in types, types


def test_fusion_single_chip_when_module_named():
    # Module nomme + UNE seule de ses puces utilisee (ex. boussole = magneto
    # seul) -> on relabelise quand meme en boite HW-612 (physiquement 1 carte).
    code = ("#include <MPU9250.h>\nMPU9250 mpu;\n"
            "void setup(){ Wire.begin(); mpu.setup(0x68); }\n"
            "void loop(){ mpu.update(); }\n")
    nl = extract_netlist(code, "arduino_uno_r3", prompt="mon HW-612", context="")
    types = {c.type for c in nl.components}
    assert "hw-612" in types, types       # 1 puce + module nomme -> boite HW-612
    assert "mpu9250" not in types, types


def test_no_fusion_single_chip_without_module_name():
    # 1 puce, sans nom de module -> reste une boite mpu9250 (pas de relabel)
    code = ("#include <MPU9250.h>\nMPU9250 mpu;\n"
            "void setup(){ Wire.begin(); mpu.setup(0x68); }\n"
            "void loop(){ mpu.update(); }\n")
    nl = extract_netlist(code, "arduino_uno_r3", prompt="lis l'accelerometre", context="")
    types = {c.type for c in nl.components}
    assert "hw-612" not in types, types
    assert "mpu9250" in types, types


TESTS = [test_detects_mpu9250_and_bmp280,
         test_fusion_when_module_named,
         test_no_fusion_without_module_name,
         test_fusion_single_chip_when_module_named,
         test_no_fusion_single_chip_without_module_name]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
