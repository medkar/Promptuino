"""User-declared components: model, persistence and in-memory registry.

When the detector cannot recognise a component, `markers.py` emits an unwired
placeholder box. The user can describe it (name, pins, labels, wiring); the
declaration is stored here and replayed in every project.

Indexed by `#include` HEADER, not by pin net: a placeholder has EMPTY nets, so
the historical `_wiring_resolutions` key ((fn_id, arduino net)) is unstable by
construction for these components.

File: ~/Documents/Promptuino/data/components.json (next to session.json).
Pure Python AT IMPORT TIME: no Qt, no ui.wiring — so the catalog can consult it
without a cycle and tests can inject a registry deterministically. The promise
is about the IMPORT, and that is what those two properties depend on: the
adoption helper at the bottom of the file (`adoptable_entry`, 2026-08-13)
reaches for `component_index` and the wiring catalog INSIDE its body, so
nothing loads unless someone actually adopts a component.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Netlist type prefix. Makes a collision with a builtin catalog type
# impossible by construction.
TYPE_PREFIX = "custom:"

_SCHEMA_VERSION = 1
from .paths import DATA_DIR
_LIBRARY_PATH = DATA_DIR / "components.json"

# Pin counts the layout can actually draw — MUST mirror _GENERIC_BY_PIN_COUNT
# in ui/wiring/layout/component_catalog.py (single row 2-8 plus odd 9/11/13,
# DIP 10-40 even). Accepting anything else would silently drop the component
# at render time.
DRAWABLE_PIN_COUNTS = frozenset(
    list(range(2, 9)) + [9, 11, 13] + list(range(10, 41, 2)))

_VCC_NETS = {"5V", "3V3", "3.3V", "VIN"}
_VCC_LABELS = {"VCC", "5V", "3V3", "3.3V", "V+", "+"}
_GND_LABELS = {"GND", "-", "G"}
_I2C_NETS = {"A4": "sda", "A5": "scl"}
_SLUG_FALLBACK = "composant"

# Accent folding for keyword matching. Deliberately minimal (the accented
# letters that actually turn up in FR/ES/IT component talk) rather than a
# unicodedata dance: the goal is that "humidité" matches "humidite", not full
# normalisation of arbitrary text.
_ACCENT_MAP = str.maketrans("àâäéèêëîïôöùûüçñ", "aaaeeeeiioouuucn")


def is_drawable_pin_count(n: int) -> bool:
    """True if the layout has an SVG asset for that pin count."""
    return n in DRAWABLE_PIN_COUNTS


def slugify(name: str, taken: set[str]) -> str:
    """Lowercase kebab-case slug, suffixed if already used by another entry."""
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    base = base or _SLUG_FALLBACK
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def new_entry_id(name: str, items: list["DeclaredComponent"]) -> str:
    """Id for a component being CREATED (never for an edit -- an edit keeps its
    id, so renaming leaves no orphan).

    `upsert` merges by id, on the premise that two components with the same name
    are the same component. That premise only holds while the id follows the
    name, and RENAMING breaks it: the old name's slug stays held by an entry
    that no longer bears that name. Creating a component under that old name
    then merged into -- and destroyed -- the renamed one: name and pinout
    replaced, while its learned `#include` and library stayed attached, so every
    schematic that included that header displayed the wrong component
    (2026-07-30 review). So the collision suffix comes back, but ONLY when the
    slug is held by a different name: re-declaring the same name is still an
    update, which is the whole point of the merge rule.
    """
    base = slugify(name, set())
    wanted = (name or "").strip().casefold()
    holder = next((c for c in items if c.id == base), None)
    if holder is None or holder.name.strip().casefold() == wanted:
        return base
    return slugify(name, {c.id for c in items})


def normalize_header(header: str) -> str:
    """`Adafruit/AS7341.H` -> `as7341.h`. Path and case are irrelevant: the same
    chip is reached through several include spellings."""
    return (header or "").replace("\\", "/").rsplit("/", 1)[-1].strip().lower()


def role_for(label: str, net: str) -> str:
    """Electrical role of a pin, derived from its net first, its label second.

    The net wins: a pin named VCC but wired to D7 is a signal, and treating it
    as a rail would make the router pull a wire to 5V that the user did not ask
    for. The user never types the role — it is computed here and stored so the
    JSON stays explicit.
    """
    n = (net or "").strip().upper()
    if n == "GND":
        return "gnd"
    if n in _VCC_NETS:
        return "vcc"
    if n in _I2C_NETS:
        return _I2C_NETS[n]
    # If net is provided but doesn't match special cases, it's a signal pin.
    # Only fall back to label if net is empty.
    if n:
        return "signal"
    lbl = (label or "").strip().upper()
    if lbl in _GND_LABELS:
        return "gnd"
    if lbl in _VCC_LABELS:
        return "vcc"
    if lbl == "SDA":
        return "sda"
    if lbl == "SCL":
        return "scl"
    return "signal"


@dataclass(frozen=True)
class DeclaredPin:
    label: str
    role: str
    net: str       # "" means "not connected" — a legitimate value, not a hole


@dataclass(frozen=True)
class DeclaredComponent:
    id: str
    name: str
    headers: tuple[str, ...]
    pins: tuple[DeclaredPin, ...]
    lib: str = ""                       # registry library name, "" if unknown
    keywords: tuple[str, ...] = ()      # phrases that recognise it in a prompt
    # TODO #51 : le TROISIEME etat. `lib` vide veut dire « a determiner » --
    # documente depuis toujours dans `preferred_lib_for` -- donc le meme vide
    # ne pouvait pas dire aussi « aucune bibliotheque n'est necessaire ». Un
    # drapeau separe, plutot qu'une convention de plus sur la meme case.
    #
    # Les deux ne peuvent pas etre vrais en meme temps : `no_lib` gagne, et
    # `component_libs.preferred_lib_for` rend "" des qu'il est pose. Le
    # formulaire, lui, efface `lib` quand l'utilisateur coche -- l'invariant
    # est tenu a l'ecriture, pas seulement a la lecture.
    no_lib: bool = False

    @property
    def type_id(self) -> str:
        return f"{TYPE_PREFIX}{self.id}"


def default_keywords(name: str) -> tuple[str, ...]:
    """Keywords a fresh declaration starts with: just its name."""
    n = (name or "").strip()
    return (n,) if n else ()


def _to_dict(c: DeclaredComponent) -> dict:
    return {
        "id": c.id, "name": c.name, "headers": list(c.headers),
        "pins": [{"label": p.label, "role": p.role, "net": p.net}
                 for p in c.pins],
        "lib": c.lib, "keywords": list(c.keywords),
        # Ecrit meme a False : un lecteur qui voit la cle sait que cette
        # version connait le 3e etat. Absente = fichier d'avant #51, et
        # `_from_dict` lit alors False, ce qui EST la verite pour ces fiches.
        "no_lib": bool(c.no_lib),
    }


def _from_dict(d: dict) -> DeclaredComponent | None:
    """None if the record is malformed (hand-edited or written by a buggy
    version): one bad entry must not take the whole library down."""
    try:
        cid = str(d["id"]).strip()
        name = str(d["name"]).strip()
        if not cid or not name:
            return None
        pins = tuple(
            DeclaredPin(label=str(p["label"]), role=str(p.get("role", "signal")),
                        net=str(p.get("net", "")))
            for p in d.get("pins", []) or []
        )
        headers = tuple(normalize_header(h) for h in d.get("headers", []) or [])
        lib = str(d.get("lib", "") or "").strip()
        kws = tuple(str(k).strip() for k in (d.get("keywords") or []) if str(k).strip())
        if "keywords" not in d:
            # No migration: a library written before this feature has no
            # "keywords" key at all. Deriving them from the name is what the
            # form would have done anyway. Checked on KEY ABSENCE rather than
            # on `kws` being empty, so an entry that legitimately round-trips
            # with no keywords (e.g. the dataclass default `()`, serialised as
            # an explicit `[]`) is not silently repopulated on every reload.
            kws = default_keywords(name)
        # Absent = fiche d'avant #51 : False EST la verite pour elle (rien
        # n'a jamais ete affirme). Et un `no_lib` vrai fait tomber `lib` : les
        # deux etats ne coexistent pas, et le faire respecter A LA LECTURE
        # protege aussi des fichiers ecrits a la main.
        no_lib = bool(d.get("no_lib", False))
        return DeclaredComponent(id=cid, name=name, headers=headers, pins=pins,
                                 lib="" if no_lib else lib, keywords=kws,
                                 no_lib=no_lib)
    except (KeyError, TypeError, ValueError):
        return None


def load() -> list[DeclaredComponent]:
    """Library content ([] if absent, unreadable or from another schema
    version). Never raises: a broken library degrades to "no library"."""
    try:
        if not _LIBRARY_PATH.exists():
            return []
        data = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != _SCHEMA_VERSION:
            return []
        out = [_from_dict(d) for d in data.get("components", []) or []]
        return [c for c in out if c is not None]
    except (OSError, ValueError, TypeError):
        # ValueError covers json.JSONDecodeError AND UnicodeDecodeError: a
        # components.json with a stray non-UTF-8 byte must degrade to "no
        # library" too, not propagate out of load() and kill the app before
        # any window exists (main.py calls this before QApplication is used).
        return []


def library_file_unusable() -> bool:
    """True if components.json exists on disk but `load()` could not read it
    as this schema version (a future build wrote a newer `version`, or the
    file is corrupt/unreadable).

    Distinguishes "no library yet" (False: fine to create one) from "a
    library exists that this build cannot understand" (True: saving over it
    would silently destroy it — the caller must refuse and warn instead).
    `load()` itself cannot make this distinction: it degrades both cases to
    `[]` on purpose, so a broken file never crashes startup.
    """
    try:
        if not _LIBRARY_PATH.exists():
            return False
        data = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
        return not (isinstance(data, dict) and data.get("version") == _SCHEMA_VERSION)
    except (OSError, ValueError, TypeError):
        return True


def save(items: list[DeclaredComponent]) -> None:
    """Atomic write (tmp + os.replace), same discipline as ui/session.py: a
    crash leaves either the whole previous file or the whole new one."""
    try:
        _LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(
            {"version": _SCHEMA_VERSION,
             "components": [_to_dict(c) for c in items]},
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
    except OSError:
        pass


# ─── In-memory registry ────────────────────────────────────────────────
# Filled once at startup by main.py (set_registry(load())). Consumers read
# THIS, never the disk: the catalog stays free of I/O and tests inject their
# own registry instead of depending on the machine's components.json.
_REGISTRY: list[DeclaredComponent] = []


def set_registry(items: list[DeclaredComponent]) -> None:
    global _REGISTRY
    _REGISTRY = list(items)


def registry() -> list[DeclaredComponent]:
    return list(_REGISTRY)


def find_by_type(type_id: str) -> DeclaredComponent | None:
    if not type_id.startswith(TYPE_PREFIX):
        return None
    wanted = type_id[len(TYPE_PREFIX):]
    return next((c for c in _REGISTRY if c.id == wanted), None)


def find_by_header(header: str) -> DeclaredComponent | None:
    key = normalize_header(header)
    if not key:
        return None
    return next((c for c in _REGISTRY if key in c.headers), None)


def upsert(items: list[DeclaredComponent],
           entry: DeclaredComponent) -> list[DeclaredComponent]:
    """Insert `entry`, or MERGE it into the existing entry with the same id.

    Rule changed on 2026-07-30: two components with the same name are the same
    component. The old `as7341-2` suffix is what made "correct a declaration by
    re-declaring it" fail -- `find_by_header` returns the FIRST match, so the
    stale entry kept winning the replay.

    The incoming name/lib/pins win (the user just typed them); headers and
    keywords are UNIONED (both were learned, losing either would forget
    something the library knew).
    """
    out: list[DeclaredComponent] = []
    merged = False
    for c in items:
        if c.id != entry.id:
            out.append(c)
            continue
        merged = True
        out.append(DeclaredComponent(
            id=c.id,
            name=entry.name,
            headers=tuple(dict.fromkeys((*c.headers, *entry.headers))),
            pins=entry.pins,
            # ⚠️ `entry.lib or c.lib` seul RESSUSCITERAIT la bibliotheque qu'on
            # vient de declarer inutile : « aucune » se represente par un lib
            # VIDE plus un drapeau, et le vide retombait sur l'existant. Le
            # drapeau entrant est la declaration COURANTE de l'utilisateur --
            # y compris quand il revient dessus -- donc il gagne sans repli.
            lib="" if entry.no_lib else (entry.lib or c.lib),
            keywords=tuple(dict.fromkeys((*c.keywords, *entry.keywords))),
            no_lib=entry.no_lib,
        ))
    if not merged:
        out.append(entry)
    return out


def _fold(text: str) -> str:
    return (text or "").lower().translate(_ACCENT_MAP)


def _keyword_hit(prompt_folded: str, keyword: str) -> bool:
    """Whole-word match of a (possibly multi-word) keyword.

    Local on purpose: `markers._has_keyword` does the same thing, but this
    module must not import `ui.wiring` -- `component_catalog` imports THIS
    module, and the reverse edge would make the cycle fragile. Three lines of
    regex are cheaper than that coupling.
    """
    kw = _fold(keyword).strip()
    if not kw:
        return False
    # `(?<!\w)` / `(?!\w)` rather than `\b`: `\b` only marks a boundary next to
    # a WORD character, so a keyword whose edge is not one ("TinyGPS++",
    # "Capteur (Grove)") could never match -- not even against its own name
    # written verbatim in the prompt (2026-07-30 review). These two look
    # AROUND the keyword instead of requiring a word character there, and keep
    # the protection that matters: "moisture" still does not match inside
    # "moistureproof".
    return re.search(rf"(?<!\w){re.escape(kw)}(?!\w)",
                     prompt_folded) is not None


def matches_in_prompt(prompt: str,
                      items: list[DeclaredComponent] | None = None
                      ) -> list[DeclaredComponent]:
    """Every declared component whose keywords appear in `prompt`."""
    folded = _fold(prompt)
    if not folded:
        return []
    pool = registry() if items is None else items
    return [c for c in pool
            if any(_keyword_hit(folded, k) for k in c.keywords)]


def match_prompt(prompt: str,
                 items: list[DeclaredComponent] | None = None
                 ) -> DeclaredComponent | None:
    """The single declared component the prompt refers to, or None.

    None on collision BY DESIGN: with two entries triggered we would not know
    which library to inject, nor which entry should receive the write-back.
    Injecting two contradictory libraries is worse than injecting none. Same
    reasoning as the disjoint-candidate dedup of the ClarifyGroups.
    """
    hits = matches_in_prompt(prompt, items)
    return hits[0] if len(hits) == 1 else None


# ── Adoption : reprendre a son compte un composant qu'on n'a pas decrit ──────
#
# Vit ICI, et non dans la fenetre principale ou il est ne, parce que DEUX
# ecrans en ont besoin : la fiche de l'onglet « Composants » et le crayon des
# cards de la modale d'ambiguite. Le resultat est un `DeclaredComponent` — la
# forme que ce module definit.
#
# ⚠️ Ces deux fonctions importent, DANS LEUR CORPS, `component_index`,
# `component_libs`, `registry_lookup` et le catalogue de cablage. C'est
# delibere : le module reste importable sans Qt et sans `ui.wiring` (la
# promesse de l'en-tete tient au niveau de l'IMPORT, qui est ce dont dependent
# le catalogue et les tests), et rien ne se charge tant que personne n'adopte.
# `lang` est un PARAMETRE plutot qu'une lecture de `lang_manager` : c'est ce
# qui garde le module a l'ecart de Qt.


def adoptable_entry(key: str, lang: str = "fr"):
    """Brouillon de déclaration pour un composant NON déclaré, ou None.

    Modifier un composant qu'on n'a pas décrit soi-même, c'est le REPRENDRE À
    SON COMPTE : le formulaire s'ouvre pré-rempli avec ce que l'app sait, et
    c'est l'enregistrement qui crée l'entrée perso. C'est aussi ce qui rend le
    choix de librairie EFFECTIF — le déclencheur « composant déclaré » force
    la librairie dans le contexte de génération, alors qu'une préférence posée
    sur une fiche curée n'aurait atteint personne (le RAG passe par le corpus,
    et la détection de part-number exclut justement ses puces).

    Deux provenances, deux sources de pré-remplissage :
    - **devinée** — le cache du registre : le jeton et la librairie retenue,
      rien d'autre ;
    - **registre curé** — l'index lui-même : nom, librairie du document, et
      brochage du catalogue quand il y en a un.

    Dans les deux cas, une librairie que l'utilisateur a **choisie** bat celle
    que l'app avait retenue (cf. plus bas).

    Aucune broche n'est inventée : quand l'app n'en connaît pas, le formulaire
    pose ses propres valeurs par défaut, modifiables.
    """
    from .component_libs import no_library_for, preferred_lib_for
    from .registry_lookup import cached_lookups

    name, lib = "", ""
    pins: tuple = ()
    try:
        record = (cached_lookups() or {}).get(key)
    except Exception:
        record = None
    if isinstance(record, dict):
        entry = record.get("entry") if isinstance(record.get("entry"), dict) else {}
        from .component_index import _token_as_name
        name = _token_as_name(key)
        lib = str(record.get("lib_name") or entry.get("arduino_lib_name") or "").strip()
    else:
        from .component_index import build_index
        info = next((i for i in build_index(lang) if i.key == key), None)
        if info is None:
            return None
        name, lib = info.name, info.lib
        pins = _catalog_pins(key)
    # Un choix de l'utilisateur bat ce que l'app avait retenu. Le cache porte
    # la DEVINETTE (ou une valeur périmée), `preferred_lib_for` porte la
    # DÉCISION, depuis le magasin qui la détient. Sans ça, reprendre un
    # composant à son compte rétablissait la devinette EN SILENCE — et comme
    # l'entrée déclarée gagne ensuite sur `component-libs.json` (une seule
    # source par composant, cf. `component_libs.preferred_lib_for`), l'ancien
    # choix devenait inatteignable autrement qu'en le refaisant à la main.
    # Mesuré en QA I5 (2026-08-10) : préférence « Adafruit VEML7700 Library »
    # remplacée par la devinette « DevLab_VEML7700 » à l'adoption.
    chosen = preferred_lib_for(key)
    if chosen:
        lib = chosen
    # Meme raison, pour le 3e etat : sans ca, reprendre a son compte un
    # composant declare sans bibliotheque retablissait la devinette EN SILENCE
    # -- le cas exact que le paragraphe ci-dessus documente pour une lib
    # nommee. L'affirmation est plus forte encore qu'un choix de nom : elle dit
    # qu'il ne faut RIEN chercher.
    no_lib = no_library_for(key)
    if no_lib:
        lib = ""
    if not name:
        return None
    return DeclaredComponent(
        # Un id EST attribué dès maintenant : le formulaire reprend celui de
        # l'entrée qu'on lui passe, et un id vide produirait une entrée sans
        # identité à l'enregistrement.
        id=new_entry_id(name, load()), name=name, headers=(), pins=pins,
        lib=lib, keywords=default_keywords(name), no_lib=no_lib)


def _catalog_pins(type_id: str) -> tuple:
    """Broches du catalogue de câblage pour ce type, ou () s'il n'y en a pas.

    Reprises telles quelles, sans net : le catalogue connaît les LIBELLÉS
    (VCC, GND, SDA…), pas à quoi la carte les relie dans ce projet. Deviner un
    net serait inventer un câblage.
    """
    try:
        from .wiring.layout.component_catalog import lookup
        entry = lookup(type_id)
    except Exception:
        entry = None
    labels = getattr(entry, "pin_labels", None) if entry is not None else None
    if not labels:
        return ()
    return tuple(
        DeclaredPin(label=labels[i], role=role_for(labels[i], ""), net="")
        for i in sorted(labels)
    )
