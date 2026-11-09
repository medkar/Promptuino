from .base import AIBackend
from .ollama_backend import (OllamaBackend, is_installed, is_server_running,
                             is_model_available, list_local_models,
                             is_process_running, start_server)
from .openai_compat import OpenAICompatBackend
from .providers import PROVIDERS, ProviderPreset, get_provider
from .factory import (get_backend_instance, special_backends,
                      extra_backend, known_backend_ids, ExtraBackend,
                      backend_requires_key, LOCAL_BACKENDS)

__all__ = [
    "AIBackend", "OllamaBackend", "OpenAICompatBackend",
    "PROVIDERS", "ProviderPreset", "get_provider",
    "is_installed", "is_server_running", "is_model_available",
    "list_local_models", "is_process_running", "start_server",
    "get_backend_instance", "special_backends", "extra_backend",
    "known_backend_ids", "ExtraBackend", "backend_requires_key",
    "LOCAL_BACKENDS",
]
