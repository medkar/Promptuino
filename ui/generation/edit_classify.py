"""Classifies a manual editor edit against the assembled baseline.

- 'clean'    : no code difference (only cosmetic: spaces, empty lines,
               comments).
- 'addition' : only added lines (all the original lines are there, intact)
               -> safe splice (anchors preserved).
- 'inline'   : original lines were modified/removed -> assembly (broken
               anchors), with a warning on the UI side.
"""
from __future__ import annotations

import difflib
import re


def _significant_lines(code: str) -> list[str]:
    """Significant code lines: without blanks, without comments, internal spaces
    normalized."""
    out: list[str] = []
    in_block = False
    for raw in code.split("\n"):
        s = raw.strip()
        if in_block:
            if "*/" in s:
                s = s.split("*/", 1)[1].strip()
                in_block = False
            else:
                continue
        # line comment
        s = re.sub(r"//.*$", "", s).strip()
        # block comment on one line or opening
        while "/*" in s:
            before, after = s.split("/*", 1)
            if "*/" in after:
                s = (before + " " + after.split("*/", 1)[1]).strip()
            else:
                s = before.strip()
                in_block = True
                break
        if not s:
            continue
        out.append(re.sub(r"\s+", " ", s))
    return out


def normalize_code(code: str) -> str:
    return "\n".join(_significant_lines(code))


def is_dirty(current_code: str, baseline: str) -> bool:
    return normalize_code(current_code) != normalize_code(baseline)


def classify_edit(current_code: str, baseline: str) -> str:
    base = _significant_lines(baseline)
    cur = _significant_lines(current_code)
    if base == cur:
        return "clean"
    sm = difflib.SequenceMatcher(a=base, b=cur, autojunk=False)
    for tag, _i1, _i2, _j1, _j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            return "inline"
    # only 'equal' and 'insert' -> pure additions
    return "addition"
