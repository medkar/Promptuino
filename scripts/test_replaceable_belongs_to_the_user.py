"""<< Remplacable >> veut dire << il est a l'utilisateur >> (TODO #62).

Le defaut repare : `NON_REPLACEABLE` servait de fourre-tout a DEUX choses que
rien ne distinguait dans le code --

  1. l'infrastructure que l'APP ajoute elle-meme (resistance de limitation,
     pile, driver deduit d'un moteur). Legitime : l'utilisateur ne l'a pas
     choisie, lui proposer de la remplacer n'aurait pas de sens.
  2. les bus proprietaires SANS pair d'echange (TM1637, HX711, registre a
     decalage...). Le motif ecrit etait << pas de pair de swap >>, autrement
     dit : on ne leur a pas trouve d'equivalent, DONC on a interdit le geste.

Ce n'est pas la meme chose, et la confusion coutait cher : si le detecteur se
trompait sur un TM1637, l'utilisateur n'avait AUCUN recours -- precisement dans
le cas ou l'app avait eu tort.

⚠️ CE QUI REND CE FICHIER NECESSAIRE : la suite complete est restee VERTE quand
les 8 types ont change de camp. **Aucun test ne verrouillait l'ancien
comportement.** Ces gardes sont donc la seule protection de la nouvelle regle,
et `test_the_two_authorities_agree` est celle qui aurait attrape #62 des
l'origine.

Run: python scripts/test_replaceable_belongs_to_the_user.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.categories import (CATEGORY_OF_TYPE, NON_REPLACEABLE,
                                  NO_SWAP_PEER, category_of)
from ui.wiring.component_replace import replace_component
from ui.wiring.netlist import Component, Netlist, Pin
from ui.wiring.replacement_ui import (build_replacement_choices,
                                      full_candidate_choices, is_replaceable)

# Ce que l'APP ajoute elle-meme. C'est la SEULE famille qui reste non
# remplacable -- decision utilisateur du 2026-08-26, reconduite telle quelle.
#
# ⚠️ Le ticket annoncait << 5 >>. Il y en a DOUZE : la resistance, la pile, et
# les DIX drivers inferes. Le 5 du ticket designait en fait l'autre groupe,
# celui des types sans famille fonctionnelle ni pair.
INFRASTRUCTURE = {
    "resistor", "battery_external",
    "l298n", "l293d", "l293d_module", "uln2003", "a4988", "drv8825",
    "tb6612fng", "drv8833", "stspin220", "tmc2209",
}

# A l'utilisateur, mais sans pair d'echange dans le catalogue.
SANS_PAIR = {
    "led_matrix", "tm1637", "tm1638", "hx711", "sr74hc595",
    "adxl335", "dotstar", "ir_reflective_sensor",
}


def _composant(type_id: str) -> Component:
    return Component(ref="U1", type=type_id, pins=[])


# -- la regle --------------------------------------------------------------

def test_only_what_the_app_adds_itself_is_non_replaceable():
    """La liste `NON_REPLACEABLE` ne doit contenir QUE de l'infrastructure.

    Y ranger un composant que l'utilisateur possede, c'est lui retirer son
    recours -- le defaut de ce ticket."""
    reel = {t for t, c in CATEGORY_OF_TYPE.items() if c == NON_REPLACEABLE}
    assert reel == INFRASTRUCTURE, {
        "en trop": sorted(reel - INFRASTRUCTURE),
        "manquants": sorted(INFRASTRUCTURE - reel),
    }


def test_the_infrastructure_keeps_its_gear_muted():
    """Reconduit explicitement : c'est la seule chose que #62 ne change pas."""
    for t in sorted(INFRASTRUCTURE):
        assert not is_replaceable(t), t
        assert full_candidate_choices(_composant(t), "fr") == [], t


def test_a_component_the_user_owns_is_always_correctable():
    """Le coeur du ticket. Ces huit types n'avaient AUCUN recours."""
    for t in sorted(SANS_PAIR):
        assert is_replaceable(t), t
        assert full_candidate_choices(_composant(t), "fr"), t


# -- la garde qui aurait attrape le defaut ---------------------------------

def test_the_two_authorities_agree():
    """LA garde de fond, et elle balaie tout le catalogue.

    `build_replacement_choices` consulte d'abord la famille FONCTIONNELLE et
    ignore la categorie ; `is_replaceable` ne regardait que la categorie. Les
    deux repondaient donc a la meme question et se contredisaient : mesure du
    2026-08-26, un `tm1637` avait 9 candidats et un `tm1638` 17 -- que
    l'engrenage, coupe par l'autre autorite, n'a jamais pu montrer.

    Des candidats calcules qu'aucun ecran ne peut afficher : c'est ca, le
    defaut, et c'est ca que ce test interdit de reintroduire."""
    muets = [t for t in CATEGORY_OF_TYPE
             if full_candidate_choices(_composant(t), "fr")
             and not is_replaceable(t)]
    assert not muets, muets


# -- l'absence de pair se dit par une liste vide ---------------------------

def test_no_swap_peer_never_groups_its_members():
    """⛔ Le piege verifie a l'ecriture. `NO_SWAP_PEER` n'est pas une classe
    electrique, c'est l'ABSENCE de classe : ses membres n'ont en commun que de
    n'avoir aucun pair.

    Les grouper (par un simple `candidates_in`) proposait de remplacer un HX711
    -- un pont de jauge -- par un TM1637 -- un afficheur 7 segments. La liste
    sortait bien les huit d'un coup. Ce serait un defaut PIRE que l'engrenage
    muet qu'on repare."""
    for t in sorted(SANS_PAIR):
        meme_cat = [x for x, _ in build_replacement_choices(_composant(t), "fr")
                    if category_of(x) == NO_SWAP_PEER]
        # Seuls des membres d'une meme FAMILLE fonctionnelle sont admis
        # (tm1637/tm1638/led_matrix sont tous des afficheurs) ; jamais le
        # fourre-tout complet.
        assert set(meme_cat) - {t} != SANS_PAIR - {t}, (t, meme_cat)
    # Le cas le plus parlant, teste nommement.
    hx = [x for x, _ in build_replacement_choices(_composant("hx711"), "fr")]
    assert hx == ["hx711"], hx


def test_a_component_without_a_peer_still_gets_escape_hatches():
    """Une liste de pairs vide n'est pas un cul-de-sac : le picker montre les
    echappatoires inter-categories et la bibliotheque de l'utilisateur."""
    for t in ("hx711", "adxl335", "sr74hc595"):
        choix = [x for x, _ in full_candidate_choices(_composant(t), "fr")]
        assert len(choix) > 1, (t, choix)
        assert choix[0] == t, (t, choix)


# -- le moteur de swap ne casse pas ----------------------------------------

def test_the_swap_engine_accepts_the_newly_opened_types():
    """L'avertissement du ticket : rendre un type remplacable ne doit pas
    casser `component_replace`, qui apparie les broches par role."""
    def swap(depart: str, cible: str):
        c = Component(ref="U1", type=depart,
                      pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                            Pin("CLK", "D2"), Pin("DIO", "D3")])
        return replace_component(Netlist(board_id="uno", components=[c]),
                                 "U1", cible)

    assert swap("tm1637", "tm1638").ok
    assert swap("tm1637", "led_matrix").ok
    # Et l'infrastructure reste refusee par le moteur lui-meme, pas seulement
    # par l'UI -- deux verrous valent mieux qu'un sur cette regle.
    assert not swap("tm1637", "a4988").ok


TESTS = [
    test_only_what_the_app_adds_itself_is_non_replaceable,
    test_the_infrastructure_keeps_its_gear_muted,
    test_a_component_the_user_owns_is_always_correctable,
    test_the_two_authorities_agree,
    test_no_swap_peer_never_groups_its_members,
    test_a_component_without_a_peer_still_gets_escape_hatches,
    test_the_swap_engine_accepts_the_newly_opened_types,
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
