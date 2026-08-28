"""Tests headless pour ui.wiring.replacement_ui (SP2 Task 4).

Runner : python scripts/test_replacement_ui.py
Aucun pytest requis.
"""
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
from ui.wiring import replacement_ui as rui


def _c(type_id, **a):
    return Component(ref="D1", type=type_id, pins=[Pin("A", "D5")],
                     attributes=dict(a))


def test_choices_same_category_current_first():
    out = rui.build_replacement_choices(_c("led"), lang="fr")
    ids = [tid for tid, _label in out]
    assert ids[0] == "led", f"Premier element attendu 'led', obtenu {ids[0]!r}"
    assert "buzzer" in ids, "'buzzer' manquant dans les choix"
    assert "relay" in ids, "'relay' manquant dans les choix"
    assert "potentiometer" not in ids, "'potentiometer' ne devrait pas etre dans single_output"
    assert all(isinstance(lbl, str) and lbl for _t, lbl in out), "Labels vides ou non-str"


def test_choices_empty_for_non_replaceable():
    result = rui.build_replacement_choices(_c("resistor"), lang="fr")
    assert result == [], f"Attendu [], obtenu {result!r}"


def test_should_warn_divergence():
    sig = _c("oled_ssd1306", signature_detected=True)
    assert rui.should_warn_divergence(sig, "lcd_i2c") is True, \
        "Devrait avertir : signature_detected=True et type different"
    assert rui.should_warn_divergence(sig, "oled_ssd1306") is False, \
        "Ne devrait pas avertir : meme type"
    bare = _c("led", signature_detected=False)
    assert rui.should_warn_divergence(bare, "buzzer") is False, \
        "Ne devrait pas avertir : signature_detected=False"


def test_is_replaceable_predicate():
    assert rui.is_replaceable("led") is True
    assert rui.is_replaceable("oled_ssd1306") is True
    assert rui.is_replaceable("resistor") is False
    assert rui.is_replaceable("battery_external") is False
    assert rui.is_replaceable("inconnu_xyz") is False


TESTS = [
    test_choices_same_category_current_first,
    test_choices_empty_for_non_replaceable,
    test_should_warn_divergence,
    test_is_replaceable_predicate,
]


def main():
    passed = 0
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__} : {e}")
            failed += 1
    total = passed + failed
    print(f"\n{passed}/{total} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
