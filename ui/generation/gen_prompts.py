"""Pure prompt builders (no Qt) for per-feature generation.

The SLM always receives the SAME contract: "write a normal Arduino mini-sketch
for THIS feature only". Python then splits it (sketch_parser). The prompts are
in English (SLM token savings) and the actual instruction is placed last
(recency bias).
"""
from __future__ import annotations

import re

from .feature_model import (
    Feature, used_pins, used_names, used_global_names, resolve_feature_pins,
)

# Directive asking the model for a short summary at the HEAD of the output, as a
# `// FEATURE: ...` comment. The parser ignores comments, so this line does not
# pollute the code; the orchestrator extracts it to display it.
FEATURE_SUMMARY_DIRECTIVE = (
    "Begin your output with EXACTLY one line `// FEATURE: <title>` — a short "
    "title (max 6 words, in the same language as the request) summarizing what "
    "this code does — then the sketch."
)

_SUMMARY_RE = re.compile(r"//\s*FEATURE\s*:\s*(.+)", re.IGNORECASE)


def build_context_summary(features: list[Feature]) -> str:
    """READ-ONLY summary of the existing code (occupied pins, taken names). Never
    the full code. Empty if there is nothing."""
    if not features:
        return ""
    pins = sorted(used_pins(features))
    names = sorted(used_names(features) | used_global_names(features))
    parts = []
    if pins:
        parts.append("PINS already used (do not reuse): " + ", ".join(pins))
    if names:
        parts.append("Identifiers already taken — variable AND function names "
                     "(pick DISTINCT new names, do NOT reuse these): "
                     + ", ".join(names))
    return "\n".join(parts)


def build_feature_instruction(feature_desc: str, *, board_hint: str,
                              existing_code: str = "", used_summary: str = "") -> str:
    """Message to ADD a feature.

    We give the model the EXISTING sketch read-only so it SEES what is already
    there (and does not have to guess it nor re-declare it); it only produces the
    ADDITIONS of the new feature. `used_summary` is a concise reminder
    (taken pins/names) placed at the end for the recency bias. The Python
    deduplication remains a safety net."""
    head = (
        f"Target board: {board_hint}.\n"
        "You are ADDING a new feature to an EXISTING Arduino sketch (shown below). "
        "Output ONLY the NEW additions for the new feature. Do NOT repeat, "
        "re-declare or re-initialize anything already present (no duplicate pins, "
        "variables, objects or functions; do NOT re-setup existing hardware). "
        "Choose pin numbers and identifier names that are NOT already used.\n"
        "Format the output as a normal Arduino sketch with this EXACT structure: "
        "the new #include and global declarations first, then a `void setup() { ... }` "
        "block, then a `void loop() { ... }` block, then any new functions. ALWAYS "
        "put executable statements INSIDE setup() or loop(): initialization (pinMode, "
        ".begin(), config) goes inside void setup(), repeating code inside void loop(). "
        "NEVER write a function call or statement at the global/top level — only "
        "declarations (const, #define, objects) live there. Each setup()/loop() block "
        "must contain ONLY the NEW lines (leave a block empty if it adds nothing); do "
        "NOT re-emit setup()/loop() lines that already exist (no second Serial.begin(), "
        "pinMode() or .begin() for hardware another feature already initialized). "
        "Raw code only, no markdown fences. " + FEATURE_SUMMARY_DIRECTIVE
    )
    ex = (f"\n\nEXISTING SKETCH (read-only, do NOT repeat any of it):\n{existing_code}"
          if existing_code.strip() else "")
    used = f"\n\n{used_summary}" if used_summary else ""
    tail = f"\n\nNEW FEATURE TO ADD:\n{feature_desc}"
    return head + ex + used + tail


def build_modify_instruction(current_code: str, modification: str,
                             context_summary: str, *, board_hint: str) -> str:
    """Message to MODIFY an existing feature.

    We give the model the CURRENT code of the feature and ask it to apply ONLY
    the described change, keeping the rest identical (behavior, timings, pins not
    mentioned). Strongly reduces the risk of losing part of the behavior
    (e.g. a frequency) during the regeneration of the block."""
    head = (
        f"Target board: {board_hint}.\n"
        "Below is the CURRENT implementation of ONE feature. Apply ONLY the "
        "change described in the modification request, and KEEP everything else "
        "exactly as it currently works (same behavior, timings, and any pins NOT "
        "mentioned in the request). Output the FULL updated mini-sketch for THIS "
        "feature only, as a normal Arduino sketch with this EXACT structure: its "
        "#include and globals first, then a `void setup() { ... }` block with its "
        "setup lines, then a `void loop() { ... }` block with its loop lines, then "
        "its functions. ALWAYS put executable statements INSIDE setup()/loop() — "
        "never write a function call or statement at the global/top level (only "
        "declarations live there). Raw code only, no markdown fences. "
        + FEATURE_SUMMARY_DIRECTIVE
    )
    cur = f"\n\nCURRENT IMPLEMENTATION:\n{current_code}"
    ctx = (f"\n\nOther features' context (read-only):\n{context_summary}"
           if context_summary else "")
    tail = f"\n\nMODIFICATION REQUEST:\n{modification}"
    return head + cur + ctx + tail


def build_regen_instruction(feature_request: str, context_summary: str,
                            *, board_hint: str) -> str:
    """Message to REGENERATE a feature FROM SCRATCH (↻ per-feature tool).

    Unlike `build_modify_instruction`, we deliberately DO NOT feed the feature's
    current code: given its current code plus "keep everything as it is", the
    model has no reason to change anything and just returns the same sketch (the
    ↻ button then looks like a no-op). Here we ask for a fresh implementation of
    the request, sharing ONLY the OTHER features' pins/names so the new code does
    not collide with them."""
    head = (
        f"Target board: {board_hint}.\n"
        "Generate a FRESH implementation of ONE feature, from scratch, based "
        "ONLY on the request below. Do NOT assume or reuse any previous code for "
        "this feature. Output the FULL mini-sketch for THIS feature only, as a "
        "normal Arduino sketch with this EXACT structure: its #include and "
        "globals first, then a `void setup() { ... }` block, then a "
        "`void loop() { ... }` block, then its functions. ALWAYS put executable "
        "statements INSIDE setup()/loop() — never write a function call or "
        "statement at the global/top level (only declarations live there). "
        "Raw code only, no markdown fences. " + FEATURE_SUMMARY_DIRECTIVE
    )
    ctx = (f"\n\nOther features already in the sketch (read-only — choose pins "
           f"and identifiers that do NOT collide with these):\n{context_summary}"
           if context_summary else "")
    tail = f"\n\nFEATURE REQUEST:\n{feature_request}"
    return head + ctx + tail


def extract_feature_summary(text: str) -> str:
    """Extracts the short title from the `// FEATURE: ...` line emitted by the
    model. Empty string if absent (the orchestrator then falls back to the prompt)."""
    m = _SUMMARY_RE.search(text)
    return m.group(1).strip() if m else ""


def combine_feature_prompts(prompts: list[str]) -> str:
    """Joint les prompts de fonctionnalités en UN seul intent pour la
    régénération combinée (quand des fonctionnalités couplées ne compilent pas
    une fois assemblées). Ignore les prompts vides."""
    parts = [p.strip() for p in prompts if p and p.strip()]
    return ", et ".join(parts)


def feature_label(feature: Feature, max_len: int = 60) -> str:
    """Display label of a feature (modal selector, chips bar): AI summary if
    present, otherwise the FIRST prompt (the original description — the later
    ones only describe modifications), truncated to `max_len` characters."""
    text = (feature.summary or feature.first_prompt or feature.id).strip()
    text = " ".join(text.split())
    if len(text) > max_len:
        text = text[:max_len - 1].rstrip() + "…"
    return text


def compact_pin_label(pins: list[str]) -> str:
    """Compact form of the pins for the « Modifier » selector label: we only
    expose ~2 pins so as not to overload it. 0 → '' ; 1-2 → listed ;
    3+ contiguous and all digital → range 'D2–D11' ; 3+ otherwise → 'first 2
    + overflow counter' ('D5, D9 +1'). The full list is in the tooltip
    (see feature_combo_tooltip)."""
    if not pins:
        return ""
    if len(pins) <= 2:
        return ", ".join(pins)
    nums: list[int] | None = []
    for p in pins:
        m = re.fullmatch(r"D(\d+)", p)
        if m is None:
            nums = None
            break
        nums.append(int(m.group(1)))
    if nums is not None and nums == list(range(nums[0], nums[0] + len(nums))):
        return f"{pins[0]}–{pins[-1]}"          # D2–D11 (en dash)
    return f"{pins[0]}, {pins[1]} +{len(pins) - 2}"


def feature_combo_label(feature: Feature, max_len: int = 48) -> str:
    """Label of an item in the « Modifier » selector: summary (truncated) +
    compact pins (e.g. « Clignote la LED — D5 », « Clignote 10 LEDs — D2–D11 »).
    The pins come from resolve_feature_pins (real numbers)."""
    base = feature_label(feature, max_len=max_len)
    compact = compact_pin_label(resolve_feature_pins(feature))
    return f"{base} — {compact}" if compact else base   # — (em dash)


def feature_combo_tooltip(feature: Feature) -> str:
    """Tooltip (hover) of an item in the selector: FULL summary (not truncated) +
    ALL the pins. Avoids overloading the label while keeping the info."""
    summary = (feature.summary or feature.first_prompt or feature.id).strip()
    summary = " ".join(summary.split())
    pins = resolve_feature_pins(feature)
    return f"{summary}\n{', '.join(pins)}" if pins else summary
