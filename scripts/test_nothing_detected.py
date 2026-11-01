"""TODO #47 volet 2 — rompre le silence d'une netlist vide (2026-08-10).

Le silence etait le PIRE symptome du chantier : rien ne distinguait « ce sketch
n'a aucun composant » de « je n'ai rien su lire ». C'est ce silence qui a laisse
quatre defauts de detection vivre jusqu'a une QA manuelle.

Les autres filets parlent tous — `unwired_unknown_component`,
`presumed_i2c_wiring`, `presumed_analog_component`, `undrawable_component`. Il
ne restait que ce cas-la, et c'est celui ou l'utilisateur voit un schema
ENTIEREMENT BLANC.

La regle ne devine rien : netlist vide + au moins un `#include` qui n'est pas
dans `_NO_HARDWARE_HEADERS`. Mesuree sur les 91 exemples du corpus, elle separe
exactement les deux seuls cas de netlist vide — `onewire` (qui doit avertir) et
`eeprom` (memoire integree au microcontroleur : rien a brancher, donc silence).

⚠️ Cause structurelle mise a jour au passage : `onewire.h` figure dans
`_KNOWN_HEADERS_LOWER`, groupe « core / utilities / companions ». C'est ce
classement qui empechait le placeholder universel de se declencher. Un en-tete
declare « connu » qui n'emet rien cree un angle mort que le filet ne peut pas
voir — d'ou ce second filet, pose plus bas et sur un autre critere.

Run : python scripts/test_nothing_detected.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui import rag
from ui.wiring.wiring_pipeline import generate_wiring

BOARD = "arduino_uno_r3"
CODE = "nothing_detected"
LANGS = ("fr", "en", "es", "it")


def _warnings(code: str) -> list[str]:
    return [w.code for w in generate_wiring(code, BOARD).warnings]


def _corpus_example(cid: str) -> str:
    e = rag.corpus_entry(cid)
    assert e is not None, cid
    return (e.get("example_code") or "").strip()


# ── Il parle quand il doit ────────────────────────────────────────────────────

def test_a_hardware_library_that_yields_nothing_is_announced():
    """Le cas reel : l'exemple officiel de OneWire ne produit AUCUN composant.
    Avant, le schema s'ouvrait vide et muet."""
    assert CODE in _warnings(_corpus_example("onewire"))


def test_an_unknown_hardware_header_alone_is_announced():
    code = ("#include <ZorgTrucSensor.h>\n"
            "void setup(){}\nvoid loop(){}\n")
    # Le placeholder universel prend ce cas EN PREMIER (il produit une boite),
    # donc la netlist n'est pas vide : c'est lui qui parle, pas nous. On
    # verifie qu'au moins UN des deux le dit — le silence est le seul echec.
    w = _warnings(code)
    assert ("unwired_unknown_component" in w) or (CODE in w), w


# ── Il se tait quand il doit ──────────────────────────────────────────────────

def test_a_component_with_nothing_to_wire_stays_silent():
    """L'EEPROM est une memoire reelle avec une vraie bibliotheque, mais
    integree au microcontroleur. Un schema vide y est la BONNE reponse."""
    assert CODE not in _warnings(_corpus_example("eeprom"))


def test_an_i2c_scanner_stays_silent():
    """Un scanner n'a que `Wire.h` et n'a legitimement rien a cabler — le TODO
    le nommait explicitement comme le cas a ne pas ameuter."""
    code = ("#include <Wire.h>\n"
            "void setup(){ Wire.begin(); }\nvoid loop(){}\n")
    assert CODE not in _warnings(code)


def test_a_blink_on_the_internal_led_stays_silent():
    """L'autre cas nomme par le TODO. Il se tait pour une raison plus forte
    qu'une exemption : le blink PRODUIT un composant, donc la regle ne
    s'applique pas du tout."""
    code = ("void setup(){ pinMode(LED_BUILTIN, OUTPUT); }\n"
            "void loop(){ digitalWrite(LED_BUILTIN, HIGH); delay(500); }\n")
    nl = generate_wiring(code, BOARD)
    assert nl.components, "le blink doit produire une LED"
    assert CODE not in [w.code for w in nl.warnings]


def test_an_empty_sketch_stays_silent():
    assert CODE not in _warnings("void setup(){}\nvoid loop(){}\n")


def test_a_software_only_library_stays_silent():
    code = ("#include <ArduinoJson.h>\n"
            "void setup(){}\nvoid loop(){}\n")
    assert CODE not in _warnings(code)


# ── La mesure, verrouillee ────────────────────────────────────────────────────

def test_on_the_whole_corpus_it_fires_exactly_once():
    """Zero faux positif sur les 91 exemples : la regle a ete ecrite APRES la
    mesure, pas avant. Si un jour elle criait sur un deuxieme exemple, ce
    serait soit un vrai trou de detection (a corriger), soit une regle devenue
    bavarde (a resserrer) — les deux meritent qu'on regarde."""
    qui = []
    for entry in rag.all_corpus_entries():
        ex = (entry.get("example_code") or "").strip()
        if ex and CODE in _warnings(ex):
            qui.append(entry.get("id"))
    assert qui == ["onewire"], qui


def test_the_message_is_translated_in_the_four_languages():
    from ui.wiring.instructions import _WARNING_TEMPLATES
    tpl = _WARNING_TEMPLATES.get(CODE)
    assert tpl, "aucun gabarit : le warning s'afficherait sous son code brut"
    for lang in LANGS:
        texte = (tpl.get(lang) or "").strip()
        assert texte, lang
        assert "{header}" in texte, f"{lang} : l'en-tete en cause n'est pas dit"


def test_the_message_says_the_reading_failed_not_that_there_is_nothing():
    """Tout l'objet du volet 2. Un « schema vide » sans explication se lit
    comme « il n'y a rien a brancher », ce qui est faux et rassurant a tort."""
    from ui.wiring.instructions import _WARNING_TEMPLATES
    fr = _WARNING_TEMPLATES[CODE]["fr"].lower()
    assert "lecture" in fr and "vide" in fr, fr


TESTS = [
    test_a_hardware_library_that_yields_nothing_is_announced,
    test_an_unknown_hardware_header_alone_is_announced,
    test_a_component_with_nothing_to_wire_stays_silent,
    test_an_i2c_scanner_stays_silent,
    test_a_blink_on_the_internal_led_stays_silent,
    test_an_empty_sketch_stays_silent,
    test_a_software_only_library_stays_silent,
    test_on_the_whole_corpus_it_fires_exactly_once,
    test_the_message_is_translated_in_the_four_languages,
    test_the_message_says_the_reading_failed_not_that_there_is_nothing,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
