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
from ui.ai_backends import get_backend_instance, backend_requires_key
from ui.ai_backends.openai_compat import OpenAICompatBackend
from ui.ai_backends.ollama_backend import OllamaBackend


def test_cloud_provider_builds_openai_compat():
    ai_config.set_api_key("openai", "sk-xyz")
    ai_config._data["ai_backend"] = "openai"
    b = get_backend_instance("openai")
    assert isinstance(b, OpenAICompatBackend)
    assert b.backend_id == "openai"
    assert b._api_key == "sk-xyz"
    assert b._base_url.endswith("/v1")


def test_ollama_builds_its_backend():
    assert isinstance(get_backend_instance("ollama"), OllamaBackend)


def test_custom_provider():
    ai_config._data["custom_base_url"] = "https://x.test/v1"
    ai_config._data["custom_model"] = "m"
    ai_config.set_api_key("custom", "k")
    b = get_backend_instance("custom")
    assert isinstance(b, OpenAICompatBackend)
    assert b._base_url == "https://x.test/v1" and b._model == "m"


def test_unknown_returns_none():
    assert get_backend_instance("nope") is None


# ── Une SEULE source a « ce backend exige-t-il une cle ? » ────────────────────
# Le defaut venait de deux reponses contradictoires : `is_available()` exigeait
# une cle de tout le monde, la pastille n'en reclamait pas a « custom ».

def test_the_key_requirement_is_derived_from_the_presets():
    """⛔ Derivee, pas enumeree : le champ `requires_key` existait deja sur
    `ProviderPreset` et n'etait lu par PERSONNE. Une liste ecrite a la main
    ici redivergerait du registre a la premiere addition."""
    from ui.ai_backends.providers import PROVIDERS
    for preset in PROVIDERS:
        assert backend_requires_key(preset.id) is preset.requires_key, preset.id


def test_local_backends_need_no_key():
    assert backend_requires_key("custom") is False
    assert backend_requires_key("ollama") is False


def test_an_unknown_id_is_assumed_to_need_a_key():
    """Le defaut prudent : mieux vaut exiger une cle en trop que declarer
    disponible un backend qu'on ne sait pas construire."""
    assert backend_requires_key("zorglub") is True


def test_custom_is_built_without_demanding_a_key():
    """Le cas du Fablab : serveur local compatible OpenAI, aucune cle.

    ⚠️ On ecrit dans `_data` et jamais par les setters -- ceux-ci appellent
    `_save_backend()`, qui ecrirait la config REELLE de l'utilisateur.
    """
    ai_config._data["custom_base_url"] = "http://localhost:1234/v1"
    ai_config._data["custom_model"] = "gemma-4"
    ai_config.set_api_key("custom", "")
    b = get_backend_instance("custom")
    assert b.requires_api_key is False
    assert b.is_available() is True, "un serveur local sans cle doit etre utilisable"


def test_a_cloud_preset_is_built_demanding_its_key():
    ai_config.set_api_key("openai", "")
    b = get_backend_instance("openai")
    assert b.requires_api_key is True
    assert b.is_available() is False


TESTS = [test_cloud_provider_builds_openai_compat, test_ollama_builds_its_backend,
         test_custom_provider, test_unknown_returns_none,
         test_the_key_requirement_is_derived_from_the_presets,
         test_local_backends_need_no_key,
         test_an_unknown_id_is_assumed_to_need_a_key,
         test_custom_is_built_without_demanding_a_key,
         test_a_cloud_preset_is_built_demanding_its_key]


def main() -> int:
    for t in TESTS:
        t()
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
