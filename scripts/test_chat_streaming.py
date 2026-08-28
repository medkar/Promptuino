"""Tests pour le streaming chat (default impl + backends natifs).

Run : python scripts/test_chat_streaming.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.ai_backends.base import AIBackend


class _StubBackend(AIBackend):
    """Backend minimal qui retourne une reponse hardcodee pour chat()."""
    @property
    def backend_id(self): return "stub"
    @property
    def name(self): return "Stub"
    @property
    def description(self): return ""
    def is_available(self): return True
    def generate_code(self, *a, **k): raise NotImplementedError
    def fix_code(self, *a, **k): raise NotImplementedError
    def explain_error(self, *a, **k): raise NotImplementedError
    def explain_code(self, *a, **k): raise NotImplementedError
    def lint_code(self, *a, **k): raise NotImplementedError
    def add_comments(self, *a, **k): raise NotImplementedError
    def repair_code(self, *a, **k): raise NotImplementedError
    def chat(self, system_prompt, messages):
        return "Hello world"


def test_default_chat_stream_yields_full_response_in_one_chunk():
    b = _StubBackend()
    chunks = list(b.chat_stream("sys", [{"role": "user", "content": "hi"}]))
    assert chunks == ["Hello world"], (
        f"Expected single chunk ['Hello world'], got {chunks}"
    )


def test_ollama_chat_stream_method_exists():
    """Smoke test : la methode chat_stream existe sur OllamaBackend
    et est override (pas l'impl default). Ne fait pas d'appel reseau."""
    from ui.ai_backends.ollama_backend import OllamaBackend
    assert "chat_stream" in OllamaBackend.__dict__, (
        "OllamaBackend doit override chat_stream() pour le streaming "
        "natif via /api/chat avec stream:true et NDJSON parsing."
    )


def test_evaluate_turn_returns_immediate_result_for_intent_generation():
    """Quand l'user demande de generer du code, evaluate_turn retourne
    un ChatTurnResult immediat (GENERATION_REDIRECT), pas un
    StreamingRequired."""
    from ui.chat.chat_controller import (
        ChatController, ChatTurnResult, ChatTurnKind,
    )
    ctrl = ChatController(backend=None, user_mode="beginner")
    out = ctrl.evaluate_turn("Génère-moi un programme pour allumer une LED")
    assert isinstance(out, ChatTurnResult), (
        f"Expected ChatTurnResult, got {type(out).__name__}"
    )
    assert out.kind == ChatTurnKind.GENERATION_REDIRECT


def test_evaluate_turn_returns_immediate_result_for_no_backend():
    from ui.chat.chat_controller import (
        ChatController, ChatTurnResult, ChatTurnKind,
    )
    ctrl = ChatController(backend=None, user_mode="beginner")
    out = ctrl.evaluate_turn("Comment ça marche un PWM ?")
    assert isinstance(out, ChatTurnResult)
    assert out.kind == ChatTurnKind.NO_BACKEND


def test_evaluate_turn_returns_streaming_required_for_llm_path():
    """Quand le pipeline aboutit a un appel LLM, evaluate_turn retourne
    un StreamingRequired avec system_prompt + messages prets."""
    from ui.chat.chat_controller import (
        ChatController, StreamingRequired,
    )
    ctrl = ChatController(backend=_StubBackend(), user_mode="beginner")
    out = ctrl.evaluate_turn("Comment ça marche un PWM ?")
    assert isinstance(out, StreamingRequired), (
        f"Expected StreamingRequired, got {type(out).__name__}"
    )
    txt = "Comment ça marche un PWM ?"
    assert out.user_text == txt
    assert out.messages[-1]["role"] == "user"
    assert txt in out.messages[-1]["content"]
    assert out.system_prompt   # non-vide


def test_commit_streamed_turn_appends_user_and_assistant():
    from ui.chat.chat_controller import ChatController
    ctrl = ChatController(backend=_StubBackend(), user_mode="beginner")
    assert ctrl.history == []
    ctrl.commit_streamed_turn("Hello", "Hi there")
    assert len(ctrl.history) == 2
    assert ctrl.history[0]["role"] == "user"
    assert ctrl.history[0]["content"] == "Hello"
    assert ctrl.history[1]["role"] == "assistant"
    assert ctrl.history[1]["content"] == "Hi there"


def test_run_turn_synchronous_path_still_works():
    """run_turn (synchrone) doit continuer a fonctionner et appeler
    chat() (pas chat_stream()) en interne pour les tests."""
    from ui.chat.chat_controller import ChatController, ChatTurnKind
    ctrl = ChatController(backend=_StubBackend(), user_mode="beginner")
    out = ctrl.run_turn("Comment ça marche un PWM ?")
    assert out.kind == ChatTurnKind.LLM_REPLY
    assert out.text == "Hello world"
    assert len(ctrl.history) == 2


def test_chat_message_update_text_reflects_new_content():
    """Verifie que update_text() change effectivement le texte de la
    bulle. Necessite QApplication."""
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print("[skip] PyQt6 non installe, test_chat_message_update_text "
              "saute.")
        return
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.chat.chat_message import ChatMessage
    bubble = ChatMessage(role="assistant", text="Hello", dark_theme=False)
    assert bubble.text == "Hello"
    bubble.update_text("Hello world updated")
    assert bubble.text == "Hello world updated"
    # Verifie aussi que l'attribut _browser existe (pour pouvoir le
    # re-render lors du streaming).
    assert getattr(bubble, "_browser", None) is not None, (
        "ChatMessage doit stocker self._browser pour permettre les "
        "updates incrementales pendant le streaming."
    )


# Cloud-provider streaming is now unified in OpenAICompatBackend.chat_stream
# (covered by scripts/test_openai_compat_backend.py); the old per-SDK Gemini /
# Anthropic streaming smoke tests were removed with those backends.
TESTS = [
    test_default_chat_stream_yields_full_response_in_one_chunk,
    test_ollama_chat_stream_method_exists,
    test_evaluate_turn_returns_immediate_result_for_intent_generation,
    test_evaluate_turn_returns_immediate_result_for_no_backend,
    test_evaluate_turn_returns_streaming_required_for_llm_path,
    test_commit_streamed_turn_appends_user_and_assistant,
    test_run_turn_synchronous_path_still_works,
    test_chat_message_update_text_reflects_new_content,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
