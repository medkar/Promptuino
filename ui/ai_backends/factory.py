"""Backend factory: instantiates the active backend from ai_config + registry."""
from .claude_code import ClaudeCodeBackend
from .ollama_backend import OllamaBackend
from .openai_compat import OpenAICompatBackend
from .providers import get_provider

# Non-cloud backends shown in the UI besides the cloud providers.
SPECIAL_BACKENDS: list[str] = ["claude_code", "ollama"]

# Transitional: ia_view still iterates this until it is rewritten (Task 9).
# Only the two special (non-cloud) backends; cloud providers come from the
# registry, not from here.
BACKEND_DEFS: list[tuple[str, type]] = [
    ("claude_code", ClaudeCodeBackend),
    ("ollama",      OllamaBackend),
]


def get_backend_instance(backend_id: str):
    """Build the backend for `backend_id`, reading keys/models from ai_config.

    Returns None for an unknown id.
    """
    from ..ai_config import ai_config   # local import: avoid import cycle

    if backend_id == "claude_code":
        return ClaudeCodeBackend()
    if backend_id == "ollama":
        return OllamaBackend(ai_config.ollama_model)
    if backend_id == "custom":
        return OpenAICompatBackend(
            base_url=ai_config.custom_base_url,
            api_key=ai_config.api_key("custom"),
            model=ai_config.custom_model,
            backend_id="custom", label="Custom",
        )
    preset = get_provider(backend_id)
    if preset is None:
        return None
    return OpenAICompatBackend(
        base_url=preset.base_url,
        api_key=ai_config.api_key(backend_id),
        model=ai_config.model_for(backend_id),
        backend_id=preset.id, label=preset.label,
        context_window_hint=preset.context_window_hint,
        extra_headers=preset.extra_headers,
    )
