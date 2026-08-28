"""Source UNIQUE des candidats proposables (bare-pin + edition).

Ce fichier s'appelait `test_beginner_advanced_parity.py` : il verrouillait que
deux modales — l'une en tuiles (debutant), l'autre en liste (avance) —
proposent EXACTEMENT le meme ensemble. La modale debutant a ete supprimee le
2026-08-13, cette parite-la n'a plus de sujet, et ses deux tests bases sur
`build_options_for_type` sont partis avec elle plutot que de rester verts
au-dessus d'un catalogue de tuiles que plus rien n'affiche. Le fichier a ete
RENOMME le meme jour : garder un nom qui annonce une parite entre deux modes
alors qu'il n'y a plus qu'un chemin ferait chercher un sujet inexistant.

Ce qui reste est la moitie qui compte, et qui vaut maintenant pour TOUS les
modes : `full_candidate_choices` est la source unique, les promotions
inter-categories n'ont qu'une definition, et ce que le picker affiche est
exactement ce que cette source rend.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)

from ui.wiring.netlist import Component, Pin
from ui.wiring.replacement_ui import (
    build_replacement_choices, full_candidate_choices, CROSS_CATEGORY_PROMOTIONS)
from ui.wiring.ambiguity_dialog import _CANDIDATES


def _led():
    return Component(ref="D1", type="led", fn_id="fn-1", pins=[Pin("A", "D3")])


def _screen():
    return Component(ref="U1", type="oled_ssd1306", fn_id="fn-1",
                     pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                           Pin("SDA", "A4"), Pin("SCL", "A5")])


def _advanced_set(component):
    """Ce que le modal avance (_build_classic_section) montre : meme-categorie
    + promotions _CANDIDATES."""
    same = {t for t, _ in build_replacement_choices(component, "fr")}
    return same | {t for _, t, _ in _CANDIDATES}


def test_promotion_lists_do_not_diverge():
    # Forcing function : la liste de promotions du helper == celle du modal avance.
    assert list(CROSS_CATEGORY_PROMOTIONS) == [t for _, t, _ in _CANDIDATES], \
        (list(CROSS_CATEGORY_PROMOTIONS), [t for _, t, _ in _CANDIDATES])


def test_full_candidate_choices_dedup_and_order():
    ch = full_candidate_choices(_led(), "fr")
    ids = [t for t, _ in ch]
    assert ids == list(dict.fromkeys(ids)), ids           # pas de doublon
    assert ids[0] == "led"                                  # type courant en tete
    assert set(ids) == _advanced_set(_led())               # meme ensemble que l'avance


def test_full_candidate_choices_empty_for_non_replaceable():
    r = Component(ref="R1", type="resistor", fn_id="fn-1", pins=[Pin("A", "D3")])
    assert full_candidate_choices(r, "fr") == []


def test_screen_keeps_family_plus_escape_hatches():
    # Re-pointe le 2026-08-13 de `build_options_for_type` (tuiles) vers la
    # source vivante : c'est la meme affirmation, sur ce qui est reellement
    # propose aujourd'hui.
    ids = {t for t, _ in full_candidate_choices(_screen(), "fr")}
    assert "sh1106" in ids                                  # meme famille ecran
    assert "bme280" not in ids and "ds3231" not in ids      # pas les autres capteurs I2C
    for t in ("servo", "dc_motor", "module_generic"):       # escape hatches (parite avance)
        assert t in ids, (t, sorted(ids))


def test_advanced_picker_consumes_single_source():
    # Revue 2026-07-29 #8 : le modal avance doit CONSOMMER
    # full_candidate_choices (source unique de la parite) — plus de
    # reconstruction inline des promotions depuis _CANDIDATES, qui pouvait
    # diverger silencieusement avec les tests au vert.
    #
    # Depuis le passage aux cards (2026-08-13), la liste deroulante est un
    # `ComponentPicker` et la consommation est INDIRECTE : elle passe par
    # `picker_logic.visible_items`. On verifie donc ce qui compte vraiment —
    # l'ENSEMBLE propose, champ de recherche vide — plutot que la presence
    # d'un appel dans un fichier : un intermediaire de plus ne doit ni ajouter
    # ni perdre un candidat.
    from ui.wiring.picker_logic import visible_items
    for comp in (_led(), _screen()):
        groups = visible_items(comp, "", "fr")
        proposes = {i.type_id for g in (groups.category, groups.promotions,
                                        groups.yours) for i in g}
        attendu = {t for t, _ in full_candidate_choices(comp, "fr")}
        assert proposes == attendu, (comp.type, proposes ^ attendu)
        # Le type courant reste en tete de sa colonne : le picker s'ouvre sur
        # ce que le detecteur a cru voir.
        assert groups.category[0].type_id == comp.type, groups.category

    src = (Path(__file__).resolve().parents[1]
           / "ui" / "wiring" / "ambiguity_dialog.py").read_text(encoding="utf-8")
    assert "ComponentPicker(c, lang_manager.lang)" in src, \
        "la section classique avancee ne construit plus le picker"
    # L'ancienne boucle inline (promotions ajoutees une a une depuis
    # _CANDIDATES) ne doit pas revenir.
    assert "for label, type_id, _transform in _CANDIDATES" not in src


TESTS = [
    test_promotion_lists_do_not_diverge,
    test_full_candidate_choices_dedup_and_order,
    test_full_candidate_choices_empty_for_non_replaceable,
    test_screen_keeps_family_plus_escape_hatches,
    test_advanced_picker_consumes_single_source,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
