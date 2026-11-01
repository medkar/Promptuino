"""Tests du sanitizer LaTeX -> texte du rendu chat (_delatex).
Run : python scripts/test_chat_render.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.chat.chat_message import _delatex


def test_strip_display_math_and_frac():
    out = _delatex(r"$$R = \frac{V_{alim} - V_{LED}}{I_{LED}}$$")
    assert "$" not in out, out
    assert "\\frac" not in out, out
    assert "(V_alim - V_LED) / (I_LED)" in out, out


def test_inline_delims_and_symbols():
    assert _delatex(r"\(5 \times 3\)") == "5 × 3"
    assert _delatex(r"R \approx 220 \Omega") == "R ≈ 220 Ω"


def test_text_macro_and_nested_frac():
    assert _delatex(r"\frac{V_{\text{alim}}}{I}") == "(V_alim) / (I)"


def test_bracket_display_delims():
    assert _delatex(r"\[a + b\]") == "a + b"


def test_plain_text_untouched():
    s = "Just a normal sentence with no math at all."
    assert _delatex(s) == s


def test_arduino_code_backslashes_safe():
    # \t et \n ne sont PAS du LaTeX -> doivent rester intacts
    s = 'Serial.println("\\t tab and \\n newline");'
    assert _delatex(s) == s


def test_single_dollar_non_math_untouched():
    s = "It costs 5$ or 10$ depending on the model."
    assert _delatex(s) == s


def test_bare_caret_underscore_untouched():
    # XOR et identifiants C ne doivent pas etre touches (pas d'accolades)
    s = "int x = a ^ b; int my_var = 3;"
    assert _delatex(s) == s


TESTS = [
    test_strip_display_math_and_frac,
    test_inline_delims_and_symbols,
    test_text_macro_and_nested_frac,
    test_bracket_display_delims,
    test_plain_text_untouched,
    test_arduino_code_backslashes_safe,
    test_single_dollar_non_math_untouched,
    test_bare_caret_underscore_untouched,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
