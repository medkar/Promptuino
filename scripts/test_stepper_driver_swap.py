"""Changer de driver pas-a-pas depuis le schema.

Les drivers pas-a-pas sont detectes par SIGNATURE (tache 3) : le code nomme la
puce. Mais une signature peut se tromper de variante -- un breakout A4988 et un
DRV8825 sont broche-a-broche compatibles et se ressemblent -- et surtout, on a
le droit de changer d'avis sur le materiel qu'on possede.

⚠️ **CE FICHIER A ETE RENFORCE LE 2026-08-29, apres une revue qui a trouve six
defauts qu'AUCUN de ses onze tests ne pouvait voir.** La cause etait la meme
partout : les assertions portaient sur des NOMS de broches, ecrits en dur dans
le helper, donc vraies par construction quoi qu'il arrive aux NETS. C'est le
motif << un test incapable d'atteindre son defaut >>, et il a laisse passer un
moteur debranche de son driver (20 fils routes avant le swap, 16 apres). La
regle de ce fichier est desormais : **on assertit sur les nets et sur l'etat
apres reouverture, jamais sur des noms.**

⚠️ **Le chemin de remplacement est DEDIE, et la mesure l'a impose.**
`apply_saved_resolution(driver_a4988, "drv8825")` rend une **LED** : ce
mecanisme ne connait que les transformations de composants ambigus et retombe
sur son defaut pour tout le reste.

⚠️ **Et la CLE de persistance porte un suffixe dedie.** La cle nue d'un driver
est partagee avec le NEMA17 qu'il pilote (les deux remontent a `STEP`), et sur
un TMC2209 UART avec la PILE. Ecrire le type du driver sous cette cle faisait
heriter le moteur et la pile d'une resolution qui n'etait pas la leur : ils
devenaient des LED a la reouverture.
"""
from __future__ import annotations
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

from PyQt6.QtGui import QCursor  # noqa: E402
QCursor.setPos(2000, 2000)

import ui.declared_components as declared_components  # noqa: E402
declared_components.set_registry([])

from ui.wiring import inference  # noqa: E402
from ui.wiring.markers import (  # noqa: E402
    STEPPER_DRIVERS, apply_stepper_driver_swap, build_stepdir_driver_pins,
    extract_netlist,
)

BOARD = "arduino_uno_r3"
CODE_A4988 = """
#include <AccelStepper.h>
AccelStepper stepper(AccelStepper::DRIVER, 2, 3);
void setup() { stepper.setMaxSpeed(1000); }
void loop() { stepper.run(); }
"""
CODE_TMC_UART = """
#include <TMC2209.h>
HardwareSerial & serial_stream = Serial1;
TMC2209 stepper_driver;
void setup() { stepper_driver.setup(serial_stream); }
void loop() {}
"""
_VIVANTS: list = []
_STUDIO: list = []


def _schema(code: str, *, inferer: bool = True):
    nl = extract_netlist(code, BOARD, prompt="", context="")
    if inferer:
        inference.apply_rules(nl)
    return nl


def _driver(nl, type_id: str):
    return next(c for c in nl.components if c.type == type_id)


def _nets(comp) -> dict:
    return {p.name: p.net for p in comp.pins}


def _studio():
    """UN seul StudioView par process (contrainte Qt, cf.
    `test_scoped_edit_persistence.py`), donc les tests qui en ont besoin le
    partagent -- et l'ordre de `TESTS` compte."""
    if not _STUDIO:
        from ui.studio_view import StudioView
        _STUDIO.append(StudioView())
    return _STUDIO[0]


# ── le brochage, un seul endroit le decrit ───────────────────────────────

def test_the_pin_table_lives_in_one_place_for_all_four():
    """⚠️ Renforce le 2026-08-29 : la version d'origine n'appelait JAMAIS le
    detecteur, donc elle affirmait << une seule table >> sans jamais comparer
    a l'autre. Trois tables etaient restees ecrites a la main."""
    from ui.wiring import markers
    src = Path(markers.__file__).read_text(encoding="utf-8")
    # Une table de broches ecrite a la main se reconnait a son `_add(` suivi
    # d'une liste litterale de `Pin(`. La seule toleree est celle du TMC2209
    # UART (cf. le test suivant).
    mains = re.findall(r'_add\(\s*"(\w+)",\s*\n?\s*\[Pin\(', src)
    steppers = [t for t in mains if t in STEPPER_DRIVERS]
    assert steppers == ["tmc2209"], (
        "toute table de driver pas-a-pas doit passer par "
        "`build_stepdir_driver_pins`, sauf celle du TMC2209 UART : %r"
        % (steppers,))
    # Et la table du helper est bien celle que la detection produit.
    p = _nets(_driver(_schema(CODE_A4988, inferer=False), "a4988"))
    ref = {x.name: x.net for x in
           build_stepdir_driver_pins("a4988", "D2", "D3")}
    assert p == ref, (p, ref)


def test_the_uart_table_is_the_only_hand_written_one():
    """Et sa difference est une INFORMATION, pas un oubli : sur un pilotage
    UART les micro-pas ne sont pas cables, donc la valeur honnete est VIDE --
    << je ne sais pas >> -- et non GND comme en step/dir."""
    p = _nets(_driver(_schema(CODE_TMC_UART, inferer=False), "tmc2209"))
    assert p["MS1"] == "" and p["MS2"] == "", p
    helper = {x.name: x.net for x in
              build_stepdir_driver_pins("tmc2209", "D2", "D3")}
    assert helper["MS1"] == "GND", helper


def test_an_unknown_driver_is_refused_loudly():
    """Un type inconnu doit lever, pas rendre un brochage vide qui
    s'afficherait comme un composant sans broches."""
    try:
        build_stepdir_driver_pins("tb6600", "D5", "D4")
    except ValueError:
        return
    raise AssertionError("un driver inconnu doit lever ValueError")


# ── le remplacement ──────────────────────────────────────────────────────

def test_swapping_keeps_the_pins_the_code_named():
    """STEP et DIR viennent du CODE : un swap ne les reinvente pas."""
    nl = _schema(CODE_A4988)
    drv = _driver(nl, "a4988")
    assert apply_stepper_driver_swap(drv, "drv8825") is True
    p = _nets(drv)
    assert drv.type == "drv8825"
    assert p["STEP"] == "D2" and p["DIR"] == "D3", p


def test_swapping_keeps_the_motor_CONNECTED():
    """⚠️ LE test que la version d'origine n'a pas su ecrire.

    Elle assertait des NOMS (`OUT1A` present, `1A` absent) -- vrais par
    construction, puisque le helper les ecrit en dur. Pendant ce temps les
    NETS repartaient vides et le NEMA17 se retrouvait ORPHELIN : 20 fils
    routes avant le swap, 16 apres. Un moteur debranche, sur un schema qui a
    l'air complet.

    Les bobines se reportent PAR POSITION : le moteur garde ses bornes
    1A/1B/2A/2B, c'est la serigraphie du DRIVER qui varie.
    """
    nl = _schema(CODE_A4988)
    drv, nema = _driver(nl, "a4988"), _driver(nl, "nema17")
    avant = [_nets(nema)[n] for n in ("1A", "1B", "2A", "2B")]
    assert all(avant), ("pre-condition : le moteur est relie", avant)
    apply_stepper_driver_swap(drv, "stspin220")
    apres = [_nets(drv)[n] for n in ("OUTA1", "OUTA2", "OUTB1", "OUTB2")]
    assert apres == avant, (
        "les bobines du driver doivent rester sur les nets du moteur : "
        "%r contre %r" % (apres, avant))


def test_swapping_keeps_what_the_code_said_about_ENABLE():
    """`ENA` lu dans le code (`digitalWrite(PIN_ENABLE, LOW)`) retombait a
    GND : le fil vers l'Arduino DISPARAISSAIT du schema alors que le code
    continue de le piloter."""
    nl = _schema(CODE_A4988)
    drv = _driver(nl, "a4988")
    drv.pin("ENA").net = "D7"
    apply_stepper_driver_swap(drv, "drv8825")
    assert _nets(drv)["ENA"] == "D7", _nets(drv)


def test_swapping_keeps_the_microstepping_setting():
    """MS3 retombait a GND, ce qui fait passer 1/16 a 1/8 EN SILENCE. Un
    reglage que l'utilisateur a pose ne doit pas bouger tout seul."""
    nl = _schema(CODE_A4988)
    drv = _driver(nl, "a4988")
    for nom in ("MS1", "MS2", "MS3"):
        drv.pin(nom).net = "5V"
    apply_stepper_driver_swap(drv, "drv8825")
    p = _nets(drv)
    assert (p["MS1"], p["MS2"], p["MS3"]) == ("5V", "5V", "5V"), p


def test_swapping_to_the_same_type_is_a_no_op():
    nl = _schema(CODE_A4988)
    drv = _driver(nl, "a4988")
    assert apply_stepper_driver_swap(drv, "a4988") is False


def test_a_uart_tmc2209_refuses_the_swap_rather_than_inventing_pins():
    """Detecte en UART, il n'a AUCUNE broche de commande. Le swap n'a rien a
    reporter -- en fabriquer serait affirmer ce que le code ne dit pas."""
    nl = _schema(CODE_TMC_UART)
    drv = _driver(nl, "tmc2209")
    assert apply_stepper_driver_swap(drv, "a4988") is False
    assert drv.type == "tmc2209", "le driver ne doit pas avoir change"


def test_the_replacement_never_turns_a_driver_into_a_LED():
    """La garde du defaut MESURE : `apply_saved_resolution` rend une LED sur
    ce meme geste."""
    from ui.wiring.ambiguity_dialog import apply_saved_resolution
    nl = _schema(CODE_A4988)
    temoin = _driver(nl, "a4988")
    apply_saved_resolution(temoin, "drv8825", nl)
    assert temoin.type == "led", (
        "pre-condition de ce test : c'est bien le chemin generique qui "
        "degrade en LED, et c'est pourquoi le swap a le sien")
    nl2 = _schema(CODE_A4988)
    drv = _driver(nl2, "a4988")
    apply_stepper_driver_swap(drv, "drv8825")
    assert drv.type == "drv8825"


# ── l'engrenage et les cards ─────────────────────────────────────────────

def test_a_signature_driver_carries_a_gear():
    """Sans cela l'utilisateur ne peut pas en changer : `is_replaceable` rend
    False pour les quatre (infrastructure), donc c'est l'appartenance aux
    refs editables qui ouvre l'engrenage."""
    from ui.wiring.wiring_diagram_dialog import gear_menu_editable
    sv = _studio()
    nl = _schema(CODE_A4988)
    drv = _driver(nl, "a4988")
    refs = sv._editable_wiring_refs(nl)
    assert drv.ref in refs, (drv.ref, sorted(refs))
    assert gear_menu_editable(drv, drv.ref in refs), "engrenage attendu"


def test_a_driver_that_cannot_be_swapped_carries_NO_gear():
    """Un TMC2209 UART refuse le swap, a juste titre. Mais l'engrenage
    s'ouvrait quand meme : on choisissait, on validait, et RIEN ne bougeait
    sans un mot. Une porte qui ne mene nulle part ment autant qu'un mauvais
    schema."""
    sv = _studio()
    nl = _schema(CODE_TMC_UART)
    drv = _driver(nl, "tmc2209")
    assert drv.ref not in sv._editable_wiring_refs(nl), (
        "aucun engrenage tant qu'il n'y a rien a remplacer")


def test_the_modal_offers_the_four_driver_cards():
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    nl = _schema(CODE_A4988)
    drv = _driver(nl, "a4988")
    dlg = AmbiguityDialog([drv], netlist=nl)
    _VIVANTS.append(dlg)
    cards = dlg._driver_cards.get(drv.ref) or {}
    assert set(cards) == set(STEPPER_DRIVERS), sorted(cards)
    # Le picker de composants n'a PAS sa place ici : un driver n'est pas
    # remplacable par une LED.
    assert drv.ref not in dlg._pickers, "pas de picker sur un driver"


def test_the_modal_preselects_the_CHOICE_not_the_detected_type():
    """Rouvrir l'engrenage sur un driver qu'on venait de remplacer
    reaffichait l'ANCIEN coche : le schema disait DRV8825, la modale disait
    A4988. `initial_choices` existe exactement pour ca et n'etait pas lu."""
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    nl = _schema(CODE_A4988)
    drv = _driver(nl, "a4988")
    dlg = AmbiguityDialog([drv], netlist=nl,
                          initial_choices={drv.ref: "tmc2209"})
    _VIVANTS.append(dlg)
    coche = [t for t, c in dlg._driver_cards[drv.ref].items()
             if getattr(c, "_selected", False)]
    assert coche == ["tmc2209"], coche


# ── le tour complet ──────────────────────────────────────────────────────

def _swap_par_la_modale(sv, cible: str, ref: str):
    from ui.wiring import ambiguity_dialog as ad
    vrai = ad.AmbiguityDialog.exec

    def _exec(self):
        c = next(x for x in self._ambiguous if x.type in STEPPER_DRIVERS)
        self._on_stepper_driver_picked(c.ref, cible)
        return self.DialogCode.Accepted

    ad.AmbiguityDialog.exec = _exec
    try:
        return sv._resolve_wiring_netlist(CODE_A4988, BOARD, "", "", {},
                                          scoped_to_ref=ref)
    finally:
        ad.AmbiguityDialog.exec = vrai


def test_two_swaps_in_a_row_do_not_destroy_the_motor():
    """⚠️ Le defaut le plus grave de la premiere version, et celui que
    `test_the_choice_survives_reopening` ne pouvait pas voir : il ne faisait
    qu'UN swap.

    La cle nue d'un driver est PARTAGEE avec le NEMA17 qu'il pilote (les deux
    remontent a `STEP`). Au second passage, le moteur heritait de la
    resolution du driver, `apply_saved_resolution` ne connaissait pas ce type,
    et le NEMA17 devenait une LED avec resistance serie.
    """
    from ui.wiring import ambiguity_dialog as ad
    sv = _studio()
    ref = _driver(_schema(CODE_A4988), "a4988").ref

    n1 = _swap_par_la_modale(sv, "drv8825", ref)
    types = {c.type for c in n1.components}
    assert "drv8825" in types and "led" not in types, sorted(types)

    n2 = _swap_par_la_modale(sv, "stspin220", ref)
    types = {c.type for c in n2.components}
    assert "stspin220" in types, sorted(types)
    assert "led" not in types, (
        "le NEMA17 a herite de la resolution du driver : %r" % sorted(types))
    assert "nema17" in types, sorted(types)

    # La cle porte bien le suffixe dedie -- c'est LUI qui supprime la
    # collision, et une cle nue qui reapparaitrait la ferait revenir.
    nues = [k for k in sv._wiring_resolutions
            if not k[1].endswith("::_stepper_driver")]
    assert nues == [], sv._wiring_resolutions

    # ── et la REOUVERTURE, modale refusee ───────────────────────────────
    vrai = ad.AmbiguityDialog.exec
    ad.AmbiguityDialog.exec = lambda self: self.DialogCode.Rejected
    try:
        rouvert = sv._resolve_wiring_netlist(CODE_A4988, BOARD, "", "", {})
    finally:
        ad.AmbiguityDialog.exec = vrai
    types = {c.type for c in rouvert.components}
    assert "stspin220" in types, sorted(types)
    assert "led" not in types, ("degradation au rejeu : %r" % sorted(types))
    # Le moteur est toujours BRANCHE apres le tour complet.
    drv = _driver(rouvert, "stspin220")
    nema = _driver(rouvert, "nema17")
    assert [_nets(drv)[n] for n in ("OUTA1", "OUTA2", "OUTB1", "OUTB2")] == \
           [_nets(nema)[n] for n in ("1A", "1B", "2A", "2B")], \
        (_nets(drv), _nets(nema))


def test_a_generic_sketch_raises_no_library_alarm():
    """La fonctionnalite se contredisait elle-meme : un swap A4988 ->
    DRV8825 declenchait << le code ne semble pas inclure DRV8825 >> sur un
    sketch AccelStepper qui pilote deja un DRV8825 sans rien changer.

    ⚠️ La << contre-epreuve >> de la premiere version s'arretait a un booleen
    et n'a jamais verifie qu'un constat SORT. Mesure de revue : sur le cas le
    plus probable (code `DRV8825.h`, choix d'un A4988), il n'en sort AUCUN --
    l'A4988 n'a pas d'entree corpus. Le predicat est donc une condition
    NECESSAIRE au constat, pas suffisante, et ce test le dit au lieu de le
    laisser croire.
    """
    from ui.component_registry import by_id
    from ui.studio_view import (missing_libs_for_resolved,
                                stepper_code_is_driver_agnostic)
    assert stepper_code_is_driver_agnostic(CODE_A4988) is True
    assert stepper_code_is_driver_agnostic(CODE_TMC_UART) is False
    nl = _schema(CODE_A4988)
    drv = _driver(nl, "a4988")
    apply_stepper_driver_swap(drv, "drv8825")
    assert missing_libs_for_resolved(CODE_A4988, [drv]) != [], (
        "pre-condition : la fonction generique signale bien l'absence -- "
        "c'est le FILTRE en amont qui rend le silence, pas elle")
    # Et vers un A4988, aucun constat ne peut sortir : documents=(). Le
    # filtre n'y change donc rien, et le pretendre serait faux.
    assert not by_id("a4988").documents, (
        "si l'A4988 gagne une entree corpus, ce test doit etre repris")


TESTS = [
    test_the_pin_table_lives_in_one_place_for_all_four,
    test_the_uart_table_is_the_only_hand_written_one,
    test_an_unknown_driver_is_refused_loudly,
    test_swapping_keeps_the_pins_the_code_named,
    test_swapping_keeps_the_motor_CONNECTED,
    test_swapping_keeps_what_the_code_said_about_ENABLE,
    test_swapping_keeps_the_microstepping_setting,
    test_swapping_to_the_same_type_is_a_no_op,
    test_a_uart_tmc2209_refuses_the_swap_rather_than_inventing_pins,
    test_the_replacement_never_turns_a_driver_into_a_LED,
    test_a_signature_driver_carries_a_gear,
    test_a_driver_that_cannot_be_swapped_carries_NO_gear,
    test_the_modal_offers_the_four_driver_cards,
    test_the_modal_preselects_the_CHOICE_not_the_detected_type,
    test_two_swaps_in_a_row_do_not_destroy_the_motor,
    test_a_generic_sketch_raises_no_library_alarm,
]


def main() -> None:
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    # Teardown Qt statique apres un StudioView : os._exit reflete les
    # assertions, pas un crash de destruction.
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
