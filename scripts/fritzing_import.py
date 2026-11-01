"""Read a Fritzing part (.fzp) and draft what our catalog needs from it.

Fritzing publishes >1800 part definitions whose `<connector>` list IS the
pinout -- exactly the axis 77 of our registry components are missing
(`wiring="unknown"`, TODO #41). Nothing else it holds is as valuable: it
carries NO Arduino library name at all, and its text is English only.

What this tool takes, and what it deliberately leaves:

  TAKEN     connector names, in order       -> `pin_display_labels` + `pin_count`
            title / tags / family           -> keyword and identity HINTS
  LEFT      the description prose           -> we write our own, in French
            the SVG graphics                -> our assets stay ours

⛔ TWO ERRORS THIS TOOL CAUSED, and now guards against (2026-09-07). The batch
of 2026-08-19 imported 40 pinouts; both mistakes were structural, not typos:

  1. It proposed the Fritzing names as `pin_labels`. But `pin_labels` is the
     ROUTING MATCH KEY -- `routing._name_to_pin_index` wants exact equality
     with the pin name `markers` emits. A silkscreen name that isn't that one
     produces NO wire and NO message. `thermistor` carried « pin 0 »/« pin 1 »
     and was drawn with no wire at all. The silkscreen belongs in
     `pin_display_labels`, and only when it differs from the emitted name.
  2. It said nothing about steps 2-4 of the « ajouter un composant » checklist.
     A catalog entry makes a component DRAWABLE, never RECOGNISABLE. Measured
     the same day: 15 prompts naming an imported component, 0 recognised -- a
     solenoid came out drawn as a LED.

Both are now printed with every draft. `placeholder_labels` also flags names
that merely number the pad, which is a part sheet that does not carry the
information at all -- not a formatting issue to strip.

Split on purpose: `parse_fzp` is PURE (stdlib only, no network), so the parsing
rules are tested against fixtures rather than against whatever the network
returns today. `fetch_fzp` is the only part that touches the wire.

Usage:
    python scripts/fritzing_import.py <url-or-path> [<url-or-path> ...]
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FritzingPart:
    title: str = ""
    description: str = ""
    family: str = ""
    tags: tuple[str, ...] = ()
    properties: dict = field(default_factory=dict)
    pins: tuple[str, ...] = ()          # deduplicated, in order
    raw_pin_count: int = 0              # before deduplication

    @property
    def pin_count(self) -> int:
        return len(self.pins)

    @property
    def has_duplicate_rows(self) -> bool:
        """True when Fritzing listed the same pins twice (two header rows)."""
        return self.raw_pin_count > len(self.pins)


def dedup_pins(names: list[str]) -> list[str]:
    """Keep the first occurrence of each pin name, preserving order.

    Fritzing declares one `<connector>` per physical PAD, so a board with two
    header rows lists every pin twice: the DS3231 module reports 10 connectors
    -- GND VCC SDA SCL SQW 32K GND VCC SDA SCL -- for 6 distinct pins.

    ⚠️ Known limit, stated rather than hidden: a part with two genuinely
    DISTINCT pins sharing a name (two independent grounds that must be wired
    separately) collapses to one here. For `pin_labels` -- a list of names to
    print next to a box -- that is what we want; it would be wrong for a
    netlist. `has_duplicate_rows` flags the case so a human can look.
    """
    vus: set[str] = set()
    out: list[str] = []
    for n in names:
        cle = n.strip()
        if not cle or cle in vus:
            continue
        vus.add(cle)
        out.append(cle)
    return out


def parse_fzp(xml_text: str) -> FritzingPart:
    """Parse a `.fzp` document. Raises `ET.ParseError` on malformed XML."""
    root = ET.fromstring(xml_text)

    def texte(balise: str) -> str:
        el = root.find(balise)
        return (el.text or "").strip() if el is not None else ""

    tags = tuple(
        (t.text or "").strip()
        for t in root.findall("./tags/tag")
        if (t.text or "").strip()
    )
    props = {
        (p.get("name") or "").strip(): (p.text or "").strip()
        for p in root.findall("./properties/property")
        if (p.get("name") or "").strip()
    }
    bruts = [
        (c.get("name") or "").strip()
        for c in root.findall("./connectors/connector")
    ]
    return FritzingPart(
        title=texte("title"),
        description=texte("description"),
        family=props.get("family", ""),
        tags=tags,
        properties=props,
        pins=tuple(dedup_pins(bruts)),
        raw_pin_count=len([b for b in bruts if b]),
    )


# Pin counts `ui/wiring/layout/component_catalog.resolve_generic` can draw:
# a single row of 2-8 (plus the odd 9, 11, 13 added by #58), or an EVEN DIP
# of 10-40. Anything else falls into the `undrawable_component` warning, so
# it is better known before the import than discovered on screen.
def is_drawable(pin_count: int) -> bool:
    if 2 <= pin_count <= 8 or pin_count in (9, 11, 13):
        return True
    return 10 <= pin_count <= 40 and pin_count % 2 == 0


# Longest pin label a component box can hold before it reads as prose. Not a
# rendering measurement -- the box width is handled elsewhere -- but the line
# between a PIN NAME ("SQW") and a DESCRIPTION ("SWQ/OUT - Clock Output").
_MAX_LABEL = 10


def prose_labels(pins: tuple[str, ...]) -> list[str]:
    """Labels that read as descriptions rather than pin names.

    Found on the pilot batch of 2026-08-19, and it is the selection rule the
    parser cannot infer on its own: Fritzing carries BOTH the bare chip and the
    breakout board. `core/DS1307.fzp` is the DIP-8 chip, and labels its pins
    « X1 - Crystal », « Vbat - Backup Supply », « SWQ/OUT - Clock Output ».
    `core/rtc_ds3231_breakout.fzp` is the module a beginner actually owns, and
    labels them « GND VCC SDA SCL SQW 32K ».

    Both are correct Fritzing data; only the second is what we draw. Prose
    labels are therefore the signal that the WRONG part was picked -- not a
    formatting problem to strip, a part to replace.
    """
    return [p for p in pins if " - " in p or len(p) > _MAX_LABEL]


# Etiquettes qui ne NOMMENT rien : Fritzing numerote les pads quand la fiche
# ne porte pas de nom de broche. « pin 0 », « Pin 1 », « pin1 », « 2 »...
_PLACEHOLDER_RE = None   # compile paresseusement, voir `placeholder_labels`


def placeholder_labels(pins: tuple[str, ...]) -> list[str]:
    """Etiquettes qui numerotent le pad au lieu de nommer la broche.

    Second signal manquant du lot du 2026-08-19, trouve le 2026-09-07 : ces
    libelles sont passes tels quels au catalogue, ou ils n'ont RIEN nomme.
    `thermistor` portait « pin 0 »/« pin 1 » et `microphone` « pin1 »/« pin2 »
    alors que le detecteur emet `VCC / OUT / GND` -- le routage appariant par
    egalite de nom, les deux composants etaient dessines SANS AUCUN FIL.

    Ce n'est pas un defaut de mise en forme a nettoyer : c'est une fiche qui
    ne porte pas l'information cherchee. Soit une autre fiche la porte, soit
    le brochage se prend ailleurs -- mais on ne recopie pas des numeros de pad.
    """
    global _PLACEHOLDER_RE
    if _PLACEHOLDER_RE is None:
        import re
        _PLACEHOLDER_RE = re.compile(r"^(?:pin|pad|broche)?\s*_?\d+$", re.I)
    return [p for p in pins if _PLACEHOLDER_RE.match(p.strip())]


def fetch_fzp(url_or_path: str) -> str:
    """Read a `.fzp` from disk, or over https for a raw.githubusercontent URL."""
    if url_or_path.startswith(("http://", "https://")):
        from urllib.request import urlopen
        with urlopen(url_or_path, timeout=30) as r:   # noqa: S310
            return r.read().decode("utf-8", errors="replace")
    from pathlib import Path
    return Path(url_or_path).read_text(encoding="utf-8")


def draft(part: FritzingPart) -> str:
    """Human-readable draft, to be reviewed before anything is committed."""
    lignes = [
        f"  titre      : {part.title}",
        f"  famille    : {part.family or '-'}",
        f"  tags       : {', '.join(part.tags) or '-'}",
        f"  broches    : {part.pin_count}  {list(part.pins)}",
    ]
    if part.has_duplicate_rows:
        lignes.append(
            f"  ⚠ {part.raw_pin_count} connecteurs pour {part.pin_count} broches "
            f"distinctes — deux rangees de header, a verifier")
    if not is_drawable(part.pin_count):
        lignes.append(
            f"  ⚠ {part.pin_count} broches : NON dessinable par resolve_generic "
            f"(2-8 en rangee simple, ou 10-40 pair en DIP)")
    prose = prose_labels(part.pins)
    if prose:
        lignes.append(
            f"  ⚠ etiquettes redigees {prose} — c'est probablement la PUCE NUE "
            f"et non le module ; chercher la fiche du breakout")
    numeros = placeholder_labels(part.pins)
    if numeros:
        lignes.append(
            f"  ⚠ etiquettes qui ne NOMMENT rien {numeros} — Fritzing a "
            f"numerote les pads. NE PAS les recopier : chercher une autre "
            f"fiche, ou prendre le brochage ailleurs")

    # ── Ce que le catalogue attend, et pourquoi ce n'est PAS ce qu'on lit ──
    # Le defaut du 2026-09-07 : ce bloc proposait les noms Fritzing comme
    # `pin_labels`. Or `pin_labels` est la CLE D'APPARIEMENT du routage --
    # `routing._name_to_pin_index` cherche l'egalite EXACTE avec le nom de
    # broche que `markers` emet. Un nom de serigraphie qui n'est pas celui-la
    # ne produit AUCUN fil et AUCUN message. Sept composants sont sortis du
    # schema mal cables ou pas cables du tout a cause de ce seul malentendu.
    lignes += [
        "",
        "  --- entree catalogue a REDIGER (ne pas coller telle quelle) ---",
        f"  pin_count={part.pin_count},",
        f"  pin_labels={{...}},        # ⚠ CE QUE `markers` EMET pour ce type,",
        "                             #   PAS ce qui est ecrit sur la carte.",
        "                             #   Le routage apparie par EGALITE DE NOM.",
        *_display_labels_draft(part.pins),
        "",
        "  --- il reste les etapes 2 a 4 de la checklist (CLAUDE.md) ---",
        "  Une entree catalogue rend le composant DESSINABLE, pas RECONNAISSABLE.",
        "  Mesure du 2026-09-07 sur le lot precedent : 15 prompts nommant le",
        "  composant, 0 reconnu -- un solenoide sortait dessine en LED.",
        "    2. detection : candidat dans `_POT_SUBTYPE_CANDIDATES` /",
        "       `_LED_RECLASSIF_CANDIDATES` + lexique `_X_KEYWORDS` en 4 langues",
        "    3. libelle humain dans `instructions._TYPE_LABEL`",
        "    4. test dans `scripts/test_wiring_disambiguation.py`",
        "  (puis 5-7 : ClarifyGroup si famille, registre, nom court <= 13 car.)",
    ]
    return "\n".join(lignes)


def _as_dict(pins: tuple[str, ...]) -> str:
    """`{1: "VCC", 2: "GND"}` — la forme attendue par `CatalogEntry`."""
    return "{" + ", ".join(f'{i + 1}: "{p}"' for i, p in enumerate(pins)) + "}"


def _display_labels_draft(pins: tuple[str, ...]) -> list[str]:
    """Les lignes `pin_display_labels` du brouillon — ou leur absence motivee.

    ⛔ Le brouillon ne doit PAS proposer des libelles qu'il vient lui-meme de
    declarer inutilisables. Trouve en jouant la QA AK5 (2026-09-08) : sur une
    fiche aux pads numerotes il affichait « NE PAS les recopier », puis
    proposait `pin_display_labels={1: "pin 0", 2: "pin 1"}` deux lignes plus
    bas. L'outil se contredisait, et un brouillon qui se contredit fait
    recopier la ligne plutot que lire l'avertissement.

    Une table d'affichage ne sert qu'a REPRODUIRE ce qui est ecrit sur
    l'objet. Des numeros de pad ne sont ecrits nulle part : il n'y a rien a
    reproduire, donc pas de table -- exactement la regle appliquee au
    `reed_switch` et au `tilt_switch` lors du #94.
    """
    numerotes = placeholder_labels(pins)
    if len(numerotes) == len(pins):
        return [
            "  # pas de `pin_display_labels` : les libelles lus ne nomment",
            "  # rien, il n'y a donc rien a reproduire a l'ecran.",
        ]
    if numerotes:
        return [
            f"  pin_display_labels={_as_dict(pins)},",
            f"  # ⚠ a REPRENDRE : {numerotes} ne nomme(nt) rien. Retirer ces",
            "  # entrees, ou chercher une fiche qui porte la vraie serigraphie.",
        ]
    return [
        f"  pin_display_labels={_as_dict(pins)},",
        "                             # la serigraphie lue ici : dessinee, et",
        "                             # SEULEMENT si elle differe du nom emis.",
    ]


def main(argv: list[str]) -> int:
    # Same guard as `bench_rag.py`, and for the same measured reason: under a
    # shell whose stdout is cp1252 (Git Bash here), printing "⚠" raises
    # UnicodeEncodeError and loses the rest of the output mid-print. Hit again
    # one day after fixing it there, which is why it is a habit and not a
    # one-off. A degraded character beats a lost report.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if len(argv) < 2:
        print(__doc__)
        return 2
    for cible in argv[1:]:
        print(f"\n=== {cible}")
        try:
            part = parse_fzp(fetch_fzp(cible))
        except Exception as e:  # noqa: BLE001
            print(f"  ECHEC : {type(e).__name__}: {e}")
            continue
        print(draft(part))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
