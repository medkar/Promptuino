import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication, QComboBox
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

_APP = QApplication.instance() or QApplication(sys.argv)

from ui.wiring.ambiguity_dialog import _install_combo_search


ITEMS = ["LED", "buzzer", "servomoteur", "ecran OLED (SSD1306)",
         "ecran OLED (SH1106)", "module generique"]


def _typed(text: str) -> QComboBox:
    """Combo starting on LED (index 0), into which `text` is typed then
    validated with Return -- exactly what a user does in the search field."""
    cb = QComboBox()
    cb.addItems(ITEMS)
    cb.setCurrentIndex(0)
    _install_combo_search(cb)
    cb.show()
    cb.setFocus()
    edit = cb.lineEdit()
    edit.selectAll()
    QTest.keyClicks(edit, text)
    QTest.keyClick(edit, Qt.Key.Key_Return)
    _APP.processEvents()
    return cb


def test_a_search_matching_one_item_actually_selects_it():
    """LE test que l'ancien ne faisait pas : le champ de recherche doit
    CHANGER LE CHOIX, pas seulement afficher du texte.

    Avant correction, taper « ssd » puis Entree laissait currentIndex sur 0
    (LED) et le texte revenait a « LED » : la recherche etait decorative, et
    valider la modale n'appliquait rien -- un echec SILENCIEUX (QA C2)."""
    cb = _typed("ssd")
    assert cb.currentText() == "ecran OLED (SSD1306)", cb.currentText()


def test_the_search_is_case_insensitive():
    assert _typed("SSD").currentText() == "ecran OLED (SSD1306)"
    assert _typed("oled (sh1106)").currentText() == "ecran OLED (SH1106)"


def test_a_search_matching_nothing_falls_back_on_the_real_choice():
    """Cas « zzz » : rien ne correspond, donc rien ne doit changer, et le
    texte doit revenir sur le choix reel plutot que de mentir."""
    cb = _typed("zzz")
    assert cb.currentIndex() == 0
    assert cb.currentText() == "LED"


def test_an_ambiguous_search_does_not_guess():
    """« oled » correspond a DEUX ecrans. Choisir le premier serait
    presenter une devinette comme un choix : on ne bouge pas, et le texte
    revient sur le choix reel pour que l'utilisateur precise."""
    cb = _typed("oled")
    assert cb.currentIndex() == 0, ITEMS[cb.currentIndex()]
    assert cb.currentText() == "LED"


def test_an_exact_match_wins_over_a_longer_item():
    """Regle pure : taper le texte COMPLET d'un item le selectionne, meme
    quand ce texte est contenu dans d'autres ("LED" face a "LED RGB")."""
    from ui.wiring.ambiguity_dialog import match_index
    items = ["LED", "LED RGB", "LED matrix"]
    assert match_index(items, "LED") == 0
    assert match_index(items, "led") == 0          # insensible a la casse
    assert match_index(items, "LED RGB") == 1


def test_the_matching_rule_refuses_to_guess():
    from ui.wiring.ambiguity_dialog import match_index
    items = ["LED", "LED RGB", "LED matrix"]
    assert match_index(items, "matr") == 2         # unique -> retenu
    assert match_index(items, "LE") is None        # 3 candidats -> aucun
    assert match_index(items, "") is None          # rien de tape
    assert match_index(items, "   ") is None
    assert match_index(items, "zzz") is None


def _dialog_with_search_combo():
    """Le montage REEL d'AmbiguityDialog : le combo vit dans un QDialog qui a
    un QDialogButtonBox OK/Annuler, avec la neutralisation du bouton par
    defaut faite a la construction."""
    from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
    dlg = QDialog()
    lay = QVBoxLayout(dlg)
    cb = QComboBox()
    cb.addItems(ITEMS)
    cb.setCurrentIndex(0)
    _install_combo_search(cb)
    lay.addWidget(cb)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                           QDialogButtonBox.StandardButton.Cancel)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    for b in box.buttons():
        b.setAutoDefault(False)
        b.setDefault(False)
    lay.addWidget(box)
    return dlg, cb


def test_enter_in_the_search_field_does_not_validate_the_modal():
    """QA C2 (2026-08-08) : Entree doit COMMETTRE la recherche, pas fermer la
    fenetre.

    Le test precedent exercait le combo SEUL -- sans QDialog, une fermeture
    est litteralement invisible. Dans le vrai montage, Entree remontait au
    QDialog qui cliquait son bouton par defaut : mesure faite, Qt RETABLIT
    `isDefault` sur OK au show(), donc le `setDefault(False)` de la
    construction ne tient pas."""
    dlg, cb = _dialog_with_search_combo()
    dlg.show()
    _APP.processEvents()
    cb.setFocus()
    edit = cb.lineEdit()
    edit.selectAll()
    QTest.keyClicks(edit, "ssd")
    QTest.keyClick(edit, Qt.Key.Key_Return)
    _APP.processEvents()
    assert cb.currentText() == "ecran OLED (SSD1306)", cb.currentText()
    assert dlg.isVisible(), "la modale s'est fermee sur Entree"
    assert dlg.result() != 1, "la modale a ete VALIDEE sur Entree"


def test_enter_on_a_search_matching_nothing_does_not_validate_either():
    """Meme exigence quand la recherche ne designe rien : le texte revient sur
    le choix reel et la fenetre RESTE ouverte, pour laisser corriger."""
    dlg, cb = _dialog_with_search_combo()
    dlg.show()
    _APP.processEvents()
    cb.setFocus()
    edit = cb.lineEdit()
    edit.selectAll()
    QTest.keyClicks(edit, "zzz")
    QTest.keyClick(edit, Qt.Key.Key_Return)
    _APP.processEvents()
    assert cb.currentText() == "LED", cb.currentText()
    assert dlg.isVisible(), "la modale s'est fermee sur Entree"


def test_combo_is_searchable():
    cb = QComboBox()
    for lab, data in [("OLED SSD1306", "adafruit-ssd1306"),
                      ("OLED SH1106", "sh1106"),
                      ("LCD I2C 16x2", "liquidcrystal-i2c")]:
        cb.addItem(lab, userData=data)
    _install_combo_search(cb)
    assert cb.isEditable()
    comp = cb.completer()
    assert comp is not None
    assert comp.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive
    # La saisie reste contrainte aux items (pas d'insertion libre).
    assert cb.insertPolicy() == QComboBox.InsertPolicy.NoInsert


TESTS = [
    test_a_search_matching_one_item_actually_selects_it,
    test_the_search_is_case_insensitive,
    test_a_search_matching_nothing_falls_back_on_the_real_choice,
    test_an_ambiguous_search_does_not_guess,
    test_an_exact_match_wins_over_a_longer_item,
    test_the_matching_rule_refuses_to_guess,
    test_enter_in_the_search_field_does_not_validate_the_modal,
    test_enter_on_a_search_matching_nothing_does_not_validate_either,
    test_combo_is_searchable,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
