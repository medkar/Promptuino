"""feature->code data model of the project.

A *feature* = what a generation action (Regenerate/Add/Correct) produced. It
stores its CONTRIBUTIONS to the final sketch: includes, globals, setup()
lines, loop() lines, and functions. The granularity is the generation action,
not the C function (a feature can contain several functions).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# Reserved id of the synthetic "manual edits" feature — code the user typed by
# hand, not produced by a generation action. It carries NO AI intent, so it is
# excluded from every prompt-building path (see `ai_features`).
MANUAL_ID = "manual"


@dataclass
class FeatureFunction:
    name: str
    code: str


@dataclass
class Feature:
    id: str
    prompt: str                # LAST prompt (the most recent modification)
    summary: str = ""          # short summary (AI) for display; fallback prompt
    # FULL prompt history, oldest first: [original, modif 1, modif 2, …].
    # The ↻ regeneration replays the whole history (full_prompt), not just
    # the last delta; the display fallback uses the FIRST one (the only one
    # that describes the feature rather than a modification).
    prompts: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    global_lines: list[str] = field(default_factory=list)
    setup_lines: list[str] = field(default_factory=list)
    loop_lines: list[str] = field(default_factory=list)
    functions: list[FeatureFunction] = field(default_factory=list)
    # Chip swap persisted from the wiring diagram (2026-07-29): corpus ids the
    # user has explicitly REPLACED (banned) / CHOSEN (forced) for this feature.
    # Every later regeneration (↻) re-applies them — without this, the next ↻
    # recomputed the RAG default and the swapped chip silently came back
    # (SSD1306 → SH1106 → ↻ → SSD1306 again).
    banned_lib_ids: list[str] = field(default_factory=list)
    forced_lib_ids: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Legacy features (or ad-hoc constructions) carry only `prompt`:
        # seed the history with it so first/full_prompt always work.
        if not self.prompts and self.prompt:
            self.prompts = [self.prompt]

    @property
    def first_prompt(self) -> str:
        """Original prompt of the feature (display fallback when the AI
        summary is missing — the later prompts only describe deltas)."""
        return self.prompts[0] if self.prompts else self.prompt

    def full_prompt(self) -> str:
        """Complete intent: original prompt + every modification, one per
        line prefixed with '+'. This is what a from-scratch regeneration
        must implement (the whole feature, not just the last delta)."""
        ps = [" ".join(p.split()) for p in self.prompts if p and p.strip()]
        if not ps:
            return self.prompt
        return "\n+ ".join(ps)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "summary": self.summary,
            "prompts": list(self.prompts),
            "includes": list(self.includes),
            "global_lines": list(self.global_lines),
            "setup_lines": list(self.setup_lines),
            "loop_lines": list(self.loop_lines),
            "functions": [{"name": f.name, "code": f.code} for f in self.functions],
            "banned_lib_ids": list(self.banned_lib_ids),
            "forced_lib_ids": list(self.forced_lib_ids),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Feature":
        return cls(
            id=str(d.get("id", "")),
            prompt=str(d.get("prompt", "")),
            summary=str(d.get("summary", "")),
            # Absent in pre-history projects -> __post_init__ seeds [prompt].
            prompts=[str(x) for x in d.get("prompts", [])],
            includes=[str(x) for x in d.get("includes", [])],
            global_lines=[str(x) for x in d.get("global_lines", [])],
            setup_lines=[str(x) for x in d.get("setup_lines", [])],
            loop_lines=[str(x) for x in d.get("loop_lines", [])],
            functions=[FeatureFunction(name=str(f.get("name", "")),
                                       code=str(f.get("code", "")))
                       for f in d.get("functions", [])],
            banned_lib_ids=[str(x) for x in d.get("banned_lib_ids", [])],
            forced_lib_ids=[str(x) for x in d.get("forced_lib_ids", [])],
        )

    def all_text(self) -> str:
        """Concatenate all contributions — for searches (pins)."""
        parts = (self.includes + self.global_lines + self.setup_lines
                 + self.loop_lines + [f.code for f in self.functions])
        return "\n".join(parts)


def ai_features(features: list[Feature]) -> list[Feature]:
    """Features that carry an AI intent — excludes the synthetic `manual`
    feature (hand-typed code has no rewritten prompt). Use at EVERY site that
    builds a prompt from features (recombine, review C intent) so the manual
    code never pollutes an AI request."""
    return [f for f in features if f.id != MANUAL_ID]


def next_feature_id(features: list[Feature]) -> str:
    max_n = 0
    for f in features:
        if f.id.startswith("f"):
            try:
                max_n = max(max_n, int(f.id[1:]))
            except ValueError:
                pass
    return f"f{max_n + 1}"


def used_names(features: list[Feature]) -> set[str]:
    """Function names already taken (to avoid collisions at generation)."""
    return {fn.name for f in features for fn in f.functions}


# Identifier declared at global scope: the name just before '=', ';' or '[' (e.g.
# 'PIN_LED' in 'const int PIN_LED = 5;', 'myServo' in 'Servo myServo;').
_GLOBAL_NAME_RE = re.compile(r"\b([A-Za-z_]\w*)\s*(?:=|;|\[)")
_C_KEYWORDS = frozenset({
    "const", "int", "long", "float", "double", "char", "byte", "bool",
    "boolean", "unsigned", "signed", "volatile", "static", "void", "short",
    "word", "uint8_t", "uint16_t", "uint32_t", "int8_t", "int16_t", "int32_t",
    "size_t", "return", "if", "else", "for", "while",
})


def used_global_names(features: list[Feature]) -> set[str]:
    """Identifiers declared at global scope (variables/objects) — to prevent the
    model from reusing the same name (e.g. `PIN_LED`) on a new feature."""
    names: set[str] = set()
    for f in features:
        for line in f.global_lines:
            for m in _GLOBAL_NAME_RE.finditer(line):
                tok = m.group(1)
                if tok not in _C_KEYWORDS:
                    names.add(tok)
    return names


_DEFINE_RE = re.compile(r"#\s*define\s+([A-Za-z_]\w*)")


def declared_name(line: str) -> str | None:
    """Identifier declared by ONE global line: name of a variable/object
    (`PIN_SERVO` in `const int PIN_SERVO = 5;`, `monServo` in
    `Servo monServo;`) or of a `#define` (`PIN_SERVO_2`). None if the line
    declares nothing (continuation of a multi-line initializer, comment…).

    Used to deduplicate declarations at assembly: if the model re-emits or
    reuses an already-declared name, Python drops the duplicate (otherwise =
    redefinition that does not compile)."""
    m = _DEFINE_RE.search(line)
    if m:
        return m.group(1)
    for m in _GLOBAL_NAME_RE.finditer(line):
        tok = m.group(1)
        if tok not in _C_KEYWORDS:
            return tok
    return None


def feature_mentions_pin(feature: Feature, pin: str) -> bool:
    """True if the feature references the pin `pin` (e.g. 'D13', 'A0', '13').

    We normalize by removing an optional 'D' prefix for numeric pins, and we
    search for the token at a word boundary in the feature's text. 'A0' is
    searched as-is (analog pin)."""
    pin = pin.strip()
    if not pin:
        return False
    candidates = {pin}
    m = re.fullmatch(r"[Dd](\d+)", pin)
    if m:
        candidates.add(m.group(1))      # 'D13' -> also searches '13'
    text = feature.all_text()
    return any(re.search(r"\b" + re.escape(c) + r"\b", text) for c in candidates)


def used_pins(features: list[Feature]) -> set[str]:
    """Heuristic: all numeric pin tokens appearing in the
    pinMode/digitalWrite/analogWrite/attach of the features. Used for the
    read-only summary provided to the model to avoid collisions."""
    pins: set[str] = set()
    pat = re.compile(r"\b(?:pinMode|digitalWrite|analogWrite|digitalRead|"
                     r"analogRead|attach)\s*\(\s*([A-Za-z0-9_]+)")
    for f in features:
        for tok in pat.findall(f.all_text()):
            pins.add(tok)
    return pins


# ── Resolution of a feature's REAL pins (for the modal display) ──
# `used_pins` above returns the 1st RAW argument of pin calls, so often a
# constant NAME ('PIN_LED') or array name ('leds'), not a number. Here we
# resolve to real numbers via the feature's local declarations (#define /
# const int / array initializer), falling back to the name if we cannot
# resolve. Used for the label of the « Modifier » selector (D5, D2–D11).

_PIN_DEFINE_RE = re.compile(r"#\s*define\s+([A-Za-z_]\w*)\s+(\d{1,3})\b")
_PIN_CONST_RE = re.compile(
    r"\b(?:const\s+|static\s+|volatile\s+)*(?:unsigned\s+)?"
    r"(?:int|byte|short|uint8_t|uint16_t)\s+([A-Za-z_]\w*)\s*=\s*(\d{1,3})\b")
_PIN_ARRAY_RE = re.compile(
    r"\b([A-Za-z_]\w*)\s*\[\s*\d*\s*\]\s*=\s*\{([^}]*)\}")
_PIN_CALL_RE = re.compile(
    r"\b(?:pinMode|digitalWrite|analogWrite|digitalRead|analogRead|tone|"
    r"noTone|attach|attachInterrupt|pulseIn)\s*\(\s*([A-Za-z0-9_]+)")


def _pin_sort_key(pin: str):
    """Display sort: digital pins by number, then analog, then unresolved
    names (alpha)."""
    m = re.fullmatch(r"D(\d+)", pin)
    if m:
        return (0, int(m.group(1)), "")
    m = re.fullmatch(r"A(\d+)", pin)
    if m:
        return (1, int(m.group(1)), "")
    return (2, 0, pin)


def resolve_feature_pins(feature: Feature) -> list[str]:
    """Real pins of the feature, resolved to numbers when possible, as sorted
    and deduplicated display tokens: 'D13', 'A0', or an unresolved name as a
    fallback ('mysteryPin').

    Strategy: we read the feature's local declarations (scalar constants +
    arrays), then iterate over the 1st arguments of the pin calls
    (pinMode/digitalWrite/analogRead/attach/…) and resolve them via those
    declarations. An unknown name is kept as-is."""
    text = feature.all_text()
    scal: dict[str, int] = {}
    for name, val in _PIN_DEFINE_RE.findall(text):
        scal.setdefault(name, int(val))
    for name, val in _PIN_CONST_RE.findall(text):
        scal.setdefault(name, int(val))
    arr: dict[str, list[int]] = {}
    for name, body in _PIN_ARRAY_RE.findall(text):
        nums = [int(n) for n in re.findall(r"\b(\d{1,3})\b", body)]
        if nums:
            arr.setdefault(name, nums)
    out: set[str] = set()
    for tok in _PIN_CALL_RE.findall(text):
        if tok.isdigit():
            out.add(f"D{int(tok)}")
        elif re.fullmatch(r"[Aa]\d+", tok):
            out.add("A" + tok[1:])
        elif tok in scal:
            out.add(f"D{scal[tok]}")
        elif tok in arr:
            for n in arr[tok]:
                out.add(f"D{n}")
        else:
            out.add(tok)
    return sorted(out, key=_pin_sort_key)


def guess_correction_target(features: list[Feature], prompt: str) -> str | None:
    """Id of the feature mentioning a pin cited in the CORRECTION prompt
    (e.g. 'CORRECTION LED sur D9 : …'), or None.

    Case-insensitive: catches 'd5' like 'D5' (school keyboards type in
    lowercase). We test the pins in text order and return the FIRST existing
    feature that matches — so « de d5 vers d2 » targets the feature on d5 (the
    occupied pin), not d2 (the target still free)."""
    for tok in re.findall(r"\b([AD]?\d{1,2})\b", prompt, re.IGNORECASE):
        for f in features:
            if feature_mentions_pin(f, tok):
                return f.id
    return None


def serialize_features(features: list[Feature]) -> list[dict]:
    return [f.to_dict() for f in features]


def deserialize_features(data: list[dict]) -> list[Feature]:
    return [Feature.from_dict(d) for d in data]
