"""Ce qui se clique doit le DIRE, et le dire dans la langue de l'app (2026-08-11).

Trouve par l'audit des « conventions appliquees a la main ». Trois constats,
tous du meme motif — la regle etait suivie par la grande majorite, et oubliee
par une minorite, ce qui la rend lisible comme un bug :

- **Le titre du projet, dans le Studio, se renomme au double-clic** et ne le
  disait NULLE PART : ni curseur, ni infobulle, ni effet de survol. C'est la
  seule porte de renommage depuis le Studio, et la phrase qui l'annonce
  existait deja, traduite dans les 4 langues (`studio_function_rename_tip`),
  branchee sur rien.
- **Trois commandes icone-seule sans infobulle** sur 17 : les deux poignees de
  repli (affichees en permanence, et invisibles a tout balayage des boutons
  car ce sont des QWidget peints au QPainter), et le chevron des cartes de
  projet — juste a cote du « ⋯ » qui, lui, a son infobulle.
- **L'infobulle « Bientot disponible » (ESP32) etait posee a la construction**
  et jamais reactualisee : elle restait en francais dans les 3 autres langues,
  alors que 84 autres infobulles suivent correctement.

Run : python scripts/test_affordances.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

from ui.i18n import lang_manager, TRANSLATIONS

_VIVANTS = []
_LANGUES = ("fr", "en", "es", "it")


def _fenetre():
    """MainWindow affichee. Construite une seule fois : deux MainWindow dans le
    meme process est un chemin connu vers un crash natif au teardown."""
    if not _VIVANTS:
        from ui import MainWindow
        w = MainWindow()
        w.resize(1280, 800)
        w.show()
        _APP.processEvents()
        _VIVANTS.append(w)
    return _VIVANTS[0]


def test_the_project_title_says_it_can_be_renamed():
    """Le cas signale : la seule porte de renommage du Studio, muette."""
    w = _fenetre()
    w._goto_tab("console")
    _APP.processEvents()
    lbl = w._views["console"]._lbl_project_name
    assert lbl.toolTip(), "le titre du projet n'a toujours aucune infobulle"
    assert lbl.cursor().shape() == Qt.CursorShape.PointingHandCursor, \
        lbl.cursor().shape()


def test_that_tooltip_is_the_one_already_written_and_follows_the_language():
    """Elle existait dans les 4 langues avant d'etre branchee : on verifie
    qu'on a bien branche CELLE-LA, et qu'elle suit le changement de langue."""
    w = _fenetre()
    w._goto_tab("console")
    avant = lang_manager.lang
    try:
        for code in _LANGUES:
            lang_manager.set_language(code)
            _APP.processEvents()
            attendu = TRANSLATIONS[code].studio_function_rename_tip
            obtenu = w._views["console"]._lbl_project_name.toolTip()
            assert obtenu == attendu, (code, obtenu, attendu)
    finally:
        lang_manager.set_language(avant)
        _APP.processEvents()


def test_the_two_collapse_handles_have_a_tooltip():
    """Elles sont affichees en PERMANENCE. Ce sont des QWidget peints au
    QPainter, pas des QAbstractButton : c'est pour ca qu'aucun balayage de
    boutons ne les avait vues."""
    w = _fenetre()
    for nom in ("_sep_handle", "_chat_handle"):
        h = getattr(w, nom)
        assert h.toolTip(), f"{nom} n'a aucune infobulle"


def test_the_collapse_handles_follow_the_language():
    w = _fenetre()
    avant = lang_manager.lang
    try:
        for code in _LANGUES:
            lang_manager.set_language(code)
            _APP.processEvents()
            s = TRANSLATIONS[code]
            assert w._sep_handle.toolTip() == s.tip_toggle_sidebar, code
            assert w._chat_handle.toolTip() == s.tip_toggle_chat, code
    finally:
        lang_manager.set_language(avant)
        _APP.processEvents()


def test_the_coming_soon_tooltip_is_no_longer_frozen_in_french():
    """LE defaut le plus net de la lentille infobulles : posee une fois a la
    construction, elle survivait a tous les changements de langue."""
    w = _fenetre()
    w._goto_tab("carte")
    _APP.processEvents()
    from ui.board_view import _EnvBtn
    avant = lang_manager.lang
    try:
        for code in ("en", "es", "it"):
            lang_manager.set_language(code)
            _APP.processEvents()
            attendu = TRANSLATIONS[code].board_coming_soon
            gelees = [b.toolTip() for b in w.findChildren(_EnvBtn)
                      if getattr(b, "_coming_soon", False)
                      and b.toolTip() != attendu]
            assert not gelees, (code, gelees)
    finally:
        lang_manager.set_language(avant)
        _APP.processEvents()


def test_the_four_new_tooltip_keys_exist_in_every_language():
    for code in _LANGUES:
        s = TRANSLATIONS[code]
        for cle in ("tip_toggle_sidebar", "tip_toggle_chat",
                    "tip_card_functions", "tip_refresh_ports"):
            assert getattr(s, cle, "").strip(), (code, cle)


def test_those_keys_are_really_translated_not_copied():
    """Quatre copies du francais passeraient le test precedent sans traduire."""
    for cle in ("tip_toggle_sidebar", "tip_toggle_chat",
                "tip_card_functions", "tip_refresh_ports"):
        mots = {getattr(TRANSLATIONS[c], cle) for c in _LANGUES}
        assert len(mots) == 4, (cle, mots)


TESTS = [
    test_the_project_title_says_it_can_be_renamed,
    test_that_tooltip_is_the_one_already_written_and_follows_the_language,
    test_the_two_collapse_handles_have_a_tooltip,
    test_the_collapse_handles_follow_the_language,
    test_the_coming_soon_tooltip_is_no_longer_frozen_in_french,
    test_the_four_new_tooltip_keys_exist_in_every_language,
    test_those_keys_are_really_translated_not_copied,
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
