"""Garde format/geometrie du generateur single-row procedural (TODO #58)."""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gen_single_row_svgs as gen

NS = {"svg": "http://www.w3.org/2000/svg"}

# Les comptes IMPAIRS ajoutes par #58. Les pairs 2-8 sont couverts par la
# meme geometrie depuis toujours ; ce sont les nouveaux qu'on garde.
COUNTS = (9, 11, 13)


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


def test_pin_count_matches_request():
    for n in COUNTS:
        pins = _pins(gen.single_row_svg(n))
        assert len(pins) == n, (n, len(pins))


def test_single_column():
    """Rangee SIMPLE : tous les cx identiques. Si deux colonnes
    apparaissaient, l'asset serait un DIP deguise et le routeur placerait
    les fils du mauvais cote."""
    for n in COUNTS:
        pins = _pins(gen.single_row_svg(n))
        cxs = {round(cx, 3) for cx, _ in pins.values()}
        assert cxs == {float(gen.PIN_CX)}, (n, cxs)


def test_vertical_pitch_is_28():
    """Le pas DOIT rester celui des trous du breadboard : un ecart ici
    desaligne toutes les broches."""
    for n in COUNTS:
        pins = _pins(gen.single_row_svg(n))
        cys = [cy for _, cy in (pins[i] for i in sorted(pins))]
        gaps = {round(b - a, 3) for a, b in zip(cys, cys[1:])}
        assert gaps == {float(gen.PITCH)}, (n, gaps)


def test_required_ids_present():
    """Ids exiges par svg_component_loader.py."""
    for n in COUNTS:
        root = ET.fromstring(gen.single_row_svg(n))
        assert root.find(".//svg:g[@id='component']", NS) is not None, n
        assert root.find(".//svg:rect[@id='component-body']", NS) is not None, n
        name = root.find(".//svg:text[@id='component-name']", NS)
        assert name is not None and name.find("svg:tspan", NS) is not None, n
        for idx in (1, n):
            assert root.find(f".//svg:circle[@id='pin-{idx}-pos']", NS) is not None
            lbl = root.find(f".//svg:text[@id='pin-{idx}-label']", NS)
            assert lbl is not None and lbl.find("svg:tspan", NS) is not None


def test_generated_assets_exist_on_disk():
    """Le generateur a bien ete EXECUTE, pas seulement modifie."""
    for n in COUNTS:
        p = (ROOT / "assets" / "wiring" / "components"
             / "single-row" / f"{n}pins.svg")
        assert p.exists(), p


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  OK {fn.__name__}")
    print(f"\n  {len(fns)} tests verts")


if __name__ == "__main__":
    _run()
