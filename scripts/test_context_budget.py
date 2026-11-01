"""TODO #48 — le prompt peut depasser la fenetre, et personne ne le disait.

`ollama_backend._call` alloue une fenetre qui doit contenir LE PROMPT ET LA
SORTIE, et rien ne verifiait qu'on y tienne. Au-dela d'une certaine taille de
projet le modele perd le DEBUT du contexte : la generation produit du code qui
ignore une partie du sketch — redeclare une variable, reutilise une broche deja
prise — sans qu'aucun message ne le dise. Le symptome n'est pas une erreur,
c'est un resultat plausible et faux.

Mesures du 2026-08-10, texture prise sur les 1409 lignes de code des 91
exemples du corpus (24,3 caracteres par ligne), fenetre locale de 8192 :

    Ajouter   depasse vers ~1070 lignes de sketch (il injecte le sketch entier)
    Modifier  depasse vers  ~560 lignes pour UNE fonctionnalite
    Regenerer ne depasse jamais (1141 tokens, plat)

Un projet debutant fait 30 a 120 lignes — 21 a 28 % de la fenetre. Le trou ne
s'ouvre que sur un gros projet, et c'est la que l'utilisateur a le plus a
perdre.

Run : python scripts/test_context_budget.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.generation.context_budget import (estimate_tokens, generation_window,
                                          prompt_overflows)
from ui.i18n import TRANSLATIONS

LANGS = ("fr", "en", "es", "it")


class _Backend:
    def __init__(self, window=8192):
        self._w = window

    def generation_context(self):
        return self._w


def _texte(tokens: int) -> str:
    return "x" * (tokens * 4)


# ── La fenetre vient du BACKEND, jamais d'un chiffre en dur ──────────────────

def test_the_window_comes_from_the_backend():
    assert generation_window(_Backend(128_000)) == 128_000


def test_it_falls_back_to_the_declared_hint():
    """Un backend sans `generation_context` (adaptateur tiers) doit quand meme
    etre garde : on retombe sur la fenetre declaree."""
    class _Vieux:
        context_window_hint = 32_000
    assert generation_window(_Vieux()) == 32_000


def test_a_mute_backend_gets_the_cautious_default():
    """Mieux vaut un avertissement de trop qu'un garde-fou qui ne garde rien."""
    assert generation_window(object()) == 8192
    assert generation_window(None) == 8192


def test_a_backend_that_raises_does_not_break_the_check():
    class _Rale:
        def generation_context(self):
            raise OSError("modele injoignable")
    assert generation_window(_Rale()) == 8192


def test_ollama_declares_what_it_really_allocates():
    """Source UNIQUE : `_call` lit `generation_context()`. Un garde-fou calcule
    sur un chiffre different de celui qui est alloue ne garderait rien."""
    src = (ROOT / "ui" / "ai_backends" / "ollama_backend.py").read_text(
        encoding="utf-8")
    assert '"num_ctx": self.generation_context(),' in src, (
        "le num_ctx alloue et la fenetre annoncee peuvent diverger")


def test_the_generation_budget_is_distinct_from_the_chat_one():
    """Le curseur de contexte de l'onglet IA pilote le CHAT. Il ne doit pas
    deplacer la fenetre de generation, qui a son propre num_ctx."""
    src = (ROOT / "ui" / "ai_backends" / "base.py").read_text(encoding="utf-8")
    assert "def generation_context" in src and "def effective_chat_context" in src


# ── Il parle quand il faut, et se tait le reste du temps ─────────────────────

def test_a_small_prompt_says_nothing():
    """C'est un avertissement, pas un compteur : un message a chaque
    generation apprend a etre ignore."""
    assert prompt_overflows(_texte(500), _texte(500), _Backend()) is None


def test_a_prompt_that_leaves_no_room_for_the_answer_speaks():
    """La sortie d'une generation EST du code : sans place pour repondre, le
    modele tronque — et le prompt, lui, sera peut-etre entre."""
    trop = prompt_overflows(_texte(4000), _texte(3000), _Backend())
    assert trop is not None
    assert trop["window"] == "8192"
    assert int(trop["tokens"]) == 7000
    assert trop["percent"] == "85"


def test_the_very_same_prompt_is_fine_on_a_cloud_model():
    """La limite depend du BACKEND, pas du mode ni du projet. Un modele cloud
    (128 k minimum) n'est pas concerne en pratique — et le message le dit en
    proposant d'y passer."""
    assert prompt_overflows(_texte(4000), _texte(3000),
                            _Backend(128_000)) is None


def test_the_measured_project_sizes_land_where_the_measure_said():
    """Ancre les chiffres du TODO. 24,3 caracteres par ligne, mesures sur les
    exemples du corpus ; on encadre plutot que d'affirmer au token pres."""
    sys_p = _texte(700)                      # prompt systeme, ordre de grandeur
    for lignes, doit_parler in ((120, False), (300, False), (1200, True)):
        code = _texte(int(lignes * 24.3 / 4))
        verdict = prompt_overflows(sys_p, code, _Backend())
        assert (verdict is not None) is doit_parler, (lignes, verdict)


def test_estimate_is_the_same_rule_of_three_used_all_along():
    assert estimate_tokens("x" * 400) == 100
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0


# ── Le message ───────────────────────────────────────────────────────────────

def test_the_message_is_translated_and_actionable():
    for code in LANGS:
        texte = getattr(TRANSLATIONS[code], "prompt_too_long", "")
        assert texte.strip(), code
        for champ in ("{percent}", "{tokens}", "{window}"):
            assert champ in texte, f"{code} : {champ} manquant"


def test_the_message_tells_what_to_do_not_just_that_it_is_big():
    """Un avertissement sans issue est du bruit. Les deux sorties reelles :
    generer fonctionnalite par fonctionnalite, ou passer sur un modele en
    ligne (128 k a 1 M, cf. providers.py)."""
    fr = TRANSLATIONS["fr"].prompt_too_long.lower()
    assert "fonctionnalité par fonctionnalité" in fr, fr
    assert "en ligne" in fr, fr


def test_both_generation_paths_are_wired():
    """Verrou par la source. Le mode n'est qu'un affichage : c'est la
    duplication de ce genre de garde qui avait fait diverger le chemin
    debutant en aout (QA G6)."""
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    assert "def _warn_if_prompt_overflows(" in src
    # DEUX appels : le chemin Regenerer/Ajouter/Modifier et le chemin debutant.
    # (La definition s'ecrit `def _warn...(self, …)` et ne compte donc pas ici :
    # mon premier jet attendait 3 et rougissait sur son propre comptage.)
    assert src.count("self._warn_if_prompt_overflows(") == 2, (
        src.count("self._warn_if_prompt_overflows("))


TESTS = [
    test_the_window_comes_from_the_backend,
    test_it_falls_back_to_the_declared_hint,
    test_a_mute_backend_gets_the_cautious_default,
    test_a_backend_that_raises_does_not_break_the_check,
    test_ollama_declares_what_it_really_allocates,
    test_the_generation_budget_is_distinct_from_the_chat_one,
    test_a_small_prompt_says_nothing,
    test_a_prompt_that_leaves_no_room_for_the_answer_speaks,
    test_the_very_same_prompt_is_fine_on_a_cloud_model,
    test_the_measured_project_sizes_land_where_the_measure_said,
    test_estimate_is_the_same_rule_of_three_used_all_along,
    test_the_message_is_translated_and_actionable,
    test_the_message_tells_what_to_do_not_just_that_it_is_big,
    test_both_generation_paths_are_wired,
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
