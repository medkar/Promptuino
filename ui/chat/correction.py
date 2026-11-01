"""Logique de la correction "ce n'est pas le bon composant" (F2 etape 5).

Pur Python (pas de Qt). Le chat conclut la conversation de correction par
une ligne `CORRECTION: <id>`. Ces helpers extraient le marqueur, le
nettoient du texte affiche, et fabriquent le prompt corrige a renvoyer
dans le Studio (prompt d'origine + le vrai composant). Import du catalogue
paresseux (dans la fonction) pour ne pas tirer de dependance lourde a
l'import du module.
"""
from __future__ import annotations

import re

# Ligne "CORRECTION: <id>" — insensible a la casse, tolere "CORRECTION :".
_MARKER_RE = re.compile(r"^\s*CORRECTION\s*:\s*(.+?)\s*$",
                        re.IGNORECASE | re.MULTILINE)


def parse_correction_marker(text: str) -> str | None:
    """Id du DERNIER `CORRECTION: <id>` (minuscule, ponctuation finale
    retiree). None si absent ou 'unknown'."""
    if not text:
        return None
    matches = _MARKER_RE.findall(text)
    if not matches:
        return None
    ident = matches[-1].strip().strip(".").strip().lower()
    if not ident or ident == "unknown":
        return None
    return ident


def strip_correction_marker(text: str) -> str:
    """Retire toutes les lignes `CORRECTION: ...` du texte affiche."""
    return _MARKER_RE.sub("", text).rstrip()


def human_component_name(marker: str) -> str:
    """Nom lisible d'un marqueur pour les libelles de bouton."""
    if marker.startswith("leds:"):
        n = marker.split(":", 1)[1]
        return f"{n} LED" + ("s" if n != "1" else "")
    if marker == "leds":
        return "LEDs"
    try:
        from ..wiring.layout.component_catalog import lookup
        entry = lookup(marker)
    except Exception:
        entry = None
    name = getattr(entry, "name", None) if entry is not None else None
    return name or marker


def build_modify_seed(pins: str, target: str) -> str:
    """Texte de base injecté dans le prompt Studio pour une correction issue du
    filet « mauvais composant ». Nomme le vrai composant et sa broche, SANS
    préfixe magique : le mode « Modifier » est désormais activé explicitement
    par StudioView.open_modify_flow. Ex. « LED sur D9 : » — l'élève complète
    ensuite le comportement voulu."""
    name = human_component_name(target)
    return f"{name} sur {pins} : "
