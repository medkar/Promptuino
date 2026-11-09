"""LogWidget extrait dans ui/studio/ : import, helpers HTML, API intacte."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(sys.argv)   # ref module-level

from ui.studio import LogWidget, phase_div_html, phase_title_html


def test_phase_html_shape():
    h = phase_title_html("Compilation", "#3b82f6")
    assert "border-left: 3px solid #3b82f6" in h
    assert "<b style=" in h and "Compilation" in h
    d = phase_div_html("<span>x</span>", "#fff")
    assert d.startswith("<div style=") and d.endswith("</div>")


def test_widget_api():
    w = LogWidget()
    for name in ("clear", "begin_phase", "append_raw", "append_serial",
                 "begin_serial_section", "append_explanation", "set_done",
                 "set_failed", "set_live_line", "commit_live_line",
                 "clear_live_line", "set_bottom_bar", "set_auto_scroll",
                 "show_repairs_action", "hide_actions"):
        assert callable(getattr(w, name)), name
    w.begin_phase("Test", "#3b82f6")
    w.append_raw("error: boom\nwarning: hmm\nok")
    w.set_done(True, "Fini")
    assert "Test" in w._text.toPlainText()


def test_compat_import_studio_view():
    import ui.studio_view as sv
    assert sv.LogWidget is LogWidget


def test_a_line_written_during_the_live_line_survives_the_next_tick():
    """Audit 2026-11-06 : set_live_line effacait de l'ancre jusqu'a la FIN du
    document, donc tout ce qui s'ecrivait pendant l'animation (diagnostics
    RAG, avertissement prompt trop long) disparaissait au tick suivant."""
    w = LogWidget()
    w.set_live_line("<b>LOADER frame0</b>")
    w.append_raw("[RAG] diagnostic important")
    w.begin_phase("Prompt trop long !", "#f59e0b")
    w.set_live_line("<b>LOADER frame1</b>")
    w.set_live_line("<b>LOADER frame2</b>")
    txt = w._text.toPlainText()
    assert "[RAG] diagnostic important" in txt, txt
    assert "Prompt trop long !" in txt, txt
    assert "LOADER frame2" in txt and "frame0" not in txt and "frame1" not in txt, txt
    w.clear_live_line()
    txt = w._text.toPlainText()
    assert "LOADER" not in txt and "Prompt trop long !" in txt, txt


TESTS = [test_phase_html_shape, test_widget_api, test_compat_import_studio_view,
         test_a_line_written_during_the_live_line_survives_the_next_tick]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
        except Exception as exc:
            print(f"FAIL {t.__name__}: {exc!r}")
            sys.stdout.flush()
            os._exit(1)
        passed += 1
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0)
