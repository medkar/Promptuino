"""QA J1 (2026-08-10) : une librairie dont le NOM ne contient pas le radical de
son EN-TETE n'etait jamais installee.

Mesure d'origine, sur le vrai registre Arduino :

    #include <Adafruit_MCP23X17.h>
    -> requete derivee « Adafruit MCP23X17 »  -> 0 resultat
    -> vraie librairie « Adafruit MCP23017 Arduino Library »  (23_0_17)

La librairie n'etait donc pas installee, la compilation echouait sur un en-tete
manquant, et TOUTE la generation etait annulee. Chercher par en-tete n'est pas
une option : `arduino-cli lib search` n'indexe pas `provides_includes`.

Or l'app connaissait la reponse dans corpus.json depuis toujours. Ces tests
verrouillent la resolution et, surtout, l'ORDRE des requetes -- le radical doit
rester essaye, sinon un nom memorise devenu perime casserait des libs qui
marchaient.

Sans reseau ni arduino-cli.

Run : python scripts/test_lib_by_header.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import declared_components, registry_lookup
from ui.arduino_cli import _search_queries
from ui.lib_by_header import lib_name_for_header


def _isolate() -> None:
    """Ni composants declares ni cache : les tests du corpus ne doivent pas
    dependre de la machine (`components.json` du dossier utilisateur)."""
    declared_components.set_registry([])
    registry_lookup.set_cache_for_tests({})


def _release() -> None:
    registry_lookup.set_cache_for_tests(None)
    declared_components.set_registry([])


def test_the_measured_case_resolves():
    """Le cas exact qui a bloque J1."""
    _isolate()
    try:
        assert lib_name_for_header("Adafruit_MCP23X17.h") == \
            "Adafruit MCP23017 Arduino Library"
    finally:
        _release()


def test_a_header_with_a_path_still_resolves():
    _isolate()
    try:
        assert lib_name_for_header("Adafruit/Adafruit_MCP23X17.h") == \
            "Adafruit MCP23017 Arduino Library"
    finally:
        _release()


def test_an_unknown_header_answers_empty_not_a_guess():
    """« Inconnu » doit rester vide : l'appelant retombe alors sur son
    heuristique. Inventer un nom ici installerait la mauvaise librairie."""
    _isolate()
    try:
        assert lib_name_for_header("CeciNExistePas_XYZ.h") == ""
        assert lib_name_for_header("") == ""
    finally:
        _release()


def test_a_companion_header_is_not_attributed_to_the_wrong_library():
    """`Adafruit_GFX.h` est cite par ssd1306 / ili9341 / ht16k33 comme
    COMPAGNON : il appartient a « Adafruit GFX Library », pas a elles. Le
    corpus ne repond donc que pour le PREMIER en-tete d'une entree. Sans cette
    regle, le resolveur renverrait « Adafruit SSD1306 » pour un en-tete GFX --
    une reponse fausse la ou l'heuristique du radical marchait deja.

    L'invariant est l'absence de MAUVAISE attribution, pas l'absence de
    reponse : `OneWire.h` a sa propre entree au corpus, donc « OneWire » est la
    bonne reponse et doit sortir (c'est ce que ce test a corrige de lui-meme au
    premier passage)."""
    _isolate()
    try:
        for companion, wrong in (("Adafruit_GFX.h", "Adafruit SSD1306"),
                                 ("Adafruit_Sensor.h", "Adafruit BME280 Library"),
                                 ("OneWire.h", "DallasTemperature")):
            got = lib_name_for_header(companion)
            assert got != wrong, f"{companion} attribue a tort a {got!r}"
        # Et la ou le corpus n'a pas d'entree propre, il se tait plutot que de
        # designer l'entree qui cite l'en-tete en compagnon.
        assert lib_name_for_header("Adafruit_GFX.h") == ""
        assert lib_name_for_header("Adafruit_Sensor.h") == ""
        assert lib_name_for_header("OneWire.h") == "OneWire"
    finally:
        _release()


def test_the_other_primary_headers_resolve_too():
    """Les 4 autres cas reels mesures sur le corpus, pour que le correctif ne
    tienne pas au seul exemple qui l'a declenche."""
    _isolate()
    try:
        for header, lib in (
            ("TM1637Display.h", "TM1637"),
            ("MAX30105.h",
             "SparkFun MAX3010x Pulse and Proximity Sensor Library"),
            ("Adafruit_ST7789.h", "Adafruit ST7735 and ST7789 Library"),
            ("Adafruit_ADXL345_U.h", "Adafruit ADXL345"),
        ):
            assert lib_name_for_header(header) == lib, header
    finally:
        _release()


def test_a_declared_component_wins_over_the_corpus():
    """Le plus specifique d'abord : ce que l'utilisateur a declare (et la
    librairie qu'il a choisie) bat le defaut cure."""
    from ui.declared_components import DeclaredComponent
    _isolate()
    try:
        declared_components.set_registry([
            DeclaredComponent(id="mien", name="Le mien",
                              headers=("Adafruit_MCP23X17.h",), pins=(),
                              lib="Ma Librairie A Moi", keywords=())])
        assert lib_name_for_header("Adafruit_MCP23X17.h") == "Ma Librairie A Moi"
    finally:
        _release()


def test_the_registry_cache_wins_over_the_corpus():
    _isolate()
    try:
        registry_lookup.set_cache_for_tests({"xyz9000": {
            "lib_name": "Lib Du Cache",
            "entry": {"headers": ["Adafruit_MCP23X17.h"]}}})
        assert lib_name_for_header("Adafruit_MCP23X17.h") == "Lib Du Cache"
    finally:
        _release()


def test_the_stem_query_is_kept_after_the_known_name():
    """L'invariant de non-regression : le radical reste essaye. Sans lui, une
    lib renommee au registre cesserait d'etre trouvee alors qu'elle l'etait."""
    assert _search_queries("Adafruit_MCP23X17",
                           "Adafruit MCP23017 Arduino Library") == \
        ["Adafruit MCP23017 Arduino Library", "Adafruit MCP23X17"]


def test_without_a_known_name_nothing_changes():
    """Le chemin de la majorite des libs doit etre bit-a-bit l'ancien."""
    assert _search_queries("Servo", None) == ["Servo"]
    assert _search_queries("Servo", "") == ["Servo"]


def test_a_known_name_equal_to_the_stem_is_not_searched_twice():
    assert _search_queries("Servo", "Servo") == ["Servo"]


TESTS = [
    test_the_measured_case_resolves,
    test_a_header_with_a_path_still_resolves,
    test_an_unknown_header_answers_empty_not_a_guess,
    test_a_companion_header_is_not_attributed_to_the_wrong_library,
    test_the_other_primary_headers_resolve_too,
    test_a_declared_component_wins_over_the_corpus,
    test_the_registry_cache_wins_over_the_corpus,
    test_the_stem_query_is_kept_after_the_known_name,
    test_without_a_known_name_nothing_changes,
    test_a_known_name_equal_to_the_stem_is_not_searched_twice,
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
