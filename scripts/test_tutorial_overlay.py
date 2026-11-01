"""Overlay tutoriel : fleche pointant au MILIEU du bord du composant + bulle
assez large pour la rangee compteur + 3 boutons (« Precedent » non tronque)."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication, QWidget
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.i18n import lang_manager
from ui.tutorial import TutorialOverlay, _BUBBLE_W

_SPOT = QRect(100, 100, 80, 40)


def test_arrow_points_to_mid_bottom_when_bubble_below():
    bub = QRect(0, _SPOT.bottom() + 40, _BUBBLE_W, 120)
    m = TutorialOverlay._spot_edge_midpoint(_SPOT, bub)
    assert m.x() == _SPOT.center().x() and m.y() == _SPOT.bottom()


def test_arrow_points_to_mid_top_when_bubble_above():
    bub = QRect(0, _SPOT.top() - 160, _BUBBLE_W, 120)
    m = TutorialOverlay._spot_edge_midpoint(_SPOT, bub)
    assert m.x() == _SPOT.center().x() and m.y() == _SPOT.top()


def test_arrow_points_to_mid_right_when_bubble_right():
    bub = QRect(_SPOT.right() + 40, 0, _BUBBLE_W, 120)
    m = TutorialOverlay._spot_edge_midpoint(_SPOT, bub)
    assert m.x() == _SPOT.right() and m.y() == _SPOT.center().y()


def test_arrow_points_to_mid_left_when_bubble_left():
    bub = QRect(_SPOT.left() - (_BUBBLE_W + 40), 0, _BUBBLE_W, 120)
    m = TutorialOverlay._spot_edge_midpoint(_SPOT, bub)
    assert m.x() == _SPOT.left() and m.y() == _SPOT.center().y()


def test_bubble_widened():
    assert _BUBBLE_W >= 400


def test_nav_buttons_fit_without_truncation_all_langs():
    host = QWidget()
    host.resize(1000, 800)
    ov = TutorialOverlay(host)
    usable = _BUBBLE_W - 32          # marges horizontales de la bulle (16 + 16)
    for lg in ("fr", "en", "es", "it"):
        lang_manager.set_language(lg)
        s = lang_manager.current
        ov._btn_back.setText(getattr(s, "tutorial_back", "Precedent"))
        ov._btn_skip.setText(getattr(s, "tutorial_skip", "Passer"))
        ov._btn_next.setText(getattr(s, "tutorial_next", "Suivant"))
        ov._counter.setText("2/5")
        for wdg in (ov._counter, ov._btn_back, ov._btn_skip, ov._btn_next):
            wdg.adjustSize()
        need = (ov._counter.sizeHint().width()
                + ov._btn_back.sizeHint().width()
                + ov._btn_skip.sizeHint().width()
                + ov._btn_next.sizeHint().width()
                + 8 * 4)             # 4 espacements de la rangee
        assert need <= usable, f"{lg}: need {need}px > usable {usable}px"
    lang_manager.set_language("fr")


TESTS = [
    test_arrow_points_to_mid_bottom_when_bubble_below,
    test_arrow_points_to_mid_top_when_bubble_above,
    test_arrow_points_to_mid_right_when_bubble_right,
    test_arrow_points_to_mid_left_when_bubble_left,
    test_bubble_widened,
    test_nav_buttons_fit_without_truncation_all_langs,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
