"""Tests pour le fix du menu engrenage + la preference "ne plus me demander"
de la popup "ce n'est pas le bon composant" (filet F2-5).

Runner standalone offscreen : python scripts/test_wrong_component_confirm.py

Couvre :
- _GearActionItem.mousePressEvent NE DOIT PAS appeler le callback de menu de
  facon synchrone (le fix du bug "le menu reste / se met la ou j'ai clique" :
  l'ouverture est differee via QTimer.singleShot pour relacher le grab souris).
- Session.skip_wrong_component_confirm : round-trip de persistance (defaut
  False, ecrit sur disque, relu par une nouvelle instance).
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

_qapp = QApplication.instance() or QApplication([])

from ui.wiring.wiring_diagram_dialog import _GearActionItem
import ui.session as session_mod


class _FakeEvent:
    def __init__(self, button=Qt.MouseButton.LeftButton):
        self._button = button
        self.accepted = False

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True


class _FakeSchemaView:
    def __init__(self):
        self.calls: list = []
        self._gear_click_fn = lambda ref: self.calls.append(ref)


def test_gear_press_defers_menu_open():
    """Le press accepte l'event mais N'OUVRE PAS le menu de facon synchrone :
    le callback ne doit etre invoque qu'apres un tour de boucle (singleShot)."""
    view = _FakeSchemaView()
    item = _GearActionItem("U1", view, QPixmap(), active=True)
    ev = _FakeEvent()
    item.mousePressEvent(ev)
    assert ev.accepted is True, "le press doit etre accepte"
    assert view.calls == [], "le menu ne doit PAS s'ouvrir dans le press (sync)"
    _qapp.processEvents()  # laisse le QTimer.singleShot(0) se declencher
    assert view.calls == ["U1"], "le menu doit s'ouvrir apres le tour de boucle"
    print("  [OK] press engrenage : ouverture du menu differee (fix grab souris)")


def test_gear_press_ignored_when_inactive():
    """Engrenage inactif : le press est accepte (ne deselectionne pas) mais
    ne declenche aucun callback, meme apres processEvents."""
    view = _FakeSchemaView()
    item = _GearActionItem("U1", view, QPixmap(), active=False)
    ev = _FakeEvent()
    item.mousePressEvent(ev)
    _qapp.processEvents()
    assert view.calls == [], "inactif : aucun callback"
    print("  [OK] press engrenage inactif : aucun callback")


def test_skip_pref_round_trip(tmp_path):
    """Defaut False ; ecriture True persistee sur disque ; relue par une
    nouvelle instance Session pointant le meme fichier."""
    orig = session_mod._SESSION_PATH
    try:
        session_mod._SESSION_PATH = tmp_path / "session.json"
        s1 = session_mod.Session()
        assert s1.skip_wrong_component_confirm is False, "defaut = False"
        s1.skip_wrong_component_confirm = True
        assert (tmp_path / "session.json").exists(), "doit etre ecrit sur disque"
        s2 = session_mod.Session()  # nouvelle instance, meme fichier
        assert s2.skip_wrong_component_confirm is True, "doit etre relu = True"
        s2.skip_wrong_component_confirm = False
        s3 = session_mod.Session()
        assert s3.skip_wrong_component_confirm is False, "remis a False persiste"
    finally:
        session_mod._SESSION_PATH = orig
    print("  [OK] pref skip_wrong_component_confirm : round-trip disque")


def main() -> int:
    print("[test_wrong_component_confirm]\n")
    tests = [
        test_gear_press_defers_menu_open,
        test_gear_press_ignored_when_inactive,
        test_skip_pref_round_trip,
    ]
    failed = 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for fn in tests:
            try:
                if fn.__code__.co_argcount == 1:
                    fn(tmp)
                else:
                    fn()
            except AssertionError as e:
                print(f"  [FAIL] {fn.__name__}: {e}"); failed += 1
            except Exception as e:
                print(f"  [ERR ] {fn.__name__}: {type(e).__name__}: {e}"); failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
