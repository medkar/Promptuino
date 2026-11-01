"""Combinaison des prompts de fonctionnalités (régénération combinée)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.generation.gen_prompts import combine_feature_prompts


def test_combine_two():
    assert combine_feature_prompts(["lis le cap", "affiche le cap sur l'OLED"]) \
        == "lis le cap, et affiche le cap sur l'OLED"

def test_combine_skips_empty():
    assert combine_feature_prompts(["lis le cap", "", "  "]) == "lis le cap"

def test_combine_single():
    assert combine_feature_prompts(["fais une boussole"]) == "fais une boussole"

TESTS = [test_combine_two, test_combine_skips_empty, test_combine_single]

def main():
    f = 0
    for t in TESTS:
        try: t(); print("OK  ", t.__name__)
        except AssertionError as e: f += 1; print("FAIL", t.__name__, e)
    print(f"\n{len(TESTS)-f}/{len(TESTS)} tests passed")
    sys.exit(1 if f else 0)

if __name__ == "__main__":
    main()
