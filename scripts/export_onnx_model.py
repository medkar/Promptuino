"""One-shot: export paraphrase-multilingual-MiniLM-L12-v2 to ONNX (fp32).

Output: assets/rag/model/
  model.onnx              ONNX graph, fp32 (~450 MB)
  config.json             HF config (kept for parity)
  tokenizer.json          fast tokenizer payload for `tokenizers` lib
  tokenizer_config.json
  special_tokens_map.json

We tried int8 dynamic quantization (per-tensor and per-channel, AVX2):
both lost 6-8 / 152 cases on the multilingual smoke test, mainly tight
motor-driver retrievals (L298N vs L293D vs DRV8833 vs TB6612FNG separated
by ~0.01 cosine). Cosine-vs-fp32 drift was ~1.3% per embedding, which
compounds across query × corpus and breaks the tighter rankings.

The 250k-token embedding matrix dominates this model (~95M of 117M params)
and quantizes poorly — the per-token row variance is too high. fp32 is
the right tradeoff for this checkpoint: 450 MB ONNX is still much smaller
than the ~700 MB pulled by the sentence-transformers + torch pilot stack.

Run from repo root, dev-only:
    pip install "optimum[onnxruntime]"
    python scripts/export_onnx_model.py

After this, runtime no longer needs sentence-transformers / torch.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "assets" / "rag" / "model"
MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Exporting {MODEL_ID} to {OUTPUT_DIR.relative_to(REPO_ROOT)} (fp32)…")

    from optimum.onnxruntime import ORTModelForFeatureExtraction
    from transformers import AutoTokenizer

    model = ORTModelForFeatureExtraction.from_pretrained(MODEL_ID, export=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print(f"\nFinal contents of {OUTPUT_DIR.relative_to(REPO_ROOT)}:")
    files = sorted(p for p in OUTPUT_DIR.iterdir() if p.is_file())
    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {size_mb:7.2f} MB  {f.name}")
    total_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
    print(f"  {total_mb:7.2f} MB  TOTAL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
