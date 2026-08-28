"""Le registre Arduino, charge une fois et filtre en memoire.

Pourquoi en memoire plutot qu'un `arduino-cli lib search` par frappe, mesure le
2026-08-12 sur l'index local : une recherche coute 1,3 s et la requete « a »
rend 9 814 bibliotheques en 3,3 s, donc chercher pendant la frappe gelerait la
fenetre a chaque lettre. L'index ENTIER se charge en 1,55 s / 11,9 Mo avec
`--omit-releases-details` (70,6 Mo sans) : on le paie une fois par session et
chaque frappe suivante n'est plus qu'une comprehension de liste.

Python pur : pas de Qt, pas de sous-processus, pas de disque. Il recoit une
charge utile JSON et rend des enregistrements — meme discipline que
component_libs.py et component_index.py, ce qui rend les regles de classement
verifiables sur une fixture.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class LibraryRecord:
    """Une bibliotheque du registre.

    Les champs sont ceux que `arduino-cli lib search` rend REELLEMENT, releves
    sur la charge utile du 2026-08-12 — pas un brochage suppose. `name` est au
    PREMIER niveau du JSON ; tout le reste vient de `latest`.

    `provides_includes` et `license` existent au schema mais valaient `null` sur
    les entrees mesurees : ils ne sont pas repris, pour ne pas afficher un champ
    vide la plupart du temps.

    Tous les champs sauf `name` ont une valeur par defaut : la liste courte
    affiche des noms venus du cache AVANT que l'index soit charge, et doit
    pouvoir construire un enregistrement a partir du nom seul.
    """
    name: str
    author: str = ""
    maintainer: str = ""
    sentence: str = ""
    paragraph: str = ""
    version: str = ""
    category: str = ""
    architectures: tuple[str, ...] = ()
    types: tuple[str, ...] = ()
    website: str = ""
    dependencies: tuple[str, ...] = ()


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _texts(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(v.strip() for v in value if isinstance(v, str) and v.strip())


def _dep_names(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out = [_text(d.get("name")) for d in value if isinstance(d, dict)]
    return tuple(n for n in out if n)


def parse_index(payload: str) -> list[LibraryRecord]:
    """Enregistrements lus dans la sortie JSON d'`arduino-cli lib search`.

    Tolerant par construction, exactement comme `_search_registry` l'est deja :
    une charge utile non JSON, un champ `libraries` qui n'est pas une liste, ou
    des entrees qui ne sont pas des dictionnaires rendent une liste vide ou
    sautent l'entree fautive, sans jamais lever. Une entree sans `name` est
    ecartee : elle ne pourrait ni s'afficher ni se choisir.
    """
    try:
        raw = json.loads(payload).get("libraries")
    except (json.JSONDecodeError, AttributeError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[LibraryRecord] = []
    for lib in raw:
        if not isinstance(lib, dict):
            continue
        name = _text(lib.get("name"))
        if not name:
            continue
        latest = lib.get("latest")
        if not isinstance(latest, dict):
            latest = {}
        out.append(LibraryRecord(
            name=name,
            author=_text(latest.get("author")),
            maintainer=_text(latest.get("maintainer")),
            sentence=_text(latest.get("sentence")),
            paragraph=_text(latest.get("paragraph")),
            version=_text(latest.get("version")),
            category=_text(latest.get("category")),
            architectures=_texts(latest.get("architectures")),
            types=_texts(latest.get("types")),
            website=_text(latest.get("website")),
            dependencies=_dep_names(latest.get("dependencies")),
        ))
    return out


# Auteurs etablis, exemples les mieux documentes d'abord. Rang = index ; un
# auteur inconnu passe dernier.
#
# DEMENAGE depuis registry_lookup le 2026-08-12, avec `norm_token` (qui s'y
# appelait `_norm`) : une seule definition du vocabulaire de departage
# (normalisation de cle + rang d'auteur) au lieu de deux copies qui auraient
# fini par deriver l'une de l'autre.
#
# Ce qui n'est PAS partage, et ne doit pas etre suppose l'etre : la logique de
# RANG. `_pick_candidate` (ui/registry_lookup.py, choix automatique du
# pipeline hors-corpus) n'a que 2 rangs et fait primer l'auteur etabli ;
# `_match_rank` ci-dessous en a 5 et fait primer le nom exact/prefixe AVANT
# l'auteur — et un enregistrement qui ne correspond que par l'auteur (rang 3)
# apparait dans cette liste alors que `_pick_candidate` l'ecarte purement et
# simplement. Verifie par l'execution (revue 2026-08-12) : sur
# [{"name": "Servo", "author": "RandomGuy"},
#  {"name": "MyServoWrapper", "author": "Adafruit"}], `_pick_candidate`
# choisit "MyServoWrapper" (l'auteur etabli) alors que `filter_libraries`
# classe "Servo" en tete (le nom exact). La premiere ligne de la liste n'est
# donc PAS forcement le choix que l'app aurait fait automatiquement — ne
# jamais s'appuyer sur cette hypothese. Ce que l'app UTILISE reellement se dit
# a l'utilisateur par le badge « en usage » de la card (Task 7), pas par la
# position dans la liste. Unifier `_pick_candidate` sur `_match_rank` est
# HORS PERIMETRE : ca changerait le choix automatique de bibliotheque de tout
# le pipeline hors-corpus, verrouille a dessein par
# `scripts/test_unknown_component_registry.py`.
_TRUSTED_AUTHORS = ("adafruit", "sparkfun", "arduino", "dfrobot", "seeed")

_NO_MATCH = 99


# Bornee (pas `maxsize=None`) : l'index fait 9 824 enregistrements x 3 champs
# normalises (nom, auteur, sentence+paragraph) ~ 30 000 chaines distinctes,
# donc 100 000 couvre l'index entier avec de la marge tout en interdisant une
# croissance sans fin si la fonction voit un jour d'autres appelants.
#
# Le meme `record.name`/`record.author` repasse par `norm_token` a CHAQUE
# frappe (chaque appel a `filter_libraries` re-normalise tout l'index), jusqu'a
# 3 `re.sub` par enregistrement avant de conclure a une non-correspondance.
# Mesure le 2026-08-12 sur 9 824 enregistrements synthetiques, mediane sur 30
# repetitions, requetes "servo"/"adafruit"/"xyz_no_match_at_all" (pire cas :
# aucune correspondance, pas un cas exotique — un nom de composant mal
# orthographie) : 42-46 ms avant cache, 5-7 ms apres. Le classement et le
# departage sont inchanges, seule la repetition de travail identique disparait.
@lru_cache(maxsize=100_000)
def norm_token(text: str) -> str:
    """Cle de comparaison : minuscules, tout ce qui n'est pas alphanumerique
    retire. « Adafruit AS7341 » et « adafruit-as7341 » donnent la meme cle."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def author_rank(author: str) -> int:
    a = (author or "").lower()
    for i, trusted in enumerate(_TRUSTED_AUTHORS):
        if trusted in a:
            return i
    return len(_TRUSTED_AUTHORS)


def supports_arch(record: LibraryRecord, arch: str) -> bool:
    """Rien ne dit le CONTRAIRE : True n'affirme pas un support prouve, il
    signifie seulement qu'aucune incompatibilite n'est connue.

    Rend True quand `arch` est vide (aucune carte selectionnee) ET quand la
    bibliotheque ne declare aucune architecture : dans ces deux cas on ne SAIT
    pas, et l'appelant ne doit afficher aucune revendication de compatibilite.
    Rendre False signifierait « incompatible », un verdict qu'on n'a pas gagne.
    """
    if not record.architectures:
        return True
    a = (arch or "").strip().lower()
    if not a:
        return True
    declared = tuple(x.lower() for x in record.architectures)
    return "*" in declared or a in declared


def is_retired(record: LibraryRecord) -> bool:
    """Le registre lui-meme marque la bibliotheque « Retired ». On repete, on
    ne devine pas."""
    return any(t.lower() == "retired" for t in record.types)


def _match_rank(record: LibraryRecord, query: str) -> int:
    """`query` doit deja etre normalisee (`norm_token`) — `filter_libraries`
    le fait avant d'appeler. Un appelant qui passerait une requete brute
    obtiendrait des rangs manques en silence (une requete "Servo" ne
    matcherait jamais un nom normalise "servo")."""
    name = norm_token(record.name)
    if name == query:
        return 0
    if name.startswith(query):
        return 1
    if query in name:
        return 2
    if query in norm_token(record.author):
        return 3
    if query in norm_token(record.sentence + " " + record.paragraph):
        return 4
    return _NO_MATCH


def filter_libraries(records: list[LibraryRecord],
                     query: str) -> list[LibraryRecord]:
    """Enregistrements correspondant a `query`, du meilleur au moins bon.

    Cinq rangs : nom exact, nom commencant par, requete dans le nom, dans
    l'auteur, dans la description. A rang egal l'ordre est
    (auteur etabli, nom le plus court, nom) — total et deterministe, donc
    stable d'un affichage a l'autre.

    Rend TOUS les correspondants. Le plafond d'affichage est une affaire de
    modale, pas de classement : c'est elle qui sait combien de cards elle peut
    construire, et c'est elle qui doit annoncer le nombre total.

    Une requete vide ne correspond a rien : le champ vide est un ETAT de la
    modale (la liste courte), pas une recherche qui rendrait les 9 824 entrees.
    """
    q = norm_token(query)
    if not q:
        return []
    scored = []
    for r in records:
        rank = _match_rank(r, q)
        if rank == _NO_MATCH:
            continue
        scored.append(((rank, author_rank(r.author), len(r.name), r.name), r))
    scored.sort(key=lambda pair: pair[0])
    return [r for _, r in scored]


# ─── Cache memoire ────────────────────────────────────────────────────────
# Rempli une fois par SESSION (pas par ouverture de la modale) : la deuxieme
# ouverture est donc instantanee. Meme motif que declared_components.set_registry
# et component_libs.set_registry — les lecteurs lisent CECI, jamais le disque ni
# la CLI, ce qui rend les tests deterministes.
_INDEX: list[LibraryRecord] = []
_LOADED = False


def set_index(records: list[LibraryRecord]) -> None:
    global _INDEX, _LOADED
    _INDEX = list(records)
    _LOADED = True


def index() -> list[LibraryRecord]:
    """Copie de la liste : un appelant qui la trie ou la filtre en place ne doit
    pas abimer le cache de toute la session."""
    return list(_INDEX)


def is_loaded() -> bool:
    """Distinct de « l'index est vide » : un registre vide est un RESULTAT, et
    les confondre relancerait le chargement en boucle."""
    return _LOADED
