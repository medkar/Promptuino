"""Provider registry for the OpenAI-compatible adapter.

Adding a cloud provider = one entry here, no new code (cf. design spec).
base_url is INDICATIVE and may change — do not hardcode quotas or prices
anywhere. Il n'y a VOLONTAIREMENT aucun modèle par défaut : les modèles
bougent, et un défaut se recopie dans la config de qui ouvre l'écran une
fois. `gemini-2.5-flash`, écrit ici en avril 2026, était retiré par Google
en septembre et continuait d'être demandé (spec 2026-09-03).
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
    requires_key: bool = True
    context_window_hint: int = 8192
    key_url: str = ""                       # where to obtain a key (UI link)
    extra_headers: "Mapping[str, str] | None" = None  # e.g. OpenRouter / Anthropic version


PROVIDERS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        "gemini", "Gemini (Google)",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        context_window_hint=1_000_000,
        key_url="https://aistudio.google.com/apikey",
    ),
    ProviderPreset(
        "openai", "OpenAI", "https://api.openai.com/v1",
        context_window_hint=128_000,
        key_url="https://platform.openai.com/api-keys",
    ),
    ProviderPreset(
        "anthropic", "Anthropic", "https://api.anthropic.com/v1",
        context_window_hint=200_000,
        key_url="https://console.anthropic.com/settings/keys",
    ),
    ProviderPreset(
        "mistral", "Mistral", "https://api.mistral.ai/v1",
        context_window_hint=128_000,
        key_url="https://console.mistral.ai/api-keys",
    ),
    ProviderPreset(
        "deepseek", "DeepSeek", "https://api.deepseek.com/v1",
        context_window_hint=64_000,
        key_url="https://platform.deepseek.com/api_keys",
    ),
    ProviderPreset(
        "qwen", "Qwen Coder",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        context_window_hint=128_000,
        key_url="https://bailian.console.alibabacloud.com/",
    ),
    ProviderPreset(
        "groq", "Groq", "https://api.groq.com/openai/v1",
        context_window_hint=128_000,
        key_url="https://console.groq.com/keys",
    ),
    ProviderPreset(
        "openrouter", "OpenRouter", "https://openrouter.ai/api/v1",
        context_window_hint=128_000,
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
