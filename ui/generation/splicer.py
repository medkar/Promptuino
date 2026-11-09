"""Inserts/replaces the contributions of a feature in the current editor text,
by CONTENT ANCHORS (never line numbers). Preserves the existing code word-for-
word. Raises SpliceError if an anchor cannot be found.
"""
from __future__ import annotations

from .assembler import _code_sig, _subtract_existing
from .brace_utils import find_function_body
from .feature_model import (
    Feature, declared_name, statement_names, _LITERAL_RE,
)
from .sketch_parser import parse_sketch, SketchParseError


class SpliceError(Exception):
    """Anchor not found (setup/loop or target function absent)."""


def _existing_global_names(code: str) -> set[str]:
    """Global identifiers already declared in `code` (best-effort via the parser)
    — so as not to re-insert an already-present global."""
    try:
        parsed = parse_sketch(code)
    except SketchParseError:
        return set()
    names: set[str] = set()
    for n in statement_names(parsed.global_lines):
        if n:
            names.add(n)
    return names


def _insert_into_body(code: str, func_name: str, lines: list[str]) -> str:
    """Inserts `lines` (indented 2 spaces) just before the closing '}' of
    `func_name`. Raises SpliceError if the function is absent."""
    if not lines:
        return code
    span = find_function_body(code, func_name)
    if span is None:
        raise SpliceError(f"fonction '{func_name}' introuvable")
    _, body_start, body_end, _ = span
    body = code[body_start:body_end]
    addition = "".join("  " + ln + "\n" for ln in lines)
    # We insert after the existing content, before the '}'. We guarantee a \n.
    if body and not body.endswith("\n"):
        body = body + "\n"
    new_body = body + addition
    return code[:body_start] + new_body + code[body_end:]


def _insert_includes(code: str, includes: list[str]) -> str:
    if not includes:
        return code
    block = "\n".join(includes) + "\n"
    return block + code


def _insert_globals(code: str, globals_: list[str]) -> str:
    """Inserts the globals just before the definition of setup()."""
    if not globals_:
        return code
    span = find_function_body(code, "setup")
    if span is None:
        raise SpliceError("setup() introuvable pour insérer les globals")
    sig_start = span[0]
    block = "\n".join(globals_) + "\n\n"
    return code[:sig_start] + block + code[sig_start:]


def _existing_body_sigs(code: str, func_name: str) -> set[str]:
    """Code signatures (without comment nor spaces) already present in the body
    of `func_name`. Empty if the function is absent."""
    span = find_function_body(code, func_name)
    if span is None:
        return set()
    _, body_start, body_end, _ = span
    return {s for ln in code[body_start:body_end].split("\n")
            if (s := _code_sig(ln))}


def splice_add(current_code: str, feature: Feature) -> str:
    """Adds the contributions of `feature` to `current_code`.

    Filters duplicate declarations (the model may re-emit already-present globals
    / includes / functions): we do not re-insert an include already there, nor a
    global whose identifier is already declared, nor a function of the same name.
    Also subtracts from the setup()/loop() lines what the model RE-EMITS of the
    existing code (duplicated init + whole re-emitted blocks), via
    `_subtract_existing` — same net as the assembler.
    """
    if find_function_body(current_code, "setup") is None or \
       find_function_body(current_code, "loop") is None:
        raise SpliceError("setup()/loop() introuvables")
    existing_names = _existing_global_names(current_code)
    new_includes = [inc for inc in feature.includes if inc.strip() not in current_code]
    new_globals = [g for g, n in zip(feature.global_lines,
                                     statement_names(feature.global_lines))
                   if n is None or n not in existing_names]
    code = _insert_includes(current_code, new_includes)
    code = _insert_globals(code, new_globals)
    new_setup = _subtract_existing(feature.setup_lines,
                                   _existing_body_sigs(code, "setup"))
    new_loop = _subtract_existing(feature.loop_lines,
                                  _existing_body_sigs(code, "loop"))
    code = _insert_into_body(code, "setup", new_setup)
    code = _insert_into_body(code, "loop", new_loop)
    for fn in feature.functions:
        if find_function_body(code, fn.name) is not None:
            continue          # function of the same name already present -> we skip
        code = code.rstrip() + "\n\n" + fn.code + "\n"
    return code


def _remove_function(code: str, name: str) -> str:
    span = find_function_body(code, name)
    if span is None:
        raise SpliceError(f"fonction '{name}' introuvable pour suppression")
    sig_start, _, _, end = span
    # Also removes the residual blanks around it.
    before = code[:sig_start].rstrip("\n")
    after = code[end:].lstrip("\n")
    sep = "\n\n" if before and after else ("\n" if (before or after) else "")
    return before + sep + after


def _remove_lines_from_body(code: str, func_name: str, lines: list[str]) -> str:
    """Removes from `func_name` the lines whose stripped content matches `lines`."""
    if not lines:
        return code
    span = find_function_body(code, func_name)
    if span is None:
        raise SpliceError(f"fonction '{func_name}' introuvable")
    _, body_start, body_end, _ = span
    body = code[body_start:body_end]
    body_lines = body.split("\n")
    old_seq = [ln.strip() for ln in lines if ln.strip()]
    nonblank = [i for i, ln in enumerate(body_lines) if ln.strip()]
    stripped = [body_lines[i].strip() for i in nonblank]
    n = len(old_seq)
    drop: set[int] = set()
    # 1. Le bloc de l'ancienne fonctionnalite est CONTIGU dans le corps (c'est
    #    ainsi que l'assembleur l'a pose) : on retire CETTE suite-la. Retirer
    #    toute ligne de meme texte emportait les `delay(1000);` et les `}` des
    #    AUTRES fonctionnalites, en silence.
    if n:
        for k in range(len(stripped) - n + 1):
            if stripped[k:k + n] == old_seq:
                drop = {nonblank[k + j] for j in range(n)}
                break
    # 2. Suite rompue (retouche a la main au milieu) : repli, mais chaque
    #    ligne ne part qu'autant de fois que l'ancienne fonctionnalite l'a.
    if not drop:
        budget: dict[str, int] = {}
        for ln in old_seq:
            budget[ln] = budget.get(ln, 0) + 1
        for i, ln in enumerate(body_lines):
            t = ln.strip()
            if budget.get(t, 0) > 0:
                budget[t] -= 1
                drop.add(i)
    kept = [ln for i, ln in enumerate(body_lines) if i not in drop]
    new_body = "\n".join(kept)
    return code[:body_start] + new_body + code[body_end:]


def _remove_global_statements(code: str, names: set[str]) -> str:
    """Retire du code les enonces globaux (niveau 0) qui declarent un des
    `names` -- multi-ligne compris. Sert a `splice_replace` : sans cela,
    `splice_add` saute la nouvelle globale (« deja declaree ») et une
    modification de VALEUR (changer de broche) n'etait jamais appliquee."""
    if not names:
        return code
    lines = code.split("\n")
    drop: set[int] = set()
    depth = 0
    skipping = False
    for i, ln in enumerate(lines):
        if depth == 0:
            skipping = declared_name(ln) in names
        if skipping:
            drop.add(i)
        c = _LITERAL_RE.sub("", ln.split("//", 1)[0])
        depth += sum(c.count(ch) for ch in "{([") - sum(c.count(ch) for ch in "})]")
        depth = max(depth, 0)
    if not drop:
        return code
    return "\n".join(ln for i, ln in enumerate(lines) if i not in drop)


def splice_replace(current_code: str, old: Feature, new: Feature) -> str:
    """Replaces the contributions of `old` with those of `new` in the text.

    First removes the functions and setup/loop lines of `old` (by content
    anchor), then adds those of `new`. Raises SpliceError if an anchor of `old`
    cannot be found (text rewritten too much -> the orchestrator falls back to
    assembly)."""
    code = current_code
    for fn in old.functions:
        code = _remove_function(code, fn.name)
    changed = ({n for n in statement_names(old.global_lines) if n}
               & {n for n in statement_names(new.global_lines) if n})
    code = _remove_global_statements(code, changed)
    code = _remove_lines_from_body(code, "setup", old.setup_lines)
    code = _remove_lines_from_body(code, "loop", old.loop_lines)
    return splice_add(code, new)
