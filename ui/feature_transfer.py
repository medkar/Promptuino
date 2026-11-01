"""TransferStaging — staging model of the feature transfer popup (no Qt).

Holds DEEP COPIES of both feature lists (IA / stable) and encodes the whole
transfer semantics of the spec (2026-07-06): copy with silent twin update
(identity = id + ORIGIN prompt — the lineage, see transfer()), re-id on
collision, dependency closure carried along, delayed deletions (marks),
constrained reorder. The dialog is only a
view over this object; nothing touches the studio before the user confirms
and the dialog reads `result()`.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .generation.feature_model import Feature, next_feature_id, MANUAL_ID
from .generation.feature_links import (
    feature_deps, dependency_closure, reorder_with_constraints,
)

SIDES = ("ia", "stable")


def _norm_origin(f: Feature) -> str:
    """Normalized ORIGIN prompt (lineage key): lowercase, collapsed spaces."""
    return " ".join((f.first_prompt or "").split()).lower()


@dataclass
class TransferRecap:
    """Counts shown in the live recap line and the confirm dialog."""
    transfers: int = 0
    deletions: int = 0
    reordered_ia: bool = False
    reordered_stable: bool = False
    # (side, consumer_fid, deleted_provider_fid) — the consumer survives but
    # references a name whose provider is marked deleted on the same side.
    warnings: list = field(default_factory=list)


class TransferStaging:
    def __init__(self, features_ia: list[Feature],
                 features_stable: list[Feature]):
        self.ia: list[Feature] = [copy.deepcopy(f) for f in features_ia]
        self.stable: list[Feature] = [copy.deepcopy(f) for f in features_stable]
        self._deleted: dict[str, set[str]] = {"ia": set(), "stable": set()}
        # (dst_side, fid_in_dst) of every feature copied/updated by a
        # transfer — recap counts unique arrivals, not drag gestures.
        self._transferred: set[tuple[str, str]] = set()
        self._reordered: dict[str, bool] = {"ia": False, "stable": False}
        # Destination sides that received a full "transfer all" snapshot
        # (IA→stable and/or stable→IA). Set (not bool) so both directions can
        # be tracked independently.
        self._transferred_all: set[str] = set()

    # ── Introspection ──────────────────────────────────────────
    def features(self, side: str) -> list[Feature]:
        return self.ia if side == "ia" else self.stable

    def deps(self, side: str) -> dict[str, set[str]]:
        return feature_deps(self.features(side))

    def group_for(self, fid: str, side: str) -> list[str]:
        """The dragged feature + its dependency closure, in display order
        (providers first — source list order keeps providers above)."""
        members = dependency_closure(fid, self.deps(side)) | {fid}
        return [f.id for f in self.features(side) if f.id in members]

    def is_deleted(self, fid: str, side: str) -> bool:
        return fid in self._deleted[side]

    # ── Mutations ──────────────────────────────────────────────
    def transfer(self, fid: str, src: str, dst: str, index: int) -> None:
        """Copy `fid` + its dependency closure from `src` to `dst`, inserting
        at `index` (position in the dst list as displayed). Twins are updated
        in place; id collisions get a fresh id; a dst delete mark on a
        travelling member is lifted. Source untouched.

        Twin identity = the LINEAGE (normalized origin prompt, first_prompt) —
        NOT the full prompt history (an evolved copy must overwrite its
        counterpart: IA corrected -> stable, stable -> IA to revert), and NOT
        the id alone. Two-step match:
          1. same id + same origin -> update in place;
          2. same origin, DIFFERENT id -> update in place, KEEPING the
             destination id. Rescues windows whose id spaces diverged —
             notably projects poisoned by earlier re-id copies (pre-fix
             2026-07-06), where the same lineage lives under another id.
        A same-id feature with a DIFFERENT origin (recycled id after a
        project reset: LED vs servo) is a different feature -> re-id, not
        replace."""
        if src == dst:
            return
        src_list, dst_list = self.features(src), self.features(dst)
        by_id_src = {f.id: f for f in src_list}
        insert_at = max(0, min(int(index), len(dst_list)))
        for gid in self.group_for(fid, src):
            member = by_id_src.get(gid)
            if member is None:
                continue
            clone = copy.deepcopy(member)
            # `manual` is a per-window SINGLETON (the hand-edit bucket): MERGE
            # into the destination's manual (or create it), never overwrite,
            # never duplicate. Skips the twin/collision logic entirely (#31).
            if clone.id == MANUAL_ID:
                self._merge_manual(clone, dst_list)
                self._deleted[dst].discard(MANUAL_ID)
                self._transferred.add((dst, MANUAL_ID))
                continue
            origin = _norm_origin(clone)
            twin = next((i for i, f in enumerate(dst_list)
                         if f.id == clone.id
                         and _norm_origin(f) == origin), None)
            if twin is None and origin:
                twin = next((i for i, f in enumerate(dst_list)
                             if _norm_origin(f) == origin), None)
            if twin is not None:
                # Silent update in place; the DESTINATION keeps its id (and
                # thus its color/persistence identity).
                clone.id = dst_list[twin].id
                dst_list[twin] = clone
            elif any(f.id == clone.id for f in dst_list):
                clone.id = next_feature_id(dst_list)       # collision re-id
                dst_list.insert(insert_at, clone)
                insert_at += 1
            else:
                dst_list.insert(insert_at, clone)
                insert_at += 1
            self._deleted[dst].discard(clone.id)           # it travels
            self._transferred.add((dst, clone.id))

    def _merge_manual(self, clone: Feature, dst_list: list[Feature]) -> None:
        """Merge a travelling `manual` feature into the destination's manual
        bucket (created — appended last — if absent). Only the NOVELTY is added,
        dedup'd against the existing manual: includes by string, globals by
        declared name (else code signature), setup/loop bodies by code
        signature, functions by name. So a back-and-forth drag is IDEMPOTENT.
        (clean_feature_contributions can't be reused: it KEEPS isolated shared
        lines like a bare `delay()`, which would duplicate on re-merge.)"""
        dst = next((f for f in dst_list if f.id == MANUAL_ID), None)
        if dst is None:
            dst_list.append(clone)               # first manual on this side
            return
        from .generation.feature_model import declared_name
        from .generation.assembler import _code_sig
        inc = {i.strip() for i in dst.includes}
        for i in clone.includes:
            if i.strip() not in inc:
                dst.includes.append(i); inc.add(i.strip())
        gnames = {declared_name(g) for g in dst.global_lines}
        gsigs = {_code_sig(g) for g in dst.global_lines if _code_sig(g)}
        for g in clone.global_lines:
            nm = declared_name(g)
            if nm is not None:
                if nm in gnames:
                    continue
                gnames.add(nm)
            elif _code_sig(g) and _code_sig(g) in gsigs:
                continue
            dst.global_lines.append(g)
            if _code_sig(g):
                gsigs.add(_code_sig(g))
        for attr in ("setup_lines", "loop_lines"):
            cur = getattr(dst, attr)
            sigs = {_code_sig(l) for l in cur if _code_sig(l)}
            for l in getattr(clone, attr):
                s = _code_sig(l)
                if s and s in sigs:
                    continue
                cur.append(l)
                if s:
                    sigs.add(s)
        fnames = {fn.name for fn in dst.functions}
        for fn in clone.functions:
            if fn.name not in fnames:
                dst.functions.append(fn); fnames.add(fn.name)

    def reorder(self, fid: str, index: int, side: str) -> None:
        lst = self.features(side)
        order = [f.id for f in lst]
        new_order = reorder_with_constraints(order, fid, index,
                                             self.deps(side))
        if new_order != order:
            by_id = {f.id: f for f in lst}
            lst[:] = [by_id[i] for i in new_order]
            self._reordered[side] = True

    def toggle_delete(self, fid: str, side: str) -> None:
        if fid in self._deleted[side]:
            self._deleted[side].discard(fid)
        else:
            self._deleted[side].add(fid)

    def transfer_all(self, src: str = "ia", dst: str = "stable") -> None:
        """`dst` becomes a full snapshot of the CURRENT `src` staging (delete
        marks on `dst` are cleared). Symmetric: IA→stable (default, the old
        chevron behavior) or stable→IA."""
        snapshot = [copy.deepcopy(f) for f in self.features(src)]
        if dst == "ia":
            self.ia = snapshot
        else:
            self.stable = snapshot
        self._deleted[dst] = set()
        self._transferred_all.add(dst)
        # Même comptabilité que les drags individuels : arrivées uniques
        # (dst, fid) enregistrées AU MOMENT du geste. Avant, recap() comptait
        # le contenu COURANT des colonnes destinataires -> un aller-retour
        # « tout transférer » annonçait 2× après coup, et les drags individuels
        # étaient écrasés du décompte (revue 2026-07-29 #10).
        self._transferred.update((dst, f.id) for f in snapshot)

    # ── Outcome ────────────────────────────────────────────────
    def recap(self) -> TransferRecap:
        r = TransferRecap(
            # Fonctionnalités UNIQUES ayant voyagé (dédup par fid, tous sens
            # confondus) : un aller-retour « tout transférer » recompte les
            # mêmes features UNE fois — avant, le recap comptait le contenu
            # courant des deux colonnes et annonçait le double (revue #10).
            transfers=len({fid for _, fid in self._transferred}),
            deletions=len(self._deleted["ia"]) + len(self._deleted["stable"]),
            reordered_ia=self._reordered["ia"],
            reordered_stable=self._reordered["stable"],
        )
        for side in SIDES:
            deleted = self._deleted[side]
            if not deleted:
                continue
            deps = self.deps(side)
            for f in self.features(side):
                if f.id in deleted:
                    continue
                for provider in deps.get(f.id, ()) & deleted:
                    r.warnings.append((side, f.id, provider))
        return r

    def has_changes(self) -> bool:
        return bool(self._transferred or self._transferred_all
                    or self._deleted["ia"] or self._deleted["stable"]
                    or self._reordered["ia"] or self._reordered["stable"])

    def result(self) -> tuple[list[Feature], list[Feature], set[str]]:
        """(features_ia, features_stable, removed_ia_ids) — deletions applied.
        `removed_ia_ids` feeds the studio metadata cleanup."""
        ia = [f for f in self.ia if f.id not in self._deleted["ia"]]
        stable = [f for f in self.stable
                  if f.id not in self._deleted["stable"]]
        return ia, stable, set(self._deleted["ia"])
