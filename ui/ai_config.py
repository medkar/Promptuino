"""
AI configuration manager.

Storage:
  - Active backend → ~/Documents/Promptuino/config.json (non-sensitive)
  - API keys      → Windows Credential Manager via `keyring` (never in plaintext on disk)

Migration: if old plaintext keys are found in config.json,
they are migrated to keyring then removed from the file.
"""
import json
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

try:
    import keyring
    _KEYRING_OK = True
except Exception:
    _KEYRING_OK = False

_SERVICE    = "promptuino"
CONFIG_PATH = Path.home() / "Documents" / "Promptuino" / "config.json"

# Valid context sizes (tokens) for the local Ollama chat. The IA-tab slider
# offers these steps; the setter snaps any stored value to the nearest one.
OLLAMA_NUM_CTX_STEPS = (2048, 4096, 8192, 16384, 32768)
_OLLAMA_NUM_CTX_DEFAULT = 8192


def _snap_num_ctx(value) -> int:
    """Snap an arbitrary value to the nearest valid Ollama context step."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return _OLLAMA_NUM_CTX_DEFAULT
    return min(OLLAMA_NUM_CTX_STEPS, key=lambda step: abs(step - v))


_DEFAULTS: dict = {
    "ai_backend":   "claude_code",
    "ollama_model": "gemma4:e2b",
    "models":       {},          # {provider_id: model override}
    "custom_base_url": "",
    "custom_model":    "",
    "ollama_num_ctx":  _OLLAMA_NUM_CTX_DEFAULT,
}


class AIConfig(QObject):
    """AI configuration singleton — emits `changed` when the active backend changes."""

    changed = pyqtSignal(str)   # emits the new backend_id

    def __init__(self):
        super().__init__(None)
        self._data: dict = dict(_DEFAULTS)
        # dict(_DEFAULTS) is shallow: detach the nested `models` dict so it is
        # never shared with _DEFAULTS across instances.
        self._data["models"] = dict(self._data.get("models", {}))
        self._load()

    # ── JSON persistence (backend only) ─────────────────

    def _load(self):
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    saved = json.load(f)
                if "ai_backend" in saved:
                    bid = saved["ai_backend"]
                    if bid == "anthropic_api":      # migration: old id -> new
                        bid = "anthropic"
                    self._data["ai_backend"] = bid
                if "ollama_model" in saved:
                    self._data["ollama_model"] = saved["ollama_model"]
                if isinstance(saved.get("models"), dict):
                    self._data["models"] = saved["models"]
                self._data["custom_base_url"] = saved.get("custom_base_url", "")
                self._data["custom_model"] = saved.get("custom_model", "")
                self._data["ollama_num_ctx"] = _snap_num_ctx(
                    saved.get("ollama_num_ctx", _OLLAMA_NUM_CTX_DEFAULT)
                )
                # Migration: plaintext keys present → keyring → removal from the JSON
                self._migrate_plain_keys(saved)
        except Exception:
            pass

    def _migrate_plain_keys(self, saved: dict):
        """Transfers plaintext keys to keyring and removes them from the JSON."""
        migrated = False
        for field in ("gemini_api_key", "anthropic_api_key"):
            if saved.get(field):
                self._keyring_set(field, saved[field])
                saved.pop(field)
                migrated = True
        if migrated:
            try:
                CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(saved, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    def _save_backend(self):
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            existing: dict = {}
            if CONFIG_PATH.exists():
                try:
                    with open(CONFIG_PATH, encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    pass
            # Never rewrite plaintext keys, even if some are still lying around
            existing.pop("gemini_api_key", None)
            existing.pop("anthropic_api_key", None)
            existing["ai_backend"]   = self._data["ai_backend"]
            existing["ollama_model"] = self._data.get("ollama_model", "gemma4:e2b")
            existing["models"]          = self._data.get("models", {})
            existing["custom_base_url"] = self._data.get("custom_base_url", "")
            existing["custom_model"]    = self._data.get("custom_model", "")
            existing["ollama_num_ctx"] = self._data.get(
                "ollama_num_ctx", _OLLAMA_NUM_CTX_DEFAULT
            )
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── Keyring (API keys) ────────────────────────────────────

    def _keyring_get(self, key: str) -> str:
        if not _KEYRING_OK:
            return ""
        try:
            return keyring.get_password(_SERVICE, key) or ""
        except Exception:
            return ""

    def _keyring_set(self, key: str, value: str):
        if not _KEYRING_OK:
            return
        try:
            if value:
                keyring.set_password(_SERVICE, key, value)
            else:
                try:
                    keyring.delete_password(_SERVICE, key)
                except Exception:
                    pass
        except Exception:
            pass

    # ── Properties ────────────────────────────────────────────

    @property
    def backend_id(self) -> str:
        return self._data["ai_backend"]

    @backend_id.setter
    def backend_id(self, value: str):
        if self._data["ai_backend"] != value:
            self._data["ai_backend"] = value
            self._save_backend()
            self.changed.emit(value)

    def api_key(self, provider_id: str) -> str:
        return self._keyring_get(f"{provider_id}_api_key")

    def set_api_key(self, provider_id: str, value: str):
        self._keyring_set(f"{provider_id}_api_key", value)

    def model_for(self, provider_id: str) -> str:
        override = self._data.get("models", {}).get(provider_id)
        if override:
            return override
        from .ai_backends.providers import get_provider
        preset = get_provider(provider_id)
        return preset.default_model if preset else ""

    def set_model(self, provider_id: str, model: str):
        models = dict(self._data.get("models", {}))
        if model:
            models[provider_id] = model
        else:
            models.pop(provider_id, None)
        if models != self._data.get("models"):
            self._data["models"] = models
            self._save_backend()
            self.changed.emit(self._data["ai_backend"])

    @property
    def custom_base_url(self) -> str:
        return self._data.get("custom_base_url", "")

    @custom_base_url.setter
    def custom_base_url(self, value: str):
        if self._data.get("custom_base_url") != value:
            self._data["custom_base_url"] = value
            self._save_backend()

    @property
    def custom_model(self) -> str:
        return self._data.get("custom_model", "")

    @custom_model.setter
    def custom_model(self, value: str):
        if self._data.get("custom_model") != value:
            self._data["custom_model"] = value
            self._save_backend()

    @property
    def ollama_model(self) -> str:
        return self._data.get("ollama_model", "gemma4:e2b")

    @ollama_model.setter
    def ollama_model(self, value: str):
        if self._data.get("ollama_model") != value:
            self._data["ollama_model"] = value
            self._save_backend()
            # Notifies the views (status bar, etc.) that the label of the active
            # backend may have changed — re-emits the current backend_id unchanged.
            self.changed.emit(self._data["ai_backend"])

    @property
    def ollama_num_ctx(self) -> int:
        return self._data.get("ollama_num_ctx", _OLLAMA_NUM_CTX_DEFAULT)

    @ollama_num_ctx.setter
    def ollama_num_ctx(self, value: int):
        snapped = _snap_num_ctx(value)
        if self._data.get("ollama_num_ctx") != snapped:
            self._data["ollama_num_ctx"] = snapped
            self._save_backend()
            self.changed.emit(self._data["ai_backend"])

    @property
    def keyring_available(self) -> bool:
        return _KEYRING_OK

    def display_name(self) -> str:
        """Short name of the active backend for the status bar."""
        bid = self._data["ai_backend"]
        if bid == "claude_code":
            return "Claude Code"
        if bid == "ollama":
            return f"Ollama ({self._data.get('ollama_model', 'gemma4:e2b')})"
        if bid == "custom":
            return f"Custom ({self._data.get('custom_model') or '?'})"
        from .ai_backends.providers import get_provider
        preset = get_provider(bid)
        return preset.label if preset else bid


# Global instance — imported by all modules
ai_config = AIConfig()
