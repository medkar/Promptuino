"""_is_scope_error : reconnait « X was not declared in this scope » (couplage
entre fonctionnalites) -> routage vers la reparation fichier-entier (hoist global).
Helper pur, sans Qt ni arduino-cli."""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.arduino_cli import _is_scope_error, _scope_repair_hint

_SCOPE = "sketch.ino:42:5: error: 'cap' was not declared in this scope\n   42 | display.print(cap);"
_SCOPE_CAPS = "error: 'heading' WAS NOT DECLARED IN THIS SCOPE"
_OTHER = "sketch.ino:10:3: error: expected ';' before '}' token"
_MISSING = "fatal error: Servo.h: No such file or directory"

def test_scope_detected(): assert _is_scope_error(_SCOPE) is True
def test_scope_case_insensitive(): assert _is_scope_error(_SCOPE_CAPS) is True
def test_other_error_not_scope(): assert _is_scope_error(_OTHER) is False
def test_missing_lib_not_scope(): assert _is_scope_error(_MISSING) is False
def test_empty_not_scope(): assert _is_scope_error("") is False

def test_hint_extracts_name():
    h = _scope_repair_hint(_SCOPE)
    assert "`cap`" in h and "GLOBAL" in h and "Do NOT re-declare" in h, h

def test_hint_multiple_names():
    err = ("error: 'cap' was not declared in this scope\n"
           "error: 'heading' was not declared in this scope")
    h = _scope_repair_hint(err)
    assert "`cap`" in h and "`heading`" in h, h

def test_hint_fallback_no_name():
    h = _scope_repair_hint("error: something was not declared in this scope")
    assert "shared variable" in h, h

TESTS = [test_scope_detected, test_scope_case_insensitive,
         test_other_error_not_scope, test_missing_lib_not_scope, test_empty_not_scope,
         test_hint_extracts_name, test_hint_multiple_names, test_hint_fallback_no_name]
def main():
    f = 0
    for t in TESTS:
        try: t(); print("OK  ", t.__name__)
        except AssertionError as e: f += 1; print("FAIL", t.__name__, e)
    print(f"\n{len(TESTS)-f}/{len(TESTS)} tests passed")
    sys.exit(1 if f else 0)
if __name__ == "__main__": main()
