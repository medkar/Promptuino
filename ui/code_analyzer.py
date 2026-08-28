"""
Static analyzer for Arduino/C++ code.

Goal: reconstruct the dependency graph between features (Function)
PURELY in Python, without asking the AI to declare anything at all.

Architecture:
  analyze_code(code, lines_by_fid) -> AnalysisResult
                                      .symbols     ({name: DeclaredSymbol})
                                      .graph       ({fid: {fid,...}})
                                      .exports_by_fid({fid: [DeclaredSymbol]})

The algorithm is LEXICAL (not a real C++ parser). It tracks the brace
level to consider ONLY the global scope when detecting declarations.
Sufficient for 95% of typical Arduino code.

Known limitations, by V1 design:
  - Comma multi-variable declarations (`int a, b;`): only `a` is
    captured. Rare in Arduino.
  - Classes and structs: the body is treated as local scope (no global
    declarations are detected within it). Rare in educational Arduino.
  - `static` variables inside functions: this is local scope, not
    exposable — they are not detected as exports (expected behavior).
  - C++ raw strings (R"(...)" ) and multi-line strings: not handled, but
    they do not appear in typical Arduino code.

This module depends on nothing but the stdlib — deliberately, so it can
be tested / used in isolation. The integration with the application
domain's Function/Export happens on the caller side (studio_view).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


# ── Arduino/C++ builtins to exclude from the dependency graph ────────────────

# These identifiers are keywords, basic C/C++ types or symbols from the
# standard Arduino library. Seeing them in a function's code does NOT
# constitute a dependency on another function (they are globally available
# without an explicit declaration in the sketch).

# Control keywords that can be followed by `ident (args)` and would
# otherwise look like a function declaration: we reject them explicitly
# in `_detect_declaration`.
_CONTROL_KEYWORDS = frozenset((
    "if", "else", "for", "while", "do", "switch", "case", "break", "continue",
    "return", "goto", "try", "catch", "throw",
))

# General keywords (ignored during tokenization so they are not counted
# as used identifiers). `void` is a valid return TYPE (not a control
# keyword) so it does NOT appear here.
_C_KEYWORDS = _CONTROL_KEYWORDS | frozenset((
    "new", "delete",
    "class", "struct", "union", "public", "private", "protected",
    "virtual", "override", "final", "friend",
    "true", "false", "NULL", "nullptr",
    "sizeof", "typedef", "enum", "namespace", "using", "this",
    "static", "const", "volatile", "extern", "inline", "template", "typename",
    "auto", "register", "mutable", "constexpr", "explicit",
    "noexcept", "operator",
))

_C_TYPES = frozenset((
    "void",
    "int", "long", "short", "char", "byte", "float", "double", "bool", "boolean",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "int8_t", "int16_t", "int32_t", "int64_t",
    "String", "Array", "word", "unsigned", "signed", "size_t", "ssize_t",
    "time_t", "ptrdiff_t", "wchar_t", "FILE",
))

# Symboles globaux Arduino : fonctions, constantes, objets (Serial, Wire, ...).
# Liste finie et stable — nouveaux ajouts faciles.
_ARDUINO_BUILTINS = frozenset((
    # Structure
    "setup", "loop",
    # IO pins
    "pinMode", "digitalWrite", "digitalRead", "analogWrite", "analogRead",
    "analogReference",
    # Timing
    "delay", "millis", "micros", "delayMicroseconds", "yield",
    # Communication
    "Serial", "Serial1", "Serial2", "Serial3", "SerialUSB",
    "Wire", "SPI", "EEPROM",
    "begin", "end", "print", "println", "printf", "write", "read",
    "available", "flush", "peek", "setTimeout",
    # Interruptions
    "attachInterrupt", "detachInterrupt", "digitalPinToInterrupt",
    "interrupts", "noInterrupts", "cli", "sei",
    # Pin / level constants
    "HIGH", "LOW", "INPUT", "OUTPUT", "INPUT_PULLUP", "INPUT_PULLDOWN",
    "CHANGE", "RISING", "FALLING",
    "LED_BUILTIN",
    "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7",
    "A8", "A9", "A10", "A11", "A12", "A13", "A14", "A15",
    # Math / util
    "map", "constrain", "min", "max", "abs", "pow", "sqrt", "sq",
    "sin", "cos", "tan", "exp", "log",
    "random", "randomSeed",
    "tone", "noTone", "pulseIn", "pulseInLong", "shiftIn", "shiftOut",
    # Bits
    "bit", "bitRead", "bitWrite", "bitSet", "bitClear",
    "lowByte", "highByte",
    # Characters
    "isAlpha", "isAlphaNumeric", "isAscii", "isControl", "isDigit",
    "isGraph", "isHexadecimalDigit", "isLowerCase", "isPrintable",
    "isPunct", "isSpace", "isUpperCase", "isWhitespace",
    # Memory
    "malloc", "calloc", "realloc", "free", "memcpy", "memset", "memmove",
    "strlen", "strcpy", "strcmp", "strcat", "strncpy", "strncmp", "strstr",
    "sprintf", "snprintf", "atoi", "atol", "atof",
))

_BUILTINS: frozenset[str] = _C_KEYWORDS | _C_TYPES | _ARDUINO_BUILTINS


# ── Regex: identifiers, declarations ─────────────────────────────────────────

# Standard C identifier: starts with letter/underscore, followed by word chars.
_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")

# `#define NAME ...` — global macro, equivalent to a declaration.
_DEFINE_RE = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\b")

# Global variable declaration:
#   [qualifiers]* <type> <name> [array] [= init] ;
# The qualifiers (static/const/volatile/extern) are absorbed, the type is
# captured (including `unsigned int` / `signed char`), the name is captured.
# The `.*` before `;` is greedy to eat everything else up to the last ;
# (allows complex initializations `= func(a, b)`).
_DECL_VAR_RE = re.compile(
    r"^\s*"
    r"(?:(?:static|const|volatile|extern|register|mutable)\s+)*"
    r"((?:unsigned\s+|signed\s+)?[A-Za-z_]\w*)"        # type (group 1)
    r"(?:\s*<[^>]+>)?"                                   # optional template args
    r"\s+"
    r"([A-Za-z_]\w*)"                                    # name (group 2)
    r"\s*(?:\[[^\]]*\])?"                                # optional array
    r"\s*(?:=[^;]*)?"                                    # optional init
    r";\s*$"
)

# Function declaration: prototype or definition.
#   [qualifiers]* <ret_type> <name> ( args ) ; | {
# We stop at `;` (prototype) or `{` (start of definition) at end of line.
_DECL_FUNC_RE = re.compile(
    r"^\s*"
    r"(?:(?:static|inline|extern|virtual)\s+)*"
    r"((?:unsigned\s+|signed\s+)?[A-Za-z_]\w*)"        # return type (group 1)
    r"(?:\s*<[^>]+>)?"                                   # template args
    r"\s+"
    r"([A-Za-z_]\w*)"                                    # name (group 2)
    r"\s*\([^)]*\)"                                      # ( args )
    r"\s*[;{].*$"                                        # `;` prototype or `{` opening (possibly a one-liner body closed on the same line)
)


# ── Data types exposed by the analyzer ───────────────────────────────────────

@dataclass
class DeclaredSymbol:
    """A symbol declared at the sketch's global scope.

    `owner_fid` is None for symbols in the scaffolding (setup/loop
    signatures for example) or declared by code that is not owned by any
    feature. Dependencies never propagate toward a None owner (shared
    symbol, not an inter-feature dependency).
    """
    name: str
    kind: str              # "var" | "func" | "define"
    type: str = ""         # Arduino type for vars, return type for funcs
    line: int = -1         # 0-indexed line number where the symbol is declared
    owner_fid: str | None = None


@dataclass
class AnalysisResult:
    """Result of a static analysis.

    `symbols`: dict {name -> DeclaredSymbol}, indexed by name. If a name
    is redeclared (rare), the last declaration wins.

    `graph`: {fid -> {other_fid that declares a symbol used by fid}}.
    Each fid in `lines_by_fid` has an entry, possibly empty.

    `exports_by_fid`: {fid -> [DeclaredSymbol]} — what each feature
    declares at the global scope. Useful to reconstruct
    `Function.exports` without querying the AI.
    """
    symbols:        dict[str, DeclaredSymbol]          = field(default_factory=dict)
    graph:          dict[str, set[str]]                = field(default_factory=dict)
    exports_by_fid: dict[str, list[DeclaredSymbol]]    = field(default_factory=dict)


# ── Preprocessing: strip comments + strings ──────────────────────────────────

def _sanitize_line(line: str, in_block: bool) -> tuple[str, bool]:
    """Strip C/C++ comments AND string/char literals from a line.

    Characters inside `"..."` or `'...'` are removed so they are NOT
    tokenized as identifiers later. `//` comments stop the rest of the
    line; multi-line `/* ... */` blocks are handled via the `in_block`
    flag.

    Returns (cleaned_line, in_block_after).
    """
    out: list[str] = []
    in_string = False
    in_char = False
    j = 0
    n = len(line)
    while j < n:
        c = line[j]
        if in_block:
            if c == "*" and j + 1 < n and line[j + 1] == "/":
                in_block = False
                j += 2
                continue
            j += 1
            continue
        if in_string:
            if c == "\\" and j + 1 < n:
                j += 2
                continue
            if c == '"':
                in_string = False
            j += 1
            continue
        if in_char:
            if c == "\\" and j + 1 < n:
                j += 2
                continue
            if c == "'":
                in_char = False
            j += 1
            continue
        # Normal code mode
        if c == '"':
            in_string = True
            j += 1
            continue
        if c == "'":
            in_char = True
            j += 1
            continue
        if c == "/" and j + 1 < n:
            if line[j + 1] == "/":
                break  # end-of-line comment
            if line[j + 1] == "*":
                in_block = True
                j += 2
                continue
        out.append(c)
        j += 1
    return "".join(out), in_block


# ── Declaration detection ────────────────────────────────────────────────────

def _detect_declaration(
    line: str, line_idx: int, owner: str | None
) -> DeclaredSymbol | None:
    """Try to match a global declaration on an already sanitized line
    (without comments or strings). Returns None if nothing matches or if
    the captured "type" is actually a C keyword (e.g. `if`, `return`) —
    a heuristic that avoids false positives on control statements.
    """
    m = _DEFINE_RE.match(line)
    if m:
        return DeclaredSymbol(
            name=m.group(1), kind="define", line=line_idx, owner_fid=owner,
        )
    m = _DECL_FUNC_RE.match(line)
    if m:
        type_, name = m.group(1).strip(), m.group(2)
        # Defensive rejection: `if (x) {` should normally not match the
        # func form (no name between `if` and `(`), but we double-check in
        # case the regex evolves. `void` is NOT rejected: it is a
        # legitimate return type.
        if type_ in _CONTROL_KEYWORDS:
            return None
        return DeclaredSymbol(
            name=name, kind="func", type=type_, line=line_idx, owner_fid=owner,
        )
    m = _DECL_VAR_RE.match(line)
    if m:
        type_, name = m.group(1).strip(), m.group(2)
        if type_ in _CONTROL_KEYWORDS:
            return None
        return DeclaredSymbol(
            name=name, kind="var", type=type_, line=line_idx, owner_fid=owner,
        )
    return None


# ── Public entry point ───────────────────────────────────────────────────────

def analyze_code(
    code: str,
    lines_by_fid: dict[str, Iterable[int]],
) -> AnalysisResult:
    """Static analysis of an Arduino sketch's code.

    `code`: the .ino content after stripping markers (what is visible to
    the user and compiled by arduino-cli).
    `lines_by_fid`: {internal fid -> iterables of 0-indexed line numbers
    owned by this feature}.

    Returns an AnalysisResult with each feature's exports, the dependency
    graph, and the global symbol table.
    """
    # 1) Reverse map line -> fid (to attribute declarations to their owner
    #    and detect cross-feature usages).
    line_to_fid: dict[int, str] = {}
    for fid, lines in lines_by_fid.items():
        for ln in lines:
            line_to_fid[ln] = fid

    # 2) Line-by-line sanitization following the `in_block` flag for the
    #    multi-line /* ... */. We keep the line count unchanged so the
    #    indices match `lines_by_fid`.
    raw_lines = code.splitlines()
    sanitized: list[str] = []
    in_block = False
    for line in raw_lines:
        s, in_block = _sanitize_line(line, in_block)
        sanitized.append(s)

    # 3) Detection of global declarations following the brace depth. We
    #    check `depth == 0` BEFORE updating the depth with the current
    #    line's braces, so that the line `void foo() {` is considered
    #    global (it opens a function but the declaration itself is at
    #    scope 0).
    symbols: dict[str, DeclaredSymbol] = {}
    exports_by_fid: dict[str, list[DeclaredSymbol]] = {}
    depth = 0
    for i, sline in enumerate(sanitized):
        if depth == 0:
            owner = line_to_fid.get(i)
            sym = _detect_declaration(sline, i, owner)
            if sym is not None:
                symbols[sym.name] = sym
                if owner is not None:
                    exports_by_fid.setdefault(owner, []).append(sym)
        depth += sline.count("{") - sline.count("}")
        if depth < 0:
            depth = 0  # robustness: malformed code must not break us

    # 4) Usage detection: for each line owned by a feature, we extract the
    #    identifiers and record a dependency on the owner of the symbols
    #    that come from ANOTHER feature. Unknown identifiers (external
    #    libs, local vars) are ignored.
    graph: dict[str, set[str]] = {fid: set() for fid in lines_by_fid}
    for i, sline in enumerate(sanitized):
        owner = line_to_fid.get(i)
        if owner is None:
            continue  # scaffolding line: we don't track its usages
        for match in _IDENT_RE.finditer(sline):
            name = match.group(1)
            if name in _BUILTINS:
                continue
            sym = symbols.get(name)
            if sym is None:
                continue  # external identifier or local var — not a dep
            if sym.owner_fid is None:
                continue  # declared by the scaffolding — shared resource
            if sym.owner_fid == owner:
                continue  # the feature uses its own symbol
            graph[owner].add(sym.owner_fid)

    return AnalysisResult(
        symbols=symbols, graph=graph, exports_by_fid=exports_by_fid,
    )


# ── Unit tests (direct execution: `python ui/code_analyzer.py`) ──────────────

if __name__ == "__main__":
    def assert_eq(got, want, label):
        if got != want:
            raise AssertionError(f"{label}: got {got!r}, want {want!r}")
        print(f"  OK {label}")

    # Scenario 1: f1 declares a button, f2 lights a LED based on the button.
    code = """#define BUTTON_PIN 2
#define LED_PIN 5

bool button_pressed = false;

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  Serial.begin(9600);
}

void readButton() {
  button_pressed = !digitalRead(BUTTON_PIN);
}

void updateLED() {
  digitalWrite(LED_PIN, button_pressed ? HIGH : LOW);
}

void loop() {
  readButton();
  updateLED();
}
"""
    # Lines 0..20 (21 lines). Distributed:
    #   f1 = readButton() (lines 0, 3, 11, 12, 13: #define BUTTON_PIN,
    #        bool button_pressed, void readButton() {, body, })
    #   f2 = updateLED() (lines 1, 15, 16, 17: #define LED_PIN, void
    #        updateLED() {, body, })
    # The setup()/loop() remain scaffolding.
    # To keep it simple I set simpler ranges:
    lines_by_fid = {
        "f1": [0, 3, 11, 12, 13],      # BUTTON_PIN, button_pressed, readButton
        "f2": [1, 15, 16, 17],          # LED_PIN, updateLED
    }
    r = analyze_code(code, lines_by_fid)

    print("Scenario 1 — bouton/LED")
    assert_eq(sorted(r.exports_by_fid.keys()), ["f1", "f2"], "exports keys")
    f1_names = sorted(s.name for s in r.exports_by_fid["f1"])
    assert_eq(f1_names, ["BUTTON_PIN", "button_pressed", "readButton"], "f1 exports")
    f2_names = sorted(s.name for s in r.exports_by_fid["f2"])
    assert_eq(f2_names, ["LED_PIN", "updateLED"], "f2 exports")
    # f2 uses button_pressed (declared by f1) and LED_PIN (declared by f2):
    # the dep goes from f2 to f1.
    assert_eq(r.graph["f2"], {"f1"}, "f2 depend de f1")
    assert_eq(r.graph["f1"], set(), "f1 independant")

    # Scenario 2: a symbol in a string literal does NOT count.
    code2 = """int myvar = 0;
void setup() { Serial.println("myvar"); }
void feature() { myvar = 1; }
"""
    r2 = analyze_code(code2, {"fA": [0], "fB": [2]})
    # "myvar" in the println string is not captured (sanitize removes the
    # content of strings). fB uses myvar (declared by fA) -> dep.
    print("Scenario 2 — string literal ignore")
    assert_eq(r2.graph["fB"], {"fA"}, "fB depend de fA")
    # setup() is owned by nobody so it does not generate a dep.

    # Scenario 3: `if (x) {` does not match as a function declaration.
    code3 = """int x = 0;
void foo() {
  if (x) {
    x = 1;
  }
}
"""
    r3 = analyze_code(code3, {"fA": [0], "fB": [1, 2, 3, 4, 5]})
    names = sorted(s.name for s in r3.exports_by_fid.get("fB", []))
    print("Scenario 3 — `if` non detecte comme func")
    assert_eq(names, ["foo"], "fB expose foo uniquement (pas `if`)")

    # Scenario 4: static function at the start of a line.
    code4 = """static int counter = 0;
void incr() { counter++; }
"""
    r4 = analyze_code(code4, {"fA": [0, 1]})
    names = sorted(s.name for s in r4.exports_by_fid["fA"])
    print("Scenario 4 — qualifiers (static, const)")
    assert_eq(names, ["counter", "incr"], "counter et incr exposes")

    # Scenario 5: multi-line comment that spans across.
    code5 = """int real_var = 1;
/* ceci est un
   commentaire qui contient fake_var
   et aussi other_fake
*/
int useful = 2;
"""
    r5 = analyze_code(code5, {"fA": [0, 1, 2, 3, 4, 5]})
    names = sorted(s.name for s in r5.exports_by_fid["fA"])
    print("Scenario 5 — commentaire multi-ligne")
    assert_eq(names, ["real_var", "useful"], "variables fake dans commentaire ignorees")

    print("\nTous les tests passent.")
