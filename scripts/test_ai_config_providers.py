"""ai_config multi-provider tests. Run: python scripts/test_ai_config_providers.py"""
from __future__ import annotations
import sys, types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Stub keyring with an in-memory store BEFORE importing ai_config.
_store = {}
fake_keyring = types.ModuleType("keyring")
fake_keyring.get_password = lambda s, k: _store.get((s, k))
fake_keyring.set_password = lambda s, k, v: _store.__setitem__((s, k), v)
def _del(s, k):
    _store.pop((s, k), None)
fake_keyring.delete_password = _del
sys.modules["keyring"] = fake_keyring

import ui.ai_config as cfg_mod


def _fresh(tmp_path):
    cfg_mod.CONFIG_PATH = tmp_path / "config.json"
    return cfg_mod.AIConfig()


def test_per_provider_key_roundtrip(tmp_path):
    c = _fresh(tmp_path)
    c.set_api_key("openai", "sk-abc")
    assert c.api_key("openai") == "sk-abc"
    assert c.api_key("mistral") == ""


def test_model_override(tmp_path):
    c = _fresh(tmp_path)
    assert c.model_for("openai") == "gpt-4o-mini"          # preset default
    c.set_model("openai", "gpt-4o")
    assert c.model_for("openai") == "gpt-4o"


def test_migration_anthropic_id(tmp_path):
    import json
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"ai_backend": "anthropic_api"}))
    cfg_mod.CONFIG_PATH = p
    c = cfg_mod.AIConfig()
    assert c.backend_id == "anthropic"                     # remapped


def test_custom_fields(tmp_path):
    c = _fresh(tmp_path)
    c.custom_base_url = "https://x.test/v1"
    c.custom_model = "m"
    assert c.custom_base_url == "https://x.test/v1"
    assert c.custom_model == "m"


TESTS = [test_per_provider_key_roundtrip, test_model_override,
         test_migration_anthropic_id, test_custom_fields]


def main() -> int:
    import tempfile
    for t in TESTS:
        with tempfile.TemporaryDirectory() as d:
            t(Path(d))
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
