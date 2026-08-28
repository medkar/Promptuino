"""QA K1 (2026-08-10) : un schema entierement VIDE pour un ecran ILI9341.

Mesure d'origine. Les deux ecritures ci-dessous declarent le meme objet :

    Adafruit_ILI9341 tft(10, 9, 8);                      <- detecte
    Adafruit_ILI9341 tft = Adafruit_ILI9341(10, 9, 8);   <- RIEN

Les detecteurs a constructeur ne reconnaissaient que la premiere. Mesure sur 8
signatures : SIX tombaient (ili9341, mfrc522, encoder, neopixel, ir_receiver,
dht) ; seules celles reconnues par leur seul `#include` (ssd1306, ina219)
survivaient. Le schema sortait vide, sans le moindre avertissement -- rien ne
distingue « aucun composant » de « aucun composant detecte ».

Ce qui rendait le trou grave plutot qu'anecdotique : c'est l'ecriture des
EXEMPLES OFFICIELS Adafruit, donc celle que le RAG fournit au modele et que le
modele recopie.

Correctif : une normalisation en phase 0 de `parse_fallback`, avant tout le
reste, pour qu'aucun detecteur n'ait a connaitre les deux ecritures.

Run : python scripts/test_ctor_assignment_form.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.markers import _normalize_ctor_assignment as normalize
from ui.wiring.markers import extract_netlist

# (type attendu, include, "Type nom", "Type(args)")
_CASES = [
    ("ili9341", "#include <Adafruit_ILI9341.h>",
     "Adafruit_ILI9341 tft", "Adafruit_ILI9341(10, 9, 8)"),
    ("mfrc522", "#include <MFRC522.h>",
     "MFRC522 rfid", "MFRC522(10, 9)"),
    ("encoder", "#include <Encoder.h>",
     "Encoder enc", "Encoder(2, 3)"),
    ("neopixel", "#include <Adafruit_NeoPixel.h>",
     "Adafruit_NeoPixel strip", "Adafruit_NeoPixel(16, 6, NEO_GRB)"),
    ("ir_receiver", "#include <IRremote.h>",
     "IRrecv irrecv", "IRrecv(11)"),
    ("dht22", "#include <DHT.h>",
     "DHT dht", "DHT(2, DHT22)"),
]


def _sketch(include: str, decl: str, ctor: str, assigned: bool) -> str:
    body = f"{decl} = {ctor};" if assigned else f"{decl}{ctor[ctor.index('('):]};"
    return f"{include}\n{body}\nvoid setup(){{}}\nvoid loop(){{}}"


def _types(code: str) -> list[str]:
    return [c.type for c in
            extract_netlist(code, "arduino_uno_r3", prompt="").components]


def test_the_assignment_form_is_detected():
    """Le coeur : les six signatures qui tombaient."""
    for expected, include, decl, ctor in _CASES:
        got = _types(_sketch(include, decl, ctor, assigned=True))
        assert expected in got, (
            f"{expected}: forme par affectation -> {got or 'RIEN'}")


def test_both_forms_give_the_same_thing():
    """L'invariant reel : l'ecriture choisie par le modele ne doit RIEN
    changer au schema. Comparer les deux formes vaut mieux que verifier la
    seule forme reparee -- si la normalisation deformait quelque chose, ce
    test le verrait, l'autre non."""
    for expected, include, decl, ctor in _CASES:
        direct = _types(_sketch(include, decl, ctor, assigned=False))
        assigned = _types(_sketch(include, decl, ctor, assigned=True))
        assert direct == assigned, f"{expected}: {direct} != {assigned}"


def test_an_assignment_from_a_DIFFERENT_name_is_never_rewritten():
    """L'invariant reel : la retro-reference exige le MEME nom de type des deux
    cotes. Sans elle, la normalisation reecrirait n'importe quelle affectation.

    NB : `String s = String(42);` EST normalise, et c'est correct -- meme nom
    des deux cotes, donc c'est bien une declaration d'objet. Sans consequence :
    la normalisation ne sert qu'a la DETECTION (variable locale de
    `parse_fallback`), le sketch de l'utilisateur n'est jamais reecrit, et
    aucun detecteur ne s'interesse a `String`. Ce test a attrape ma premiere
    assertion, trop large."""
    for src in ("int x = foo(1);",
                "int v = analogRead(A0);",
                "Servo s = other(3);",
                "float f = map(v, 0, 1023, 0, 5);",
                "Adafruit_ILI9341 tft = makeScreen(10, 9);"):
        assert normalize(src) == src, src


def test_leading_qualifiers_are_kept():
    """`static` / `const` en tete ne doivent ni bloquer la normalisation ni
    disparaitre du code."""
    assert normalize("static DHT dht = DHT(2, DHT22);") == \
        "static DHT dht(2, DHT22);"
    assert normalize("  const Encoder e = Encoder(2, 3);") == \
        "  const Encoder e(2, 3);"


def test_indentation_is_preserved():
    """La normalisation tourne sur le fichier entier : ecraser l'indentation
    casserait la lecture du code par les autres detecteurs (blocs, accolades)."""
    assert normalize("    MFRC522 r = MFRC522(10, 9);") == \
        "    MFRC522 r(10, 9);"


def test_a_hpp_include_is_seen_by_every_detector():
    r"""QA K1, second temps. Les ~40 regex d'include du module figent `\.h`,
    `_INCLUDE_ANY_RE` comprise : un en-tete `.hpp` etait invisible des
    detecteurs dedies ET du filet universel -- ni composant, ni boite
    placeholder, ni avertissement. Netlist vide, sur un sketch parfaitement
    valide."""
    from ui.wiring.markers import _normalize_include_extensions as norm_inc
    assert norm_inc("#include <IRremote.hpp>") == "#include <IRremote.h>"
    assert norm_inc('#include "Foo.hh"') == '#include "Foo.h"'
    assert norm_inc("#include <Wire.h>") == "#include <Wire.h>"
    # Ce qui n'est pas une directive include ne bouge pas.
    assert norm_inc("String s = x.hpp;") == "String s = x.hpp;"


def test_both_irremote_api_generations_are_detected():
    """La v4 a supprime le constructeur au profit d'un objet global
    `IrReceiver`. C'est l'ecriture de l'exemple officiel, donc du corpus, donc
    du modele. Les deux doivent donner le MEME recepteur."""
    v4 = "\n".join([
        "#include <IRremote.hpp>",
        "#define DECODE_NEC",
        "const int IR_RECEIVE_PIN = 11;",
        "void setup(){ IrReceiver.begin(IR_RECEIVE_PIN, ENABLE_LED_FEEDBACK); }",
        "void loop(){}",
    ])
    v3 = "\n".join([
        "#include <IRremote.h>",
        "IRrecv irrecv(11);",
        "void setup(){ irrecv.enableIRIn(); }",
        "void loop(){}",
    ])
    from ui.wiring.markers import extract_netlist
    def pins(code):
        nl = extract_netlist(code, "arduino_uno_r3", prompt="")
        comps = [c for c in nl.components if c.type == "ir_receiver"]
        assert len(comps) == 1, f"{[c.type for c in nl.components] or 'AUCUN'}"
        return [(p.name, p.net) for p in comps[0].pins]
    assert pins(v4) == pins(v3) == [("OUT", "D11"), ("GND", "GND"), ("VCC", "5V")]


def test_an_unknown_hpp_still_gets_its_placeholder():
    """Le filet universel doit voir un `.hpp` inconnu comme n'importe quel
    autre : une boite non cablee ET un avertissement. Sans ca, l'app promet
    « tout include inconnu devient visible » et ne le tient pas."""
    from ui.wiring.markers import extract_netlist
    code = "\n".join(["#include <LibInconnueXY.hpp>",
                      "void setup(){}", "void loop(){}"])
    nl = extract_netlist(code, "arduino_uno_r3", prompt="")
    assert [c.attributes.get("unrecognized") for c in nl.components] == [True]
    assert "unwired_unknown_component" in [w.code for w in nl.warnings]


TESTS = [
    test_the_assignment_form_is_detected,
    test_both_forms_give_the_same_thing,
    test_an_assignment_from_a_DIFFERENT_name_is_never_rewritten,
    test_leading_qualifiers_are_kept,
    test_indentation_is_preserved,
    test_a_hpp_include_is_seen_by_every_detector,
    test_both_irremote_api_generations_are_detected,
    test_an_unknown_hpp_still_gets_its_placeholder,
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
