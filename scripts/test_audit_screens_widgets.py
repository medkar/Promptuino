"""Audit 2026-11-06, lot other-screens-and-widgets (about_dialog, tutorial,
code_editor, lib_choice_dialog). Aucun reseau, aucune ecriture."""
import os, sys, threading, time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QEvent, Qt, QCoreApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QWidget
_APP = QApplication.instance() or QApplication([])
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.theme import theme_manager
from ui.i18n import lang_manager


def _pump(ms=50):
    end = time.time() + ms / 1000
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


# -- 1+3. fenetre "A propos" : fil non detruit, pas de reseau sur le fil GUI --
def test_update_thread_is_not_a_child_of_the_dialog_and_survives_close():
    import ui.about_dialog as ad
    release = threading.Event()
    saved = ad.check_updates
    ad.check_updates = lambda: (release.wait(5) and None)
    try:
        dlg = ad.AboutDialog()
        dlg._on_check_updates()
        w = dlg._maj_worker
        assert w is not None
        assert w.parent() is not dlg, "le fil ne doit pas mourir avec la fenetre"
        _pump(50)
        assert w.isRunning()
        dlg.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        _pump(50)
        assert w.isRunning(), "le fil doit survivre a la fermeture"
    finally:
        release.set()
        _pump(300)
        ad.check_updates = saved


def test_update_result_does_not_hit_the_network_on_the_gui_thread():
    import ui.about_dialog as ad
    import ui.updates as up
    import ui.version as ver
    calls = []
    saved = up.fetch_latest
    saved_release = ver.is_release_build
    up.fetch_latest = lambda *a, **k: calls.append(1) or (None, True)
    try:
        dlg = ad.AboutDialog()
        s = lang_manager.current
        # Build de developpement (les sources) : ni << a jour >> ni << echec >>
        # (audit #124).
        ver.is_release_build = lambda: False
        dlg._on_update_result((None, True))
        assert dlg._lbl_update.text() == s.update_dev_build
        ver.is_release_build = lambda: True
        dlg._on_update_result((None, True))
        assert not calls, "requete HTTP sur le fil graphique"
        assert dlg._lbl_update.text() == s.update_up_to_date
        dlg._on_update_result((None, False))
        assert dlg._lbl_update.text() == s.update_failed
        dlg._on_update_result(("v9.9.9", True))
        assert "9.9.9" in dlg._lbl_update.text()
    finally:
        up.fetch_latest = saved
        ver.is_release_build = saved_release


# -- 2. tutoriel : texte lisible en theme clair ------------------------------
def test_tutorial_text_is_readable_in_light_theme():
    from ui.tutorial import TutorialOverlay
    theme_manager.apply_light()
    try:
        host = QWidget()
        host.resize(800, 600)
        ov = TutorialOverlay(host)
        c = theme_manager.current
        qss = ov._bubble.styleSheet()
        seg = qss[qss.index("#TutoText"):].split("}")[0]
        assert "#ffffff" not in seg.lower(), seg
        assert c.text_primary in seg, seg
        assert c.text_primary.lower() != c.surface.lower()
    finally:
        theme_manager.apply_dark()


# -- 4. editeur verrouille : raccourcis Ctrl qui modifient --------------------
def _key(key, mods=Qt.KeyboardModifier.NoModifier, text=""):
    return QKeyEvent(QEvent.Type.KeyPress, key, mods, text)


def test_locked_editor_blocks_ctrl_edit_shortcuts():
    from ui.code_editor import CodeEditor
    ctrl = Qt.KeyboardModifier.ControlModifier
    for k in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete, Qt.Key.Key_Z,
              Qt.Key.Key_Y, Qt.Key.Key_V, Qt.Key.Key_X):
        assert CodeEditor._is_edit_key(_key(k, ctrl)), k
    for k in (Qt.Key.Key_C, Qt.Key.Key_A, Qt.Key.Key_Left):
        assert not CodeEditor._is_edit_key(_key(k, ctrl)), k
    assert CodeEditor._is_edit_key(
        _key(Qt.Key.Key_Insert, Qt.KeyboardModifier.ShiftModifier))
    ed = CodeEditor()
    ed.setPlainText("int mot")
    ed.set_edit_locked(True)
    from PyQt6.QtGui import QTextCursor
    ed.moveCursor(QTextCursor.MoveOperation.End)
    hits = []
    ed.edit_attempted.connect(lambda: hits.append(1))
    ed.keyPressEvent(_key(Qt.Key.Key_Backspace, ctrl))
    assert ed.toPlainText() == "int mot" and hits == [1]


# -- 5. echec de chargement de l'index != registre vide -----------------------
def test_failed_index_load_is_not_memorised_as_empty():
    import ui.lib_choice_dialog as lcd
    from ui import library_index as li
    import ui.registry_lookup as rl
    li._INDEX, li._LOADED = [], False
    saved = rl.fetch_library_index
    rl.fetch_library_index = lambda cfg: ""
    try:
        dlg = lcd.LibChoiceDialog(token="as7341", current_lib="Adafruit AS7341",
                                  alternatives=[], config_file="x.yaml")
        for _ in range(100):
            _pump(30)
            if dlg._load_failed:
                break
        assert dlg._load_failed
        assert not li.is_loaded(), "un echec ne doit pas devenir un index vide"
        s = lang_manager.current
        assert dlg._lbl_empty.text() == s.lib_choice_search_unavailable
    finally:
        rl.fetch_library_index = saved
        li._INDEX, li._LOADED = [], False


TESTS = [
    test_update_thread_is_not_a_child_of_the_dialog_and_survives_close,
    test_update_result_does_not_hit_the_network_on_the_gui_thread,
    test_tutorial_text_is_readable_in_light_theme,
    test_locked_editor_blocks_ctrl_edit_shortcuts,
    test_failed_index_load_is_not_memorised_as_empty,
]


def main():
    f = 0
    for t in TESTS:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as e:
            f += 1
            print("FAIL", t.__name__, type(e).__name__, ascii(str(e))[:300])
    print(f"\n{len(TESTS)-f}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(1 if f else 0)


if __name__ == "__main__":
    main()
