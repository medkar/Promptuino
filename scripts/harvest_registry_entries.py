"""Récolte de la moitié MÉCANIQUE des 48 futures entrées corpus (Task 4).

Pour chacun des 48 composants du registre qui n'ont pas encore de document
corpus (``not c.documents and c.lib_name``), interroge le registre Arduino via
``ui.registry_lookup.lookup_component`` : celui-ci cherche la bibliothèque,
l'installe, et rend ses en-têtes réels + son exemple officiel le plus simple.
Ce script n'écrit QUE ce qui a été trouvé — jamais un en-tête ou un exemple
inventé (cf. CLAUDE.md, § composant hors-corpus).

Rejouable : `scripts/registry_harvest.json`, s'il existe, est rechargé et les
entrées déjà en `status == "found"` sont sautées (elles ont déjà coûté leur
~17 s de réseau). Ne lève jamais : un composant en échec est écrit avec son
statut réel et la récolte continue sur le suivant.

Run:
    python scripts/harvest_registry_entries.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.component_registry import REGISTRY  # noqa: E402
from ui.registry_lookup import lookup_component  # noqa: E402
from ui.workspace import workspace_manager  # noqa: E402

OUTPUT_PATH = ROOT / "scripts" / "registry_harvest.json"

# FQBN de référence pour obtenir un fichier de config arduino-cli : n'importe
# quelle carte AVR convient, la recherche/installation de libs ne dépend pas
# du FQBN précis (seul le workspace/config compte).
_FQBN = "arduino:avr:uno"


def _load_existing() -> dict:
    """Contenu déjà récolté ({} si le fichier est absent, illisible ou d'une
    forme inattendue). Ne lève jamais : un fichier cassé dégrade en « rien
    encore récolté », pas en crash."""
    if not OUTPUT_PATH.exists():
        return {}
    try:
        data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(results: dict) -> None:
    OUTPUT_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")


def _components_to_harvest() -> list:
    """Les 48 composants du registre encore sans document corpus, dans
    l'ordre du registre (ordre stable et reproductible d'une exécution à
    l'autre)."""
    return [c for c in REGISTRY if not c.documents and c.lib_name]


def main() -> int:
    components = _components_to_harvest()
    results = _load_existing()

    try:
        cfg = workspace_manager.cli_config(_FQBN)
    except Exception as exc:  # noqa: BLE001 - ne jamais lever, consigner et continuer en "unavailable"
        print(f"[harvest] impossible d'obtenir la config arduino-cli : {exc}")
        cfg = None

    t_start = time.monotonic()
    for comp in components:
        existing = results.get(comp.id)
        if isinstance(existing, dict) and existing.get("status") == "found":
            print(f"{comp.id:<24} deja-trouve   (saute)", flush=True)
            continue

        t0 = time.monotonic()
        try:
            res = lookup_component(comp.id, cfg, search_query=comp.lib_name)
            status = res.status
            entry = {
                "lib_name": res.lib_name,
                "headers": (res.entry or {}).get("headers", []),
                "example_code": (res.entry or {}).get("example_code", ""),
                "status": status,
            }
        except Exception as exc:  # noqa: BLE001 - un échec ne doit jamais arrêter la récolte
            status = "error"
            entry = {
                "lib_name": "",
                "headers": [],
                "example_code": "",
                "status": status,
                "error": str(exc),
            }
        elapsed = time.monotonic() - t0
        results[comp.id] = entry
        _save(results)  # sauvegarde après CHAQUE composant : un crash en cours de route ne perd rien
        print(f"{comp.id:<24} {status:<15} {elapsed:6.1f}s", flush=True)

    total = time.monotonic() - t_start
    n_found = sum(1 for v in results.values()
                  if isinstance(v, dict) and v.get("status") == "found")
    print(f"\n[harvest] termine : {n_found}/{len(components)} en 'found', "
          f"{total:.1f}s de reseau reel cette execution.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
