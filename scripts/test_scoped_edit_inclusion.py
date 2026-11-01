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

from ui.wiring.netlist import Component, Pin, Netlist
from ui.wiring.ambiguity_dialog import collect_ambiguous, include_scoped_target


def _nl():
    # une LED medium-confidence (nommee dans le prompt) -> PAS dans collect_ambiguous
    led = Component(ref="D1", type="led", pins=[Pin("A", "D5"), Pin("K", "GND")],
                    attributes={"_confidence": "medium", "category": "single_output",
                                "signature_detected": False})
    return Netlist(board_id="", components=[led])


def test_collect_ambiguous_excludes_medium():
    nl = _nl()
    assert collect_ambiguous(nl) == []          # confirme le trou


def test_include_scoped_target_adds_confident_component():
    nl = _nl()
    amb = collect_ambiguous(nl)                  # []
    out = include_scoped_target(amb, nl, "D1")
    assert any(c.ref == "D1" for c in out)       # la LED est maintenant a moder


def test_include_scoped_target_noop_when_already_present():
    led = Component(ref="D2", type="led", pins=[Pin("A", "D6")],
                    attributes={"_confidence": "low"})
    nl = Netlist(board_id="", components=[led])
    amb = collect_ambiguous(nl)                  # [D2]
    out = include_scoped_target(amb, nl, "D2")
    assert sum(1 for c in out if c.ref == "D2") == 1   # pas de doublon


def test_include_scoped_target_noop_when_none():
    nl = _nl()
    amb = collect_ambiguous(nl)
    assert include_scoped_target(amb, nl, None) == amb


TESTS = [
    test_collect_ambiguous_excludes_medium,
    test_include_scoped_target_adds_confident_component,
    test_include_scoped_target_noop_when_already_present,
    test_include_scoped_target_noop_when_none,
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
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
