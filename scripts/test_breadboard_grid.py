"""Gardes grid-consistency de la breadboard regridee (#1)."""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules.setdefault("ui", ui_pkg)

from ui.wiring.layout.breadboard_generator import (
    Breadboard, PITCH, _COL_OFFSETS, BODY_W,
)


def test_central_sillon_is_three_pitches():
    assert _COL_OFFSETS["f"] - _COL_OFFSETS["e"] == 3 * PITCH  # 84 px = 0,3"


def test_intra_group_offsets_are_integer_pitch():
    for group in (["a", "b", "c", "d", "e"], ["f", "g", "h", "i", "j"]):
        offs = [_COL_OFFSETS[c] for c in group]
        for a, b in zip(offs, offs[1:]):
            assert (b - a) == PITCH


def test_body_width_recomputed():
    assert BODY_W == 498


def test_hole_positions_e_f_84px_apart():
    bb = Breadboard(rows=30)
    ex, _ = bb.hole_position("e", 10)
    fx, _ = bb.hole_position("f", 10)
    assert round(fx - ex) == 84


def test_dip_pins_land_on_holes():
    """Chaque broche d'un DIP on-BB coincide avec un trou — miroir ET non-miroir.

    Netlist : 1 servo + 1 sr74hc595 (DIP non-I2C) + 1 pcf8574 (DIP I2C) + 6 LEDs.
    Le placement cree 2 breadboards :
      BB0 (mirrored=True)  : servo + sr74hc595 + LEDs
      BB1 (mirrored=False) : pcf8574 (I2C groupe sur la BB droite)
    Les deux orientations de DIP sont ainsi exercees dans la meme passe.
    """
    from ui.wiring.layout.layout import place_scene
    from ui.wiring.layout.renderer import SceneRenderer

    board_svg = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
    netlist = [
        # Servo : force le split 2-BB (servos sur BB0, I2C sur BB1)
        {"ref": "SRV1", "type": "servo",
         "pins": [{"name": "SIG", "net": "D9"}, {"name": "VCC", "net": "5V"},
                  {"name": "GND", "net": "GND"}]},
        # DIP non-I2C -> "other" -> BB0 (mirrored=True)
        {"ref": "U_SHIFT", "type": "sr74hc595",
         "pins": [{"name": "VCC", "net": "5V"}, {"name": "GND", "net": "GND"},
                  {"name": "DATA", "net": "D11"}, {"name": "CLK", "net": "D13"},
                  {"name": "LATCH", "net": "D10"}]},
        # DIP I2C -> bb1_required -> BB1 (mirrored=False)
        {"ref": "U_IO", "type": "pcf8574",
         "pins": [{"name": "VCC", "net": "5V"}, {"name": "GND", "net": "GND"},
                  {"name": "SDA", "net": "A4"}, {"name": "SCL", "net": "A5"}]},
        # LEDs de remplissage (trigger depassement cap BB0 -> 2 BBs)
        {"ref": "D1", "type": "led", "pins": [{"name": "A", "net": "D2"}, {"name": "K", "net": "GND"}]},
        {"ref": "D2", "type": "led", "pins": [{"name": "A", "net": "D3"}, {"name": "K", "net": "GND"}]},
        {"ref": "D3", "type": "led", "pins": [{"name": "A", "net": "D4"}, {"name": "K", "net": "GND"}]},
        {"ref": "D4", "type": "led", "pins": [{"name": "A", "net": "D5"}, {"name": "K", "net": "GND"}]},
        {"ref": "D5", "type": "led", "pins": [{"name": "A", "net": "D6"}, {"name": "K", "net": "GND"}]},
        {"ref": "D6", "type": "led", "pins": [{"name": "A", "net": "D7"}, {"name": "K", "net": "GND"}]},
    ]
    scene = place_scene(netlist, board_svg)
    renderer = SceneRenderer(scene, [])

    dips = [p for p in scene.placed_components
            if p.breadboard_idx >= 0
            and getattr(p.catalog_entry, "is_dip", False)]
    assert dips, "aucun DIP place sur breadboard"

    # Assertion de couverture : les deux orientations doivent etre exercees
    mirrored_seen = {p.mirrored for p in dips}
    assert True in mirrored_seen, "aucun DIP mirrored=True — cas miroir non couvert"
    assert False in mirrored_seen, "aucun DIP mirrored=False — cas non-miroir non couvert"

    for placed in dips:
        loader = renderer._loader_for(placed)
        tx, ty = renderer._compute_component_translate(placed)
        # Les composants miroir sont rendus avec scale(-1, 1) autour de x=0
        # dans le referentiel local, puis translate(tx, ty). La position
        # canvas reelle de pin.cx local est donc tx - cx (et non tx + cx).
        x_sign = -1 if placed.mirrored else 1
        pin_local = loader.pin_positions()   # positions locales (avant translate)
        pin_canvas = {
            n: (tx + x_sign * cx, ty + cy)
            for n, (cx, cy) in pin_local.items()
        }
        bb = scene.breadboards[placed.breadboard_idx]
        bbtx, bbty = scene.breadboard_translates[placed.breadboard_idx]
        for pin_idx, (col, row) in placed.pin_to_hole.items():
            hx, hy = bb.hole_position(col, row)
            hx += bbtx; hy += bbty
            px, py = pin_canvas[pin_idx]
            assert abs(px - hx) <= 1 and abs(py - hy) <= 1, (
                f"{placed.component_ref} pin {pin_idx} "
                f"(mirrored={placed.mirrored}) a ({px:.1f},{py:.1f}) "
                f"vs trou ({hx:.1f},{hy:.1f})")


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  OK {fn.__name__}")
    print(f"\n  {len(fns)} tests verts")


if __name__ == "__main__":
    _run()
