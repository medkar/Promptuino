"""IAView refonte smoke test. Run: python scripts/test_ia_view_smoke.py"""
from __future__ import annotations
import os, sys, types
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_store = {}
fk = types.ModuleType("keyring")
fk.get_password = lambda s, k: _store.get((s, k))
fk.set_password = lambda s, k, v: _store.__setitem__((s, k), v)
fk.delete_password = lambda s, k: _store.pop((s, k), None)
sys.modules["keyring"] = fk

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from ui.ia_view import IAView
from ui.ai_backends.providers import PROVIDERS


def test_iaview_builds_and_lists_providers():
    v = IAView()
    combo = v._cloud._provider_combo
    items = [combo.itemData(i) for i in range(combo.count())]
    for p in PROVIDERS:
        assert p.id in items, f"provider {p.id} missing from combo"
    assert "custom" in items, "custom entry missing from combo"
    # Model selector is now an editable combo (pick from /models or type one).
    assert v._cloud._model_combo.isEditable(), "model combo must be editable"


def main() -> int:
    test_iaview_builds_and_lists_providers()
    print("OK : 1 tests")
    sys.stdout.flush()   # os._exit skips buffer flushing
    os._exit(0)   # avoid Qt teardown crash on exit (project convention for offscreen tests)


if __name__ == "__main__":
    main()
