"""Tests des outils bas niveau brace/comment-aware (ui/generation/brace_utils.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.brace_utils import (
    strip_fences, match_brace, find_function_body, iter_functions,
)


def test_strip_fences_removes_cpp_fence():
    txt = "```cpp\nvoid setup() {}\n```"
    assert strip_fences(txt) == "void setup() {}"


def test_strip_fences_noop_when_unfenced():
    assert strip_fences("void loop() {}") == "void loop() {}"


def test_match_brace_simple():
    code = "void f() { int x = 1; }"
    open_idx = code.index("{")
    assert code[match_brace(code, open_idx)] == "}"


def test_match_brace_nested():
    code = "void f() { if (a) { g(); } }"
    open_idx = code.index("{")
    # le } correspondant est le DERNIER
    assert match_brace(code, open_idx) == len(code) - 1


def test_match_brace_ignores_brace_in_string():
    code = 'void f() { Serial.print("}"); }'
    open_idx = code.index("{")
    assert match_brace(code, open_idx) == len(code) - 1


def test_match_brace_ignores_brace_in_comment():
    code = "void f() { // }\n int x; }"
    open_idx = code.index("{")
    assert match_brace(code, open_idx) == len(code) - 1


def test_find_function_body_returns_inner_text():
    code = "int g(int a) {\n  return a;\n}"
    span = find_function_body(code, "g")
    assert span is not None
    sig_start, body_start, body_end, end = span
    assert code[body_start:body_end].strip() == "return a;"
    assert code[sig_start:end].strip() == code.strip()


def test_find_function_body_absent():
    assert find_function_body("int x = 1;", "setup") is None


def test_iter_functions_finds_all_top_level():
    code = (
        "#include <X.h>\n"
        "int g = 3;\n"
        "void setup() { pinMode(1, OUTPUT); }\n"
        "void loop() { foo(); }\n"
        "void foo() { digitalWrite(1, HIGH); }\n"
    )
    names = [f[0] for f in iter_functions(code)]
    assert names == ["setup", "loop", "foo"]


def test_iter_functions_skips_nested():
    code = "void setup() { if (x) { y(); } }\n"
    names = [f[0] for f in iter_functions(code)]
    assert names == ["setup"]   # y() is nested, not top-level


TESTS = [
    test_strip_fences_removes_cpp_fence, test_strip_fences_noop_when_unfenced,
    test_match_brace_simple, test_match_brace_nested,
    test_match_brace_ignores_brace_in_string, test_match_brace_ignores_brace_in_comment,
    test_find_function_body_returns_inner_text, test_find_function_body_absent,
    test_iter_functions_finds_all_top_level, test_iter_functions_skips_nested,
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
