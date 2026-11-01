"""Registre des modules hardware NOMMÉS = plusieurs puces sur une carte.

Source unique de vérité, consultée par le codegen (ui/rag.py) ET le wiring
(ui/wiring/markers.py). Pur Python, aucune dépendance (pas de cycle d'import).

Un module est déclaré EXPLICITEMENT (son nom dans le prompt) : c'est ce qui
distingue « un HW-612 » (une carte) de « un MPU9250 + un BMP280 » réellement
séparés. Sans nom de module → pas de forçage codegen ni de fusion wiring.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from functools import lru_cache


@dataclass(frozen=True)
class HardwareModule:
    """Une carte multi-puces, vue du câblage et de la détection.

    ⚠️ Ce que ce module ne porte PLUS depuis le 2026-08-18 : les **puces** et
    les **mots-clés**. Ils vivent dans `ui/component_registry.py`, parce qu'un
    module est un **composant** — c'est ce que l'utilisateur possède — et que
    sa composition est de l'**identité**, pas du dessin.

    Les lire au lieu de les redéclarer garantit UNE source de vérité. Deux
    listes divergeraient, et la divergence ne se verrait qu'à la génération :
    une puce déclarée ici mais absente là forcerait une bibliothèque de moins,
    en silence.

    Reste ici ce qui est réellement propre au câblage : l'id (type de la boîte
    fusionnée), le libellé de la note envoyée au modèle, et les broches.
    """
    id: str                      # "hw-612" (= type wiring de la boîte fusionnée)
    label: str                   # libellé humain, pour la note au modèle
    i2c_pins: tuple[str, ...]    # broches de la boîte fusionnée

    @property
    def keywords(self) -> tuple[str, ...]:
        """Alias de détection, lus sur le composant de registre du module."""
        from .component_registry import by_id
        comp = by_id(self.id)
        return comp.keywords if comp is not None else ()

    @property
    def chips(self) -> tuple[str, ...]:
        """Puces portées, lues sur `Component.contains`."""
        from .component_registry import by_id
        comp = by_id(self.id)
        return comp.contains if comp is not None else ()


MODULES: tuple[HardwareModule, ...] = (
    HardwareModule(
        id="hw-612",
        label="HW-612 (centrale inertielle 10-DOF)",
        i2c_pins=("VCC", "GND", "SDA", "SCL"),
    ),
    # ── Ajoutés le 2026-08-18 (TODO #54 étape 2) ──────────────────────────────
    # Avant : « GY-80 » partait au registre Arduino, qui ne trouve rien — il
    # n'existe aucune bibliothèque de ce nom, ce sont les PUCES qui en ont une.
    # L'utilisateur lisait la sérigraphie de sa carte et l'app répondait
    # « composant inconnu ».
    #
    # ✅ CES DEUX MODULES SONT COMPLETS DEPUIS LE 2026-08-26 (TODO #54).
    # Ils ont longtemps été volontairement PARTIELS : une puce ne force sa
    # bibliothèque que si elle a un DOCUMENT corpus, et `l3g4200d`, `itg3200`
    # et `bmp085` étaient des composants connus du registre SANS document.
    # `bmp085` a reçu le sien au lot #60 (2026-08-21), les deux gyroscopes au
    # lot final de #54 — GY-80 force donc ses QUATRE puces et GY-85 ses TROIS.
    # Le compromis qui tenait entre-temps reste la bonne règle si le cas se
    # représente : forcer les puces documentées et NOMMER la carte au modèle
    # vaut mieux que « composant inconnu », et
    # `test_every_module_chip_actually_forces_a_library` distingue
    # explicitement ce cas d'une faute de frappe.
    HardwareModule(
        id="gy-80",
        label="GY-80 (centrale inertielle 10-DOF)",
        i2c_pins=("VCC", "GND", "SDA", "SCL"),
    ),
    HardwareModule(
        id="gy-85",
        label="GY-85 (centrale inertielle 9-DOF)",
        i2c_pins=("VCC", "GND", "SDA", "SCL"),
    ),
    # ── Ajoutés le 2026-08-26 (TODO #57) ──────────────────────────────────────
    # Ils existaient déjà dans le prompt de l'utilisateur, mais comme ALIAS de
    # `hw-612` — donc avec les mauvaises puces forcées. Voir le commentaire de
    # `hw-612` dans component_registry.py.
    #
    # GY-87 force ses TROIS puces (toutes documentées au corpus). GY-86 en force
    # deux sur trois : son MS5611 a une identité et une bibliothèque vérifiée,
    # mais pas de document corpus — le traitement « partiel » déjà assumé pour
    # gy-80/gy-85, et que `test_every_module_chip_actually_forces_a_library`
    # distingue explicitement d'une faute de frappe.
    HardwareModule(
        id="gy-87",
        label="GY-87 / HW-290 (centrale inertielle 10-DOF)",
        i2c_pins=("VCC", "GND", "SDA", "SCL"),
    ),
    HardwareModule(
        id="gy-86",
        label="GY-86 (centrale inertielle 10-DOF, baromètre MS5611)",
        i2c_pins=("VCC", "GND", "SDA", "SCL"),
    ),
)


@lru_cache(maxsize=None)
def _alias_pattern(alias: str) -> "re.Pattern[str]":
    """Regex tolerante depuis un alias : decoupe en runs lettres/chiffres,
    separateur optionnel entre eux, bornes alphanumeriques (pas de match au
    milieu d'un token plus long). 'hw612' -> hw[\\s\\-_]?612 borne."""
    compact = re.sub(r"[^a-z0-9]", "", alias.lower())
    runs = re.findall(r"[a-z]+|[0-9]+", compact)
    if not runs:
        return re.compile(r"(?!x)x")  # ne matche jamais
    body = r"[\s\-_]?".join(re.escape(r) for r in runs)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")


def detect_module(text: str, modules=None) -> HardwareModule | None:
    """Premier module dont un alias matche `text` (regex tolerante,
    insensible a la casse et aux separateurs). None si aucun.

    `modules` injecte un jeu de modules factice, pour les TESTS uniquement --
    en production il reste None et le pool est `MODULES`.
    """
    if not text:
        return None
    pool = MODULES if modules is None else modules
    t = text.lower()
    for mod in pool:
        if any(_alias_pattern(kw).search(t) for kw in mod.keywords):
            return mod
    return None


def module_chips_needing_lookup(
        prompt: str,
        modules=None) -> list[tuple[str, str, str]]:
    """(lib_name, chip_id, module alias) for each chip of the module named in
    `prompt` that has a VERIFIED library but no corpus document.

    Why this exists: a user reads the reference silkscreened on their board
    ("HW-617"), not the chip soldered on it ("TCA9548A"). The registry knows
    the mapping, but `rag.module_forced_libs` only forces a library when the
    chip has a corpus DOCUMENT -- and the corpus is frozen (its embedding
    matrix is aligned by position), so the 42 identities added on 2026-08-19
    carry a verified `lib_name` and no document. They were inert for code
    generation until this function fed them to the existing off-corpus
    lookup pipeline.

    Returns nothing for chips that already have a document (the synchronous
    path handles them -- returning them here would search twice) nor for
    chips with neither (nothing verified to search: the "partial" treatment
    already assumed for gy-80/gy-85).

    The two names are NOT interchangeable, and dropping `chip_id` (as an
    earlier version did, "nothing needs it yet") was the bug: `lib_name` is
    only a SEARCH QUERY, while `chip_id` is the IDENTITY. Downstream, the
    lookup token becomes the cache key, the id of the ad-hoc corpus entry fed
    to the model, the name of the card in the "Composants" tab and the
    `{part}` printed in the banner -- all of which must read "BMP085", not
    "Adafruit BMP085 Library". Measured on 2026-08-20: of the 48 lib_name-only
    registry entries, only 3 have `id == lib_name`, so the divergence is the
    norm, not an edge case. Callers pass `lib_name` as the registry search
    query and keep `chip_id` as the identity (`lookup_component(token=chip_id,
    search_query=lib_name)`).
    """
    mod = detect_module(prompt, modules)
    if mod is None:
        return []
    from .component_registry import by_id
    alias = mod.id
    out: list[tuple[str, str, str]] = []
    for chip_id in mod.chips:
        comp = by_id(chip_id)
        if comp is None or comp.documents or not comp.lib_name:
            continue
        out.append((comp.lib_name, comp.id, alias))
    return out
