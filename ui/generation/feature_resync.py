"""Rebuild feature contributions from the editor text + line-owner map.

After a repair (auto or via the Tools) or a manual edit, the editor code
diverges from the feature MODEL: `_set_code_with_attribution` refreshes the
line-owner map but never re-splits the `Feature.*_lines`. Any flow that
reconstructs code from the model (assemble) — notably the transfer popup —
then works on the STALE, pre-repair contributions.

`sync_features_from_editor` re-derives each feature's contributions
(includes / globals / setup / loop / functions) from the current editor code
and its owner map, so `assemble(result)` reflects the repaired code. It is
best-effort (the owner map itself is heuristic after a structural repair):
the caller MUST verify `assemble(result)` still matches the editor before
trusting it, and fall back to the stale model otherwise. Orphan lines
(owner None) are attached to a neighbor so nothing is silently dropped.

Pure module — no Qt.
"""
from __future__ import annotations

import copy
from bisect import bisect_right

from .brace_utils import iter_functions
from .feature_model import Feature, FeatureFunction


def _line_starts(lines: list[str]) -> list[int]:
    starts = [0]
    for ln in lines[:-1]:
        starts.append(starts[-1] + len(ln) + 1)   # +1 for the '\n'
    return starts


def sync_features_from_editor(features: list[Feature], code: str,
                              owners: list,
                              manual_id: str | None = None) -> list[Feature]:
    """Return fresh Feature copies whose contributions are rebuilt from
    `code` + `owners` (block index -> feature id | None, aligned on
    code.split('\\n')). Ids/prompts/summary are preserved; the *_lines are
    replaced. See module docstring for the best-effort contract.

    `manual_id` (TODO #31): when set, orphan lines (owner None / unknown) are
    routed to a synthetic `manual` feature — reused if already in `features`,
    else created — instead of being attached to the previous known owner. The
    manual feature is placed LAST and only included if it ends up carrying
    contributions (or already existed). Round-trip stays the caller's guard:
    interleaved orphans won't reproduce the editor once regrouped last, so the
    caller falls back to the neighbor mode (`manual_id=None`)."""
    if not features and manual_id is None:
        return []
    lines = code.split("\n")
    owners = list(owners) + [None] * (len(lines) - len(owners))

    fresh = {f.id: copy.deepcopy(f) for f in features}
    for f in fresh.values():
        f.includes, f.global_lines = [], []
        f.setup_lines, f.loop_lines, f.functions = [], [], []
    order = [f.id for f in features]
    # Manual receptacle: reuse if present, else a scratch feature added to the
    # result only if it ends up carrying orphan (hand-typed) lines.
    manual_preexisting = manual_id is not None and manual_id in fresh
    if manual_id is not None and not manual_preexisting:
        fresh[manual_id] = Feature(id=manual_id, prompt="")
    real_order = [fid for fid in order if fid != manual_id]
    default_owner = real_order[0] if real_order else (order[0] if order else manual_id)

    starts = _line_starts(lines)

    def line_of(offset: int) -> int:
        return max(0, min(len(lines) - 1, bisect_right(starts, offset) - 1))

    # Classify every line index: which function body it belongs to, or None
    # (top-level). Function signature/brace lines are marked scaffold.
    # Anchor on the line of the OPENING BRACE (body_start-1), NOT on sig_start:
    # iter_functions' sig_start includes the leading "\n\n" block separator, so
    # line_of(sig_start) lands on the PREVIOUS content line (it would steal the
    # last global / the previous function's '}'). From the brace line, walk
    # back over any multi-line signature continuation.
    section = ["top"] * len(lines)     # top | setup | loop | scaffold | fn:<idx>
    fn_spans: list[tuple[int, int, str]] = []   # (l0, l1, name)
    for name, sig_start, body_start, body_end, end in iter_functions(code):
        open_line = line_of(body_start - 1)     # the '{'
        close_line = line_of(body_end)          # the matching '}'
        sig_line = open_line
        while sig_line - 1 >= 0:
            prev = lines[sig_line - 1].strip()
            if not prev or prev.endswith((";", "}", "{")):
                break
            sig_line -= 1                        # multi-line signature line
        if name in ("setup", "loop"):
            for i in range(sig_line, close_line + 1):
                section[i] = "scaffold"
            for i in range(open_line + 1, close_line):
                section[i] = name
        else:
            for i in range(sig_line, close_line + 1):
                section[i] = f"fn:{len(fn_spans)}"
            fn_spans.append((sig_line, close_line, name))

    last_owner = default_owner

    def owner_at(i: int) -> str:
        nonlocal last_owner
        o = owners[i]
        if o in fresh and o != manual_id:
            last_owner = o
            return o
        # orphan (None / unknown) or an already-manual line:
        if manual_id is not None:
            return manual_id     # route hand-typed code to the manual bucket
        return last_owner        # legacy: attach to the previous known owner

    # Top-level (includes / globals) + setup / loop bodies, line by line.
    for i, raw in enumerate(lines):
        s = raw.strip()
        sec = section[i]
        if not s or sec in ("scaffold",) or sec.startswith("fn:"):
            continue
        f = fresh[owner_at(i)]
        if sec == "setup":
            f.setup_lines.append(s)
        elif sec == "loop":
            f.loop_lines.append(s)
        elif s.startswith("#include"):
            f.includes.append(s)
        else:
            f.global_lines.append(s)

    # Whole-function blocks: one FeatureFunction owned by the dominant owner
    # of the block's lines.
    for l0, l1, name in fn_spans:
        counts: dict[str, int] = {}
        for i in range(l0, l1 + 1):
            o = owners[i]
            if o in fresh and o != manual_id:
                counts[o] = counts.get(o, 0) + 1
        if counts:
            fid = max(counts, key=counts.get)
        elif manual_id is not None:
            fid = manual_id          # orphan function -> manual bucket
        else:
            fid = last_owner
        block = "\n".join(lines[l0:l1 + 1]).strip()
        fresh[fid].functions.append(FeatureFunction(name=name, code=block))

    result = [fresh[fid] for fid in real_order]
    if manual_id is not None:
        m = fresh[manual_id]
        has_contrib = any((m.includes, m.global_lines, m.setup_lines,
                           m.loop_lines, m.functions))
        if has_contrib:
            result.append(m)             # manual LAST; an EMPTY manual is dropped
    return result
