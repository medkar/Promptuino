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

from ui.wiring.netlist import Component, Pin
from ui.wiring import markers


def _c(type_id, **attrs):
    return Component(ref="X1", type=type_id, pins=[Pin("A", "D5")],
                     attributes=dict(attrs))


def test_tag_sets_category_from_type():
    c = _c("led")
    markers.tag_component_category(c, signature_detected=False)
    assert c.attributes["category"] == "single_output"
    assert c.attributes["signature_detected"] is False


def test_tag_marks_signature_detected_true():
    c = _c("servo")
    markers.tag_component_category(c, signature_detected=True)
    assert c.attributes["category"] == "servo"
    assert c.attributes["signature_detected"] is True


def test_tag_unknown_type_category_none():
    c = _c("weird_thing")
    markers.tag_component_category(c, signature_detected=True)
    assert c.attributes["category"] is None


def test_bare_pin_button_pot_not_signature_detected():
    from ui.wiring.netlist import Component, Pin
    for t in ("button", "potentiometer"):
        c = Component(ref="X1", type=t, pins=[Pin("A", "D4")], attributes={})
        markers.tag_component_category(
            c, signature_detected=markers._is_signature_detected(c))
        assert c.attributes["signature_detected"] is False, t


TESTS = [
    test_tag_sets_category_from_type,
    test_tag_marks_signature_detected_true,
    test_tag_unknown_type_category_none,
    test_bare_pin_button_pot_not_signature_detected,
]


def main():
    passed = 0
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
