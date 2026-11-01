"""Wiring pipeline orchestrator.

Main entry point: `generate_wiring(code, board_id)`.

  code (.ino)  ─┐
                ├─ markers.extract_netlist  ─►  Raw netlist
  board_id     ─┘                                │
                                                 ▼
                              inference.apply_rules  +  detect_conflicts
                                                 │
                                                 ▼
                                         Enriched netlist
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from . import inference, markers
from .netlist import Netlist


def generate_wiring(code: str, board_id: str,
                    project_path: Path | str | None = None,
                    prompt: str = "", context: str = "",
                    prompts_by_fn: dict | None = None,
                    suppressed_headers: frozenset[str] = frozenset()
                    ) -> Netlist:
    """Build an enriched netlist from the Arduino code.

    Args:
        code          : complete .ino source.
        board_id      : catalog id (e.g. "arduino_uno_r3").
        project_path  : if provided, persists the netlist into
                        `<project_path>/<projet>.wiring.json`.
        prompt        : natural-language user prompt (forwarded to the
                        static detector for semantic disambiguation).
        context       : project context file content (BOM, specs).
        prompts_by_fn : dict {fn_id_token: prompt} (key = "fn-N") enables
                        per-fn scoping of the disambiguation. Otherwise the
                        global prompt is used.

    Returns the `Netlist` (possibly empty if there is nothing to infer).
    """
    netlist = markers.extract_netlist(code, board_id,
                                       prompt=prompt, context=context,
                                       prompts_by_fn=prompts_by_fn,
                                       suppressed_headers=suppressed_headers)
    inference.apply_rules(netlist)
    inference.detect_conflicts(netlist)

    netlist.metadata.setdefault("generated_at",
                                datetime.now(tz=timezone.utc).isoformat())
    netlist.metadata.setdefault("code_hash", _hash_code(code))

    if project_path is not None:
        try:
            _persist(netlist, Path(project_path))
        except OSError:
            # Persistence is best-effort — a write-only project
            # must not block displaying the dialog.
            pass

    return netlist


# ─── Persistence ────────────────────────────────────────────────────────
def _persist(netlist: Netlist, project_dir: Path) -> None:
    """Write `<project_dir>/<projet>.wiring.json`.

    The file name follows the <projet>.<ext> convention where <projet> is
    the folder name (consistent with .ino and .promptuino.json).
    """
    project_dir = project_dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    name = project_dir.name
    target = project_dir / f"{name}.wiring.json"
    target.write_text(
        json.dumps(netlist.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _hash_code(code: str) -> str:
    return hashlib.sha1(code.encode("utf-8", errors="replace")).hexdigest()
