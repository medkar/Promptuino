import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_studio_does_not_open_lib_clarification_dialog():
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    assert "LibClarificationDialog(" not in src, \
        "la modale pre-generation ne doit plus etre instanciee"


def test_module_forcing_preserved():
    # Les modules nommes forcent toujours leurs libs (sans modale).
    from ui.rag import module_forced_libs
    ids = [l.get("id") for l in module_forced_libs("un sketch avec un HW-612")]
    assert ids == ["mpu9250", "bmp280"], ids
    assert module_forced_libs("allume une led") == []


def test_forced_libs_keep_module_and_named_chip():
    # Regression 2026-07-08 : supprimer la MODALE ne doit PAS supprimer le
    # forcage SILENCIEUX des puces NOMMEES (SSD1306) ni des modules (HW-612).
    from ui.rag import forced_libs_for_generation
    ids = [l.get("id") for l in forced_libs_for_generation(
        "affiche la temperature avec HW612 sur oled SSD1306")]
    assert "mpu9250" in ids and "bmp280" in ids, ids       # module HW-612
    assert "adafruit-ssd1306" in ids, ids                  # puce nommee SSD1306
    # Un prompt basique ne force rien.
    assert forced_libs_for_generation("allume une led") == []


TESTS = [test_studio_does_not_open_lib_clarification_dialog, test_module_forcing_preserved,
         test_forced_libs_keep_module_and_named_chip]


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
