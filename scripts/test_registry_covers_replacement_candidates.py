"""Tout candidat proposable par la modale d'ambiguite doit avoir une fiche.

39 % des types proposables n'avaient AUCUNE fiche dans build_index() : leur
card aurait ete vide. Ce script est la garde qui empeche le trou de revenir.

Run : python scripts/test_registry_covers_replacement_candidates.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.declared_components as dc
import ui.registry_lookup as rl

dc.set_registry([])   # jamais le disque de la machine
# Meme discipline que test_component_index.py : build_index() lit aussi le
# cache de lookup (registry-cache.json, un VRAI fichier de la machine). Un
# token cache egal a un id candidat ferait passer la garde par chance sur une
# machine et pas sur l'autre.
rl.set_cache_for_tests({})

from ui.component_index import build_index
from ui.wiring import categories as cats
from ui.wiring.categories import CATEGORY_OF_TYPE, NON_REPLACEABLE
from ui.wiring.replacement_catalog import REPLACEMENT_CATALOG
from ui.component_registry import (NON_COMPONENT_CATALOG_TYPES,
                                   NON_COMPONENT_WIRING_TYPES)

EXEMPT = NON_COMPONENT_CATALOG_TYPES | NON_COMPONENT_WIRING_TYPES

BARE_PIN = (cats.SINGLE_OUTPUT, cats.ANALOG_IN, cats.DIGITAL_IN)

# Tache 3 (2026-08-12) : la garde couvre desormais TOUTES les categories
# proposables, pas seulement la broche nue. Les composants sur bus (I2C, SPI,
# UART, ultrason) sont ceux qui manquaient le plus : un BMP180 sans fiche
# aurait affiche une card vide dans la modale unifiee.
#
# DERIVE, jamais recopie a la main (revue 2026-08-12) : une liste ecrite en dur
# est exactement le genre de derive que ce fichier existe pour attraper -- une
# 12e categorie ajoutee a categories.py resterait hors garde en silence.
# Verifie a l'ecriture : la derivation rend les 11 memes categories que la
# liste manuelle qu'elle remplace.
ALL_CATS = tuple(sorted(set(CATEGORY_OF_TYPE.values()) - {NON_REPLACEABLE}))


def _merge_into_did_its_job():
    """L'invariant que le plancher numerique pretendait defendre.

    `candidates_in` lit `CATEGORY_OF_TYPE`, que `replacement_catalog.merge_into`
    remplit au chargement. Si ce remplissage cassait, les candidats
    tomberaient aux seuls types cables en dur et la garde ne verifierait plus
    grand-chose -- d'ou un plancher. Mais le plancher etait INERTE (mesure en
    revue 2026-08-12) : 134 candidats aujourd'hui, 73 avec un `merge_into`
    entierement casse, soit toujours au-dessus du seuil de 60. Il serait reste
    vert pendant que les 60 types cures du catalogue ne sont plus verifies du
    tout.

    L'invariant reel n'est pas un compte, c'est une appartenance : CHAQUE id du
    catalogue cure doit avoir atteint `CATEGORY_OF_TYPE`. Ca, un `merge_into`
    casse le fait rougir immediatement, quel que soit le nombre de types
    cables ailleurs.
    """
    missing = sorted({t for t, _cat, _lbl in REPLACEMENT_CATALOG
                      if t not in CATEGORY_OF_TYPE})
    assert not missing, (
        "merge_into n'a pas fait son travail -- ces types cures n'ont plus de "
        f"categorie, donc plus aucun candidat ne les propose : {missing}")


def _missing_for(categories):
    index_keys = {i.key for i in build_index()}
    missing = []
    for cat in categories:
        for t in cats.candidates_in(cat):
            if t not in index_keys and t not in EXEMPT:
                missing.append((cat, t))
    return missing


def test_every_bare_pin_candidate_has_a_card():
    _merge_into_did_its_job()   # sinon la garde ci-dessous serait vide de sens
    missing = _missing_for(BARE_PIN)
    assert not missing, (
        f"candidats sans fiche : {missing} -- pour chacun, ajouter une "
        "entree Component a ui/component_registry.py (bloc Lot A)")


def test_bare_pin_newcomers_say_no_library():
    """Decision utilisateur 2026-08-12 : ces composants ne necessitent pas
    de librairie. La card doit dire 'aucune librairie a installer'."""
    newcomers = {"acs712", "buttonpad", "dip_switch", "force_sensor",
                 "hall_sensor", "joystick", "light_sensor", "load_cell",
                 "passive_buzzer", "reed_switch", "rgb_led", "slide_switch",
                 "slider", "soil_moisture", "solenoid", "speaker",
                 "tilt_switch", "toggle_switch", "touch_sensor"}
    by_key = {i.key: i for i in build_index()}
    for t in sorted(newcomers):
        assert t in by_key, f"{t} absent de l'index"
        assert by_key[t].library == "none", (t, by_key[t].library)
        assert by_key[t].name != t, f"{t} : nom = id brut, libelle manquant"
        assert by_key[t].description, f"{t} : description vide"


def test_every_replacement_candidate_has_a_card():
    _merge_into_did_its_job()
    # Les 11 categories doivent etre couvertes, pas une poignee : la
    # derivation ne doit pas pouvoir se vider sans qu'on le voie.
    assert len(ALL_CATS) >= 11, ALL_CATS
    missing = _missing_for(ALL_CATS)
    assert not missing, (
        f"candidats sans fiche : {missing} -- pour chacun, ajouter une "
        "entree Component a ui/component_registry.py (bloc Lot A)")


def test_cross_category_promotions_have_cards():
    from ui.wiring.replacement_ui import CROSS_CATEGORY_PROMOTIONS
    index_keys = {i.key for i in build_index()}
    missing = [t for t in CROSS_CATEGORY_PROMOTIONS
               if t not in index_keys and t not in EXEMPT]
    assert not missing, f"promotions sans fiche : {missing}"


TESTS = [
    test_every_bare_pin_candidate_has_a_card,
    test_bare_pin_newcomers_say_no_library,
    test_every_replacement_candidate_has_a_card,
    test_cross_category_promotions_have_cards,
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
