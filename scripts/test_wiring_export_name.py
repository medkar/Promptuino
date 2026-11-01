"""Test du nom de fichier proposé à l'export PNG du schéma : wiring_<projet>.

`_default_export_name` n'utilise que self._project_name → appel non lié avec un
faux self (pas besoin d'instancier le dialog complet).

Run : QT_QPA_PLATFORM=offscreen python scripts/test_wiring_export_name.py
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from PyQt6.QtWidgets import QApplication
from ui.wiring.wiring_diagram_dialog import WiringDiagramDialog

_qapp = QApplication.instance() or QApplication([])


def _name(project_name):
    fake = types.SimpleNamespace(_project_name=project_name)
    return WiringDiagramDialog._default_export_name(fake)


def test_uses_project_name():
    assert _name("Feu tricolore") == "wiring_Feu tricolore.png", _name("Feu tricolore")
    print("  [OK] nom d'export = wiring_<projet>.png")


def test_fallback_when_empty():
    assert _name("") == "wiring.png"
    assert _name(None) == "wiring.png"
    print("  [OK] repli wiring.png sans projet")


def test_strips_illegal_chars():
    assert _name('a/b:c*?"<>|d') == "wiring_abcd.png", _name('a/b:c*?"<>|d')
    print("  [OK] caractères interdits retirés du nom")


TESTS = [test_uses_project_name, test_fallback_when_empty, test_strips_illegal_chars]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            sys.stdout.flush()
            os._exit(1)
    print(f"OK : {len(TESTS)} tests")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
