import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules.setdefault("ui", ui_pkg)


def test_replace_fields_present_all_langs():
    from ui.i18n import TRANSLATIONS
    for lang, s in TRANSLATIONS.items():
        for f in ("component_replace_dropdown",
                  "component_replace_divergence_title",
                  "component_replace_divergence_message",
                  "component_replace_continue"):
            assert getattr(s, f), f"{f} manquant en {lang}"


TESTS = [
    test_replace_fields_present_all_langs,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
