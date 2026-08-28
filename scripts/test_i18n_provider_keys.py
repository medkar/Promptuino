"""Provider i18n keys present in all 4 languages. Run: python scripts/test_i18n_provider_keys.py"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.i18n import TRANSLATIONS

KEYS = [
    "ia_err_auth", "ia_err_notfound", "ia_err_quota", "ia_err_provider",
    "ia_err_network", "ia_err_bad_response",
    "ia_cloud_provider_title", "ia_cloud_provider_subtitle",
    "ia_provider_label", "ia_model_label", "ia_model_placeholder",
    "ia_base_url_label", "ia_get_key_link",
    "ia_model_disclaimer", "ia_models_loading",
    "ia_models_none", "ia_models_unsupported",
]


def test_keys_present_all_langs():
    for code, s in TRANSLATIONS.items():
        for k in KEYS:
            assert getattr(s, k, ""), f"{code}: clé '{k}' manquante/vide"


TESTS = [test_keys_present_all_langs]


def main() -> int:
    for t in TESTS:
        t()
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
