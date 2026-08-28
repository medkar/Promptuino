"""Provider registry tests. Run: python scripts/test_providers_registry.py"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.ai_backends.providers import PROVIDERS, ProviderPreset, get_provider


def test_all_presets_well_formed():
    ids = set()
    for p in PROVIDERS:
        assert isinstance(p, ProviderPreset)
        assert p.id and p.id not in ids, f"id manquant ou dupliqué: {p.id}"
        ids.add(p.id)
        assert p.label, f"label manquant: {p.id}"
        assert p.base_url.startswith("http"), f"base_url invalide: {p.id}"
        assert p.default_model, f"default_model manquant: {p.id}"
        assert p.context_window_hint > 0


def test_expected_providers_present():
    ids = {p.id for p in PROVIDERS}
    assert {"gemini", "openai", "anthropic", "mistral",
            "deepseek", "qwen", "groq", "openrouter"} <= ids


def test_get_provider_lookup():
    assert get_provider("openai").label == "OpenAI"
    assert get_provider("does-not-exist") is None


def test_custom_not_in_registry():
    # "custom" is built from user config, not a preset.
    assert get_provider("custom") is None


TESTS = [test_all_presets_well_formed, test_expected_providers_present,
         test_get_provider_lookup, test_custom_not_in_registry]


def main() -> int:
    for t in TESTS:
        t()
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
