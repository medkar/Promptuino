"""Tests ai_config.ollama_num_ctx (persistence + snap to valid steps).
Run : python scripts/test_ai_config_ollama_ctx.py
"""
from __future__ import annotations
import sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.ai_config as aicfg
from ui.ai_config import AIConfig, OLLAMA_NUM_CTX_STEPS


def _fresh(tmp: str) -> AIConfig:
    """A config instance bound to an isolated temp file."""
    aicfg.CONFIG_PATH = Path(tmp) / "config.json"
    return AIConfig()


def test_default_is_8192():
    with tempfile.TemporaryDirectory() as tmp:
        assert _fresh(tmp).ollama_num_ctx == 8192


def test_set_valid_value_persists():
    with tempfile.TemporaryDirectory() as tmp:
        c = _fresh(tmp)
        c.ollama_num_ctx = 16384
        assert c.ollama_num_ctx == 16384
        # New instance reads the same file -> value survived.
        assert _fresh(tmp).ollama_num_ctx == 16384


def test_snaps_to_nearest_step():
    with tempfile.TemporaryDirectory() as tmp:
        c = _fresh(tmp)
        c.ollama_num_ctx = 9000        # nearest is 8192
        assert c.ollama_num_ctx == 8192
        c.ollama_num_ctx = 100         # below min -> 2048
        assert c.ollama_num_ctx == 2048
        c.ollama_num_ctx = 10 ** 9     # above max -> 32768
        assert c.ollama_num_ctx == 32768


def test_steps_are_expected():
    assert OLLAMA_NUM_CTX_STEPS == (2048, 4096, 8192, 16384, 32768)


TESTS = [
    test_default_is_8192,
    test_set_valid_value_persists,
    test_snaps_to_nearest_step,
    test_steps_are_expected,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
