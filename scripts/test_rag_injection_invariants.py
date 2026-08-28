"""Reliability checks for the RAG bench's two characterization guards
(TODO #54, chantier A).

Not "invariants" in the sense of a property that never changes: the corpus
does NOT satisfy "no generic prompt ever injects" or "every named prompt gets
the imperative header" as of 2026-08-18 -- both guards below tolerate a known,
dated set of exceptions and fail if that set drifts in EITHER direction (a new
exception, or a fixed one nobody removed from the constant). A guard that
asserted raw scores would go red at every legitimate corpus change, which is
noise, and noise ends up disabled; a guard that claimed purity here would be a
docstring that lies. This file holds those two characterization guards plus
two checks on the RELIABILITY of the measurement itself (model availability,
corpus-example title forgery) that both guards depend on to mean anything.

Run : python scripts/test_rag_injection_invariants.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import bench_rag
import bench_rag_core as core
import ui.rag as rag
from ui import registry_lookup

BATTERY = ROOT / "scripts" / "bench_rag_prompts.json"

# ✅ VIDE DEPUIS LE 2026-08-26 -- et c'est la garde elle-meme qui l'a exige.
#
# Ce que la liste contenait, mesure a la tache 4 (2026-08-18) : deux prompts
# GENERIQUES -- aucun materiel nomme ni decrit, juste « affiche un compteur sur
# le moniteur serie » -- injectaient quand meme un afficheur 7 segments TM1637.
#
#   [es] "muestra un contador de segundos en el monitor serie"  -> TM1637, 0.537
#   [it] "mostra un contatore di secondi sul monitor seriale"   -> TM1637, 0.543
#
# Les tournures FR et EN de la MEME demande ne le declenchaient pas : ce
# n'etait donc pas une propriete de l'intention, mais du bruit d'embedding sur
# ces deux phrases precises.
#
# TODO #65 les a supprimees : plafonner la description a 64 tokens rend chaque
# empreinte plus nette, et ces deux scores passent SOUS le plancher de 0,50
# (0.537 -> 0.487 et 0.543 -> 0.495). Ce n'est pas un effet de bord heureux,
# c'est le mecanisme meme du correctif -- l'empreinte etant la MOYENNE des
# tokens, une longue description generique attirait des demandes generiques.
#
# ⚠️ La garde reste, et elle reste utile VIDE : elle echoue toujours dans les
# DEUX directions. Un prompt generique qui se remettrait a injecter devra etre
# ajoute ici en connaissance de cause, jamais masque.
KNOWN_GENERIC_INJECTIONS: set[tuple[str, str]] = set()

# Measured at task 6 (2026-08-18), REVISED at the final branch review (I3,
# 2026-08-18): of the 11 `named` prompts originally found under the HEDGED
# header, 4 (the NEO-6M ones) turned out to assert a FALSE fact about
# production and were removed from this set -- see the exclusion in
# `test_named_hedge_escapes_match_the_known_list` below for why. The 7
# remaining are real: the right library IS retrieved for all of them
# (`classify()` calls them "correct"), but the model reads it alongside
# "if NONE matches, IGNORE this section entirely", on a library it should be
# told to use without question -- exactly the regression the categorical
# authority of #37 is supposed to prevent, leaking through a LEXICAL trap.
#
# TWO remaining root causes, verified one at a time in `ui/rag.py`, neither of
# which this bench chantier is allowed to touch (no `ui/` edits):
#
#   - `keypad` : `_signature_tokens` is `{'keypad'}`, English only. The EN
#     prompt contains the literal word and passes; FR "clavier matriciel",
#     ES "teclado matricial", IT "tastiera matriciale" never do.
#   - `mhz19` : `_signature_tokens` is `{'mhz19', 'mhz19b', 'mhz19c', 'z19b',
#     'z19c'}` -- it wants a model suffix or the joined form. The prompts
#     write "MH-Z19" (hyphenated), which the tokenizer
#     (`re.findall(r"[a-z0-9]+", ...)`) splits into `{'mh', 'z19'}` -- bare
#     `z19` is not in the set. Affects all 4 languages (same spelling
#     everywhere).
#
# ✅ EMPTIED 2026-08-18 — TODO #56 is CLOSED, and this is the guard working as
# designed: it went red announcing the seven escapes had resolved, and the entry
# it asked to be removed is this whole set. Both causes were fixed in
# `ui/rag.py` (out of reach of the bench chantier, in scope once it had merged):
#
#   - `mhz19` : `_prompt_tokens` now also yields the JOINED form of hyphenated
#     runs, so « MH-Z19 » reads as `mhz19`. Fixed on the prompt side rather than
#     per-entry, the same normalisation `registry_lookup` already applied to
#     « ZXQ-9000 » -> `zxq9000` — so every hyphenated spelling benefits.
#   - `keypad` : `clavier`/`teclado`/`tastiera` added to
#     `_EXTRA_SIGNATURE_TOKENS`, the only available route (the regular filter
#     keeps tokens of >= 4 chars WITH a digit; no translation can satisfy it).
#
# Covered by `scripts/test_named_chip_lexicon.py`.
#
# KEEP THIS SET, EMPTY. It is not dead weight: an escape appearing tomorrow
# fails the guard by name, and re-deriving this whole apparatus from scratch is
# what the empty set spares. Do not delete it because it looks unused.
KNOWN_HEDGED_NAMED_PROMPTS: set[tuple[str, str]] = set()


def _cases(band):
    return [c for c in core.load_battery(BATTERY) if c["band"] == band]


def _require_valid_measurement() -> None:
    """Guard the two characterization tests below against a false "no more
    defects" reading when the model can't load at all.

    `retrieve_libs` swallows a load failure and returns `[]`, so a missing
    or desynced embeddings artifact makes `build_lib_context` return "" for
    EVERY case in the battery. Left unchecked, that reads as "nothing
    injects" to `test_generic_injections_match_the_known_list` (which would
    then order a maintainer to REMOVE the two known entries -- "bonne
    nouvelle, elles ne fautent plus") and as "every named prompt is muted" to
    `test_named_hedge_escapes_match_the_known_list` (a confusing failure that
    blames all 72 prompts instead of naming the real cause). Both are wrong
    conclusions drawn from an invalid measurement, and the second one
    destroys the only record of a real defect if acted on (C2, final review
    2026-08-18). `test_the_model_is_available` catches this too, but each
    guard checks for itself rather than depending on `TESTS` run order.
    """
    assert rag._load(), (
        "MESURE INVALIDE, RIEN A CONCLURE : " + bench_rag.diagnose_missing_model()
        + "\n  Tant que cette assertion echoue, NE RETIRER AUCUNE ENTREE des "
          "listes KNOWN_* ci-dessus : un contexte vide n'est pas une preuve "
          "que le defaut a disparu.")


def test_the_model_is_available():
    """Check this first, or the next two guards would lie.

    `retrieve_libs` swallows the loading failure and returns [] : without this
    test, a missing model would make the "generic" guard trivially true
    and the "named" guard false, which would send someone chasing a
    regression that does not exist.
    """
    assert rag._load(), (
        "MESURE INVALIDE : " + bench_rag.diagnose_missing_model())


def test_generic_injections_match_the_known_list():
    """Characterization guard, not a purity claim.

    The corpus does NOT satisfy "no generic prompt ever injects a library" as
    of 2026-08-18 -- two cases genuinely misfire (see KNOWN_GENERIC_
    INJECTIONS above). Pretending otherwise here would be a docstring that
    lies. So this test asserts a narrower, honest property: the set of
    generic prompts that inject beyond their `expect` is EXACTLY the known
    set, no more and no less. A third prompt joining the set is a new
    regression to investigate. One of the two known prompts falling silent
    is good news, but it still fails the test on purpose -- it means
    KNOWN_GENERIC_INJECTIONS has drifted out of date and must be trimmed by
    hand, not left as an exception nobody re-checks.
    """
    _require_valid_measurement()
    n2i = bench_rag._name_to_id()
    fautifs = set()
    for case in _cases("generic"):
        ctx = rag.build_lib_context(case["prompt"])
        if core.classify(ctx, case["expect"], n2i) == "wrong":
            fautifs.add((case["lang"], case["prompt"]))

    surprises = fautifs - KNOWN_GENERIC_INJECTIONS
    resolus = KNOWN_GENERIC_INJECTIONS - fautifs

    messages = []
    if surprises:
        messages.append(
            "nouveaux prompts generiques qui injectent (a ajouter a "
            "KNOWN_GENERIC_INJECTIONS seulement apres avoir confirme que "
            "c'est un constat reel, pas une regression a corriger) :\n  "
            + "\n  ".join(f"[{lg}] {p!r}" for lg, p in sorted(surprises)))
    if resolus:
        messages.append(
            "bonne nouvelle : ces prompts n'injectent plus a tort — retirer "
            "leur entree de KNOWN_GENERIC_INJECTIONS dans "
            "scripts/test_rag_injection_invariants.py :\n  "
            + "\n  ".join(f"[{lg}] {p!r}" for lg, p in sorted(resolus)))
    assert not messages, "\n".join(messages)


def test_named_hedge_escapes_match_the_known_list():
    """The categorical authority of #37, which nothing was testing -- and a
    characterization guard, not a purity claim, exactly like
    `test_generic_injections_match_the_known_list` above.

    `forced_libs` or `prompt_names_a_chip` => imperative header ; merely
    found by similarity => hedged header. We call with `forced_libs=None`,
    so it is `prompt_names_a_chip` that decides -- and a prompt from the
    `named` band SHOULD trigger it. As of 2026-08-18 it does not, for 7 of
    the 72 cases (see KNOWN_HEDGED_NAMED_PROMPTS above for the two root
    causes). A function named "...under_the_imperative_header" that silently
    tolerated 7 exceptions would be a docstring that lies, hence the rename.
    The property actually verified: no prompts are muted (a `named` prompt
    injecting nothing at all is a different, harder failure), and the set of
    `named` prompts served under the HEDGED header is EXACTLY the known set --
    no more (a new escape), no less (a fixed one, which must be removed from
    the constant by hand).

    LIMIT of this guard, which is exactly what produced the NEO-6M false
    alarm below (I3, final review 2026-08-18): it only ever measures
    `build_lib_context` called with `forced_libs=None` -- it is blind to
    whatever happens UPSTREAM of that call in the real app. Named prompts
    whose part number `registry_lookup.detect_unknown_part_tokens` flags as
    unknown to the corpus are therefore excluded from this measurement: in
    production they never reach a `forced_libs=None` call at all, because
    `studio_view`'s unknown-part-number pipeline sets `forced_libs` to a
    non-None list (found or empty) BEFORE generation, and `build_lib_
    context`'s `authoritative` flag is `forced_libs is not None` --
    imperative regardless of what `prompt_names_a_chip` says. Measuring them
    here would count a production non-issue as one of this guard's tracked
    defects.
    """
    _require_valid_measurement()
    muets, hedges = [], set()
    for case in _cases("named"):
        if registry_lookup.detect_unknown_part_tokens(case["prompt"]):
            # Rescued upstream by the registry-lookup pipeline in production
            # (see the docstring above) -- this exact call shape never
            # happens for these prompts outside this guard.
            continue
        ctx = rag.build_lib_context(case["prompt"])
        if not ctx.strip():
            muets.append((case["lang"], case["prompt"]))
        elif ctx.startswith(rag._HEDGED_HEADER):
            hedges.add((case["lang"], case["prompt"]))
    assert not muets, f"prompts nommes sans aucune injection : {muets}"

    surprises = hedges - KNOWN_HEDGED_NAMED_PROMPTS
    resolus = KNOWN_HEDGED_NAMED_PROMPTS - hedges

    messages = []
    if surprises:
        messages.append(
            "nouveaux prompts nommes servis sous en-tete HEDGE (a ajouter a "
            "KNOWN_HEDGED_NAMED_PROMPTS seulement apres avoir identifie la "
            "cause racine dans prompt_names_a_chip / _signature_tokens) :\n  "
            + "\n  ".join(f"[{lg}] {p!r}" for lg, p in sorted(surprises)))
    if resolus:
        messages.append(
            "bonne nouvelle : ces prompts nommes passent desormais sous "
            "en-tete IMPERATIF — retirer leur entree de "
            "KNOWN_HEDGED_NAMED_PROMPTS dans "
            "scripts/test_rag_injection_invariants.py (et fermer TODO #56 "
            "si la liste est vide) :\n  "
            + "\n  ".join(f"[{lg}] {p!r}" for lg, p in sorted(resolus)))
    assert not messages, "\n".join(messages)


def test_characterization_guards_refuse_to_conclude_without_a_valid_measurement():
    """C2 (final review 2026-08-18): a load failure must read as an invalid
    measurement, never as good news.

    Monkeypatches `rag._load` to simulate exactly what a missing/desynced
    ONNX artifact does to `build_lib_context` (silently return "" for every
    case), and checks that BOTH characterization guards refuse to conclude
    anything: each must fail (never pass in silence) with a message that
    names the measurement as invalid and never says "bonne nouvelle" --
    the exact phrase both guards use to recommend trimming a KNOWN_* entry,
    which must never be triggered by an unavailable model.
    """
    original = rag._load
    rag._load = lambda: False
    try:
        for guard in (test_generic_injections_match_the_known_list,
                      test_named_hedge_escapes_match_the_known_list):
            try:
                guard()
            except AssertionError as e:
                msg = str(e)
                assert "invalide" in msg.lower(), (
                    f"{guard.__name__} doit nommer la mesure comme invalide "
                    f"quand le modele est indisponible : {msg}")
                assert "bonne nouvelle" not in msg.lower(), (
                    f"{guard.__name__} ne doit JAMAIS conclure a une bonne "
                    f"nouvelle quand la mesure elle-meme est invalide : {msg}")
            else:
                raise AssertionError(
                    f"{guard.__name__} doit echouer quand le modele est "
                    f"indisponible, pas passer en silence")
    finally:
        rag._load = original


def test_every_expect_names_a_real_corpus_id():
    """I4 (final review 2026-08-18): a typo'd `expect` would count `wrong`
    forever, inflating the one number this bench asks you to watch, with
    nothing to catch it -- `battery_drift` guards a wrong PROMPT slipping in
    unnoticed, nothing guarded the EXPECT side until now. Runs against the
    real corpus; needs no ONNX model, only `corpus.json`.
    """
    n2i = bench_rag._name_to_id()
    problems = core.validate_expect_ids(
        core.load_battery(BATTERY), set(n2i.values()))
    assert not problems, "\n".join(problems)


def test_no_corpus_example_forges_a_block_title():
    """The parsing of injected libraries reads `### ` lines.

    If a corpus `example_code` contained such a line, it would forge a
    phantom injection and skew every measurement. Verified empty on
    2026-08-18 ; this test keeps a future corpus addition from making it
    false.
    """
    coupables = [e["id"] for e in rag.all_corpus_entries()
                 if re.search(r"(?m)^###\s", e.get("example_code") or "")]
    assert not coupables, (
        f"ces entrees corpus contiennent une ligne '### ' : {coupables}")


TESTS = [
    test_the_model_is_available,
    test_generic_injections_match_the_known_list,
    test_named_hedge_escapes_match_the_known_list,
    test_characterization_guards_refuse_to_conclude_without_a_valid_measurement,
    test_every_expect_names_a_real_corpus_id,
    test_no_corpus_example_forges_a_block_title,
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
