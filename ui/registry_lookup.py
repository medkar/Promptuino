"""Dynamic RAG through the Arduino library registry (spec 2026-07-29).

When the user names a component the corpus has never heard of (an "unknown
part-number", e.g. "AS7341" while the corpus only knows TCS34725), the semantic
retrieval degrades into pure noise: an ordinary FR sentence scores ~0.53
against UNRELATED libs, which then get injected with "reference these exact
APIs" — and the SLM dutifully writes code for the wrong chip. That code
compiles, so the failure is 100 % silent.

This module turns that path into an honest one:

  1. ``detect_unknown_part_tokens(prompt)`` — purely lexical, deterministic:
     find part-number-shaped tokens in the prompt that the corpus does NOT
     know (and that are not a named multi-chip module or a board/MCU name).
  2. ``lookup_component(token, config_file)`` — ask the Arduino library
     registry (``arduino-cli lib search``, LOCAL index → fast, offline once
     the index is cached). If a lib exists: install it (~30-250 KB — it would
     have been installed at compile time anyway, we just do it BEFORE
     generation), read its real headers + its simplest official example
     sketch, and build an AD-HOC corpus entry injected exactly like the
     curated ones. For a pattern-imitating SLM this is the closest thing to a
     real corpus entry.
  3. ``unknown_component_directive(tokens)`` — when the registry knows
     nothing either, the generation prompt gets an explicit protocol-agnostic
     instruction: minimal sketch, every hardware assumption as a TODO, and
     NEVER substitute another chip's library. The eventual failure surfaces
     at compile time instead of shipping wrong-chip code with a green check.

The caller (studio_view) decides what to do with the results: found entries
are appended to ``forced_libs`` (existing injection mechanism); when nothing
is found the semantic retrieval is SUPPRESSED (``forced_libs=[]``) so noise
never reaches the prompt again.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from . import arduino_cli
from .library_index import author_rank as _author_rank, norm_token as _norm


# ── Detection ─────────────────────────────────────────────────────────────────

# Board / MCU / C-type tokens that LOOK like part numbers but never designate a
# component the user wants to drive. Kept small on purpose: only tokens that
# match the part-number shape (≥4 chars, letters+digits) can false-positive.
_TOKEN_BLOCKLIST = {
    "esp32", "esp8266", "esp01",
    "atmega328", "atmega328p", "atmega2560", "atmega32u4", "attiny85",
    "stm32", "rp2040", "rp2350", "mega2560", "leonardo32u4",
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "utf8", "base64", "float32", "float64",
}

# At most this many unknown tokens are looked up per generation — a pathological
# prompt must not fan out into a dozen registry installs.
_MAX_UNKNOWN_TOKENS = 2

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HYPHENATED_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")
_HEX_RE = re.compile(r"0x[0-9a-f]+")


def _is_part_shaped(token: str) -> bool:
    """Part-number shape: ≥4 chars, at least one digit AND one letter, not a
    hex literal (0x40). Same spirit as ``rag._signature_tokens`` — pure digits
    (baud rates, delays) and pure words are never part numbers."""
    return (
        len(token) >= 4
        and any(c.isdigit() for c in token)
        and any(c.isalpha() for c in token)
        and not _HEX_RE.fullmatch(token)
    )


def detect_unknown_part_tokens(prompt: str) -> list[str]:
    """Part-number-shaped tokens of ``prompt`` that the corpus does NOT know.

    Purely lexical and deterministic (no embedding, no network). Hyphenated
    references are joined ("ZXQ-9000" → "zxq9000") so exotic vendor names are
    caught too. Excluded: corpus signature tokens (known chips), named
    multi-chip modules (HW-612…, handled by ``hardware_modules``), and the
    board/MCU blocklist. Order = first appearance; capped at
    ``_MAX_UNKNOWN_TOKENS``. Empty list when the corpus itself cannot load
    (we cannot tell known from unknown — better to change nothing)."""
    if not prompt or not prompt.strip():
        return []
    from .rag import known_part_tokens
    known = known_part_tokens()
    if not known:
        return []
    from .hardware_modules import detect_module

    low = prompt.lower()
    candidates: list[str] = list(_TOKEN_RE.findall(low))
    # Joined hyphenated forms, inserted right after their split parts.
    for m in _HYPHENATED_RE.findall(low):
        candidates.append(m.replace("-", ""))

    out: list[str] = []
    seen: set[str] = set()
    for tok in candidates:
        if tok in seen:
            continue
        seen.add(tok)
        if not _is_part_shaped(tok):
            continue
        if tok in _TOKEN_BLOCKLIST:
            continue
        if tok in known:
            continue
        if detect_module(tok) is not None:
            continue
        out.append(tok)
        if len(out) >= _MAX_UNKNOWN_TOKENS:
            break
    return out


# ── Registry lookup ───────────────────────────────────────────────────────────

# ── Cache persistant des entrées fabriquées ───────────────────────────────────
# Sans lui, la MÊME puce est re-cherchée et RÉ-INSTALLÉE à chaque génération qui
# la nomme (latence + réseau). Le cache sert deux choses :
#   1. la latence (pas de sous-processus du tout sur un hit) ;
#   2. le HORS LIGNE : une puce déjà vue reste utilisable sans réseau — cas
#      concret en établissement scolaire (cf. §Fritzing « socle offline »).
# On ne met en cache que les SUCCÈS : un « introuvable » ne coûte qu'une
# recherche sur index LOCAL (rapide) et le mettre en cache empêcherait de
# découvrir une lib publiée depuis.
_CACHE_VERSION = 1
_CACHE_MAX_ENTRIES = 100
# À côté de session.json (même dossier applicatif). Modifiable par les tests.
_CACHE_PATH = Path.home() / "Documents" / "Promptuino" / "registry-cache.json"

# Test seam (TODO #39 task 5): the cache is a real file under the user's
# Documents folder, and the "Composants" tab now reads it through
# `cached_lookups`. None (the default) means "no override -- read the real
# file"; a dict makes `_cache_load` return it as-is, so tests never depend on
# -- or pollute -- the machine's actual registry-cache.json.
_CACHE_OVERRIDE: dict | None = None


def set_cache_for_tests(entries: dict | None) -> None:
    """Test seam: the cache is a real file in the user's Documents folder, and
    the "Composants" tab now reads it. Tests inject their own content instead
    of depending on the machine's registry-cache.json."""
    global _CACHE_OVERRIDE
    _CACHE_OVERRIDE = entries


def cached_lookups() -> dict:
    """Every component the registry was asked about, token -> cache record.

    Read-only view for the "Composants" tab. Records may be EVICTED (the cache
    is bounded): a purely guessed component can therefore disappear from the
    tab, while one the user has CHOSEN a library for lives in `component_libs`
    and never does.
    """
    return _cache_load()


def _cache_load() -> dict:
    """Contenu du cache ({} si absent, illisible ou d'une version antérieure).
    Ne lève jamais : un cache cassé doit dégrader en « pas de cache »."""
    if _CACHE_OVERRIDE is not None:
        return dict(_CACHE_OVERRIDE)
    try:
        if not _CACHE_PATH.exists():
            return {}
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("v") != _CACHE_VERSION:
            return {}
        entries = data.get("entries")
        return entries if isinstance(entries, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _cache_get(token: str) -> dict | None:
    """Résultat mis en cache pour ce token, ou None. Rejette les enregistrements
    malformés (cache écrit par une version buguée / édité à la main)."""
    rec = _cache_load().get(token)
    if not isinstance(rec, dict):
        return None
    entry = rec.get("entry")
    if not isinstance(entry, dict) or not entry.get("name"):
        return None
    return rec


def _cache_put(token: str, lib_name: str, entry: dict,
               alternatives: list[str]) -> None:
    """Mémorise un succès. Écriture best-effort : un cache non écrit fait
    seulement perdre l'optimisation, jamais la génération en cours."""
    try:
        entries = _cache_load()
        entries[token] = {"lib_name": lib_name, "entry": entry,
                          "alternatives": list(alternatives)}
        # Borne la taille : au-delà, on retire les plus anciennement insérés
        # (dict Python = ordre d'insertion).
        while len(entries) > _CACHE_MAX_ENTRIES:
            entries.pop(next(iter(entries)))
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(
            json.dumps({"v": _CACHE_VERSION, "entries": entries},
                       ensure_ascii=False, indent=1),
            encoding="utf-8")
    except (OSError, TypeError, ValueError):
        pass


@dataclass
class RegistryLookupResult:
    token: str                       # unknown part token, as detected
    # "found"          : lib installed, `entry` ready
    # "not_found"      : the registry genuinely knows no such part
    # "unavailable"    : could not even ask (no arduino-cli, search broke)
    # "install_failed" : the registry HAS it, downloading it failed (network).
    #                    Distinct from "not_found" on purpose: the two lead the
    #                    user to opposite actions. `lib_name` is set.
    status: str
    lib_name: str = ""               # registry name of the installed lib
    entry: dict | None = None        # ad-hoc corpus entry, ready for forced_libs
    alternatives: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


# Example sketches whose stem contains one of these are preferred (simplest
# first); ties broken by shortest content. Mirrors what the corpus curates.
_EXAMPLE_STEM_PREFS = (
    "basic", "simple", "simpletest", "minimal", "hello", "read", "test", "demo",
)

_MAX_EXAMPLE_CHARS = 3500


def _pick_candidate(token: str, libraries: list[dict]) -> tuple[dict | None, list[str]]:
    """Deterministic choice among registry search results.

    Only libs whose NAME or short description actually contains the token are
    eligible (the search may match on loose prose — driving the wrong chip is
    the very failure this pipeline removes). Rank: token in name first, then
    established author, then shortest name. Returns (winner, other_names)."""
    tok = _norm(token)
    scored: list[tuple[tuple, dict]] = []
    for lib in libraries:
        name = lib.get("name") or ""
        latest = lib.get("latest") or {}
        author = latest.get("author") or ""
        sentence = (latest.get("sentence") or "") + " " + (latest.get("paragraph") or "")
        if tok in _norm(name):
            where = 0
        elif tok in _norm(sentence):
            where = 1
        else:
            continue  # not clearly about this part → never pick silently
        scored.append(((where, _author_rank(author), len(name)), lib))
    if not scored:
        return None, []
    scored.sort(key=lambda t: t[0])
    winner = scored[0][1]
    others = [lib.get("name") or "" for _, lib in scored[1:]]
    return winner, [n for n in others if n][:3]


def _pick_example(install_dir: str) -> str:
    """Simplest official example sketch of an installed lib ('' if none).
    Preference by stem keyword (basic/simple/…), ties by shortest content;
    truncated at a line boundary to ``_MAX_EXAMPLE_CHARS``."""
    root = Path(install_dir)
    inos = sorted(root.glob("examples/*/*.ino")) + sorted(root.glob("examples/*/*/*.ino"))
    if not inos:
        return ""

    def _pref(path: Path) -> int:
        stem = path.stem.lower()
        for i, kw in enumerate(_EXAMPLE_STEM_PREFS):
            if kw in stem:
                return i
        return len(_EXAMPLE_STEM_PREFS)

    best: tuple[tuple, str] | None = None
    for path in inos:
        try:
            content = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if not content:
            continue
        key = (_pref(path), len(content))
        if best is None or key < best[0]:
            best = (key, content)
    if best is None:
        return ""
    code = best[1]
    if len(code) > _MAX_EXAMPLE_CHARS:
        code = code[:_MAX_EXAMPLE_CHARS]
        cut = code.rfind("\n")
        if cut > 0:
            code = code[:cut]
        code += "\n// … (example truncated)"
    return code


def _headers_of(install_dir: str, provides: list[str]) -> list[str]:
    """Headers of the lib: registry metadata first, else top-level ``*.h``
    files of the install dir (root + src/)."""
    if provides:
        return list(provides)
    root = Path(install_dir)
    hs = sorted(p.name for p in root.glob("*.h")) + \
         sorted(p.name for p in (root / "src").glob("*.h"))
    return hs[:4]


def norm_lib_name(name: str) -> str:
    """Case- and whitespace-insensitive comparison key for a library name."""
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _search_registry(query: str, config_file: str | None) -> tuple[list[dict], str]:
    """Raw `arduino-cli lib search` results for `query`, plus a log line.

    The lone caller is `lookup_component` (finds + installs one). Until
    2026-08-12 this was also shared with the choice dialog's per-keystroke
    search field, which called through here too -- removed once the dialog
    started loading the whole registry index once and filtering it in memory
    (`library_index.parse_index` + `filter_libraries`) instead of searching
    per keystroke.

    The second element is "" on success and the failure reason otherwise.
    Returning it rather than swallowing it is deliberate (2026-08-03 review):
    a search that BROKE (subprocess error, non-zero exit) and a search that
    genuinely found nothing are OPPOSITE messages for the user -- "retry, or
    check your setup" versus "this part does not exist, stop looking" -- and
    collapsing them would be the same defect this chantier exists to remove,
    just wearing a different hat. `lookup_component` logs the reason and
    reports "unavailable" for it.

    Malformed but PARSEABLE responses (a `libraries` field that isn't a list,
    or entries that aren't dicts) are NOT failures and carry no reason: the
    original code crashed on them (`lib.get(...)` on a non-dict, or iterating
    a non-list), so there was no original wording to preserve, and dropping
    the bad shape (or the whole batch, if the field itself is not a list) is
    a strict improvement over that crash, not a behaviour this needs to
    explain to the user.
    """
    if config_file is None or not arduino_cli.is_available():
        return [], ""
    try:
        ret, out = arduino_cli._run([
            "arduino-cli", "lib", "search", query,
            "--config-file", config_file, "--format", "json",
        ])
    except (subprocess.TimeoutExpired, OSError) as e:
        return [], (f"[REGISTRY] recherche registre échouée pour "
                    f"« {query} » : {e}")
    if ret != 0:
        return [], (f"[REGISTRY] recherche registre échouée pour "
                    f"« {query} » (code {ret}).")
    try:
        raw = json.loads(out).get("libraries")
    except (json.JSONDecodeError, AttributeError):
        return [], ""
    if not isinstance(raw, list):
        return [], ""
    return [lib for lib in raw if isinstance(lib, dict)], ""


def fetch_library_index(config_file: str | None) -> str:
    """Sortie JSON BRUTE d'`arduino-cli lib search` pour l'index ENTIER.

    Rend "" quand la CLI est absente, qu'aucune carte n'est selectionnee, que
    l'appel echoue ou qu'il depasse le delai : l'appelant affiche alors
    « recherche indisponible » et garde les alternatives deja connues, qui ne
    demandent aucune CLI.

    Volontairement PAS route par `_search_registry` : celui-ci parse en
    dictionnaires, alors que `library_index.parse_index` possede l'etape
    JSON -> enregistrement (c'est la moitie pure et testable). Rendre le texte
    brut garde donc exactement UN analyseur. La CLI, elle, n'a toujours qu'un
    proprietaire : ce module.

    `--omit-releases-details` n'est pas une optimisation cosmetique : mesure le
    2026-08-12, la charge utile passe de 70,6 Mo a 11,9 Mo et le temps de 3,07 s
    a 1,55 s. Aucun champ affiche par la modale n'est perdu — les details de
    version ne servent qu'a l'installation, faite ailleurs.
    """
    if config_file is None or not arduino_cli.is_available():
        return ""
    try:
        ret, out = arduino_cli._run([
            "arduino-cli", "lib", "search",
            "--config-file", config_file, "--format", "json",
            "--omit-releases-details",
        ])
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return out if ret == 0 else ""


def lookup_component(token: str, config_file: str | None,
                     preferred_lib: str | None = None,
                     search_query: str | None = None) -> RegistryLookupResult:
    """Search the Arduino registry for ``token``; on success install the lib
    and build an ad-hoc corpus entry (headers + official example). Never
    raises — every failure degrades to "not_found"/"unavailable" with a log.

    ``token`` is the component's IDENTITY, and it is used as such everywhere
    downstream: cache key, ``RegistryLookupResult.token``, id + keyword of the
    ad-hoc corpus entry, name of the card in the "Composants" tab, ``{part}``
    in the banner. ``search_query`` decouples "what to type into the registry
    search" from that identity, for the one caller that knows them to differ:
    a chip named through a silkscreened module reference (spec 2026-08-20)
    has a VERIFIED library name but the user must still read "BMP085", not
    "Adafruit BMP085 Library". Defaults to ``token``, so every pre-existing
    caller keeps its exact behaviour.

    ``preferred_lib``, when given, names a library the caller already knows
    is the right one (e.g. a user-declared component that has been resolved
    before). If a search result matches it (case/space-insensitive), it is
    taken directly — bypassing ``_pick_candidate`` entirely, since that
    heuristic exists only to guess what the user just told us explicitly. If
    it matches nothing in the search results, we fall back to the heuristic
    but LOG that the preference was not found — an explicit user intent must
    never fail silently. For the same reason it also OVERRIDES a cached result
    that disagrees with it (see the cache read below).

    Runs arduino-cli subprocesses (search is local-index fast; install hits
    the network) — call from a worker thread, not the UI thread."""
    res = RegistryLookupResult(token=token, status="not_found")
    query = search_query or token
    # Cache AVANT tout : c'est ce qui rend le hors-ligne possible (aucun
    # sous-processus, pas besoin d'arduino-cli). L'installation reelle de la lib
    # reste assuree par la compilation (`_ensure_libs` lit les #include du code
    # genere) — le cache ne sert qu'a nourrir le contexte de generation.
    cached = _cache_get(token)
    if cached is not None and preferred_lib and norm_lib_name(
            cached.get("lib_name", "")) != norm_lib_name(preferred_lib):
        # Une preference EXPLICITE bat le cache (revue finale 2026-07-30). Sinon
        # le hit de cache repondait AVANT la logique `preferred_lib` : la lib que
        # l'utilisateur venait de corriger a la main n'etait jamais lue, le
        # journal annoncait « memorisee, pas de nouvelle recherche », et aucune
        # UI ne permet de purger le cache -> correction manuelle inoperante a
        # vie. Un nom memorise qui contredit la preference est perime par
        # definition : on refait la recherche (et `_cache_put` le remplacera).
        res.log.append(
            f"[REGISTRY] lib mémorisée « {cached.get('lib_name', '')} » ≠ "
            f"préférence « {preferred_lib} » — nouvelle recherche au registre.")
        cached = None
    if cached is not None:
        res.status = "found"
        res.lib_name = cached.get("lib_name", "")
        res.entry = cached.get("entry")
        res.alternatives = list(cached.get("alternatives") or [])
        res.log.append(f"[REGISTRY] « {token} » → lib « {res.lib_name} » "
                       f"(mémorisée, pas de nouvelle recherche).")
        return res
    if config_file is None or not arduino_cli.is_available():
        res.status = "unavailable"
        res.log.append(f"[REGISTRY] arduino-cli indisponible — "
                       f"« {token} » non recherché au registre.")
        return res
    # The CLI invocation + JSON parse (with malformed-shape guards, see its
    # docstring) live in _search_registry. A genuine failure (subprocess
    # error, non-zero exit) comes back as a non-empty `reason` and is
    # reported here EXACTLY as before ("unavailable" + the original wording)
    # -- collapsing it into "introuvable au registre" would tell the user a
    # BROKEN search found nothing, the same defect this chantier exists to
    # remove. A parseable-but-malformed response (bad shape, non-dict
    # entries) carries no reason and legitimately falls through as an
    # empty/filtered `libraries` list, same as before.
    libraries, reason = _search_registry(query, config_file)
    if reason:
        res.status = "unavailable"
        res.log.append(reason)
        return res
    winner: dict | None = None
    alternatives: list[str] = []
    if preferred_lib:
        wanted = norm_lib_name(preferred_lib)
        winner = next((lib for lib in libraries
                      if norm_lib_name(lib.get("name") or "") == wanted), None)
        if winner is None:
            res.log.append(
                f"[REGISTRY] préférence « {preferred_lib} » introuvable au "
                f"registre pour « {token} » — repli sur l'heuristique.")
    if winner is None:
        winner, alternatives = _pick_candidate(query, libraries)
    if winner is None:
        res.log.append(f"[REGISTRY] « {token} » introuvable au registre "
                       f"Arduino ({len(libraries)} résultat(s) non pertinents).")
        return res

    name = winner.get("name") or ""
    try:
        ret, _ = arduino_cli._run([
            "arduino-cli", "lib", "install", "--config-file", config_file, name,
        ])
    # L'installation a ECHOUE : statut dédié, et on retient le nom de la lib.
    # Sans ça le résultat repartait avec le statut initial `not_found`, donc
    # l'utilisateur lisait « composant inconnu au registre Arduino » alors que
    # le registre venait précisément de le trouver — deux diagnostics opposés
    # menant à deux actions opposées (« cherche une autre puce » contre
    # « rebranche ton réseau »). C'est la même confusion que celle corrigée
    # dans `_search_registry` le 2026-08-03, un étage plus haut (QA A4).
    except (subprocess.TimeoutExpired, OSError) as e:
        res.status = "install_failed"
        res.lib_name = name
        res.log.append(f"[REGISTRY] installation de « {name} » échouée : {e}")
        return res
    if ret != 0:
        res.status = "install_failed"
        res.lib_name = name
        res.log.append(f"[REGISTRY] installation de « {name} » échouée "
                       f"(code {ret}).")
        return res

    installed = arduino_cli._installed_libs(config_file)
    info = installed.get(name)
    if info is None:
        # Registry vs lib-list naming can differ in case — tolerant match.
        low = name.lower()
        info = next((v for k, v in installed.items() if k.lower() == low), None)
    if info is None or not info.get("install_dir"):
        res.log.append(f"[REGISTRY] « {name} » installée mais introuvable "
                       f"dans la liste des libs.")
        return res

    example = _pick_example(info["install_dir"])
    headers = _headers_of(info["install_dir"], info.get("headers") or [])
    res.status = "found"
    res.lib_name = name
    res.alternatives = alternatives
    res.entry = {
        "id": token,
        "name": name,
        "headers": headers,
        "keywords": [token],
        "example_code": example,
        "api_signatures": {},
        "_registry": True,
    }
    _cache_put(token, name, res.entry, alternatives)
    res.log.append(
        f"[REGISTRY] « {token} » → lib « {name} » du registre Arduino "
        f"(exemple {'inclus' if example else 'absent'}"
        + (f", alternatives : {', '.join(alternatives)}" if alternatives else "")
        + ")."
    )
    return res


def unknown_component_directive(tokens: list[str]) -> str:
    """Protocol-agnostic honest instruction appended to the generation prompt
    when neither the corpus nor the registry knows the component. Keeps the
    SLM from silently borrowing another chip's library — the historical
    silent-failure mode this pipeline removes."""
    if not tokens:
        return ""
    parts = ", ".join(f"'{t}'" for t in tokens)
    # No `// TODO` comments any more (user decision 2026-08-08): the model did
    # not reliably emit them, and the banner promised a section that was often
    # absent -- promising something the code does not contain is worse than
    # saying nothing. What matters, and what stays, is the ban on borrowing
    # another chip's library: that is the silent failure this pipeline exists
    # to remove. The honesty now lives in the banner, which says plainly that
    # the code may not work.
    return (
        f"UNKNOWN COMPONENT: the user's component {parts} is not in any known "
        f"Arduino library (corpus and registry). Write a minimal sketch that "
        f"drives it anyway, and do NOT include or imitate a library written "
        f"for a different chip."
    )


def no_library_directive(tokens: list[str]) -> str:
    """Instruction pour un composant dont l'UTILISATEUR affirme qu'il ne
    demande AUCUNE bibliotheque (TODO #51).

    ⛔ DELIBEREMENT DISTINCTE de `unknown_component_directive`, et ce n'est pas
    une nuance de ton : les deux situations menent le modele a des codes
    differents.

      - « inconnu » = l'app a CHERCHE et n'a rien trouve. C'est un aveu
        d'ignorance : le sketch produit risque de ne pas marcher, et la seule
        chose qui compte est d'interdire d'emprunter la bibliotheque d'une
        AUTRE puce.
      - « aucune » = l'utilisateur SAIT qu'il n'en faut pas. C'est une
        affirmation, et la consequence est positive et sure : le composant se
        pilote avec les fonctions du coeur Arduino (digitalRead, analogRead,
        analogWrite, tone...). Une LDR, un buzzer, un bouton, un moteur DC
        derriere son driver -- 13 des 139 entrees du corpus sont dans ce cas.

    Emettre l'aveu d'ignorance a la place de l'affirmation ferait ecrire au
    modele du code timide pour un composant parfaitement maitrise ; l'inverse
    ferait affirmer une maitrise que personne n'a. D'ou deux textes.
    """
    if not tokens:
        return ""
    parts = ", ".join(f"'{t}'" for t in tokens)
    return (
        f"NO LIBRARY NEEDED: the user states that {parts} needs NO Arduino "
        f"library. Drive it with the core Arduino functions only "
        f"(pinMode, digitalRead, digitalWrite, analogRead, analogWrite, tone, "
        f"millis...). Do NOT add an #include for it, and do NOT substitute a "
        f"library written for another part."
    )


class RegistryLookupWorker(QThread):
    """Background lookup of the unknown tokens (search + install are
    subprocess/network work — never on the UI thread). Emits ``done`` with the
    list of ``RegistryLookupResult`` in token order."""

    done = pyqtSignal(list)

    def __init__(self, tokens: list[str], config_file: str | None, parent=None,
                preferred_libs: dict[str, str] | None = None,
                search_queries: dict[str, str] | None = None):
        super().__init__(parent)
        self._tokens = list(tokens)
        self._config_file = config_file
        self._preferred_libs = dict(preferred_libs or {})
        # {token: registry search query}, same shape as `preferred_libs`, for
        # the tokens whose identity is not what should be typed into the
        # registry search (module chips -- see `lookup_component`). Absent =
        # search the token itself, the behaviour of every other caller.
        self._search_queries = dict(search_queries or {})

    def run(self):
        results = [lookup_component(t, self._config_file,
                                    self._preferred_libs.get(t),
                                    self._search_queries.get(t))
                  for t in self._tokens]
        self.done.emit(results)
