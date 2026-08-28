"""Test offscreen du filigrane des exports/copies PNG (#13).

Vérifie que le filigrane (logo badge + URL) :
  - est posé SOUS la carte (jamais sur elle) ;
  - fait agrandir le canevas vers le bas quand la carte touche le bas du schéma
    (au lieu de remonter sur la carte) ;
  - garde l'intérieur de la carte intact ;
  - utilise un logo réduit (~21 % de la hauteur carte).

Run : QT_QPA_PLATFORM=offscreen python scripts/test_wiring_watermark.py
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
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QByteArray, QSize
from PyQt6.QtSvg import QSvgRenderer

from ui.wiring.wiring_diagram_dialog import (
    WiringDiagramDialog, _LOGO_DIR, _WATERMARK_LOGO_SVG, _WATERMARK_TAGLINE,
)

_qapp = QApplication.instance() or QApplication([])


def _svg(board_y: int, board_h: int = 120) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" '
        'viewBox="0 0 400 300">'
        '<rect width="400" height="300" fill="#ffffff"/>'
        f'<g id="board-instance"><rect x="120" y="{board_y}" width="160" '
        f'height="{board_h}" fill="#0b8a86"/></g>'
        '</svg>'
    )


_SVG_BOARD_BOTTOM = _svg(170)   # carte en bas (y 170..290 sur 300) → peu de place
_SVG_BOARD_TOP = _svg(30)       # carte en haut → place dessous


class _Fake:
    """Porte juste ce qu'il faut pour appeler _render_png_image hors QDialog."""
    _watermark_layout = WiringDiagramDialog._watermark_layout
    _paint_watermark = WiringDiagramDialog._paint_watermark
    _render_png_image = WiringDiagramDialog._render_png_image

    def __init__(self, svg):
        self._svg_str = svg


def _layout(svg, scale=2.0):
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    size = r.defaultSize()
    region = QSize(int(size.width() * scale), int(size.height() * scale))
    wm = WiringDiagramDialog._watermark_layout(None, r, region, scale)
    return wm, region


def test_logo_asset_exists():
    assert (_LOGO_DIR / _WATERMARK_LOGO_SVG).exists()
    assert _WATERMARK_LOGO_SVG == "icon-dark.svg", _WATERMARK_LOGO_SVG
    print("  [OK] logo badge à fond sombre (icon-dark.svg) présent")


def test_logo_is_below_board_and_small():
    wm, region = _layout(_SVG_BOARD_TOP)   # board y30..150 → bottom*2 = 300
    board_bottom = 150 * 2
    assert wm["logo_rect"].top() > board_bottom, "logo pas sous la carte"
    # box_h = ref_h(120*2=240) * 0.21 = 50.4 → logo ~50 px (scaled down 50%).
    assert abs(wm["logo_rect"].height() - 50.4) < 1.5, wm["logo_rect"].height()
    print(f"  [OK] logo sous la carte, réduit (~{wm['logo_rect'].height():.0f}px)")


def test_tagline_above_logo():
    assert _WATERMARK_TAGLINE == "Generated with", _WATERMARK_TAGLINE
    wm, region = _layout(_SVG_BOARD_TOP)
    # "Generated with" stacked ABOVE the logo, logo ABOVE the URL.
    assert wm["tag_rect"].bottom() <= wm["logo_rect"].top() + 1, "tagline pas au-dessus"
    assert wm["logo_rect"].bottom() <= wm["url_rect"].top() + 1, "URL pas en dessous"
    print("  [OK] « Generated with » au-dessus du logo, URL en dessous")


def test_canvas_extends_when_board_at_bottom():
    img = _Fake(_SVG_BOARD_BOTTOM)._render_png_image(scale=2.0)
    # SVG zone = 400×300 ×2 = 800×600; board at bottom forces an extra strip.
    assert img.height() > 600, f"canevas non agrandi ({img.height()})"
    # A pixel from the added strip (below 600) is not white → watermark is there.
    found = any(
        QColor(img.pixel(x, y)) != QColor("#ffffff")
        for y in range(605, img.height(), 3) for x in range(0, img.width(), 6)
    )
    assert found, "rien de dessiné dans la bande ajoutée"
    print(f"  [OK] canevas agrandi (h={img.height()}) + filigrane dans la bande")


def test_no_extension_when_room_below():
    img = _Fake(_SVG_BOARD_TOP)._render_png_image(scale=2.0)
    assert img.height() == 600, f"canevas agrandi à tort ({img.height()})"
    print("  [OK] pas d'agrandissement quand il y a la place sous la carte")


def test_board_interior_untouched():
    img = _Fake(_SVG_BOARD_TOP)._render_png_image(scale=2.0)
    # Centre de la carte (board y30..150, centre y90 → ×2 = 180 ; x200 → 400).
    px = QColor(img.pixel(400, 180))
    assert (px.red(), px.green(), px.blue()) == (11, 138, 134), px.getRgb()
    print("  [OK] intérieur de la carte intact (teal préservé)")


TESTS = [
    test_logo_asset_exists,
    test_logo_is_below_board_and_small,
    test_tagline_above_logo,
    test_canvas_extends_when_board_at_bottom,
    test_no_extension_when_room_below,
    test_board_interior_untouched,
]


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
