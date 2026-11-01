"""Backend factory: instantiates the active backend from ai_config + registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .base import AIBackend
from .ollama_backend import OllamaBackend
from .openai_compat import OpenAICompatBackend
from .providers import PROVIDERS, get_provider


@dataclass(frozen=True)
class ExtraBackend:
    """A backend supplied by the OPTIONAL package `ui.ai_backends.dev`.

    The application knows nothing about what such a backend is: only this
    shape, which is all the view and the configuration need to list it,
    label it, probe it and build it.
    """
    backend_id: str
    label: str
    subtitle: str
    available_text: str
    unavailable_text: str
    status_name: str
    create: Callable[[], AIBackend]


def _extras() -> dict[str, ExtraBackend]:
    """The optional backends, keyed by id -- EMPTY when the package is absent.

    ⚠️ Absence is the NORMAL state of an installation, not a failure: the
    package is never part of the published tree, so an unguarded import here
    would stop the application from starting. Evaluated on every call, never
    memorised -- the package decides what it offers.
    """
    try:
        from .dev import extra_backends
    except ImportError:
        return {}
    return {e.backend_id: e for e in extra_backends()}


def extra_backend(backend_id: str) -> "ExtraBackend | None":
    return _extras().get(backend_id)


def special_backends() -> list[str]:
    """Non-cloud backends shown in the UI, in display order."""
    return [*_extras(), "ollama"]


def known_backend_ids() -> set[str]:
    """Every backend id this build can actually run."""
    return {*_extras(), "ollama", "custom", *(p.id for p in PROVIDERS)}


def get_backend_instance(backend_id: str):
    """Build the backend for `backend_id`, reading keys/models from ai_config.

    Returns None for an unknown id.
    """
    from ..ai_config import ai_config   # local import: avoid import cycle

    extra = extra_backend(backend_id)
    if extra is not None:
        return extra.create()
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
