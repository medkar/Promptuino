"""Smoke-test retrieve_libs() against representative prompts."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.rag import retrieve_libs  # noqa: E402

PROMPTS = [
    # Vague (no model mentioned)
    "afficher du texte sur un ecran 16x2",
    # User adds the screen type / model
    "afficher du texte sur un LCD 16x2",
    "afficher du texte sur un LCD I2C",
    "display text on an HD44780 LCD",
    "afficher du texte sur un ecran OLED",  # corpus has no OLED yet
    # Vague EN
    "show text on a 16x2 screen",
]

for prompt in PROMPTS:
    print(f"\n=== {prompt!r}")
    libs = retrieve_libs(prompt, k=3, threshold=0.0)
    if not libs:
        print("  (no results)")
        continue
    for lib in libs:
        print(f"  {lib['_score']:.3f}  {lib['name']}")
