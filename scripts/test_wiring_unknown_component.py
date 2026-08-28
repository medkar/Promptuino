"""Honnetete du wiring pour les composants INCONNUS (revue 2026-07-29).

Le detecteur a trois filets de securite (UART generique, I2C generique,
placeholder universel). Ils rattrapent les #include inconnus, mais presentaient
leurs devinettes comme des certitudes et laissaient le composant non
corrigeable. Ces tests verrouillent le contrat honnete :
  - un include inconnu SANS I2C -> boite non cablee + warning ;
  - un include inconnu AVEC I2C -> cablage PRESUME (jamais signature_detected)
    + warning dedie ;
  - dans les deux cas le composant reste EDITABLE (engrenage) ;
  - un composant que le rendu ne sait pas dessiner le DIT (avant : disparition
    silencieuse).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.markers import extract_netlist, _warn_unrenderable_components
from ui.wiring.netlist import Component, Pin, Netlist
from ui.wiring.replacement_ui import (full_candidate_choices,
                                      is_uncertain_component)

_BOARD = "arduino:avr:uno"

_CODE_UNKNOWN = """
#include <LibInconnue.h>
LibInconnue capteur;
void setup(){ Serial.begin(9600); capteur.begin(); }
void loop(){ Serial.println(capteur.read()); }
"""

_CODE_UNKNOWN_I2C = """
#include <Wire.h>
#include <LibInconnue.h>
LibInconnue capteur;
void setup(){ Wire.begin(); capteur.begin(); }
void loop(){ }
"""


def _one(code):
    nl = extract_netlist(code, _BOARD, prompt="", context="")
    comps = [c for c in nl.components if c.type == "libinconnue"]
    assert len(comps) == 1, [c.type for c in nl.components]
    return nl, comps[0]


def _codes(nl):
    return {w.code for w in nl.warnings}


def test_unknown_include_is_placeholder_and_warns():
    nl, c = _one(_CODE_UNKNOWN)
    assert c.attributes.get("unrecognized") is True
    assert [p.net for p in c.pins] == ["", "", "", ""]   # aucun fil invente
    assert "unwired_unknown_component" in _codes(nl)


def test_presumed_i2c_wiring_is_not_presented_as_certain():
    # Le trou le plus trompeur : le filet I2C cablait VCC/GND/SDA/SCL et
    # marquait signature_detected=True -> une DEVINETTE presentee comme lue
    # dans le code, sans warning ni correction possible.
    nl, c = _one(_CODE_UNKNOWN_I2C)
    assert c.attributes.get("presumed_wiring") is True
    assert c.attributes.get("signature_detected") is False
    assert [p.net for p in c.pins] == ["5V", "GND", "A4", "A5"]
    assert "presumed_i2c_wiring" in _codes(nl)


def test_constructor_pins_are_reported_not_invented():
    # Broches passees au SEUL constructeur d'une lib inconnue : invisibles pour
    # parse_fallback (qui ne voit que pinMode/digitalWrite/analogRead...). On ne
    # peut pas deviner quelle broche fait quoi -> on ne cable RIEN, mais on dit
    # a l'utilisateur ce que le code utilise (le schema doit rester instructif).
    code = """
#include <LibInconnue.h>
LibInconnue capteur(5, 6);
void setup(){ capteur.begin(); }
void loop(){ }
"""
    nl, c = _one(code)
    assert c.attributes.get("constructor_pins") == ["D5", "D6"], c.attributes
    assert [p.net for p in c.pins] == ["", "", "", ""]     # aucun fil invente
    assert "unwired_unknown_component_pins" in _codes(nl)
    msg = next(w.message for w in nl.warnings
               if w.code == "unwired_unknown_component_pins")
    assert "D5" in msg and "D6" in msg


def test_constructor_without_pins_keeps_plain_warning():
    # Constructeur sans broche (ou sans constructeur) -> warning simple, pas de
    # mention de broches inventees.
    nl, c = _one(_CODE_UNKNOWN)
    assert "constructor_pins" not in c.attributes
    assert "unwired_unknown_component" in _codes(nl)


def test_user_defined_class_is_not_reported_as_component():
    # Une classe definie DANS le sketch n'est pas un composant inconnu : sans
    # #include, rien ne doit apparaitre (sinon faux positif sur du code
    # utilisateur parfaitement normal).
    code = """
class MonCompteur { public: MonCompteur(int a, int b){} };
MonCompteur c(5, 6);
void setup(){}
void loop(){}
"""
    nl = extract_netlist(code, _BOARD, prompt="", context="")
    assert [c.type for c in nl.components] == [], [c.type for c in nl.components]


def test_placeholder_is_not_signature_detected():
    _nl, c = _one(_CODE_UNKNOWN)
    assert c.attributes.get("signature_detected") is False


def test_uncertain_components_stay_editable():
    # Le bandeau promet « clique sur l'engrenage pour corriger » : ca doit etre
    # VRAI justement quand l'app s'est probablement trompee.
    for code in (_CODE_UNKNOWN, _CODE_UNKNOWN_I2C):
        _nl, c = _one(code)
        assert is_uncertain_component(c) is True
        ids = [t for t, _ in full_candidate_choices(c)]
        assert ids and ids[0] == "libinconnue", ids       # « garder tel quel »
        for promo in ("led", "buzzer", "servo", "dc_motor", "module_generic"):
            assert promo in ids, (promo, ids)


def test_non_replaceable_stays_empty():
    # Garde-fou : la resistance/pile reste NON proposable (l'ouverture ci-dessus
    # ne doit pas rendre toute l'infrastructure editable).
    r = Component(ref="R1", type="resistor", fn_id="fn-1",
                  pins=[Pin("A", "D3"), Pin("B", "GND")])
    assert full_candidate_choices(r) == []
    assert is_uncertain_component(r) is False


def test_undrawable_component_warns_instead_of_vanishing():
    # 15 broches : ni single-row (2-8, 9, 11, 13) ni DIP (10-40 pair) ->
    # resolve_generic renvoie None et le layout SAUTAIT le composant sans aucune
    # trace.
    nl = Netlist(board_id=_BOARD, components=[
        Component(ref="U15", type="truc_15_broches", fn_id="fn-1",
                  pins=[Pin(str(i + 1), f"D{i + 2}") for i in range(15)])
    ])
    _warn_unrenderable_components(nl)
    assert "undrawable_component" in _codes(nl)


def test_drawable_components_do_not_warn():
    # Pas de faux positif sur les composants normaux (4 broches -> single-row,
    # types catalogues).
    nl = Netlist(board_id=_BOARD, components=[
        Component(ref="U1", type="libinconnue", fn_id="fn-1",
                  pins=[Pin(str(i + 1), "") for i in range(4)]),
        Component(ref="D1", type="led", fn_id="fn-1",
                  pins=[Pin("A", "D3"), Pin("K", "GND")]),
    ])
    _warn_unrenderable_components(nl)
    assert "undrawable_component" not in _codes(nl)


_CODE_BARE_ANALOG = """
void setup(){ Serial.begin(9600); }
void loop(){ int v = analogRead(A0); Serial.println(v); }
"""


def _analog(prompt=""):
    """Netlist + the single component born from a bare analogRead."""
    nl = extract_netlist(_CODE_BARE_ANALOG, _BOARD, prompt=prompt, context="")
    assert len(nl.components) == 1, [c.type for c in nl.components]
    return nl, nl.components[0]


def test_a_bare_analog_pin_is_a_guess_and_says_so():
    # Le 4e filet, oublie par la revue 2026-07-29 : une broche analogique nue
    # devenait un potentiometre 10k entierement cable, sans le moindre signe
    # que c'etait une supposition.
    nl, c = _analog()
    assert c.type == "potentiometer"
    assert c.attributes.get("presumed_analog") == "true"
    assert "presumed_analog_component" in _codes(nl)


def test_a_named_potentiometer_is_not_a_guess():
    # Le prompt corrobore : plus de supposition, donc plus de warning.
    nl, c = _analog("lis un potentiometre sur A0")
    assert c.type == "potentiometer"
    assert "presumed_analog" not in c.attributes
    assert "presumed_analog_component" not in _codes(nl)


def test_a_recognised_analog_subtype_is_not_a_guess():
    nl, c = _analog("lis une photoresistance sur A0")
    assert c.type == "ldr", c.type
    assert "presumed_analog" not in c.attributes
    assert "presumed_analog_component" not in _codes(nl)


def test_an_unknown_part_on_an_analog_pin_stays_a_guess():
    # Le cas qui a remonte le probleme : l'utilisateur NOMME un composant que
    # l'app ne connait pas. Rien ne corrobore un potentiometre -- le dire.
    nl, c = _analog("lis mon capteur AS7341 sur A0")
    assert c.attributes.get("presumed_analog") == "true"
    assert "presumed_analog_component" in _codes(nl)


def test_a_declared_component_clears_the_presumed_analog_warning():
    # Une fois que l'utilisateur a decrit son composant, le warning ne decrit
    # plus rien : il doit disparaitre comme ceux des trois autres filets.
    from ui.wiring.declared_apply import _OBSOLETE_CODES
    assert "presumed_analog_component" in _OBSOLETE_CODES


def _info_refs_and_tips(nl):
    from ui.wiring.wiring_diagram_dialog import WiringDiagramDialog
    dlg = WiringDiagramDialog.__new__(WiringDiagramDialog)   # pas de __init__
    dlg._netlist = nl
    refs = dlg._compute_info_refs()
    return refs, dlg._compute_info_tooltips(refs)


def test_all_three_safety_nets_carry_the_attention_chip():
    """QA E2 (2026-08-08). E1 (include inconnu) portait deja la puce
    d'attention, mais E2 -- le cablage I2C PRESUME, que la doc qualifie
    elle-meme de « le plus trompeur » -- n'en avait PAS. Et `presumed_analog`,
    ajoute trois jours plus tot, etait branche au panneau d'instructions mais
    jamais a la puce visuelle. L'inverse exact de ce qu'il faudrait."""
    # E1 : include inconnu, non I2C
    nl, c = _one(_CODE_UNKNOWN)
    refs, _ = _info_refs_and_tips(nl)
    assert c.ref in refs, refs

    # E2 : cablage I2C presume
    nl, c = _one(_CODE_UNKNOWN_I2C)
    refs, _ = _info_refs_and_tips(nl)
    assert c.ref in refs, f"{c.ref} absent de {refs} (le cas le plus trompeur)"

    # Broche analogique nue
    nl, c = _analog()
    refs, _ = _info_refs_and_tips(nl)
    assert c.ref in refs, refs


def test_the_hover_says_the_problem_instead_of_inviting_to_click():
    """Decision utilisateur : l'info doit etre AU SURVOL. L'infobulle etait
    une chaine generique (« clic pour comprendre ») identique pour tous les
    composants ; elle porte desormais le texte du warning -- deja ecrit, deja
    traduit, et qui dit exactement la bonne chose."""
    nl, c = _one(_CODE_UNKNOWN_I2C)
    refs, tips = _info_refs_and_tips(nl)
    tip = tips.get(c.ref, "")
    assert tip, tips
    assert "présumé" in tip.lower() or "presume" in tip.lower(), tip
    assert "clic" not in tip.lower(), f"infobulle restee generique : {tip}"
    # Pas de gras markdown brut dans une infobulle Qt.
    assert "**" not in tip, tip


def test_warning_labels_exist_in_all_languages():
    from ui.wiring.instructions import _WARNING_TEMPLATES
    for code in ("presumed_i2c_wiring", "undrawable_component",
                 "unwired_unknown_component_pins",
                 "presumed_analog_component"):
        tpl = _WARNING_TEMPLATES[code]
        for lang in ("fr", "en", "es", "it"):
            assert lang in tpl and len(tpl[lang]) > 20, (code, lang)


TESTS = [
    test_unknown_include_is_placeholder_and_warns,
    test_constructor_pins_are_reported_not_invented,
    test_constructor_without_pins_keeps_plain_warning,
    test_user_defined_class_is_not_reported_as_component,
    test_presumed_i2c_wiring_is_not_presented_as_certain,
    test_placeholder_is_not_signature_detected,
    test_uncertain_components_stay_editable,
    test_non_replaceable_stays_empty,
    test_undrawable_component_warns_instead_of_vanishing,
    test_drawable_components_do_not_warn,
    test_a_bare_analog_pin_is_a_guess_and_says_so,
    test_a_named_potentiometer_is_not_a_guess,
    test_a_recognised_analog_subtype_is_not_a_guess,
    test_an_unknown_part_on_an_analog_pin_stays_a_guess,
    test_a_declared_component_clears_the_presumed_analog_warning,
    test_all_three_safety_nets_carry_the_attention_chip,
    test_the_hover_says_the_problem_instead_of_inviting_to_click,
    test_warning_labels_exist_in_all_languages,
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
