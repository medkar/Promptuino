"""Prototype: extract public API signatures from a C++ Arduino library header.

Usage: python scripts/extract_api_signatures.py <path/to/header.h> [<path2.h> ...]

Strategy (regex-based, sufficient for Arduino headers which follow a regular
pattern — no nested classes, no template metaprogramming, no fancy macros):
  1. Strip comments (// and /* */).
  2. Find each `class Foo ... { ... };` block and remember the class name.
  3. Within the class body, track section (public/protected/private — default
     is private for `class`, but public is what we want).
  4. In public sections, capture each declaration ending with `;` that looks
     like a function (has `(` before the `;`, after stripping `=` defaults).
  5. Normalize whitespace, drop default arg values for compactness.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _strip_comments(src: str) -> str:
    src = _BLOCK_COMMENT.sub("", src)
    src = _LINE_COMMENT.sub("", src)
    return src


def _strip_preprocessor(src: str) -> str:
    """Drop every `#`-line. Required before brace-matching: `#if/#else`
    branches frequently pair a `{` in one branch with a `}` in the other,
    which throws off naive depth counting (cf. PJRC Encoder).

    We replace each preprocessor line with a same-length blank to preserve
    offsets — not strictly required, but makes debug traces easier.
    """
    out = []
    i = 0
    n = len(src)
    while i < n:
        # Find start of line
        j = i
        # Skip leading spaces/tabs
        while j < n and src[j] in " \t":
            j += 1
        if j < n and src[j] == "#":
            # Replace whole line (including continuation lines ending with \)
            line_start = i
            while i < n and src[i] != "\n":
                i += 1
            # Handle line-continuations
            while line_start < i and src[i - 1] == "\\":
                i += 1  # past the newline
                while i < n and src[i] != "\n":
                    i += 1
            # Replace with blanks of same length
            blank_len = i - line_start
            out.append(" " * blank_len)
            if i < n:
                out.append("\n")
                i += 1
            continue
        # Otherwise, copy until end of line
        while i < n and src[i] != "\n":
            out.append(src[i])
            i += 1
        if i < n:
            out.append("\n")
            i += 1
    return "".join(out)


def _iter_class_bodies(src: str):
    """Yield (class_name, body) for each `class X ... { ... };`.

    Naive brace matcher — works as long as the header doesn't have nested
    classes (true for our Arduino libs). Preprocessor lines are stripped
    upstream by `extract()` before this is called.

    Fallback: if brace matching fails (typically when `#if/#else` branches
    duplicate methods so the count is off), we still yield a body that
    spans up to the next `^};` at column 0 — enough for the decl extractor
    to find public signatures even if some duplicates leak in.
    """
    pos = 0
    while True:
        m = re.search(r"\bclass\s+(\w+)[^{;]*\{", src[pos:])
        if not m:
            return
        class_name = m.group(1)
        start = pos + m.end()
        depth = 1
        i = start
        while i < len(src) and depth > 0:
            c = src[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        if depth == 0:
            body = src[start : i - 1]
            yield class_name, body
            pos = i
            continue
        # Fallback: find the next class-end pattern `^};` from start.
        end_m = re.search(r"^};", src[start:], re.MULTILINE)
        if end_m is None:
            return
        body = src[start : start + end_m.start()]
        yield class_name, body
        pos = start + end_m.end()


def _skip_to_eol(body: str, i: int) -> int:
    while i < len(body) and body[i] != "\n":
        i += 1
    return i


def _skip_balanced_braces(body: str, i: int) -> int:
    """Assumes body[i] == '{'. Returns index just after matching '}'."""
    depth = 0
    while i < len(body):
        c = body[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _extract_public_decls(body: str) -> list[str]:
    section = "private"  # `class` default
    out: list[str] = []
    buf = ""
    i = 0
    while i < len(body):
        # Skip preprocessor lines entirely (#if/#else/#endif/#define).
        if body[i] == "#":
            i = _skip_to_eol(body, i)
            continue
        # Section markers
        matched_section = False
        for kw in ("public:", "protected:", "private:"):
            if body[i:].startswith(kw):
                section = kw[:-1]
                i += len(kw)
                buf = ""
                matched_section = True
                break
        if matched_section:
            continue
        c = body[i]
        # Inline method body { ... } — capture the signature so far, skip body.
        if c == "{":
            j = _skip_balanced_braces(body, i)
            if section == "public":
                decl = buf.strip()
                if decl:
                    out.append(decl)
            buf = ""
            i = j
            # Optional trailing `;`
            while i < len(body) and body[i] in " \t\n\r":
                i += 1
            if i < len(body) and body[i] == ";":
                i += 1
            continue
        buf += c
        if c == ";":
            if section == "public":
                decl = buf[:-1].strip()
                if decl:
                    out.append(decl)
            buf = ""
        i += 1
    return out


def _looks_like_function(decl: str) -> bool:
    if "(" not in decl or ")" not in decl:
        return False
    # Skip pure data members, typedefs, enums, friend declarations.
    if decl.startswith(("typedef", "enum", "friend", "using")):
        return False
    return True


def _normalize(decl: str, class_name: str) -> str:
    # Collapse whitespace.
    decl = re.sub(r"\s+", " ", decl).strip()
    # Drop default arg values: replace ` = something` up to next `,` or `)`.
    # We do this iteratively to handle nested parens in defaults (rare).
    out = []
    depth = 0
    skip = False
    i = 0
    while i < len(decl):
        c = decl[i]
        if skip:
            if c == "(":
                depth += 1
            elif c == ")":
                if depth == 0:
                    skip = False
                    out.append(c)
                else:
                    depth -= 1
            elif c == "," and depth == 0:
                skip = False
                out.append(c)
            i += 1
            continue
        if c == "=" and depth == 0:
            skip = True
            i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        out.append(c)
        i += 1
    decl = "".join(out)
    decl = re.sub(r"\s+", " ", decl).strip()
    decl = decl.replace(" ,", ",").replace("( ", "(").replace(" )", ")")
    # Skip constructors/destructors of *other* classes (shouldn't happen but
    # defensive). Keep ctors/dtor of this class.
    return decl


def extract(headers: list[Path]) -> dict[str, list[str]]:
    """Return {class_name: [signature, ...]} aggregated across files.

    Duplicates within a class are removed (preserves first-seen order) — they
    happen with `#if ARDUINO >= 100 / #else` branches that declare the same
    function with two return types.
    """
    by_class: dict[str, list[str]] = {}
    for h in headers:
        raw = h.read_text(encoding="utf-8", errors="replace")
        src = _strip_preprocessor(_strip_comments(raw))
        for class_name, body in _iter_class_bodies(src):
            decls = _extract_public_decls(body)
            sigs = []
            for d in decls:
                if not _looks_like_function(d):
                    continue
                n = _normalize(d, class_name)
                # Filter operator overloads, internal-looking helpers.
                if "operator" in n:
                    continue
                sigs.append(n)
            if sigs:
                by_class.setdefault(class_name, []).extend(sigs)
    # Dedupe per class while preserving order.
    for cls, sigs in by_class.items():
        seen: set[str] = set()
        deduped: list[str] = []
        for s in sigs:
            if s in seen:
                continue
            seen.add(s)
            deduped.append(s)
        by_class[cls] = deduped
    return by_class


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    json_mode = False
    if args[0] == "--json":
        json_mode = True
        args = args[1:]
    headers = [Path(p) for p in args]
    result = extract(headers)
    if json_mode:
        import json as _json
        print(_json.dumps(result, indent=2, ensure_ascii=False))
        return
    total_sigs = 0
    for cls, sigs in result.items():
        print(f"\n## {cls} ({len(sigs)} signatures)")
        for s in sigs:
            print(f"  {s}")
        total_sigs += len(sigs)
    print(f"\n--- TOTAL: {total_sigs} signatures across {len(result)} classes ---")


if __name__ == "__main__":
    main()
