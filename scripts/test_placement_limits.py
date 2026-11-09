"""Limites editoriales du placement : un message NOMME, pas « impossible de
generer le schema » (TODO #124, constat layout.py:1178, 2026-11-07).

Avant : 7 servos ou 17 composants levaient un RuntimeError nu, avale par le
pipeline ; l'eleve lisait « Impossible de générer le schéma pour ce code »
sans savoir ce qui etait de trop ni quoi faire.

Run : python scripts/test_placement_limits.py
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.layout import pipeline
from ui.wiring.instructions import render_instructions

BOARD = "arduino_uno_r3"


def _servos(n: int) -> str:
    return ("#include <Servo.h>\n"
            + "".join(f"Servo s{i};\n" for i in range(n))
            + "void setup(){\n"
            + "".join(f"  s{i}.attach({i + 2});\n" for i in range(n))
            + "}\nvoid loop(){}\n")


def _leds(n: int) -> str:
    pins = list(range(2, 14)) + ["A0", "A1", "A2", "A3", "A4", "A5"]
    return ("void setup(){\n"
            + "".join(f"  pinMode({pins[i]}, OUTPUT);\n" for i in range(n))
            + "}\nvoid loop(){\n"
            + "".join(f"  digitalWrite({pins[i]}, HIGH);\n" for i in range(n))
            + "}\n")


def _render(code: str, lang: str = "fr"):
    nl = pipeline.analyze_netlist(code, BOARD)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        svg, _md, _sc, _w = pipeline.render_netlist_with_meta(
            nl, BOARD, lang=lang)
    return nl, svg


def _limit(nl):
    return [w for w in nl.warnings
            if w.code in pipeline.PLACEMENT_LIMIT_CODES]


def test_seven_servos_are_named_with_count_and_limit():
    nl, svg = _render(_servos(7))
    assert svg == ""
    ws = _limit(nl)
    assert [(w.code, w.params) for w in ws] == \
        [("too_many_servos", {"count": 7, "limit": 6})], ws


def test_the_instructions_explain_the_limit_in_the_chosen_language():
    nl, _svg = _render(_servos(7))
    en = render_instructions(nl, lang="en")
    assert "**7 servos** in this project" in en and "**6 at most**" in en, en
    fr = render_instructions(nl, lang="fr")
    assert "**6 au maximum**" in fr


def test_seventeen_spots_are_too_many_components():
    nl, svg = _render(_leds(17))
    assert svg == ""
    assert [(w.code, w.params) for w in _limit(nl)] == \
        [("too_many_components", {"count": 17, "limit": 16})]


def test_a_render_that_fits_clears_a_stale_limit_warning():
    """Le meme Netlist est rendu plusieurs fois (engrenage, modale) : un
    depassement d'un rendu precedent ne doit pas survivre."""
    nl = pipeline.analyze_netlist(_servos(2), BOARD)
    nl.add_warning(code="too_many_servos", severity="warning", message="x",
                   params={"count": 7, "limit": 6})
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        svg, *_ = pipeline.render_netlist_with_meta(nl, BOARD)
    assert svg, "le rendu de 2 servos devrait reussir"
    assert not _limit(nl)


def test_the_dialog_banner_names_the_limit():
    from ui.wiring.wiring_diagram_dialog import WiringDiagramDialog
    nl, _svg = _render(_servos(7))
    fake = SimpleNamespace(
        _netlist=nl, _instructions_lang=lambda: "en",
        _render_failed_message=lambda: "GENERIC")
    banner = WiringDiagramDialog._render_failed_banner(fake)
    assert banner.startswith("⚠️ 7 servos") and "6 at most" in banner, banner
    fake._netlist = pipeline.analyze_netlist(_servos(1), BOARD)
    assert WiringDiagramDialog._render_failed_banner(fake) == "GENERIC"


def test_every_limit_code_has_text_in_four_languages():
    from ui.wiring.instructions import _WARNING_TEMPLATES
    from ui.wiring.wiring_diagram_dialog import _DIALOG_LABELS
    for code in pipeline.PLACEMENT_LIMIT_CODES:
        for lang in ("fr", "en", "es", "it"):
            assert _WARNING_TEMPLATES[code][lang].strip(), (code, lang)
            assert _DIALOG_LABELS[f"{code}_banner"][lang].strip(), (code, lang)


TESTS = [
    test_seven_servos_are_named_with_count_and_limit,
    test_the_instructions_explain_the_limit_in_the_chosen_language,
    test_seventeen_spots_are_too_many_components,
    test_a_render_that_fits_clears_a_stale_limit_warning,
    test_the_dialog_banner_names_the_limit,
    test_every_limit_code_has_text_in_four_languages,
]


def main() -> int:
    print("[test_placement_limits]\n")
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  [OK] {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
