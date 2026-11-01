"""Pure core of the RAG bench: schema, case identity, outcome classification
and baseline deltas.

Imports NOTHING heavy on purpose -- no `ui.rag`, no numpy, no onnxruntime at
module level. The ONNX model weighs 470 MB and is git-ignored, so anything that
can only be tested by loading it would end up tested by nobody. `bench_rag.py`
does the loading; this module does the thinking.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BANDS = ("generic", "described", "named")
SPECIFICITIES = ("specific", "vague")
LANGS = ("fr", "en", "es", "it")

_REQUIRED = ("prompt", "lang", "band", "expect", "added", "source")


def validate_case(case: dict) -> list[str]:
    """Return the list of problems with one battery case; empty means valid.

    Returns problems rather than raising so a whole battery can be reported at
    once: fixing a data file one exception at a time is miserable.
    """
    problems: list[str] = []
    for field in _REQUIRED:
        if field not in case:
            problems.append(f"champ obligatoire manquant : {field}")
    if problems:
        return problems

    if not str(case["prompt"]).strip():
        problems.append("prompt vide")
    if case["lang"] not in LANGS:
        problems.append(
            f"lang invalide : {case['lang']!r} (attendu {LANGS}, en minuscules)")
    if case["band"] not in BANDS:
        problems.append(f"band invalide : {case['band']!r} (attendu {BANDS})")
    if not isinstance(case["expect"], list):
        problems.append("expect doit etre une LISTE, meme a un seul element")

    # `specificity` splits the described band by how precise the wording is --
    # the axis that produced 3/10 on vague prompts and 80% on specific ones.
    # It is meaningless on the other bands, so its presence there is a mistake
    # worth reporting rather than ignoring.
    has_spec = "specificity" in case
    if case["band"] == "described":
        if not has_spec:
            problems.append("specificity obligatoire sur la bande described")
        elif case["specificity"] not in SPECIFICITIES:
            problems.append(
                f"specificity invalide : {case['specificity']!r}")
    elif has_spec:
        problems.append(
            f"specificity interdite sur la bande {case['band']!r}")
    return problems


def case_identity(case: dict) -> tuple[str, str]:
    """Stable identity of a case: (prompt, lang).

    Not the index -- it shifts on any insertion. Not the prompt alone -- the
    same sentence can legitimately exist in two languages ("scanner i2c").
    """
    return (case["prompt"], case["lang"])


def load_battery(path: str | Path) -> list[dict]:
    """Read and validate a battery file. Raises ValueError on any problem.

    A half-read battery would produce silently wrong deltas, so this refuses
    to return anything at all when a single case is malformed.
    """
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: la batterie doit etre une LISTE de cas")
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for i, case in enumerate(raw):
        for problem in validate_case(case):
            errors.append(f"cas #{i}: {problem}")
        if isinstance(case, dict) and "prompt" in case and "lang" in case:
            ident = case_identity(case)
            if ident in seen:
                errors.append(f"cas #{i}: doublon d'identite {ident}")
            seen.add(ident)
    if errors:
        raise ValueError(f"{path} invalide :\n  " + "\n  ".join(errors))
    return raw


# `rag._render_lib_block` writes `f"### {name}"` as the first line of each
# injected block, so the block titles ARE the injected library names.
# Verified 2026-08-18: no corpus `example_code` contains a line starting with
# "### ", so a fenced code block cannot forge one. `test_no_corpus_example_
# forges_a_block_title` (task 6) keeps that true.
_BLOCK_TITLE = re.compile(r"(?m)^###[ \t]+(.+?)[ \t]*$")


def injected_names(context: str) -> list[str]:
    """Names of the libraries injected into a generation context."""
    return _BLOCK_TITLE.findall(context or "")


def resolve_to_ids(names: list[str], name_to_id: dict[str, str]) -> list[str]:
    """Map injected names onto corpus ids, keeping unknown names as-is.

    Keeping the raw name is not a fallback for errors -- it is the Wire case:
    `_WIRE_I2C_SCANNER_REF` has no `id` key at all, only a `name`, because it
    is a core library that lives outside the corpus.
    """
    return [name_to_id.get(n, n) for n in names]


def classify(context: str, expect: list[str],
             name_to_id: dict[str, str]) -> str:
    """One of "correct" | "silent" | "wrong".

    Three outcomes rather than pass/fail: a binary would put "nothing was
    injected" and "the wrong library was injected" in the same bucket, while
    the project's doctrine says the opposite -- silence is acceptable,
    falsehood is not. The number to watch is the WRONG rate, not the success
    rate.
    """
    if not (context or "").strip():
        return "silent"
    injected = set(resolve_to_ids(injected_names(context), name_to_id))
    return "correct" if injected & set(expect) else "wrong"


OUTCOMES = ("correct", "silent", "wrong")


def band_label(case: dict) -> str:
    """Reporting band: `described` is split by specificity, the others are not.

    That split is not cosmetic: vague and specific wordings measured 3/10 and
    80% on the same mechanism, so merging them would average away the only
    distinction that matters.
    """
    if case["band"] == "described":
        return f"described/{case['specificity']}"
    return case["band"]


def summarize(results: list[dict]) -> dict:
    """{band_label: {lang|'_all': {outcome: count}}}."""
    out: dict = {}
    for r in results:
        per_lang = out.setdefault(r["band_label"], {})
        for key in ("_all", r["lang"]):
            counts = per_lang.setdefault(key, {o: 0 for o in OUTCOMES})
            counts[r["outcome"]] += 1
    return out


def resolve_expected(substring: str, corpus_ids: list[str]) -> list[str]:
    """Turn one legacy expected SUBSTRING into real corpus ids.

    `smoke_test_rag_multilingual.py` stores substrings, not ids, and they are
    ambiguous: "sd" is contained in `adafruit-ssd1306`, `sd` and `ssd1351`;
    "stepper" in `accelstepper`, `stepper` and `stepper_28byj48`. A naive
    substring migration would build false `expect` lists, hence undeserved
    "correct" verdicts -- so an exact id always wins.

    Raises ValueError when nothing matches: a substring resolving to nothing
    is a migration error, and swallowing it would silently drop a case.
    """
    needle = substring.lower()
    exact = [i for i in corpus_ids if i.lower() == needle]
    if exact:
        return exact
    loose = [i for i in corpus_ids if needle in i.lower()]
    if not loose:
        raise ValueError(
            f"la sous-chaine {substring!r} ne resout vers aucun id du corpus")
    return loose


def battery_drift(baseline_ids, current_ids) -> tuple[list, list]:
    """(additions, removals) between a frozen battery and the current one.

    Reported BEFORE any delta: comparing term by term across a changed battery
    is meaningless. And a bench that hid a removal would allow exactly the
    cheat it exists to prevent -- dropping the prompt that turned red.
    """
    base = {tuple(i) for i in baseline_ids}
    cur = {tuple(i) for i in current_ids}
    return (sorted(cur - base), sorted(base - cur))


def format_deltas(current: dict, baseline: dict) -> list[str]:
    """Human-readable before/after lines, one per reporting band.

    The delta is the authoritative output: on a FROZEN sample the sampling bias
    is a constant, so it cancels out in the difference. A biased bench still
    yields a true delta.
    """
    lines: list[str] = []
    for band in sorted(set(current) | set(baseline)):
        cur = current.get(band, {}).get("_all", {})
        old = baseline.get(band, {}).get("_all", {})
        parts = []
        for outcome in OUTCOMES:
            a, b = old.get(outcome, 0), cur.get(outcome, 0)
            mark = "=" if a == b else f"{b - a:+d}"
            parts.append(f"{outcome} {a:3d} → {b:3d} ({mark})")
        # Only WRONG carries the warning: a drop in `correct` that becomes
        # `silent` is a loss of coverage, never a wrong sketch.
        worse = cur.get("wrong", 0) > old.get("wrong", 0)
        lines.append(f"{band:20} " + "   ".join(parts) + ("   ⚠" if worse else ""))
    return lines


# ── C1 (final review 2026-08-18): baseline schema, restricted to common cases ──
#
# The old baseline stored only aggregate `cases`/`summary`/`ceiling` -- no
# issue per case. Deltas could therefore only ever be totals over whatever the
# CURRENT battery happens to contain: removing a case that used to be `wrong`
# silently dropped it from both sides of the "after" total, which reads as an
# improvement (`wrong -1`) obtained by erasing the finding. The fix is a
# schema change (per-case `results`, one that lets both sides be restricted to
# their intersection before being re-summarized), not a filter bolted onto the
# old shape -- hence the version key: an old-shape baseline must be refused
# with a clear message, not misread as if it had `results`.

SCHEMA_VERSION = 2


def check_baseline_schema(baseline: dict) -> None:
    """Raise ValueError when a baseline predates the per-case schema.

    A baseline written before `SCHEMA_VERSION` has no `results` key at all
    (aggregate `summary` only) -- reading it as the new shape would either
    KeyError far from here or silently compare against an empty per-case set.
    Refusing loudly here, with the fix spelled out, is cheaper than either.
    """
    version = baseline.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"reference obsolete (schema_version={version!r}, attendu "
            f"{SCHEMA_VERSION}) : regele-la avec python scripts/bench_rag.py "
            f"--freeze")


def common_identities(a, b) -> set[tuple[str, str]]:
    """(prompt, lang) identities present on BOTH sides.

    The only population a delta may honestly be computed over -- comparing
    raw totals across two different populations is exactly what let a removed
    case read as an improvement.
    """
    return {tuple(i) for i in a} & {tuple(i) for i in b}


def restrict_to_common(results: list[dict], identities) -> list[dict]:
    """Keep only the results whose (prompt, lang) identity is in `identities`.

    `identities` accepts anything iterable of `(prompt, lang)` pairs --
    typically the output of `common_identities`.
    """
    idset = {tuple(i) for i in identities}
    return [r for r in results if (r["prompt"], r["lang"]) in idset]


def max_ceiling(by_case: dict, identities) -> float:
    """Highest score among `by_case` entries whose identity is in `identities`.

    0.0 (never a crash) when nothing matches -- an empty intersection is a
    legitimate outcome (e.g. every generic prompt got renamed at once), not
    an error worth raising here.
    """
    idset = {tuple(i) for i in identities}
    vals = [v for k, v in by_case.items() if tuple(k) in idset]
    return max(vals) if vals else 0.0


def format_ceiling_deltas(current: dict, baseline: dict) -> list[str]:
    """Per-case before/after lines for the generic-band noise ceiling.

    I1 (final review 2026-08-18): a single global max is blind to 11 of the
    12 generic prompts -- an entry that pushed ONE prompt's score past the
    floor would leave the reported max unchanged as long as a different
    prompt already held it. Same "restrict to common, then diff every case"
    doctrine as `format_deltas`, at the grain the ceiling actually needs.
    Callers are expected to have already restricted both dicts to the cases
    they want compared (e.g. via `max_ceiling`'s `identities` argument).
    """
    lines: list[str] = []
    for prompt, lang in sorted(set(current) | set(baseline)):
        a = baseline.get((prompt, lang), 0.0)
        b = current.get((prompt, lang), 0.0)
        mark = "=" if abs(a - b) < 1e-9 else f"{b - a:+.3f}"
        lines.append(f"    [{lang}] {prompt[:48]:48} {a:.3f} → {b:.3f} ({mark})")
    return lines


# ── I2 (final review 2026-08-18): libraries injected alongside the right one ──

def stray_libs(context: str, expect: list[str],
                name_to_id: dict[str, str]) -> list[str]:
    """Injected ids that are NOT in `expect`, regardless of the case outcome.

    `classify` only asks "is at least one expected id present" -- a `correct`
    verdict says nothing about what ELSE rode along. Measured 2026-08-18:
    32/164 cases inject 2-3 libs, and the 143 `correct` cases alone carry 48
    ids outside their own `expect`. A new corpus entry climbing into 2nd/3rd
    position under the relative_gate moves NONE of the three `classify`
    outcomes -- this is the number that does.
    """
    injected = resolve_to_ids(injected_names(context), name_to_id)
    return [i for i in injected if i not in expect]


def stray_summary(results: list[dict]) -> dict:
    """{"cases": N, "ids": N} over `results` -- how many cases carry at least
    one stray (unexpected) injected id, and how many stray ids in total.
    Each result needs a "stray" key, as produced alongside "outcome" by
    `bench_rag.measure`."""
    cases = sum(1 for r in results if r.get("stray"))
    ids = sum(len(r.get("stray", [])) for r in results)
    return {"cases": cases, "ids": ids}


# ── I5 (final review 2026-08-18): the name -> id map is a bijection, guarded ──

def name_to_id_map(entries: list[dict]) -> dict[str, str]:
    """The name -> id map `classify`/`resolve_to_ids` run on.

    Stays permissive on a collision on purpose -- `name_collisions` below is
    the actual guard; refusing to build a map here would take down every
    OTHER id's resolution over a single bad one.
    """
    return {e["name"]: e["id"] for e in entries if e.get("name") and e.get("id")}


def name_collisions(entries: list[dict]) -> dict[str, list[str]]:
    """{name: [ids, ...]} for every corpus name shared by 2+ ids.

    `name_to_id_map` is a dict comprehension: a collision would silently let
    the LAST id win, and every case that injects the shadowed id would
    misread as `wrong`, or `correct` for the wrong reason. Empty means the
    map used throughout the bench is a true bijection.
    """
    by_name: dict[str, list[str]] = {}
    for e in entries:
        if e.get("name") and e.get("id"):
            by_name.setdefault(e["name"], []).append(e["id"])
    return {n: ids for n, ids in by_name.items() if len(ids) > 1}


# ── I4 (final review 2026-08-18): `expect` must name a real id ──

_SPECIAL_EXPECTED_IDS = {"Wire (I2C core library)"}


def validate_expect_ids(cases: list[dict], known_ids) -> list[str]:
    """Report any `expect` entry naming neither a real corpus id nor a
    documented special id.

    `battery_drift` guards a wrong PROMPT slipping into the battery
    unnoticed; nothing guarded a wrong EXPECT, which would count `wrong`
    forever and inflate the one number this bench asks you to watch, without
    ever being caught.

    `_SPECIAL_EXPECTED_IDS` covers `_WIRE_I2C_SCANNER_REF`, whose entry has a
    `name` but deliberately no corpus `id` (see `resolve_to_ids`'s Wire case)
    -- it can never appear in `known_ids`.
    """
    allowed = set(known_ids) | _SPECIAL_EXPECTED_IDS
    problems: list[str] = []
    for i, case in enumerate(cases):
        for eid in case.get("expect", []):
            if eid not in allowed:
                problems.append(
                    f"cas #{i} ({case.get('prompt')!r}): expect {eid!r} ne "
                    f"correspond a aucun id de corpus connu")
    return problems
