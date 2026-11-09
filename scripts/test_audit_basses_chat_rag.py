"""Audit 2026-11-06, constats de gravite BASSE, zone « chat + RAG + registre ».

Un test par constat corrige. Aucun appel reseau, aucune ecriture dans
~/Documents/Promptuino (chemins detournes vers un dossier temporaire).

Run : python scripts/test_audit_basses_chat_rag.py
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_ALIVE: list = []


def _app():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    _ALIVE.append(app)
    return app


class _MockBackend:
    name = "Mock"
    is_slm = True

    def chat_stream(self, system, messages):
        yield "x"

    def chat(self, system, messages):
        return "x"

    def cancel(self):
        pass


# ── chat_controller.py:165 ──────────────────────────────────────────────

def test_preloaded_context_does_not_survive_a_new_conversation():
    from ui.chat.chat_controller import ChatController
    c = ChatController(backend=None, user_mode="beginner")
    c.system_extras_once = "ERREUR DU PROJET A"
    c.reset()
    assert c.system_extras_once == "", "reset() garde le contexte « ? »"
    c.system_extras_once = "ERREUR DU PROJET A"
    c.load_history([])
    assert c.system_extras_once == "", (
        "load_history() (changement de projet) garde le contexte « ? »")


# ── chat_message.py:209 ─────────────────────────────────────────────────

def test_a_header_in_prose_is_not_swallowed_as_a_tag():
    _app()
    from PyQt6.QtWidgets import QTextBrowser
    from ui.chat.chat_message import _md_to_html
    html = _md_to_html("Ajoute #include <Servo.h> en haut du sketch.")
    b = QTextBrowser()
    b.setHtml(html)
    assert "<Servo.h>" in b.toPlainText(), b.toPlainText()


def test_code_is_not_escaped_twice():
    _app()
    from PyQt6.QtWidgets import QTextBrowser
    from ui.chat.chat_message import _md_to_html
    text = ("Voici :\n\n```cpp\n#include <Servo.h>\nif (a < b) {}\n```\n\n"
            "et `x<y` en ligne.")
    b = QTextBrowser()
    b.setHtml(_md_to_html(text))
    plain = b.toPlainText()
    assert "#include <Servo.h>" in plain, plain
    assert "a < b" in plain, plain
    assert "x<y" in plain, plain
    assert "&lt;" not in plain, plain


# ── chat_message.py:362 ─────────────────────────────────────────────────

def test_user_bubble_is_plain_text():
    _app()
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel
    from ui.chat.chat_message import ChatMessage
    m = ChatMessage(role="user", text="pourquoi if (a<b && c>d) ne marche pas")
    _ALIVE.append(m)
    labels = [l for l in m.findChildren(QLabel)
              if "a<b" in l.text()]
    assert labels, "bulle utilisateur introuvable"
    assert labels[0].textFormat() == Qt.TextFormat.PlainText, (
        labels[0].textFormat())


# ── chat_view.py:788 ────────────────────────────────────────────────────

def _bubble_texts(view):
    from ui.chat.chat_message import ChatMessage
    out = []
    for i in range(view._conv_lay.count()):
        w = view._conv_lay.itemAt(i).widget()
        if isinstance(w, ChatMessage):
            out.append(w)
    return out


def test_a_theme_switch_keeps_bubbles_outside_the_history():
    _app()
    from ui.chat.chat_controller import ChatController
    from ui.chat.chat_view import ChatView
    ctrl = ChatController(backend=_MockBackend(), user_mode="beginner")
    v = ChatView(ctrl)
    _ALIVE.append(v)
    ctrl.commit_streamed_turn("q1", "a1")
    v._rebuild_conversation()
    v._append_temp_bubble("assistant", "REDIRECTION HORS HISTORIQUE",
                          action=("Corriger dans le Studio", lambda: None))
    # Force a stale theme on the temp bubble so the toggle has to swap it.
    temp = [b for b in _bubble_texts(v)
            if b.text == "REDIRECTION HORS HISTORIQUE"][0]
    temp._dark = not v._is_dark_theme()
    v._apply_theme()
    after = [b for b in _bubble_texts(v)
             if b.text == "REDIRECTION HORS HISTORIQUE"]
    assert after, "la bulle hors historique a disparu au changement de theme"
    fresh = after[0]
    assert fresh._dark == v._is_dark_theme(), "bulle pas re-themee"
    assert fresh._actions, "le bouton de la bulle a disparu"
    assert any(b.text == "a1" for b in _bubble_texts(v)), "historique perdu"


# ── chat_view.py:1056 ───────────────────────────────────────────────────

def test_quit_stops_a_running_stream_worker():
    app = _app()
    from ui.chat.chat_controller import ChatController
    from ui.chat.chat_view import ChatView, _StreamWorker

    gate = threading.Event()

    class _Blocking(_MockBackend):
        def chat_stream(self, system, messages):
            gate.wait(10)        # blocked « HTTP read » until cancel
            yield "x"

        def cancel(self):
            gate.set()

    ctrl = ChatController(backend=_Blocking(), user_mode="beginner")
    v = ChatView(ctrl)
    _ALIVE.append(v)
    assert hasattr(v, "_stop_workers_on_quit"), "aucun garde aboutToQuit"
    w = _StreamWorker(ctrl.backend, "s", [], parent=v)
    v._worker = w
    w.start()
    v._stop_workers_on_quit()
    assert not w.isRunning(), "le worker tourne encore a la sortie"
    v._worker = None
    gate.set()
    w.wait(2000)


# ── behavior_review.py:47 ───────────────────────────────────────────────

def test_conformance_reads_is_slm_as_a_property():
    from ui.generation import behavior_review as br

    class _B:
        def __init__(self, slm):
            self._slm = slm

        @property
        def is_slm(self):
            return self._slm

    old = br.CONFORMANCE_ON_SLM
    br.CONFORMANCE_ON_SLM = False
    try:
        assert br.conformance_available(_B(True)) is False
        assert br.conformance_available(_B(False)) is True
    finally:
        br.CONFORMANCE_ON_SLM = old


# ── add_router.py:139 ───────────────────────────────────────────────────

def test_markers_are_matched_on_word_boundaries():
    from ui.generation.add_router import prompt_asks_a_modification as asks
    for p in ("ajoute un buzzer sur D8, j'ai déjà des LEDs",
              "ajoute une plus grande LED rouge",
              "add a commonly used buzzer"):
        assert not asks(p), p
    for p in ("le clignotement ne doit avoir lieu que si l'interrupteur est "
              "fermé", "only blink the LED when the button is pressed",
              "modifier le clignotement", "deja de parpadear el LED",
              "reemplazar el sonido", "la LED ne plus clignoter"):
        assert asks(p), p


# ── component_index.py:178 ──────────────────────────────────────────────

def test_a_no_library_choice_is_not_shown_as_a_library_name():
    import ui.component_libs as cl
    import ui.registry_lookup as rl
    from ui.component_index import _looked_up_components
    old_reg, old_loaded = dict(cl._REGISTRY), cl._REGISTRY_LOADED
    rl.set_cache_for_tests({"veml7700": {"lib_name": "DevLab_VEML7700",
                                         "entry": {"name": "x"}}})
    cl.set_registry({"veml7700": cl.NO_LIBRARY})
    try:
        card = [c for c in _looked_up_components() if c.key == "veml7700"][0]
        assert card.lib == "", card.lib
        assert card.library == "none", card.library
    finally:
        rl.set_cache_for_tests(None)
        cl._REGISTRY, cl._REGISTRY_LOADED = old_reg, old_loaded


# ── declared_components.py:281 ──────────────────────────────────────────

def test_declared_save_reports_a_failed_write():
    import ui.declared_components as dc
    old = dc._LIBRARY_PATH
    with tempfile.TemporaryDirectory() as td:
        try:
            dc._LIBRARY_PATH = Path(td) / "components.json"
            assert dc.save([]) is True
            blocker = Path(td) / "un_fichier"
            blocker.write_text("x", encoding="utf-8")
            dc._LIBRARY_PATH = blocker / "components.json"   # parent = file
            assert dc.save([]) is False, "un echec d'ecriture reste muet"
        finally:
            dc._LIBRARY_PATH = old


# ── onnx_setup.py:270 ───────────────────────────────────────────────────

def test_the_download_thread_is_awaited_after_cancel():
    _app()
    from PyQt6.QtCore import QThread
    import ui.onnx_setup as os_mod

    class _SlowWorker(QThread):
        def __init__(self):
            super().__init__()
            self._stop = threading.Event()

        def cancel(self):
            self._stop.set()

        def run(self):
            # Cancel is only seen after a « read » of 3 s.
            self.msleep(3000)

    dlg = os_mod.OnnxDownloadDialog()
    _ALIVE.append(dlg)
    w = _SlowWorker()
    dlg._worker = w
    w.start()
    dlg._on_cancel()               # waits only 2 s
    assert hasattr(dlg, "finish_worker"), "aucune attente du fil"
    dlg.finish_worker()
    assert not w.isRunning(), "le fil tourne encore apres la fermeture"

    # ...and ensure_model_or_exit calls it.
    called = []

    class _FakeDlg:
        def exec(self):
            return os_mod.QDialog.DialogCode.Rejected

        def finish_worker(self):
            called.append(True)

    old_dlg, old_conf = os_mod.OnnxDownloadDialog, os_mod.modele_conforme
    os_mod.OnnxDownloadDialog = _FakeDlg
    os_mod.modele_conforme = lambda *a, **k: (False, "absent")
    try:
        assert os_mod.ensure_model_or_exit() is False
    finally:
        os_mod.OnnxDownloadDialog, os_mod.modele_conforme = old_dlg, old_conf
    assert called, "ensure_model_or_exit n'attend pas le fil"


# ── rag.py:695 ──────────────────────────────────────────────────────────

def test_an_unsupported_sharp_variant_drops_both_libraries():
    from ui import rag
    assert rag._load_corpus()
    forced = [rag._corpus_by_id["sharpir"], rag._corpus_by_id["sharpdistsensor"]]
    with contextlib.redirect_stdout(io.StringIO()):
        ctx, _ = rag._build_lib_context(
            "capteur infrarouge sharp GP2Y0A80 sur A0", forced_libs=forced)
    assert "Unsupported sensor variant" in ctx, ctx[:400]
    assert "SharpDistSensor.h" not in ctx, (
        "SharpDistSensor injectee au-dessus de « do NOT use either library »")
    assert "SharpIR.h" not in ctx


# ── registry_lookup.py:330 ──────────────────────────────────────────────

def test_the_registry_cache_is_written_atomically():
    import ui.registry_lookup as rl
    old_path, old_replace = rl._CACHE_PATH, rl.os.replace
    with tempfile.TemporaryDirectory() as td:
        try:
            rl._CACHE_PATH = Path(td) / "registry-cache.json"
            entry = {"name": "Adafruit AS7341"}
            rl._cache_put("as7341", "Adafruit AS7341", entry, [])
            before = rl._CACHE_PATH.read_text(encoding="utf-8")

            def _crash(*a, **k):
                raise OSError("coupure pendant l'ecriture")
            rl.os.replace = _crash
            rl._cache_put("veml7700", "DevLab", {"name": "DevLab"}, [])
            rl.os.replace = old_replace
            assert rl._CACHE_PATH.read_text(encoding="utf-8") == before, (
                "le cache a ete ecrase sans passer par un fichier temporaire")
            assert not list(Path(td).glob("*.tmp")), "fichier .tmp oublie"
            assert rl._cache_get("as7341") is not None
        finally:
            rl._CACHE_PATH, rl.os.replace = old_path, old_replace


# ── registry_lookup.py:651 ──────────────────────────────────────────────

def _fake_cli(rl, run, installed=None):
    old = (rl.arduino_cli._run, rl.arduino_cli.is_available,
           rl.arduino_cli._installed_libs)
    rl.arduino_cli._run = run
    rl.arduino_cli.is_available = lambda: True
    if installed is not None:
        rl.arduino_cli._installed_libs = installed
    return old


def _restore_cli(rl, old):
    (rl.arduino_cli._run, rl.arduino_cli.is_available,
     rl.arduino_cli._installed_libs) = old


def _with_temp_cache(fn):
    import ui.registry_lookup as rl
    with tempfile.TemporaryDirectory() as td:
        old = rl._CACHE_PATH
        rl._CACHE_PATH = Path(td) / "registry-cache.json"
        try:
            return fn(rl)
        finally:
            rl._CACHE_PATH = old


def _search_ok(cmd):
    import json
    if "search" in cmd:
        return 0, json.dumps({"libraries": [
            {"name": "Adafruit AS7341",
             "latest": {"author": "Adafruit", "sentence": "AS7341 sensor."}}]})
    return 0, ""        # install OK


def test_an_unreadable_search_is_not_an_unknown_component():
    def body(rl):
        old = _fake_cli(rl, lambda cmd: (0, "WARNING: blah\n{\"libraries\""))
        try:
            r = rl.lookup_component("as7341", "cfg")
        finally:
            _restore_cli(rl, old)
        assert r.status == "unavailable", r.status
    _with_temp_cache(body)


def test_an_installed_but_unlisted_lib_is_not_an_unknown_component():
    def body(rl):
        old = _fake_cli(rl, _search_ok, installed=lambda cfg: {})
        try:
            r = rl.lookup_component("as7341", "cfg")
        finally:
            _restore_cli(rl, old)
        assert r.status != "not_found", r.status
        assert r.lib_name == "Adafruit AS7341", r.lib_name
        assert r.entry is None
    _with_temp_cache(body)


# ── registry_lookup.py:757 ──────────────────────────────────────────────

def test_a_lib_list_timeout_does_not_escape_lookup_component():
    import subprocess

    def body(rl):
        def _boom(cfg):
            raise subprocess.TimeoutExpired("arduino-cli lib list", 180)
        old = _fake_cli(rl, _search_ok, installed=_boom)
        try:
            r = rl.lookup_component("as7341", "cfg")    # must not raise
        finally:
            _restore_cli(rl, old)
        assert r.status == "unavailable", r.status
    _with_temp_cache(body)


def test_the_worker_always_emits_done():
    _app()
    import ui.registry_lookup as rl
    old = rl.lookup_component

    def _raise(*a, **k):
        raise RuntimeError("inattendu")
    rl.lookup_component = _raise
    got = []
    try:
        w = rl.RegistryLookupWorker(["as7341"], "cfg")
        w.done.connect(lambda res: got.append(res))
        w.run()                                      # synchronous on purpose
    finally:
        rl.lookup_component = old
    assert got, "done jamais emis"
    assert got[0][0].token == "as7341"
    assert got[0][0].status == "unavailable"


TESTS = [
    test_preloaded_context_does_not_survive_a_new_conversation,
    test_a_header_in_prose_is_not_swallowed_as_a_tag,
    test_code_is_not_escaped_twice,
    test_user_bubble_is_plain_text,
    test_a_theme_switch_keeps_bubbles_outside_the_history,
    test_quit_stops_a_running_stream_worker,
    test_conformance_reads_is_slm_as_a_property,
    test_markers_are_matched_on_word_boundaries,
    test_a_no_library_choice_is_not_shown_as_a_library_name,
    test_declared_save_reports_a_failed_write,
    test_the_download_thread_is_awaited_after_cancel,
    test_an_unsupported_sharp_variant_drops_both_libraries,
    test_the_registry_cache_is_written_atomically,
    test_an_unreadable_search_is_not_an_unknown_component,
    test_an_installed_but_unlisted_lib_is_not_an_unknown_component,
    test_a_lib_list_timeout_does_not_escape_lookup_component,
    test_the_worker_always_emits_done,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
