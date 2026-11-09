"""Audit 2026-11-06 : modale d'ambiguite (ambiguity_dialog) et instructions de
cablage (instructions). Script autonome.

Run : python scripts/test_audit_wiring_ambiguity_instructions.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])
from PyQt6.QtGui import QCursor  # noqa: E402
from PyQt6.QtWidgets import QDialogButtonBox  # noqa: E402
QCursor.setPos(2000, 2000)

import ui.declared_components as declared_components  # noqa: E402
declared_components.set_registry([])

from ui.wiring.netlist import Component, Pin, Netlist  # noqa: E402

_VIVANTS: list = []


# --- 1 : valider le type courant d'un placeholder ne le change pas en LED ----
def _placeholder():
    return Component(
        ref="U1", type="zorglib",
        pins=[Pin("1", ""), Pin("2", ""), Pin("3", ""), Pin("4", "")],
        attributes={"unrecognized": True, "header": "ZorgLib.h"})


def test_validating_an_unknown_type_does_not_make_it_a_led():
    from ui.wiring.ambiguity_dialog import apply_saved_resolution
    c = _placeholder()
    nl = Netlist(board_id="", components=[c])
    apply_saved_resolution(c, "zorglib", nl)
    assert c.type == "zorglib", c.type
    assert c.attributes.get("unrecognized"), c.attributes


# --- 2 : la resistance serie n'est pas decrite « entre D7 et GND » ----------
def _instructions(code: str, prompt: str, lang: str = "fr") -> str:
    from ui.wiring.markers import extract_netlist
    from ui.wiring.inference import apply_rules
    from ui.wiring.instructions import render_instructions
    nl = apply_rules(extract_netlist(code, "uno", prompt=prompt))
    return render_instructions(nl, "simple", lang)


def test_series_resistor_is_not_bridged_through_the_led():
    for lang in ("fr", "en"):
        txt = _instructions(
            "void setup(){pinMode(7, OUTPUT);}\n"
            "void loop(){digitalWrite(7, HIGH);}",
            "une LED sur la broche 7", lang)
        low = txt.lower().replace("*", "")
        assert "entre d7 et gnd" not in low and "between d7 and gnd" not in low, txt
    # le buzzer aussi
    txt = _instructions(
        "void setup(){}\nvoid loop(){tone(8, 440);}",
        "un buzzer sur la broche 8")
    assert "entre d8 et gnd" not in txt.lower().replace("*", ""), txt


# --- 3 : la R serie d'un buzzer (pont sur « + ») est retiree ----------------
def _buzzer_with_r():
    bz = Component(ref="BZ1", type="buzzer",
                   pins=[Pin("+", "NET_A"), Pin("-", "GND")],
                   attributes={"category": "single_output"})
    r = Component(ref="R1", type="resistor", inferred=True,
                  pins=[Pin("A", "D8"), Pin("B", "NET_A")],
                  attributes={"value": "100", "role": "series"})
    nl = Netlist(board_id="", components=[bz, r])
    nl.add_warning(code="buzzer_series_resistor", severity="warning",
                   message="x", refs=["BZ1", "R1"],
                   params={"resistor_ref": "R1"})
    return bz, nl


def test_buzzer_series_resistor_is_dropped_on_requalification():
    from ui.wiring.ambiguity_dialog import apply_saved_resolution
    bz, nl = _buzzer_with_r()
    apply_saved_resolution(bz, "servo", nl)
    assert bz.type == "servo" and bz.pin("SIG").net == "D8"
    assert not [c for c in nl.components if c.type == "resistor"], \
        [(c.ref, [(p.name, p.net) for p in c.pins]) for c in nl.components]
    assert not nl.warnings, nl.warnings


# --- 4 : un choix deja fait mais absent des cards reste visible et validable -
def test_a_remembered_search_only_choice_is_visible_and_valid():
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    c = Component(ref="D1", type="led",
                  pins=[Pin("A", "D7"), Pin("K", "GND")],
                  attributes={"category": "single_output",
                              "_confidence": "low"})
    nl = Netlist(board_id="", components=[c])
    dlg = AmbiguityDialog([c], netlist=nl,
                          initial_choices={"D1": "oled_ssd1306"})
    _VIVANTS.append(dlg)
    picker = dlg._pickers["D1"]
    assert picker.current_type_id() == "oled_ssd1306", picker.current_type_id()
    assert "oled_ssd1306" in picker.visible_type_ids()
    ok = dlg._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok.isEnabled()


TESTS = [
    test_validating_an_unknown_type_does_not_make_it_a_led,
    test_series_resistor_is_not_bridged_through_the_led,
    test_buzzer_series_resistor_is_dropped_on_requalification,
    test_a_remembered_search_only_choice_is_visible_and_valid,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {ascii(e)}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
