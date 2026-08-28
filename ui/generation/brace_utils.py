"""Low-level tools to analyze Arduino/C code while being insensitive to comments
and string literals (a '{' inside "..." or // ... does not count).

Everything is in char-offset on the raw string — no Qt dependency.
"""
import re


def strip_fences(text: str) -> str:
    """Removes a markdown fence ```lang ... ``` wrapping the whole text.
    No-op if the text is not fenced."""
    t = text.strip()
    if not t.startswith("```"):
        return text
    lines = t.split("\n")
    lines = lines[1:]                      # removes the ```lang line
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]                 # removes the final ``` line
    return "\n".join(lines)


def _skip_string(code: str, i: int) -> int:
    """Returns the index just after the string/char literal starting at `i`."""
    quote = code[i]
    i += 1
    n = len(code)
    while i < n:
        if code[i] == "\\":
            i += 2
            continue
        if code[i] == quote:
            return i + 1
        i += 1
    return i


def match_brace(code: str, open_idx: int) -> int | None:
    """Index of the '}' closing the '{' located at `open_idx`, insensitive to
    comments and strings. None if not balanced."""
    depth = 0
    i = open_idx
    n = len(code)
    while i < n:
        c = code[i]
        if c == "/" and i + 1 < n and code[i + 1] == "/":
            j = code.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and code[i + 1] == "*":
            j = code.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c in "\"'":
            i = _skip_string(code, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def iter_functions(code: str):
    """Iterates over the TOP-LEVEL function definitions.

    Yields tuples (name, sig_start, body_start, body_end, end):
      - name       : identifier of the function (before the '(')
      - sig_start  : index of the start of the signature (after the last
                     top-level ';' or '}', leading spaces included)
      - body_start : index just after the '{'
      - body_end   : index of the closing '}'
      - end        : index just after the '}'
    Insensitive to comments/strings. Ignores nested blocks.
    """
    n = len(code)
    i = 0
    depth = 0
    seg_start = 0
    while i < n:
        c = code[i]
        if c == "/" and i + 1 < n and code[i + 1] == "/":
            j = code.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and code[i + 1] == "*":
            j = code.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c in "\"'":
            i = _skip_string(code, i)
            continue
        if c == "#" and depth == 0:
            # Preprocessor directive (#include / #define / #ifdef …): a top-level
            # unit with NO ';' terminator. Without advancing seg_start past it,
            # an `#include` sitting directly before `void setup()` (no ';'
            # statement in between) gets absorbed into the function's signature
            # span (seg_start never moved) and is then carved away by the
            # parser — the generated sketch silently loses its includes. Treat
            # the whole directive line as its own segment.
            j = code.find("\n", i)
            i = n if j == -1 else j + 1
            seg_start = i
            continue
        if c == "{":
            if depth == 0:
                header = code[seg_start:i]
                m = re.search(r"([A-Za-z_]\w*)\s*\([^)]*\)\s*$", header)
                if m:
                    close = match_brace(code, i)
                    if close is not None:
                        yield (m.group(1), seg_start, i + 1, close, close + 1)
                        i = close + 1
                        seg_start = i
                        continue
            depth += 1
        elif c == "}":
            if depth > 0:
                depth -= 1
            if depth == 0:
                seg_start = i + 1
        elif c == ";":
            if depth == 0:
                seg_start = i + 1
        i += 1


def find_function_body(code: str, name: str):
    """Like iter_functions but for ONE named function. Returns the tuple
    (sig_start, body_start, body_end, end) or None if absent."""
    for fname, sig_start, body_start, body_end, end in iter_functions(code):
        if fname == name:
            return (sig_start, body_start, body_end, end)
    return None
