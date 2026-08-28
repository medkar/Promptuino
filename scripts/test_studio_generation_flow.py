"""generation_flow (ui/studio) : worker de génération + aperçu de prompt."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(sys.argv)   # ref module-level

from ui.studio import GenerateWorker, build_codegen_preview, PromptPreviewDialog


def test_compose_user_prompt_beginner_pedagogical():
    out = GenerateWorker.compose_user_prompt("clignote une LED", "beginner", 0)
    assert "clignote une LED" in out
    assert "learner discovering embedded programming" in out


def test_compose_user_prompt_advanced_verbosity_none():
    out = GenerateWorker.compose_user_prompt("x", "advanced", 0)
    assert "Do NOT add ANY comments" in out
    out3 = GenerateWorker.compose_user_prompt("x", "advanced", 3)
    assert "learner discovering embedded programming" in out3
    # Clamp hors bornes.
    assert GenerateWorker.compose_user_prompt("x", "advanced", 99)


def test_build_codegen_preview_has_both_sections():
    class _FakeBackend:
        def codegen_system_prompt(self, board, rules):
            return f"SYS[{board}|{rules}]"
    txt = build_codegen_preview(_FakeBackend(), "user prompt", "Arduino Uno",
                                "beginner", 2, rules_prompt="raw")
    assert "SYSTEM PROMPT" in txt and "MESSAGE UTILISATEUR" in txt
    assert "SYS[Arduino Uno|raw]" in txt      # rules_prompt utilisé, pas augmenté
    assert "user prompt" in txt


def test_compat_aliases_in_studio_view():
    import ui.studio_view as sv
    assert sv._GenerateWorker is GenerateWorker
    assert sv._build_codegen_preview is build_codegen_preview
    assert sv._PromptPreviewDialog is PromptPreviewDialog


TESTS = [test_compose_user_prompt_beginner_pedagogical,
         test_compose_user_prompt_advanced_verbosity_none,
         test_build_codegen_preview_has_both_sections,
         test_compat_aliases_in_studio_view]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        t()
        passed += 1
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0)
