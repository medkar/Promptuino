"""Tout attribut `self._…worker` lu par StudioView existe des la construction.

Trouve le 2026-11-07 en pilotant la vraie fenetre : la garde de reentrance
de « Ajouter des commentaires » (audit du 2026-11-06, #4) lisait
`self._addcmt_worker` AVANT que rien ne l'ait jamais pose -- le premier clic
levait AttributeError. Le test d'audit ne pouvait pas le voir : il appelait
la methode sur un faux `self` (MagicMock) qui avait l'attribut. Ce test-ci
construit une VRAIE vue, et balaie le source pour ne pas dependre d'une
liste ecrite a la main.
"""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_APP = None


def _vue():
    global _APP
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])
    import ui.studio_view as sv
    return sv.StudioView()


def test_every_worker_attribute_exists_on_a_fresh_view():
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    noms = sorted(set(re.findall(r"self\.(_\w*worker)\b", src)))
    assert "_addcmt_worker" in noms, noms        # le balayage voit bien le cas
    v = _vue()
    manquants = [n for n in noms if not hasattr(v, n)]
    assert not manquants, f"lus mais jamais initialises : {manquants}"


def test_add_comments_first_click_does_not_raise():
    v = _vue()
    import ui.studio_view as sv
    vrai = sv.get_backend_instance
    sv.get_backend_instance = lambda bid: None     # aucun vrai moteur
    import ui.studio_view as m
    avertissements = []
    vraie_boite = m.QMessageBox.warning
    m.QMessageBox.warning = staticmethod(lambda *a, **k: avertissements.append(a))
    try:
        v._run_add_comments()                       # levait AttributeError
    finally:
        sv.get_backend_instance = vrai
        m.QMessageBox.warning = vraie_boite
    assert avertissements, "sans moteur, la carte le dit"


TESTS = [test_every_worker_attribute_exists_on_a_fresh_view,
         test_add_comments_first_click_does_not_raise]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t(); print("PASS", t.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1; print("FAIL", t.__name__, repr(e)[:300])
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    sys.stdout.flush()
    os._exit(1 if failed else 0)
