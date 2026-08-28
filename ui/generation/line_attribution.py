"""Attribution lignes->fonctionnalité SANS marqueurs IA (TODO #29).

Trois mécanismes complémentaires (cf. spec 2026-07-03) :
- la carte EXACTE vient de l'assembleur (assemble_with_map, assembler.py) ;
- entre deux événements moteur, les ancres de blocs Qt suivent les edits
  (ui/code_editor.py) ;
- quand le texte est réécrit HORS assembleur (splice, réparation IA, code
  brut), ce module reconstruit la carte : transfert par diff positionnel
  (régions intactes -> propriétaires conservés) puis matching des
  contributions stockées (exact normalisé par séquences, puis fuzzy).

Garantie : jamais de fausse couleur -> une ligne douteuse reste orpheline
(None). Le fuzzy est le seul risque, d'où son kill switch.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .feature_model import Feature

# Kill switch de la passe fuzzy (décision utilisateur 2026-07-03 : « on la
# retire si elle produit de fausses attributions »). Mettre à False pour ne
# garder que le matching exact normalisé.
# Garde « mêmes identifiants » (revue finale #29, 2026-07-03) : un match fuzzy
# n'est accepté QUE si la ligne orpheline et la ligne de référence ont
# EXACTEMENT le même multiset d'identifiants (cf. _identifiers) — seuls les
# LITTÉRAUX peuvent différer (delay(500) -> delay(250), tone(...,440) ->
# tone(...,880)). Sans cette garde, `digitalWrite(PIN_BUZZER, HIGH);` matche
# `digitalWrite(PIN_LED, HIGH);` à 0.881 (>= 0.8) -> fausse couleur sur le cas
# Arduino le plus banal (même API, autre broche). La garde élimine toute la
# classe « même API, autre broche » ; le kill switch reste pour tout risque
# résiduel sur le reste (littéraux).
_FUZZY_RESEED_ENABLED: bool = True
_FUZZY_THRESHOLD = 0.8
# Préfiltre longueur (perf, avant tout SequenceMatcher.ratio) : deux lignes
# dont les longueurs diffèrent de plus de 25 % n'ont aucune chance d'atteindre
# _FUZZY_THRESHOLD -> on les élimine sans calcul de ratio.
_FUZZY_LEN_TOLERANCE = 0.25

# Ligne « triviale » : vide ou pure ponctuation/accolades — jamais attribuée
# par matching (seulement par carte exacte ou transfert positionnel).
_TRIVIAL_RE = re.compile(r"^[\s{}();,]*$")
# Signatures du scaffolding : jamais attribuées, même par fuzzy.
_SCAFFOLD_RE = re.compile(r"^\s*void\s+(setup|loop)\s*\(")

LineMap = list   # list[str | None], index = n° de ligne 0-based


def normalize(line: str) -> str:
    """Forme canonique pour comparer deux lignes (indentation/espaces ignorés)."""
    return " ".join(line.split())


def is_trivial(line: str) -> bool:
    return bool(_TRIVIAL_RE.match(line)) or bool(_SCAFFOLD_RE.match(line))


def transfer_map(old_lines: list[str], old_map: LineMap,
                 new_lines: list[str]) -> LineMap:
    """Transfert positionnel : les régions communes (SequenceMatcher, formes
    normalisées) transportent leurs propriétaires ; le reste -> None."""
    result: LineMap = [None] * len(new_lines)
    sm = SequenceMatcher(None,
                         [normalize(l) for l in old_lines],
                         [normalize(l) for l in new_lines],
                         autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            continue
        for k in range(i2 - i1):
            if i1 + k < len(old_map):
                result[j1 + k] = old_map[i1 + k]
    return result


def _sequences(feature: Feature) -> list[list[str]]:
    """Suites contiguës de la feature (formes normalisées) : corps setup,
    corps loop, chaque fonction."""
    seqs: list[list[str]] = []
    for group in (feature.setup_lines, feature.loop_lines):
        if group:
            seqs.append([normalize(l) for l in group])
    for fn in feature.functions:
        seqs.append([normalize(l) for l in fn.code.split("\n")])
    return seqs


def _pool(feature: Feature) -> set[str]:
    """Toutes les lignes de contribution (normalisées, non triviales)."""
    out: set[str] = set()
    for ln in feature.includes + feature.global_lines:
        if not is_trivial(ln):
            out.add(normalize(ln))
    for seq in _sequences(feature):
        for ln in seq:
            if not is_trivial(ln):
                out.add(ln)
    return out


def _identifiers(line: str) -> tuple:
    """Multiset trié des identifiants d'une ligne (noms de fonction, constantes,
    variables, mots-clés) — ignore les littéraux numériques/chaînes. Deux
    lignes ne peuvent matcher en fuzzy que si ce multiset est IDENTIQUE
    (cf. garde au-dessus de _FUZZY_RESEED_ENABLED)."""
    return tuple(sorted(re.findall(r"[A-Za-z_]\w*", line)))


def match_contributions(lines: list[str], features: list[Feature],
                        base_map: LineMap) -> LineMap:
    """Comble les None de `base_map` en matchant les contributions stockées.
    1) séquences contiguës (>= 2 lignes alignées) ; 2) singletons non ambigus
    (ligne unique dans le document ET dans UNE seule feature) ; 3) passe fuzzy
    (ratio >= _FUZZY_THRESHOLD, feature candidate unique) si le kill switch
    est actif. Les lignes triviales ne sont JAMAIS attribuées ici."""
    owners: LineMap = list(base_map[:len(lines)])
    owners += [None] * (len(lines) - len(owners))
    norm = [normalize(l) for l in lines]

    def open_(i: int) -> bool:
        return owners[i] is None and not is_trivial(lines[i])

    # 1) Séquences contiguës.
    for f in features:
        for seq in _sequences(f):
            if not seq:
                continue
            sm = SequenceMatcher(None, norm, seq, autojunk=False)
            for i, _j, n in sm.get_matching_blocks():
                if n < 2:
                    continue
                for k in range(n):
                    if open_(i + k):
                        owners[i + k] = f.id
    # 2) Singletons non ambigus.
    doc_counts: dict[str, int] = {}
    for ln in norm:
        doc_counts[ln] = doc_counts.get(ln, 0) + 1
    line_owner: dict[str, "str | None"] = {}
    for f in features:
        for ln in _pool(f):
            line_owner[ln] = None if ln in line_owner else f.id  # None = ambigu
    for i in range(len(lines)):
        if not open_(i):
            continue
        fid = line_owner.get(norm[i])
        if fid is not None and doc_counts[norm[i]] == 1:
            owners[i] = fid
    # 3) Fuzzy (kill switch). Indexée par identifiants (cf. _identifiers) :
    # c'est le gros pruning perf (évite SequenceMatcher.ratio sur des refs
    # qui n'ont de toute façon aucune chance de matcher, cf. 300 lignes
    # orphelines x 5 features = gel UI observé sans cette garde) ET la garde
    # de correction (seuls les littéraux peuvent différer entre 2 lignes
    # fuzzy-proches).
    if _FUZZY_RESEED_ENABLED:
        by_ids: dict[tuple, dict[str, list[str]]] = {}
        for f in features:
            for ref in _pool(f):
                by_ids.setdefault(_identifiers(ref), {}).setdefault(f.id, []).append(ref)
        for i in range(len(lines)):
            if not open_(i):
                continue
            same_ids = by_ids.get(_identifiers(norm[i]))
            if not same_ids:
                continue
            candidates: set[str] = set()
            for fid, refs in same_ids.items():
                for ref in refs:
                    la, lb = len(norm[i]), len(ref)
                    if abs(la - lb) > _FUZZY_LEN_TOLERANCE * max(la, lb, 1):
                        continue                      # préfiltre longueur (perf)
                    if SequenceMatcher(None, norm[i], ref).ratio() >= _FUZZY_THRESHOLD:
                        candidates.add(fid)
                        break
            if len(candidates) == 1:
                owners[i] = candidates.pop()
    return owners


def single_feature_map(code: str, feature_id: str) -> LineMap:
    """Carte du cas « code brut mono-feature » (1ère génération débutant /
    REGENERATE plein) : tout appartient à la feature SAUF le trivial et les
    signatures setup/loop — la feature a été parsée de ce texte même."""
    return [None if is_trivial(l) else feature_id for l in code.split("\n")]
