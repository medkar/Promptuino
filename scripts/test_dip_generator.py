"""Garde format/geometrie du generateur DIP procedural (#1)."""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gen_dip_svgs as gen

NS = {"svg": "http://www.w3.org/2000/svg"}


def _pins(svg: str) -> dict[int, tuple[float, float]]:
    root = ET.fromstring(svg)
    out: dict[int, tuple[float, float]] = {}
    idx = 1
    while True:
        c = root.find(f".//svg:circle[@id='pin-{idx}-pos']", NS)
        if c is None:
            break
        out[idx] = (float(c.get("cx")), float(c.get("cy")))
        idx += 1
    return out


def test_pin_count_and_two_columns():
    pins = _pins(gen.dip_svg(16))
    assert len(pins) == 16
    cxs = sorted({round(cx) for cx, _ in pins.values()})
    assert len(cxs) == 2


def test_channel_span():
    pins = _pins(gen.dip_svg(16))
    cxs = sorted({round(cx) for cx, _ in pins.values()})
    assert cxs[1] - cxs[0] == gen.CHANNEL_SPAN == 140


def test_vertical_pitch_is_28():
    pins = _pins(gen.dip_svg(16))
    left_cx = min(round(cx) for cx, _ in pins.values())
    col = sorted(cy for cx, cy in pins.values() if round(cx) == left_cx)
    for a, b in zip(col, col[1:]):
        assert round(b - a) == gen.PITCH == 28


def test_numbering_matches_layout_convention():
    # pin 1..half = colonne gauche haut->bas ; half+1..N = droite bas->haut
    pins = _pins(gen.dip_svg(6))
    left_cx = min(round(cx) for cx, _ in pins.values())
    assert round(pins[1][0]) == left_cx and round(pins[3][0]) == left_cx
    assert pins[1][1] < pins[3][1]          # 1 au-dessus de 3 (gauche)
    assert round(pins[4][0]) != left_cx     # 4 a droite
    assert pins[4][1] > pins[6][1]          # 4 en bas, 6 en haut (droite)


def test_numbering_n4_smallest_case():
    # n=4 (half=2) : plus petit DIP, garde-fou de generalisation de la formule
    pins = _pins(gen.dip_svg(4))
    left_cx = min(round(cx) for cx, _ in pins.values())
    assert round(pins[1][0]) == left_cx and round(pins[2][0]) == left_cx
    assert pins[1][1] < pins[2][1]          # 1 au-dessus de 2 (gauche)
    assert round(pins[3][0]) != left_cx     # 3 a droite
    assert pins[3][1] > pins[4][1]          # 3 en bas, 4 en haut (droite)


def test_required_ids_present():
    root = ET.fromstring(gen.dip_svg(8))
    assert root.find(".//svg:g[@id='component']", NS) is not None
    assert root.find(".//svg:rect[@id='component-body']", NS) is not None
    name = root.find(".//svg:text[@id='component-name']", NS)
    assert name is not None and name.find("svg:tspan", NS) is not None
    # Also verify pin ids
    assert root.find(".//svg:circle[@id='pin-1-pos']", NS) is not None
    assert root.find(".//svg:circle[@id='pin-8-pos']", NS) is not None
    label = root.find(".//svg:text[@id='pin-1-label']", NS)
    assert label is not None and label.find("svg:tspan", NS) is not None


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  OK {fn.__name__}")
    print(f"\n  {len(fns)} tests verts")


if __name__ == "__main__":
    _run()
