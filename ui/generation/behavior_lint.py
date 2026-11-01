"""Deterministic behavioral lint for Arduino sketches (pure, no Qt, no model).

Catches STATIC pitfalls that make a sketch compile but MISBEHAVE — the class
of bugs a weak local SLM audits unreliably. Layer B of the behavioral-review
pipeline (spec 2026-07-06): 100% reproducible, backend-independent. It only
REPORTS (never mutates the code); applying a fix is the user's / layer C's job.

Rules are intentionally conservative (no false positives on clean code). The
pin/call regexes mirror the wiring detector (ui/wiring/markers.py) but are
kept local so this module has NO heavy dependency and can evolve on its own.

Extensible: add a `_rule_*` function returning findings and list it in
`_RULES`. Deliberately NOT covered in V1 (too board-specific / ambiguous to
stay false-positive-free): analog-on-digital-pin and digital-on-analog-pin —
needs per-board pin tables; add when the board pin map is threaded in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .brace_utils import find_function_body

# Call patterns (mirror ui/wiring/markers.py).
_PINMODE_RE = re.compile(r"\bpinMode\s*\(\s*([A-Za-z0-9_]+)\s*,\s*(INPUT_PULLUP|INPUT|OUTPUT)\s*\)")
_DIGITAL_WRITE_RE = re.compile(r"\bdigitalWrite\s*\(\s*([A-Za-z0-9_]+)\s*,")
_DIGITAL_READ_RE = re.compile(r"\bdigitalRead\s*\(\s*([A-Za-z0-9_]+)\s*\)")
# Pin constants declared globally: `const int X = 5;` / `#define X 5`.
_CONST_PIN_RE = re.compile(r"\bconst\s+(?:unsigned\s+)?(?:int|byte|uint8_t)\s+([A-Za-z_]\w*)\s*=\s*A?\d")
_DEFINE_PIN_RE = re.compile(r"#\s*define\s+([A-Za-z_]\w*)\s+A?\d")
# Narrow integer types that overflow with millis()/micros().
_NARROW_DECL_RE = re.compile(
    r"\b(?:int|short|byte|uint8_t|uint16_t|unsigned\s+int)\s+([A-Za-z_]\w*)\s*=\s*(?:millis|micros)\s*\(\s*\)")
_NARROW_VAR_DECL_RE = re.compile(
    r"\b(?:int|short|byte|uint8_t|uint16_t|unsigned\s+int)\s+([A-Za-z_]\w*)\s*[;=]")
_TIME_ASSIGN_RE = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*(?:millis|micros)\s*\(\s*\)")
_DELAY_RE = re.compile(r"\bdelay\s*\(\s*(\d+)\s*\)")

_BLOCKING_DELAY_MS = 500      # a delay >= this in loop() with input polling


@dataclass
class Finding:
    line: int
    severity: str      # "error" | "warn"
    rule: str
    message: str
    fix_hint: str


def _blank_strings_comments(code: str) -> str:
    """Replace string/char literal and comment CONTENT with spaces, preserving
    every newline (so line numbers stay exact). Lets the regexes ignore a
    `digitalWrite(...)` sitting in a comment or a string."""
    out = []
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        two = code[i:i + 2]
        if two == "//":
            j = code.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i)); i = j
        elif two == "/*":
            j = code.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append("".join(ch if ch == "\n" else " " for ch in code[i:j]))
            i = j
        elif c in "\"'":
            q = c; j = i + 1
            while j < n and code[j] != q:
                j += 2 if code[j] == "\\" else 1
            j = min(j + 1, n)
            out.append("".join(ch if ch == "\n" else " " for ch in code[i:j]))
            i = j
        else:
            out.append(c); i += 1
    return "".join(out)


def _line_of(code: str, pos: int) -> int:
    return code.count("\n", 0, pos) + 1


def _pin_tokens(code: str) -> set[str]:
    """Tokens that DENOTE a pin: numeric literals, A-pins, LED_BUILTIN, and
    identifiers declared as pin constants (const int / #define)."""
    consts = {m.group(1) for m in _CONST_PIN_RE.finditer(code)}
    consts |= {m.group(1) for m in _DEFINE_PIN_RE.finditer(code)}
    consts.add("LED_BUILTIN")
    return consts


def _is_pin_like(tok: str, consts: set[str]) -> bool:
    if tok in consts:
        return True
    if re.fullmatch(r"\d+", tok):          # numeric pin literal
        return True
    if re.fullmatch(r"[Aa][0-5]", tok):    # analog pin
        return True
    return False


# ── Rules ────────────────────────────────────────────────────────

def _rule_pinmode_missing(code, consts) -> list[Finding]:
    moded = {m.group(1) for m in _PINMODE_RE.finditer(code)}
    out = []
    for rx, verb in ((_DIGITAL_WRITE_RE, "digitalWrite"),
                     (_DIGITAL_READ_RE, "digitalRead")):
        for m in rx.finditer(code):
            tok = m.group(1)
            if tok in moded or not _is_pin_like(tok, consts):
                continue
            out.append(Finding(
                _line_of(code, m.start()), "error", "pinmode_missing",
                f"`{verb}({tok}, …)` sur une broche jamais configurée par "
                f"`pinMode`.",
                f"Ajoute `pinMode({tok}, "
                f"{'OUTPUT' if verb == 'digitalWrite' else 'INPUT_PULLUP'});` "
                f"dans setup()."))
    return out


def _rule_button_no_pullup(code, consts) -> list[Finding]:
    plain_input = {m.group(1) for m in _PINMODE_RE.finditer(code)
                   if m.group(2) == "INPUT"}
    out = []
    for m in _DIGITAL_READ_RE.finditer(code):
        tok = m.group(1)
        if tok in plain_input:
            out.append(Finding(
                _line_of(code, m.start()), "warn", "button_no_pullup",
                f"`{tok}` est lue en `digitalRead` mais configurée `INPUT` "
                f"(pas `INPUT_PULLUP`) : sans résistance externe, l'entrée "
                f"flotte et lit du bruit.",
                f"Utilise `pinMode({tok}, INPUT_PULLUP);` (bouton vers GND) "
                f"ou ajoute une résistance de tirage."))
    return out


def _rule_millis_into_int(code, consts) -> list[Finding]:
    out = []
    seen = set()
    for m in _NARROW_DECL_RE.finditer(code):
        out.append(Finding(
            _line_of(code, m.start()), "error", "millis_into_int",
            f"`millis()`/`micros()` stocké dans `{m.group(1)}` (type trop "
            f"petit) : débordement (~32 s / 71 min) → timing cassé.",
            f"Déclare `{m.group(1)}` en `unsigned long`."))
        seen.add(m.group(1))
    narrow_vars = {m.group(1) for m in _NARROW_VAR_DECL_RE.finditer(code)}
    for m in _TIME_ASSIGN_RE.finditer(code):
        v = m.group(1)
        if v in narrow_vars and v not in seen:
            out.append(Finding(
                _line_of(code, m.start()), "error", "millis_into_int",
                f"`{v} = millis()/micros()` alors que `{v}` est un entier "
                f"court : débordement → timing cassé.",
                f"Déclare `{v}` en `unsigned long`."))
            seen.add(v)
    return out


def _rule_blocking_delay_with_input(code, consts) -> list[Finding]:
    span = find_function_body(code, "loop")
    if span is None:
        return []
    _sig, body_start, body_end, _end = span
    body = code[body_start:body_end]
    if not (_DIGITAL_READ_RE.search(body) or "analogRead" in body):
        return []
    out = []
    for m in _DELAY_RE.finditer(body):
        if int(m.group(1)) >= _BLOCKING_DELAY_MS:
            out.append(Finding(
                _line_of(code, body_start + m.start()), "warn",
                "blocking_delay_with_input",
                f"`delay({m.group(1)})` bloquant dans `loop()` qui lit une "
                f"entrée : pendant l'attente, les entrées ne sont pas lues "
                f"(le bouton « rate »).",
                "Remplace par un timing non bloquant `millis()` "
                "(pattern « blink without delay »)."))
    return out


_RULES = (
    _rule_pinmode_missing,
    _rule_button_no_pullup,
    _rule_millis_into_int,
    _rule_blocking_delay_with_input,
)


def lint_behavior(code: str, board: str = "") -> list[Finding]:
    """Run every deterministic behavioral rule on `code`. Returns findings
    sorted by line. `board` is accepted for future per-board rules
    (analog/digital pin tables) — unused in V1."""
    if not code or not code.strip():
        return []
    blanked = _blank_strings_comments(code)
    consts = _pin_tokens(blanked)
    findings: list[Finding] = []
    for rule in _RULES:
        findings.extend(rule(blanked, consts))
    return sorted(findings, key=lambda f: (f.line, f.rule))
