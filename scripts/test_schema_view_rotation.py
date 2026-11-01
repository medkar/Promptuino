"""Rotation 90° de la vue schema : le zoom reste correct apres rotation.

Verifie que :
 - rotate_view_90() pivote bien la vue (m11 ~ 0 a 90°, ce qui CASSERAIT
   l'ancien zoom base sur m11) ;
 - _current_scale() reste l'echelle reelle (invariante a la rotation) ;
 - zoom_in / set_zoom continuent de fonctionner apres rotation.

Qt requis (offscreen) ; skip propre si absent.
"""
from __future__ import annotations
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PyQt6.QtWidgets import QApplication, QGraphicsRectItem
    from PyQt6.QtCore import QRectF
    _HAS_QT = True
except Exception:
    _HAS_QT = False


def _view_with_content():
    from ui.wiring.wiring_diagram_dialog import SchemaView
    v = SchemaView()
    v._gscene.addItem(QGraphicsRectItem(QRectF(0, 0, 240, 120)))
    v.resize(400, 400)
    v.show()
    QApplication.instance().processEvents()
    return v


def test_rotation_keeps_zoom_working():
    app = QApplication.instance() or QApplication([])
    v = _view_with_content()

    v.fit_to_view()
    s0 = v._current_scale()
    assert s0 > 0, s0

    # Rotation 90° : m11 devient ~0 (= ce qui cassait l'ancien zoom base
    # sur m11), mais l'echelle reelle reste > 0.
    v.rotate_view_90()
    t = v.transform()
    assert abs(t.m11()) < 1e-6, f"m11 attendu ~0 a 90°, got {t.m11()}"
    s1 = v._current_scale()
    assert s1 > 0, s1
    assert math.isfinite(s1)

    # Zoom in apres rotation : l'echelle augmente (ne plante pas, n'est pas
    # bloquee par un cur=0).
    v.zoom_in()
    s2 = v._current_scale()
    assert s2 > s1, (s1, s2)

    # set_zoom absolu fonctionne aussi malgre la rotation.
    v.set_zoom(1.0)
    assert abs(v._current_scale() - 1.0) < 1e-6, v._current_scale()

    # On a deja pivote 1x ; 3 rotations de plus = 360° total = retour a
    # l'orientation initiale (m12 ~ 0).
    for _ in range(3):
        v.rotate_view_90()
    assert abs(v.transform().m12()) < 1e-6, v.transform().m12()


TESTS = [test_rotation_keeps_zoom_working]


def main() -> int:
    if not _HAS_QT:
        print("SKIP (PyQt6 absent)")
        return 0
    for t in TESTS:
        t()
        print(f"PASS {t.__name__}")
    print(f"OK : {len(TESTS)} test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
