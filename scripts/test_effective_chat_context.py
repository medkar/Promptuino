"""Tests AIBackend.effective_chat_context().
Run : python scripts/test_effective_chat_context.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.ai_backends.openai_compat import OpenAICompatBackend


def test_base_default_equals_context_window_hint():
    # A backend that does NOT override effective_chat_context() must fall back
    # to its declared window (a cloud backend gets the whole window).
    b = OpenAICompatBackend(base_url="https://x.test/v1", api_key="k",
                            model="m", backend_id="x", label="X")
    assert b.effective_chat_context() == b.context_window_hint


TESTS = [
    test_base_default_equals_context_window_hint,
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
