"""Deterministic code formatting (no AI).

Two building blocks — cf docs/superpowers/specs/2026-06-22-auto-indent-brace-locator-design.md :

  (A) reindent_code(code)
      Re-indents code with BALANCED braces by brace depth,
      **1 tab per level**. Returns the code UNCHANGED if it is unbalanced
      (we don't indent code that doesn't parse). Idempotent.

  (B) locate_missing_brace(code) / insert_missing_brace(code)
      Locates a missing CLOSING brace via the existing indentation (a
      line that "de-indents" without `}`) and reinserts it. Only applies to
      exactly ONE missing `}` (balanced parentheses), and only if
      the insertion restores a CONSISTENT indentation (otherwise None → model fallback).

Pure module: no Qt dependency. Tested by scripts/test_code_format.py.
"""
from __future__ import annotations

INDENT = "\t"   # 1 tab per level (decision D4)


# ── Cleanup (strings / comments) ────────────────────────────────────────

def _clean_lines(code: str) -> list[str]:
    """Lines of `code` with strings and comments removed (replaced by
    blanks), keeping the SAME number of lines. Used for reliable counting of
    braces/parentheses: we don't count those inside "..." or // /* */."""
    out: list[str] = []
    in_block = False        # inside a multi-line /* ... */
    for line in code.split("\n"):
        res: list[str] = []
        i, n = 0, len(line)
        in_str = ""         # '"' or "'" if we are inside a literal
        while i < n:
            c = line[i]
            two = line[i:i + 2]
            if in_block:
                if two == "*/":
                    in_block = False
                    i += 2
                    continue
                i += 1
                continue
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == in_str:
                    in_str = ""
                i += 1
                continue
            if two == "//":
                break
            if two == "/*":
                in_block = True
                i += 2
                continue
            if c in ('"', "'"):
                in_str = c
                i += 1
                continue
            res.append(c)
            i += 1
        out.append("".join(res))
    return out


def _counts(cleaned: list[str]) -> tuple[int, int, int, int]:
    j = "".join(cleaned)
    return j.count("{"), j.count("}"), j.count("("), j.count(")")


def _leading_tabs(line: str) -> int:
    n = 0
    for c in line:
        if c == "\t":
            n += 1
        else:
            break
    return n


def _leading_closes(cleaned_stripped: str) -> int:
    """Number of `}` at the head of the cleaned line (before any other character)."""
    n = 0
    for c in cleaned_stripped:
        if c == "}":
            n += 1
        elif c.isspace():
            continue
        else:
            break
    return n


def _net(cleaned_line: str) -> int:
    return cleaned_line.count("{") - cleaned_line.count("}")


def is_balanced(code: str) -> bool:
    """True if braces AND parentheses are balanced (excluding strings/comments)."""
    o, c, op, cp = _counts(_clean_lines(code))
    return o == c and op == cp


# ── (A) Reformatting ───────────────────────────────────────────────────────────

def reindent_code(code: str) -> str:
    cleaned = _clean_lines(code)
    o, c, _, _ = _counts(cleaned)
    if o != c:
        return code                      # unbalanced → we touch nothing
    orig = code.split("\n")
    out: list[str] = []
    depth = 0
    for raw, cl in zip(orig, cleaned):
        stripped = raw.strip()
        if not stripped:
            out.append("")
        elif stripped.startswith("#"):
            out.append(stripped)         # preprocessor: column 0
        else:
            lead = _leading_closes(cl.strip())
            level = max(0, depth - lead)
            out.append(INDENT * level + stripped)
        depth += _net(cl)
    return "\n".join(out)


# ── (B) Locating / inserting a missing brace ─────────────────────

def _indent_consistent(code: str) -> bool:
    """True if each line (excluding blank / preprocessor) is indented to EXACTLY
    its brace depth (in tabs). This is the confidence criterion: we
    only insert a brace if the result is perfectly consistent — otherwise
    the indentation is unreliable (flat code) and we prefer to do nothing."""
    cleaned = _clean_lines(code)
    o, c, _, _ = _counts(cleaned)
    if o != c:
        return False
    depth = 0
    for raw, cl in zip(code.split("\n"), cleaned):
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            expected = max(0, depth - _leading_closes(cl.strip()))
            if _leading_tabs(raw) != expected:
                return False
        depth += _net(cl)
    return True


def _find_dedent(code: str, cleaned: list[str]) -> int | None:
    """Index of the 1st line that "exits" its block without `}` (actual
    indentation < expected depth), or `len(lines)` if the block runs to EOF,
    or None if nothing usable."""
    orig = code.split("\n")
    depth = 0
    for idx, (raw, cl) in enumerate(zip(orig, cleaned)):
        cs = cl.strip()
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and not cs.startswith("}"):
            if _leading_tabs(raw) < depth - _leading_closes(cs):
                return idx
        depth += _net(cl)
    return len(orig) if depth == 1 else None


def _insertion_indent(cleaned: list[str], orig: list[str], idx: int) -> int:
    """Indentation (level) of the `}` to insert = that of the line that OPENED the
    innermost block still open at point `idx`."""
    depth = 0
    open_indent = {0: 0}
    for i in range(min(idx, len(orig))):
        line_indent = _leading_tabs(orig[i])
        for ch in cleaned[i]:
            if ch == "{":
                depth += 1
                open_indent[depth] = line_indent
            elif ch == "}":
                depth = max(0, depth - 1)
    return open_indent.get(depth, 0)


def _do_insert(code: str, cleaned: list[str], idx: int) -> str:
    orig = code.split("\n")
    indent = _insertion_indent(cleaned, orig, idx)
    brace = INDENT * indent + "}"
    pos = idx
    # EOF: insert BEFORE the trailing blank lines (cosmetic).
    if pos >= len(orig):
        pos = len(orig)
        while pos > 0 and orig[pos - 1] == "":
            pos -= 1
    return "\n".join(orig[:pos] + [brace] + orig[pos:])


def locate_missing_brace(code: str) -> int | None:
    """0-based index BEFORE which to insert the missing `}` (or `len(lines)` for
    EOF). None if: not exactly 1 missing `}`, unbalanced parentheses, or
    unreliable indentation (the insertion does not restore perfect consistency)."""
    cleaned = _clean_lines(code)
    o, c, op, cp = _counts(cleaned)
    if o - c != 1 or op != cp:
        return None
    idx = _find_dedent(code, cleaned)
    if idx is None:
        return None
    candidate = _do_insert(code, cleaned, idx)
    return idx if _indent_consistent(candidate) else None


def insert_missing_brace(code: str) -> str | None:
    """Inserts the missing `}` at the right place/indentation. None if not locatable
    (→ the caller falls back to the model / the analysis)."""
    idx = locate_missing_brace(code)
    if idx is None:
        return None
    return _do_insert(code, _clean_lines(code), idx)
