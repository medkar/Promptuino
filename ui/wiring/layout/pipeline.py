"""Orchestrator of the wiring pipeline (production).

Bridge between netlist extraction/inference (`ui/wiring/`) and rendering
(placement `layout/` + routing `routing/` + SVG render `layout/renderer.py`).

Main entry point: `render_complete(code, board_id, ...)`.

Strategy:
  code (.ino) ──► generate_wiring ──► Netlist
                                              │
                                              ▼
                              _netlist_v1_to_dicts (adapter)
                                              │
                                              ▼
                              layout.place_scene ──► PlacedScene
                                              │
                                              ▼
                              routing.route_wires ──► list[Wire]
                                              │
                                              ▼
                              SceneRenderer.render ──► SVG
                                              │
                                              ▼
                              instructions.render_instructions ──► markdown
"""
from __future__ import annotations

from pathlib import Path

from .. import wiring_pipeline as _v1_pipeline
from .. import instructions as _v1_instructions
from ..netlist import Netlist as _V1Netlist

from .layout import place_scene
from ..routing import route_wires as _route_wires
from .renderer import SceneRenderer


# Resolution board_id → board SVG file.
_ASSETS_BOARDS_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "assets" / "wiring" / "boards"
)

_BOARD_SVG_BY_ID: dict[str, Path] = {
    "arduino_uno_r3":   _ASSETS_BOARDS_ROOT / "arduino" / "uno_r3.svg",
    "arduino_uno_r4":   _ASSETS_BOARDS_ROOT / "arduino" / "uno_r4.svg",
    "arduino_nano":     _ASSETS_BOARDS_ROOT / "arduino" / "nano.svg",
    "arduino_leonardo": _ASSETS_BOARDS_ROOT / "arduino" / "leonardo.svg",
    "arduino_mega_2560": _ASSETS_BOARDS_ROOT / "arduino" / "mega_2560.svg",
}


def _board_svg_path(board_id: str) -> Path | None:
    """Returns the board SVG path or None if the asset does not exist."""
    p = _BOARD_SVG_BY_ID.get(board_id)
    if p is None or not p.exists():
        return None
    return p


def _netlist_v1_to_dicts(netlist: _V1Netlist) -> list[dict]:
    """Adapts the v1 Netlist to the `list[dict]` format expected by place_scene v2.

    V1 Component → v2 dict with `ref`, `type` and `pins` (list of
    `{"name", "net"}`). We filter out the non-physical `inferred` components:
    the resistors added by the v1 inference are kept (they have a
    catalog asset), it is up to the v1 rules to decide what is hardware.
    """
    return [
        {
            "ref": comp.ref,
            "type": comp.type,
            "pins": [
                {"name": p.name, "net": p.net}
                for p in comp.pins
            ],
            "attributes": dict(comp.attributes),
        }
        for comp in netlist.components
    ]


def analyze_netlist(code: str, board_id: str,
                        prompt: str = "", context: str = "",
                        prompts_by_fn: dict | None = None) -> _V1Netlist:
    """Step 1: parse code (+ prompt + context + prompts_by_fn) -> Netlist
    v1 (with ambiguous components marked `_confidence: low` in their
    attributes).

    `prompts_by_fn` lets the disambiguation and the modal use
    the SPECIFIC prompt of each component's fn -- useful after an
    iterate where the current prompt is no longer the one that generated fn-1.
    """
    return _v1_pipeline.generate_wiring(code, board_id,
                                         prompt=prompt, context=context,
                                         prompts_by_fn=prompts_by_fn)


def _build_scene_wires_svg_md(netlist, board_id, theme, mode, lang):
    """Internal helper: returns (svg, md, placed_scene, wires).

    On failure (unsupported board, empty netlist, pipeline exception),
    returns ("", "", None, []).
    """
    board_path = _board_svg_path(board_id)
    if board_path is None:
        return ("", "", None, [])

    netlist_dicts = _netlist_v1_to_dicts(netlist)
    if not netlist_dicts:
        import sys
        print(f"[wiring] netlist vide (aucun composant extrait du code, "
              f"board={board_id}, components_v1={len(netlist.components)})",
              file=sys.stderr)
        return ("", "", None, [])

    try:
        scene = place_scene(netlist_dicts, board_path)
        wires = _route_wires(scene, netlist_dicts)
        svg = SceneRenderer(scene, wires, lang=lang).render()
    except Exception:
        import sys, traceback
        print(f"[wiring] exception dans le pipeline :", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print(f"[wiring] netlist recu: {netlist_dicts!r}", file=sys.stderr)
        return ("", "", None, [])

    md = _v1_instructions.render_instructions(netlist, mode=mode, lang=lang)
    return (svg, md, scene, wires)


def render_netlist(netlist: _V1Netlist, board_id: str,
                       theme: str = "light",
                       mode: str = "simple",
                       lang: str = "fr") -> tuple[str, str]:
    """Step 2: netlist (possibly mutated after modal) -> (svg, md).

    If the board has no v2 SVG asset or if the netlist is empty, returns
    ("", "") -- the caller can then display an error banner.
    """
    svg, md, _scene, _wires = _build_scene_wires_svg_md(
        netlist, board_id, theme, mode, lang)
    return (svg, md)


def render_netlist_with_meta(netlist: _V1Netlist, board_id: str,
                                 theme: str = "light",
                                 mode: str = "simple",
                                 lang: str = "fr"):
    """Variant also returning placed_scene + wires for the interactive
    SchemaView. Returns (svg, md, placed_scene, wires) or
    ("", "", None, []) on failure.
    """
    return _build_scene_wires_svg_md(netlist, board_id, theme, mode, lang)


def render_complete(code: str, board_id: str,
                        theme: str = "light",
                        mode: str = "simple",
                        lang: str = "fr",
                        prompt: str = "",
                        context: str = "",
                        ) -> tuple[str, str]:
    """One-shot v2 pipeline: code → (svg, instructions_md). Handy
    helper for the tests / scripts that do not go through the ambiguous
    component confirmation modal.

    For the UI path (with a possible modal), use
    `analyze_netlist` then `render_netlist` separately.
    """
    netlist = analyze_netlist(code, board_id,
                                  prompt=prompt, context=context)
    return render_netlist(netlist, board_id,
                              theme=theme, mode=mode, lang=lang)
