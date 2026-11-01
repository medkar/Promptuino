import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules.setdefault("ui", ui_pkg)

from ui.wiring import categories as cat


def test_core_category_constants_exist():
    assert cat.SINGLE_OUTPUT == "single_output"
    assert cat.ANALOG_IN == "analog_in"
    assert cat.DIGITAL_IN == "digital_in"
    assert cat.I2C == "i2c"
    assert cat.SPI == "spi"
    assert cat.UART == "uart"
    assert cat.SERVO == "servo"
    assert cat.ULTRASONIC == "ultrasonic"
    assert cat.ONEWIRE_TEMP == "onewire_temp"
    assert cat.MOTOR_DC == "motor_dc"
    assert cat.MOTOR_STEPPER == "motor_stepper"
    assert cat.NON_REPLACEABLE == "non_replaceable"


def test_category_of_known_types():
    assert cat.category_of("led") == cat.SINGLE_OUTPUT
    assert cat.category_of("buzzer") == cat.SINGLE_OUTPUT
    assert cat.category_of("relay") == cat.SINGLE_OUTPUT
    assert cat.category_of("ldr") == cat.ANALOG_IN
    assert cat.category_of("potentiometer") == cat.ANALOG_IN
    assert cat.category_of("button") == cat.DIGITAL_IN
    assert cat.category_of("pir") == cat.DIGITAL_IN
    assert cat.category_of("oled_ssd1306") == cat.I2C
    assert cat.category_of("servo") == cat.SERVO
    assert cat.category_of("hcsr04") == cat.ULTRASONIC
    assert cat.category_of("dht22") == cat.ONEWIRE_TEMP
    assert cat.category_of("dc_motor") == cat.MOTOR_DC
    assert cat.category_of("nema17") == cat.MOTOR_STEPPER
    assert cat.category_of("resistor") == cat.NON_REPLACEABLE
    assert cat.category_of("l298n") == cat.NON_REPLACEABLE
    assert cat.category_of("unknown_xyz") is None


def test_candidates_in_returns_same_category_members():
    out = cat.candidates_in(cat.SINGLE_OUTPUT)
    assert "led" in out and "buzzer" in out and "relay" in out
    assert "ldr" not in out
    assert cat.candidates_in(cat.NON_REPLACEABLE) == []


def test_candidates_in_motor_stepper_has_no_phantom_type():
    out = cat.candidates_in(cat.MOTOR_STEPPER)
    assert out == ["nema17", "stepper_motor"]  # no phantom "stepper" type


def test_candidates_in_i2c_members():
    out = cat.candidates_in(cat.I2C)
    assert "lcd_i2c" in out and "oled_ssd1306" in out and "module_generic" in out


def test_every_catalog_type_has_a_category():
    from ui.wiring.layout.component_catalog import CATALOG
    missing = [t for t in CATALOG if cat.category_of(t) is None]
    assert not missing, f"types catalogue sans catégorie : {missing}"


def test_markers_emitted_types_have_a_category():
    import re, pathlib
    src = pathlib.Path("ui/wiring/markers.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'_add\(\s*"([a-z0-9_]+)"', src))
    missing = sorted(t for t in emitted if cat.category_of(t) is None)
    assert not missing, f"types markers sans catégorie : {missing}"


TESTS = [
    test_core_category_constants_exist,
    test_category_of_known_types,
    test_candidates_in_returns_same_category_members,
    test_candidates_in_motor_stepper_has_no_phantom_type,
    test_candidates_in_i2c_members,
    test_every_catalog_type_has_a_category,
    test_markers_emitted_types_have_a_category,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
