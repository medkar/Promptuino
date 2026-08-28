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

from ui.wiring.layout import component_catalog as cc


def test_role_of_explicit_entry():
    assert cc.role_of("buzzer", 1) == "signal"
    assert cc.role_of("buzzer", 2) == "gnd"


def test_role_of_servo():
    assert cc.role_of("servo", 1) == "vcc"
    assert cc.role_of("servo", 2) == "gnd"
    assert cc.role_of("servo", 3) == "signal"


def test_default_roles_from_labels_when_unspecified():
    roles = cc._default_roles({1: "VCC", 2: "OUT", 3: "GND"})
    assert roles == {1: "vcc", 2: "signal", 3: "gnd"}


def test_led_signal_then_gnd():
    assert cc.role_of("led", 1) == "signal"
    assert cc.role_of("led", 2) == "gnd"


def test_role_of_default_path_for_driver_entries():
    # entries without explicit pin_roles -> derived from labels
    assert cc.role_of("uln2003", 1) == "vcc"   # label "VCC"
    assert cc.role_of("uln2003", 2) == "gnd"   # label "GND"
    assert cc.role_of("dc_motor", 1) == "out_a"  # now explicit
    assert cc.role_of("dc_motor", 2) == "out_b"


def test_stepper_coil_roles_are_distinct():
    nema = [cc.role_of("nema17", i) for i in range(1, 5)]
    assert len(set(nema)) == 4, f"rôles nema17 non distincts : {nema}"
    st = [cc.role_of("stepper_motor", i) for i in range(1, 6)]
    assert len(set(st)) == 5, f"rôles stepper_motor non distincts : {st}"


TESTS = [
    test_role_of_explicit_entry,
    test_role_of_servo,
    test_default_roles_from_labels_when_unspecified,
    test_led_signal_then_gnd,
    test_role_of_default_path_for_driver_entries,
    test_stepper_coil_roles_are_distinct,
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
