"""Tests de la logique de correction chat (ui/chat/correction.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.chat.correction import (
    parse_correction_marker, strip_correction_marker,
    build_modify_seed,
)


def test_parse_basic():
    assert parse_correction_marker("Bla bla\nCORRECTION: bmp280") == "bmp280"


def test_parse_case_and_spacing():
    assert parse_correction_marker("correction :  LED") == "led"


def test_parse_trailing_punctuation():
    assert parse_correction_marker("CORRECTION: bmp280.") == "bmp280"


def test_parse_leds_n():
    assert parse_correction_marker("CORRECTION: leds:3") == "leds:3"


def test_parse_unknown_is_none():
    assert parse_correction_marker("CORRECTION: unknown") is None


def test_parse_absent_is_none():
    assert parse_correction_marker("juste une reponse normale") is None


def test_parse_takes_last_marker():
    txt = "CORRECTION: led\n...puis\nCORRECTION: bmp280"
    assert parse_correction_marker(txt) == "bmp280"


def test_strip_removes_marker_line():
    txt = "On a identifie le capteur.\nCORRECTION: bmp280"
    assert strip_correction_marker(txt) == "On a identifie le capteur."


def test_modify_seed_names_target_and_pin_no_prefix():
    p = build_modify_seed("D9", "led")
    assert not p.upper().startswith("CORRECTION"), p   # plus de préfixe magique
    assert "D9" in p, p
    assert "LED" in p.upper(), p


def test_modify_seed_uses_human_name():
    p = build_modify_seed("D5", "bmp280")
    assert "D5" in p, p
    assert p.strip().endswith(":"), p


TESTS = [
    test_parse_basic, test_parse_case_and_spacing,
    test_parse_trailing_punctuation, test_parse_leds_n,
    test_parse_unknown_is_none, test_parse_absent_is_none,
    test_parse_takes_last_marker, test_strip_removes_marker_line,
    test_modify_seed_names_target_and_pin_no_prefix,
    test_modify_seed_uses_human_name,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
