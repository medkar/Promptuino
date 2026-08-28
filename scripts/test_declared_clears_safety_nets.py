"""QA L4 (2026-08-10) : declarer son composant ne faisait pas taire le message
« composant presume ».

Mesure d'origine. Une broche analogique nue devient un potentiometre 10 kOhm
« presume » -- devinette assumee, annoncee par le warning
`presumed_analog_component`. L'utilisateur decrit alors SON composant via
l'engrenage. Resultat avant correctif :

    APRES  type=custom:mon-capteur  presumed_analog='true'
           warnings = [..., 'presumed_analog_component']

Le schema continuait donc a dire « presume » sur un composant que l'utilisateur
venait de decrire lui-meme -- il contredisait la correction a l'instant ou elle
etait faite.

Deux causes, l'une derriere l'autre :
  - `_apply_declared` ne retirait que 3 attributs de filet
    (`unrecognized`, `presumed_wiring`, `constructor_pins`), pas
    `presumed_analog` ;
  - il ne touchait PAS aux warnings. Le nettoyage existait bien, mais dans
    `declared_apply`, qui n'itere que sur les composants `unrecognized` /
    `presumed_wiring` -- un potentiometre devine n'est ni l'un ni l'autre,
    donc il n'etait jamais regarde.

Les deux listes vivent desormais dans `netlist` (module sans Qt), partagees par
les deux consommateurs.

Run : python scripts/test_declared_clears_safety_nets.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level

import ui.declared_components as dc
from ui.declared_components import DeclaredComponent, DeclaredPin, TYPE_PREFIX
from ui.wiring.ambiguity_dialog import apply_saved_resolution
from ui.wiring.markers import extract_netlist
from ui.wiring.netlist import SAFETY_NET_ATTRS, SAFETY_NET_WARNING_CODES

BARE_ANALOG = ("void setup(){Serial.begin(9600);}\n"
               "void loop(){int v = analogRead(A0); Serial.println(v);}")

_DECL = DeclaredComponent(
    id="mon-capteur", name="Mon capteur", headers=(),
    pins=(DeclaredPin(label="VCC", role="vcc", net="5V"),
          DeclaredPin(label="OUT", role="signal", net="A0"),
          DeclaredPin(label="GND", role="gnd", net="GND")),
    lib="", keywords=("Mon capteur",))


def _presumed_netlist():
    """Le decor reel : un potentiometre PRESUME, tel que `markers` le produit."""
    dc.set_registry([_DECL])
    nl = extract_netlist(BARE_ANALOG, "arduino_uno_r3",
                         prompt="Lis un capteur sur A0")
    comp = next(c for c in nl.components if c.type == "potentiometer")
    assert comp.attributes.get("presumed_analog") == "true"
    assert "presumed_analog_component" in [w.code for w in nl.warnings]
    return nl, comp


def test_declaring_clears_the_attribute_and_the_warning():
    nl, comp = _presumed_netlist()
    try:
        apply_saved_resolution(comp, TYPE_PREFIX + "mon-capteur", nl)
        assert comp.type == "custom:mon-capteur"
        assert comp.attributes.get("presumed_analog") is None
        assert "presumed_analog_component" not in [w.code for w in nl.warnings]
    finally:
        dc.set_registry([])


def test_the_other_warnings_survive():
    """Seuls les avertissements des FILETS partent. `wiring_inferred` decrit le
    schema entier, pas ce composant : l'effacer mentirait dans l'autre sens."""
    nl, comp = _presumed_netlist()
    try:
        apply_saved_resolution(comp, TYPE_PREFIX + "mon-capteur", nl)
        assert "wiring_inferred" in [w.code for w in nl.warnings]
    finally:
        dc.set_registry([])


def test_a_warning_about_ANOTHER_component_is_kept():
    """Le nettoyage est scope au ref. Sans ca, declarer un composant ferait
    taire les filets poses sur tous les autres."""
    nl, comp = _presumed_netlist()
    try:
        nl.add_warning(code="presumed_i2c_wiring", severity="warning",
                       message="autre composant", refs=["ZZ99"])
        apply_saved_resolution(comp, TYPE_PREFIX + "mon-capteur", nl)
        restants = [w for w in nl.warnings if w.code == "presumed_i2c_wiring"]
        assert len(restants) == 1 and restants[0].refs == ["ZZ99"]
    finally:
        dc.set_registry([])


def test_the_two_lists_agree_with_each_other():
    """`presumed_analog` doit etre dans les DEUX listes : l'attribut et son
    warning. En oublier une remettrait exactement le defaut de L4 -- un
    composant nettoye qui garde son message, ou l'inverse."""
    assert "presumed_analog" in SAFETY_NET_ATTRS
    assert "presumed_analog_component" in SAFETY_NET_WARNING_CODES


def test_declared_apply_shares_the_same_set():
    """Les deux consommateurs doivent partager la liste, sinon elle redivergera
    comme elle l'a fait jusqu'au 2026-08-10."""
    from ui.wiring.declared_apply import _OBSOLETE_CODES
    assert _OBSOLETE_CODES is SAFETY_NET_WARNING_CODES


TESTS = [
    test_declaring_clears_the_attribute_and_the_warning,
    test_the_other_warnings_survive,
    test_a_warning_about_ANOTHER_component_is_kept,
    test_the_two_lists_agree_with_each_other,
    test_declared_apply_shares_the_same_set,
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
