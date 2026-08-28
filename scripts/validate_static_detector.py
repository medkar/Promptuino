"""Validation du detecteur Python statique vs balises IA.

Pour chaque fixture .ino :
1. Parse les balises IA -> netlist "attendu" (oracle)
2. Strip les balises et appelle extract_netlist (-> netlist "detecte")
3. Compare type/pins/nets ; rapporte les divergences

Usage : `python scripts/validate_static_detector.py`
"""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Stub ui pour eviter les imports lourds (numpy, Qt, etc.)
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg
ui_wiring_pkg = types.ModuleType("ui.wiring")
ui_wiring_pkg.__path__ = [str(ROOT / "ui" / "wiring")]
sys.modules["ui.wiring"] = ui_wiring_pkg

from ui.wiring.markers import extract_netlist, parse_wiring_blocks


_WIRING_BLOCK_RE = re.compile(
    r"/\*\s*<<<\s*fn-\d+_wiring\s*>>>.*?<<<\s*end\s*>>>\s*\*/",
    re.IGNORECASE | re.DOTALL,
)


def strip_ai_markers(code: str) -> str:
    """Retire tous les blocs `<<< fn-N_wiring >>>` du code source."""
    return _WIRING_BLOCK_RE.sub("", code)


def _component_signature(c) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Signature comparable d'un composant : (type, pins triees par nom)."""
    return (c.type, tuple(sorted((p.name, p.net) for p in c.pins)))


def _diff(expected: list, detected: list) -> tuple[list, list, list]:
    """Compare les 2 listes par signature (type+pins). Retourne (matched, only_expected, only_detected)."""
    exp_sigs = {_component_signature(c): c for c in expected}
    det_sigs = {_component_signature(c): c for c in detected}
    common = exp_sigs.keys() & det_sigs.keys()
    matched = [(exp_sigs[s], det_sigs[s]) for s in common]
    only_exp = [c for s, c in exp_sigs.items() if s not in common]
    only_det = [c for s, c in det_sigs.items() if s not in common]
    return matched, only_exp, only_det


def _format_comp(c) -> str:
    pins = ", ".join(f"{p.name}={p.net}" for p in c.pins)
    return f"{c.type}({c.ref}, [{pins}])"


def main() -> int:
    fixtures_dir = ROOT / "tests" / "wiring" / "fixtures"
    fixtures = sorted(fixtures_dir.glob("*.ino"))
    if not fixtures:
        print(f"Aucun fixture dans {fixtures_dir}")
        return 1

    print(f"Detecteur Python statique vs balises IA — {len(fixtures)} fixtures\n")
    overall_ok = True
    for f in fixtures:
        code = f.read_text(encoding="utf-8")

        # Oracle = balises IA parsees seules
        blocks = parse_wiring_blocks(code)
        expected = [c for comps in blocks.values() for c in comps]
        if not expected:
            print(f"  {f.name}: pas de balise IA, skip")
            continue

        # Detecte = code strippe -> extract_netlist
        stripped = strip_ai_markers(code)
        detected_nl = extract_netlist(stripped, board_id="arduino_uno_r3")
        detected = list(detected_nl.components)

        matched, only_exp, only_det = _diff(expected, detected)
        ok = not only_exp and not only_det
        status = "OK" if ok else "MISMATCH"
        print(f"  {f.name}: {status}  (matched={len(matched)}, manqu={len(only_exp)}, ajoutes={len(only_det)})")
        for e in only_exp:
            print(f"    - manque  : {_format_comp(e)}")
        for d in only_det:
            print(f"    + ajoute  : {_format_comp(d)}")
        if not ok:
            overall_ok = False

    print()
    print("Bilan global :", "OK" if overall_ok else "MISMATCH (a iterer)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
