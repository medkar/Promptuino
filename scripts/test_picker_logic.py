"""Filtre du picker de composants : champ vide = categorie detectee,
la frappe traverse le filtre et atteint toute la bibliotheque.

Run : python scripts/test_picker_logic.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.declared_components as dc

dc.set_registry([])

from ui.wiring.netlist import Component, Pin
from ui.wiring.picker_logic import (visible_items, PickerGroups,
                                    _all_library_items)


def _led_d5():
    return Component(ref="D1", type="led",
                     pins=[Pin("A", "D5"), Pin("K", "GND")],
                     attributes={"category": "single_output",
                                 "_confidence": "low"})


def test_empty_query_shows_the_detected_category_and_groups():
    g = visible_items(_led_d5(), "", "fr")
    assert isinstance(g, PickerGroups)
    cat_ids = [i.type_id for i in g.category]
    assert "led" in cat_ids and "buzzer" in cat_ids
    promo_ids = [i.type_id for i in g.promotions]
    assert "servo" in promo_ids and "dc_motor" in promo_ids
    # pas de fuite : les promotions ne sont pas dans le groupe categorie
    assert not set(cat_ids) & set(promo_ids)


def _bme280_i2c():
    return Component(ref="U1", type="bme280",
                     pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                           Pin("SDA", "A4"), Pin("SCL", "A5")],
                     attributes={"category": "i2c", "_confidence": "low"})


def test_typing_crosses_the_family_boundary():
    """La frappe atteint toute la bibliotheque APPLICABLE.

    ⚠️ Ce test s'appelait `..._crosses_the_category_boundary` et sondait une
    LED avec << bmp180 >>. Il passait, et il MENTAIT : le picker affichait la
    card, mais cliquer dessus ne faisait rien -- verifie le 2026-08-26,
    `apply_saved_resolution(led, "bmp180")` laisse le composant en LED, broches
    inchangees, sans le moindre message. `replace_component` refuse un
    changement de categorie, et refusait deja.

    Ce qui EST vrai, et que ce test verifie maintenant : depuis un BME280, la
    frappe sort de sa famille fonctionnelle pour atteindre n'importe quel
    composant I2C de la bibliotheque -- et ceux-la, le moteur les accepte."""
    g = visible_items(_bme280_i2c(), "bmp180", "fr")
    everything = [i.type_id for i in g.category + g.promotions + g.yours]
    assert "bmp180" in everything, "la frappe doit atteindre la bibliotheque"
    assert g.crossed_filter, "bmp180 est hors de la famille du BME280"


def test_typing_never_reaches_what_the_engine_would_refuse():
    """La contrepartie, et c'est elle le TODO #67 : un DS18B20 mesure bien une
    temperature comme un BME280, mais ne se cable pas pareil. L'offrir puis ne
    rien faire etait la promesse vide."""
    g = visible_items(_bme280_i2c(), "ds18b20", "fr")
    everything = [i.type_id for i in g.category + g.promotions + g.yours]
    assert "ds18b20" not in everything, everything


def test_match_is_accent_and_case_insensitive():
    g1 = visible_items(_led_d5(), "SOLENOIDE", "fr")
    g2 = visible_items(_led_d5(), "solénoïde", "fr")
    ids1 = {i.type_id for i in g1.category + g1.promotions}
    ids2 = {i.type_id for i in g2.category + g2.promotions}
    assert "solenoid" in ids1 and ids1 == ids2


def test_declared_components_form_their_own_group():
    from ui.declared_components import DeclaredComponent
    dc.set_registry([DeclaredComponent(
        id="monchip", name="MonChip", headers=("monchip.h",),
        pins=(), lib="", keywords=("monchip",))])
    try:
        g = visible_items(_led_d5(), "", "fr")
        assert any(i.type_id == "custom:monchip" for i in g.yours)
    finally:
        dc.set_registry([])


def test_every_item_has_a_display_name_never_the_raw_id():
    """Un nom non resolu retombe sur le slug : c'est CA que la garde attrape.

    Le balayage porte sur TOUTE la bibliotheque, pas sur les seuls candidats
    d'une LED : ceux-ci ne sont que 11, et la regression que cette garde vise
    (les 53 fiches du lot A, absentes de `_TYPE_LABEL` par construction, plus
    tout le catalogue de remplacement) n'est atteignable qu'a la frappe. Un
    « bmp180 » rendu en slug brut serait passe sans bruit sur les 11.

    Une seule exception, et elle n'est pas un echec de resolution : le libelle
    francais de `buzzer` EST le mot « buzzer », identique a son id. Coincidence
    de vocabulaire (en anglais il y en a trois autres : relay, potentiometer,
    thermistor). Capitaliser pour la contourner rendrait la garde VIDE — un
    « bmp180 » non resolu passerait en « Bmp180 » et personne ne le verrait
    plus jamais.
    """
    coincidences = {"buzzer"}
    g = visible_items(_led_d5(), "", "fr")
    for item in g.category + g.promotions + _all_library_items("fr"):
        assert item.name, item.type_id
        assert item.name != item.type_id or item.type_id in coincidences, \
            f"{item.type_id} : nom = id brut, libelle non resolu"


def test_current_type_is_first_in_its_group():
    g = visible_items(_led_d5(), "", "fr")
    assert g.category[0].type_id == "led"


def test_a_non_replaceable_component_offers_nothing_even_when_typing():
    """Infrastructure (resistance, pile, drivers deja inferes) : jamais
    proposable. Champ vide, c'etait deja inerte — `full_candidate_choices`
    rend [] pour ces types. Mais le balayage de bibliotheque, lui, ne
    demandait l'avis de personne : une seule lettre tapee et l'app proposait
    de transformer une resistance en LED.
    """
    r = Component(ref="R1", type="resistor",
                  pins=[Pin("1", "D5"), Pin("2", "GND")], attributes={})
    g = visible_items(r, "led", "fr")
    assert g.category == [] and g.promotions == [] and g.yours == [], \
        [i.type_id for i in g.category + g.promotions + g.yours]
    assert g.crossed_filter is False

    # ... et l'echappatoire du 2026-07-29 survit. Un placeholder tire son type
    # du nom de la lib inconnue, qui peut tomber sur un id justement classe
    # NON_REPLACEABLE : le fermer sur le seul critere de la categorie rendrait
    # muet l'engrenage que le bandeau promet.
    ph = Component(ref="U1", type="hx711", pins=[Pin("1", "")],
                   attributes={"unrecognized": True, "header": "HX711.h"})
    g2 = visible_items(ph, "led", "fr")
    assert any(i.type_id == "led"
               for i in g2.category + g2.promotions), "engrenage muet"


TESTS = [
    test_empty_query_shows_the_detected_category_and_groups,
    test_typing_crosses_the_family_boundary,
    test_typing_never_reaches_what_the_engine_would_refuse,
    test_match_is_accent_and_case_insensitive,
    test_declared_components_form_their_own_group,
    test_every_item_has_a_display_name_never_the_raw_id,
    test_current_type_is_first_in_its_group,
    test_a_non_replaceable_component_offers_nothing_even_when_typing,
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
