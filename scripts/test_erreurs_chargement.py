"""Un refus de chargement se dit SIMPLEMENT, dans la langue de l'app.

Demande de l'auteur du 2026-11-06, capture a l'appui : « LM Studio n'a pas pu
charger le modele : Failed to load LLM '…': Error: Model loading was stopped
due to insufficient system resources. Under the current settings, this model
requires approximately 29.11 GB of memory, and continuing… » -- trop long,
trop complexe, en anglais. Plus de texte brut : le manque de memoire a son
message (avec le chiffre, utile), les autres echecs une phrase simple.

Run: python scripts/test_erreurs_chargement.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.erreurs_chargement import message  # noqa: E402
from ui.i18n import TRANSLATIONS  # noqa: E402

# Recopie EXACTE de la capture de l'auteur.
LMS_MEMOIRE = ("Failed to load LLM 'google/gemma-4-12b-qat': Error: Model loading was "
               "stopped due to insufficient system resources. Under the current settings, "
               "this model requires approximately 29.11 GB of memory, and continuing to "
               "load it would likely overload your system and cause it to freeze. If you "
               "think this is incorrect, you can adjust the model loading guardrails in "
               "settings.")
# Forme du refus d'Ollama.
OLLAMA_MEMOIRE = "model requires more system memory (9.1 GiB) than is available (4.0 GiB)"


def test_lm_studios_memory_refusal_becomes_a_short_sentence_with_the_size():
    s = TRANSLATIONS["fr"]
    m = message("lmstudio", LMS_MEMOIRE, s)
    assert m == s.load_no_memory.format(go=29), m
    assert "Failed" not in m and "guardrails" not in m


def test_ollamas_memory_refusal_too():
    s = TRANSLATIONS["fr"]
    assert message("ollama", OLLAMA_MEMOIRE, s) == s.load_no_memory.format(go=9)


def test_a_memory_refusal_without_a_number_still_says_memory():
    s = TRANSLATIONS["fr"]
    assert message("lmstudio", "insufficient system resources", s) == s.load_no_memory_short


def test_any_other_failure_is_one_plain_sentence_never_the_raw_text():
    s = TRANSLATIONS["fr"]
    assert message("lmstudio", "Error: kaboom 0x80004005", s) == s.lms_load_failed
    assert message("ollama", "boom", s) == s.om_load_failed
    assert message("lmstudio", "instance busy", s, decharge=True) == s.lms_unload_failed
    assert message("ollama", "", s, decharge=True) == s.om_unload_failed


def test_every_language_has_short_texts_without_the_raw_error_slot():
    for code, s in TRANSLATIONS.items():
        for cle in ("lms_load_failed", "lms_unload_failed", "om_load_failed",
                    "om_unload_failed", "load_no_memory_short"):
            assert "{err}" not in getattr(s, cle), (code, cle)
        assert "{go}" in s.load_no_memory, code
        assert len(s.load_no_memory.format(go=29)) < 170, (code, "trop long")


def test_a_download_failure_says_what_to_do_never_the_raw_text():
    """Meme regle pour les telechargements (demande de l'auteur, 2026-11-06)."""
    from ui.erreurs_chargement import telechargement
    s = TRANSLATIONS["fr"]
    # Ollama, nom inconnu ; LM Studio, nom inconnu (forme du test de la fenetre).
    assert telechargement("pull model manifest: file does not exist", s) == s.dl_not_found
    assert telechargement("x/y not found", s) == s.dl_not_found
    assert telechargement("URLError", s) == s.dl_network
    assert telechargement("<urlopen error [Errno 11001] getaddrinfo failed>", s) == s.dl_network
    assert telechargement("unexpected EOF", s) == s.md_failed
    assert telechargement("", s) == s.md_failed
    for code, t in TRANSLATIONS.items():
        for cle in ("md_failed", "dl_not_found", "dl_network", "md_delete_failed"):
            assert getattr(t, cle).strip() and "{err}" not in getattr(t, cle), (code, cle)


TESTS = [
    test_a_download_failure_says_what_to_do_never_the_raw_text,
    test_lm_studios_memory_refusal_becomes_a_short_sentence_with_the_size,
    test_ollamas_memory_refusal_too,
    test_a_memory_refusal_without_a_number_still_says_memory,
    test_any_other_failure_is_one_plain_sentence_never_the_raw_text,
    test_every_language_has_short_texts_without_the_raw_error_slot,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
