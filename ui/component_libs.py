"""The user's own library choice for components the app had to guess.

When a part number is not in the corpus, `registry_lookup` searches the Arduino
registry, often finds SEVERAL libraries and picks one by a deterministic
heuristic (name containing the token > established author > shortest name).
This module holds the user's answer when that guess is wrong.

Keyed by the token `detect_unknown_part_tokens` produces. That token is ALREADY
normalised by construction -- extracted from `prompt.lower()`, hyphens joined
("ZXQ-9000" -> "zxq9000") -- and is the very string `registry_lookup` uses as
its cache key. Two normalisations drifting by one character would silently miss
the preference, so this module reuses the same string and only strips/lowers
defensively for callers reading a UI field.

NOT stored in registry-cache.json, for two reasons read in that module rather
than assumed:
  1. the cache EVICTS (bounded size, oldest insertion first) -- a preference
     would vanish on its own;
  2. a file named "cache" must stay safe to delete. Preferences are decisions,
     not an optimisation.

Only part-number tokens live here. A DECLARED component carries its own choice
in `DeclaredComponent.lib`: one source per component, so there is no precedence
rule to write, test or explain. `preferred_lib_for` picks the source.

Pure Python: no Qt, no dependency on ui.wiring.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

# v2 (2026-08-27, TODO #51) : ajoute le 3e etat « AUCUNE bibliotheque ».
#
# ⛔ POURQUOI UN SCHEMA ET PAS UNE VALEUR VIDE. En v1, une preference vide etait
# ECARTEE a la lecture (`if v.strip()`) : une preference « aucune » aurait vecu
# la session puis disparu au redemarrage -- une perte SILENCIEUSE. Et du cote
# des fiches declarees, `DeclaredComponent.lib` vide veut DEJA dire « a
# determiner ». Le meme vide ne peut pas dire aussi « aucune » : il faut une
# troisieme place, pas une convention de plus sur la meme case.
#
# La forme retenue garde `preferences` INCHANGE et ajoute une liste a cote.
# Consequence directe : la migration depuis v1 est une lecture, pas une
# conversion -- rien a transformer, donc rien a casser. Le controle de version
# de la v1 JETAIT le fichier des que la version differait ; c'est pour ca
# qu'ajouter un etat exigeait un vrai numero de schema et une migration
# explicite, et non un champ glisse en douce.
_SCHEMA_VERSION = 2
_MIGRATABLE_VERSIONS = (1, 2)
_LIBRARY_PATH = Path.home() / "Documents" / "Promptuino" / "component-libs.json"

# Ce que porte le 3e etat, en clair : « ce composant ne demande AUCUNE
# bibliotheque ». Ce n'est ni « je ne sais pas encore » (absent du magasin) ni
# « utilise celle-ci » (nommee). 13 des 139 entrees du corpus sont dans ce cas
# -- LDR, buzzer, PIR, MQ-135, moteur DC... -- donc le cas est courant, pas
# theorique.
NO_LIBRARY = "no_library"


def _key(token: str) -> str:
    """Defensive normalisation. Tokens from the detector are already in this
    shape; a caller reading a text field may not be."""
    return (token or "").strip().lower()


def load() -> dict[str, str]:
    """Stored preferences ({} if absent, unreadable or from an unknown schema
    version). Never raises: a broken store degrades to "no preference".

    A token the user declared library-free carries the `NO_LIBRARY` sentinel
    as its value, so ONE dict still describes the whole store and every
    existing caller keeps working on it. The sentinel is chosen to be
    unmistakable for a library name -- and `set_preference` refuses to store
    it as one, so the two can never be confused by accident.

    ⚠️ v1 files are read, NOT rejected. The v1 check was `!= _SCHEMA_VERSION`,
    which would have silently thrown away every preference the user had made
    the day the version was bumped.
    """
    try:
        if not _LIBRARY_PATH.exists():
            return {}
        data = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or                 data.get("version") not in _MIGRATABLE_VERSIONS:
            return {}
        raw = data.get("preferences")
        if not isinstance(raw, dict):
            raw = {}
        # One malformed pair must not take the whole store down (hand-edited
        # file, or one written by a buggy build).
        out = {_key(k): v.strip() for k, v in raw.items()
               if isinstance(k, str) and isinstance(v, str) and v.strip()}
        # v1 has no such list; absent means empty, which is the v1 truth.
        for tok in data.get("no_library") or []:
            if isinstance(tok, str) and _key(tok):
                # A token in BOTH places is a corrupted file. « Aucune » wins:
                # it is the more recent gesture in every path that writes here
                # (`set_no_library` clears the named value, never the reverse),
                # so honouring it cannot resurrect something already dropped.
                out[_key(tok)] = NO_LIBRARY
        return out
    except (OSError, ValueError, TypeError):
        # ValueError covers JSONDecodeError AND UnicodeDecodeError.
        return {}


def save(prefs: dict[str, str]) -> bool:
    """Atomic write (tmp + os.replace), same discipline as ui/session.py: a
    crash leaves either the whole previous file or the whole new one.

    Returns True when the write landed. Callers need to know: this module's
    whole purpose is that a choice STAYS, so a write that silently did not
    happen must not be reported upward as success.
    """
    try:
        _LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        named = {k: v for k, v in prefs.items() if v != NO_LIBRARY}
        none_ = sorted(k for k, v in prefs.items() if v == NO_LIBRARY)
        text = json.dumps({"version": _SCHEMA_VERSION,
                           "preferences": named,
                           "no_library": none_},
                          indent=2, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(dir=str(_LIBRARY_PATH.parent),
                                        suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, _LIBRARY_PATH)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
        return True
    except OSError:
        return False


# ─── In-memory registry ────────────────────────────────────────────────
# Filled at startup and after every write. Readers use THIS, never the disk,
# so a generation never pays a file read and tests inject their own state.
_REGISTRY: dict[str, str] = {}
_REGISTRY_LOADED = False


def set_registry(prefs: dict[str, str]) -> None:
    global _REGISTRY, _REGISTRY_LOADED
    _REGISTRY = dict(prefs)
    _REGISTRY_LOADED = True


def registry() -> dict[str, str]:
    return dict(_REGISTRY)


def _mutation_base() -> dict[str, str]:
    """The dict a mutation starts from.

    Memory once it has been initialised (startup does `set_registry(load())`),
    because memory -- not disk -- holds what the user decided: a write that
    failed leaves disk stale, and re-reading it would resurrect a value the
    user changed or CLEARED. Re-reading was the first shape of this function
    and it did exactly that: a failed `clear_preference` followed by any other
    mutation brought the cleared entry back, because a dict merge can express
    "new value wins" but never "this key is gone".

    Disk only when nothing has been loaded yet, so a mutation in a fresh
    process cannot wipe a file it never read.
    """
    return registry() if _REGISTRY_LOADED else load()


def preference_for(token: str) -> str:
    """The stored library NAME for this token, "" if none. This file only.

    ⚠️ Rend "" pour un composant declare sans bibliotheque : la sentinelle
    n'est pas un nom, et la laisser sortir d'ici la ferait voyager dans tout le
    code qui traite ce retour comme un nom de lib (recherche au registre,
    affichage, comparaisons). L'affirmation se lit par `declares_no_library`.
    """
    v = _REGISTRY.get(_key(token), "")
    return "" if v == NO_LIBRARY else v


def set_preference(token: str, lib: str) -> bool:
    """Store the user's choice for `token`. Returns whether the write reached
    disk; the in-session choice is applied to memory either way, because a
    failed write must not undo a choice the user just made -- a caller can use
    the return value to warn that it did not persist.

    Does nothing and returns False for a blank token: persisting one would
    make `preference_for("")` start answering non-empty while
    `preferred_lib_for("")` still answers "" -- two getters disagreeing on the
    same input.
    """
    key = _key(token)
    if not key:
        return False
    value = (lib or "").strip()
    if value == NO_LIBRARY:
        # Une bibliotheque ne peut pas s'appeler comme la sentinelle. Refuser
        # ici est la seule barriere qui empeche les deux etats de se confondre
        # -- passer par `set_no_library` est le chemin explicite.
        return False
    prefs = _mutation_base()
    prefs[key] = value          # remplace un eventuel NO_LIBRARY : nommer une
    ok = save(prefs)            # bibliotheque, c'est revenir sur « aucune »
    set_registry(prefs)
    return ok


def set_no_library(token: str) -> bool:
    """Record that this component needs NO library at all.

    Distinct de `clear_preference`, et c'est tout l'objet du ticket #51 :
    effacer rend le composant a la devinette de l'app, tandis que ceci est une
    AFFIRMATION de l'utilisateur, qui doit survivre au redemarrage et etre dite
    au modele. Meme contrat de durabilite que `set_preference`.
    """
    key = _key(token)
    if not key:
        return False
    prefs = _mutation_base()
    prefs[key] = NO_LIBRARY
    ok = save(prefs)
    set_registry(prefs)
    return ok


def declares_no_library(token: str) -> bool:
    """True si CE fichier porte l'affirmation « aucune bibliotheque ».

    Ne consulte pas les fiches declarees : c'est `no_library_for` qui arbitre
    la source, exactement comme `preference_for` / `preferred_lib_for`.
    """
    return _REGISTRY.get(_key(token), "") == NO_LIBRARY


def clear_preference(token: str) -> bool:
    """Remove the stored preference for `token`. Same durability contract as
    `set_preference`: returns whether the write reached disk, and still
    applies to memory when it did not. Does nothing and returns False for a
    blank token (nothing to clear, and nothing should ever be written under
    that key -- see `set_preference`)."""
    key = _key(token)
    if not key:
        return False
    prefs = _mutation_base()
    prefs.pop(key, None)
    ok = save(prefs)
    set_registry(prefs)
    return ok


def preferred_lib_for(token: str) -> str:
    """The library the user chose for this token, from whichever store owns it.

    A DECLARED component whose search token is this one answers with its OWN
    `lib` field -- including when that field is EMPTY, which means "still to
    determine" and must not fall back to the file: declaring a component is a
    more recent and more specific statement than an older bare-token choice.
    Anything else answers from this module's file.

    The declared token derivation MUST match `studio_view._declared_lookup_token`
    (entry name, stripped, lowercased); that function is the single source of
    truth for it, and diverging here would make the lookup miss.
    """
    key = _key(token)
    if not key:
        return ""
    from .declared_components import registry as declared_registry
    for c in declared_registry():
        if c.name.strip().lower() == key:
            return "" if c.no_lib else c.lib
    return preference_for(key)


def no_library_for(token: str) -> bool:
    """« Ce composant ne demande AUCUNE bibliotheque », depuis le magasin qui
    en est proprietaire.

    Miroir exact de `preferred_lib_for` : meme derivation du jeton, meme regle
    de source (la fiche declaree gagne des qu'elle correspond, y compris pour
    dire non). Les deux fonctions DOIVENT lire la meme source pour un jeton
    donne, sinon l'app pourrait a la fois nommer une bibliotheque et affirmer
    qu'il n'en faut aucune.
    """
    key = _key(token)
    if not key:
        return False
    from .declared_components import registry as declared_registry
    for c in declared_registry():
        if c.name.strip().lower() == key:
            return bool(c.no_lib)
    return declares_no_library(key)
