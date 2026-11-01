"""Inserts/replaces the contributions of a feature in the current editor text,
by CONTENT ANCHORS (never line numbers). Preserves the existing code word-for-
word. Raises SpliceError if an anchor cannot be found.
"""
from __future__ import annotations

from .assembler import _code_sig, _subtract_existing
from .brace_utils import find_function_body
from .feature_model import Feature, declared_name
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
    for g in parsed.global_lines:
        n = declared_name(g)
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
    new_globals = [g for g in feature.global_lines
                   if declared_name(g) is None or declared_name(g) not in existing_names]
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
    to_remove = {ln.strip() for ln in lines}
    kept = [ln for ln in body.split("\n") if ln.strip() not in to_remove]
    new_body = "\n".join(kept)
    return code[:body_start] + new_body + code[body_end:]


def splice_replace(current_code: str, old: Feature, new: Feature) -> str:
    """Replaces the contributions of `old` with those of `new` in the text.

    First removes the functions and setup/loop lines of `old` (by content
    anchor), then adds those of `new`. Raises SpliceError if an anchor of `old`
    cannot be found (text rewritten too much -> the orchestrator falls back to
    assembly)."""
    code = current_code
    for fn in old.functions:
        code = _remove_function(code, fn.name)
    code = _remove_lines_from_body(code, "setup", old.setup_lines)
    code = _remove_lines_from_body(code, "loop", old.loop_lines)
    return splice_add(code, new)
