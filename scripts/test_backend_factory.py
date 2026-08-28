"""Backend factory tests. Run: python scripts/test_backend_factory.py"""
from __future__ import annotations
import sys, types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_store = {}
fk = types.ModuleType("keyring")
fk.get_password = lambda s, k: _store.get((s, k))
fk.set_password = lambda s, k, v: _store.__setitem__((s, k), v)
fk.delete_password = lambda s, k: _store.pop((s, k), None)
sys.modules["keyring"] = fk

from ui.ai_config import ai_config
from ui.ai_backends import get_backend_instance
from ui.ai_backends.openai_compat import OpenAICompatBackend
from ui.ai_backends.ollama_backend import OllamaBackend
from ui.ai_backends.claude_code import ClaudeCodeBackend


def test_cloud_provider_builds_openai_compat():
    ai_config.set_api_key("openai", "sk-xyz")
    ai_config._data["ai_backend"] = "openai"
    b = get_backend_instance("openai")
    assert isinstance(b, OpenAICompatBackend)
    assert b.backend_id == "openai"
    assert b._api_key == "sk-xyz"
    assert b._base_url.endswith("/v1")


def test_ollama_and_claude_special():
    assert isinstance(get_backend_instance("ollama"), OllamaBackend)
    assert isinstance(get_backend_instance("claude_code"), ClaudeCodeBackend)


def test_custom_provider():
    ai_config._data["custom_base_url"] = "https://x.test/v1"
    ai_config._data["custom_model"] = "m"
    ai_config.set_api_key("custom", "k")
    b = get_backend_instance("custom")
    assert isinstance(b, OpenAICompatBackend)
    assert b._base_url == "https://x.test/v1" and b._model == "m"


def test_unknown_returns_none():
    assert get_backend_instance("nope") is None


TESTS = [test_cloud_provider_builds_openai_compat, test_ollama_and_claude_special,
         test_custom_provider, test_unknown_returns_none]


def main() -> int:
    for t in TESTS:
        t()
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
