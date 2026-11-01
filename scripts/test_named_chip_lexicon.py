"""A named component must be recognised as named (TODO #56).

Found by `scripts/test_rag_injection_invariants.py`: 7 prompts out of 72 in the
bench battery spelled their part out in full, the right library WAS retrieved,
and yet they were served under the HEDGED header -- the model being told « if
NONE matches, IGNORE this section entirely » about the very library it should
follow. That is the gap #37's categorical authority exists to close:
`forced_libs` or `prompt_names_a_chip` => imperative header, merely retrieved
=> hedged one.

Two root causes, measured on 2026-08-18:

1. « MH-Z19 » tokenises to `mh` + `z19`. The corpus entry knows `mhz19`,
   `mhz19b`, `mhz19c`, `z19b`, `z19c` -- but never bare `z19`. Fixed on the
   PROMPT side by also generating the joined form of hyphenated runs, exactly
   what `registry_lookup.detect_unknown_part_tokens` already does for
   « ZXQ-9000 » -> `zxq9000`. General rather than per-entry: people write part
   numbers with or without their hyphen, and joining only ADDS tokens.
2. `keypad` had one signature token, in English. FR « clavier », ES « teclado »
   and IT « tastiera » never contain it. Fixed by `_EXTRA_SIGNATURE_TOKENS`,
   the only route available: `_signature_tokens` keeps tokens of >= 4 chars
   WITH a digit, so no accented-free translation could ever get through, and
   `prompt_names_a_chip` intersects SINGLE tokens, so a multi-word expression
   could not match either.

⚠️ LE POINT 2 A CHANGE LE 2026-08-26. Les jetons du `keypad` sont passes de
« clavier / teclado / tastiera » a « matriciel / matricial / matriciale /
tastierino ». Raison : #60 a ajoute au corpus trois autres claviers -- `mpr121`
(tactile capacitif), `bluefruit_le` (BLE) et `trellis` (grille de boutons) --
donc le mot vague ne designait plus une seule chose, et « gerer un clavier
tactile capacitif » etait servi `keypad` SEUL sous en-tete imperatif. Les
quatre prompts `keypad` du banc gardent leur en-tete ; le mot vague, lui,
n'affirme plus rien. Voir `test_an_ambiguous_keyboard_word_no_longer_names_a_
chip`.

Run : python scripts/test_named_chip_lexicon.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.rag as rag

# The seven prompts of the bench battery that this ticket is about, verbatim.
# `keypad` and `mhz19` only -- the four NEO-6M ones were requalified out at the
# 2026-08-18 branch review: an unknown part token routes them through the
# out-of-corpus pipeline, which forces `forced_libs` to a list, so their header
# is imperative in production whatever `prompt_names_a_chip` answers.
SEPT_PROMPTS = [
    "lire un clavier matriciel 4x4",
    "leer un teclado matricial 4x4",
    "leggere una tastiera matriciale 4x4",
    "lire un capteur de CO2 NDIR MH-Z19",
    "read NDIR CO2 sensor MH-Z19",
    "leer sensor de CO2 NDIR MH-Z19",
    "leggere sensore di CO2 NDIR MH-Z19",
]


def test_the_seven_prompts_are_recognised_as_naming_a_component():
    rates = [p for p in SEPT_PROMPTS if not rag.prompt_names_a_chip(p)]
    assert not rates, (
        "ces prompts nomment leur composant en toutes lettres et doivent "
        f"declencher l'en-tete imperatif : {rates}"
    )


def test_a_hyphenated_part_number_is_joined():
    """« MH-Z19 » must read as `mhz19`, like ZXQ-9000 reads as `zxq9000`."""
    assert rag.prompt_names_a_chip("mesure le CO2 avec un MH-Z19")
    # The un-hyphenated spelling already worked; it must keep working.
    assert rag.prompt_names_a_chip("mesure le CO2 avec un MHZ19")


def test_joining_generalises_beyond_this_one_entry():
    """The fix is on the prompt side, so any hyphenated spelling benefits."""
    assert rag.prompt_names_a_chip("lis un capteur DHT-22")
    assert rag.prompt_names_a_chip("affiche sur un ecran SSD-1306")


def test_the_keypad_translations_are_known():
    """Les traductions du PAVE MATRICIEL declenchent l'en-tete imperatif.

    ⚠️ Ce test affirmait, jusqu'au 2026-08-26, que « clavier », « teclado » et
    « tastiera » suffisaient. C'etait le contrat de #56, vrai sur un corpus de
    91 entrees ou `keypad` etait le SEUL clavier. #60 l'a perime en ajoutant
    `mpr121` (clavier tactile), `bluefruit_le` (clavier BLE) et `trellis`
    (grille de boutons) : le mot ne designe plus une seule chose, et « gerer un
    clavier tactile capacitif » etait servi `keypad` SEUL sous en-tete
    imperatif.

    Le contrat est donc devenu PRECIS. Voir la moitie negative juste en
    dessous : c'est elle qui porte le correctif."""
    for mot in ("clavier matriciel", "teclado matricial",
                "tastiera matriciale", "tastierino"):
        assert rag.prompt_names_a_chip(f"lire un {mot}"), mot


def test_an_ambiguous_keyboard_word_no_longer_names_a_chip():
    """LA moitie qui compte : le mot vague ne doit PLUS rien affirmer.

    Depuis #60 le corpus contient quatre « claviers » differents. Traiter
    « clavier » comme le nom d'une puce revenait a servir `keypad` avec
    autorite a quelqu'un qui decrivait un MPR121 ou un module Bluetooth.

    Mesure du 2026-08-26 : « un clavier bluetooth pour mon telephone »
    remontait `keypad` DEVANT `bluefruit_le` ; il remonte desormais
    `bluefruit_le` seul."""
    for mot in ("clavier", "teclado", "tastiera"):
        assert not rag.prompt_names_a_chip(f"lire un {mot}"), mot


def test_a_prompt_that_names_nothing_stays_unnamed():
    """The counterpart that makes the whole thing worth anything.

    Joining only ADDS tokens, so the risk is a false positive. A prompt with no
    component name must still answer False -- otherwise every vague request
    would get the imperative header, which is exactly the #37 regression in
    reverse.
    """
    for p in ("fais clignoter une led", "affiche bonjour sur le moniteur serie",
              "fais un scanner i2c", "un chronometre qui compte les secondes"):
        assert not rag.prompt_names_a_chip(p), p


def test_a_hyphen_between_two_plain_words_invents_nothing():
    """« marche-arret » must not become a part number by being joined."""
    assert not rag.prompt_names_a_chip("un bouton marche-arret")
    assert not rag.prompt_names_a_chip("un capteur tout-ou-rien")


def test_the_boost_and_the_header_read_the_same_tokens():
    """Both must see the joined form, or the two would disagree.

    `prompt_names_a_chip` decides the header, `retrieve_libs` applies the
    lexical boost. If only one of them joined hyphens, a component named with a
    hyphen would be served authoritatively without being boosted -- or boosted
    without authority. Same helper, so same answer.

    Asserts the boost is actually APPLIED, not merely that the right entry wins:
    on this prompt `mhz19` already came top-1 by similarity alone, so a test
    that only checked the ranking would pass without the fix and prove nothing.
    """
    if not rag._load():
        return          # encoder unavailable: the header half is tested above
    prompt = "mesure le CO2 avec un MH-Z19"
    libs = rag.retrieve_libs(prompt, k=3, threshold=rag._CODEGEN_MIN_SCORE)
    assert libs, "un composant nomme doit franchir le plancher"
    assert libs[0].get("id") == "mhz19", [l.get("id") for l in libs]

    # Raw cosine similarity of the same entry, boost excluded.
    idx = next(i for i, e in enumerate(rag._corpus) if e["id"] == "mhz19")
    brut = float(rag._embeddings[idx] @ rag.encode([prompt])[0])
    ecart = libs[0]["_score"] - brut
    assert abs(ecart - rag._LEXICAL_BOOST) < 1e-4, (
        f"le boost lexical doit s'appliquer sur la forme jointe : ecart mesure "
        f"{ecart:.4f}, attendu {rag._LEXICAL_BOOST}"
    )


TESTS = [
    test_the_seven_prompts_are_recognised_as_naming_a_component,
    test_a_hyphenated_part_number_is_joined,
    test_joining_generalises_beyond_this_one_entry,
    test_the_keypad_translations_are_known,
    test_an_ambiguous_keyboard_word_no_longer_names_a_chip,
    test_a_prompt_that_names_nothing_stays_unnamed,
    test_a_hyphen_between_two_plain_words_invents_nothing,
    test_the_boost_and_the_header_read_the_same_tokens,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} test(s) au vert")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
