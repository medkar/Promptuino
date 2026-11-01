"""Deterministic reassignment of pins in conflict between features.

Python net (not an LLM nudge): when a NEW feature places a component on a pin
already occupied by ANOTHER feature, we move the new one to a free pin valid for
the board and rewrite the value of its named constant (+ comment). v1 scope:
named constants (#define / const int); bare literals produce a warning.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from .feature_model import Feature, resolve_feature_pins, declared_name

# boards.json capabilities marking a bus pin to NEVER reassign
# (neither source nor target): I2C, SPI, UART, power.
_BUS_CAPS = ("sda", "scl", "miso", "mosi", "sck", "ss", "rx", "tx", "power")

_DEFINE_RE = re.compile(r"#\s*define\s+([A-Za-z_]\w*)\s+(A?\d{1,3})\b")
_CONST_RE = re.compile(
    r"\b(?:const\s+|static\s+|volatile\s+)*(?:unsigned\s+)?"
    r"(?:int|byte|short|uint8_t|uint16_t)\s+([A-Za-z_]\w*)\s*=\s*(A?\d{1,3})\b")
_AW_RE = re.compile(r"\banalogWrite\s*\(\s*([A-Za-z0-9_]+)")
_AR_RE = re.compile(r"\banalogRead\s*\(\s*([A-Za-z0-9_]+)")


@dataclass
class PinMove:
    const_name: str
    kind: str            # "pwm" | "analog" | "digital"
    old_pin: str         # token "D9" / "A0"
    new_pin: str


@dataclass
class ReassignResult:
    feature: Feature
    moves: list = field(default_factory=list)        # list[PinMove]
    warnings: list = field(default_factory=list)      # list[str]


def _value_to_token(val: str) -> str:
    """'9' -> 'D9' ; 'A0' -> 'A0'."""
    if val[:1] in ("A", "a"):
        return "A" + val[1:]
    return f"D{int(val)}"


def _pin_index(token: str) -> int:
    digits = re.sub(r"\D", "", token)
    return int(digits) if digits else 0


def _constant_pins(feature: Feature) -> dict:
    """{const_name: (token, kind)} for the pins declared by constant.
    kind = 'pwm' (analogWrite) | 'analog' (Ax value or analogRead) | 'digital'."""
    text = feature.all_text()
    aw = set(_AW_RE.findall(text))
    ar = set(_AR_RE.findall(text))
    out: dict = {}
    for rx in (_DEFINE_RE, _CONST_RE):
        for name, val in rx.findall(text):
            if name in out:
                continue
            token = _value_to_token(val)
            if token.startswith("A") or name in ar:
                kind = "analog"
            elif name in aw:
                kind = "pwm"
            else:
                kind = "digital"
            out[name] = (token, kind)
    return out


def _is_bus_token(board, tok: str) -> bool:
    return board.has_pin(tok) and any(
        board.has_capability(tok, c) for c in _BUS_CAPS)


def _free_pin(board, kind: str, used: set) -> str | None:
    """1st free pin of the board, of the right type, off-bus, by ascending
    number. None if none available."""
    cands = []
    for pin in board.pins():
        if _is_bus_token(board, pin):
            continue
        if kind == "pwm" and pin.startswith("D") and board.has_capability(pin, "pwm"):
            cands.append(pin)
        elif kind == "analog" and pin.startswith("A") and board.has_capability(pin, "analog"):
            cands.append(pin)
        elif kind == "digital" and pin.startswith("D") and board.has_capability(pin, "digital"):
            cands.append(pin)
    for pin in sorted(cands, key=_pin_index):
        if pin not in used:
            return pin
    return None


def _feature_tokens(feature: Feature) -> set:
    """Pin tokens actually used by the feature ('D9','A0'), constants (numeric
    AND Ax) + literals. Filters out unresolved names."""
    toks = {t for t in resolve_feature_pins(feature)
            if re.fullmatch(r"[DA]\d+", t)}
    for tok, _kind in _constant_pins(feature).values():
        toks.add(tok)
    return toks


def _rewrite_value(line: str, const_name: str, new_token: str, comment: str) -> str:
    """Replaces the value of the constant `const_name` in `line` + adds the
    comment (if there is not already a comment on the line)."""
    new_val = new_token[1:] if new_token.startswith("D") else new_token  # D6->6 ; A1->A1
    done = False
    for rx in (
        re.compile(r"(#\s*define\s+" + re.escape(const_name) + r"\s+)A?\d{1,3}\b"),
        re.compile(r"(\b" + re.escape(const_name) + r"\s*=\s*)A?\d{1,3}\b"),
    ):
        line, n = rx.subn(lambda m: m.group(1) + new_val, line, count=1)
        if n:
            done = True
            break
    if done and "//" not in line:
        line = line.rstrip() + "  " + comment
    return line


def _rewrite_summary_pins(summary: str, moves: list) -> str:
    """Updates the pin token in the summary (« Modifier » label) after
    reassignment: « Contrôle du Servo sur D7 » → « … sur D2 ». We only replace
    the token form (D7/A0) on word boundary (case-insensitive); the plain-text
    mentions (« broche 7 ») are left (replacing a bare « 7 » would be too risky)."""
    for m in moves:
        summary = re.sub(r"\b" + re.escape(m.old_pin) + r"\b", m.new_pin,
                         summary, flags=re.IGNORECASE)
    return summary


def format_reassign_notice(moves: list, warnings: list) -> str:
    """Notice text (int/advanced). Empty if nothing to report."""
    lines: list[str] = []
    for m in moves:
        lines.append(
            f"• {m.const_name} déplacé de {m.old_pin} à {m.new_pin} "
            f"({m.old_pin} était déjà utilisée par une autre fonctionnalité).")
    for w in warnings:
        lines.append(f"⚠ {w}")
    return "\n".join(lines)


def reassign_conflicting_pins(new_feature: Feature,
                              existing_features: list,
                              board) -> ReassignResult:
    feat = copy.deepcopy(new_feature)
    result = ReassignResult(feature=feat)
    if board is None:
        return result

    existing_tokens: set = set()
    for f in existing_features:
        existing_tokens |= _feature_tokens(f)
    new_tokens = _feature_tokens(feat)
    conflicts = sorted(new_tokens & existing_tokens, key=_pin_index)
    if not conflicts:
        return result

    consts = _constant_pins(feat)                  # name -> (token, kind)
    token_to_const: dict = {}
    for name, (tok, kind) in consts.items():
        token_to_const.setdefault(tok, (name, kind))

    used = set(existing_tokens) | set(new_tokens)

    for tok in conflicts:
        if _is_bus_token(board, tok):
            result.warnings.append(
                f"{tok} partagé (bus I2C/SPI/UART) — non réaffecté.")
            continue
        if tok not in token_to_const:
            result.warnings.append(
                f"{tok} en conflit mais utilisé en littéral (pas de constante "
                f"nommée) — non réaffecté.")
            continue
        name, kind = token_to_const[tok]
        new_pin = _free_pin(board, kind, used)
        if new_pin is None:
            result.warnings.append(
                f"{tok} en conflit mais plus de broche {kind} libre — "
                f"non réaffecté.")
            continue
        used.add(new_pin)
        comment = (f"// déplacé {tok}→{new_pin} : {tok} déjà utilisé par une "
                   f"autre fonctionnalité")
        feat.global_lines = [
            _rewrite_value(ln, name, new_pin, comment)
            if declared_name(ln) == name else ln
            for ln in feat.global_lines
        ]
        result.moves.append(PinMove(const_name=name, kind=kind,
                                    old_pin=tok, new_pin=new_pin))
    if result.moves:
        feat.summary = _rewrite_summary_pins(feat.summary, result.moves)
    return result
