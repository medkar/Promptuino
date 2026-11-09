"""Audit 2026-11-06, constats de gravite BASSE de la zone « studio ».

Chaque test vise un constat du rapport (docs/audit-2026-11-06.md) :

- log_widget.py:330 : le bouton « voir les corrections » suit la langue.
- studio/generation_flow.py:110 : l'avis « Coulisses modifiees » n'est plus
  efface par le vidage du journal qui suit.
- studio_view.py:7403 : fermer « Analyser / Reparer » pendant la cascade
  n'ouvre plus d'elle-meme une fenetre d'audit (ni d'appel IA).
- studio_view.py:7814 : en Debutant, un echec de creation du projet ne dit
  plus « aucun modele IA ».
- studio_view.py:9925 : le projet cree d'office porte le nom traduit.
- studio_view.py:3235 : les modales fermees sont detruites.

Aucun test n'ecrit sur disque, n'appelle de serveur ni ne lance l'app.

Run: python scripts/test_audit_basses_studio.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtWidgets import QApplication, QDialog  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

from ui.i18n import lang_manager, TRANSLATIONS  # noqa: E402
from ui.studio.log_widget import LogWidget  # noqa: E402
import ui.studio_view as sv  # noqa: E402
from ui.studio_view import StudioView  # noqa: E402
from ui.project_manager import is_name_valid  # noqa: E402


class _Patch:
    """Remplace des attributs de module le temps d'un test."""

    def __init__(self, mod, **values):
        self._mod, self._values, self._saved = mod, values, {}

    def __enter__(self):
        for k, v in self._values.items():
            self._saved[k] = getattr(self._mod, k)
            setattr(self._mod, k, v)
        return self

    def __exit__(self, *a):
        for k, v in self._saved.items():
            setattr(self._mod, k, v)


def _in_lang(code):
    lang_manager.set_language(code)


# ── log_widget.py:330 ─────────────────────────────────────────────────────
def test_the_repairs_button_follows_the_language():
    _in_lang("fr")
    try:
        w = LogWidget()
        w.show_repairs_action(
            lambda: lang_manager.current.studio_repairs_link.format(n=2))
        assert w._repairs_btn.text() == \
            TRANSLATIONS["fr"].studio_repairs_link.format(n=2)
        _in_lang("en")
        assert w._repairs_btn.text() == \
            TRANSLATIONS["en"].studio_repairs_link.format(n=2), \
            w._repairs_btn.text()
    finally:
        _in_lang("fr")


def test_a_plain_string_label_still_works():
    w = LogWidget()
    w.show_repairs_action("voir")
    assert w._repairs_btn.text() == "voir"


# ── generation_flow.py:110 ────────────────────────────────────────────────
def _loader_view():
    view = StudioView.__new__(StudioView)
    stub = SimpleNamespace(close_port=lambda: None)
    view._serial_monitor = stub
    view._serial_monitor_beg = stub
    view._current_mode = "advanced"
    view._output_area = LogWidget()
    view._beg_output_area = view._output_area
    view._ensure_loader_timer = lambda: None
    view._install_gen_slow_watchdog = lambda: None
    view._stop_gen_loader = lambda: None
    view._active_output_area = lambda: view._output_area
    return view


class _EditedPreview:
    def __init__(self, *a, **k):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted

    def edited(self):
        return True

    def user_message(self):
        return "message modifie"


def test_the_backstage_notice_survives_the_loader():
    view = _loader_view()
    view._comments_verbosity = lambda: 1
    with _Patch(sv, session=SimpleNamespace(prompt_backstage=True),
                _PromptPreviewDialog=_EditedPreview,
                _build_codegen_parts=lambda *a, **k: ("sys", "user")):
        out = StudioView._prompt_backstage(view, None, "prompt", "Uno")
    assert out == "message modifie"
    text = view._output_area._text.toPlainText()
    notice = lang_manager.current.backstage_edited
    assert notice in text, f"avis efface du journal : {text!r}"


# ── studio_view.py:7403 ───────────────────────────────────────────────────
def test_a_dismissed_manual_repair_opens_no_audit():
    view = StudioView.__new__(StudioView)
    view._manual_repair = {"target": "ia", "backend": None,
                           "original": "void setup(){}", "dismissed": True}
    view._manual_repair_dialog = None
    view._last_repair_steps = []
    out = LogWidget()
    view._active_output_area = lambda: out
    opened = []
    view._open_audit_dialog = lambda *a: opened.append(a)
    view._build_review_call = lambda *a: opened.append(("review",) + a)
    StudioView._on_manual_repair_done(view, True, "")
    assert opened == [], f"audit ouvert apres fermeture : {opened}"


class _FakeRepairDialog:
    """Se ferme tout de suite, comme un clic sur « Fermer »."""

    def __init__(self, *a, **k):
        self.apply_requested = SimpleNamespace(connect=lambda f: None)
        self.summary_ready = SimpleNamespace(connect=lambda f: None)
        self.deleted = False

    def exec(self):
        return 0

    def deleteLater(self):
        self.deleted = True


def test_closing_the_repair_dialog_marks_the_repair_dismissed():
    import ui.repair_code_dialog as rcd
    view = StudioView.__new__(StudioView)
    view._code_target = "ia"
    view._full_code_for = lambda t: "void setup(){}"
    view._cu_running = False
    view._gen_busy = None
    view._beginner_running = False
    view._manual_repair_running = False
    view._verify_worker = None
    view._board_name = lambda: "Uno"
    out = LogWidget()
    view._active_output_area = lambda: out
    view._active_console = lambda: None
    view._compile_service = SimpleNamespace(run=lambda **k: object())
    backend = SimpleNamespace(is_available=lambda: True)
    with _Patch(sv, get_backend_instance=lambda _id: backend,
                board_manager=SimpleNamespace(env="arduino", model="Uno"),
                get_fqbn=lambda e, m: "arduino:avr:uno",
                arduino_cli=SimpleNamespace(is_available=lambda: True)), \
            _Patch(rcd, RepairCodeDialog=_FakeRepairDialog):
        StudioView._run_repair_code(view)
    assert view._manual_repair.get("dismissed") is True, view._manual_repair


# ── studio_view.py:7814 ───────────────────────────────────────────────────
def test_a_project_creation_failure_is_not_blamed_on_the_model():
    view = StudioView.__new__(StudioView)
    view._gen_busy = None
    view._beginner_running = False
    view.get_prompt = lambda: "fais clignoter une led"
    view._has_generated = False
    view._resolve_lib_ambiguity = lambda p: None

    def _fail():
        view._untitled_error = "Acces refuse : Documents"
        return False
    view._auto_create_untitled = _fail
    shown = []
    view._show_beginner_status = lambda msg, **k: shown.append(msg)
    backend = SimpleNamespace(is_available=lambda: True)
    with _Patch(sv, get_backend_instance=lambda _id: backend,
                board_manager=SimpleNamespace(env="arduino", model="Uno",
                                              port="COM3"),
                get_fqbn=lambda e, m: "arduino:avr:uno",
                arduino_cli=SimpleNamespace(is_available=lambda: True,
                                            _find_port_auto=lambda: "COM3")):
        StudioView._on_generate_and_send(view)
    assert shown, "aucun message"
    assert shown[-1] != lang_manager.current.studio_err_no_backend, shown
    assert "Acces refuse" in shown[-1], shown


# ── studio_view.py:9925 ───────────────────────────────────────────────────
def test_the_untitled_name_follows_the_language():
    try:
        seen = {}
        for code in ("fr", "en", "es", "it"):
            _in_lang(code)
            name = sv._untitled_name()
            assert is_name_valid(name), (code, name)
            seen[code] = name
        assert seen["fr"] == "Sans-titre", seen
        assert seen["en"] == "Untitled", seen
        assert seen["es"] == "Sin titulo", seen   # accent replie
        assert seen["it"] == "Senza titolo", seen
    finally:
        _in_lang("fr")


class _Created(Exception):
    pass


def test_the_auto_created_project_uses_the_translated_name():
    view = StudioView.__new__(StudioView)
    view._current_project = None
    view._infer_project_type = lambda: "arduino"
    view.get_code = lambda: ""
    errors = []
    view._show_gen_error = errors.append
    names = []

    def _create(name, ptype, **k):
        names.append(name)
        raise _Created("stop")   # rien n'est ecrit
    fake_pm = SimpleNamespace(unique_name=lambda base, d: base,
                              create=_create)
    fake_dir = SimpleNamespace(mkdir=lambda **k: None)
    _in_lang("en")
    try:
        with _Patch(sv, project_manager=fake_pm, type_dir=lambda t: fake_dir):
            ok = StudioView._auto_create_untitled(view)
    finally:
        _in_lang("fr")
    assert ok is False
    assert names == ["Untitled"], names
    assert view._untitled_error == "stop", view._untitled_error


# ── studio_view.py:3235 ───────────────────────────────────────────────────
class _FakeModal:
    instances = []

    def __init__(self, *a, **k):
        self.result_choice = ("add", None)
        self.deleted = False
        _FakeModal.instances.append(self)

    def exec(self):
        return QDialog.DialogCode.Accepted

    def deleteLater(self):
        self.deleted = True


def test_the_generation_modal_is_destroyed_after_use():
    view = StudioView.__new__(StudioView)
    view._features = []
    _FakeModal.instances.clear()
    with _Patch(sv, GenerationModal=_FakeModal):
        choice = StudioView._open_action_modal(view, "prompt")
    assert choice == ("add", None)
    assert _FakeModal.instances[0].deleted, "modale jamais detruite"


def test_a_dialog_with_a_running_worker_is_kept():
    dlg = _FakeRepairDialog()
    dlg._worker = SimpleNamespace(isRunning=lambda: True)
    StudioView._dispose_dialog(dlg)
    assert not dlg.deleted, "detruire ici detruirait un QThread en cours"
    dlg._worker = SimpleNamespace(isRunning=lambda: False)
    StudioView._dispose_dialog(dlg)
    assert dlg.deleted


TESTS = [
    test_the_repairs_button_follows_the_language,
    test_a_plain_string_label_still_works,
    test_the_backstage_notice_survives_the_loader,
    test_a_dismissed_manual_repair_opens_no_audit,
    test_closing_the_repair_dialog_marks_the_repair_dismissed,
    test_a_project_creation_failure_is_not_blamed_on_the_model,
    test_the_untitled_name_follows_the_language,
    test_the_auto_created_project_uses_the_translated_name,
    test_the_generation_modal_is_destroyed_after_use,
    test_a_dialog_with_a_running_worker_is_kept,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}", flush=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {e!r}", flush=True)
    print(f"\n{passed}/{len(TESTS)} tests passed", flush=True)
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
