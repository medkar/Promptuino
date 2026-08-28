"""Tests parsing taille modele + is_slm / context_window_hint Ollama.
Run : python scripts/test_chat_is_slm.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.ai_backends.ollama_backend import OllamaBackend, _parse_param_size_b


def test_parse_param_size():
    assert _parse_param_size_b("7B") == 7.0
    assert _parse_param_size_b("2.6B") == 2.6
    assert _parse_param_size_b("8.0B") == 8.0
    assert abs(_parse_param_size_b("350M") - 0.35) < 1e-9
    assert _parse_param_size_b(None) is None
    assert _parse_param_size_b("garbage") is None


def test_is_slm_from_show_details():
    b = OllamaBackend(model="whatever")
    b._show_cache = {"details": {"parameter_size": "2.6B"}}
    assert b.is_slm is True
    b2 = OllamaBackend(model="whatever")
    b2._show_cache = {"details": {"parameter_size": "8.0B"}}
    assert b2.is_slm is False


def test_is_slm_from_name_fallback():
    b = OllamaBackend(model="gemma:2b")
    b._show_cache = {}
    assert b.is_slm is True
    b2 = OllamaBackend(model="llama3:8b")
    b2._show_cache = {}
    assert b2.is_slm is False


def test_is_slm_unknown_is_false():
    b = OllamaBackend(model="customblob")
    b._show_cache = {}
    assert b.is_slm is False


def test_context_window_hint_from_model_info():
    b = OllamaBackend(model="whatever")
    b._show_cache = {"model_info": {"gemma.context_length": 8192}}
    assert b.context_window_hint == 8192
    b2 = OllamaBackend(model="whatever")
    b2._show_cache = {"model_info": {"llama.context_length": 131072}}
    assert b2.context_window_hint == 131072


def test_context_window_hint_fallback():
    b = OllamaBackend(model="whatever")
    b._show_cache = {}
    assert b.context_window_hint == 8192


TESTS = [
    test_parse_param_size,
    test_is_slm_from_show_details,
    test_is_slm_from_name_fallback,
    test_is_slm_unknown_is_false,
    test_context_window_hint_from_model_info,
    test_context_window_hint_fallback,
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
