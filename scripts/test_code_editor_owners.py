"""CodeEditor : ancres de proprietaires (QTextBlockUserData) + heritage +
rendu extraSelections du surlignage par fonctionnalite (#29)."""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from PyQt6.QtGui import QColor, QTextCursor
from ui.code_editor import CodeEditor

CODE = "int a;\nint b;\nint c;"


def _editor():
    ed = CodeEditor()
    ed.setPlainText(CODE)
    ed.set_line_owners(["f1", "f1", "f2"])
    return ed


def test_roundtrip():
    ed = _editor()
    assert ed.line_owners() == ["f1", "f1", "f2"]


def test_edit_in_place_keeps_owner():
    ed = _editor()
    cur = ed.textCursor()
    cur.setPosition(len("int a;") - 1)
    cur.insertText("aa")                       # edite la ligne 0 en place
    assert ed.line_owners() == ["f1", "f1", "f2"]


def test_inserted_line_inherits_from_above():
    ed = _editor()
    cur = ed.textCursor()
    cur.setPosition(len("int a;"))             # fin de ligne 0
    cur.insertText("\nint nouveau;")           # nouvelle ligne sous f1
    assert ed.line_owners() == ["f1", "f1", "f1", "f2"]


def test_inserted_line_at_start_inherits_above():
    # Enter PILE au debut de « int b; » : la nouvelle ligne (vide) herite du
    # bloc au-dessus (f1) et « int b; » GARDE f2 (la data suit le contenu).
    ed = CodeEditor()
    ed.setPlainText(CODE)
    ed.set_line_owners(["f1", "f2", "f3"])
    cur = ed.textCursor()
    cur.setPosition(len("int a;") + 1)         # position du bloc 1
    cur.insertText("\n")
    assert ed.line_owners() == ["f1", "f1", "f2", "f3"], ed.line_owners()


def test_paste_at_start_keeps_owner_on_content():
    # Collage d'une ligne complete au debut de « int b; » : « int x; »
    # herite de f1, « int b; » garde f2.
    ed = CodeEditor()
    ed.setPlainText(CODE)
    ed.set_line_owners(["f1", "f2", "f3"])
    cur = ed.textCursor()
    cur.setPosition(len("int a;") + 1)         # position du bloc 1
    cur.insertText("int x;\n")
    assert ed.line_owners() == ["f1", "f1", "f2", "f3"], ed.line_owners()


def test_deleted_line_removes_owner():
    ed = _editor()
    cur = ed.textCursor()
    cur.setPosition(0)
    cur.movePosition(QTextCursor.MoveOperation.Down,
                     QTextCursor.MoveMode.KeepAnchor)
    cur.removeSelectedText()                   # supprime la ligne 0
    assert ed.line_owners() == ["f1", "f2"]


def test_setplaintext_resets_owners():
    ed = _editor()
    ed.setPlainText("int x;")
    assert ed.line_owners() == [None]


def test_feature_highlights_extra_selections():
    ed = _editor()
    ed.set_feature_highlights({"f1": QColor("#5EA9FF")})
    sels = ed.extraSelections()
    # Ligne courante possible en plus -> on compte les fonds pleine largeur
    # de la couleur f1 (2 lignes possedees par f1).
    feature_sels = [s for s in sels
                    if s.format.background().color().rgb() & 0xFFFFFF
                    == QColor("#5EA9FF").rgb() & 0xFFFFFF]
    assert len(feature_sels) == 2, len(sels)
    ed.set_feature_highlights({})
    sels = ed.extraSelections()
    assert not [s for s in sels
                if s.format.background().color().alpha() == 64]


def test_scroll_to_first_owned_moves_cursor():
    ed = _editor()
    ed.scroll_to_first_owned("f2")
    assert ed.textCursor().blockNumber() == 2


def test_full_replacement_clears_all_owners():
    # select-all + insertText (remplacement complet) : removed > 0 -> la
    # "data suit le contenu" ne doit PAS s'appliquer (contenu neuf) ->
    # tout orphelin, meme si Qt reutilise un bloc porteur d'un ancien owner
    # (revue finale #29).
    ed = _editor()
    cur = ed.textCursor()
    cur.select(QTextCursor.SelectionType.Document)
    cur.insertText("int x;\nint y;\nint z;\nint w;")
    assert ed.line_owners() == [None, None, None, None], ed.line_owners()


TESTS = [test_roundtrip, test_edit_in_place_keeps_owner,
         test_inserted_line_inherits_from_above,
         test_inserted_line_at_start_inherits_above,
         test_paste_at_start_keeps_owner_on_content,
         test_deleted_line_removes_owner, test_setplaintext_resets_owners,
         test_feature_highlights_extra_selections,
         test_scroll_to_first_owned_moves_cursor,
         test_full_replacement_clears_all_owners]


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
