"""Le parseur de fiches Fritzing (TODO #54 / #41).

Fritzing publie plus de 1800 definitions de composants dont la liste
`<connector>` EST le brochage — l'axe qui manque a 77 de nos composants
(`wiring="unknown"`). Ce fichier teste la partie PURE : le parsing et la
deduplication, sur des fixtures, sans jamais toucher au reseau.

Le cas qui a motive la deduplication est reel et mesure le 2026-08-19 : la fiche
`core/rtc_ds3231_breakout.fzp` declare DIX connecteurs — GND VCC SDA SCL SQW 32K
GND VCC SDA SCL — pour SIX broches distinctes, parce que la carte a deux rangees
de header. Sans deduplication, on inscrirait un composant a 10 broches qui en a 6.

Run : python scripts/test_fritzing_import.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import fritzing_import as fi

# Reduction fidele de core/rtc_ds3231_breakout.fzp : memes balises, memes
# connecteurs dans le meme ordre, y compris la seconde rangee.
FZP_DS3231 = """<?xml version="1.0" encoding="UTF-8"?>
<module fritzingVersion="0.9.3b" moduleId="rtc_ds3231">
  <version>4</version>
  <author>Fritzing</author>
  <title>ZS-042 RTC Module</title>
  <label>U</label>
  <tags><tag>clock</tag><tag>DS3231</tag><tag>RTC</tag><tag>ZS-042</tag></tags>
  <properties>
    <property name="family">rtc</property>
    <property name="chip">DS3231</property>
    <property name="variant">variant 4</property>
  </properties>
  <description>This is the ZS-042 RTC module.</description>
  <connectors>
    <connector id="connector0" name="GND" type="male"><description>Ground</description></connector>
    <connector id="connector1" name="VCC" type="male"><description>Power</description></connector>
    <connector id="connector2" name="SDA" type="male"><description>I2C data</description></connector>
    <connector id="connector3" name="SCL" type="male"><description>I2C clock</description></connector>
    <connector id="connector4" name="SQW" type="male"><description>Square wave</description></connector>
    <connector id="connector5" name="32K" type="male"><description>32 kHz</description></connector>
    <connector id="connector6" name="GND" type="male"><description>Ground</description></connector>
    <connector id="connector7" name="VCC" type="male"><description>Power</description></connector>
    <connector id="connector8" name="SDA" type="male"><description>I2C data</description></connector>
    <connector id="connector9" name="SCL" type="male"><description>I2C clock</description></connector>
  </connectors>
</module>
"""

FZP_SANS_TAGS = """<?xml version="1.0" encoding="UTF-8"?>
<module moduleId="x">
  <title>Minimal</title>
  <connectors>
    <connector id="c0" name="A" type="male"/>
    <connector id="c1" name="B" type="male"/>
  </connectors>
</module>
"""


def test_the_metadata_is_read():
    p = fi.parse_fzp(FZP_DS3231)
    assert p.title == "ZS-042 RTC Module"
    assert p.family == "rtc"
    assert p.properties.get("chip") == "DS3231"
    assert "ZS-042" in p.tags and "DS3231" in p.tags


def test_the_two_header_rows_collapse_to_the_real_pinout():
    """Le cas qui justifie tout ce fichier : 10 connecteurs, 6 broches."""
    p = fi.parse_fzp(FZP_DS3231)
    assert p.raw_pin_count == 10
    assert p.pins == ("GND", "VCC", "SDA", "SCL", "SQW", "32K")
    assert p.pin_count == 6


def test_the_duplication_is_flagged_not_hidden():
    """Un humain doit pouvoir aller verifier : la regle de deduplication est
    juste pour des ETIQUETTES, pas pour une netlist."""
    assert fi.parse_fzp(FZP_DS3231).has_duplicate_rows is True
    assert fi.parse_fzp(FZP_SANS_TAGS).has_duplicate_rows is False


def test_the_pin_order_is_preserved():
    """L'ordre est la donnee : il decide de la place des etiquettes."""
    assert fi.parse_fzp(FZP_DS3231).pins[0] == "GND"
    assert fi.parse_fzp(FZP_DS3231).pins[-1] == "32K"


def test_dedup_keeps_the_first_occurrence():
    assert fi.dedup_pins(["A", "B", "A", "C", "B"]) == ["A", "B", "C"]
    assert fi.dedup_pins([]) == []
    assert fi.dedup_pins(["  A  ", "A"]) == ["A"], "les blancs ne creent pas de doublon"
    assert fi.dedup_pins(["", "A", ""]) == ["A"], "un nom vide n'est pas une broche"


def test_a_part_without_tags_or_properties_still_parses():
    """Toutes les fiches ne sont pas completes ; l'absence n'est pas une erreur."""
    p = fi.parse_fzp(FZP_SANS_TAGS)
    assert p.title == "Minimal"
    assert p.tags == () and p.family == ""
    assert p.pins == ("A", "B")


def test_malformed_xml_raises_instead_of_returning_something_wrong():
    """Un brochage a moitie lu serait pire que pas de brochage du tout."""
    import xml.etree.ElementTree as ET
    try:
        fi.parse_fzp("<module><connectors>")
    except ET.ParseError:
        pass
    else:
        raise AssertionError("un XML casse doit lever")


def test_drawability_matches_what_resolve_generic_can_do():
    """2-8 en rangee simple (plus les impairs 9, 11, 13 depuis #58), ou
    10-40 PAIR en DIP. Le reste tombe dans `undrawable_component`, et mieux
    vaut le savoir avant l'import."""
    for n in (2, 3, 4, 6, 8, 9, 10, 11, 13, 16, 40):
        assert fi.is_drawable(n), n
    for n in (0, 1, 15, 17, 41, 42):
        assert not fi.is_drawable(n), n


def test_the_draft_says_when_something_needs_a_human():
    p = fi.parse_fzp(FZP_DS3231)
    texte = fi.draft(p)
    assert "pin_count=6" in texte
    assert "deux rangees" in texte, "la duplication doit etre signalee"


def test_the_parser_never_touches_the_network():
    """Le contrat qui rend ce fichier testable : `parse_fzp` est PUR.

    Si le parsing dependait du reseau, ces regles ne seraient testees que le
    jour ou GitHub repond — c'est-a-dire jamais, en pratique.
    """
    import inspect
    src = inspect.getsource(fi.parse_fzp) + inspect.getsource(fi.dedup_pins)
    for interdit in ("urlopen", "requests", "http"):
        assert interdit not in src, interdit


def test_prose_labels_flag_the_bare_chip_instead_of_the_module():
    """La lecon du lot pilote du 2026-08-19.

    Fritzing porte la PUCE NUE et le MODULE. `core/DS1307.fzp` est le DIP-8 et
    nomme ses broches « X1 - Crystal », « Vbat - Backup Supply » ;
    `core/rtc_ds3231_breakout.fzp` est le module et les nomme « GND VCC SDA ».
    Les deux sont des donnees justes ; une seule est celle qu'on dessine.
    """
    puce_nue = ("X1 - Crystal", "Vbat - Backup Supply", "0V", "+V")
    module = ("GND", "VCC", "SDA", "SCL", "SQW", "32K")
    assert fi.prose_labels(puce_nue), "la puce nue doit etre signalee"
    assert fi.prose_labels(module) == [], "le module ne doit rien declencher"


def test_a_long_single_word_label_is_prose_too():
    assert fi.prose_labels(("ThermocoupleInput",)) == ["ThermocoupleInput"]
    assert fi.prose_labels(("TRIG", "ECHO")) == []


TESTS = [
    test_the_metadata_is_read,
    test_the_two_header_rows_collapse_to_the_real_pinout,
    test_the_duplication_is_flagged_not_hidden,
    test_the_pin_order_is_preserved,
    test_dedup_keeps_the_first_occurrence,
    test_a_part_without_tags_or_properties_still_parses,
    test_malformed_xml_raises_instead_of_returning_something_wrong,
    test_drawability_matches_what_resolve_generic_can_do,
    test_the_draft_says_when_something_needs_a_human,
    test_the_parser_never_touches_the_network,
    test_prose_labels_flag_the_bare_chip_instead_of_the_module,
    test_a_long_single_word_label_is_prose_too,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} test(s) au vert")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
