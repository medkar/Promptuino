"""Projection of the three component populations onto ONE ComponentInfo descriptor.

The "Composants" tab aggregates:
- what the USER declared (`components.json`) -- editable;
- the curated component REGISTRY (`ui/component_registry.py`) -- read-only,
  each entry pointing at the corpus documents (if any) that describe it;
- components the app had to GUESS a library for (`ui/registry_lookup.py`'s
  lookup cache, unioned with the user's own choices in `ui/component_libs.py`)
  -- read-only except for the library itself. Added 2026-08-03: without this
  third population a guessed component lived in NO screen at all (neither
  declared nor in the registry), so the ephemeral info banner was the only
  place it ever existed.

A ComponentInfo answers two questions along three-state axes: can the app DRAW
this component (`wiring`) and does it need a library, and if so is one known
(`library`)? The old two booleans (`generable`, `drawable`) lied: "generable"
meant "a library entry exists", classifying a plain LDR as "not generable"
when a bare `analogRead` is all it needs.

Pure module: no Qt. It reads the in-memory declared registry and the
accessors of `rag` / `component_registry` / `component_catalog` /
`registry_lookup` / `component_libs`, never a file directly. That keeps it
deterministic in tests and keeps the view thin.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

ORIGIN_DECLARED = "declared"
ORIGIN_CORPUS = "corpus"
ORIGIN_WIRING = "wiring"
ORIGIN_LOOKED_UP = "looked_up"


@dataclass(frozen=True)
class ComponentInfo:
    key: str                      # stable identity: registry id or declared id
    name: str
    lib: str                      # library name, "" when there is none
    origin: str                   # ORIGIN_*
    editable: bool
    pin_count: int                # meaningful only when wiring == "known"
    wiring: str                   # "known" | "unknown" | "none"
    library: str                  # "known" | "unknown" | "none"
    description: str = ""
    keywords: tuple[str, ...] = ()


def _declared_components() -> list[ComponentInfo]:
    from .declared_components import registry
    return [
        ComponentInfo(
            key=c.id, name=c.name, lib=c.lib, origin=ORIGIN_DECLARED,
            editable=True, pin_count=len(c.pins),
            wiring="known",
            library="known" if c.lib else "unknown",   # "lib to determine"
            keywords=tuple(c.keywords),
        )
        for c in registry()
    ]


def _library_state(comp, doc: dict | None) -> tuple[str, str]:
    """(state, library name) for a registry component.

    Three states mirroring the wiring axis, because the old boolean lied: it
    said "the app can code this", it meant "a library entry exists". An LDR
    needs no library at all -- that is `none`, not a failure. The registry's
    own fields carry the same three states: `lib_name` set -> `known`,
    `lib_to_determine` -> `unknown`, neither -> `none` -- true for an LDR, a
    lie the tab used to tell for a BMP180.

    PRECEDENCE (settled 2026-08-12, tache 3 of #44): a registry field that is
    SET wins over the corpus document. The corpus is frozen -- its embedding
    matrix is aligned by position, so a wrong value cannot be corrected in
    place -- while the registry is the curated identity layer, editable by
    design. `sd_card` is the case that settled it: the `sd` document carries
    `arduino_lib_name: null`, so the card announced "no library to install"
    for a component that needs `#include <SD.h>`. Reading the document first
    would make these fields dead code for every component that HAS one, and
    would keep repeating a defect nobody is allowed to fix at the source.
    """
    if comp.lib_name:
        return ("known", comp.lib_name)
    if comp.lib_to_determine:
        return ("unknown", "")
    if doc is None:
        return ("none", "")
    lib = str(doc.get("arduino_lib_name") or "").strip()
    return (("known", lib) if lib else ("none", ""))


def _corpus_docs_by_id() -> dict[str, dict]:
    from .rag import all_corpus_entries
    return {str(e.get("id")): e for e in all_corpus_entries() if e.get("id")}


def _registry_components(lang: str) -> list[ComponentInfo]:
    """Every curated component, projected from `component_registry`.

    `origin` mirrors PROVENANCE, not usefulness: a registry entry with no
    document at all (a bare LED, a push-button... -- the six catalog types
    with nothing to reference) is ORIGIN_WIRING; one with at least one
    document -- whether or not that document carries a library -- is
    ORIGIN_CORPUS.

    `lang` only picks which language `_label` renders the name in -- this
    module stays Qt-free and lang_manager-free, the caller decides. Names
    have a SECOND source: a type absent from `_TYPE_LABEL` takes its curated
    label from `replacement_catalog.label_of`, which `lang` does not affect
    (that catalog is language-neutral by documented stance: proper nouns,
    identical fr/en/es/it).
    """
    from .component_registry import registry as reg_registry
    from .wiring.layout.component_catalog import CATALOG
    from .wiring.instructions import _TYPE_LABEL, _label
    from .wiring.replacement_catalog import label_of
    docs = _corpus_docs_by_id()
    out: list[ComponentInfo] = []
    for comp in reg_registry():
        doc = docs.get(comp.default_document) if comp.documents else None
        library, lib = _library_state(comp, doc)
        entry = CATALOG.get(comp.id)
        pin_count = entry.pin_count if (comp.wiring == "known"
                                        and entry is not None) else 0
        # `_label` is never falsy -- absent from `_TYPE_LABEL` it returns the
        # RAW id, so membership decides the fallback: a type the replacement
        # catalog knows takes its curated label ("BMP180 (baromètre)"), never
        # the bare slug.
        name = (_label(comp.id, lang) if comp.id in _TYPE_LABEL
                else label_of(comp.id) or comp.id)
        out.append(ComponentInfo(
            key=comp.id,
            name=name,
            lib=lib,
            origin=ORIGIN_CORPUS if comp.documents else ORIGIN_WIRING,
            editable=False,
            pin_count=pin_count,
            wiring=comp.wiring,
            library=library,
            # Same precedence as `_library_state` above: a registry field
            # that is set wins over the frozen corpus document.
            description=(comp.description
                         or (str(doc.get("description") or "") if doc else "")),
            keywords=comp.keywords,
        ))
    return out


def _looked_up_components() -> list[ComponentInfo]:
    """Components the app had to GUESS a library for.

    Third origin, added 2026-08-03: such a component is neither declared nor in
    the curated registry, so without this it appeared in no screen at all and
    the user had no card to come back to.

    Source = the lookup cache UNION the user's preferences. An entry that was
    only guessed comes from the cache and may be evicted; one the user chose a
    library for lives in `component_libs` and never disappears.
    """
    from .component_libs import registry as libs_registry
    from .registry_lookup import cached_lookups
    cached = cached_lookups()
    prefs = libs_registry()
    out: list[ComponentInfo] = []
    for token in [*cached, *(t for t in prefs if t not in cached)]:
        rec = cached.get(token)
        if not isinstance(rec, dict):
            # A hand-edited or buggy-build cache file can hold a malformed
            # value for one token; `_cache_get` already rejects that shape for
            # the generation path (`isinstance(rec, dict)` guard) -- this view
            # must degrade the same way rather than crash the whole tab on it.
            rec = {}
        entry = rec.get("entry") if isinstance(rec.get("entry"), dict) else {}
        # The user's choice wins over the cached guess: that is the whole point
        # of this chantier.
        lib = prefs.get(token) or str(rec.get("lib_name") or "").strip()
        out.append(ComponentInfo(
            key=token,
            # Nommée d'après le TOKEN, pas d'après l'entrée trouvée : celle-ci
            # est fabriquée à la volée et porte le nom de la LIBRAIRIE, si
            # bien que la carte s'appelait « DevLab_VEML7700 » pour un
            # composant que l'utilisateur appelle VEML7700 — et la librairie
            # est déjà écrite sur sa propre ligne, juste en dessous. Le token
            # est ce que l'utilisateur a écrit : c'est ce que l'app sait de
            # plus proche d'un nom de composant (QA I4, 2026-08-08).
            name=_token_as_name(token),
            lib=lib,
            origin=ORIGIN_LOOKED_UP,
            editable=False,
            pin_count=0,
            wiring="unknown",        # guessed: no catalog footprint
            library="known" if lib else "unknown",
            description=str(entry.get("description") or ""),
            keywords=(token,),
        ))
    return out


def build_index(lang: str = "fr") -> list[ComponentInfo]:
    """All three populations, deduplicated by `key`, declared entries first.

    Precedence is deliberate: a DECLARED entry shadows a registry entry of the
    same key, which in turn shadows a looked-up one -- otherwise the user
    could no longer edit a component they described themselves, or lose the
    ability to arbitrate a guess once it happens to match a curated entry's id.

    `lang` only affects the registry entries' `name` (defaults to "fr" so
    existing callers -- tests -- keep working unchanged).
    """
    seen: set[str] = set()
    out: list[ComponentInfo] = []
    for info in (*_declared_components(), *_registry_components(lang),
                 *_looked_up_components()):
        fp = _dedup_key(info)
        if fp in seen:
            continue
        seen.add(fp)
        out.append(info)
    return out


def _token_as_name(token: str) -> str:
    """Nom lisible à partir du jeton de recherche.

    Un numéro de pièce s'écrit en capitales (`veml7700` → « VEML7700 ») ; un
    nom en plusieurs mots garde sa casse de mots (`grove ultrasonic ranger` →
    « Grove Ultrasonic Ranger »), le tout-capitales y crierait.
    """
    t = (token or "").strip()
    if not t:
        return t
    return t.upper() if " " not in t else t.title()


def _dedup_key(info: ComponentInfo) -> str:
    """Identité d'une fiche pour le dé-doublonnage.

    La clé brute ne suffit pas : un composant DÉCLARÉ porte un slug
    (`grove-ultrasonic-ranger`) tandis que sa recherche au registre est
    mémorisée sous le token du prompt (`grove ultrasonic ranger`). Les deux
    ne diffèrent que par le séparateur, donc l'égalité de chaîne les laissait
    passer et le même composant apparaissait DEUX fois — une fois éditable,
    une fois devinée (QA G3, 2026-08-08). On compare sur une forme repliée :
    minuscules, et tirets/espaces/soulignés retirés.
    """
    return "".join(ch for ch in info.key.lower()
                   if ch not in "-_ ")


def _fold(text: str) -> str:
    """Lowercase + strip accents, for accent-insensitive search.

    Local on purpose, like `declared_components._keyword_hit`: importing
    `picker_logic._fold` would drag `ui.wiring` into this module, whose whole
    contract is to stay pure. Three lines of stdlib beat that coupling.

    NFD rather than the fixed table of `declared_components`: the registry's
    1311 keywords are written WITHOUT accents by convention, so the folding
    only ever has to run on what the USER types — and a user types whatever
    their keyboard produces, not a curated set of fifteen characters.
    """
    nfd = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in nfd if not unicodedata.combining(ch))


def filter_components(components: list[ComponentInfo], query: str = "",
                      kind: str = "all") -> list[ComponentInfo]:
    """Filter by free text and by kind. Kinds are DERIVED from the two
    three-state axes, they carry no logic of their own: `declared` =
    editable, `with_library` = a library is known, `drawable` = the pinout
    is known.

    The text search folds accents on BOTH sides. Measured 2026-08-18 before
    the fix: « température » returned 6 components, « temperature » returned
    16. The display NAMES are translated and carry their accents, so the
    accented query matched those; the 1311 registry keywords are stored
    unaccented (`capteur de temperature`) and were unreachable. The search was
    therefore not empty but SILENTLY PARTIAL — worse than a visible failure,
    since 6 plausible results look like the whole answer.
    """
    out = list(components)
    if kind == "declared":
        out = [c for c in out if c.editable]
    elif kind == "with_library":
        out = [c for c in out if c.library == "known"]
    elif kind == "drawable":
        out = [c for c in out if c.wiring == "known"]
    q = _fold(query).strip()
    if q:
        out = [c for c in out
               if q in _fold(c.name)
               or q in _fold(c.lib)
               or q in _fold(c.key)
               or any(q in _fold(k) for k in c.keywords)]
    return out
