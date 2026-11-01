"""Tout bouton ACTIF montre la main (2026-08-11).

Le constat utilisateur : « en hover sur certains boutons j'ai la main, sur
d'autres le curseur classique ». Mesure sur les widgets reels avant
correction : 575 boutons avaient PointingHandCursor, 28 non. Le ratio est ce
qui rendait l'ecart lisible comme un bug -- on apprend « un bouton donne la
main », puis on en croise un qui ne la donne pas. Les 28 n'etaient pas une
famille : c'etait ce sur quoi personne n'avait pense a ecrire setCursor,
dont TOUS les boutons des modales de composants.

`ui/cursors.py` en fait un defaut d'application. Ce fichier verrouille les
trois proprietes qui comptent, et notamment les deux exceptions -- sans
elles, « la main partout » casserait des intentions existantes.

⚠️ PIEGE DE MESURE, paye pendant l'ecriture : l'evenement Polish n'arrive
qu'au PREMIER SHOW. Auditer un dialogue seulement construit donne 6 faux
negatifs -- on mesure un widget que l'utilisateur ne voit jamais. Tout test
ici DOIT afficher la fenetre avant de regarder les curseurs.

Run : python scripts/test_button_cursors.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QAbstractButton, QCheckBox, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)

# Reference module-level : une QApplication collectee par le GC fait tomber le
# process en crash natif, sans sortie.
_APP = QApplication.instance() or QApplication([])

from ui.cursors import install_button_cursors

_FILTER = install_button_cursors(_APP)
_HAND = Qt.CursorShape.PointingHandCursor
# Les fenetres restent vivantes jusqu'a la fin : un widget detruit pendant que
# le filtre est installe n'apporte rien et complique le teardown.
_VIVANTS = []


def _host(*widgets) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    for x in widgets:
        lay.addWidget(x)
    w.show()
    _APP.processEvents()
    _VIVANTS.append(w)
    return w


def test_a_plain_button_gets_the_hand():
    b = QPushButton("ok")
    _host(b)
    assert b.cursor().shape() == _HAND, b.cursor().shape()


def test_radios_and_checkboxes_get_it_too():
    """Ce sont des QAbstractButton et ils se cliquent. L'app en avait deja
    beaucoup avec la main : les laisser de cote aurait garde l'incoherence
    exacte qu'on corrige."""
    r, c = QRadioButton("r"), QCheckBox("c")
    _host(r, c)
    for w in (r, c):
        assert w.cursor().shape() == _HAND, (type(w).__name__, w.cursor().shape())


def test_a_disabled_button_does_NOT_get_the_hand():
    """« Je veux la main partout sur un bouton NON GRISE ». Qt continue de
    peindre le curseur d'un widget desactive, donc sans ce cas un bouton
    grise inviterait au clic qu'il refuse."""
    b = QPushButton("nope")
    b.setEnabled(False)
    _host(b)
    assert b.cursor().shape() != _HAND, b.cursor().shape()


def test_the_cursor_follows_the_enabled_state_BOTH_ways():
    b = QPushButton("toggle")
    _host(b)
    assert b.cursor().shape() == _HAND
    b.setEnabled(False)
    _APP.processEvents()
    assert b.cursor().shape() != _HAND, "grise mais toujours la main"
    b.setEnabled(True)
    _APP.processEvents()
    assert b.cursor().shape() == _HAND, "reactive mais plus de main"


def test_a_deliberate_cursor_is_never_overridden():
    """L'exception qui compte. Des boutons posent ArrowCursor EXPRES pour dire
    « pas pour toi » : les entrees ESP32 « bientot disponible » (carte,
    filtres, parametres) et le logo de la sidebar, qui est un QPushButton
    mais ne se clique pas. Les repeindre en main leur ferait promettre un
    clic qui n'arrive jamais."""
    b = QPushButton("ESP32")
    b.setCursor(Qt.CursorShape.ArrowCursor)
    _host(b)
    assert b.cursor().shape() == Qt.CursorShape.ArrowCursor, b.cursor().shape()


def test_a_button_that_sets_the_hand_ITSELF_is_still_managed():
    """575 boutons posaient deja la main a la main. Les traiter comme des
    opt-out les aurait laisses la garder une fois grises -- on aurait
    remplace l'incoherence signalee par une autre. Poser la main n'est pas un
    refus, c'est la meme intention ecrite a l'ancienne."""
    b = QPushButton("historique")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    _host(b)
    b.setEnabled(False)
    _APP.processEvents()
    assert b.cursor().shape() != _HAND, "grise mais toujours la main"


def test_an_opt_out_survives_an_unsetCursor():
    """Le verdict est pris UNE fois et memorise. Sans ca, un unsetCursor
    ulterieur remettrait WA_SetCursor a faux et le filtre adopterait un
    bouton qui avait explicitement refuse."""
    b = QPushButton("ESP32")
    b.setCursor(Qt.CursorShape.ArrowCursor)
    _host(b)
    b.unsetCursor()
    b.setEnabled(False)
    b.setEnabled(True)          # deux EnabledChange -> deux passages du filtre
    _APP.processEvents()
    assert b.cursor().shape() != _HAND, "un opt-out a ete adopte apres coup"


def test_a_real_dialog_has_no_enabled_button_left_behind():
    """Le cas signale. Le formulaire de declaration n'avait la main sur AUCUN
    de ses boutons ; il ne pose pourtant aucun curseur lui-meme -- il herite
    du defaut, comme il herite deja de son style."""
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    dlg = DeclareComponentDialog(board_nets=["5V", "GND", "D2"], lang="fr")
    dlg.show()                       # cf. le piege Polish en tete de fichier
    _APP.processEvents()
    _VIVANTS.append(dlg)
    fautifs = [
        (type(b).__name__, b.text() or b.toolTip() or "(icone)")
        for b in dlg.findChildren(QAbstractButton)
        if b.isEnabled() and b.cursor().shape() != _HAND
    ]
    assert not fautifs, fautifs


TESTS = [
    test_a_plain_button_gets_the_hand,
    test_radios_and_checkboxes_get_it_too,
    test_a_disabled_button_does_NOT_get_the_hand,
    test_the_cursor_follows_the_enabled_state_BOTH_ways,
    test_a_deliberate_cursor_is_never_overridden,
    test_a_button_that_sets_the_hand_ITSELF_is_still_managed,
    test_an_opt_out_survives_an_unsetCursor,
    test_a_real_dialog_has_no_enabled_button_left_behind,
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
