"""CodeEditor : auto-indentation a l'Entree (conserve l'indentation, +1 niveau
apres « { », developpe une paire « {|} » en bloc indente)."""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor
from ui.code_editor import CodeEditor


def _press(ed, key, text=""):
    ed.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text))


def _at_end(ed):
    ed.moveCursor(QTextCursor.MoveOperation.End)


def test_enter_replicates_current_indentation():
    ed = CodeEditor()
    ed.setPlainText("    int x = 1;")          # 4 espaces de retrait
    _at_end(ed)
    _press(ed, Qt.Key.Key_Return, "\r")
    lines = ed.toPlainText().split("\n")
    assert lines[0] == "    int x = 1;"
    assert lines[1] == "    "                   # la nouvelle ligne garde le retrait


def test_enter_after_open_brace_adds_one_level():
    ed = CodeEditor()
    ed.setPlainText("void setup() {")          # pas de « } » apres le curseur
    _at_end(ed)
    _press(ed, Qt.Key.Key_Return, "\r")
    lines = ed.toPlainText().split("\n")
    assert lines[0] == "void setup() {"
    assert lines[1] == "\t"                     # UN niveau d'indentation (tab)


def test_enter_after_open_brace_stacks_on_existing_indent():
    ed = CodeEditor()
    ed.setPlainText("\tif (x) {")              # deja 1 tab de retrait
    _at_end(ed)
    _press(ed, Qt.Key.Key_Return, "\r")
    lines = ed.toPlainText().split("\n")
    assert lines[1] == "\t\t"                   # retrait courant + 1 niveau


def test_brace_pair_expands_into_indented_block():
    ed = CodeEditor()
    ed.setPlainText("void loop() ")
    _at_end(ed)
    # Frappe « { » -> auto-paire « {} », curseur entre les accolades.
    _press(ed, Qt.Key.Key_BraceLeft, "{")
    assert ed.toPlainText() == "void loop() {}"
    # Entree -> developpe le bloc.
    _press(ed, Qt.Key.Key_Return, "\r")
    assert ed.toPlainText() == "void loop() {\n\t\n}"
    cur = ed.textCursor()
    assert cur.block().text() == "\t"           # curseur sur la ligne du milieu
    assert cur.positionInBlock() == 1           # apres la tabulation


def test_brace_expansion_preserves_outer_indent():
    ed = CodeEditor()
    ed.setPlainText("\tvoid loop() ")          # bloc deja indente d'1 tab
    _at_end(ed)
    _press(ed, Qt.Key.Key_BraceLeft, "{")
    _press(ed, Qt.Key.Key_Return, "\r")
    assert ed.toPlainText() == "\tvoid loop() {\n\t\t\n\t}"


def test_enter_is_single_undo_step():
    ed = CodeEditor()
    ed.setPlainText("void loop() ")
    _at_end(ed)
    _press(ed, Qt.Key.Key_BraceLeft, "{")
    _press(ed, Qt.Key.Key_Return, "\r")
    assert ed.toPlainText() == "void loop() {\n\t\n}"
    ed.undo()                                   # 1 seul Ctrl+Z annule l'expansion
    assert ed.toPlainText() == "void loop() {}"


def test_enter_on_plain_line_no_extra_indent():
    ed = CodeEditor()
    ed.setPlainText("int y;")                   # ni retrait ni « { »
    _at_end(ed)
    _press(ed, Qt.Key.Key_Return, "\r")
    assert ed.toPlainText() == "int y;\n"


TESTS = [test_enter_replicates_current_indentation,
         test_enter_after_open_brace_adds_one_level,
         test_enter_after_open_brace_stacks_on_existing_indent,
         test_brace_pair_expands_into_indented_block,
         test_brace_expansion_preserves_outer_indent,
         test_enter_is_single_undo_step,
         test_enter_on_plain_line_no_extra_indent]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t(); print("OK  ", t.__name__)
        except AssertionError as e:
            failed += 1; print("FAIL", t.__name__, e)
    print(f"\n{len(TESTS)-failed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
