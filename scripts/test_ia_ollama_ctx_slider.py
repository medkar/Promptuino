"""Smoke test: the Ollama section has a context-size slider that writes config.
Run : python scripts/test_ia_ollama_ctx_slider.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])   # keep a module-level ref

from ui.ai_config import ai_config, OLLAMA_NUM_CTX_STEPS
from ui.ia_view import _BackendSection


def test_slider_present_and_writes_config():
    ai_config._save_backend = lambda: None    # no disk writes during the test
    sec = _BackendSection("ollama")
    assert hasattr(sec, "_ctx_slider"), "Ollama section missing the context slider"
    sec._ctx_slider.setValue(len(OLLAMA_NUM_CTX_STEPS) - 1)   # max step
    assert ai_config.ollama_num_ctx == OLLAMA_NUM_CTX_STEPS[-1]
    assert sec._lbl_ctx_value.text() == f"{OLLAMA_NUM_CTX_STEPS[-1] // 1024}k tokens"


TESTS = [test_slider_present_and_writes_config]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"OK : {len(TESTS)} tests")
    os._exit(0)   # bypass Qt teardown (avoids GC-order crash on exit)


if __name__ == "__main__":
    main()
