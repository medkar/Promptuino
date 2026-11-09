"""Le journal dit « Annulé. », pas « Annuler. » (libelle du BOUTON).

Trouve le 2026-11-07 en pilotant la vraie fenetre : apres une annulation, le
journal affichait l'infinitif du bouton -- `studio_cancel + "."` -- dans les
trois journaux (Debutant, compilation avancee, generation).
"""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.i18n import Strings, lang_manager  # noqa: E402


def _toutes():
    from ui.i18n import TRANSLATIONS
    return list(TRANSLATIONS.values())


def test_the_state_differs_from_the_button_in_every_language():
    langues = _toutes()
    assert len(langues) >= 4, len(langues)
    for s in langues:
        assert s.studio_cancelled and s.studio_cancelled != s.studio_cancel, s.studio_cancel


def test_french_says_annule():
    lang_manager.set_language("fr")
    assert lang_manager.current.studio_cancelled == "Annulé"


def test_no_journal_reuses_the_button_label():
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    assert 'studio_cancel + "."' not in src


TESTS = [test_the_state_differs_from_the_button_in_every_language,
         test_french_says_annule, test_no_journal_reuses_the_button_label]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t(); print("PASS", t.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1; print("FAIL", t.__name__, repr(e))
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    raise SystemExit(1 if failed else 0)
