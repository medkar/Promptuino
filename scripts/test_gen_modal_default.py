"""Tests du défaut intelligent de la modale (ui/generation/gen_modal.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.gen_modal import default_action
from ui.generation.feature_model import Feature


def test_default_regenerate_when_empty():
    assert default_action([], "fais clignoter une led") == "regenerate"


def test_default_add_after_generation():
    assert default_action([Feature(id="f1", prompt="led")], "ajoute un buzzer") == "add"


def test_correct_is_no_longer_inferred_from_prompt_prefix():
    # Contrat ACTUEL (cf. docstring de default_action) : « correct » n'est plus
    # deduit d'un prefixe « CORRECTION … » du prompt — il est force
    # explicitement via GenerationModal(default_override=CORRECT)
    # (StudioView.open_modify_flow). Les deux tests qui exigeaient l'ancienne
    # deduction sont donc remplaces par cette garde.
    feats = [Feature(id="f1", prompt="led")]
    assert default_action(feats, "CORRECTION LED sur D9 : clignote") == "add"
    assert default_action([], "  correction servo sur D3 : ") == "regenerate"


TESTS = [
    test_default_regenerate_when_empty, test_default_add_after_generation,
    test_correct_is_no_longer_inferred_from_prompt_prefix,
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
