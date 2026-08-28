"""QA K1 (2026-08-10) : un `#include <...hpp>` n'etait traite NULLE PART.

Mesure d'origine, sur le sketch IRremote que le corpus fournit au modele (API
v4, dont l'en-tete est bien `IRremote.hpp`) :

    _extract_unknown_libs('#include <IRremote.hpp>') -> ['IRremote.hpp']
    _detect_missing_lib('fatal error: IRremote.hpp: ...') -> None

Consequences en chaine : le nom cherche au registre etait « IRremote.hpp »
(zero resultat), la librairie n'etait donc jamais installee, la compilation
echouait sur un en-tete manquant, et cet echec n'etait meme pas RECONNU comme
« librairie manquante » -- l'utilisateur recevait une erreur de compilation
brute au lieu du nom de la lib a installer.

`_extract_unknown_libs` rend desormais l'EN-TETE et non un nom de lib devine :
les deux different (« Adafruit MCP23017 Arduino Library » fournit
« Adafruit_MCP23X17.h »), et seul l'en-tete identifie le fournisseur dans
`provides_includes`.

Sans reseau ni arduino-cli.

Run : python scripts/test_header_extensions.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.arduino_cli import (
    _detect_missing_lib, _extract_unknown_libs, _header_stem,
)
from ui.lib_by_header import lib_name_for_header


def test_the_measured_case_extracts_the_header():
    assert _extract_unknown_libs("#include <IRremote.hpp>") == ["IRremote.hpp"]
    assert _header_stem("IRremote.hpp") == "IRremote"


def test_every_header_extension_loses_its_suffix():
    for header, stem in (("Foo.h", "Foo"), ("Foo.hpp", "Foo"),
                         ("Foo.hh", "Foo")):
        assert _header_stem(header) == stem, header


def test_an_unknown_extension_is_kept_whole():
    """Mieux vaut chercher un nom bizarre que chercher une chaine vide."""
    assert _header_stem("Foo") == "Foo"
    assert _header_stem("Foo.inc") == "Foo.inc"


def test_a_missing_hpp_is_recognised_as_a_missing_library():
    for header in ("IRremote.hpp", "Adafruit_NeoPixel.h", "Wire.hh"):
        err = f"fatal error: {header}: No such file or directory"
        assert _detect_missing_lib(err) == header, header


def test_the_error_message_names_the_real_library():
    """Le bout de la chaine : ce que l'utilisateur lit doit etre installable.
    « IRremote.hpp » ne l'etait pas."""
    for header, expected in (("IRremote.hpp", "IRremote"),
                             ("Adafruit_NeoPixel.h", "Adafruit NeoPixel")):
        missing = _detect_missing_lib(
            f"fatal error: {header}: No such file or directory")
        shown = lib_name_for_header(missing) or _header_stem(missing)
        assert shown == expected, f"{header} -> {shown!r}"


def test_builtin_headers_are_still_skipped():
    """Le passage de « nom de lib » a « en-tete » ne doit pas remettre les
    en-tetes du core dans la liste a installer."""
    code = ("#include <Arduino.h>\n#include <Wire.h>\n#include <SPI.h>\n"
            "#include <EEPROM.h>\n#include <IRremote.hpp>")
    assert _extract_unknown_libs(code) == ["IRremote.hpp"]


def test_duplicates_collapse_on_the_header():
    code = "#include <IRremote.hpp>\n#include <IRremote.hpp>"
    assert _extract_unknown_libs(code) == ["IRremote.hpp"]


TESTS = [
    test_the_measured_case_extracts_the_header,
    test_every_header_extension_loses_its_suffix,
    test_an_unknown_extension_is_kept_whole,
    test_a_missing_hpp_is_recognised_as_a_missing_library,
    test_the_error_message_names_the_real_library,
    test_builtin_headers_are_still_skipped,
    test_duplicates_collapse_on_the_header,
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
