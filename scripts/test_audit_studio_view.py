"""Audit 2026-11-06, lot studio_view : reentrance des workers et pertes de donnees.

Aucun vrai QThread : chaque test appelle la methode REELLE de `StudioView` sur
un `self` double (MagicMock) dont on branche les helpers voulus, et les workers
sont remplaces par des doublures (`_FakeWorker`).
"""
from __future__ import annotations
import os
import sys
from functools import partial
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])   # ref module-level

import ui.studio_view as sv
from ui.studio_view import StudioView

# Methodes reelles que les doubles doivent pouvoir s'appeler entre elles.
_REAL = (
    "_detach_registry_worker", "_detach_verify_worker", "_detach_gen_worker",
    "_stop_gen_worker_safely", "_on_recombine_error", "_full_code_for",
    "_generation_prompt", "_refuse_while_busy", "_generation_in_flight",
)


class _Stop(Exception):
    pass


class _Sig:
    def __init__(self):
        self.disconnected = False
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self, *a):
        self.disconnected = True
        self.slots = []


class _FakeWorker:
    def __init__(self, running=True):
        self._running = running
        self.cancelled = False
        for n in ("done", "finished", "error", "status", "output",
                  "code_updated", "repair_steps"):
            setattr(self, n, _Sig())
        self.backend = mock.MagicMock()

    def isRunning(self):
        return self._running

    def cancel(self):
        self.cancelled = True

    def start(self):
        pass

    def wait(self, *_):
        return False


def _view(**attrs):
    m = mock.MagicMock()
    m._gen_busy = None
    m._beginner_running = False
    m._cu_running = False
    m._manual_repair_running = False
    m._gen_worker = None
    m._verify_worker = None
    m._registry_worker = None
    m._addcmt_worker = None
    m._detached_gen_workers = []
    for n in _REAL:
        f = getattr(StudioView, n, None)
        if f is not None:
            setattr(m, n, partial(f, m))
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# ── 1 : reentrance de _launch_generation ─────────────────────────────────

def test_launch_generation_refused_while_busy():
    for busy in ({"_gen_busy": "advanced"}, {"_beginner_running": True}):
        m = _view(**busy)
        StudioView._launch_generation(m, "regenerate", None, "p")
        m._auto_create_untitled.assert_not_called()
        m._start_generation.assert_not_called()


def test_launch_generation_runs_when_idle():
    m = _view()
    m._auto_create_untitled.return_value = False
    StudioView._launch_generation(m, "regenerate", None, "p")
    m._auto_create_untitled.assert_called_once()


# ── 2 / 6 : annulation et worker du registre ─────────────────────────────

def test_cancel_detaches_the_registry_worker():
    w = _FakeWorker()
    m = _view(_registry_worker=w)
    StudioView._cancel_gen_worker(m)
    assert w.done.disconnected, "le done du lookup doit etre coupe"
    assert m._registry_worker is None
    assert w in m._detached_gen_workers


def test_cancel_cuts_the_error_signal_before_the_backend_stops():
    """2026-11-07 : l'annulation coupe desormais vraiment la socket, donc le
    worker SORT pendant le `wait` en emettant l'erreur de coupure. Ses signaux
    doivent etre coupes AVANT `backend.cancel()`, sinon « HTTP 500 context
    canceled » s'affiche apres « Annule »."""
    w = _FakeWorker()
    ordre = []
    w.backend.cancel.side_effect = lambda: ordre.append(
        ("cancel", w.error.disconnected, w.finished.disconnected))

    def wait(*_):
        w._running = False          # le worker sort grace a la coupure
        return True
    w.wait = wait
    m = _view(_gen_worker=w)
    StudioView._stop_gen_worker_safely(m)
    assert ordre == [("cancel", True, True)], ordre
    assert m._gen_worker is None
    assert w not in m._detached_gen_workers, "un worker fini n'a rien a garer"


def test_the_busy_notice_leaves_when_the_generation_ends():
    """Vu le 2026-11-07 en pilotant la vraie fenetre : « operation deja en
    cours » restait affiche sous un bouton revenu au repos."""
    from ui.i18n import lang_manager
    busy_txt = lang_manager.current.studio_busy_try_later
    for texte, doit_partir in ((busy_txt, True), ("Erreur Ollama : HTTP 500", False)):
        m = _view(_current_mode="advanced", _gen_busy=None)
        m._hide_gen_error = mock.MagicMock()
        m._lbl_gen_error.text.return_value = texte
        StudioView._sync_generation_buttons(m)
        assert m._hide_gen_error.called is doit_partir, texte


def test_cancel_keeps_a_worker_that_outlives_the_wait():
    w = _FakeWorker()               # wait() rend False, le worker tourne
    m = _view(_gen_worker=w)
    StudioView._stop_gen_worker_safely(m)
    assert w.error.disconnected and w in m._detached_gen_workers


def test_cancel_beginner_detaches_the_registry_worker():
    w = _FakeWorker()
    m = _view(_registry_worker=w, _cu_worker=None)
    StudioView._cancel_beginner(m)
    assert w.done.disconnected
    assert m._registry_worker is None


def test_beginner_continue_ignored_after_cancel_during_lookup():
    m = _view(_beginner_running=False)
    StudioView._continue_beginner_generation(
        m, mock.MagicMock(), "fqbn", "COM1", "prompt", [],
        registry_results=[mock.MagicMock()])
    m._apply_registry_results.assert_not_called()
    m._assemble_generation_prompt.assert_not_called()


# ── 3 : reparation IA appliquee = nouveau code « livre » ─────────────────

def test_repaired_code_becomes_the_delivered_code():
    state = {"code": "A"}
    m = _view(_manual_repair_running=False, _manual_repair=None,
              _active_repair_target="ia", _verify_delivered_code="A")
    m.get_code = lambda: state["code"]
    m._set_code_with_attribution = lambda c, f: state.update(code=c)
    StudioView._on_service_code_updated(m, "B")
    assert state["code"] == "B"
    assert m._verify_delivered_code == "B"


def test_user_edit_is_not_taken_for_delivered_code():
    state = {"code": "edited"}
    m = _view(_manual_repair_running=False, _manual_repair=None,
              _active_repair_target="ia", _verify_delivered_code="A")
    m.get_code = lambda: state["code"]
    m._set_code_with_attribution = lambda c, f: state.update(code=c)
    StudioView._on_service_code_updated(m, "B")
    assert m._verify_delivered_code == "A"


# ── 4 : _run_add_comments non reentrant ──────────────────────────────────

def test_add_comments_refused_while_running():
    m = _view(_addcmt_worker=_FakeWorker(running=True))
    with mock.patch("ui.add_comments_dialog._AddCommentsWorker",
                    side_effect=AssertionError("second worker")):
        StudioView._run_add_comments(m)
    m._tools_panel.assert_not_called()


# ── 5 : annulation de la verification ────────────────────────────────────

def test_cancel_detaches_the_verify_worker():
    w = _FakeWorker()
    m = _view(_verify_worker=w)
    StudioView._cancel_gen_worker(m)
    assert w.cancelled
    for n in ("code_updated", "status", "output", "repair_steps", "done"):
        assert getattr(w, n).disconnected, n
    assert m._verify_worker is None
    assert w in m._detached_gen_workers


def test_repair_not_started_while_verify_worker_runs():
    w = _FakeWorker(running=True)
    m = _view(_verify_worker=w, _code_target="ia")
    backend = mock.MagicMock()
    backend.is_available.return_value = True
    with mock.patch.object(sv, "get_backend_instance", return_value=backend), \
         mock.patch.object(sv.arduino_cli, "is_available", return_value=True), \
         mock.patch.object(sv, "get_fqbn", return_value="a:b:c"), \
         mock.patch.object(sv, "board_manager",
                           mock.MagicMock(env="arduino", model="uno")):
        StudioView._run_repair_code(m)
    m._compile_service.run.assert_not_called()
    assert m._verify_worker is w


# ── 7 / 12 : load_project ────────────────────────────────────────────────

def test_load_project_cancels_a_running_generation():
    m = _view(_gen_busy="advanced", _dirty=False, _current_project=None)
    m._clear_previous_project_screen.side_effect = _Stop
    try:
        StudioView.load_project(m, mock.MagicMock())
    except _Stop:
        pass
    m._cancel_generation.assert_called_once()


def test_load_project_aborts_when_the_save_failed():
    m = _view(_dirty=True, _current_project=mock.MagicMock())
    m._confirm_unsaved.return_value = "save"
    m._clear_previous_project_screen.side_effect = _Stop
    StudioView.load_project(m, mock.MagicMock())      # save_project laisse _dirty
    m._clear_previous_project_screen.assert_not_called()


# ── 8 : prompt capture au lancement ──────────────────────────────────────

def test_feature_prompt_is_the_one_typed_at_launch():
    m = _view(_pending_action=("regenerate", None),
              _gen_launch_prompt="clignote une LED")
    m.get_prompt = lambda: "ajoute un buzzer"
    seen = []

    def _ff(parsed, fid, prompt, *a, **k):
        seen.append(prompt)
        raise _Stop
    m._feature_from_parsed = _ff
    m._features_with_id.return_value = []
    code = ("int x;\nvoid setup() {\n  pinMode(13, OUTPUT);\n}\n"
            "void loop() {\n  digitalWrite(13, HIGH);\n}\n")
    try:
        StudioView._on_generation_done(m, code)
    except _Stop:
        pass
    assert seen == ["clignote une LED"], seen


# ── 9 : erreur du worker de recombinaison ────────────────────────────────

def test_recombine_error_goes_through_the_revert():
    worker = _FakeWorker()
    m = _view(_features=[], _current_mode="advanced")
    with mock.patch.object(sv, "get_backend_instance",
                           return_value=mock.MagicMock()), \
         mock.patch.object(sv, "_GenerateWorker", return_value=worker):
        StudioView._start_recombine(m)
    assert worker.error.slots, "error doit etre branche"
    worker.error.slots[0]("boom")
    m._finalize_verify_failure.assert_called_once()


# ── 10 / 13 : source des commentaires = code COURANT ─────────────────────

_FULL = "int a;  // un\nint b;\n"


def _unchecked_view(editor_text):
    chk = mock.MagicMock()
    chk.isChecked.return_value = False
    ed = mock.MagicMock()
    ed.toPlainText.return_value = editor_text
    stripped = sv._strip_comments(_FULL)
    return _view(
        _code_target="ia",
        _code_with_comments={"ia": _FULL, "stable": None},
        _stripped_at_decoche={"ia": stripped, "stable": None},
        _tools_chk=lambda t=None: chk, _tools_editor=lambda t=None: ed)


def test_full_code_keeps_comments_and_later_edits():
    stripped = sv._strip_comments(_FULL)
    m = _unchecked_view(stripped + "int c;\n")
    out = StudioView._full_code_for(m, "ia")
    assert "// un" in out and "int c;" in out, out


def test_full_code_is_the_editor_when_checked():
    m = _unchecked_view("zzz")
    m._tools_chk = lambda t=None: mock.MagicMock(isChecked=lambda: True)
    assert StudioView._full_code_for(m, "ia") == "zzz"


def test_add_comments_sends_the_current_code():
    stripped = sv._strip_comments(_FULL)
    m = _unchecked_view(stripped + "int c;\n")
    m._code_with_comments["ia"] = _FULL
    sent = []

    class _W:
        def __init__(self, backend, code, *a):
            sent.append(code)
            self.finished = _Sig()
            self.error = _Sig()

        def start(self):
            pass

        def isRunning(self):
            return False
    backend = mock.MagicMock()
    backend.is_available.return_value = True
    with mock.patch.object(sv, "get_backend_instance", return_value=backend), \
         mock.patch("ui.add_comments_dialog._AddCommentsWorker", _W):
        StudioView._run_add_comments(m)
    assert sent and "int c;" in sent[0], sent


def test_save_writes_the_commented_code():
    stripped = sv._strip_comments(_FULL)
    m = _unchecked_view(stripped)
    m.get_code = lambda: stripped
    m._wiring_resolutions = {}
    m._implicit_actions = {}
    m._current_project = mock.MagicMock()
    m._stable_panel.editor.toPlainText.return_value = ""
    saved = {}
    with mock.patch.object(sv.project_manager, "save",
                           side_effect=lambda p, **kw: saved.update(kw)):
        StudioView.save_project(m)
    assert "// un" in saved["code"], saved.get("code")


# ── 11 : resultat « commentaires » perime ────────────────────────────────

def test_add_comments_result_dropped_if_editor_changed():
    ed = mock.MagicMock()
    ed.toPlainText.return_value = "code modifie depuis"
    m = _view(_addcmt_target="ia", _addcmt_editor_at_launch="code d'origine",
              _tools_editor=lambda t=None: ed)
    with mock.patch.object(sv.QMessageBox, "warning"):
        StudioView._on_add_comments_done(m, "// commente\nint a;")
    m._apply_add_comments_result.assert_not_called()


def test_add_comments_result_applied_if_editor_unchanged():
    ed = mock.MagicMock()
    ed.toPlainText.return_value = "code"
    chk = mock.MagicMock()
    chk.isChecked.return_value = True
    m = _view(_addcmt_target="ia", _addcmt_editor_at_launch="code",
              _tools_editor=lambda t=None: ed, _tools_chk=lambda t=None: chk)
    StudioView._on_add_comments_done(m, "// commente\nint a;")
    m._apply_add_comments_result.assert_called_once()


TESTS = [v for k, v in sorted(globals().items())
         if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
        except BaseException as e:      # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)
