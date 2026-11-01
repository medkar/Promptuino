"""Lexical dependency graph between features (pure module, no Qt).

Feeds the transfer popup (spec 2026-07-06): a feature B *depends on* a
feature A when B references a name (global variable, #define, function)
that A provides. Used for:
  - drag solidarity: dragging a consumer carries its dependency closure;
  - the drawn links between cards;
  - the reorder constraint (a consumer must stay below its providers,
    because C++ forbids referencing a global declared further down).

Semantics aligned with the assembler dedup ("first emitter owns the name",
cf. assemble_with_map): when several features declare the same name, only
the FIRST one (list order) is the provider — the others *consume* its
declaration (their duplicate line is dropped at assembly).

Detection is lexical over the Feature model (global_lines/setup/loop/
functions), NOT over the editor text: manual edits or auto-repairs that
diverged from the model are invisible here (assumed limit of the spec).
"""
from __future__ import annotations

import re

from .assembler import _BODY_DECL_RE, _DECL_CONTROL_WORDS
from .feature_model import (
    Feature, _C_KEYWORDS, _DEFINE_RE, _GLOBAL_NAME_RE,
)

# Names shorter than this are ignored (loop indices `i`, flags `ok`…):
# too generic, they would create bogus links on every feature.
_MIN_NAME_LEN = 3


def providers(feature: Feature) -> set[str]:
    """Names PROVIDED by the feature: global identifiers (variables/objects),
    #define constants, and function names. Filtered by _MIN_NAME_LEN."""
    names: set[str] = set()
    for line in feature.global_lines:
        m = _DEFINE_RE.search(line)
        if m:
            names.add(m.group(1))
            continue
        for gm in _GLOBAL_NAME_RE.finditer(line):
            tok = gm.group(1)
            if tok not in _C_KEYWORDS:
                names.add(tok)
    for fn in feature.functions:
        if fn.name:
            names.add(fn.name)
    # Les VARIABLES LOCALES de `setup()`/`loop()` fournissent elles aussi un
    # nom (2026-08-31). Elles manquaient, et c'était un trou de la même
    # nature que celui du graphe des globales : les contributions de toutes
    # les fonctionnalités atterrissent dans LE MÊME corps de `loop()`, donc
    # une locale déclarée par A est visible — et consommable — par B. Depuis
    # que l'assembleur supprime la redéclaration dupliquée de B (sinon le
    # sketch ne compile pas), B consomme RÉELLEMENT celle de A : sans ce
    # fournisseur, aucun lien n'était dessiné, la solidarité de glisser ne
    # jouait pas, et rien n'empêchait de faire remonter B au-dessus de A —
    # ce qui ne compile plus (variable utilisée avant sa déclaration).
    #
    # Seule la profondeur 0 compte : une déclaration dans un `if` de A est
    # scopée à ce bloc et n'est visible de personne (même règle de
    # profondeur que la garde d'imbrication de l'assembleur).
    for body in (feature.setup_lines, feature.loop_lines):
        depth = 0
        for line in body:
            if depth == 0:
                m = _BODY_DECL_RE.match(line)
                if m and m.group(1) not in _DECL_CONTROL_WORDS:
                    names.add(m.group(2))
            depth += line.count("{") - line.count("}")
    return {n for n in names if len(n) >= _MIN_NAME_LEN}


def feature_deps(features: list[Feature]) -> dict[str, set[str]]:
    """For each feature id, the set of feature ids it DEPENDS on.

    Provider of a name = FIRST feature (list order) that declares it — same
    rule as the assembler dedup. Any other feature whose text references the
    name (word boundary) depends on that provider, including a feature that
    re-declares the same name (its duplicate declaration is dropped at
    assembly, so it really consumes the provider's one)."""
    name_owner: dict[str, str] = {}
    for f in features:
        for name in providers(f):
            name_owner.setdefault(name, f.id)
    deps: dict[str, set[str]] = {f.id: set() for f in features}
    for f in features:
        text = f.all_text()
        for name, owner in name_owner.items():
            if owner == f.id:
                continue        # no self-dependency
            if re.search(rf"\b{re.escape(name)}\b", text):
                deps[f.id].add(owner)
    return deps


def dependency_closure(fid: str, deps: dict[str, set[str]]) -> set[str]:
    """Transitive closure of `fid`'s providers (providers of providers…).
    Does NOT include `fid` itself."""
    out: set[str] = set()
    stack = list(deps.get(fid, ()))
    while stack:
        cur = stack.pop()
        if cur in out or cur == fid:
            continue
        out.add(cur)
        stack.extend(deps.get(cur, ()))
    return out


def reorder_with_constraints(order: list[str], moved: str, new_index: int,
                             deps: dict[str, set[str]]) -> list[str]:
    """Move `moved` to `new_index` (position in the list WITHOUT the moved
    item), then repair dependency violations by sliding the linked block
    WITH the moved card (spec rule: "le bloc lié glisse ensemble"):

      - a fully legal move comes out exactly as requested;
      - dropping a consumer above its providers pulls those providers just
        above it, AT the drop position (internal order kept);
      - moving a provider below its consumers pushes those consumers just
        below it.

    One pass is sufficient: pulled providers only move up (never past their
    own providers — either pulled too, order kept, or already above the drop
    point), pushed consumers only move down (symmetric argument). Cycles
    (should not happen) are harmless: closures use a visited set and the
    block rebuild terminates by construction."""
    if moved not in order:
        return list(order)
    requested = [fid for fid in order if fid != moved]
    idx = max(0, min(int(new_index), len(requested)))
    requested.insert(idx, moved)
    pos = {fid: i for i, fid in enumerate(requested)}

    prov_closure = dependency_closure(moved, deps)
    # Transitive consumers of `moved` = features whose closure contains it.
    cons_closure = {fid for fid in requested
                    if fid != moved and moved in dependency_closure(fid, deps)}

    pulled = [fid for fid in requested
              if fid in prov_closure and pos[fid] > pos[moved]]
    pushed = [fid for fid in requested
              if fid in cons_closure and pos[fid] < pos[moved]]
    block = set(pulled) | set(pushed) | {moved}
    rest = [fid for fid in requested if fid not in block]
    # Anchor the block where `moved` was requested: count the rest-items
    # sitting before it.
    k = sum(1 for fid in rest if pos[fid] < pos[moved])
    return rest[:k] + pulled + [moved] + pushed + rest[k:]
