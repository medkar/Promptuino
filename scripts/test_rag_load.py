"""RAG loading tests: (1) the encoder loads independently of the embeddings
(unblocks the rebuild even if they're stale); (2) a corpus/embeddings desync
logs an explicit warning instead of dying silently.

Loads the real ONNX model (~1-2 s). Resets module state before/after."""
import contextlib
import io
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui.rag as rag


def _reset():
    rag._corpus = None
    rag._embeddings = None
    rag._session = None
    rag._tokenizer = None
    rag._input_names = set()
    rag._load_failed = False


def test_load_encoder_independent_of_embeddings():
    _reset()
    try:
        assert rag._load_encoder() is True
        vecs = rag.encode(["measure current with a sensor"])
        assert vecs.shape == (1, 384)
    finally:
        _reset()


def test_load_warns_on_desync():
    _reset()
    orig_np_load = np.load
    # Force a desync: embeddings with 1 row against the real corpus (!= 1).
    rag.np.load = lambda *a, **k: np.zeros((1, 384), dtype=np.float32)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = rag._load()
        out = buf.getvalue()
        assert ok is False
        assert "DÉSACTIVÉ" in out and "désync" in out
    finally:
        rag.np.load = orig_np_load
        _reset()


TESTS = [
    test_load_encoder_independent_of_embeddings,
    test_load_warns_on_desync,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
