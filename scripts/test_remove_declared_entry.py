"""« Retirer de ma librairie » : le disque suivait, l'ecran non (2026-08-10).

`DeclareComponentDialog._on_remove` supprimait bien l'entree de
`components.json` et posait `self.removed = True`. Mais ce drapeau n'etait LU
NULLE PART — deux occurrences dans tout le depot, l'initialisation et
l'ecriture. Consequence dans la modale d'ambiguite : elle continuait d'offrir
le type `custom:` disparu, et le choisir ne faisait plus rien du tout
(`_apply_declared` -> `find_by_type` -> None -> « on laisse la boite telle
quelle »).

Le besoin est reel : pendant la QA, une entree creee par inadvertance a du etre
supprimee EN LIGNE DE COMMANDE, faute que le bouton fasse effet. Un utilisateur
n'a pas cette issue.

Ces tests exercent la logique de repli SANS construire la modale : ce qui est
teste est la DECISION (quel type disparait, sur quoi retomber), pas la mise en
page. Depuis le passage aux cards (2026-08-13) le choix ne vit plus dans un
QComboBox mais dans un `ComponentPicker` — on lui en donne un VRAI, pour que
« l'entree a disparu de la bibliotheque » se rejoue comme en vrai (le picker
relit le registre) au lieu d'etre mime par un faux objet.

Run : python scripts/test_remove_declared_entry.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level

import ui.declared_components as dc
from ui.wiring.ambiguity_dialog import AmbiguityDialog
from ui.wiring.component_picker import ComponentPicker
from ui.wiring.netlist import Component, Pin

REF = "U1"
CUSTOM = f"{dc.TYPE_PREFIX}mon-capteur"

_VIVANTS: list = []


def _entry():
    return dc.DeclaredComponent(
        id="mon-capteur", name="Mon capteur", headers=("MonCapteur.h",),
        pins=(dc.DeclaredPin("VCC", "power", "5V"),
              dc.DeclaredPin("GND", "ground", "GND")),
        lib="", keywords=("mon capteur",))


class _Spy:
    """AmbiguityDialog sans `__init__` : `_forget_declared_type` ne touche que
    le picker et `_on_type_toggled`, qu'on intercepte pour observer la
    decision."""
    def __init__(self, picker=None):
        self.toggled: list = []
        self._pickers = {REF: picker} if picker is not None else {}

    def _on_type_toggled(self, ref, type_id):
        self.toggled.append((ref, type_id))


def _picker(component_type: str = "led", declared=True) -> ComponentPicker:
    """Un vrai picker, ouvert sur un composant dont l'entree perso existe."""
    dc.set_registry([_entry()] if declared else [])
    comp = Component(ref=REF, type=component_type,
                     pins=[Pin("A", "D5"), Pin("K", "GND")],
                     attributes={"_confidence": "low"})
    picker = ComponentPicker(comp, "fr")
    _VIVANTS.append(picker)
    return picker


def _forget(picker, type_id=CUSTOM) -> _Spy:
    """Simule ce que fait le formulaire : l'entree quitte la bibliotheque,
    puis la modale est prevenue."""
    dc.set_registry([])
    spy = _Spy(picker)
    AmbiguityDialog._forget_declared_type(spy, REF, type_id)
    return spy


def test_the_removed_type_leaves_the_list():
    picker = _picker()
    picker.select(CUSTOM)
    assert picker.current_type_id() == CUSTOM, "l'entree perso n'etait pas la"
    _forget(picker)
    assert CUSTOM not in picker.visible_type_ids(), picker.visible_type_ids()


def test_the_selection_falls_back_on_the_detector_s_type():
    """`full_candidate_choices` commence par le type que le detecteur avait
    propose, et le picker garde cet ordre : la premiere card est donc l'etat
    d'avant la declaration."""
    picker = _picker()
    picker.select(CUSTOM)
    spy = _forget(picker)
    assert picker.current_type_id() == "led", picker.current_type_id()
    assert spy.toggled[-1] == (REF, "led"), spy.toggled


def test_the_choice_is_announced_so_the_modal_follows():
    """Sans cette annonce, `_chosen_type` garderait un type qui n'existe plus
    — et c'est lui que « Valider » appliquerait."""
    picker = _picker()
    picker.select(CUSTOM)
    assert _forget(picker).toggled, "aucun choix annonce"


def test_removing_a_type_absent_from_the_list_is_harmless():
    """L'appelant passe le type rendu par le formulaire ; s'il ne designe rien
    ici, il ne faut ni planter ni laisser la selection dans le vide."""
    picker = _picker(declared=False)
    avant = picker.visible_type_ids()
    spy = _forget(picker, f"{dc.TYPE_PREFIX}jamais-vu")
    assert picker.visible_type_ids() == avant, picker.visible_type_ids()
    assert picker.current_type_id() == "led"
    assert spy.toggled[-1] == (REF, "led"), spy.toggled


def test_an_empty_picker_does_not_announce_a_choice():
    """Cas limite : rien a proposer (un composant d'infrastructure n'est jamais
    requalifiable) -> ne pas annoncer un type vide, qui remonterait tel quel
    dans `_chosen_type`."""
    picker = _picker(component_type="resistor")
    assert picker.visible_type_ids() == [], picker.visible_type_ids()
    assert _forget(picker).toggled == []


def test_a_dialog_without_a_picker_is_harmless():
    """La section consolidee (moteurs) n'en a pas : le repli ne doit pas
    supposer qu'il y en a toujours un."""
    spy = _Spy()
    AmbiguityDialog._forget_declared_type(spy, REF, CUSTOM)
    assert spy.toggled == []


def test_the_dialog_reports_which_type_disappeared():
    """L'appelant ne peut plus le retrouver apres coup : `find_by_type` ne
    repond plus. Le contrat est donc que la modale le dise."""
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    assert hasattr(DeclareComponentDialog, "_on_remove")
    src = (Path(__file__).resolve().parents[1] / "ui" / "wiring"
           / "declare_component_dialog.py").read_text(encoding="utf-8")
    assert "self.removed_type_id = self._existing.type_id" in src


TESTS = [
    test_the_removed_type_leaves_the_list,
    test_the_selection_falls_back_on_the_detector_s_type,
    test_the_choice_is_announced_so_the_modal_follows,
    test_removing_a_type_absent_from_the_list_is_harmless,
    test_an_empty_picker_does_not_announce_a_choice,
    test_a_dialog_without_a_picker_is_harmless,
    test_the_dialog_reports_which_type_disappeared,
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
