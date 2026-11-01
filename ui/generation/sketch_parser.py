"""Split an Arduino mini-sketch (produced by the model) into contributions.

It is PYTHON that categorizes — never the model. The model writes a normal
sketch; we extract setup()/loop() via brace-counting, the other functions,
the includes, and the rest into globals.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .brace_utils import strip_fences, iter_functions
from .feature_model import FeatureFunction


class SketchParseError(Exception):
    """Raised when the text contains no usable code structure."""


@dataclass
class ParsedContributions:
    includes: list[str] = field(default_factory=list)
    global_lines: list[str] = field(default_factory=list)
    setup_lines: list[str] = field(default_factory=list)
    loop_lines: list[str] = field(default_factory=list)
    functions: list[FeatureFunction] = field(default_factory=list)


def _body_lines(code: str, body_start: int, body_end: int) -> list[str]:
    body = code[body_start:body_end]
    return [ln.strip() for ln in body.split("\n") if ln.strip()]


# Is a top-level statement EXECUTABLE (function call, member access, control
# flow, assignment) — as opposed to a DECLARATION (const/int/object/#define)?
# Serves ONLY as a safety net when the model (weak local SLM) forgot to wrap
# its code in void setup()/loop(): these statements are illegal at global
# scope (do not compile), so we route them to setup() instead of letting them
# corrupt the globals. Declarations, however, stay in globals.
_EXEC_STMT_RE = re.compile(
    r"^(?:"
    r"(?:if|for|while|do|switch|else|return|delay|break|continue|goto)\b"  # control flow
    r"|[A-Za-z_]\w*\s*\("                          # bare call: name(
    r"|[A-Za-z_]\w*\s*(?:\.|->)"                   # member call: obj. / obj->
    r"|[A-Za-z_]\w*(?:\s*\[[^\]]*\])?\s*=(?!=)"     # assignment (var = , arr[i] = )
    r")"
)


def _looks_executable(line: str) -> bool:
    return bool(_EXEC_STMT_RE.match(line))


def parse_sketch(sketch: str) -> ParsedContributions:
    code = strip_fences(sketch)
    out = ParsedContributions()

    # 1) Top-level functions: setup/loop -> lines; others -> FeatureFunction.
    spans: list[tuple[int, int]] = []
    has_setup = has_loop = False
    for name, sig_start, body_start, body_end, end in iter_functions(code):
        spans.append((sig_start, end))
        if name == "setup":
            out.setup_lines = _body_lines(code, body_start, body_end)
            has_setup = True
        elif name == "loop":
            out.loop_lines = _body_lines(code, body_start, body_end)
            has_loop = True
        else:
            # Full code of the function, leading whitespace removed.
            frag = code[sig_start:end]
            out.functions.append(FeatureFunction(name=name, code=frag.strip()))

    # 2) Carve: we replace the function spans with blanks to keep only the
    #    remaining top-level (includes + globals).
    chars = list(code)
    for start, end in spans:
        for k in range(start, end):
            chars[k] = " " if code[k] != "\n" else "\n"
    leftover = "".join(chars)

    # "Forgotten wrappers" safety net: if the model produced NEITHER setup()
    # NOR loop(), its executable statements end up at global scope (illegal,
    # does not compile) — we redirect them to setup(), the declarations staying
    # in globals. When setup()/loop() exist, behavior is strictly unchanged.
    rescue = not has_setup and not has_loop

    # 3) Classify the remainder line by line. We keep a line if it is C/C++
    #    code (declaration with ;, brace, or # directive) OR if we are inside
    #    an open multi-line initializer (depth > 0) — this way a multi-line
    #    global (e.g. melody array) is NEVER stripped of its middle line. Pure
    #    prose (without C punctuation, outside a block) is rejected. `sink`
    #    propagates the destination of a multi-line block to its inner lines
    #    (the body of an if redirected to setup stays whole there).
    depth = 0
    sink = "global"
    for raw in leftover.split("\n"):
        s = raw.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("#include"):
            out.includes.append(s)
            continue
        if depth > 0 or s.startswith("#") or ";" in s or "{" in s or "}" in s:
            if depth > 0:
                target = sink                          # continuation of an open block
            elif rescue and _looks_executable(s):
                target = "setup"
            else:
                target = "global"
            (out.setup_lines if target == "setup"
             else out.global_lines).append(s)
            if depth == 0:
                sink = target
        depth += s.count("{") - s.count("}")
        if depth < 0:
            depth = 0

    if not (out.includes or out.global_lines or out.setup_lines
            or out.loop_lines or out.functions):
        raise SketchParseError("aucune structure de code exploitable")
    return out
