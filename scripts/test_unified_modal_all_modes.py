"""Une SEULE modale d'ambiguite, et un SEUL comportement, quel que soit le mode.

Le mode (Debutant / Intermediaire / Avance) n'est qu'un affichage : le prompt
envoye a l'IA et l'etat du projet sont identiques entre modes (regle CLAUDE.md).
`studio_view` violait cette regle a deux endroits, tous deux supprimes le
2026-08-13 :

- une branche `if is_beginner:` de 236 lignes qui construisait une AUTRE modale ;
- un « peel-off » servo qui ne tournait qu'en debutant et ecrivait donc des
  `_wiring_resolutions` DIFFERENTS d'un mode a l'autre pour le meme code.

Ce script verrouille les deux, plus la parite de persistance (les choix ecrits
par l'ancienne modale debutant se rejouent a l'identique) et la condition de
l'avertissement « code moteur sans moteur choisi », portee sur le chemin commun.

Run : python scripts/test_unified_modal_all_modes.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.declared_components as dc

dc.set_registry([])   # jamais le disque de la machine


def test_no_beginner_branch_remains():
    """Verrou par la source : plus aucun aiguillage de modale par mode."""
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    assert "VisualAmbiguityDialog" not in src
    assert "visual_ambiguity_dialog" not in src


def test_no_mode_test_survives_in_the_resolution_path():
    """La garde qui COMPTE. Verifier l'absence de `VisualAmbiguityDialog` ne
    prouve rien sur le mode : le peel-off servo, lui, ne nommait aucune modale
    et faisait pourtant diverger l'etat du projet entre debutant et avance.

    On interdit donc toute comparaison de `_current_mode` dans le corps de
    `_resolve_wiring_netlist` — la methode qui decide du cablage et qui ECRIT
    `_wiring_resolutions`. Ailleurs dans le fichier, le mode reste legitime :
    c'est un affichage.
    """
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    start = src.index("    def _resolve_wiring_netlist(")
    # Fin = debut de la methode suivante au meme niveau d'indentation.
    end = src.index("\n    def ", start + 10)
    body = src[start:end]
    offenders = [ln.strip() for ln in body.splitlines()
                 if "_current_mode" in ln]
    assert not offenders, (
        "le cablage ne doit dependre d'AUCUN mode : le mode est un affichage, "
        "le netlist et _wiring_resolutions sont l'etat du projet. "
        f"Trouve : {offenders}")


def test_beginner_resolutions_reapply_identically():
    """Parite : les choix persistes par l'ANCIENNE modale debutant se
    rejouent a l'identique. La forme des cles ne change pas :
    (fn_id, net) -> type_id, driver sous (fn_id, net + '::_driver')."""
    saved = {("fn-1", "D5"): "buzzer",
             ("fn-1", "D6"): "dc_motor",
             ("fn-1", "D6::_driver"): "l298n"}
    from ui.wiring.ambiguity_dialog import apply_saved_resolution
    from ui.wiring.netlist import Component, Netlist, Pin

    # Le type simple.
    c1 = Component(ref="D1", type="led",
                   pins=[Pin("A", "D5"), Pin("K", "GND")],
                   attributes={"category": "single_output",
                               "_confidence": "low"})
    nl1 = Netlist(board_id="", components=[c1])
    apply_saved_resolution(c1, saved[("fn-1", "D5")], nl1)
    assert c1.type == "buzzer"
    assert c1.attributes.get("_confidence") == "high"

    # Le moteur + son driver, lu sous la cle suffixee.
    c2 = Component(ref="D2", type="led",
                   pins=[Pin("A", "D6"), Pin("K", "GND")],
                   attributes={"category": "single_output",
                               "_confidence": "low"})
    nl2 = Netlist(board_id="", components=[c2])
    apply_saved_resolution(c2, saved[("fn-1", "D6")], netlist=nl2,
                           driver_type=saved[("fn-1", "D6::_driver")])
    assert c2.type == "dc_motor"
    assert c2.attributes.get("_confidence") == "high"


def test_the_prepass_skip_no_longer_depends_on_a_mode():
    """Le terme `is_beginner and scoped_motor_family` n'etait sur que parce
    que la modale debutant reconstruisait l'etat partiel via `saved_pin_types`.
    La modale survivante n'a pas d'equivalent : elle re-coche TOUS les moteurs
    groupes. Garder le saut aurait re-propose en moteur ce que l'utilisateur
    avait deja declare ne pas en etre un.

    On regarde le CODE, pas la prose : le commentaire qui explique cette
    suppression nomme forcement les deux identifiants, et un test qui
    trebuche sur sa propre explication pousserait a effacer l'explication.
    """
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    code_only = "\n".join(ln.split("#", 1)[0] for ln in src.splitlines())
    for dead in ("scoped_motor_family", "saved_pin_types"):
        assert dead not in code_only, dead


def test_motor_warning_fires_on_motor_code_without_motor_choice():
    from ui.studio_view import code_says_motor_but_none_chosen
    code = "void loop(){ setMotor(9, 8, 7, 150); }"
    assert code_says_motor_but_none_chosen(code, ["led", "buzzer"]) is True


def test_motor_warning_silent_when_a_motor_was_chosen():
    from ui.studio_view import code_says_motor_but_none_chosen
    code = "void loop(){ setMotor(9, 8, 7, 150); }"
    assert code_says_motor_but_none_chosen(code, ["led", "dc_motor"]) is False


def test_motor_warning_silent_without_motor_code():
    from ui.studio_view import code_says_motor_but_none_chosen
    assert code_says_motor_but_none_chosen(
        "void loop(){ digitalWrite(13, HIGH); }", ["led"]) is False
    # Un nom qui CONTIENT setMotor ne compte pas : la garde est un mot entier.
    assert code_says_motor_but_none_chosen(
        "void loop(){ resetMotorState(); }", ["led"]) is False


def test_motor_warning_silent_when_nothing_was_resolved():
    """Modale annulee / jamais ouverte : l'utilisateur n'a rien affirme,
    il n'y a rien a contredire."""
    from ui.studio_view import code_says_motor_but_none_chosen
    code = "void loop(){ setMotor(9, 8, 7, 150); }"
    assert code_says_motor_but_none_chosen(code, []) is False


def test_motor_warning_silent_on_a_declared_component():
    """Ecart ASSUME avec la branche debutant, qui elle avertissait ici :
    qui vient de decrire son propre materiel a pu decrire un driver de
    moteur, et l'app n'a aucun titre a lui dire que son schema n'en a pas."""
    from ui.studio_view import code_says_motor_but_none_chosen
    from ui.declared_components import TYPE_PREFIX
    code = "void loop(){ setMotor(9, 8, 7, 150); }"
    assert code_says_motor_but_none_chosen(
        code, ["led", f"{TYPE_PREFIX}monpont"]) is False


def test_consolidated_motor_section_has_its_help_button():
    """Les sections classique et groupee avaient leur '?' ; la consolidee
    (N moteurs) ne l'a recupere qu'en reprenant l'affordance de la modale
    debutant supprimee. Une modale dont l'objet est d'etre uniforme ne peut
    pas avoir un trou d'aide sur son cas le plus complexe."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])   # noqa: F841
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    from ui.wiring.netlist import Component, Netlist, Pin

    motors = []
    nl = Netlist(board_id="arduino_uno_r3", components=[])
    for i, (pwm, d1, d2) in enumerate((("D9", "D8", "D7"),
                                       ("D10", "D11", "D12")), start=1):
        c = Component(ref=f"D{i}", type="led", fn_id="fn-1",
                      pins=[Pin("A", pwm), Pin("K", "GND")],
                      attributes={"category": "single_output",
                                  "_confidence": "low",
                                  "_grouped_pwm_pin": pwm,
                                  "_grouped_dir_pins": [d1, d2]})
        nl.add_component(c)
        motors.append(c)

    dlg = AmbiguityDialog(motors, netlist=nl)
    got: list = []
    dlg.motor_help_requested.connect(got.append)
    # Le bouton d'aide de la section consolidee est celui dont le clic emet
    # motor_help_requested (les autres emettent help_requested).
    fired = False
    for btn in dlg._help_buttons:
        got.clear()
        btn.click()
        if got:
            fired = True
            pins = got[0]
            for expected in ("D9", "D8", "D7", "D10", "D11", "D12"):
                assert expected in pins, (expected, pins)
            break
    assert fired, "aucun '?' n'ouvre l'aide moteur dans la section consolidee"
    dlg.deleteLater()


TESTS = [
    test_no_beginner_branch_remains,
    test_no_mode_test_survives_in_the_resolution_path,
    test_beginner_resolutions_reapply_identically,
    test_the_prepass_skip_no_longer_depends_on_a_mode,
    test_motor_warning_fires_on_motor_code_without_motor_choice,
    test_motor_warning_silent_when_a_motor_was_chosen,
    test_motor_warning_silent_without_motor_code,
    test_motor_warning_silent_when_nothing_was_resolved,
    test_motor_warning_silent_on_a_declared_component,
    test_consolidated_motor_section_has_its_help_button,
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
