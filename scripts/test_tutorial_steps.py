"""Tutoriel d'accueil (#22) : pas par mode + resolution des textes i18n.
Couvre l'alignement post-#33/#34/#35 : edition libre en Intermediaire, tour
Avance « 2 fenetres » (stable + transfert), pas dropdown de fonctionnalites."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.i18n import lang_manager, TRANSLATIONS
from ui.session import session
session._save = lambda: None                 # ne pas ecrire le vrai session.json

from ui.main_window import MainWindow
_WIN = MainWindow()                          # construite UNE fois (lourde)


def _keys(mode):
    return [s.text_attr for s in _WIN._tutorial_steps(mode)]


def test_intermediate_has_features_step():
    keys = _keys("intermediate")
    assert keys == ["tuto_int_generate", "tuto_int_editor", "tuto_int_features",
                    "tuto_int_tools", "tuto_int_compile"], keys


def test_intermediate_compile_step_targets_only_the_two_buttons():
    from PyQt6.QtWidgets import QPushButton
    studio = _WIN._views.get("console")
    step = _WIN._tutorial_steps("intermediate")[-1]      # 5/5 = tuto_int_compile
    assert step.text_attr == "tuto_int_compile"
    target = step.target()
    assert target is studio._ia_controls_w               # pas toute la colonne
    btns = target.findChildren(QPushButton)
    assert studio._btn_compile in btns                   # Compiler & Uploader
    assert studio._btn_view_schema_adv in btns           # Voir le schéma
    assert len(btns) == 2                                 # exactement ces 2


def test_advanced_is_two_window_tour():
    keys = _keys("advanced")
    assert keys == ["tuto_adv_editor", "tuto_adv_stable", "tuto_adv_transfer",
                    "tuto_adv_comments", "tuto_adv_serial"], keys


def test_all_step_texts_resolve_in_all_langs():
    all_keys = set(_keys("beginner")) | set(_keys("intermediate")) | set(_keys("advanced"))
    for code, strings in TRANSLATIONS.items():
        for k in all_keys:
            v = getattr(strings, k, None)
            assert isinstance(v, str) and v.strip(), f"{code}:{k} vide/absent"


def test_int_editor_text_no_longer_stale():
    # #33 : plus de « pas modifiable / passe en Avance » dans le pas editeur Int.
    for code, strings in TRANSLATIONS.items():
        t = strings.tuto_int_editor.lower()
        assert "pas modifiable" not in t and "not be edited" not in t
        assert "no se puede editar" not in t and "non è modificabile" not in t


def test_target_lambdas_do_not_raise():
    # Les cibles sont resolues paresseusement et tolerent l'absence -> aucune
    # ne doit lever (elles peuvent retourner None selon le mode courant).
    for mode in ("beginner", "intermediate", "advanced"):
        for step in _WIN._tutorial_steps(mode):
            step.target()   # ne doit pas lever


TESTS = [
    test_intermediate_has_features_step,
    test_intermediate_compile_step_targets_only_the_two_buttons,
    test_advanced_is_two_window_tour,
    test_all_step_texts_resolve_in_all_langs,
    test_int_editor_text_no_longer_stale,
    test_target_lambdas_do_not_raise,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    lang_manager.set_language("fr")
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
