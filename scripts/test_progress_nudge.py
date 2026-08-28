"""Tests de la logique pure des nudges de progression.
Run : python scripts/test_progress_nudge.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.progress_nudge import (
    should_show_nudge,
    BEGINNER_GEN_THRESHOLD, INTERMEDIATE_EDIT_THRESHOLD, MANUAL_EDIT_NUDGE_THRESHOLD,
    COUNTER_BEGINNER, COUNTER_INTERMEDIATE, COUNTER_MANUAL_EDIT,
    NUDGE_BEGINNER, NUDGE_INTERMEDIATE, NUDGE_MANUAL_EDIT,
)


def test_thresholds_and_keys_are_stable():
    assert BEGINNER_GEN_THRESHOLD == 5
    assert INTERMEDIATE_EDIT_THRESHOLD == 15
    assert MANUAL_EDIT_NUDGE_THRESHOLD == 5
    assert COUNTER_BEGINNER == "beginner_gen"
    assert COUNTER_INTERMEDIATE == "intermediate_edit"
    assert COUNTER_MANUAL_EDIT == "intermediate_manual_edit"
    assert NUDGE_BEGINNER == "beginner_to_intermediate"
    assert NUDGE_INTERMEDIATE == "intermediate_to_advanced"
    assert NUDGE_MANUAL_EDIT == "manual_edit_to_advanced"


def test_below_threshold_no_nudge():
    assert should_show_nudge(count=4, threshold=5, seen=False, in_target_mode=True) is False


def test_at_threshold_shows():
    assert should_show_nudge(count=5, threshold=5, seen=False, in_target_mode=True) is True


def test_above_threshold_still_shows_if_unseen():
    assert should_show_nudge(count=8, threshold=5, seen=False, in_target_mode=True) is True


def test_seen_never_repeats():
    assert should_show_nudge(count=99, threshold=5, seen=True, in_target_mode=True) is False


def test_wrong_mode_no_nudge():
    assert should_show_nudge(count=99, threshold=5, seen=False, in_target_mode=False) is False


def _rep(count, shown):
    from ui.progress_nudge import (should_show_repeating_nudge,
                                   MANUAL_EDIT_NUDGE_THRESHOLDS as T)
    return should_show_repeating_nudge(
        count=count, thresholds=T, shown=shown, in_target_mode=True)


def test_repeating_nudge_follows_the_series():
    # Seuils 5 / 20 / 40 / 60 : chaque affichage attend le SUIVANT.
    assert _rep(4, 0) is False
    assert _rep(5, 0) is True        # 1er
    assert _rep(19, 1) is False      # pas 2 fois de suite
    assert _rep(20, 1) is True       # 2e
    assert _rep(40, 2) is True       # 3e
    assert _rep(60, 3) is True       # 4e


def test_repeating_nudge_goes_quiet_after_the_last_threshold():
    # Serie epuisee : plus jamais, meme tres au-dela du dernier seuil.
    assert _rep(60, 4) is False
    assert _rep(10_000, 4) is False


def test_a_long_standing_session_does_not_get_the_whole_series_at_once():
    """Session ecrite AVANT ce compteur : elle n'a que l'ancien drapeau
    booleen. Repartir de zero ferait tirer les 4 affichages coup sur coup chez
    quelqu'un dont le compteur est deja tres haut -- l'inverse de « ne pas
    saouler ». On reconstruit depuis les seuils deja franchis.

    Cas reel mesure en QA : compteur a 119, nudge deja vu.
    """
    from ui.progress_nudge import (showings_so_far,
                                   MANUAL_EDIT_NUDGE_THRESHOLDS as T)
    shown = showings_so_far(shown=None, legacy_seen=True, count=119,
                            thresholds=T)
    assert shown == 4, shown                  # les 4 seuils sont franchis
    assert _rep(119, shown) is False          # donc il se tait


def test_a_fresh_session_starts_at_zero():
    from ui.progress_nudge import (showings_so_far,
                                   MANUAL_EDIT_NUDGE_THRESHOLDS as T)
    # Jamais vu -> 0, meme avec un compteur deja eleve (l'utilisateur vient
    # d'installer : il n'a rien rate).
    assert showings_so_far(shown=None, legacy_seen=False, count=99,
                           thresholds=T) == 0
    # Compteur present -> il fait foi, l'ancien drapeau ne le contredit pas.
    assert showings_so_far(shown=2, legacy_seen=True, count=99,
                           thresholds=T) == 2


TESTS = [
    test_thresholds_and_keys_are_stable,
    test_below_threshold_no_nudge,
    test_at_threshold_shows,
    test_above_threshold_still_shows_if_unseen,
    test_seen_never_repeats,
    test_wrong_mode_no_nudge,
    test_repeating_nudge_follows_the_series,
    test_repeating_nudge_goes_quiet_after_the_last_threshold,
    test_a_long_standing_session_does_not_get_the_whole_series_at_once,
    test_a_fresh_session_starts_at_zero,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            return 1
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
