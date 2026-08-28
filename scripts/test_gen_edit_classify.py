"""Tests de la classification d'édition (ui/generation/edit_classify.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.edit_classify import normalize_code, is_dirty, classify_edit

BASE = """void setup() {
  pinMode(13, OUTPUT);
}
void loop() {
  digitalWrite(13, HIGH);
}
"""


def test_cosmetic_whitespace_is_clean():
    edited = BASE.replace("  pinMode", "      pinMode") + "\n\n\n"
    assert is_dirty(edited, BASE) is False
    assert classify_edit(edited, BASE) == "clean"


def test_added_comment_is_clean():
    edited = BASE.replace("void loop() {", "// ma boucle\nvoid loop() {")
    assert classify_edit(edited, BASE) == "clean"


def test_pure_addition_detected():
    edited = BASE.replace("void loop() {\n  digitalWrite(13, HIGH);\n}",
                          "void loop() {\n  digitalWrite(13, HIGH);\n  extra();\n}")
    assert classify_edit(edited, BASE) == "addition"


def test_inline_modification_detected():
    edited = BASE.replace("digitalWrite(13, HIGH);", "digitalWrite(13, LOW);")
    assert classify_edit(edited, BASE) == "inline"


def test_deletion_counts_as_inline():
    edited = BASE.replace("  pinMode(13, OUTPUT);\n", "")
    assert classify_edit(edited, BASE) == "inline"


TESTS = [
    test_cosmetic_whitespace_is_clean, test_added_comment_is_clean,
    test_pure_addition_detected, test_inline_modification_detected,
    test_deletion_counts_as_inline,
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
