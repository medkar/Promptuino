"""Audit 2026-11-06 -- zone wiring/routing : rail V+ partage 3V3/5V, broche
nommee SDA sur un net SPI, echec d'A* signale.

Run: python scripts/test_audit_wiring_routing.py
"""
from __future__ import annotations
import contextlib
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

import ui.declared_components as declared_components  # noqa: E402
declared_components.set_registry([])

from ui.wiring import inference  # noqa: E402
from ui.wiring.markers import extract_netlist  # noqa: E402
from ui.wiring.layout.layout import place_scene  # noqa: E402
from ui.wiring.routing.router import route_wires  # noqa: E402

BOARD = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"

CODE_RFID_SERVO = """#include <SPI.h>
#include <MFRC522.h>
#include <Servo.h>
MFRC522 r(10,9);
Servo s;
void setup(){ SPI.begin(); r.PCD_Init(); s.attach(6);}
void loop(){}
"""


def _route(code: str):
    nl = extract_netlist(code, "arduino_uno_r3", prompt="", context="")
    inference.apply_rules(nl)
    comps = [{"ref": c.ref, "type": c.type,
              "pins": [{"name": p.name, "net": p.net} for p in c.pins],
              "attributes": dict(c.attributes)} for c in nl.components]
    scene = place_scene(comps, BOARD)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wires = route_wires(scene, comps)
    return scene, comps, wires, buf.getvalue()


def test_3v3_and_5v_never_share_a_rail_hole():
    """Constat 1 : 5V et 3V3 sur le MEME rail V+ = court-circuit du 3,3 V."""
    scene, _c, wires, log = _route(CODE_RFID_SERVO)
    ends = {}
    for w in wires:
        if w.net in ("5V", "3V3"):
            ends.setdefault(w.net, set()).add(tuple(w.path[-1]))
    assert ends.get("3V3") and ends.get("5V"), ends
    first = {n: next(w for w in wires if w.net == n).path[-1]
             for n in ("5V", "3V3")}
    assert first["5V"] != first["3V3"], first
    assert "FAIL] 5V" not in log, log


def test_a_pin_named_SDA_on_an_spi_net_is_not_wired_as_i2c():
    """Constat 2 : le SS du MFRC522 s'appelle SDA sur la carte mais va sur
    D10 : le fil doit partir de D10, pas de la broche I2C."""
    scene, _c, wires, _log = _route(CODE_RFID_SERVO)
    d10 = [w for w in wires if w.net == "D10"]
    assert d10, "aucun fil pour le net D10"
    want = scene.board_loader.pin_position("D10", scene.board_translate)
    sda = scene.board_loader.pin_position("SDA", scene.board_translate)
    start = tuple(d10[0].path[0])
    assert start == tuple(want), (start, want)
    assert start != tuple(sda), (start, sda)


def test_a_failed_astar_is_reported_not_silently_dropped():
    """Constat 5 : un echec d'A* n'etait qu'un print sur stdout ; le schema
    s'affichait avec des fils en moins, presente comme complet."""
    from ui.wiring.routing import router
    from ui.wiring.layout import pipeline
    from ui.wiring.instructions import render_instructions
    nl = extract_netlist(CODE_RFID_SERVO, "arduino_uno_r3", prompt="", context="")
    inference.apply_rules(nl)
    real = router.astar
    router.astar = lambda *a, **k: None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            _svg, _md, scene, _w = pipeline.render_netlist_with_meta(
                nl, "arduino_uno_r3", "light", "simple", "fr")
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline.render_netlist_with_meta(
                nl, "arduino_uno_r3", "light", "simple", "fr")
    finally:
        router.astar = real
    assert scene is not None and scene.routing_failures, "echec non remonte"
    ws = [w for w in nl.warnings if w.code == "unrouted_wires"]
    assert len(ws) == 1, "un rendu repete ne doit pas empiler l'avertissement"
    for lang in ("fr", "en", "es", "it"):
        md = render_instructions(nl, lang=lang)
        assert ws[0].params["nets"].split(",")[0].strip() in md, (lang, md[:300])
    # Et un rendu qui reussit retire l'avertissement perime.
    with contextlib.redirect_stdout(io.StringIO()):
        pipeline.render_netlist_with_meta(
            nl, "arduino_uno_r3", "light", "simple", "fr")
    assert not [w for w in nl.warnings if w.code == "unrouted_wires"]


TESTS = [
    test_a_failed_astar_is_reported_not_silently_dropped,
    test_3v3_and_5v_never_share_a_rail_hole,
    test_a_pin_named_SDA_on_an_spi_net_is_not_wired_as_i2c,
]


def main() -> None:
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc!r}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
