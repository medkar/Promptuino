"""Les boutons STANDARD de Qt parlent la langue de l'app (2026-08-11).

Le constat : dans la modale d'ambiguite, les deux boutons du bas affichaient
« OK » et « Cancel » quelle que soit la langue choisie. Qt fournit ses propres
traductions pour ses boutons standard et les prend dans la locale SYSTEME, qui
n'a aucun rapport avec `lang_manager`.

Le defaut avait deux visages opposes, et c'est ce qui le rend interessant :
- ambiguity_dialog ne posait AUCUN texte      -> anglais partout ;
- wiring_diagram_dialog en posait un a la main, en FRANCAIS, sur 10 boutons
  -> francais meme en anglais, en espagnol et en italien.
Les deux moities se compensaient a l'oeil d'un utilisateur francais, ce qui
explique qu'elles aient survecu si longtemps.

Run : python scripts/test_standard_buttons_i18n.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QDialogButtonBox

_APP = QApplication.instance() or QApplication([])

from ui.i18n import lang_manager, localize_button_box, TRANSLATIONS

_LANGUES = ("fr", "en", "es", "it")
_VIVANTS = []


def test_every_language_defines_the_button_words():
    for code in _LANGUES:
        s = TRANSLATIONS[code]
        for cle in ("btn_validate", "btn_cancel", "btn_understood",
                    "btn_yes", "btn_no"):
            assert getattr(s, cle, "").strip(), (code, cle)


def test_the_words_actually_differ_between_languages():
    """Une cle copiee-collee du francais dans les 4 langues passerait le test
    precedent sans rien traduire. On exige que les 4 ne soient pas toutes
    identiques -- « No » en es et it est legitime, « Annuler » partout non."""
    for cle in ("btn_validate", "btn_understood", "btn_yes"):
        mots = {getattr(TRANSLATIONS[c], cle) for c in _LANGUES}
        assert len(mots) > 1, (cle, mots)


def test_a_button_box_follows_the_app_language():
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                           | QDialogButtonBox.StandardButton.Cancel)
    _VIVANTS.append(box)
    avant = lang_manager.lang
    try:
        for code in _LANGUES:
            lang_manager.set_language(code)
            localize_button_box(box)
            s = TRANSLATIONS[code]
            ok = box.button(QDialogButtonBox.StandardButton.Ok)
            cancel = box.button(QDialogButtonBox.StandardButton.Cancel)
            assert ok.text() == s.btn_validate, (code, ok.text())
            assert cancel.text() == s.btn_cancel, (code, cancel.text())
    finally:
        lang_manager.set_language(avant)


def test_the_override_is_honoured():
    """Les modales purement informatives valident par « J'ai compris », pas
    par « Valider »."""
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    _VIVANTS.append(box)
    localize_button_box(box, ok=lang_manager.current.btn_understood)
    assert (box.button(QDialogButtonBox.StandardButton.Ok).text()
            == lang_manager.current.btn_understood)


def test_the_real_dialog_no_longer_says_OK_Cancel():
    """Le cas signale, sur le vrai dialogue."""
    from ui.wiring.netlist import Netlist, Component, Pin
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    led = Component(ref="D1", type="led", pins=[Pin("A", "D5"), Pin("K", "GND")],
                    attributes={"category": "single_output", "_confidence": "low"})
    dlg = AmbiguityDialog([led], netlist=Netlist(board_id="uno_r3",
                                                components=[led]))
    _VIVANTS.append(dlg)
    box = dlg._buttons
    textes = {box.button(b).text()
              for b in (QDialogButtonBox.StandardButton.Ok,
                        QDialogButtonBox.StandardButton.Cancel)}
    assert not (textes & {"OK", "Cancel", "&OK", "&Cancel"}), textes
    assert textes == {lang_manager.current.btn_validate,
                      lang_manager.current.btn_cancel}, textes


# -- La garde : plus aucun libelle de bouton standard ecrit en dur ------------

_EN_DUR = re.compile(
    r"StandardButton\.\w+\)\.setText\(\s*[\"']", re.M)


def test_no_standard_button_label_is_hard_coded():
    """wiring_diagram_dialog en avait DIX, tous en francais. Une chaine posee
    a la main sur un bouton standard ne peut pas suivre la langue : elle est
    fausse dans 3 langues sur 4, par construction."""
    fautifs = []
    for p in sorted((ROOT / "ui").rglob("*.py")):
        t = p.read_text(encoding="utf-8", errors="replace")
        for m in _EN_DUR.finditer(t):
            fautifs.append(f"{p.relative_to(ROOT).as_posix()}:"
                           f"{t.count(chr(10), 0, m.start()) + 1}")
    assert not fautifs, fautifs


def test_no_static_question_box_is_left():
    """`QMessageBox.question(...)` ne donne aucune prise sur ses boutons : ils
    restent ceux de Qt, donc en anglais. Passer par `ask_yes_no` est la seule
    facon de les traduire."""
    fautifs = []
    for p in sorted((ROOT / "ui").rglob("*.py")):
        if p.name == "message_box.py":
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        if "QMessageBox.question(" in t:
            fautifs.append(p.relative_to(ROOT).as_posix())
    assert not fautifs, fautifs


TESTS = [
    test_every_language_defines_the_button_words,
    test_the_words_actually_differ_between_languages,
    test_a_button_box_follows_the_app_language,
    test_the_override_is_honoured,
    test_the_real_dialog_no_longer_says_OK_Cancel,
    test_no_standard_button_label_is_hard_coded,
    test_no_static_question_box_is_left,
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
