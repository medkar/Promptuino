import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# _t is the i18n resolver used by the wiring dialog. Find its exact import via:
#   grep "too_many_dc_motors_banner" ui/wiring/wiring_diagram_dialog.py
from ui.wiring.wiring_diagram_dialog import _t


def test_experimental_banner_all_langs():
    for lang in ("fr", "en", "es", "it"):
        txt = _t("wiring_experimental_banner", lang)
        assert txt and "wiring_experimental_banner" != txt, (lang, txt)
        assert len(txt) > 20, (lang, txt)


TESTS = [test_experimental_banner_all_langs]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
