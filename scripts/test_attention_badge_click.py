"""QA L1 (2026-08-10) : la pastille d'attention ne repondait pas au clic sur
les composants « presumes ».

Mesure d'origine. `_compute_info_refs` pose bien la pastille sur les quatre
filets d'honnetete du detecteur, `presumed_analog` et `presumed_wiring`
compris. Mais `_on_info_clicked` ne dispatchait que sur `unrecognized`,
`unwired_pins` et trois types de drivers : pour les deux autres, la pastille
affichait un curseur « main », avalait le clic et ne montrait RIEN.

Le survol, lui, marchait deja (`_compute_info_tooltips` rend le texte du
warning). C'est donc bien le CLIC qui manquait, pas le message.

Corrige par un repli generique plutot qu'une branche de plus : il couvrira
aussi le prochain filet ajoute.

Run : python scripts/test_attention_badge_click.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level

from ui.wiring import wiring_diagram_dialog as wdd
from ui.wiring.instructions import _render_warning_message
from ui.wiring.markers import extract_netlist

BARE_ANALOG = ("int pinCapteur = A0;\nint valeurLue = 0;\n"
               "void setup(){ Serial.begin(9600); }\n"
               "void loop(){ valeurLue = analogRead(pinCapteur); }")

PRESUMED_I2C = ('#include <Wire.h>\n#include <LibInconnueZZ.h>\n'
                "void setup(){ Wire.begin(); }\nvoid loop(){}")


def _netlist(code: str):
    return extract_netlist(code, "arduino_uno_r3", prompt="Lis un capteur")


class _FakeDialog:
    """La methode testee lit `self._netlist` et `self._CONFRONTATION_CODES`,
    puis ouvre une boite. On intercepte la boite : ce qu'on veut savoir,
    c'est SI elle s'ouvre et avec quel texte, pas la peindre.

    ⚠️ `_CONFRONTATION_CODES` est repris de la VRAIE classe, jamais recopie :
    depuis la revue finale du #45 (2026-08-27), `_show_warning_info` fait
    passer ces codes devant sa regle « premier warning par ref » -- une copie
    figee ici laisserait ce test au vert le jour ou un 3e code de
    confrontation apparait.
    """
    _CONFRONTATION_CODES = wdd.WiringDiagramDialog._CONFRONTATION_CODES

    def __init__(self, netlist):
        self._netlist = netlist
        self.shown: list = []


def _click(netlist, ref: str) -> list:
    dlg = _FakeDialog(netlist)
    from PyQt6.QtWidgets import QMessageBox
    original = QMessageBox.information
    QMessageBox.information = staticmethod(
        lambda parent, title, text, *a, **k: dlg.shown.append((title, text)))
    try:
        wdd.WiringDiagramDialog._show_warning_info(dlg, ref)
    finally:
        QMessageBox.information = original
    return dlg.shown


def test_a_presumed_analog_component_answers_the_click():
    nl = _netlist(BARE_ANALOG)
    comp = next(c for c in nl.components if c.attributes.get("presumed_analog"))
    shown = _click(nl, comp.ref)
    assert len(shown) == 1, "le clic n'a rien affiche"
    title, text = shown[0]
    assert title and text
    assert "**" not in text, "le gras markdown apparaitrait tel quel"


def test_the_text_is_the_warning_already_emitted():
    """Pas de prose neuve : le clic montre ce que le warning dit deja, comme
    l'infobulle. Deux textes a maintenir divergeraient."""
    nl = _netlist(BARE_ANALOG)
    comp = next(c for c in nl.components if c.attributes.get("presumed_analog"))
    warning = next(w for w in nl.warnings if comp.ref in (w.refs or []))
    expected = _render_warning_message(warning, "fr").replace("**", "")
    assert _click(nl, comp.ref)[0][1] == expected


def test_a_presumed_i2c_component_answers_too():
    """L'autre filet sans branche. La doc qualifie elle-meme ce cas de « le
    plus trompeur » : un cablage PRESUME presente sans explication."""
    nl = _netlist(PRESUMED_I2C)
    comps = [c for c in nl.components if c.attributes.get("presumed_wiring")]
    assert comps, "le decor n'a pas produit de composant presume"
    assert len(_click(nl, comps[0].ref)) == 1


def test_a_ref_without_warning_shows_nothing():
    """Un repli generique ne doit pas ouvrir une boite vide."""
    assert _click(_netlist(BARE_ANALOG), "ZZ99") == []


TESTS = [
    test_a_presumed_analog_component_answers_the_click,
    test_the_text_is_the_warning_already_emitted,
    test_a_presumed_i2c_component_answers_too,
    test_a_ref_without_warning_shows_nothing,
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
