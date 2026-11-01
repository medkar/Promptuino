"""Le libelle des trois boutons « Voir le schema » vient de l'i18n (2026-08-10).

Contexte du defaut. Les trois boutons (debutant, fenetre IA, fenetre stable)
etaient construits par `QPushButton("Voir le schema")` — le francais **en dur**,
et rien ne les retraduisait. Pendant ce temps la cle `studio_action_schema`
existait, traduite dans les 4 langues, et le chat la citait a l'utilisateur
comme le vocabulaire de l'app (`chat_prompts`) : l'app **nommait** le bouton
dans une langue et le **decrivait** dans une autre.

Le defaut a survecu longtemps parce qu'il est invisible en francais — la seule
langue dans laquelle l'app est developpee et testee a la main.

Run : python scripts/test_view_schema_label.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.i18n import TRANSLATIONS, lang_manager
from ui.session import session

session._save = lambda: None            # ne JAMAIS ecrire le vrai session.json

LANGS = ("fr", "en", "es", "it")
BUTTONS = ("_btn_view_schema", "_btn_view_schema_adv", "_btn_view_schema_stable")


def _view():
    from ui.studio_view import StudioView
    return StudioView()


def _labels(v):
    return {name: getattr(v, name).text() for name in BUTTONS}


def test_the_key_is_translated_in_the_four_languages():
    """Sans ca le reste du test passerait sur une cle qui ne dit rien."""
    for code in LANGS:
        s = TRANSLATIONS[code]
        assert getattr(s, "studio_action_schema", "").strip(), code


def test_the_three_buttons_carry_the_key_not_a_hard_coded_string():
    v = _view()
    attendu = lang_manager.current.studio_action_schema
    for name, texte in _labels(v).items():
        assert texte == attendu, f"{name}: {texte!r} != {attendu!r}"


def test_changing_the_language_changes_all_three():
    """Le vrai symptome : l'app passait en anglais, les boutons restaient en
    francais. Un seul des trois oublie serait une regression partielle."""
    v = _view()
    for code in ("en", "es", "it", "fr"):
        v.apply_lang(TRANSLATIONS[code])
        attendu = TRANSLATIONS[code].studio_action_schema
        for name, texte in _labels(v).items():
            assert texte == attendu, f"{code}/{name}: {texte!r} != {attendu!r}"


def test_no_button_is_left_on_the_french_wording_in_english():
    """Garde ciblee sur la forme exacte du defaut d'origine : le francais fige.
    Elle ne tiendrait pas si la traduction anglaise etait identique au
    francais — le test precedent le verifie, celui-ci nomme le symptome."""
    v = _view()
    v.apply_lang(TRANSLATIONS["en"])
    for name, texte in _labels(v).items():
        assert texte != TRANSLATIONS["fr"].studio_action_schema, name


def test_the_source_no_longer_hard_codes_the_label():
    """Un quatrieme bouton ajoute plus tard avec le libelle en dur passerait
    les tests ci-dessus (ils n'interrogent que les trois connus). On verrouille
    donc aussi la source."""
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "ui", "studio_view.py")
    with open(src, encoding="utf-8") as f:
        code = f.read()
    assert 'QPushButton("Voir le' not in code, "libelle en dur reintroduit"


TESTS = [
    test_the_key_is_translated_in_the_four_languages,
    test_the_three_buttons_carry_the_key_not_a_hard_coded_string,
    test_changing_the_language_changes_all_three,
    test_no_button_is_left_on_the_french_wording_in_english,
    test_the_source_no_longer_hard_codes_the_label,
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
