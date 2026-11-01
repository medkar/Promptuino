"""Smoke test : la section classique de la modale d'ambiguite est faite de
CARDS, pas d'une liste deroulante.

Ce fichier remplace `test_ambiguity_dropdown_smoke.py` (SP2 Task 6, la liste
deroulante meme-categorie). L'intention est la meme — ce qui est PROPOSABLE
pour une broche ambigue, et ce qui ne l'est pas — mais le widget a change : un
`ComponentPicker` (recherche + cards selectionnables), la meme card que
l'onglet « Composants ».

Deux garanties nouvelles, qu'une liste deroulante n'avait pas a porter :

- **regle Q9** : une recherche qui masque le choix le rend NON VALIDABLE. Sans
  ca, « Valider » resterait actif au-dessus d'un picker vide — l'etat de
  resolution change sans qu'aucun clic ne se produise ;
- le sous-menu « Quel driver ? » est lui aussi en cards, meme facture que les
  composants.
"""
from __future__ import annotations
import os, sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# QApplication conservee au niveau module : sans reference gardee,
# `QApplication.instance() or QApplication([])` ecrit inline cree une app
# temporaire immediatement GC-ee, et construire un QWidget ensuite crashe le
# process (0xC0000409) sous Windows. On garde donc l'app vivante ici.
from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

from PyQt6.QtCore import Qt                      # noqa: E402
from PyQt6.QtGui import QCursor                  # noqa: E402
from PyQt6.QtTest import QTest                   # noqa: E402
from PyQt6.QtWidgets import QComboBox, QDialogButtonBox  # noqa: E402

import ui.declared_components as declared_components     # noqa: E402

# La bibliotheque declaree vient de la MEMOIRE : un test ne lit jamais le
# ~/Documents/Promptuino de la machine.
declared_components.set_registry([])
# Offscreen, `QCursor.pos()` est fige a (10,10) et force le :hover sur tout
# widget proche de l'origine — sans effet sur les assertions ci-dessous, mais
# on eloigne le curseur par principe (piege memorise le 2026-08-11).
QCursor.setPos(2000, 2000)

_VIVANTS: list = []


def _dialog(comps, **kw):
    from ui.wiring.netlist import Netlist
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    nl = Netlist(board_id="", components=list(comps))
    dlg = AmbiguityDialog(list(comps), netlist=nl, **kw)
    _VIVANTS.append(dlg)
    return dlg


def _led(ref="D1", net="D5", **attrs):
    from ui.wiring.netlist import Component, Pin
    base = {"category": "single_output", "_confidence": "low"}
    base.update(attrs)
    return Component(ref=ref, type="led",
                     pins=[Pin("A", net), Pin("K", "GND")], attributes=base)


def _ok_enabled(dlg) -> bool:
    return dlg._buttons.button(
        QDialogButtonBox.StandardButton.Ok).isEnabled()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_the_classic_section_proposes_the_same_category_in_cards():
    """Ce qui est proposable n'a pas bouge (led -> led/buzzer, jamais
    potentiometre) ; c'est la facon de le choisir qui change."""
    led = _led()
    dlg = _dialog([led])

    picker = dlg._pickers.get("D1")
    assert picker is not None, "aucun ComponentPicker dans la section classique"
    assert not dlg.findChildren(QComboBox), \
        "une liste deroulante subsiste dans la modale"

    ids = picker.visible_type_ids()
    assert "led" in ids, ids
    assert "buzzer" in ids, ids
    assert "potentiometer" not in ids, ids
    # Sortie volontairement ASCII : `run_all_tests.py` reimprime la sortie
    # d'un test rouge, et une console cp1252 le fait planter sur un tiret cadratin.
    print(f"  OK - types proposes : {ids}")


def test_an_ambiguous_pin_opens_with_nothing_selected():
    """⚠️ CE CONTRAT S'EST INVERSE LE 2026-08-29 (retour utilisateur).

    Ce test affirmait l'inverse : « le picker s'ouvre sur ce que le detecteur
    a cru voir, jamais vierge ». Sur une AMBIGUITE, ce type est un DEFAUT --
    toute sortie numerique nue sort en « led » --, pas une deduction, et le
    cocher faisait passer une ignorance pour une reponse : « Valider » etait
    actif au-dessus de questions auxquelles personne n'avait repondu.
    """
    led = _led()
    dlg = _dialog([led])
    picker = dlg._pickers["D1"]
    assert picker.current_type_id() is None, picker.current_type_id()
    assert "D1" not in dlg._chosen_type, dlg._chosen_type
    assert not picker.card_for("led").is_selected()
    assert not _ok_enabled(dlg), "rien n'est choisi, Valider doit etre gris"


def test_a_component_read_from_the_code_keeps_its_type():
    """Le pendant du precedent : l'engrenage ouvert sur un composant detecte
    avec CERTITUDE. La son type est une information, pas un defaut."""
    led = _led()
    led.type = "relay"
    led.attributes["_confidence"] = "high"
    dlg = _dialog([led])
    assert dlg._pickers["D1"].current_type_id() == "relay"
    assert dlg._chosen_type["D1"] == "relay", dlg._chosen_type


def test_the_cross_category_escape_hatches_stay_reachable():
    led = _led(ref="D3", net="D3")
    dlg = _dialog([led])
    ids = dlg._pickers["D3"].visible_type_ids()
    assert "dc_motor" in ids, ids
    assert "servo" in ids, ids


def test_clicking_a_card_records_the_choice():
    led = _led()
    dlg = _dialog([led])
    picker = dlg._pickers["D1"]
    card = picker.card_for("buzzer")
    assert card is not None, picker.visible_type_ids()
    QTest.mouseClick(card, Qt.MouseButton.LeftButton)
    assert dlg._chosen_type["D1"] == "buzzer", dlg._chosen_type
    assert picker.current_type_id() == "buzzer"
    assert not picker.card_for("led").is_selected(), \
        "deux cards selectionnees a la fois"


def test_a_search_that_hides_the_choice_forbids_validating():
    """Regle Q9. Rien d'invisible n'est validable : masquer la card choisie
    doit griser « Valider », meme si aucun clic n'a eu lieu."""
    led = _led()
    dlg = _dialog([led])
    picker = dlg._pickers["D1"]
    # Rien n'est preselectionne depuis 2026-08-29 : on choisit d'abord, sinon
    # « Valider » est gris pour une raison qui n'a rien a voir avec Q9.
    QTest.mouseClick(picker.card_for("led"), Qt.MouseButton.LeftButton)
    assert _ok_enabled(dlg), "Valider devrait etre actif apres un choix"

    picker.set_query("zzzzzzz")
    assert picker.current_type_id() is None, picker.visible_type_ids()
    assert not _ok_enabled(dlg), \
        "Valider reste actif alors que le choix n'est plus a l'ecran"

    # ... et effacer la recherche le rend a nouveau validable : le SOUVENIR du
    # choix survit au filtre, l'utilisateur n'a rien annule.
    picker.set_query("")
    assert picker.current_type_id() == "led"
    assert _ok_enabled(dlg), "Valider n'est pas revenu apres la recherche"


def test_a_rebuild_does_not_leave_an_offscreen_picker_gating_validate():
    """Un picker qui a quitte l'ecran ne doit plus rien decider.

    `_update_ok_state` grise Valider tant qu'un picker n'a aucune selection
    effective (regle Q9). Si une reconstruction oublie de vider le cache des
    pickers, celui d'une section disparue continue de gater la decision —
    invisible, donc intouchable : Valider reste grise pour toujours.

    La sequence exacte, reproduite en revue : decocher « c'est bien un
    moteur » (le moteur se degroupe en broches classiques), taper dans le
    picker de l'une d'elles une recherche qui masque son choix, puis recocher
    (les sections classiques disparaissent). Aucun autre test ne l'attrape :
    avec le `clear()` retire, tout le reste du fichier reste vert."""
    from ui.wiring.netlist import Component, Pin
    comps = []
    for ref, pwm, dirs in (("D1", "D9", ["D8", "D7"]),
                           ("D2", "D10", ["D11", "D12"])):
        comps.append(Component(
            ref=ref, type="led",
            pins=[Pin("A", pwm), Pin("K", "GND")],
            attributes={"_confidence": "low", "_grouped_pwm_pin": pwm,
                        "_grouped_dir_pins": dirs}))
    dlg = _dialog(comps, suggested_dc_driver="l298n")
    assert _ok_enabled(dlg), "Valider devrait etre actif sur 2 moteurs groupes"

    dlg._toggle_motor_declared("D9", is_motor=False)     # -> sections classiques
    assert dlg._pickers, "le degroupage n'a produit aucun picker"
    ref, picker = next(iter(dlg._pickers.items()))
    picker.set_query("zzzzzzz")
    assert not _ok_enabled(dlg), (
        "un choix masque devrait griser Valider — le test ne prouve rien sinon")

    dlg._toggle_motor_declared("D9", is_motor=True)      # regroupe -> rebuild
    assert ref not in dlg._pickers, \
        "le picker d'une section disparue survit a la reconstruction"
    assert _ok_enabled(dlg), (
        "Valider reste grise par un picker qui n'est plus a l'ecran")


def test_the_driver_menu_is_made_of_cards_too():
    """Le sous-menu « Quel driver ? » : meme facture que les composants."""
    from ui.wiring.ambiguity_dialog import _DC_DRIVERS
    led = _led(ref="D2", net="D9", _prompt_suggested_type="dc_motor")
    dlg = _dialog([led])
    cards = dlg._driver_cards.get("D2")
    assert cards is not None, "aucune card de driver"
    assert sorted(cards) == sorted(_DC_DRIVERS), sorted(cards)
    QTest.mouseClick(cards["drv8833"], Qt.MouseButton.LeftButton)
    assert dlg._chosen_driver["D2"] == "drv8833", dlg._chosen_driver
    assert cards["drv8833"].is_selected()
    assert not cards["l298n"].is_selected(), "deux drivers selectionnes"


def test_the_driver_pencil_opens_the_form_without_requalifying_the_pin():
    """Une card porte toujours son crayon — y compris dans le sous-menu
    driver, ou il ne doit surtout PAS reposer le type du composant : le driver
    n'est pas ce qu'on identifie ici, et poser `l298n` sur la broche la
    transformerait en driver. D'ou `ref=None`.

    On intercepte le routeur SUR L'INSTANCE (le branchement appelle
    `self._edit_component`) : sinon le clic ouvrirait vraiment le formulaire,
    dont l'`exec()` bloque le test."""
    led = _led(ref="D2", net="D9", _prompt_suggested_type="dc_motor")
    dlg = _dialog([led])
    vus: list = []
    dlg._edit_component = lambda ref, tid: vus.append((ref, tid))
    carte = dlg._driver_cards["D2"]["l298n"]
    assert carte._btn_edit is not None, "la card de driver n'a pas de crayon"
    carte._btn_edit.click()
    assert vus == [(None, "l298n")], vus
    assert dlg._chosen_type["D2"] == "dc_motor", dlg._chosen_type


def test_driver_frame_visible_when_dc_motor_preselected():
    """Quand _prompt_suggested_type=dc_motor, le sous-menu driver doit etre
    visible d'emblee.

    `isVisible()` rend False tant que le parent (la modale non affichee) l'est
    aussi : on lit `isHidden()`, qui reflete l'etat du widget lui-meme."""
    led = _led(ref="D2", net="D9", _prompt_suggested_type="dc_motor")
    dlg = _dialog([led])
    frame = dlg._driver_frames.get("D2")
    assert frame is not None, "_driver_frames['D2'] doit exister"
    assert not frame.isHidden(), \
        "sous-menu driver cache alors que dc_motor est pre-selectionne"


def test_choosing_the_dc_motor_card_reveals_the_driver_menu():
    led = _led()
    dlg = _dialog([led])
    frame = dlg._driver_frames["D1"]
    assert frame.isHidden(), "le sous-menu driver ne devrait pas etre la"
    QTest.mouseClick(dlg._pickers["D1"].card_for("dc_motor"),
                     Qt.MouseButton.LeftButton)
    assert not frame.isHidden(), \
        "choisir « moteur DC » n'a pas revele le sous-menu driver"
    # ... et tant qu'aucun driver n'est choisi, on ne valide pas.
    assert not _ok_enabled(dlg), \
        "Valider actif sur un moteur DC sans driver"


def test_consolidated_driver_preselected_from_suggestion():
    """A la reouverture (engrenage), studio_view repose le driver DEJA choisi
    sur les moteurs via `_prompt_suggested_driver`. La section consolidee
    (>=2 moteurs) doit le pre-cocher."""
    from ui.wiring.netlist import Component, Pin
    comps = []
    for ref, pwm, dirs in (("D1", "D9", ["D8", "D7"]),
                           ("D2", "D10", ["D11", "D12"])):
        comps.append(Component(
            ref=ref, type="led",
            pins=[Pin("A", pwm), Pin("K", "GND")],
            attributes={"_confidence": "low", "_grouped_pwm_pin": pwm,
                        "_grouped_dir_pins": dirs,
                        "_prompt_suggested_driver": "tb6612fng"}))
    dlg = _dialog(comps)
    assert dlg._chosen_driver, "aucun driver pre-selectionne"
    assert all(v == "tb6612fng" for v in dlg._chosen_driver.values()), \
        dlg._chosen_driver
    cards = dlg._driver_cards.get("__consolidated__")
    assert cards is not None, "aucune card de driver partage"
    assert cards["tb6612fng"].is_selected(), "le driver suggere n'est pas coche"


def test_the_shared_driver_applies_to_every_motor():
    from ui.wiring.netlist import Component, Pin
    comps = []
    for ref, pwm, dirs in (("D1", "D9", ["D8", "D7"]),
                           ("D2", "D10", ["D11", "D12"])):
        comps.append(Component(
            ref=ref, type="led",
            pins=[Pin("A", pwm), Pin("K", "GND")],
            attributes={"_confidence": "low", "_grouped_pwm_pin": pwm,
                        "_grouped_dir_pins": dirs}))
    dlg = _dialog(comps)
    cards = dlg._driver_cards["__consolidated__"]
    QTest.mouseClick(cards["l298n"], Qt.MouseButton.LeftButton)
    assert dlg._chosen_driver == {"D1": "l298n", "D2": "l298n"}, \
        dlg._chosen_driver


def test_a_signature_component_does_not_claim_the_prompt_said_nothing():
    """QA AC1 (2026-08-31) : le gear d'un servo reconnu par `Servo.h` ouvrait
    la page avec « Pas de mention explicite dans ton prompt — le composant a
    ete detecte a partir du code » — FAUX des que le prompt nomme le
    composant (la phrase parlait de l'extrait PAR BROCHE, que le prompt ne
    peut pas fournir puisqu'il ne nomme pas « D9 »). Un composant de niveau 1
    a sa propre phrase : rien n'a ete devine, le code utilise sa
    bibliotheque."""
    from PyQt6.QtWidgets import QLabel
    from ui.wiring.netlist import Component, Pin
    from ui.wiring.visual_ambiguity_catalog import dialog_label
    servo = Component(
        ref="SV1", type="servo",
        pins=[Pin("VCC", "5V"), Pin("GND", "GND"), Pin("SIG", "D9")],
        attributes={"signature_detected": True})
    dlg = _dialog([servo],
                  prompt="un servo commande par un potentiometre")
    textes = [l.text() for l in dlg.findChildren(QLabel)]
    # « le code nomme ce composant » (retouche QA AC2) : exact aussi pour un
    # driver signature SANS librairie propre (A4988 via AccelStepper).
    assert any("certitude" in t and "nomme" in t for t in textes), textes
    missing = dialog_label("prompt_excerpt_missing", "fr")
    assert all(missing not in t for t in textes), textes
    # La phrase existe dans les 4 langues (garde de derive du catalogue).
    for lang in ("fr", "en", "es", "it"):
        assert dialog_label("signature_excerpt", lang), lang


def test_the_missing_excerpt_phrase_speaks_of_the_pin_not_the_component():
    """QA AC2 (2026-08-31) : « Pas de mention explicite dans ton prompt — le
    composant a ete detecte... » devenait FAUX des que le prompt nommait le
    composant sans nommer la broche (« un potentiometre » -> la page du pot
    affichait cette phrase). La branche ne sait qu'une chose — aucun extrait
    PAR BROCHE n'a ete trouve — donc la phrase ne parle que de la broche."""
    from ui.wiring.visual_ambiguity_catalog import dialog_label
    for lang in ("fr", "en", "es", "it"):
        assert dialog_label("prompt_excerpt_missing", lang), lang
    fr = dialog_label("prompt_excerpt_missing", "fr").lower()
    assert "broche" in fr, fr
    assert "mention explicite" not in fr, fr


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_a_signature_component_does_not_claim_the_prompt_said_nothing,
    test_the_missing_excerpt_phrase_speaks_of_the_pin_not_the_component,
    test_the_classic_section_proposes_the_same_category_in_cards,
    test_an_ambiguous_pin_opens_with_nothing_selected,
    test_a_component_read_from_the_code_keeps_its_type,
    test_the_cross_category_escape_hatches_stay_reachable,
    test_clicking_a_card_records_the_choice,
    test_a_search_that_hides_the_choice_forbids_validating,
    test_a_rebuild_does_not_leave_an_offscreen_picker_gating_validate,
    test_the_driver_menu_is_made_of_cards_too,
    test_the_driver_pencil_opens_the_form_without_requalifying_the_pin,
    test_driver_frame_visible_when_dc_motor_preselected,
    test_choosing_the_dc_motor_card_reveals_the_driver_menu,
    test_consolidated_driver_preselected_from_suggestion,
    test_the_shared_driver_applies_to_every_motor,
]


def main():
    passed = 0
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    # Sous Windows + Qt offscreen, detruire plusieurs AmbiguityDialog pendant
    # le teardown Qt statique crashe le process (0xC0000409) APRES que les
    # assertions ont deja tranche. On sort par os._exit pour que le code de
    # retour reflete les assertions, pas le crash de teardown.
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
