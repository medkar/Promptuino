"""Tests for the deterministic formatting module (ui/code_format.py).

(A) reindent_code: re-indents VALID code by brace depth (1 tab per level).
(B) locate_missing_brace / insert_missing_brace: locates a missing closing brace
    via existing indentation and reinserts it.

Repo convention: standalone runner, no pytest.
  QT_QPA_PLATFORM=offscreen python scripts/test_code_format.py
(Pure module — no Qt required, but convention is kept.)
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.code_format import (
    reindent_code, locate_missing_brace, insert_missing_brace,
)

T = "\t"


# ── (A) reindent_code ────────────────────────────────────────────

def test_reindent_flat_to_nested():
    flat = (
        "void loop() {\n"
        "for (int i=0;i<3;i++) {\n"
        "f(i);\n"
        "}\n"
        "}\n"
    )
    out = reindent_code(flat)
    assert out == (
        "void loop() {\n"
        f"{T}for (int i=0;i<3;i++) {{\n"
        f"{T}{T}f(i);\n"
        f"{T}}}\n"
        "}\n"
    ), repr(out)


def test_reindent_idempotent():
    code = "void s() {\nf();\n}\n"
    once = reindent_code(code)
    assert reindent_code(once) == once


def test_reindent_else_brace_dedents():
    code = "void s() {\nif (x) {\na();\n} else {\nb();\n}\n}\n"
    out = reindent_code(code).split("\n")
    assert out[3] == f"{T}}} else {{"          # "} else {" at the if level
    assert out[4] == f"{T}{T}b();"


def test_reindent_preprocessor_column0():
    code = "#include <Servo.h>\nvoid s() {\nf();\n}\n"
    out = reindent_code(code).split("\n")
    assert out[0] == "#include <Servo.h>"     # never indented


def test_reindent_ignores_braces_in_strings_comments():
    code = 'void s() {\nSerial.println("}");  // }\nf();\n}\n'
    out = reindent_code(code).split("\n")
    # The "}" in a string/comment does not dedent: line stays at level 1.
    assert out[1] == f'{T}Serial.println("}}");  // }}'
    assert out[2] == f"{T}f();"


def test_reindent_unbalanced_returns_unchanged():
    broken = "void s() {\nf();\n"     # } missing
    assert reindent_code(broken) == broken


def test_reindent_preserves_blank_lines():
    code = "void s() {\n\nf();\n}\n"
    out = reindent_code(code).split("\n")
    assert out[1] == ""               # blank line preserved, no stray tab


# ── (B) localisation / insertion ─────────────────────────────────

# Properly indented sketch (tabs). The "}" on line 4 (index 3) closes the for.
_GOOD = (
    "void loop() {\n"
    f"{T}for (int i=0;i<3;i++) {{\n"
    f"{T}{T}a(i);\n"
    f"{T}}}\n"
    f"{T}b();\n"
    "}\n"
)


def test_locate_missing_middle_brace():
    broken = _GOOD.replace(f"{T}}}\n", "", 1)   # retire le } du for (index 3)
    idx = locate_missing_brace(broken)
    # Should point to the "\tb();" line (where dedent happens without }).
    lines = broken.split("\n")
    assert lines[idx] == f"{T}b();", (idx, lines)


def test_insert_missing_middle_brace_roundtrip():
    broken = _GOOD.replace(f"{T}}}\n", "", 1)
    fixed = insert_missing_brace(broken)
    assert fixed is not None
    # Rebalanced and structurally identical to the original (modulo reindent).
    assert reindent_code(fixed) == reindent_code(_GOOD)


def test_locate_missing_eof_brace():
    broken = (
        "void loop() {\n"
        f"{T}a();\n"
    )   # final } missing
    idx = locate_missing_brace(broken)
    assert idx == len(broken.split("\n"))      # insertion en fin


def test_locate_flat_code_returns_none():
    # Flat code (no reliable indentation) → not locatable.
    flat_broken = "void loop() {\nfor(;;) {\na();\n}\n"   # } missing, all flat
    assert locate_missing_brace(flat_broken) is None


def test_locate_balanced_returns_none():
    assert locate_missing_brace(_GOOD) is None


def test_locate_extra_brace_returns_none():
    extra = _GOOD + "}\n"                       # extra }
    assert locate_missing_brace(extra) is None


def test_locate_missing_paren_returns_none():
    paren = "void loop() {\n" + f"{T}if (x {{\n" + f"{T}{T}a();\n" + f"{T}}}\n" + "}\n"
    # missing parenthesis (not a brace) → out of scope
    assert locate_missing_brace(paren) is None


def test_insert_unlocatable_returns_none():
    assert insert_missing_brace("void loop() {\nfor(;;) {\na();\n}\n") is None


TESTS = [
    test_reindent_flat_to_nested,
    test_reindent_idempotent,
    test_reindent_else_brace_dedents,
    test_reindent_preprocessor_column0,
    test_reindent_ignores_braces_in_strings_comments,
    test_reindent_unbalanced_returns_unchanged,
    test_reindent_preserves_blank_lines,
    test_locate_missing_middle_brace,
    test_insert_missing_middle_brace_roundtrip,
    test_locate_missing_eof_brace,
    test_locate_flat_code_returns_none,
    test_locate_balanced_returns_none,
    test_locate_extra_brace_returns_none,
    test_locate_missing_paren_returns_none,
    test_insert_unlocatable_returns_none,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
