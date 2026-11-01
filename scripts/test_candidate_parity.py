"""Ce que la modale MONTRE est exactement ce que la source PROPOSE.

Ce fichier verrouillait la parite entre les tuiles de la modale debutant et
les choix de la modale avancee. Depuis le 2026-08-13 il n'y a plus qu'une
modale, donc plus deux listes a comparer — mais la question qui comptait
reste entiere, deplacee d'un cran : le picker interpose `picker_logic` entre
`full_candidate_choices` et l'ecran, et un intermediaire de plus ne doit ni
ajouter ni perdre un candidat, ni casser l'ordre.

Le filtre FONCTIONNEL est ce qu'on protege surtout : un ecran ne propose que
d'autres ecrans, jamais les peripheriques I2C hors-famille (RTC, capteurs).

Run : python scripts/test_candidate_parity.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui.declared_components as dc

dc.set_registry([])   # jamais le disque de la machine

from ui.wiring.netlist import Component, Pin
from ui.wiring.picker_logic import visible_items
from ui.wiring.replacement_ui import build_replacement_choices


def _screen():
    return Component(ref="U1", type="oled_ssd1306", fn_id="fn-1",
                     pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                           Pin("SDA", "A4"), Pin("SCL", "A5")])


def _led():
    return Component(ref="D1", type="led", fn_id="fn-1",
                     pins=[Pin("A", "D3"), Pin("K", "GND")])


def _shown(component):
    """Tout ce que le picker affiche, champ de recherche vide."""
    g = visible_items(component, "", "fr")
    return g.category, g.promotions, g.yours


def test_the_category_column_is_build_replacement_choices_in_order():
    """Le groupe « meme categorie » du picker EST build_replacement_choices,
    meme contenu et meme ordre — pas un sous-ensemble reordonne."""
    cat, _, _ = _shown(_screen())
    attendu = [t for t, _ in build_replacement_choices(_screen(), "fr")]
    assert [i.type_id for i in cat] == attendu, ([i.type_id for i in cat],
                                                 attendu)


def test_the_functional_filter_survives_the_picker():
    """Filtre fonctionnel herite : que des ecrans, pas de RTC ni de capteur
    I2C — y compris apres passage par les trois groupes du picker."""
    cat, promos, yours = _shown(_screen())
    tout = {i.type_id for i in cat + promos + yours}
    for intrus in ("bme280", "adafruit-bme280", "ds3231"):
        assert intrus not in tout, (intrus, sorted(tout))


def test_the_escape_hatches_are_offered_on_a_screen():
    """Requalifier un ecran en servo/moteur/module reste possible : ce sont
    les echappatoires inter-categories, elles ne dependent pas du type."""
    _, promos, _ = _shown(_screen())
    ids = {i.type_id for i in promos}
    for t in ("servo", "dc_motor", "module_generic"):
        assert t in ids, (t, sorted(ids))


def test_generic_led_unchanged():
    """'led' n'a pas de famille fonctionnelle -> categorie electrique."""
    cat, _, _ = _shown(_led())
    ids = [i.type_id for i in cat]
    assert ids[0] == "led", ids           # le type courant en tete
    assert any(x in ids for x in ("buzzer", "relay", "neopixel")), ids


def test_non_replaceable_proposes_nothing():
    r = Component(ref="R1", type="resistor", fn_id="fn-1",
                  pins=[Pin("A", "D3")])
    cat, promos, yours = _shown(r)
    assert not (cat or promos or yours), (cat, promos, yours)


TESTS = [test_the_category_column_is_build_replacement_choices_in_order,
         test_the_functional_filter_survives_the_picker,
         test_the_escape_hatches_are_offered_on_a_screen,
         test_generic_led_unchanged,
         test_non_replaceable_proposes_nothing]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
