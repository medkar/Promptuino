"""Formulation des avertissements du schema (2026-08-10).

Deux corrections demandees en QA, toutes deux sur ce que l'UTILISATEUR lit :

1. « Le cablage a ete deduit du code **(les marqueurs IA n'ont pas ete
   fournis)** » — la parenthese expliquait un detail d'IMPLEMENTATION a
   quelqu'un qui veut brancher son montage. Elle etait de surcroit perimee :
   le detecteur ne s'appuie plus sur des balises emises par le modele depuis
   `WIRING_DETECTOR_MODE = "python"`.

2. Le glyphe des avertissements de severite `info` etait un ℹ️ alors que la
   PASTILLE posee sur le composant, elle, est un symbole d'attention. Or tous
   les filets d'honnetete du detecteur sont en `info` et disent « l'app a
   devine ici » : le ℹ️ les faisait passer pour de la decoration, et le schema
   se contredisait avec lui-meme.

Run : python scripts/test_warning_wording.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.instructions import _WARNING_TEMPLATES, render_instructions
from ui.wiring.markers import extract_netlist

LANGS = ("fr", "en", "es", "it")

BARE_ANALOG = ("int pinCapteur = A0;\nint valeurLue = 0;\n"
               "void setup(){}\nvoid loop(){ valeurLue = analogRead(pinCapteur); }")


def _netlist():
    return extract_netlist(BARE_ANALOG, "arduino_uno_r3",
                           prompt="Lis un capteur sur A0")


def test_no_language_mentions_the_ai_markers():
    """Le detail d'implementation, dans les 4 langues."""
    tpl = _WARNING_TEMPLATES["wiring_inferred"]
    for lang in LANGS:
        low = tpl[lang].lower()
        for interdit in ("marqueur", "marker", "marcador", "marcatori"):
            assert interdit not in low, f"{lang}: {tpl[lang]!r}"


def test_no_language_keeps_a_parenthesis():
    """La parenthese elle-meme : c'est elle qui signalait l'apartee technique."""
    for lang in LANGS:
        assert "(" not in _WARNING_TEMPLATES["wiring_inferred"][lang], lang


def test_the_hardcoded_fallback_says_the_same_thing():
    """`markers` pose un message BRUT sur le warning, utilise si le gabarit
    traduit manque. Il portait sa propre copie de la phrase — donc sa propre
    copie de la parenthese."""
    warning = next(w for w in _netlist().warnings if w.code == "wiring_inferred")
    assert "marqueur" not in warning.message.lower(), warning.message
    assert "(" not in warning.message, warning.message


def test_the_warnings_section_uses_an_attention_glyph():
    """Ce que l'utilisateur voit vraiment, rendu de bout en bout."""
    md = render_instructions(_netlist(), lang="fr")
    lignes = [l for l in md.splitlines() if l.startswith("- ")]
    assert lignes, "aucun avertissement rendu"
    for l in lignes:
        assert l.startswith("- ⚠"), l
        assert "ℹ" not in l, l


def test_the_message_still_says_the_useful_part():
    """Retirer l'apartee ne doit pas vider le message : ce qui concerne
    l'utilisateur — le cablage est DEDUIT — doit rester."""
    md = render_instructions(_netlist(), lang="fr")
    assert "déduit du code" in md


def test_every_language_admits_it_may_be_wrong_and_points_somewhere():
    """Le wiring est experimental PAR CONSTRUCTION (il lit le code). Un constat
    neutre — « deduit du code » — ne dit ni que ca peut etre faux, ni ou aller
    si ca l'est. Les deux moities doivent survivre a une future reformulation,
    dans les 4 langues."""
    tpl = _WARNING_TEMPLATES["wiring_inferred"]
    aveu = {"fr": "inexact", "en": "inaccurate", "es": "inexacto",
            "it": "esatto"}
    for lang in LANGS:
        low = tpl[lang].lower()
        assert aveu[lang] in low, f"{lang} n'avoue pas l'imprecision : {tpl[lang]!r}"
        assert "chat" in low, f"{lang} n'indique pas ou demander de l'aide"


def test_the_hardcoded_fallback_carries_both_halves_too():
    """Le repli de `markers` doit rester aligne sur le gabarit : c'est lui qui
    s'affiche si le gabarit traduit disparait."""
    warning = next(w for w in _netlist().warnings if w.code == "wiring_inferred")
    low = warning.message.lower()
    assert "inexact" in low and "chat" in low, warning.message


TESTS = [
    test_no_language_mentions_the_ai_markers,
    test_no_language_keeps_a_parenthesis,
    test_the_hardcoded_fallback_says_the_same_thing,
    test_the_warnings_section_uses_an_attention_glyph,
    test_the_message_still_says_the_useful_part,
    test_every_language_admits_it_may_be_wrong_and_points_somewhere,
    test_the_hardcoded_fallback_carries_both_halves_too,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
