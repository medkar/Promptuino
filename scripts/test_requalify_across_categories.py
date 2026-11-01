"""Requalifier un composant vers une AUTRE categorie (TODO #68).

Le besoin, et c'est le plus utile que fasse l'engrenage : << l'app croit voir
une LED sur D5, j'ai en fait un BMP180 >>. Avant ce ticket, le picker
l'affichait et cliquer ne faisait RIEN -- `apply_saved_resolution(led,
"bmp180")` laissait le composant en LED, broches inchangees, sans message.
#67 a supprime le mensonge en cessant de le proposer ; #68 rend la chose vraie.

LA REGLE EST STRUCTURELLE, ET C'EST TOUT L'ENJEU. Un changement de categorie
est autorise quand la cible est AUTOSUFFISANTE : chacune de ses broches a un
role a net fixe (vcc/gnd/sda/scl), donc le remplacement la cable entierement
sans rien emprunter -- ni deviner -- au composant remplace.

⛔ DEUX PISTES ONT ETE ECARTEES SUR MESURE AVANT CELLE-CI, et ces tests
existent pour qu'on ne les retente pas :

  1. lever la garde du moteur. Mesure : `bme280 -> dht22` cable **DATA sur
     GND** (capteur mort), `oled_ssd1306 -> st7735` met **trois broches de
     signal sur GND**.
  2. un critere generique << sur >> (aucune broche sur GND). Mesure : 186 sains
     contre 191 douteux, et il laisse passer `bme280 -> ir_receiver`, qui met
     la broche **OUT sur 5V**.

L'autosuffisance, elle, ne se calibre sur rien : elle se LIT dans le catalogue.
37 types la satisfont, et 180 swaps simules (5 sources tres differentes x 36
cibles) ne produisent aucune broche mal cablee.

Run: python scripts/test_requalify_across_categories.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.ambiguity_dialog import apply_saved_resolution
from ui.wiring.categories import CATEGORY_OF_TYPE, NON_REPLACEABLE, category_of
from ui.wiring.component_replace import (_ROLE_FIXED_NET, is_self_sufficient,
                                         replace_component)
from ui.wiring.layout.component_catalog import CATALOG, role_of
from ui.wiring.netlist import Component, Netlist, Pin
from ui.wiring.replacement_ui import can_replace_with, is_replaceable

# Cinq sources volontairement DIFFERENTES : sortie nue, entree nue, entree
# analogique, famille a brochage fixe, bus proprietaire.
SOURCES = {
    "led":     [("A", "D5"), ("K", "GND")],
    "button":  [("1", "D2"), ("2", "GND")],
    "ldr":     [("1", "A0"), ("2", "GND")],
    "hcsr04":  [("VCC", "5V"), ("TRIG", "D9"), ("ECHO", "D10"), ("GND", "GND")],
    "tm1637":  [("VCC", "5V"), ("GND", "GND"), ("CLK", "D2"), ("DIO", "D3")],
}

# Les quatre cas que les pistes ecartees cassaient, nommes.
CASSES_PAR_LES_FAUSSES_PISTES = ("ds18b20", "dht22", "st7735", "ir_receiver")


def _source(type_id: str) -> Component:
    return Component(ref="U1", type=type_id,
                     pins=[Pin(n, v) for n, v in SOURCES[type_id]],
                     attributes={"_confidence": "low"})


def _cibles_autosuffisantes() -> list[str]:
    return [t for t in sorted(CATEGORY_OF_TYPE)
            if is_self_sufficient(t) and category_of(t) != NON_REPLACEABLE]


# -- Le besoin du ticket ----------------------------------------------------

def test_the_led_that_is_actually_a_bmp180():
    """LE cas fondateur, teste sur le VRAI chemin de production.

    C'est exactement l'appel qui ne faisait rien avant #68 ; il doit
    maintenant rendre un BMP180 correctement cable."""
    c = _source("led")
    nl = Netlist(board_id="uno", components=[c])
    apply_saved_resolution(c, "bmp180", nl)
    obtenu = nl.components[0]
    assert obtenu.type == "bmp180", obtenu.type
    nets = {p.name.lower(): p.net for p in obtenu.pins}
    assert nets["vcc"] == "5V" and nets["gnd"] == "GND", nets
    assert nets["sda"] == "A4" and nets["scl"] == "A5", nets


def test_the_picker_offers_it_again():
    """Sans ca le correctif serait inatteignable : #67 avait retire ces choix
    parce qu'ils ne marchaient pas."""
    assert can_replace_with("led", "bmp180")
    assert can_replace_with("button", "bh1750")
    assert can_replace_with("tm1637", "bmp180")


# -- La regle est structurelle ----------------------------------------------

def test_every_self_sufficient_target_wires_correctly_from_any_source():
    """LA preuve, et elle est exhaustive plutot qu'echantillonnee.

    Si une seule broche d'une seule paire sortait ailleurs que sur un net fixe,
    l'autosuffisance ne serait plus une propriete structurelle mais une
    heuristique -- et il faudrait la retirer, pas la calibrer."""
    fixes = set(_ROLE_FIXED_NET.values())
    mauvais = []
    for src in SOURCES:
        for cible in _cibles_autosuffisantes():
            c = _source(src)
            nl = Netlist(board_id="uno", components=[c])
            if not replace_component(nl, "U1", cible).ok:
                mauvais.append((src, cible, "refuse")); continue
            for p in nl.components[0].pins:
                if p.net not in fixes:
                    mauvais.append((src, cible, p.name, p.net))
    assert not mauvais, mauvais[:6]


def test_self_sufficiency_is_read_from_the_catalogue():
    """Aucune liste ecrite a la main : la reponse se deduit des roles de
    broches. Une table figee derivterait du catalogue au premier ajout."""
    for t in ("bmp180", "bh1750", "aht20"):
        assert is_self_sufficient(t), t
        e = CATALOG[t]
        assert all((role_of(t, i) or "signal") in _ROLE_FIXED_NET
                   for i in range(1, e.pin_count + 1)), t


# -- Ce qui doit RESTER refuse ----------------------------------------------

def test_the_cases_the_rejected_paths_broke_are_still_refused():
    """⛔ Les quatre cas mesures qui produisaient du cablage FAUX. Ce test
    existe pour que la prochaine idee de << elargissons un peu >> rougisse."""
    for cible in CASSES_PAR_LES_FAUSSES_PISTES:
        assert not is_self_sufficient(cible), cible
        c = _source("bme280") if "bme280" in SOURCES else _source("led")
        nl = Netlist(board_id="uno", components=[c])
        assert not replace_component(nl, "U1", cible).ok, cible


def test_a_target_needing_a_signal_pin_is_never_self_sufficient():
    """La frontiere, dite en une phrase : des qu'une broche doit recevoir un
    net que la source seule pourrait fournir, on devine -- donc on refuse."""
    for t in sorted(CATEGORY_OF_TYPE):
        if not is_self_sufficient(t):
            continue
        e = CATALOG.get(t)
        roles = [(role_of(t, i) or "signal") for i in range(1, e.pin_count + 1)]
        assert "signal" not in roles, (t, roles)


# -- Les deux autorites ne doivent pas diverger -----------------------------

def test_the_predicate_and_the_engine_never_disagree():
    """LA garde de fond, et elle vise une erreur que ce depot a commise TROIS
    fois : #62 (deux autorites sur << remplacable >>), #67 (mon propre predicat
    rouvrait par la recherche ce que l'autre bloquait), et celle-ci.

    Le predicat de l'UI et le moteur repondent a la meme question. S'ils
    divergent, l'un des deux ment : soit le picker propose ce qui echouera,
    soit il cache ce qui marcherait."""
    ecarts = []
    for src in SOURCES:
        for cible in sorted(CATEGORY_OF_TYPE):
            if cible == src or not is_replaceable(src):
                continue
            c = _source(src)
            nl = Netlist(board_id="uno", components=[c])
            moteur = replace_component(nl, "U1", cible).ok
            predicat = can_replace_with(src, cible)
            # Les cinq requalifications passent par un transform dedie, jamais
            # par le moteur : les comparer ici mesurerait un chemin mort.
            from ui.wiring.replacement_ui import CROSS_CATEGORY_PROMOTIONS
            if cible in CROSS_CATEGORY_PROMOTIONS:
                continue
            if moteur != predicat:
                ecarts.append((src, cible, "moteur", moteur, "predicat", predicat))
    assert not ecarts, ecarts[:8]


TESTS = [
    test_the_led_that_is_actually_a_bmp180,
    test_the_picker_offers_it_again,
    test_every_self_sufficient_target_wires_correctly_from_any_source,
    test_self_sufficiency_is_read_from_the_catalogue,
    test_the_cases_the_rejected_paths_broke_are_still_refused,
    test_a_target_needing_a_signal_pin_is_never_self_sufficient,
    test_the_predicate_and_the_engine_never_disagree,
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
