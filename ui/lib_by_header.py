"""Which Arduino library provides a given `#include` header.

`arduino_cli._extract_unknown_libs` used to derive the library NAME from the
header stem (`Servo.h` -> "Servo"). That works for most libraries and fails
silently for every one whose registry name does not contain its header stem.

Measured case (QA J1, 2026-08-10): `Adafruit_MCP23X17.h` is provided by
"Adafruit MCP23**0**17 Arduino Library" -- one character apart. The derived
query "Adafruit MCP23X17" returns ZERO results from `arduino-cli lib search`,
the library is never installed, compilation fails on a missing header, and the
whole generation is reverted. Searching by header is not an option either:
`lib search` does not index `provides_includes` (the field comes back empty
until a library is installed).

The answer was already in the app, in three stores, none of which was asked:

  1. the user's DECLARED components (`components.json`) -- their own statement,
     and where their library choice lives for a declared component;
  2. the registry lookup CACHE -- what was resolved for an out-of-corpus part
     number, including a library the user picked by hand;
  3. the RAG CORPUS (`assets/rag/corpus.json`) -- 82 of its 91 documents carry
     both `headers` and `arduino_lib_name`.

Order = most specific first: a user's own decision beats a curated default.

Pure Python: no Qt. Imports are function-local on purpose -- `registry_lookup`
imports `arduino_cli`, which is this module's consumer, so a module-level
import would close the cycle.
"""
from __future__ import annotations


def _norm(header: str) -> str:
    """Base file name, lowercased: `Adafruit/Foo.h` and `foo.h` are one key."""
    return (header or "").replace("\\", "/").rsplit("/", 1)[-1].strip().lower()


def _from_declared(key: str) -> str:
    from .declared_components import registry
    for comp in registry():
        if not comp.lib:
            continue
        if any(_norm(h) == key for h in (comp.headers or ())):
            return comp.lib
    return ""


def _from_cache(key: str) -> str:
    from .registry_lookup import cached_lookups
    for record in (cached_lookups() or {}).values():
        if not isinstance(record, dict):
            continue
        entry = record.get("entry")
        headers = entry.get("headers") or [] if isinstance(entry, dict) else []
        if any(_norm(h) == key for h in headers):
            return str(record.get("lib_name") or "").strip()
    return ""


def _from_corpus(key: str) -> str:
    """Corpus documents, restricted to each entry's FIRST header.

    A corpus entry lists its own header first, then its COMPANIONS -- headers
    that belong to a different library (`Adafruit_GFX.h` under `adafruit-ssd1306`,
    `Adafruit_Sensor.h` under `adafruit-bme280`, `OneWire.h` under
    `dallas-temperature`). Mapping a companion to the entry's library name would
    be simply wrong. Verified on the 91 documents (2026-08-10): every header
    whose stem is absent from its entry's library name is either FIRST (5 real
    cases, `mcp23017`, `tm1637`, `max30102`, `st7789`, `adxl345`) or a companion
    (8 cases, all of which the stem heuristic resolves on its own -- "Adafruit
    GFX" finds the GFX library, "OneWire" finds OneWire).

    The restriction is corpus-only. A declared component's headers and a cache
    record's headers all genuinely come from the one library they are stored
    with (`provides_includes` of the library that was installed).
    """
    from .rag import all_corpus_entries
    for entry in all_corpus_entries():
        if not isinstance(entry, dict):
            continue
        headers = entry.get("headers") or []
        if headers and _norm(headers[0]) == key:
            return str(entry.get("arduino_lib_name") or "").strip()
    return ""


def lib_name_for_header(header: str) -> str:
    """Registry name of the library providing `header`, "" when unknown.

    "" is not a failure: the caller keeps its stem heuristic, which covers the
    majority of libraries. This only fills the gap where the two names differ.

    Never raises -- a broken store must not stop a compilation, it must fall
    back to the heuristic that was there before.
    """
    key = _norm(header)
    if not key:
        return ""
    for source in (_from_declared, _from_cache, _from_corpus):
        try:
            name = source(key)
        except Exception:
            name = ""
        if name:
            return name
    return ""
