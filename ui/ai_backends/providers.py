"""Provider registry for the OpenAI-compatible adapter.

Adding a cloud provider = one entry here, no new code (cf. design spec).
base_url / default_model are INDICATIVE and may change — do not hardcode
quotas or prices anywhere; only these defaults live here.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ProviderPreset:
    """One OpenAI-compatible provider, reduced to config."""
    id: str
    label: str
    base_url: str
    default_model: str
    requires_key: bool = True
    context_window_hint: int = 8192
    key_url: str = ""                       # where to obtain a key (UI link)
    extra_headers: "Mapping[str, str] | None" = None  # e.g. OpenRouter / Anthropic version


PROVIDERS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        "gemini", "Gemini (Google)",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.5-flash", context_window_hint=1_000_000,
        key_url="https://aistudio.google.com/apikey",
    ),
    ProviderPreset(
        "openai", "OpenAI", "https://api.openai.com/v1",
        "gpt-4o-mini", context_window_hint=128_000,
        key_url="https://platform.openai.com/api-keys",
    ),
    ProviderPreset(
        "anthropic", "Anthropic", "https://api.anthropic.com/v1",
        "claude-sonnet-4-6", context_window_hint=200_000,
        key_url="https://console.anthropic.com/settings/keys",
    ),
    ProviderPreset(
        "mistral", "Mistral", "https://api.mistral.ai/v1",
        "mistral-small-latest", context_window_hint=128_000,
        key_url="https://console.mistral.ai/api-keys",
    ),
    ProviderPreset(
        "deepseek", "DeepSeek", "https://api.deepseek.com/v1",
        "deepseek-chat", context_window_hint=64_000,
        key_url="https://platform.deepseek.com/api_keys",
    ),
    ProviderPreset(
        "qwen", "Qwen Coder",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "qwen-coder-plus", context_window_hint=128_000,
        key_url="https://bailian.console.alibabacloud.com/",
    ),
    ProviderPreset(
        "groq", "Groq", "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile", context_window_hint=128_000,
        key_url="https://console.groq.com/keys",
    ),
    ProviderPreset(
        "openrouter", "OpenRouter", "https://openrouter.ai/api/v1",
        "qwen/qwen-2.5-coder-32b-instruct", context_window_hint=128_000,
        key_url="https://openrouter.ai/keys",
        extra_headers=MappingProxyType({"HTTP-Referer": "https://github.com/medkar/Promptuino",
                                       "X-Title": "Promptuino"}),
    ),
)


def get_provider(provider_id: str) -> ProviderPreset | None:
    """Preset for `provider_id`, or None (incl. 'custom', built from config)."""
    for p in PROVIDERS:
        if p.id == provider_id:
            return p
    return None
