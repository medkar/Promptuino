"""Tests de persistance du champ Project.features + migration legacy."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.project_manager import Project, ProjectType
from ui.generation.feature_model import Feature, FeatureFunction


def test_features_roundtrip_in_to_from_dict():
    p = Project(path=Path("."), name="x", type=ProjectType.ARDUINO)
    p.features = [Feature(id="f1", prompt="led",
                          functions=[FeatureFunction(name="blink", code="void blink(){}")])]
    d = p.to_dict()
    p2 = Project.from_dict(d, Path("."), ProjectType.ARDUINO)
    assert len(p2.features) == 1
    assert p2.features[0].functions[0].name == "blink"


def test_legacy_project_has_empty_features():
    # A .promptuino.json from before the refactor has no "features" key.
    d = {"name": "old", "type": ProjectType.ARDUINO.value}
    p = Project.from_dict(d, Path("."), ProjectType.ARDUINO)
    assert p.features == []


TESTS = [test_features_roundtrip_in_to_from_dict, test_legacy_project_has_empty_features]


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
