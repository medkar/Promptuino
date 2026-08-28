"""Nudge #35 : segments d'edition manuelle -> popup « 2 fenetres » (5 segments)
+ compteur d'actions Intermediaire -> bandeau (15 actions). Verifie le comptage
par SEGMENT (borne par generation/upload), le gating par mode, et la double
comptabilite (popup + bandeau)."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui import progress_nudge as PN
from ui.session import session

# Ne JAMAIS ecrire le vrai session.json pendant les tests.
session._save = lambda: None


def _reset_session():
    for k in (PN.COUNTER_MANUAL_EDIT, PN.COUNTER_INTERMEDIATE, PN.COUNTER_BEGINNER):
        session._data.pop(f"progress_count_{k}", None)
    for k in (PN.NUDGE_MANUAL_EDIT, PN.NUDGE_INTERMEDIATE, PN.NUDGE_BEGINNER):
        session._data.pop(f"nudge_seen_{k}", None)
        # Nudge repete (QA C5) : sans ca la serie restait epuisee d'un test a
        # l'autre et les suivants echouaient sans rapport avec ce qu'ils
        # testent.
        session._data.pop(f"nudge_shown_{k}", None)


def _view(mode="intermediate"):
    from ui.studio_view import StudioView
    v = StudioView()
    v._on_mode_changed(mode)
    v._popup_calls = []
    v._show_advanced_nudge_popup = lambda: v._popup_calls.append(1)  # pas d'exec()
    return v


def test_popup_after_5_manual_edit_segments():
    _reset_session()
    v = _view("intermediate")
    for _ in range(5):
        v._manual_edit_segment_open = False        # gen/upload entre 2 segments
        v._register_manual_edit_segment()
    assert session.progress_count(PN.COUNTER_MANUAL_EDIT) == 5
    # Revue 2026-07-29 #7 : au 5e segment la popup est DUE mais PAS affichee
    # (on est dans le debounce de frappe) — elle part a la frontiere de
    # segment suivante (fin de generation/upload).
    assert v._popup_calls == [], v._popup_calls
    assert v._manual_edit_popup_due is True
    assert session.nudge_seen(PN.NUDGE_MANUAL_EDIT)
    v._maybe_show_deferred_manual_popup()           # frontiere de segment
    assert v._popup_calls == [1], v._popup_calls
    v._maybe_show_deferred_manual_popup()           # idempotent
    assert v._popup_calls == [1], v._popup_calls


def test_continuous_editing_counts_as_one_segment():
    _reset_session()
    v = _view("intermediate")
    for _ in range(6):                              # aucun reset -> meme segment
        v._register_manual_edit_segment()
    assert session.progress_count(PN.COUNTER_MANUAL_EDIT) == 1
    assert v._popup_calls == []


def test_segment_counts_toward_both_counters():
    _reset_session()
    v = _view("intermediate")
    v._register_manual_edit_segment()
    assert session.progress_count(PN.COUNTER_MANUAL_EDIT) == 1
    assert session.progress_count(PN.COUNTER_INTERMEDIATE) == 1   # aussi le bandeau


def test_no_count_outside_intermediate():
    _reset_session()
    v = _view("advanced")
    v._manual_edit_segment_open = False
    v._register_manual_edit_segment()
    assert session.progress_count(PN.COUNTER_MANUAL_EDIT) == 0
    assert v._popup_calls == []


def test_banner_fires_at_15_actions():
    _reset_session()
    v = _view("intermediate")
    for _ in range(15):
        v._manual_edit_segment_open = False
        v._register_manual_edit_segment()
    # Popup au 5e, bandeau au 15e (les deux once-only, coexistent).
    assert session.nudge_seen(PN.NUDGE_MANUAL_EDIT)
    assert session.nudge_seen(PN.NUDGE_INTERMEDIATE)
    assert session.progress_count(PN.COUNTER_INTERMEDIATE) == 15


def test_popup_only_once_even_after_more_segments():
    _reset_session()
    v = _view("intermediate")
    for _ in range(8):
        v._manual_edit_segment_open = False
        v._register_manual_edit_segment()
        v._maybe_show_deferred_manual_popup()       # frontiere apres chaque segment
    assert v._popup_calls == [1]                    # jamais deux fois


def test_popup_comes_back_at_the_next_threshold():
    """QA C5 (2026-08-08) : un nudge de PROGRESSION qui ne parle qu'une fois
    rate sa cible -- mesure sur une vraie session, 119 segments d'edition
    manuelle sans qu'on ait jamais reparle du mode Avance. Il revient donc a
    seuils croissants (5, 20, 40, 60) puis se tait definitivement."""
    _reset_session()
    v = _view("intermediate")
    for _ in range(20):
        v._manual_edit_segment_open = False
        v._register_manual_edit_segment()
        v._maybe_show_deferred_manual_popup()
    assert v._popup_calls == [1, 1], v._popup_calls      # au 5e ET au 20e


def test_popup_goes_quiet_once_the_series_is_exhausted():
    _reset_session()
    v = _view("intermediate")
    for _ in range(80):
        v._manual_edit_segment_open = False
        v._register_manual_edit_segment()
        v._maybe_show_deferred_manual_popup()
    # 4 seuils franchis (5, 20, 40, 60) puis plus rien jusqu'a 80.
    assert v._popup_calls == [1, 1, 1, 1], v._popup_calls


def test_deferred_popup_dropped_if_mode_left():
    # La popup due est ABANDONNEE si l'utilisateur a deja quitte
    # l'Intermediaire avant la frontiere de segment (nudge devenu inutile).
    _reset_session()
    v = _view("intermediate")
    for _ in range(5):
        v._manual_edit_segment_open = False
        v._register_manual_edit_segment()
    assert v._manual_edit_popup_due is True
    v._on_mode_changed("advanced")
    v._maybe_show_deferred_manual_popup()
    assert v._popup_calls == [], v._popup_calls
    assert v._manual_edit_popup_due is False


TESTS = [
    test_popup_after_5_manual_edit_segments,
    test_continuous_editing_counts_as_one_segment,
    test_segment_counts_toward_both_counters,
    test_no_count_outside_intermediate,
    test_banner_fires_at_15_actions,
    test_popup_only_once_even_after_more_segments,
    test_popup_comes_back_at_the_next_threshold,
    test_popup_goes_quiet_once_the_series_is_exhausted,
    test_deferred_popup_dropped_if_mode_left,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
