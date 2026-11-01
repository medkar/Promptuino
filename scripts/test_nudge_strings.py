"""Les 2 chaînes de nudge existent et sont non vides dans les 4 langues.
Run : python scripts/test_nudge_strings.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.i18n import TRANSLATIONS


def test_nudge_strings_present_all_langs():
    for code in ("fr", "en", "es", "it"):
        s = TRANSLATIONS[code]
        assert getattr(s, "nudge_beginner_to_intermediate", "").strip(), code
        assert getattr(s, "nudge_intermediate_to_advanced", "").strip(), code


TESTS = [test_nudge_strings_present_all_langs]


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
