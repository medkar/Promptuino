"""Test isole de la convention SVG composants generiques.

Affiche une breadboard verticale (pitch 28x28) et y depose le composant
2-pins charge depuis assets/wiring/components/component-2pins.svg.
Les placeholders sont remplaces dynamiquement :
    - id="component-name"  -> "LED"
    - id="pin-1-label"     -> "GND"
    - id="pin-2-label"     -> "res"

Le composant est positionne pour que pin-1-pos et pin-2-pos tombent
exactement sur 2 trous adjacents de la grille (validation visuelle de
la convention).

Usage : python scripts/test_svg_component.py
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PyQt6.QtCore import QByteArray
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QScrollArea, QFrame,
)


ROOT = Path(__file__).resolve().parent.parent
COMPONENT_SVG = ROOT / "assets" / "wiring" / "components" / "single-row" / "2pins.svg"

NS = {
    "svg": "http://www.w3.org/2000/svg",
    "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
    "inkscape": "http://www.inkscape.org/namespaces/inkscape",
}
ET.register_namespace("", NS["svg"])
ET.register_namespace("sodipodi", NS["sodipodi"])
ET.register_namespace("inkscape", NS["inkscape"])


# --- Geometrie test ----------------------------------------------------
PITCH = 28
BB_ORIGIN_X = 60
BB_ORIGIN_Y = 60
BB_COLS = 8
BB_ROWS = 22
HOLE_R = 3
CANVAS_W = BB_ORIGIN_X * 2 + (BB_COLS - 1) * PITCH + 80
CANVAS_H = BB_ORIGIN_Y * 2 + (BB_ROWS - 1) * PITCH + 30


def hole_xy(col: int, row: int) -> tuple[int, int]:
    return (BB_ORIGIN_X + col * PITCH, BB_ORIGIN_Y + row * PITCH)


# --- Loader composant --------------------------------------------------
def _merge_style(elem: ET.Element, **props: str) -> None:
    """Merge des proprietes CSS dans l'attribut style d'un element."""
    pairs: list[tuple[str, str]] = []
    for chunk in elem.get("style", "").split(";"):
        chunk = chunk.strip()
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            pairs.append((k.strip(), v.strip()))
    style_dict = dict(pairs)
    style_dict.update(props)
    elem.set("style", ";".join(f"{k}:{v}" for k, v in style_dict.items()))


def _apply_text_style(text_elem: ET.Element, cfg: dict | None) -> None:
    """Applique size / bold / italic au <text> et ses <tspan>.

    cfg keys :
      - size   : int (px)
      - bold   : bool
      - italic : bool
    """
    if not cfg or text_elem is None:
        return
    css: dict[str, str] = {}
    if "size" in cfg:
        css["font-size"] = f"{cfg['size']}px"
    if "bold" in cfg:
        css["font-weight"] = "bold" if cfg["bold"] else "normal"
    if "italic" in cfg:
        css["font-style"] = "italic" if cfg["italic"] else "normal"
    if not css:
        return
    _merge_style(text_elem, **css)
    for tspan in text_elem.findall("svg:tspan", NS):
        _merge_style(tspan, **css)


def load_component(svg_path: Path, name: str, pin_labels: dict[int, str],
                   name_style: dict | None = None,
                   pin_label_style: dict | None = None,
                   stroke_widths: dict | None = None,
                   ) -> tuple[ET.Element, dict[int, tuple[float, float]]]:
    """Charge un SVG composant, remplace les placeholders et applique
    optionnellement un style sur le nom, les labels et les stroke-widths.

    stroke_widths keys :
      - body : epaisseur du contour du component-body (rect)
      - leg  : epaisseur des pattes (tous les <path>)
      - pin  : epaisseur du contour des pin-N-pos (circles)
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()
    component = root.find(".//svg:g[@id='component']", NS)
    if component is None:
        raise ValueError(f"<g id='component'> introuvable dans {svg_path}")

    # Remplace component-name (1 seul tspan attendu) + style optionnel.
    name_text = component.find("svg:text[@id='component-name']", NS)
    if name_text is not None:
        tspans = name_text.findall("svg:tspan", NS)
        if tspans:
            tspans[0].text = name
            for extra in tspans[1:]:
                name_text.remove(extra)
        _apply_text_style(name_text, name_style)

    # Pour chaque pin-N-pos present, lit ses coords + remplace son label.
    pin_positions: dict[int, tuple[float, float]] = {}
    idx = 1
    while True:
        circle = component.find(f"svg:circle[@id='pin-{idx}-pos']", NS)
        if circle is None:
            break
        cx = float(circle.get("cx", "0"))
        cy = float(circle.get("cy", "0"))
        pin_positions[idx] = (cx, cy)
        if idx in pin_labels:
            label = component.find(f"svg:text[@id='pin-{idx}-label']", NS)
            if label is not None:
                tspans = label.findall("svg:tspan", NS)
                if tspans:
                    tspans[0].text = pin_labels[idx]
                    for extra in tspans[1:]:
                        label.remove(extra)
                _apply_text_style(label, pin_label_style)
        if stroke_widths and "pin" in stroke_widths:
            _merge_style(circle, **{"stroke-width": str(stroke_widths["pin"])})
        idx += 1

    if stroke_widths:
        if "body" in stroke_widths:
            body = component.find("svg:rect[@id='component-body']", NS)
            if body is not None:
                _merge_style(body, **{"stroke-width": str(stroke_widths["body"])})
        if "leg" in stroke_widths:
            for path in component.findall("svg:path", NS):
                _merge_style(path, **{"stroke-width": str(stroke_widths["leg"])})

    return component, pin_positions


# --- Generation du SVG composite --------------------------------------
def build_test_svg() -> str:
    component, pins = load_component(
        COMPONENT_SVG,
        name="LED",
        pin_labels={1: "GND", 2: "res"},
        # Demo : nom plus gros + bold, labels italiques.
        name_style={"size": 12, "bold": True, "italic": False},
        pin_label_style={"size": 7, "bold": False, "italic": True},
        # Demo epaisseurs : body fin, pattes epaisses, pins fins.
        stroke_widths={"body": 1, "leg": 3, "pin": 0.8},
    )

    # Cible : pin-1-pos sur le trou (col=1, row=5).
    target_col, target_row = 1, 5
    target_x, target_y = hole_xy(target_col, target_row)
    p1_cx, p1_cy = pins[1]
    tx = target_x - p1_cx
    ty = target_y - p1_cy

    # Compute where pin-2-pos lands (in canvas coords) for highlight.
    p2_cx, p2_cy = pins[2]
    p2_canvas_x = p2_cx + tx
    p2_canvas_y = p2_cy + ty

    component_xml = ET.tostring(component, encoding="unicode")

    # Grille de trous.
    holes_lines = []
    for col in range(BB_COLS):
        for row in range(BB_ROWS):
            x, y = hole_xy(col, row)
            holes_lines.append(
                f'<circle cx="{x}" cy="{y}" r="{HOLE_R}" '
                f'fill="#222" stroke="none"/>'
            )
    holes_xml = "\n      ".join(holes_lines)

    # Highlight des 2 trous cibles.
    highlights = (
        f'<circle cx="{target_x}" cy="{target_y}" r="7" fill="none" '
        f'stroke="#d62728" stroke-width="1.5" stroke-dasharray="2,2"/>'
        f'<circle cx="{p2_canvas_x}" cy="{p2_canvas_y}" r="7" fill="none" '
        f'stroke="#d62728" stroke-width="1.5" stroke-dasharray="2,2"/>'
    )

    title = (
        f'<text x="{CANVAS_W // 2}" y="28" text-anchor="middle" '
        f'font-family="sans-serif" font-size="13" font-weight="bold" '
        f'fill="#333">Breadboard verticale (pitch {PITCH}px) — '
        f'composant 2-pins charge depuis SVG Inkscape</text>'
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{CANVAS_W}" height="{CANVAS_H}" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}">\n'
        f'  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="#ffffff"/>\n'
        f'  {title}\n'
        f'  <g id="breadboard">\n      {holes_xml}\n  </g>\n'
        f'  <g id="targets">{highlights}</g>\n'
        f'  <g transform="translate({tx},{ty})">\n    {component_xml}\n  </g>\n'
        f'</svg>\n'
    )


# --- Dialog PyQt -------------------------------------------------------
class TestComponentDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test SVG composant — breadboard verticale 28x28")
        self.resize(min(CANVAS_W + 60, 800), min(CANVAS_H + 60, 900))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        svg_str = build_test_svg()
        widget = QSvgWidget()
        widget.load(QByteArray(svg_str.encode("utf-8")))
        widget.resize(CANVAS_W, CANVAS_H)
        scroll.setWidget(widget)

        layout.addWidget(scroll)


def main():
    # Dump le SVG sur stdout si --dump pour inspection sans GUI.
    if "--dump" in sys.argv:
        print(build_test_svg())
        return

    app = QApplication(sys.argv)
    dlg = TestComponentDialog()
    dlg.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
