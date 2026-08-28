"""Assembles a list of features into a complete Arduino sketch (clean path).

Deterministic order: includes (deduplicated) -> globals -> setup() -> loop()
-> functions. 2-space indentation in setup()/loop().
"""
from __future__ import annotations

import re

from .feature_model import Feature, declared_name


# Idempotent INIT lines: re-emitting them is always redundant.
_INIT_RE = re.compile(r"\.begin\(|pinMode\(|\.attach\(")


def _code_sig(line: str) -> str:
    """Signature of a body line: the code without end-of-line comment nor
    spaces. Empty string if the line is a pure comment or empty. Used to compare
    lines by their CODE (the same call stays equal whether or not it carries an
    inline comment, or different spaces)."""
    code = line.split("//", 1)[0]
    return re.sub(r"\s+", "", code)


def _init_key(line: str) -> str | None:
    """Signature of the line if it is an idempotent init (`Serial.begin`,
    `pinMode`, `X.begin(`, `X.attach(`), insensitive to comments and spaces.
    None otherwise (the line is then never deduplicated as init)."""
    sig = _code_sig(line)
    return sig if (sig and _INIT_RE.search(sig)) else None


def _subtract_existing(lines: list[str], existing: set[str]) -> list[str]:
    """Removes from `lines` what the model RE-EMITTED of already-present content
    (code signatures in `existing`):

    - a duplicated idempotent INIT line → always removed (pointless re-init);
    - a duplicated NON-init line → removed only if it belongs to a contiguous
      BLOCK of ≥2 code lines all duplicated (= re-emission of a whole feature);
      an identical isolated line (e.g. a `delay(1000);` legitimately shared by
      two distinct features) is KEPT;
    - orphan comments just above a removed line go away with it.

    `existing` must NEVER contain the empty string (comments/blanks)."""
    n = len(lines)
    if not existing or n == 0:
        return list(lines)
    sig = [_code_sig(ln) for ln in lines]
    dup = [bool(sig[i]) and sig[i] in existing for i in range(n)]
    drop = [False] * n
    i = 0
    while i < n:
        if sig[i] and dup[i]:                       # start of a run of duplicated code
            j = i
            while j < n and sig[j] and dup[j]:
                j += 1
            run = range(i, j)
            # Brace-balance guard (bug 2026-07-06): a bare "}" carries the
            # trivial signature "}" and counts as duplicated code; dropping a
            # run that is NOT brace-balanced (e.g. [dup_body, "}"]) would leave
            # a feature's own "{" dangling -> broken sketch. Only remove runs
            # that open and close as many braces as they carry (whole
            # re-emitted blocks, or brace-free init/body lines).
            balanced = sum(lines[k].count("{") - lines[k].count("}")
                           for k in run) == 0
            if balanced and ((j - i) >= 2
                             or any(_init_key(lines[k]) is not None for k in run)):
                for k in run:
                    drop[k] = True
            i = j
        else:
            i += 1
    # Orphan header comments: a pure comment just above a removed line is removed
    # too (backward pass → collapses the chains).
    for i in range(n - 1, -1, -1):
        if (not drop[i] and sig[i] == "" and lines[i].lstrip().startswith("//")
                and i + 1 < n and drop[i + 1]):
            drop[i] = True
    return [lines[i] for i in range(n) if not drop[i]]


def clean_feature_contributions(feature: Feature,
                                existing: list[Feature]) -> Feature:
    """Returns a copy of `feature` keeping only its REAL novelty: we subtract
    what it RE-EMITS of `existing` (the model sometimes spits back the whole
    sketch instead of the delta). Used at the moment the feature is STORED, so
    that its content reflects only its own contributions — otherwise
    `resolve_feature_pins` and the « Modifier » label expose foreign pins/refs
    (e.g. a servo displayed with « PIN_LED » because it re-emitted the LED code).

    Same filter as the assembler/splicer: setup/loop via `_subtract_existing`
    (duplicated init + re-emitted blocks ≥2 lines; isolated lines kept), globals
    by already-declared identifier, already-present includes, functions of the
    same name."""
    setup_sigs = {s for f in existing for ln in f.setup_lines if (s := _code_sig(ln))}
    loop_sigs = {s for f in existing for ln in f.loop_lines if (s := _code_sig(ln))}
    g_names = {n for f in existing for g in f.global_lines
               if (n := declared_name(g)) is not None}
    inc_present = {inc.strip() for f in existing for inc in f.includes}
    fn_names = {fn.name for f in existing for fn in f.functions}
    return Feature(
        id=feature.id, prompt=feature.prompt, summary=feature.summary,
        prompts=list(feature.prompts),
        # Decisions of the USER, not model output: this function subtracts
        # re-emitted CODE, so it must carry them through untouched. Dropping
        # them silently undid every chip swap (QA B1, 2026-08-08).
        banned_lib_ids=list(feature.banned_lib_ids),
        forced_lib_ids=list(feature.forced_lib_ids),
        includes=[inc for inc in feature.includes
                  if inc.strip() not in inc_present],
        global_lines=[g for g in feature.global_lines
                      if declared_name(g) is None or declared_name(g) not in g_names],
        setup_lines=_subtract_existing(feature.setup_lines, setup_sigs),
        loop_lines=_subtract_existing(feature.loop_lines, loop_sigs),
        functions=[fn for fn in feature.functions if fn.name not in fn_names],
    )


def assemble_with_map(features: list[Feature]) -> "tuple[str, list[str | None]]":
    """assemble() + carte de propriétaires : pour CHAQUE ligne du sketch émis,
    l'id de la feature qui l'a produite, ou None (scaffolding : signatures
    setup/loop, accolades, lignes vides inter-blocs). Ligne dédupliquée →
    propriétaire = PREMIÈRE feature émettrice (même règle que _dedup /
    _dedup_globals / la dédup de fonctions par nom).

    Source de vérité du surlignage par fonctionnalité (#29) : la carte est
    exacte par construction, aucun marqueur IA nécessaire."""
    # Includes : même sémantique que _dedup sur la liste aplatie.
    inc_pairs: list[tuple[str, str]] = []
    seen_inc: set[str] = set()
    for f in features:
        for inc in f.includes:
            if inc not in seen_inc:
                seen_inc.add(inc)
                inc_pairs.append((inc, f.id))
    # Globals : même sémantique que _dedup_globals (dédup par identifiant
    # déclaré, lignes sans déclaration toujours conservées).
    glob_pairs: list[tuple[str, str]] = []
    seen_names: set[str] = set()
    for f in features:
        for g in f.global_lines:
            name = declared_name(g)
            if name is not None:
                if name in seen_names:
                    continue
                seen_names.add(name)
            glob_pairs.append((g, f.id))
    # Corps setup/loop : même sémantique que _merge_body_lines, en gardant
    # l'origine de chaque ligne conservée.
    def _merge_pairs(groups: "list[tuple[list[str], str]]") -> "list[tuple[str, str]]":
        seen: set[str] = set()
        out: list[tuple[str, str]] = []
        for lines, fid in groups:
            for ln in _subtract_existing(lines, seen):
                out.append((ln, fid))
            for ln in lines:
                s = _code_sig(ln)
                if s:
                    seen.add(s)
        return out
    setup_pairs = _merge_pairs([(f.setup_lines, f.id) for f in features])
    loop_pairs = _merge_pairs([(f.loop_lines, f.id) for f in features])
    # Fonctions dédupliquées par nom (1ère émettrice).
    func_blocks: list[tuple[str, str]] = []
    seen_fn: set[str] = set()
    for f in features:
        for fn in f.functions:
            if fn.name in seen_fn:
                continue
            seen_fn.add(fn.name)
            func_blocks.append((fn.code, f.id))

    # Émission texte + carte en parallèle. Blocs séparés par UNE ligne vide
    # (le "\n\n".join historique), propriétaire None.
    out_lines: list[str] = []
    owners: "list[str | None]" = []

    def emit(line: str, owner: "str | None") -> None:
        out_lines.append(line)
        owners.append(owner)

    def emit_block(pairs_or_lines, first_block: bool) -> None:
        if not first_block:
            emit("", None)          # séparateur inter-blocs
        for ln, fid in pairs_or_lines:
            emit(ln, fid)

    first = True
    if inc_pairs:
        emit_block(inc_pairs, first)
        first = False
    if glob_pairs:
        emit_block(glob_pairs, first)
        first = False
    # setup()
    if not first:
        emit("", None)
    first = False
    emit("void setup() {", None)
    for ln, fid in setup_pairs:
        emit("  " + ln, fid)
    emit("}", None)
    # loop()
    emit("", None)
    emit("void loop() {", None)
    for ln, fid in loop_pairs:
        emit("  " + ln, fid)
    emit("}", None)
    # fonctions : chaque bloc séparé par une ligne vide, TOUTES ses lignes
    # appartiennent à la feature porteuse.
    for code_block, fid in func_blocks:
        emit("", None)
        for ln in code_block.split("\n"):
            emit(ln, fid)
    # Fin de fichier : assemble() historique termine par "\n" -> le split
    # produit une dernière ligne vide, la carte doit la couvrir.
    emit("", None)
    return "\n".join(out_lines), owners


def assemble(features: list[Feature]) -> str:
    return assemble_with_map(features)[0]
