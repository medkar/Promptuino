"""Le bouton de suppression du formulaire de composant (2026-08-10).

Deux demandes de l'utilisateur, une seule raison :

  - libelle « Supprimer » et non « Retirer de ma librairie ». Le libelle long
    decrivait le MECANISME (d'ou l'entree part) la ou l'utilisateur veut lire
    l'ACTE — et il se confondait avec « retirer le composant du schema », qui
    n'existe pas. C'est ce quiproquo qui a laisse la decision sur ce bouton en
    suspens deux jours ;
  - rouge, contours rouges. Tous les autres controles de l'app passent au VERT
    au survol (`secondary_button_qss`) : c'est la couleur du « continue ». Le
    seul geste irreversible de l'ecran ne doit pas l'emprunter, et doit se
    signaler AVANT que la souris n'arrive — donc rouge des le repos, pas
    seulement au survol.

Run : python scripts/test_destructive_button.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication, QPushButton
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level
from ui.fonts import setup_fonts
setup_fonts(_APP)

import ui.declared_components as dc
import ui.wiring.declare_component_dialog as m
from ui.declared_components import DeclaredComponent, DeclaredPin
from ui.theme import DARK, LIGHT, destructive_button_qss, theme_manager
from ui.wiring.declare_component_dialog import DeclareComponentDialog, _t

LANGS = ("fr", "en", "es", "it")

_ENTRY = DeclaredComponent(
    id="mon-capteur", name="Mon capteur", headers=(),
    pins=(DeclaredPin(label="VCC", role="vcc", net="5V"),
          DeclaredPin(label="OUT", role="signal", net="A0")),
    lib="", keywords=("Mon capteur",))


def _dialog(lang="fr"):
    """Le formulaire ouvert sur une entree REELLEMENT enregistree : c'est la
    seule situation ou le bouton existe."""
    dc.set_registry([_ENTRY])
    m.load = lambda: [_ENTRY]
    return DeclareComponentDialog(None, existing=_ENTRY,
                                  board_nets=["5V", "GND", "A0"], lang=lang)


def _remove_button(dlg, lang="fr"):
    return next((b for b in dlg.findChildren(QPushButton)
                 if b.text() == _t("remove", lang)), None)


def test_the_label_names_the_act_not_the_mechanism():
    attendu = {"fr": "Supprimer", "en": "Delete", "es": "Eliminar",
               "it": "Elimina"}
    for lang in LANGS:
        assert _t("remove", lang) == attendu[lang], lang


def test_no_language_mentions_the_library_anymore():
    """« de ma librairie » est ce qui le faisait confondre avec le schema."""
    for lang in LANGS:
        low = _t("remove", lang).lower()
        for mot in ("librairie", "library", "biblioteca", "libreria"):
            assert mot not in low, f"{lang}: {_t('remove', lang)!r}"


def test_the_button_is_red_at_rest():
    """Au repos, pas seulement au survol : l'utilisateur doit le voir AVANT
    d'approcher la souris."""
    btn = _remove_button(_dialog())
    assert btn is not None, "bouton absent"
    qss, c = btn.styleSheet(), theme_manager.current
    assert f"color: {c.signal_error}" in qss
    assert f"border: 1px solid {c.signal_error}" in qss


def test_it_never_borrows_the_green_of_the_other_controls():
    """Le vert dit « continue » partout ailleurs dans l'app."""
    btn = _remove_button(_dialog())
    assert theme_manager.current.signal_ok not in btn.styleSheet()


def test_its_neighbours_keep_the_default_style():
    """Seul lui est repeint : « Annuler » et « Enregistrer » restent sur le
    style global, sinon on aurait deplace la convention au lieu de faire une
    exception."""
    dlg = _dialog()
    for b in dlg.findChildren(QPushButton):
        if b.text() in (_t("cancel", "fr"), _t("save", "fr")):
            assert not b.styleSheet(), b.text()


def test_the_helper_works_on_both_themes():
    """`destructive_button_qss` lit `main_bg` pour le texte au survol : une
    faute de nom d'attribut ne se verrait qu'a l'execution."""
    for scheme in (DARK, LIGHT):
        qss = destructive_button_qss(scheme)
        assert scheme.signal_error in qss
        assert scheme.main_bg in qss


TESTS = [
    test_the_label_names_the_act_not_the_mechanism,
    test_no_language_mentions_the_library_anymore,
    test_the_button_is_red_at_rest,
    test_it_never_borrows_the_green_of_the_other_controls,
    test_its_neighbours_keep_the_default_style,
    test_the_helper_works_on_both_themes,
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
