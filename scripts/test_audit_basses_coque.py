"""Audit 2026-11-06, constats de gravite BASSE de la « coque » (arduino_cli,
main_window, project_manager, serial_monitor, session, settings_dialog,
code_editor, components_view, explain_code_dialog, lib_choice_dialog,
library_view, workspace).

⚠️ AUCUNE ecriture dans ~/Documents/Promptuino. Importer `ui.session`
importe `ui/__init__` (donc toute l'app) : le vrai singleton est deja LU a ce
moment-la, et `ui.workspace` l'a deja lie. Les tests qui touchent la session
travaillent donc sur une instance TEMPORAIRE, injectee la ou elle est lue
(`ui.workspace.session`), et `platform_dir` est detourne pour la config
arduino-cli. Aucun serveur, aucun arduino-cli.

Run : python scripts/test_audit_basses_coque.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

_TMP = Path(tempfile.mkdtemp(prefix="audit_coque_"))
import ui.session as session_mod  # noqa: E402
_VRAI_CHEMIN = session_mod._SESSION_PATH
session_mod._SESSION_PATH = _TMP / "session.json"
_SESSION_TMP = session_mod.Session()      # jamais le vrai fichier
session_mod._SESSION_PATH = _VRAI_CHEMIN

import ui.declared_components as declared_components  # noqa: E402
declared_components.set_registry([])

_VIVANTS: list = []


class _FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot, *_a, **_k):
        self.slots.append(slot)


# ── arduino_cli.py:531 ────────────────────────────────────────────────────

def test_a_url_in_a_string_does_not_unbalance_the_sketch():
    from ui.arduino_cli import _is_structurally_balanced
    code = ('void setup() {\n  Serial.println("http://x.com");\n}\n'
            'void loop() { /* ( */ char c = \'(\'; // )\n}\n')
    assert _is_structurally_balanced(code)
    # Une vraie parenthese manquante reste vue.
    assert not _is_structurally_balanced('void f() { g("http://a"; }')


# ── main_window.py:723 ────────────────────────────────────────────────────

def test_closing_waits_for_the_update_check():
    from ui.main_window import MainWindow
    attendu = []
    worker = SimpleNamespace(isRunning=lambda: True,
                             wait=lambda ms: attendu.append(ms) or True)
    fake = SimpleNamespace(_views={}, _update_worker=worker)
    event = MagicMock()
    MainWindow.closeEvent(fake, event)
    assert event.accept.called
    assert attendu, "le fil de mise a jour n'est pas attendu a la fermeture"


# ── project_manager.py:424 / 559 ──────────────────────────────────────────

def test_a_cp1252_sketch_still_opens():
    from ui.project_manager import ProjectManager, Project, ProjectType
    d = Path(tempfile.mkdtemp(dir=_TMP)) / "proj"
    d.mkdir()
    (d / "proj.ino").write_bytes("// é\nvoid setup() {}\n".encode("cp1252"))
    p = Project(path=d, name="proj", type=list(ProjectType)[0])
    code = ProjectManager().load_code(p)
    assert "// é" in code, code


def test_renaming_only_the_case_works():
    from ui.project_manager import ProjectManager, Project, ProjectType
    parent = Path(tempfile.mkdtemp(dir=_TMP))
    d = parent / "led"
    d.mkdir()
    (d / "led.ino").write_text("void setup() {}\n", encoding="utf-8")
    p = Project(path=d, name="led", type=list(ProjectType)[0])
    ProjectManager().rename(p, "LED")
    assert os.listdir(parent) == ["LED"], os.listdir(parent)
    assert "LED.ino" in os.listdir(parent / "LED"), os.listdir(parent / "LED")


def test_renaming_onto_another_project_still_refuses():
    from ui.project_manager import ProjectManager, Project, ProjectType
    parent = Path(tempfile.mkdtemp(dir=_TMP))
    for n in ("a", "b"):
        (parent / n).mkdir()
        (parent / n / f"{n}.ino").write_text("", encoding="utf-8")
    p = Project(path=parent / "a", name="a", type=list(ProjectType)[0])
    try:
        ProjectManager().rename(p, "b")
    except FileExistsError:
        return
    raise AssertionError("renommer sur un projet existant a ete accepte")


# ── serial_monitor.py:193 / 378 / 455 ─────────────────────────────────────

def _monitor():
    from ui.serial_monitor import SerialMonitorWidget
    w = SerialMonitorWidget()
    _VIVANTS.append(w)
    return w


def test_the_serial_display_is_bounded():
    w = _monitor()
    assert w._display.maximumBlockCount() > 0


def test_connect_without_a_port_says_so():
    import ui.serial_monitor as sm
    from ui.i18n import lang_manager
    w = _monitor()
    vrais = (sm.board_manager, sm.arduino_cli)
    sm.board_manager = SimpleNamespace(port="")
    sm.arduino_cli = SimpleNamespace(_find_port_auto=lambda: "")
    try:
        w.open_port(refresh_baud=False)
    finally:
        sm.board_manager, sm.arduino_cli = vrais
    assert lang_manager.current.studio_err_no_port in \
        w._display.toPlainText(), w._display.toPlainText()


def test_a_worker_still_finishing_is_parked_not_dropped():
    import ui.serial_monitor as sm
    w = _monitor()
    fake = SimpleNamespace(isRunning=lambda: True, finished=_FakeSignal())
    w._worker = fake
    w._on_error("port pris")
    try:
        assert w._worker is None
        assert fake in sm._STILL_RUNNING, \
            "le fil encore actif a perdu sa derniere reference"
        assert fake.finished.slots
        w._on_disconnected()            # le second signal du finally
        assert sm._STILL_RUNNING.count(fake) == 1
    finally:
        while fake in sm._STILL_RUNNING:
            sm._STILL_RUNNING.remove(fake)


# ── session.py:38 ─────────────────────────────────────────────────────────

def test_a_session_file_of_the_wrong_type_does_not_crash():
    for contenu in ("[]", "null", "42"):
        d = Path(tempfile.mkdtemp(dir=_TMP))
        vrai = session_mod._SESSION_PATH
        session_mod._SESSION_PATH = d / "session.json"
        try:
            (d / "session.json").write_text(contenu, encoding="utf-8")
            s = session_mod.Session()
            assert s.is_workspace_root_configured() is False
            assert (d / "session.json.corrupt").exists(), contenu
        finally:
            session_mod._SESSION_PATH = vrai


# ── settings_dialog.py:594 ────────────────────────────────────────────────

def test_the_backstage_button_follows_the_theme():
    from ui.settings_dialog import SettingsDialog
    from ui.theme import theme_manager
    fake = MagicMock()
    SettingsDialog.apply_theme(fake, theme_manager.current)
    assert fake._btn_backstage.apply_theme.called


# ── code_editor.py:210 ────────────────────────────────────────────────────

def _formats(text: str):
    from PyQt6.QtGui import QTextDocument
    from ui.code_editor import ArduinoHighlighter
    doc = QTextDocument()
    h = ArduinoHighlighter(doc)
    _VIVANTS.extend([doc, h])
    doc.setPlainText(text)
    h.rehighlight()
    comment = h._fmt_comment.foreground().color()

    def is_comment(line: int, col: int) -> bool:
        block = doc.findBlockByNumber(line)
        for r in block.layout().formats():
            if r.start <= col < r.start + r.length:
                return r.format.foreground().color() == comment
        return False
    return is_comment


def test_a_block_comment_opener_in_a_string_is_not_a_comment():
    is_c = _formats('Serial.println("a /* b");\nint x = 1;\n')
    assert not is_c(1, 0), "la ligne suivante est grisee comme un commentaire"


def test_a_block_comment_opener_after_a_line_comment_is_inert():
    is_c = _formats('int a; // voir /* ici\nint y = 2;\n')
    assert is_c(0, 8)
    assert not is_c(1, 0)


def test_a_url_keeps_its_string_colour():
    text = 'f("http://x");'
    is_c = _formats(text)
    assert not is_c(0, text.index('");') + 0), "fin de chaine coloree en commentaire"


def test_real_comments_are_still_coloured():
    is_c = _formats('int a; /* debut\nmilieu\nfin */ int b; // fin\n')
    assert is_c(0, 8) and is_c(1, 0) and is_c(2, 0)
    assert not is_c(2, 7)
    assert is_c(2, 15)


# ── components_view.py:556 ────────────────────────────────────────────────

def test_a_language_switch_keeps_the_grid_lazy():
    from ui.components_view import ComponentsView, _ComponentCardWidget
    from ui.i18n import lang_manager
    v = ComponentsView()
    _VIVANTS.append(v)
    v.apply_lang(lang_manager.current)
    assert v._rendered is False
    assert not v.findChildren(_ComponentCardWidget)
    v.refresh()
    v.apply_lang(lang_manager.current)   # une grille rendue suit la langue
    assert v.findChildren(_ComponentCardWidget)


# ── explain_code_dialog.py:125 ────────────────────────────────────────────

def test_the_explain_dialog_is_freed_and_parks_its_request():
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent, Qt
    import ui.explain_code_dialog as ecd
    dlg = ecd.ExplainCodeDialog(object(), "void setup() {}", "", "Arduino Uno")
    assert dlg.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    fake = SimpleNamespace(isRunning=lambda: True, finished=_FakeSignal(),
                           error=_FakeSignal(), wait=lambda *a: True)
    dlg._worker = fake
    dlg.show()
    dlg.done(0)
    try:
        assert fake in ecd._PARKED, "la requete en cours meurt avec la fenetre"
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        assert sip.isdeleted(dlg), "la fenetre fermee reste vivante"
        fake.finished.slots[0]("texte")
        assert fake not in ecd._PARKED
    finally:
        while fake in ecd._PARKED:
            ecd._PARKED.remove(fake)


# ── lib_choice_dialog.py:270 ──────────────────────────────────────────────

def test_a_typed_name_is_escaped_in_the_body():
    import ui.lib_choice_dialog as lcd

    class _FakeLoader:
        def __init__(self, *_a, **_k):
            self.done = _FakeSignal()

        def start(self):
            pass
    vrai = lcd._IndexLoader
    lcd._IndexLoader = _FakeLoader
    try:
        dlg = lcd.LibChoiceDialog(None, token="capteur <3v", current_lib="R&D",
                                  alternatives=[], config_file="", arch="")
    finally:
        lcd._IndexLoader = vrai
    _VIVANTS.append(dlg)
    body = dlg._lbl_body.text()
    assert "&lt;3V" in body and "R&amp;D" in body, body


# ── library_view.py:699 ───────────────────────────────────────────────────

def test_clearing_the_search_drops_the_late_result():
    from ui.library_view import LibraryView
    fake = MagicMock()
    fake._search_request_id = 5
    LibraryView._on_search_text_changed(fake, "")
    LibraryView._on_search_done(fake, 5, [{"name": "Servo"}])
    assert not fake._render_search.called, "resultat tardif affiche"
    fake2 = MagicMock()
    fake2._search_request_id = 5
    LibraryView._on_search_text_changed(fake2, "s")
    LibraryView._on_search_done(fake2, 5, [])
    assert not fake2._render_search.called


# ── workspace.py:64 / 121 ─────────────────────────────────────────────────

def test_an_unwritable_root_does_not_raise_in_the_slot():
    import ui.workspace as wsm
    bloque = _TMP / "un_fichier"
    bloque.write_text("x", encoding="utf-8")   # mkdir dessous echoue
    _SESSION_TMP._data["workspace_root"] = str(bloque)
    vraie = wsm.session
    wsm.session = _SESSION_TMP
    try:
        assert wsm.workspace_manager.root == bloque
        wsm.workspace_manager._ensure_structure()  # ne doit pas lever
    finally:
        wsm.session = vraie
        _SESSION_TMP._data.pop("workspace_root", None)


def test_cli_config_recreates_its_folder_and_skips_identical_writes():
    from ui.workspace import WorkspaceManager, workspace_manager
    base = Path(tempfile.mkdtemp(dir=_TMP)) / "Arduino"
    vrais = (WorkspaceManager._get_data_dir, workspace_manager.platform_dir)
    WorkspaceManager._get_data_dir = staticmethod(lambda: "")
    workspace_manager.platform_dir = lambda env: base
    try:
        cfg = Path(workspace_manager.cli_config("arduino:avr:uno"))
        assert cfg.exists()
        avant = cfg.stat().st_mtime_ns
        os.utime(cfg, ns=(avant - 10**9, avant - 10**9))
        fige = cfg.stat().st_mtime_ns
        workspace_manager.cli_config("arduino:avr:uno")
        assert cfg.stat().st_mtime_ns == fige, "fichier identique reecrit"
    finally:
        WorkspaceManager._get_data_dir = vrais[0]
        del workspace_manager.platform_dir


TESTS = [
    test_a_url_in_a_string_does_not_unbalance_the_sketch,
    test_closing_waits_for_the_update_check,
    test_a_cp1252_sketch_still_opens,
    test_renaming_only_the_case_works,
    test_renaming_onto_another_project_still_refuses,
    test_the_serial_display_is_bounded,
    test_connect_without_a_port_says_so,
    test_a_worker_still_finishing_is_parked_not_dropped,
    test_a_session_file_of_the_wrong_type_does_not_crash,
    test_the_backstage_button_follows_the_theme,
    test_a_block_comment_opener_in_a_string_is_not_a_comment,
    test_a_block_comment_opener_after_a_line_comment_is_inert,
    test_a_url_keeps_its_string_colour,
    test_real_comments_are_still_coloured,
    test_a_language_switch_keeps_the_grid_lazy,
    test_the_explain_dialog_is_freed_and_parks_its_request,
    test_a_typed_name_is_escaped_in_the_body,
    test_clearing_the_search_drops_the_late_result,
    test_an_unwritable_root_does_not_raise_in_the_slot,
    test_cli_config_recreates_its_folder_and_skips_identical_writes,
]


def main() -> None:
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
