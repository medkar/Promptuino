"""Audit 2026-11-06, constats de gravite BASSE de la zone cablage.

Un test (au moins) par constat corrige. Script autonome.

Run : python scripts/test_audit_basses_cablage.py
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

import ui.declared_components as declared_components  # noqa: E402
declared_components.set_registry([])

from ui.i18n import lang_manager  # noqa: E402
from ui.wiring.netlist import Component, Pin, Netlist  # noqa: E402

_VIVANTS: list = []
_LANGS = ("fr", "en", "es", "it")


def _reset_lang():
    lang_manager.set_language("fr")


# --- ambiguity_dialog.py:264 : re-appliquer le MEME type garde la couleur ---
def test_reapplying_led_keeps_the_prompt_colour():
    from ui.wiring.ambiguity_dialog import _to_led, _to_servo
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D7"), Pin("K", "GND")],
                    attributes={"color": "blue", "_confidence": "low"})
    nl = Netlist(board_id="", components=[led])
    _to_led(led, nl)
    assert led.attributes == {"color": "blue"}, led.attributes

    servo = Component(ref="M1", type="servo",
                      pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                            Pin("SIG", "D9")],
                      attributes={"signature_detected": True})
    nl = Netlist(board_id="", components=[servo])
    _to_servo(servo, nl)
    assert servo.attributes.get("signature_detected") is True, servo.attributes


def test_changing_type_still_starts_from_scratch():
    from ui.wiring.ambiguity_dialog import _to_buzzer
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D7"), Pin("K", "GND")],
                    attributes={"color": "blue"})
    nl = Netlist(board_id="", components=[led])
    _to_buzzer(led, nl)
    assert led.type == "buzzer" and led.attributes == {}, led.attributes


# --- ambiguity_dialog.py:1769 : titre de section d'un placeholder ----------
def test_placeholder_section_title_is_the_component_name():
    from PyQt6.QtWidgets import QGroupBox
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    from ui.wiring.instructions import _label
    lang_manager.set_language("fr")
    c = Component(ref="U1", type="zorglib",
                  pins=[Pin("1", ""), Pin("2", ""), Pin("3", ""),
                        Pin("4", "")],
                  attributes={"unrecognized": True, "header": "ZorgLib.h"})
    nl = Netlist(board_id="", components=[c])
    dlg = AmbiguityDialog([c], netlist=nl)
    _VIVANTS.append(dlg)
    sec = dlg._build_classic_section(c)
    _VIVANTS.append(sec)
    title = sec.title()
    assert title.strip() and title == _label("zorglib", "fr"), repr(title)
    _reset_lang()


# --- ambiguity_dialog.py:1787 : un « < » du prompt ne tronque plus ---------
def test_prompt_excerpt_with_less_than_is_not_truncated():
    from PyQt6.QtGui import QTextDocument
    from PyQt6.QtWidgets import QLabel
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    lang_manager.set_language("fr")
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D7"), Pin("K", "GND")],
                    attributes={"_confidence": "low"})
    nl = Netlist(board_id="", components=[led])
    dlg = AmbiguityDialog([led], netlist=nl,
                          prompt="allume la LED sur D7 si temp < 25")
    _VIVANTS.append(dlg)
    rendus = []
    for lab in dlg.findChildren(QLabel):
        doc = QTextDocument()
        doc.setHtml(lab.text())
        rendus.append(doc.toPlainText())
    assert any("< 25" in t for t in rendus), rendus
    _reset_lang()


# --- instructions.py:824 : le bouton cite est celui qui existe -------------
def test_skipped_motors_explainer_names_the_real_button():
    from ui.wiring.instructions import _SECTION_TITLES
    from ui.wiring.wiring_diagram_dialog import _t
    for lang in _LANGS:
        txt = _SECTION_TITLES["skipped_motors_explainer"][lang]
        assert _t("btn_regenerate", lang) in txt, (lang, txt)


# --- instructions.py:1384 : la ligne d'un moteur non cable est traduite ----
def test_skipped_motor_line_follows_the_language():
    from ui.wiring.instructions import render_instructions
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D5"), Pin("K", "GND")])
    nl = Netlist(board_id="", components=[led])
    nl.metadata["_skipped_motors"] = [
        {"ref": "M3", "control_pin": "D9", "aux_dir_pins": ["D7", "D8"]}]
    en = render_instructions(nl, "simple", "en")
    assert "**M3**" in en and "PWM pin `D9`" in en, en
    assert "broche" not in en, en
    fr = render_instructions(nl, "simple", "fr")
    assert "broche PWM `D9`" in fr, fr


# --- instructions.py:1739 : l'explication d'une R depend de son composant --
def _detailed(code: str, prompt: str, lang: str = "en") -> str:
    from ui.wiring.markers import extract_netlist
    from ui.wiring.inference import apply_rules
    from ui.wiring.instructions import render_instructions
    nl = apply_rules(extract_netlist(code, "uno", prompt=prompt))
    return render_instructions(nl, "detailed", lang)


def test_resistor_explanation_matches_its_component():
    from ui.wiring.instructions import _EXPLANATIONS
    led_txt = _EXPLANATIONS["led_series"]["en"]
    btn_txt = _EXPLANATIONS["button_pullup"]["en"]
    # DS18B20 + buzzer : ni texte du bouton, ni texte de la LED.
    txt = _detailed(
        "#include <OneWire.h>\n#include <DallasTemperature.h>\n"
        "OneWire ow(2);\nDallasTemperature s(&ow);\n"
        "void setup(){s.begin();}\n"
        "void loop(){s.requestTemperatures(); tone(8, 440);}",
        "un capteur DS18B20 et un buzzer sur la broche 8")
    # Le cas n'est pas vide : la pull-up et la R serie sont bien la.
    assert "4.7k" in txt.replace("4,7", "4.7") and "100" in txt, txt
    assert btn_txt not in txt, txt
    assert led_txt not in txt, txt
    # La LED garde son explication.
    txt = _detailed("void setup(){pinMode(7, OUTPUT);}\n"
                    "void loop(){digitalWrite(7, HIGH);}",
                    "une LED sur la broche 7")
    assert led_txt in txt, txt


def test_button_pullup_keeps_its_explanation():
    from ui.wiring.instructions import _EXPLANATIONS, _explanation_for
    btn = Component(ref="S1", type="button",
                    pins=[Pin("1", "D2"), Pin("2", "GND")])
    r = Component(ref="R1", type="resistor", inferred=True,
                  pins=[Pin("A", "5V"), Pin("B", "D2")],
                  attributes={"value": "10k", "role": "pullup"})
    ds = Component(ref="U1", type="ds18b20",
                   pins=[Pin("VCC", "5V"), Pin("DATA", "D4"),
                         Pin("GND", "GND")])
    r2 = Component(ref="R2", type="resistor", inferred=True,
                   pins=[Pin("A", "5V"), Pin("B", "D4")],
                   attributes={"value": "4.7k", "role": "pullup"})
    nl = Netlist(board_id="", components=[btn, r, ds, r2])
    assert _explanation_for(r, "fr", nl) == _EXPLANATIONS["button_pullup"]["fr"]
    assert _explanation_for(r2, "fr", nl) == ""


# --- visual_ambiguity_catalog.py:398 : plus de promesse de dégroupement ----
def test_motors_limit_warning_does_not_promise_reclassification():
    from ui.wiring.visual_ambiguity_catalog import DIALOG_LABELS
    entry = DIALOG_LABELS["motors_limit_warning"]
    for lang, mot in (("fr", "reclasser"), ("en", "reclassify"),
                      ("es", "reclasificar"), ("it", "riclassificare")):
        assert mot not in entry[lang], (lang, entry[lang])


# --- visual_ambiguity_catalog.py:545 : singulier pour un seul moteur -------
def test_a_single_motor_title_is_singular():
    from ui.wiring.ambiguity_dialog import _motors_title
    for lang in _LANGS:
        un = _motors_title(1, lang)
        assert un.startswith("1 ") and "moteurs" not in un \
            and "motors" not in un and "motores" not in un \
            and "motori" not in un, (lang, un)
        assert "2" in _motors_title(2, lang)


def test_a_single_motor_consolidated_section_reads_singular():
    from PyQt6.QtWidgets import QGroupBox, QLabel
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    lang_manager.set_language("fr")
    motor = Component(
        ref="D1", type="led",
        pins=[Pin("A", "D9"), Pin("K", "GND")],
        attributes={"_confidence": "low", "_grouped_pwm_pin": "D9",
                    "_grouped_dir_pins": ["D8", "D7"]})
    nl = Netlist(board_id="", components=[motor])
    dlg = AmbiguityDialog([motor], netlist=nl)
    _VIVANTS.append(dlg)
    titres = [g.title() for g in dlg.findChildren(QGroupBox)]
    assert "1 moteur DC détecté" in titres, titres
    textes = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert "1 moteurs" not in textes and "plusieurs groupes" not in textes, \
        textes
    _reset_lang()


# --- implicit_actions.py:290 : les avertissements suivent les actions ------
def _nl_led_button_buzzer():
    from ui.wiring.markers import extract_netlist
    from ui.wiring.inference import apply_rules
    code = ("void setup(){pinMode(7, OUTPUT); pinMode(2, INPUT);}\n"
            "void loop(){digitalWrite(7, digitalRead(2)); tone(8, 440);}")
    return apply_rules(extract_netlist(
        code, "uno",
        prompt="une LED sur la broche 7, un bouton sur la broche 2 et un "
               "buzzer sur la broche 8"))


def test_level3_actions_keep_warnings_in_sync():
    from ui.wiring.implicit_actions import apply_action
    nl = _nl_led_button_buzzer()
    by_type = {c.type: c for c in nl.components}
    assert {"led", "button", "buzzer"} <= set(by_type), sorted(by_type)
    codes = {w.code for w in nl.warnings}
    assert {"led_series_resistor", "button_external_pullup",
            "buzzer_series_resistor"} <= codes, codes
    apply_action(by_type["led"], "led_series_value", nl, value="470")
    apply_action(by_type["button"], "btn_pullup_external", nl)
    apply_action(by_type["buzzer"], "buzzer_series_value", nl, value="none")
    led_w = [w for w in nl.warnings if w.code == "led_series_resistor"]
    assert led_w and all(w.params["value"] == "470" for w in led_w), led_w
    restants = {w.code for w in nl.warnings}
    assert "button_external_pullup" not in restants, restants
    assert "buzzer_series_resistor" not in restants, restants


# --- markers.py:2248 : un en-tete de donnees ne nomme pas le module serie --
def test_pitches_header_does_not_name_the_serial_module():
    from ui.wiring.markers import extract_netlist
    code = ('#include <SoftwareSerial.h>\n#include "pitches.h"\n'
            "SoftwareSerial bt(10, 11);\n"
            "void setup(){bt.begin(9600);}\n"
            "void loop(){tone(8, NOTE_C4);}")
    nl = extract_netlist(code, "uno", prompt="")
    types_ = [c.type for c in nl.components]
    assert "pitches" not in types_, types_
    assert "uart_module" in types_, types_


# --- wiring_diagram_dialog.py:3606 : broches Mega / Nano reconnues ---------
def test_board_pin_nets_cover_mega_and_nano():
    from ui.wiring.wiring_diagram_dialog import SchemaView
    nets = SchemaView._extract_board_pin_nets(None)
    for pin in ("D13", "D22", "D53", "A5", "A6", "A7", "A15", "GND"):
        assert pin in nets, pin


# --- wiring_diagram_dialog.py:4797 / 4817 : copie --------------------------
def _fake_dialog(render, lang="en"):
    from PyQt6.QtWidgets import QPushButton
    from ui.wiring.wiring_diagram_dialog import _t
    btn = QPushButton(_t("btn_copy", lang))
    _VIVANTS.append(btn)
    return types.SimpleNamespace(
        _svg_str="<svg/>", _btn_copy=btn,
        _instructions_lang=lambda: lang,
        _render_png_image=render)


def test_copy_failure_is_reported_in_the_ui_language():
    import ui.wiring.wiring_diagram_dialog as wdd
    vus = []
    orig = wdd.QMessageBox.warning
    wdd.QMessageBox.warning = staticmethod(
        lambda parent, title, body, *a, **k: vus.append((title, body)))
    try:
        def boom(scale=2.0):
            raise RuntimeError(wdd._t("export_svg_invalid", "en"))
        wdd.WiringDiagramDialog._copy_png(_fake_dialog(boom))
    finally:
        wdd.QMessageBox.warning = orig
    assert vus, "l'echec de la copie doit etre dit"
    title, body = vus[0]
    assert title == wdd._t("copy_failed_title", "en"), title
    assert "invalide" not in body and "could not be read" in body, body
    for cle in ("export_write_failed", "export_svg_invalid",
                "copy_failed_title", "copy_failed_body"):
        assert len({wdd._t(cle, l) for l in _LANGS}) == 4, cle


def test_double_copy_click_restores_the_canonical_label():
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtGui import QImage
    import ui.wiring.wiring_diagram_dialog as wdd

    def img(scale=2.0):
        im = QImage(4, 4, QImage.Format.Format_ARGB32)
        im.fill(0)
        return im
    fake = _fake_dialog(img)
    wdd.WiringDiagramDialog._copy_png(fake)
    loop = QEventLoop()
    QTimer.singleShot(400, loop.quit)
    loop.exec()
    wdd.WiringDiagramDialog._copy_png(fake)
    QTimer.singleShot(1700, loop.quit)
    loop.exec()
    assert fake._btn_copy.text() == wdd._t("btn_copy", "en"), \
        fake._btn_copy.text()


# --- svg_component_loader.py:233 : nom d'un asset sans tspan ---------------
def test_set_name_without_tspan_replaces_the_text():
    from ui.wiring.layout.svg_component_loader import ComponentSVGLoader
    path = ROOT / "assets/wiring/components/external/battery.svg"
    loader = ComponentSVGLoader(path)
    loader.set_name("BAT")
    out = loader.render(translate=(0, 0), instance_id="c0")
    assert ">BAT<" in out and ">Battery<" not in out, out[:400]


# --- router.py:506 : le code mort a disparu --------------------------------
def test_dead_battery_helpers_are_gone():
    import ui.wiring.routing.router as router
    assert not hasattr(router, "_external_battery_plus_info")
    assert not hasattr(router, "_external_battery_gnd_info")
    assert hasattr(router, "_external_batteries_info")


# --- zone_editor/editor_widget.py:305 : la taille de cellule est enregistree
def test_cell_size_change_marks_the_store_dirty_and_reload_rebuilds():
    from ui.wiring.routing.zone_editor.editor_widget import ZoneEditorView
    from ui.wiring.routing.zone_editor.zone_store import ZoneStore
    store = ZoneStore()
    view = ZoneEditorView(ROOT / store.bb_svg, store)
    _VIVANTS.append(view)
    assert not store.is_dirty()
    view.set_cell_size(store.cell_size + 2)
    assert store.is_dirty(), "changer la taille doit proposer d'enregistrer"
    # Rechargement : le store remplace porte deja une autre taille.
    neuf = ZoneStore(cell_size=store.cell_size + 3)
    view.store = neuf
    view.set_cell_size(neuf.cell_size)
    assert view._grid_cell_size == neuf.cell_size, view._grid_cell_size
    assert not neuf.is_dirty()


TESTS = [
    test_reapplying_led_keeps_the_prompt_colour,
    test_changing_type_still_starts_from_scratch,
    test_placeholder_section_title_is_the_component_name,
    test_prompt_excerpt_with_less_than_is_not_truncated,
    test_skipped_motors_explainer_names_the_real_button,
    test_skipped_motor_line_follows_the_language,
    test_resistor_explanation_matches_its_component,
    test_button_pullup_keeps_its_explanation,
    test_motors_limit_warning_does_not_promise_reclassification,
    test_a_single_motor_title_is_singular,
    test_a_single_motor_consolidated_section_reads_singular,
    test_level3_actions_keep_warnings_in_sync,
    test_pitches_header_does_not_name_the_serial_module,
    test_board_pin_nets_cover_mega_and_nano,
    test_copy_failure_is_reported_in_the_ui_language,
    test_double_copy_click_restores_the_canonical_label,
    test_set_name_without_tspan_replaces_the_text,
    test_dead_battery_helpers_are_gone,
    test_cell_size_change_marks_the_store_dirty_and_reload_rebuilds,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  ok  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {t.__name__}: {type(e).__name__}: {e}")
    _reset_lang()
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
