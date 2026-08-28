"""Helpers d'unification StudioView (Prompt 1) — parties pures."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(sys.argv)   # ref module-level

from ui.studio_view import StudioView
from ui.studio.compile_service import upload_error_class, cu_status_label


def test_upload_error_class():
    f = upload_error_class
    assert f("no PORT found") == "port"
    assert f("Serial device busy") == "port"
    assert f("upload TIMEOUT") == "timeout"
    assert f("compile failed") == "compile"
    assert f("error: 'x' was not declared") == "compile"
    assert f("undefined reference") == "compile"
    assert f("???") == "unknown"
    assert f("") == "unknown"
    assert f(None) == "unknown"


def test_feature_from_parsed():
    from ui.generation import parse_sketch
    parsed = parse_sketch(
        "#include <Servo.h>\nint x = 1;\n"
        "void setup() {\n  x = 2;\n}\nvoid loop() {\n  x = 3;\n}\n")
    f = StudioView._feature_from_parsed(parsed, "f2", "fais un truc", "Truc")
    assert f.id == "f2" and f.includes and f.setup_lines and f.loop_lines
    assert f.prompts == ["fais un truc"]          # seed __post_init__
    f2 = StudioView._feature_from_parsed(None, "f1", "p", "s", prompts=["a", "b"])
    assert f2.includes == [] and f2.prompts == ["a", "b"] and f2.prompt == "p"


def test_cu_status_label():
    from ui.i18n import lang_manager
    s = lang_manager.current
    label, color = cu_status_label("compile", 1, 3)
    assert label == s.studio_compiling and color == "#3b82f6"
    label, color = cu_status_label("compile", 2, 3)
    assert "(2/3)" in label
    label, color = cu_status_label("upload", 1, 3)
    assert label == s.studio_uploading and color == "#8b5cf6"
    label, color = cu_status_label("fix", 1, 2)
    assert "(1/2)" in label and color == "#f97316"
    label, color = cu_status_label("inconnu", 1, 1)
    assert color == "#3b82f6"          # fallback


TESTS = [test_upload_error_class, test_feature_from_parsed, test_cu_status_label]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        t()
        passed += 1
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0)
