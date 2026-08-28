"""i18n : libellés dropdown/overlay + label « Commentaires » (4 langues)."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.i18n import lang_manager


def test_new_feature_strings_all_langs():
    keys = ("feature_dropdown_label", "feature_action_regen", "feature_action_delete")
    for lang in ("fr", "en", "es", "it"):
        lang_manager.set_language(lang)
        s = lang_manager.current
        for k in keys:
            assert getattr(s, k), f"{lang}:{k} vide"
    lang_manager.set_language("fr")


def test_comments_label_shortened():
    lang_manager.set_language("fr")
    assert lang_manager.current.studio_show_comments == "Commentaires"
    lang_manager.set_language("en")
    assert lang_manager.current.studio_show_comments == "Comments"
    lang_manager.set_language("es")
    assert lang_manager.current.studio_show_comments == "Comentarios"
    lang_manager.set_language("it")
    assert lang_manager.current.studio_show_comments == "Commenti"
    lang_manager.set_language("fr")


TESTS = [test_new_feature_strings_all_langs, test_comments_label_shortened]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
