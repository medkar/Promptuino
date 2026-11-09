"""Audit 2026-11-06, lot app-shell (arduino_cli, board_view/manager,
project_manager, serial_monitor). Aucun appel reseau, aucune ecriture hors
dossier temporaire."""
import os, sys, subprocess, tempfile, types
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from ui import arduino_cli, serial_monitor, project_manager
from ui.board_manager import BoardManager, BoardState


# -- 1. delai d'installation du core ---------------------------------------
def test_core_install_has_a_long_timeout():
    seen = []
    orig = arduino_cli._run
    arduino_cli._run = lambda cmd, cwd=None, register=None, timeout=180: (
        seen.append((cmd, timeout)) or (0, ""))
    try:
        arduino_cli._install_core("arduino:renesas_uno", "cfg")
    finally:
        arduino_cli._run = orig
    assert seen and all(t > 180 for _, t in seen), seen


def _patched_worker(code="void setup(){}\nvoid loop(){}\n"):
    w = arduino_cli.CompileUploadWorker(code, "arduino:renesas_uno:unor4wifi",
                                        backend=object())
    got = {"done": [], "code": []}
    w.done.connect(lambda ok, m: got["done"].append((ok, m)))
    w.code_updated.connect(lambda c: got["code"].append(c))
    return w, got


def test_core_install_timeout_says_it_was_the_core():
    w, got = _patched_worker()
    saved = (arduino_cli._core_installed, arduino_cli._install_core)
    arduino_cli._core_installed = lambda *a, **k: False

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("arduino-cli", 1)
    arduino_cli._install_core = boom
    try:
        w.run()
    finally:
        arduino_cli._core_installed, arduino_cli._install_core = saved
    assert got["done"], got
    ok, msg = got["done"][0]
    assert ok is False and "arduino:renesas" in msg, msg
    assert "arduino-cli timeout" not in msg, msg


# -- 2. revert quand la lib manquante vient d'une reparation ---------------
def test_missing_lib_after_a_repair_reverts_the_editor():
    code = "void setup(){}\nvoid loop(){ int x = ; }\n"
    w, got = _patched_worker(code)
    fixed = "#include <FooBar.h>\n" + code
    outs = iter([(1, "sketch.ino:2: error: expected primary-expression"),
                 (1, "fatal error: FooBar.h: No such file or directory")])
    cls = arduino_cli.CompileUploadWorker
    saved = (arduino_cli._run, arduino_cli._core_installed,
             arduino_cli.line_anchored_repair, cls._ensure_libs)
    arduino_cli._run = lambda *a, **k: next(outs)
    arduino_cli._core_installed = lambda *a, **k: True
    arduino_cli.line_anchored_repair = lambda *a, **k: fixed
    cls._ensure_libs = lambda self, *a, **k: None
    try:
        w.run()
    finally:
        (arduino_cli._run, arduino_cli._core_installed,
         arduino_cli.line_anchored_repair, cls._ensure_libs) = saved
    assert got["code"] and got["code"][0] == fixed, got
    assert got["code"][-1] == code, got["code"]
    assert got["done"] and got["done"][0][0] is False, got


# -- 3. port manuel perime --------------------------------------------------
def test_manual_port_is_forgotten_on_auto_detection_and_unplug():
    bm = BoardManager()
    bm.set_board_manual("arduino", "Uno")
    bm.set_port("COM3")
    bm.set_board_connected("arduino", "Uno")
    assert bm.port == "", bm.port
    bm.set_port("COM3")
    bm.set_connected(False)
    assert bm.port == "", bm.port


def test_switch_to_auto_without_board_forgets_manual_selection():
    from ui import board_view
    bm = BoardManager()
    saved = (board_view.board_manager, board_view.detect_board)
    board_view.board_manager = bm
    board_view.detect_board = lambda: None
    try:
        bm.set_board_manual("arduino", "Uno")
        bm.set_port("COM3")
        view = board_view.BoardView()
        view._switch_to_auto()
    finally:
        board_view.board_manager, board_view.detect_board = saved
    assert (bm.env, bm.model, bm.port) == ("", "", ""), (bm.env, bm.model, bm.port)
    assert bm.state == BoardState.NONE


# -- 4. ecriture atomique + meta corrompue ----------------------------------
def _project(tmp):
    pm = project_manager.ProjectManager()
    p = project_manager.Project(
        path=Path(tmp) / "demo", name="demo",
        type=list(project_manager.ProjectType)[0],
        mode="beginner", created_at="x", updated_at="x")
    return pm, p


def test_save_is_atomic():
    with tempfile.TemporaryDirectory() as tmp:
        pm, p = _project(tmp)
        pm.save(p, code="void setup(){}\nvoid loop(){}\n")
        before = p.meta_path.read_text(encoding="utf-8")
        real = os.replace

        def boom(*a, **k):
            raise OSError("power cut")
        project_manager.os.replace = boom
        try:
            try:
                pm.save(p, code="// new\n")
            except OSError:
                pass
        finally:
            project_manager.os.replace = real
        assert p.meta_path.read_text(encoding="utf-8") == before
        assert p.ino_path.read_text(encoding="utf-8").startswith("void setup")
        assert not [f for f in os.listdir(p.path) if f.endswith(".tmp")]


def test_corrupt_meta_is_kept_not_overwritten():
    with tempfile.TemporaryDirectory() as tmp:
        pm, p = _project(tmp)
        pm.save(p, code="void setup(){}\nvoid loop(){}\n")
        good = p.meta_path.read_text(encoding="utf-8")
        truncated = good[: len(good) // 2]
        p.meta_path.write_text(truncated, encoding="utf-8")
        loaded = pm._load_folder(p.path, p.type)
        assert loaded is not None
        pm.save(loaded, code="void setup(){}\nvoid loop(){}\n")   # ecrase la meta
        kept = [f for f in p.path.iterdir() if ".corrupt" in f.name]
        assert kept and kept[0].read_text(encoding="utf-8") == truncated, kept


# -- 5. UTF-8 coupe entre deux lectures -------------------------------------
def test_split_utf8_char_is_not_replaced():
    raw = "Température\n".encode("utf-8")
    cut = raw.index(b"\xc3") + 1
    chunks = [raw[:cut], raw[cut:]]

    class FakeSerial:
        def __init__(self, *a, **k):
            self.is_open = True

        @property
        def in_waiting(self):
            return len(chunks[0]) if chunks else 0

        def read(self, n):
            c = chunks.pop(0)
            if not chunks:
                worker._running = False
            return c

        def close(self):
            self.is_open = False

    fake = types.ModuleType("serial")
    fake.Serial = FakeSerial
    fake.SerialException = type("SerialException", (Exception,), {})
    saved = sys.modules.get("serial")
    sys.modules["serial"] = fake
    worker = serial_monitor._SerialReaderWorker("COM1", 9600)
    got = []
    worker.data_received.connect(got.append)
    try:
        worker.run()
    finally:
        if saved is None:
            sys.modules.pop("serial", None)
        else:
            sys.modules["serial"] = saved
    text = "".join(got)
    assert text == "Température\n", repr(text)


# -- 6. close_port ne detruit pas un fil vivant ----------------------------
def test_close_port_does_not_delete_a_running_thread():
    class FakeWorker(QObject):
        data_received = pyqtSignal(str)
        error = pyqtSignal(str)
        disconnected = pyqtSignal()
        finished = pyqtSignal()

        def __init__(self):
            super().__init__()
            self.deleted = False

        def stop(self):
            pass

        def wait(self, ms):
            return False      # toujours en cours

        def deleteLater(self):
            self.deleted = True

    mon = serial_monitor.SerialMonitorWidget()
    w = FakeWorker()
    mon._worker = w
    mon.close_port()
    assert w.deleted is False
    w.finished.emit()          # le fil se termine enfin
    assert w.deleted is True


TESTS = [
    test_core_install_has_a_long_timeout,
    test_core_install_timeout_says_it_was_the_core,
    test_missing_lib_after_a_repair_reverts_the_editor,
    test_manual_port_is_forgotten_on_auto_detection_and_unplug,
    test_switch_to_auto_without_board_forgets_manual_selection,
    test_save_is_atomic,
    test_corrupt_meta_is_kept_not_overwritten,
    test_split_utf8_char_is_not_replaced,
    test_close_port_does_not_delete_a_running_thread,
]


def main():
    f = 0
    for t in TESTS:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as e:
            f += 1
            print("FAIL", t.__name__, type(e).__name__, ascii(str(e))[:200])
    print(f"\n{len(TESTS)-f}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(1 if f else 0)


if __name__ == "__main__":
    main()
