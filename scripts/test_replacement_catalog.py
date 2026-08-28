"""Guards for the SP3 replacement catalog (Fritzing Tier-1 bus)."""
from __future__ import annotations
import os, sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# QApplication kept at module level (cf. gotcha SP2: without a kept reference,
# the temporary app is GC'd and constructing a QWidget crashes on Windows).
from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])


def test_catalog_categories_match_constants():
    """Every literal category in the table is a valid category constant."""
    from ui.wiring import categories as cat
    from ui.wiring.replacement_catalog import REPLACEMENT_CATALOG
    valid = {cat.I2C, cat.SPI, cat.UART, cat.ULTRASONIC,
             cat.ONEWIRE_TEMP, cat.MOTOR_DC, cat.MOTOR_STEPPER,
             cat.SINGLE_OUTPUT, cat.ANALOG_IN, cat.DIGITAL_IN}
    for type_id, category, _label in REPLACEMENT_CATALOG:
        assert category in valid, f"{type_id}: categorie inconnue {category!r}"
    print(f"  OK — {len(REPLACEMENT_CATALOG)} entrees, categories valides")


def test_catalog_label_coverage():
    """Every entry has a non-empty label that differs from its raw type_id."""
    from ui.wiring.replacement_catalog import REPLACEMENT_CATALOG, label_of
    for type_id, _category, label in REPLACEMENT_CATALOG:
        assert label and label != type_id, f"{type_id}: libelle brut/absent"
        assert label_of(type_id) == label, f"{type_id}: label_of incoherent"
    assert label_of("type_inexistant_xyz") is None
    print("  OK — libelles couverts, aucun type_id brut")


def test_catalog_no_duplicate_type_ids():
    """No duplicate type_id in the table (multi-view merge applied)."""
    from ui.wiring.replacement_catalog import REPLACEMENT_CATALOG
    ids = [t for t, _c, _l in REPLACEMENT_CATALOG]
    dups = sorted({t for t in ids if ids.count(t) > 1})
    assert not dups, f"type_ids dupliques: {dups}"
    print(f"  OK — {len(ids)} type_ids uniques")


def test_merge_into_populates_map():
    """merge_into writes every entry into a given map."""
    from ui.wiring.replacement_catalog import REPLACEMENT_CATALOG, merge_into
    m = {}
    merge_into(m)
    for type_id, category, _label in REPLACEMENT_CATALOG:
        assert m.get(type_id) == category, f"{type_id} non fusionne"
    print("  OK — merge_into peuple la map")


def test_no_collision_after_merge():
    """No curated type reclassifies a pre-existing type to a different category."""
    from ui.wiring.replacement_catalog import REPLACEMENT_CATALOG
    from ui.wiring import categories as cat
    for type_id, category, _label in REPLACEMENT_CATALOG:
        actual = cat.category_of(type_id)
        assert actual == category, (
            f"{type_id}: attendu {category}, obtenu {actual} "
            f"(collision avec une entrée existante ?)")
    print("  OK — aucune collision de catégorie après merge")


def test_round_trip_candidates_in():
    """Every curated type appears in candidates_in for its category."""
    from ui.wiring.replacement_catalog import REPLACEMENT_CATALOG
    from ui.wiring.categories import candidates_in
    for type_id, category, _label in REPLACEMENT_CATALOG:
        members = candidates_in(category)
        assert type_id in members, f"{type_id} absent de candidates_in({category})"
    print("  OK — round-trip candidates_in")


def test_spot_bus_categories():
    """Spot-check: a known SPI -> SPI, a known I2C -> I2C, ultrasonic -> ULTRASONIC."""
    from ui.wiring import categories as cat
    assert cat.category_of("nrf24l01") == cat.SPI
    assert cat.category_of("ds3231") == cat.I2C
    assert cat.category_of("us100") == cat.ULTRASONIC
    # invariant unchanged
    assert cat.candidates_in(cat.NON_REPLACEABLE) == []
    print("  OK — spot bus + invariant NON_REPLACEABLE")


def test_dropdown_uses_curated_label():
    """build_replacement_choices displays the curated label, not the raw type_id.

    Depuis le filtre fonctionnel (Task 5), oled_ssd1306 ne propose plus que
    les ecrans (famille 'ecran'), pas tous les I2C. On verifie que les labels
    cures sont bien utilises sur les candidats de la meme famille.
    """
    from ui.wiring.netlist import Component, Pin
    from ui.wiring.replacement_ui import build_replacement_choices
    oled = Component(
        ref="U1", type="oled_ssd1306",
        pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5")],
        attributes={"category": "i2c"},
    )
    choices = build_replacement_choices(oled, "fr")
    by_id = dict(choices)
    assert by_id.get("nrf24l01") is None  # SPI, pas dans la famille ecran
    # ds3231 (horloge RTC) n'est pas un ecran -> exclu par le filtre fonctionnel
    assert by_id.get("ds3231") is None, \
        f"ds3231 ne devrait pas etre propose pour un ecran, obtenu {by_id.get('ds3231')!r}"
    # lcd_i2c est un ecran -> present avec son label cure
    assert by_id.get("lcd_i2c") == "écran LCD I²C", \
        f"label cure attendu pour lcd_i2c, obtenu {by_id.get('lcd_i2c')!r}"
    print("  OK — dropdown libelle cure")


def test_engine_bus_replacement_keeps_nets():
    """Replacing an OLED (I2C) with an SP3 bus type preserves VCC/GND/SDA/SCL."""
    from ui.wiring.netlist import Component, Pin, Netlist
    from ui.wiring.component_replace import replace_component
    oled = Component(
        ref="U1", type="oled_ssd1306",
        pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5")],
        attributes={"category": "i2c"},
    )
    nl = Netlist(board_id="uno", components=[oled])
    result = replace_component(nl, "U1", "ds3231")
    comp = next(c for c in result.netlist.components if c.ref == "U1")
    nets = {p.net for p in comp.pins}
    assert {"5V", "GND", "A4", "A5"}.issubset(nets), \
        f"nets de bus perdus après remplacement: {nets}"
    assert comp.type == "ds3231"
    print("  OK — remplacement bus->bus conserve les nets")


def test_spot_tier2_bare_pin_categories():
    """Spot-check Tier-2 bare pin + mpr121 recategorized as I2C fix."""
    from ui.wiring import categories as cat
    assert cat.category_of("solenoid") == cat.SINGLE_OUTPUT
    assert cat.category_of("hall_sensor") == cat.ANALOG_IN
    assert cat.category_of("tilt_switch") == cat.DIGITAL_IN
    # scrape fix: mpr121 is a tactile I2C controller, not digital_in
    assert cat.category_of("mpr121") == cat.I2C
    print("  OK — spot Tier-2 broche nue + mpr121 I2C")


TESTS = [
    test_dropdown_uses_curated_label,
    test_catalog_categories_match_constants,
    test_catalog_label_coverage,
    test_catalog_no_duplicate_type_ids,
    test_merge_into_populates_map,
    test_no_collision_after_merge,
    test_round_trip_candidates_in,
    test_spot_bus_categories,
    test_spot_tier2_bare_pin_categories,
    test_engine_bus_replacement_keeps_nets,
]


def main():
    passed = failed = 0
    for t in TESTS:
        try:
            t(); print(f"PASS  {t.__name__}"); passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
