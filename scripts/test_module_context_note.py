"""Note de contexte MODULE : quand le prompt nomme un module (HW-612/GY-91),
le contexte de generation doit lier EXPLICITEMENT le module a ses puces, sinon
un SLM ne comprend pas que MPU9250+BMP280 SONT le HW-612 et les abandonne.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.rag import build_lib_context, forced_libs_for_generation, corpus_entry


def test_named_module_gets_explicit_note():
    p = "affiche la temperature avec HW612 sur oled SSD1306"
    forced = forced_libs_for_generation(p)
    ctx = build_lib_context(p, forced_libs=forced)
    # La note lie explicitement le module a ses puces.
    assert "HW-612" in ctx, ctx[:300]
    low = ctx.lower()
    assert "module" in low and "breakout" in low, ctx[:300]
    assert "must" in low, "la note doit rendre l'usage des libs obligatoire"
    # Les puces (et l'ecran nomme) sont bien presentes.
    assert "MPU9250" in ctx and "BMP280" in ctx, ctx[:300]


def test_no_module_no_note():
    # Une puce NOMMEE seule (pas un module) ne declenche PAS la note module.
    ssd = corpus_entry("adafruit-ssd1306")
    assert ssd is not None
    ctx = build_lib_context("affiche du texte sur un ssd1306", forced_libs=[ssd])
    assert "breakout board" not in ctx.lower(), ctx[:200]


TESTS = [test_named_module_gets_explicit_note, test_no_module_no_note]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
