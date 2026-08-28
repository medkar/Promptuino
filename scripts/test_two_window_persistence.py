"""Persistance du buffer stable (champ stable_code de Project)."""
import os
import sys
import tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.project_manager import Project, ProjectType


def test_stable_code_roundtrip():
    d = {"name": "p", "type": ProjectType.ARDUINO.value, "stable_code": "void loop(){}"}
    proj = Project.from_dict(d, Path("x"), ProjectType.ARDUINO)
    assert proj.stable_code == "void loop(){}"
    assert proj.to_dict()["stable_code"] == "void loop(){}"


def test_stable_code_defaults_empty_for_legacy():
    d = {"name": "p", "type": ProjectType.ARDUINO.value}
    proj = Project.from_dict(d, Path("x"), ProjectType.ARDUINO)
    assert proj.stable_code == ""


def test_default_field_is_empty():
    proj = Project(path=Path("x"), name="p", type=ProjectType.ARDUINO)
    assert proj.stable_code == ""


def test_stable_features_roundtrip():
    from ui.generation.feature_model import Feature
    f = Feature(id="f1", prompt="fais clignoter une LED")
    proj = Project(path=Path("x"), name="p", type=ProjectType.ARDUINO,
                   stable_features=[f])
    d = proj.to_dict()
    back = Project.from_dict(d, Path("x"), ProjectType.ARDUINO)
    assert len(back.stable_features) == 1
    assert back.stable_features[0].id == "f1"
    assert back.stable_features[0].first_prompt == "fais clignoter une LED"


def test_studio_saves_and_loads_stable_features():
    import tempfile
    from pathlib import Path
    from ui.studio_view import StudioView
    from ui.project_manager import Project, ProjectType
    from ui.generation.feature_model import Feature
    v = StudioView()
    v._on_mode_changed("advanced")
    with tempfile.TemporaryDirectory() as tmp:
        proj = Project(path=Path(tmp) / "p", name="p", type=ProjectType.ARDUINO)
        v._current_project = proj
        v._stable_features = [Feature(id="f1", prompt="led")]
        v._stable_panel.editor.setPlainText("void loop(){}\n")
        v.save_project()
    assert [f.id for f in v._current_project.stable_features] == ["f1"]


TESTS = [test_stable_code_roundtrip, test_stable_code_defaults_empty_for_legacy,
         test_default_field_is_empty, test_stable_features_roundtrip,
         test_studio_saves_and_loads_stable_features]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        t()
        passed += 1
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0)
