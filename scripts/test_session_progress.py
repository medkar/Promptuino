"""Régression : compteurs + drapeaux de nudge persistés AU NIVEAU APP
(session.json), pas par projet.

IMPORTANT : patche `_SESSION_PATH` vers un dossier TEMPORAIRE — ne touche
jamais le vrai ~/Documents/Promptuino/session.json.

Run : python scripts/test_session_progress.py
"""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.session as session_mod


def _fresh_session(tmpdir: Path):
    session_mod._SESSION_PATH = tmpdir / "session.json"
    return session_mod.Session()


def test_counter_starts_at_zero_and_bumps():
    with tempfile.TemporaryDirectory() as d:
        s = _fresh_session(Path(d))
        assert s.progress_count("beginner_gen") == 0
        assert s.bump_progress_count("beginner_gen") == 1
        assert s.bump_progress_count("beginner_gen") == 2
        assert s.progress_count("beginner_gen") == 2


def test_counter_persists_across_instances():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _fresh_session(tmp)
        s.bump_progress_count("intermediate_edit")
        s.bump_progress_count("intermediate_edit")
        s2 = _fresh_session(tmp)
        assert s2.progress_count("intermediate_edit") == 2


def test_nudge_seen_flag():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _fresh_session(tmp)
        assert s.nudge_seen("beginner_to_intermediate") is False
        s.mark_nudge_seen("beginner_to_intermediate")
        assert s.nudge_seen("beginner_to_intermediate") is True
        s2 = _fresh_session(tmp)
        assert s2.nudge_seen("beginner_to_intermediate") is True


TESTS = [
    test_counter_starts_at_zero_and_bumps,
    test_counter_persists_across_instances,
    test_nudge_seen_flag,
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
