"""Tests feature 'composants a la volee' : INA219 dedie + fallback I2C generique.

Runner standalone (pas pytest) : python scripts/test_wiring_on_the_fly_components.py
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

from ui.wiring.markers import _detect_libraries


def _by_type(components, ctype):
    return [c for c in components if c.type == ctype]


def _pin_net(comp, pin_name):
    for p in comp.pins:
        if p.name == pin_name:
            return p.net
    return None


INA219_CODE = """
#include <Wire.h>
#include <Adafruit_INA219.h>
Adafruit_INA219 ina219(0x41);
void setup() { ina219.begin(); }
void loop() {}
"""

INA219_CODE_NOADDR = """
#include <Wire.h>
#include <Adafruit_INA219.h>
Adafruit_INA219 ina219;
void setup() { ina219.begin(); }
void loop() {}
"""


def test_ina219_detected():
    comps, _claimed = _detect_libraries(INA219_CODE)
    found = _by_type(comps, "ina219")
    assert len(found) == 1, f"attendu 1 ina219, recu {len(found)} ({[c.type for c in comps]})"
    c = found[0]
    assert len(c.pins) == 6, f"attendu 6 pins, recu {len(c.pins)}"
    assert _pin_net(c, "SDA") == "A4", _pin_net(c, "SDA")
    assert _pin_net(c, "SCL") == "A5", _pin_net(c, "SCL")
    assert _pin_net(c, "VCC") == "5V"
    assert _pin_net(c, "GND") == "GND"
    assert _pin_net(c, "VIN+") == ""
    assert _pin_net(c, "VIN-") == ""
    assert c.attributes.get("address") == "0x41", c.attributes
    print("  [OK] INA219 detecte (6 pins, A4/A5, addr 0x41)")


def test_ina219_address_default():
    comps, _ = _detect_libraries(INA219_CODE_NOADDR)
    c = _by_type(comps, "ina219")[0]
    assert c.attributes.get("address") == "0x40", c.attributes
    print("  [OK] INA219 adresse defaut 0x40")


FASTLED_WS2812_CODE = """
#include <FastLED.h>
#define NUM_LEDS 30
CRGB leds[NUM_LEDS];
void setup() { FastLED.addLeds<WS2812, 6, GRB>(leds, NUM_LEDS); }
void loop() {}
"""

FASTLED_WS2812B_CODE = """
#include <FastLED.h>
CRGB leds[10];
void setup() { FastLED.addLeds<WS2812B, 5>(leds, 10); }
void loop() {}
"""

FASTLED_CONST_PIN_CODE = """
#include <FastLED.h>
#define LED_PIN 6
CRGB leds[8];
void setup() { FastLED.addLeds<WS2812, LED_PIN>(leds, 8); }
void loop() {}
"""

FASTLED_APA102_CODE = """
#include <FastLED.h>
CRGB leds[8];
void setup() { FastLED.addLeds<APA102, 11, 13>(leds, 8); }
void loop() {}
"""


def test_fastled_ws2812_detected():
    comps, _ = _detect_libraries(FASTLED_WS2812_CODE)
    strip = _by_type(comps, "neopixel")
    assert len(strip) == 1, f"attendu 1 neopixel, recu {[c.type for c in comps]}"
    c = strip[0]
    assert _pin_net(c, "DIN") == "D6", _pin_net(c, "DIN")
    assert _pin_net(c, "VCC") == "5V"
    assert _pin_net(c, "GND") == "GND"
    assert not [x for x in comps if x.attributes.get("unrecognized")], \
        "aucun placeholder attendu"
    print("  [OK] FastLED WS2812 -> neopixel DIN=D6, pas de placeholder")


def test_fastled_ws2812b_detected():
    comps, _ = _detect_libraries(FASTLED_WS2812B_CODE)
    c = _by_type(comps, "neopixel")[0]
    assert _pin_net(c, "DIN") == "D5", _pin_net(c, "DIN")
    print("  [OK] FastLED WS2812B -> neopixel DIN=D5")


def test_fastled_const_pin_resolved():
    from ui.wiring.markers import _resolve_aliases
    comps, _ = _detect_libraries(_resolve_aliases(FASTLED_CONST_PIN_CODE))
    c = _by_type(comps, "neopixel")[0]
    assert _pin_net(c, "DIN") == "D6", _pin_net(c, "DIN")
    print("  [OK] FastLED #define LED_PIN 6 resolu -> DIN=D6")


def test_fastled_apa102_falls_to_placeholder():
    comps, _ = _detect_libraries(FASTLED_APA102_CODE)
    assert not _by_type(comps, "neopixel"), "APA102 ne doit PAS etre un neopixel"
    ph = [c for c in comps if c.attributes.get("unrecognized")]
    assert len(ph) == 1 and ph[0].type == "fastled", [c.type for c in comps]
    print("  [OK] FastLED APA102 (2 fils) -> placeholder, pas de neopixel")


def test_neopixel_label_broadened():
    from ui.wiring.instructions import _label
    assert "WS2812" in _label("neopixel", "fr"), _label("neopixel", "fr")
    assert "WS2812" in _label("neopixel", "en"), _label("neopixel", "en")
    print("  [OK] label neopixel elargi (mentionne WS2812)")


GENERIC_I2C_CODE = """
#include <Wire.h>
#include <Adafruit_ADS1015.h>
Adafruit_ADS1015 ads;
void setup() { Wire.begin(); ads.begin(); }
void loop() {}
"""

OLED_CODE = """
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
Adafruit_SSD1306 display(128, 64, &Wire, -1);
void setup() { display.begin(SSD1306_SWITCHCAPVCC, 0x3C); }
void loop() {}
"""

UNKNOWN_NO_I2C_CODE = """
#include <FastLED.h>
void setup() {}
void loop() {}
"""


def test_generic_i2c_unknown_lib():
    comps, _ = _detect_libraries(GENERIC_I2C_CODE)
    found = _by_type(comps, "ads1015")
    assert len(found) == 1, f"attendu 1 module ads1015, recu {[c.type for c in comps]}"
    c = found[0]
    assert len(c.pins) == 4, f"attendu 4 pins, recu {len(c.pins)}"
    assert _pin_net(c, "SDA") == "A4"
    assert _pin_net(c, "SCL") == "A5"
    assert _pin_net(c, "VCC") == "5V"
    assert _pin_net(c, "GND") == "GND"
    print("  [OK] module I2C generique 'ads1015' (4 pins)")


def test_generic_no_double_emit_oled():
    comps, _ = _detect_libraries(OLED_CODE)
    assert len(_by_type(comps, "oled_ssd1306")) == 1, "OLED non detecte"
    types_ = sorted(c.type for c in comps)
    assert types_ == ["oled_ssd1306"], f"types parasites : {types_}"
    print("  [OK] OLED : pas de doublon generique")


def test_generic_skips_ina219():
    comps, _ = _detect_libraries(INA219_CODE)
    assert len(_by_type(comps, "ina219")) == 1
    assert sorted(c.type for c in comps) == ["ina219"], [c.type for c in comps]
    print("  [OK] INA219 : signature dediee, pas de doublon generique")


def test_unknown_no_i2c_placeholder():
    # #include inconnu SANS Wire -> placeholder non cable (nouveau comportement,
    # remplace l'ancien test qui attendait []).
    comps, _ = _detect_libraries(UNKNOWN_NO_I2C_CODE)
    ph = [c for c in comps if c.attributes.get("unrecognized")]
    assert len(ph) == 1, f"attendu 1 placeholder, recu {[c.type for c in comps]}"
    c = ph[0]
    assert c.type == "fastled", c.type
    assert all(p.net == "" for p in c.pins), [(p.name, p.net) for p in c.pins]
    assert c.attributes.get("header") == "FastLED.h", c.attributes
    print("  [OK] #include inconnu sans Wire -> placeholder non cable")


def test_placeholder_pin_count():
    from ui.wiring.markers import _PLACEHOLDER_PIN_COUNT
    comps, _ = _detect_libraries(UNKNOWN_NO_I2C_CODE)
    c = [c for c in comps if c.attributes.get("unrecognized")][0]
    assert len(c.pins) == _PLACEHOLDER_PIN_COUNT, len(c.pins)
    print(f"  [OK] placeholder a {_PLACEHOLDER_PIN_COUNT} broches")


def test_multi_unknown_placeholders():
    code = """
#include <FastLED.h>
#include <CustomThing.h>
void setup() {}
void loop() {}
"""
    comps, _ = _detect_libraries(code)
    ph = sorted(c.type for c in comps if c.attributes.get("unrecognized"))
    assert ph == ["customthing", "fastled"], ph
    print("  [OK] 2 includes inconnus -> 2 placeholders distincts")


def test_core_headers_no_placeholder():
    code = """
#include <SPI.h>
#include <math.h>
#include <Arduino.h>
void setup() {}
void loop() {}
"""
    comps, _ = _detect_libraries(code)
    assert comps == [], f"aucun placeholder pour les libs coeur, recu {[c.type for c in comps]}"
    print("  [OK] libs coeur -> aucun placeholder")


def test_i2c_unknown_lib_not_placeholder():
    # Non-regression : un include I2C inconnu (avec Wire) reste un module I2C
    # CABLE, PAS un placeholder nu.
    comps, _ = _detect_libraries(GENERIC_I2C_CODE)
    c = _by_type(comps, "ads1015")[0]
    assert not c.attributes.get("unrecognized"), "ne doit PAS etre un placeholder"
    assert _pin_net(c, "SDA") == "A4" and _pin_net(c, "SCL") == "A5"
    print("  [OK] include I2C inconnu -> module cable, pas placeholder")


def test_two_unknown_i2c():
    """Deux libs I2C inconnues distinctes -> deux modules distincts, chacun
    nomme d'apres sa lib (precedence + dedup ne fusionnent pas des libs
    differentes)."""
    code = """
#include <Wire.h>
#include <Adafruit_ADS1015.h>
#include <SparkFun_VL53L1X.h>
Adafruit_ADS1015 ads;
SFEVL53L1X dist;
void setup() { Wire.begin(); ads.begin(); dist.begin(); }
void loop() {}
"""
    comps, _ = _detect_libraries(code)
    assert len(_by_type(comps, "ads1015")) == 1, [c.type for c in comps]
    assert len(_by_type(comps, "vl53l1x")) == 1, [c.type for c in comps]
    print("  [OK] 2 modules I2C inconnus distincts (ads1015 + vl53l1x)")


def test_ina219_instruction_label():
    from ui.wiring.instructions import _label
    assert _label("ina219", "fr") == "capteur de courant INA219", _label("ina219", "fr")
    assert _label("ina219", "en") == "INA219 current sensor", _label("ina219", "en")
    print("  [OK] label instructions INA219")


def test_render_ina219_scene():
    from PyQt6.QtWidgets import QApplication
    from ui.wiring.netlist import Netlist, Component, Pin
    from ui.wiring.layout.pipeline import render_netlist_with_meta
    _app = QApplication.instance() or QApplication([])
    nl = Netlist(
        board_id="arduino_uno_r3",
        components=[
            Component(ref="U1", type="ina219",
                      pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                            Pin("SDA", "A4"), Pin("SCL", "A5"),
                            Pin("VIN+", ""), Pin("VIN-", "")]),
        ],
    )
    svg, _md, scene, _wires = render_netlist_with_meta(
        nl, "arduino_uno_r3", theme="light", mode="simple", lang="fr")
    assert svg, "svg vide"
    assert any(pc.component_ref == "U1" for pc in scene.placed_components), \
        "INA219 absent de la scene placee"
    print(f"  [OK] rendu INA219 : scene={len(scene.placed_components)} comp")


def test_placeholder_warning_emitted():
    from ui.wiring.markers import extract_netlist
    nl = extract_netlist(UNKNOWN_NO_I2C_CODE, "arduino_uno_r3")
    codes = [w.code for w in nl.warnings]
    assert "unwired_unknown_component" in codes, codes
    w = next(w for w in nl.warnings if w.code == "unwired_unknown_component")
    assert w.params.get("name"), w.params
    print("  [OK] warning unwired_unknown_component emis avec params.name")


def test_placeholder_warning_i18n_all_langs():
    from ui.wiring.instructions import _WARNING_TEMPLATES
    t = _WARNING_TEMPLATES["unwired_unknown_component"]
    for lang in ("fr", "en", "es", "it"):
        assert "{name}" in t[lang], f"{lang}: {t.get(lang)!r}"
    print("  [OK] template warning i18n present (4 langues, {name})")


def test_render_placeholder_scene():
    from PyQt6.QtWidgets import QApplication
    from ui.wiring.netlist import Netlist, Component, Pin
    from ui.wiring.layout.pipeline import render_netlist_with_meta
    _app = QApplication.instance() or QApplication([])
    nl = Netlist(
        board_id="arduino_uno_r3",
        components=[
            Component(ref="U1", type="fastled",
                      pins=[Pin("1", ""), Pin("2", ""), Pin("3", ""), Pin("4", "")],
                      attributes={"unrecognized": True, "header": "FastLED.h"}),
        ],
    )
    svg, _md, scene, wires = render_netlist_with_meta(
        nl, "arduino_uno_r3", theme="light", mode="simple", lang="fr")
    assert svg, "svg vide"
    assert any(pc.component_ref == "U1" for pc in scene.placed_components), \
        "placeholder absent de la scene"
    assert not wires, f"aucun fil attendu (nets vides), recu {len(wires)}"
    print(f"  [OK] placeholder rendu (scene={len(scene.placed_components)} comp, 0 fil)")


def test_placeholder_gets_attention_icon():
    from PyQt6.QtWidgets import QApplication
    from ui.wiring.netlist import Netlist, Component, Pin
    from ui.wiring.wiring_diagram_dialog import WiringDiagramDialog
    _app = QApplication.instance() or QApplication([])
    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="U1", type="fastled",
                  pins=[Pin("1", ""), Pin("2", ""), Pin("3", ""), Pin("4", "")],
                  attributes={"unrecognized": True, "header": "FastLED.h"}),
        Component(ref="D1", type="led", pins=[Pin("A", "D8"), Pin("K", "GND")]),
    ])
    # Bypass du constructeur lourd : _compute_info_refs ne lit que _netlist.
    dlg = WiringDiagramDialog.__new__(WiringDiagramDialog)
    dlg._netlist = nl
    refs = dlg._compute_info_refs()
    assert "U1" in refs, refs       # placeholder -> icone attention
    assert "D1" not in refs, refs   # LED normale -> pas d'icone
    print("  [OK] placeholder recoit l'icone attention (LED non)")


def test_attention_tooltip_has_a_title_and_wraps():
    """QA E2 (2026-08-08) : l'avertissement s'etalait sur UNE ligne qui
    debordait de l'ecran, et rien ne disait de quoi il s'agissait."""
    from PyQt6.QtWidgets import QApplication
    from ui.wiring.netlist import Netlist, Component, Pin, Warning_
    from ui.wiring.wiring_diagram_dialog import (WiringDiagramDialog,
                                                 _TOOLTIP_WRAP_CHARS)
    _app = QApplication.instance() or QApplication([])
    nl = Netlist(board_id="arduino_uno_r3", components=[
        Component(ref="U1", type="module_generic",
                  pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                        Pin("SDA", "A4"), Pin("SCL", "A5")],
                  attributes={"presumed_wiring": True,
                              "header": "LibInconnue.h"}),
    ])
    nl.warnings = [Warning_(code="presumed_i2c_wiring", severity="warning",
                            message="cablage presume", params={"name": "U1"},
                            refs=["U1"])]
    dlg = WiringDiagramDialog.__new__(WiringDiagramDialog)
    dlg._netlist = nl
    tip = dlg._compute_info_tooltips({"U1"})["U1"]
    assert "<b>" in tip and "</b>" in tip, tip       # titre en evidence
    assert "Câblage présumé" in tip, tip             # ... et le BON titre
    assert "**" not in tip, tip                      # gras markdown retire
    # Le texte est REPLIE : aucune ligne ne depasse le budget, et il y en a
    # plus d'une (sinon on n'aurait rien corrige).
    body = tip.split("</b><br>", 1)[1]
    lines = body.split("<br>")
    assert len(lines) > 1, tip
    assert max(len(l) for l in lines) <= _TOOLTIP_WRAP_CHARS + 10, lines
    print("  [OK] infobulle : titre en gras + texte replie")


def test_attention_tooltip_titles_do_not_lie():
    """« Composant non reconnu » ne doit PAS coiffer une broche analogique
    nue : le composant y est reconnu, c'est le cablage qui est presume."""
    from ui.wiring.wiring_diagram_dialog import _INFO_TITLE_BY_CODE, _t
    assert _INFO_TITLE_BY_CODE["unwired_unknown_component"] == \
        "info_title_unrecognized"
    assert _INFO_TITLE_BY_CODE["presumed_analog_component"] == \
        "info_title_presumed"
    for key in ("info_title_unrecognized", "info_title_presumed",
                "info_title_generic"):
        for lang in ("fr", "en", "es", "it"):
            assert _t(key, lang) and _t(key, lang) != key, f"{key}/{lang}"
    print("  [OK] un titre par cas, traduit en 4 langues")


def test_tooltip_html_escapes_its_input():
    from ui.wiring.wiring_diagram_dialog import _tooltip_html
    out = _tooltip_html("A & B", "pin <SDA> & <SCL>")
    assert "A &amp; B" in out, out
    assert "&lt;SDA&gt;" in out, out
    print("  [OK] infobulle : entrees echappees")


def test_placeholder_info_i18n():
    from ui.wiring.wiring_diagram_dialog import _t
    for lang in ("fr", "en", "es", "it"):
        assert "{name}" in _t("placeholder_info_body", lang), f"{lang} body"
        assert _t("placeholder_info_title", lang), f"{lang} title"
    print("  [OK] i18n modale placeholder (4 langues, {name})")


FASTLED_PLUS_I2C_CODE = """
#include <FastLED.h>
#include <Wire.h>
CRGB leds[8];
void setup() {
  FastLED.addLeds<WS2812, 6>(leds, 8);
  Wire.begin();
}
void loop() {}
"""


def test_fastled_with_wire_no_spurious_i2c_module():
    # FastLED WS2812 cable + Wire present : ne doit PAS creer un module I2C
    # "fastled" parasite (le header est dans claimed_headers).
    comps, _ = _detect_libraries(FASTLED_PLUS_I2C_CODE)
    assert len(_by_type(comps, "neopixel")) == 1, [c.type for c in comps]
    assert not _by_type(comps, "fastled"), \
        f"module I2C 'fastled' parasite : {[c.type for c in comps]}"
    assert not [c for c in comps if c.attributes.get("unrecognized")], \
        "aucun placeholder attendu"
    print("  [OK] FastLED + Wire -> neopixel seul (pas de module I2C parasite)")


# ─── Tests UART generique (HC-05/HC-06 via SoftwareSerial nu) ────────────────

UART_BARE_CODE = """
#include <SoftwareSerial.h>
SoftwareSerial bt(10, 11);
void setup() { bt.begin(9600); }
void loop() {}
"""

UART_NAMED_CODE = """
#include <HC05.h>
SoftwareSerial bt(10, 11);
void setup() {}
void loop() {}
"""

UART_WITH_GPS_CODE = """
#include <TinyGPS++.h>
#include <SoftwareSerial.h>
SoftwareSerial gps(4, 3);
SoftwareSerial bt(10, 11);
void setup() {}
void loop() {}
"""


def test_uart_bare_softwareserial():
    comps, _ = _detect_libraries(UART_BARE_CODE)
    mods = _by_type(comps, "uart_module")
    assert len(mods) == 1, f"attendu 1 uart_module, recu {[c.type for c in comps]}"
    c = mods[0]
    assert _pin_net(c, "TX") == "D10", _pin_net(c, "TX")
    assert _pin_net(c, "RX") == "D11", _pin_net(c, "RX")
    assert _pin_net(c, "VCC") == "5V"
    assert _pin_net(c, "GND") == "GND"
    assert not [x for x in comps if x.attributes.get("unrecognized")], "pas de placeholder"
    print("  [OK] SoftwareSerial nu -> uart_module TX=D10 RX=D11")


def test_uart_named_from_unknown_include():
    comps, _ = _detect_libraries(UART_NAMED_CODE)
    named = _by_type(comps, "hc05")
    assert len(named) == 1, f"attendu 1 module hc05, recu {[c.type for c in comps]}"
    assert _pin_net(named[0], "TX") == "D10"
    assert _pin_net(named[0], "RX") == "D11"
    assert not [x for x in comps if x.attributes.get("unrecognized")], \
        "HC05.h doit etre claime (pas de placeholder)"
    print("  [OK] include inconnu unique + SS -> module hc05, pas de placeholder")


def test_uart_gps_takes_first_then_generic():
    comps, _ = _detect_libraries(UART_WITH_GPS_CODE)
    assert len(_by_type(comps, "gps")) == 1, [c.type for c in comps]
    mods = _by_type(comps, "uart_module")
    assert len(mods) == 1, [c.type for c in comps]
    assert _pin_net(_by_type(comps, "gps")[0], "TX") == "D4"
    assert _pin_net(mods[0], "TX") == "D10", _pin_net(mods[0], "TX")
    assert _pin_net(_by_type(comps, "gps")[0], "RX") == "D3"
    assert _pin_net(mods[0], "RX") == "D11"
    print("  [OK] GPS prend la 1ere SS, uart_module la 2eme")


def test_uart_module_label():
    from ui.wiring.instructions import _label
    assert _label("uart_module", "fr") == "module UART", _label("uart_module", "fr")
    assert _label("uart_module", "en") == "UART module", _label("uart_module", "en")
    assert _label("uart_module", "es") == "módulo UART", _label("uart_module", "es")
    assert _label("uart_module", "it") == "modulo UART", _label("uart_module", "it")
    print("  [OK] label uart_module")


def main() -> int:
    tests = [
        test_ina219_detected,
        test_ina219_address_default,
        test_fastled_ws2812_detected,
        test_fastled_ws2812b_detected,
        test_fastled_const_pin_resolved,
        test_fastled_apa102_falls_to_placeholder,
        test_neopixel_label_broadened,
        test_generic_i2c_unknown_lib,
        test_generic_no_double_emit_oled,
        test_generic_skips_ina219,
        test_unknown_no_i2c_placeholder,
        test_placeholder_pin_count,
        test_multi_unknown_placeholders,
        test_core_headers_no_placeholder,
        test_i2c_unknown_lib_not_placeholder,
        test_two_unknown_i2c,
        test_ina219_instruction_label,
        test_render_ina219_scene,
        test_placeholder_warning_emitted,
        test_placeholder_warning_i18n_all_langs,
        test_render_placeholder_scene,
        test_placeholder_gets_attention_icon,
        test_placeholder_info_i18n,
        test_attention_tooltip_has_a_title_and_wraps,
        test_attention_tooltip_titles_do_not_lie,
        test_tooltip_html_escapes_its_input,
        test_fastled_with_wire_no_spurious_i2c_module,
        test_uart_bare_softwareserial,
        test_uart_named_from_unknown_include,
        test_uart_gps_takes_first_then_generic,
        test_uart_module_label,
    ]
    print("[test_wiring_on_the_fly_components]\n")
    failed = 0
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERR ] {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
