"""Aucun modèle par défaut : les modèles bougent, un défaut pourrit.

Un défaut écrit en avril 2026 (`gemini-2.5-flash`) était retiré par Google en
septembre, et il s'était recopié dans la config de tous ceux qui avaient
ouvert l'écran une fois. Voir la spec 2026-09-03.

Run: python scripts/test_no_default_model.py
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.ai_backends.providers import PROVIDERS, ProviderPreset


def test_the_field_is_gone_from_the_dataclass():
    """Vidé ne suffit pas : un champ qui existe finit par être lu."""
    noms = {f.name for f in dataclasses.fields(ProviderPreset)}
    assert "default_model" not in noms, sorted(noms)


def test_no_provider_carries_a_model():
    for p in PROVIDERS:
        assert not hasattr(p, "default_model"), p.id


def test_the_useful_fields_stayed():
    """Seul `default_model` part -- le reste du registre sert encore."""
    noms = {f.name for f in dataclasses.fields(ProviderPreset)}
    for attendu in ("id", "label", "base_url", "context_window_hint",
                    "key_url", "requires_key", "extra_headers"):
        assert attendu in noms, (attendu, sorted(noms))


def test_the_entries_did_not_shift():
    """Les arguments sont POSITIONNELS : retirer le 4e decalait tout ce qui
    suit. Une base_url atterrie dans le mauvais champ ne se verrait qu'a
    l'usage, sur un fournisseur qu'on n'utilise pas."""
    attendu = {
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "mistral": "https://api.mistral.ai/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "groq": "https://api.groq.com/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }
    vus = {p.id: p.base_url for p in PROVIDERS}
    assert vus == attendu, vus
    for p in PROVIDERS:
        assert p.label and not p.label.startswith("http"), p
        assert p.key_url.startswith("http"), (p.id, p.key_url)
        assert isinstance(p.context_window_hint, int) and \
            p.context_window_hint > 0, (p.id, p.context_window_hint)


def test_an_unchosen_provider_has_no_model():
    """`model_for` ne doit plus inventer : sans choix enregistre, rien."""
    from ui.ai_config import AIConfig
    cfg = AIConfig.__new__(AIConfig)     # sans __init__ : n'ecrit PAS la
    cfg._data = {"models": {}}           # config reelle de l'utilisateur
    assert cfg.model_for("gemini") == ""
    assert cfg.model_for("openai") == ""
    assert cfg.model_for("inconnu") == ""


def test_a_chosen_provider_keeps_its_model():
    from ui.ai_config import AIConfig
    cfg = AIConfig.__new__(AIConfig)
    cfg._data = {"models": {"gemini": "gemini-3.5-flash"}}
    assert cfg.model_for("gemini") == "gemini-3.5-flash"
    assert cfg.model_for("openai") == ""


def test_the_settings_screen_names_the_missing_model():
    """<< Aucun modele choisi >> doit etre un etat DIT au reglage, pas un
    echec decouvert a la premiere generation."""
    from ui.i18n import TRANSLATIONS
    vus = {}
    for code, s in TRANSLATIONS.items():
        msg = getattr(s, "ia_model_none_chosen", "")
        assert msg, f"{code}: cle 'ia_model_none_chosen' manquante/vide"
        vus[code] = msg
    assert len(set(vus.values())) == len(vus), \
        f"au moins une langue recopie une autre : {vus}"


TESTS = [
    test_the_field_is_gone_from_the_dataclass,
    test_no_provider_carries_a_model,
    test_the_useful_fields_stayed,
    test_the_entries_did_not_shift,
    test_an_unchosen_provider_has_no_model,
    test_a_chosen_provider_keeps_its_model,
    test_the_settings_screen_names_the_missing_model,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
