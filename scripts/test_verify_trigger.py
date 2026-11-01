import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.studio_view import should_verify_assembly, REGENERATE, ADD, CORRECT

def test_add_multi(): assert should_verify_assembly(ADD, 2) is True
def test_regenerate(): assert should_verify_assembly(REGENERATE, 1) is False
def test_add_single(): assert should_verify_assembly(ADD, 1) is False
def test_correct_multi(): assert should_verify_assembly(CORRECT, 3) is True

TESTS = [test_add_multi, test_regenerate, test_add_single, test_correct_multi]
def main():
    f = 0
    for t in TESTS:
        try: t(); print("OK  ", t.__name__)
        except AssertionError as e: f += 1; print("FAIL", t.__name__, e)
    print(f"\n{len(TESTS)-f}/{len(TESTS)} tests passed")
    sys.exit(1 if f else 0)
if __name__ == "__main__": main()
