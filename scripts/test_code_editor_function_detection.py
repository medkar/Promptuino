"""Tests pour la detection de fonction sous curseur dans CodeEditor
(pont contextuel chat F2 etape 4)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import only the pure helper, no Qt dependency.
from ui.code_editor import _find_function_at_cursor


SAMPLE_CODE = '''#include <Arduino.h>

const int LED = 13;

void setup() {
  pinMode(LED, OUTPUT);
  Serial.begin(9600);
}

void loop() {
  digitalWrite(LED, HIGH);
  delay(500);
  digitalWrite(LED, LOW);
  delay(500);
}

int compute(int x, int y) {
  return x + y;
}
'''


def _pos_of(text: str, substr: str) -> int:
    return text.index(substr)


def test_find_function_at_cursor_inside_setup():
    pos = _pos_of(SAMPLE_CODE, "pinMode(LED")
    result = _find_function_at_cursor(SAMPLE_CODE, pos)
    assert result is not None, "Should find setup()"
    name, body = result
    assert name == "setup"
    assert "pinMode" in body
    assert "Serial.begin" in body


def test_find_function_at_cursor_inside_loop():
    pos = _pos_of(SAMPLE_CODE, "digitalWrite(LED, HIGH")
    result = _find_function_at_cursor(SAMPLE_CODE, pos)
    assert result is not None
    name, body = result
    assert name == "loop"
    assert "digitalWrite" in body
    assert "delay(500)" in body


def test_find_function_at_cursor_inside_compute():
    pos = _pos_of(SAMPLE_CODE, "return x + y")
    result = _find_function_at_cursor(SAMPLE_CODE, pos)
    assert result is not None
    name, body = result
    assert name == "compute"
    assert "return x + y" in body


def test_find_function_at_cursor_outside_function():
    # Position dans #include (top of file)
    pos = _pos_of(SAMPLE_CODE, "#include")
    result = _find_function_at_cursor(SAMPLE_CODE, pos)
    assert result is None, (
        "Should not find function for cursor in #include"
    )


def test_find_function_at_cursor_on_global_var():
    pos = _pos_of(SAMPLE_CODE, "const int LED")
    result = _find_function_at_cursor(SAMPLE_CODE, pos)
    assert result is None, (
        "Should not find function for cursor on global variable"
    )


def test_find_function_at_cursor_empty_code():
    result = _find_function_at_cursor("", 0)
    assert result is None


def test_find_function_at_cursor_skips_control_flow_keywords():
    """Code partiel en cours d'edition : `if/while/for` a top-level
    (= au lieu d'etre dans setup/loop) ne doit pas etre matche comme
    fonction nommee `if` / `while` / `for`."""
    code = (
        '#include <Arduino.h>\n\n'
        'int x = 0;\n\n'
        'if (x > 0) {\n'
        '  x = 1;\n'
        '}\n\n'
        'while (x < 10) {\n'
        '  x++;\n'
        '}\n'
    )
    pos_if = code.index("x = 1")
    pos_while = code.index("x++")
    assert _find_function_at_cursor(code, pos_if) is None, (
        "Should not match `if` as a function name"
    )
    assert _find_function_at_cursor(code, pos_while) is None, (
        "Should not match `while` as a function name"
    )


TESTS = [
    test_find_function_at_cursor_inside_setup,
    test_find_function_at_cursor_inside_loop,
    test_find_function_at_cursor_inside_compute,
    test_find_function_at_cursor_outside_function,
    test_find_function_at_cursor_on_global_var,
    test_find_function_at_cursor_empty_code,
    test_find_function_at_cursor_skips_control_flow_keywords,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
