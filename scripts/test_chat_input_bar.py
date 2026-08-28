"""Tests refonte barre de saisie chat. Runner standalone offscreen :
python scripts/test_chat_input_bar.py
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.chat.chat_controller import ChatController

# Prevents Python GC from destroying ChatView QObjects between tests
# (premature destruction → LanguageManager C++ invalidated via signal cleanup).
_keep_alive: list = []

# QApplication and ChatView imported once at module level so that
# PyQt6 singletons (lang_manager, theme_manager) stay alive.
from PyQt6.QtWidgets import QApplication as _QApplication
_qapp = _QApplication.instance() or _QApplication([])
from ui.chat.chat_view import ChatView as _ChatView
# Explicit anchor on singletons to prevent GC between tests.
from ui.i18n import lang_manager as _lang_manager_anchor
from ui.theme import theme_manager as _theme_manager_anchor
_keep_alive.extend([_lang_manager_anchor, _theme_manager_anchor])


def _ctrl():
    return ChatController(backend=None, user_mode="beginner")


def test_combined_material_no_attachment():
    c = _ctrl()
    c.user_material = "MATERIEL PROJET"
    assert c._combined_material() == "MATERIEL PROJET"
    print("  [OK] combined = user_material seul si pas de piece jointe")


def test_combined_material_with_attachment():
    c = _ctrl()
    c.user_material = "MATERIEL PROJET"
    c.attachment_name = "notes.txt"
    c.attachment_text = "CONTENU DOC"
    out = c._combined_material()
    assert "MATERIEL PROJET" in out
    assert "notes.txt" in out
    assert "CONTENU DOC" in out
    print("  [OK] combined inclut materiel projet + nom + texte du doc")


def test_combined_material_attachment_only():
    c = _ctrl()
    c.attachment_name = "notes.txt"
    c.attachment_text = "CONTENU DOC"
    out = c._combined_material()
    assert "CONTENU DOC" in out and "notes.txt" in out
    print("  [OK] combined = doc seul si pas de materiel projet")


def test_reset_clears_attachment():
    c = _ctrl()
    c.attachment_name = "notes.txt"
    c.attachment_text = "CONTENU"
    c.history.append({"role": "user", "content": "x", "ts": "t"})
    c.reset()
    assert c.attachment_name == "" and c.attachment_text == ""
    assert c.history == []
    print("  [OK] reset() vide la piece jointe + l'historique")


def test_i18n_keys_present_all_langs():
    from ui.i18n import TRANSLATIONS
    keys = ("chat_attach_tooltip", "chat_attachment_too_large",
            "chat_model_label_tooltip", "chat_no_model_label")
    for code, strings in TRANSLATIONS.items():
        for k in keys:
            v = getattr(strings, k, None)
            assert isinstance(v, str) and v.strip(), f"{code}.{k} manquant/vide"
    print("  [OK] clés i18n nouvelle barre présentes dans les 4 langues")


def _make_view():
    view = _ChatView(ChatController(backend=None, user_mode="beginner"))
    _keep_alive.append(view)  # prevents premature GC between tests
    return view, _qapp


def test_no_send_button():
    view, _ = _make_view()
    assert not hasattr(view, "_send_btn"), "le bouton envoyer doit etre supprime"
    print("  [OK] bouton envoyer supprime")


def test_stop_button_hidden_then_streaming():
    view, _ = _make_view()
    assert view._stop_btn.isHidden() is True
    view._set_streaming_ui(True)
    assert view._stop_btn.isHidden() is False
    assert view._input.isEnabled() is False
    assert view._attach_btn.isEnabled() is False
    view._set_streaming_ui(False)
    assert view._stop_btn.isHidden() is True
    assert view._attach_btn.isEnabled() is True
    print("  [OK] Stop visible <=> stream (via _set_streaming_ui)")


def test_chip_reflects_shared_context():
    """Le chip n'a plus d'état propre : il reflète le fichier de contexte
    PARTAGÉ poussé par le Studio via set_project_context (nom = chip + libellé,
    contenu = user_material du system prompt). Nom vide -> chip masqué."""
    view, _ = _make_view()
    view.set_project_context(context_name="notes.txt", user_material="CONTENU")
    assert view._attach_chip.isHidden() is False
    assert "notes.txt" in view._chip_lbl.text()
    assert view.controller.user_material == "CONTENU"
    # Combined = shared material (no chat-specific attachment).
    assert view.controller._combined_material() == "CONTENU"
    view.set_project_context(context_name="", user_material="")
    assert view._attach_chip.isHidden() is True
    print("  [OK] chip piloté par set_project_context (fichier partagé)")


def test_clear_attachment_emits_detach():
    """Le ✕ du chip route le retrait vers le Studio (detach_file_requested) et
    masque le chip immédiatement — il ne touche plus l'état du controller."""
    view, _ = _make_view()
    view.set_project_context(context_name="notes.txt", user_material="CONTENU")
    fired = []
    view.detach_file_requested.connect(lambda: fired.append(True))
    view._clear_attachment()
    assert fired == [True], "le retrait doit émettre detach_file_requested"
    assert view._attach_chip.isHidden() is True
    print("  [OK] retrait chip emet detach_file_requested + masque le chip")


def test_input_file_drop_emits_attach():
    """Déposer un fichier local sur l'input émet attach_file_requested (le
    Studio fera la copie/persistance du contexte partagé)."""
    from PyQt6.QtCore import QMimeData, QUrl, QPointF, Qt
    from PyQt6.QtGui import QDropEvent
    view, _ = _make_view()
    got = []
    view.attach_file_requested.connect(got.append)
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(ROOT / "README.md"))])
    ev = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, md,
                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    view._input.dropEvent(ev)
    assert len(got) == 1 and got[0].endswith("README.md"), got
    print("  [OK] drop fichier sur l'input -> attach_file_requested")


def test_chatview_drop_anywhere_emits_attach():
    """Déposer un fichier n'importe où dans la fenêtre de chat (pas seulement
    l'input) émet attach_file_requested via le handler du ChatView."""
    from PyQt6.QtCore import QMimeData, QUrl, QPointF, Qt
    from PyQt6.QtGui import QDropEvent
    view, _ = _make_view()
    got = []
    view.attach_file_requested.connect(got.append)
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(ROOT / "README.md"))])
    ev = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, md,
                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    view.dropEvent(ev)
    assert len(got) == 1 and got[0].endswith("README.md"), got
    print("  [OK] drop n'importe ou dans le chat -> attach_file_requested")


def test_assistant_bubble_does_not_capture_drops():
    """Les bulles assistant (QTextBrowser) ne capturent PAS les drops : l'event
    propage jusqu'au ChatView (drop d'un document sur une bulle = attache)."""
    from ui.chat.chat_message import ChatMessage
    msg = ChatMessage(role="assistant", text="bonjour **monde**",
                      dark_theme=False)
    _keep_alive.append(msg)
    assert msg._browser is not None
    assert msg._browser.acceptDrops() is False
    print("  [OK] bulle assistant ne capture pas les drops (propage)")


def test_shared_context_survives_reset():
    """Le fichier de contexte est lié au PROJET : repartir à zéro la
    conversation (reset) ne vide pas user_material ni le chip."""
    view, _ = _make_view()
    view.set_project_context(context_name="notes.txt", user_material="CONTENU")
    view.controller.history.append({"role": "user", "content": "x", "ts": "t"})
    view.controller.reset()
    assert view.controller.user_material == "CONTENU"
    assert view._attach_chip.isHidden() is False
    print("  [OK] contexte partagé survit à reset() (lié au projet)")


class _MockBackend:
    name = "Mock Model 4.8"
    def chat_stream(self, system, messages):
        yield "hi"
    def chat(self, system, messages):
        return "hi"
    def cancel(self):
        pass


def test_model_label_reflects_backend():
    view, _ = _make_view()
    from ui.i18n import lang_manager
    assert view._model_lbl.text() == lang_manager.current.chat_no_model_label
    view.set_backend(_MockBackend())
    assert view._model_lbl.text() == "Mock Model 4.8"
    print("  [OK] label modèle reflète backend.name / aucun modèle")


def test_model_label_click_emits_signal():
    view, _ = _make_view()
    fired = []
    view.open_model_settings_requested.connect(lambda: fired.append(True))
    view._model_lbl.click()
    assert fired == [True], "clic label modèle doit émettre le signal"
    print("  [OK] clic label modèle émet open_model_settings_requested")


def test_typing_indicator_show_remove():
    view, _ = _make_view()
    assert view._typing_indicator is None
    view._show_typing_indicator()
    assert view._typing_indicator is not None
    idx = view._conv_lay.indexOf(view._typing_indicator)
    assert idx >= 0, "indicateur absent du layout"
    view._remove_typing_indicator()
    assert view._typing_indicator is None
    print("  [OK] indicateur loader show/remove")


def test_view_builds_with_all_elements():
    view, _ = _make_view()
    for attr in ("_input", "_stop_btn", "_attach_btn", "_attach_chip",
                 "_chip_lbl", "_model_lbl"):
        assert hasattr(view, attr), f"{attr} manquant"
    assert not hasattr(view, "_send_btn")
    view._apply_theme()   # ne doit pas lever
    print("  [OK] vue construite avec tous les éléments + thème OK")


def test_stop_finalizes_immediately():
    """Clic Stop : l'UI est rendue IMMÉDIATEMENT (input + joindre réactivés,
    Stop caché), le partiel est commité tout de suite, et le worker est
    détaché (ses callbacks UI sont coupés → pas de double commit)."""
    from ui.chat.chat_message import ChatMessage
    from ui.chat.chat_view import _StreamWorker
    view, _ = _make_view()
    view.set_backend(_MockBackend())
    view._streaming_bubble = ChatMessage(role="assistant", text="",
                                         dark_theme=False)
    view._streaming_user_text = "question"
    view._last_buffer = "reponse partielle"
    # Real worker but NOT started (no thread launched).
    view._worker = _StreamWorker(_MockBackend(), "", [])
    view._set_streaming_ui(True)
    n_before = len(view.controller.history)

    view._on_stop_clicked()
    # UI re-enabled immediately (no waiting for worker to exit).
    assert view._stop_btn.isHidden() is True
    assert view._input.isEnabled() is True
    assert view._attach_btn.isEnabled() is True
    assert view._worker is None                  # worker detached
    # Partial committed exactly once (user + assistant).
    assert len(view.controller.history) == n_before + 2
    assert "reponse partielle" in view.controller.history[-1]["content"]
    print("  [OK] stop : input réactivé immédiatement + partiel commité + worker détaché")


def main() -> int:
    tests = [
        test_combined_material_no_attachment,
        test_combined_material_with_attachment,
        test_combined_material_attachment_only,
        test_reset_clears_attachment,
        test_i18n_keys_present_all_langs,
        test_no_send_button,
        test_stop_button_hidden_then_streaming,
        test_chip_reflects_shared_context,
        test_clear_attachment_emits_detach,
        test_input_file_drop_emits_attach,
        test_chatview_drop_anywhere_emits_attach,
        test_assistant_bubble_does_not_capture_drops,
        test_shared_context_survives_reset,
        test_model_label_reflects_backend,
        test_model_label_click_emits_signal,
        test_typing_indicator_show_remove,
        test_view_builds_with_all_elements,
        test_stop_finalizes_immediately,
    ]
    print("[test_chat_input_bar]\n")
    failed = 0
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}"); failed += 1
        except Exception as e:
            print(f"  [ERR ] {fn.__name__}: {type(e).__name__}: {e}"); failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
