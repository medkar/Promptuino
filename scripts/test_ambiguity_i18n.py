"""Bout en bout (2026-08-11) : la modale d'ambiguite AVANCEE (AmbiguityDialog)
rend-elle vraiment un texte different en italien qu'en francais ?

Complement des gardes statiques de test_visual_ambiguity_catalog.py
(cle/langue/placeholder sur la table) : ici on CONSTRUIT la modale et on lit
le texte des widgets, comme test_warning_templates.py le fait pour les
avertissements de cablage. Ca attrape ce que la garde statique ne peut pas
voir : un `.format(k=...)` dont le nom de parametre ne correspond pas au
`{n}` du gabarit leverait un KeyError ICI, pas dans le scan AST.
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from ui.i18n import lang_manager
from ui.wiring.netlist import Component, Pin, Netlist
from ui.wiring.ambiguity_dialog import AmbiguityDialog


def _classic_dialog(lang: str, with_excerpt: bool) -> AmbiguityDialog:
    lang_manager.set_language(lang)
    led = Component(
        ref="D1", type="led",
        pins=[Pin("A", "D5"), Pin("K", "GND")],
        attributes={"_confidence": "low"},
    )
    nl = Netlist(board_id="", components=[led])
    prompt = "Une LED sur la broche 5" if with_excerpt else ""
    return AmbiguityDialog([led], netlist=nl, prompt=prompt)


def _grouped_dialog(lang: str, with_excerpt: bool) -> AmbiguityDialog:
    lang_manager.set_language(lang)
    motor = Component(
        ref="D1", type="led",
        pins=[Pin("A", "D9"), Pin("K", "GND")],
        attributes={"_confidence": "low", "_grouped_pwm_pin": "D9",
                    "_grouped_dir_pins": ["D8", "D7"]},
    )
    nl = Netlist(board_id="", components=[motor])
    prompt = "Un moteur DC sur la broche 9" if with_excerpt else ""
    return AmbiguityDialog([motor], netlist=nl, prompt=prompt)


def _consolidated_dialog(lang: str, motors_limit: int | None = None) -> AmbiguityDialog:
    lang_manager.set_language(lang)
    comps = []
    for ref, pwm, dirs in (("D1", "D9", ["D8", "D7"]),
                           ("D2", "D10", ["D11", "D12"])):
        comps.append(Component(
            ref=ref, type="led",
            pins=[Pin("A", pwm), Pin("K", "GND")],
            attributes={"_confidence": "low", "_grouped_pwm_pin": pwm,
                        "_grouped_dir_pins": dirs}))
    nl = Netlist(board_id="", components=comps)
    return AmbiguityDialog(comps, netlist=nl, motors_limit=motors_limit)


def _reset_lang():
    lang_manager.set_language("fr")


def test_window_title_differs_fr_it():
    fr = _classic_dialog("fr", with_excerpt=False).windowTitle()
    it = _classic_dialog("it", with_excerpt=False).windowTitle()
    assert fr and it and fr != it, (fr, it)
    _reset_lang()


def test_classic_section_no_excerpt_differs_fr_it():
    from PyQt6.QtWidgets import QGroupBox, QLabel
    dlg_fr = _classic_dialog("fr", with_excerpt=False)
    dlg_it = _classic_dialog("it", with_excerpt=False)
    title_fr = dlg_fr.findChild(QGroupBox).title()
    title_it = dlg_it.findChild(QGroupBox).title()
    assert title_fr and title_it and title_fr != title_it, (title_fr, title_it)
    assert "5" in title_fr and "5" in title_it
    _reset_lang()


def test_classic_section_excerpt_found_differs_fr_it():
    from PyQt6.QtWidgets import QLabel
    dlg_fr = _classic_dialog("fr", with_excerpt=True)
    dlg_it = _classic_dialog("it", with_excerpt=True)
    labels_fr = [l.text() for l in dlg_fr.findChildren(QLabel)]
    labels_it = [l.text() for l in dlg_it.findChildren(QLabel)]
    ctx_fr = next((t for t in labels_fr if "broche 5" in t.lower()
                   or "broche" in t.lower()), None)
    ctx_it = next((t for t in labels_it if "broche 5" in t.lower()
                   or "broche" in t.lower()), None)
    assert ctx_fr is not None, labels_fr
    assert ctx_it is not None, labels_it
    assert ctx_fr != ctx_it, (ctx_fr, ctx_it)
    _reset_lang()


def test_a_lone_motor_uses_the_consolidated_section_too():
    """⚠️ CONTRAT CHANGE LE 2026-08-29 (QA).

    Un moteur UNIQUE passait par `_build_grouped_section` — radios « Oui,
    c'est un moteur DC » / « Non, ce sont des composants séparés » — et deux
    moteurs ou plus par la section consolidée, en cases à cocher. Deux
    présentations pour la même question, et l'utilisateur tombait sur l'une ou
    l'autre selon la porte : « la vue est différente entre la modif composant
    via engrenage et modifier mes choix ». Il n'y en a plus qu'une.

    Ce test garde ce qu'il gardait — les libellés suivent la langue — sur la
    vue qui reste.
    """
    from PyQt6.QtWidgets import QCheckBox, QGroupBox, QRadioButton
    dlg_fr = _grouped_dialog("fr", with_excerpt=False)
    dlg_it = _grouped_dialog("it", with_excerpt=False)
    title_fr = dlg_fr.findChild(QGroupBox).title()
    title_it = dlg_it.findChild(QGroupBox).title()
    assert title_fr != title_it, (title_fr, title_it)
    # Plus aucune radio « oui/non » : ce sont les cases de la section
    # consolidee qui portent desormais la question, pour 1 comme pour N.
    assert not dlg_fr.findChildren(QRadioButton),         [r.text() for r in dlg_fr.findChildren(QRadioButton)]
    cases_fr = {c.text() for c in dlg_fr.findChildren(QCheckBox)}
    cases_it = {c.text() for c in dlg_it.findChildren(QCheckBox)}
    assert "C'est bien un moteur" in cases_fr, cases_fr
    assert cases_fr.isdisjoint(cases_it), (cases_fr, cases_it)
    _reset_lang()


def test_grouped_excerpt_paths_differ_fr_it():
    from PyQt6.QtWidgets import QLabel
    for with_excerpt in (True, False):
        dlg_fr = _grouped_dialog("fr", with_excerpt)
        dlg_it = _grouped_dialog("it", with_excerpt)
        texts_fr = {l.text() for l in dlg_fr.findChildren(QLabel)}
        texts_it = {l.text() for l in dlg_it.findChildren(QLabel)}
        assert texts_fr != texts_it, (with_excerpt, texts_fr, texts_it)
    _reset_lang()


def test_consolidated_section_and_limit_warning_differ_fr_it():
    from PyQt6.QtWidgets import QGroupBox, QCheckBox, QLabel
    dlg_fr = _consolidated_dialog("fr", motors_limit=1)
    dlg_it = _consolidated_dialog("it", motors_limit=1)
    title_fr = dlg_fr.findChild(QGroupBox).title()
    title_it = dlg_it.findChild(QGroupBox).title()
    assert "2" in title_fr and "2" in title_it, (title_fr, title_it)
    assert title_fr != title_it, (title_fr, title_it)

    checks_fr = {c.text() for c in dlg_fr.findChildren(QCheckBox)}
    checks_it = {c.text() for c in dlg_it.findChildren(QCheckBox)}
    assert "Câbler le moteur" in checks_fr, checks_fr
    assert "Cablare il motore" in checks_it, checks_it

    banners_fr = [l.text() for l in dlg_fr.findChildren(QLabel)
                  if "1" in l.text() and "2" in l.text()]
    banners_it = [l.text() for l in dlg_it.findChildren(QLabel)
                  if "1" in l.text() and "2" in l.text()]
    assert banners_fr, "banniere limite (fr) introuvable"
    assert banners_it, "banniere limite (it) introuvable"
    assert banners_fr[0] != banners_it[0]
    _reset_lang()


def _driver_names(dlg, key: str = "__consolidated__") -> dict:
    """{type_driver: nom affiche sur sa card}.

    La cle est celle du sous-menu PARTAGE : depuis le 2026-08-29 les moteurs
    passent tous par la section consolidee, meme seuls, donc leurs cards de
    pilote vivent sous `__consolidated__` et non plus sous la ref du
    composant."""
    return {d: card.name for d, card in dlg._driver_cards[key].items()}


def test_driver_card_labels_tell_the_two_l293d_apart_in_each_language():
    """Le sous-menu « Quel driver ? » est passe des radios aux CARDS
    (2026-08-13) : le nom affiche vient desormais de la fiche de la
    bibliotheque (`component_index`), comme partout ailleurs dans l'app, et
    non plus de `_driver_label`.

    Ce qui doit survivre a ce changement est le SENS, pas le libelle exact :
    les deux L293D (module breakout / DIP nu) restent distinguables l'un de
    l'autre, et leur qualificatif suit la langue. Le part number, lui, est un
    nom propre : il ne se traduit pas."""
    dlg_fr = _grouped_dialog("fr", with_excerpt=False)
    dlg_it = _grouped_dialog("it", with_excerpt=False)
    fr, it = _driver_names(dlg_fr), _driver_names(dlg_it)
    assert fr["l293d_module"] != fr["l293d"], fr
    assert it["l293d_module"] != it["l293d"], it
    assert fr["l293d_module"] != it["l293d_module"], (fr, it)
    for names in (fr, it):
        assert "L293D" in names["l293d_module"], names
        assert "L293D" in names["l293d"], names
        assert "L298N" in names["l298n"], names
    _reset_lang()


def test_limit_toast_message_differs_fr_it():
    lang_manager.set_language("fr")
    dlg = _consolidated_dialog("fr", motors_limit=1)
    dlg._toggle_motor_grouping("D10", keep=True)  # over the limit -> toast
    from ui.wiring.visual_ambiguity_catalog import dialog_label
    fr = dialog_label("motors_limit_toast", "fr").format(limit=1)
    it = dialog_label("motors_limit_toast", "it").format(limit=1)
    assert fr != it and "1" in fr and "1" in it, (fr, it)
    _reset_lang()


TESTS = [
    test_window_title_differs_fr_it,
    test_classic_section_no_excerpt_differs_fr_it,
    test_classic_section_excerpt_found_differs_fr_it,
    test_a_lone_motor_uses_the_consolidated_section_too,
    test_grouped_excerpt_paths_differ_fr_it,
    test_consolidated_section_and_limit_warning_differ_fr_it,
    test_driver_card_labels_tell_the_two_l293d_apart_in_each_language,
    test_limit_toast_message_differs_fr_it,
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
    # Meme motif que test_ambiguity_dropdown_smoke.py : detruire plusieurs
    # AmbiguityDialog pendant le teardown Qt statique crashe le process
    # (0xC0000409) sous Windows APRES que les assertions ont deja tranche.
    os._exit(0 if passed == len(TESTS) else 1)
