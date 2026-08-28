"""Read a Fritzing part (.fzp) and draft what our catalog needs from it.

Fritzing publishes >1800 part definitions whose `<connector>` list IS the
pinout -- exactly the axis 77 of our registry components are missing
(`wiring="unknown"`, TODO #41). Nothing else it holds is as valuable: it
carries NO Arduino library name at all, and its text is English only.

What this tool takes, and what it deliberately leaves:

  TAKEN     connector names, in order       -> `pin_labels` + `pin_count`
            title / tags / family           -> keyword and identity HINTS
  LEFT      the description prose           -> we write our own, in French
            the SVG graphics                -> our assets stay ours

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
    lignes.append(f"  catalogue  : pin_count={part.pin_count}, "
                  f"pin_labels={list(part.pins)}")
    return "\n".join(lignes)


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
