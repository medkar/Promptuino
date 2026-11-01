"""Tests OllamaBackend.effective_chat_context() + num_ctx wired into chat.
Run : python scripts/test_ollama_chat_num_ctx.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.ai_backends.ollama_backend as ob
from ui.ai_backends.ollama_backend import OllamaBackend
from ui.ai_config import ai_config


def _backend(model_ctx: int) -> OllamaBackend:
    b = OllamaBackend("m")
    # Inject the /api/show cache so context_window_hint is deterministic.
    b._show_cache = {"model_info": {"m.context_length": model_ctx}}
    return b


def test_effective_is_min_of_setting_and_model():
    ai_config._data["ollama_num_ctx"] = 8192      # in-memory only (no disk)
    assert _backend(100000).effective_chat_context() == 8192
    assert _backend(4096).effective_chat_context() == 4096   # model smaller


def test_chat_sets_num_ctx():
    ai_config._data["ollama_num_ctx"] = 16384
    b = _backend(100000)
    captured = {}

    def fake_post(path, payload, timeout=0):
        captured["payload"] = payload
        return {"message": {"content": "ok"}}

    orig = ob._post
    ob._post = fake_post
    try:
        out = b.chat("sys", [{"role": "user", "content": "hi"}])
    finally:
        ob._post = orig
    assert out == "ok"
    assert captured["payload"]["options"]["num_ctx"] == 16384


def test_chat_stream_sets_num_ctx():
    ai_config._data["ollama_num_ctx"] = 8192
    b = _backend(100000)
    captured = {}

    def fake_post_stream(path, payload, timeout=0):
        captured["payload"] = payload
        yield {"message": {"content": "ok"}, "done": False}
        yield {"done": True}

    orig = ob._post_stream
    ob._post_stream = fake_post_stream
    try:
        chunks = list(b.chat_stream("sys", [{"role": "user", "content": "hi"}]))
    finally:
        ob._post_stream = orig
    assert "".join(chunks) == "ok"
    assert captured["payload"]["options"]["num_ctx"] == 8192


TESTS = [
    test_effective_is_min_of_setting_and_model,
    test_chat_sets_num_ctx,
    test_chat_stream_sets_num_ctx,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
