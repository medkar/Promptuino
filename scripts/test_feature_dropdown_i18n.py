"""i18n en direct des lignes du popup `FeatureDropdown`.

La ligne « Éditions manuelles » est un texte d'APPLI : elle doit suivre un
changement de langue SANS reconstruction (`set_features`). Les lignes voisines,
elles, portent un résumé produit par le MODÈLE dans la langue où il a été
généré : elles ne doivent surtout PAS être retraduites (c'est exactement le
piège qui a fait naître le défaut — la ligne manuelle avait suivi par défaut le
sort du contenu généré à côté d'elle).
"""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.feature_dropdown import FeatureDropdown          # noqa: E402
from ui.generation.feature_model import Feature, MANUAL_ID   # noqa: E402
from ui.i18n import lang_manager                          # noqa: E402

_LANGS = ("fr", "en", "es", "it")


def _dropdown():
    """A dropdown fed ONCE, in French, with an AI feature + the manual one."""
    lang_manager.set_language("fr")
    dd = FeatureDropdown()
    dd.set_features([
        Feature(id="f1", prompt="clignoter la LED", summary="Clignote la LED"),
        Feature(id=MANUAL_ID, prompt=""),
    ])
    rows = dict(dd._rows)
    return dd, rows[MANUAL_ID], rows["f1"]


def test_manual_row_text_follows_language_switch():
    # No set_features() after the switch: the live retranslation is the point.
    dd, manual_cb, _ai_cb = _dropdown()
    assert manual_cb.text() == "Éditions manuelles"
    for lang in _LANGS:
        lang_manager.set_language(lang)
        expected = lang_manager.current.studio_manual_feature_label
        assert manual_cb.text() == expected, (
            f"{lang}: ligne manuelle = {manual_cb.text()!r}, attendu {expected!r}")
        # Control: the popup button itself was already retranslated.
        assert dd._btn.text().startswith(
            lang_manager.current.feature_dropdown_label)
    lang_manager.set_language("fr")


def test_manual_row_tooltip_follows_language_switch():
    dd, manual_cb, _ai_cb = _dropdown()
    for lang in _LANGS:
        lang_manager.set_language(lang)
        expected = lang_manager.current.studio_manual_feature_label
        assert manual_cb.toolTip() == expected, (
            f"{lang}: infobulle = {manual_cb.toolTip()!r}, attendu {expected!r}")
    lang_manager.set_language("fr")


def test_ai_row_label_is_never_retranslated():
    # A model-written summary must stay verbatim in every language: nothing in
    # the app knows how to translate it, and rewriting it would be a lie.
    dd, _manual_cb, ai_cb = _dropdown()
    text, tip = ai_cb.text(), ai_cb.toolTip()
    assert "Clignote la LED" in text
    for lang in _LANGS:
        lang_manager.set_language(lang)
        assert ai_cb.text() == text, f"{lang}: résumé IA réécrit -> {ai_cb.text()!r}"
        assert ai_cb.toolTip() == tip
    lang_manager.set_language("fr")


def test_language_switch_after_rebuild_without_manual_row():
    # set_features() destroys the rows: a stale reference to the old manual
    # checkbox would raise (deleted C++ object) on the next language change.
    dd, _manual_cb, _ai_cb = _dropdown()
    dd.set_features([Feature(id="f1", prompt="LED", summary="Clignote la LED")])
    lang_manager.set_language("en")          # must not raise
    assert all(fid != MANUAL_ID for fid, _cb in dd._rows)
    # And a manual row rebuilt AFTER the switch is labelled in the new language.
    dd.set_features([Feature(id="f1", prompt="LED", summary="Clignote la LED"),
                     Feature(id=MANUAL_ID, prompt="")])
    manual_cb = dict(dd._rows)[MANUAL_ID]
    assert manual_cb.text() == lang_manager.current.studio_manual_feature_label
    lang_manager.set_language("fr")
    assert manual_cb.text() == "Éditions manuelles"


TESTS = [
    test_manual_row_text_follows_language_switch,
    test_manual_row_tooltip_follows_language_switch,
    test_ai_row_label_is_never_retranslated,
    test_language_switch_after_rebuild_without_manual_row,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
        else:
            print(f"OK   {t.__name__}")
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
