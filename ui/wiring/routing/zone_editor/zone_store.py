"""In-memory model + JSON I/O + undo stack for the zone editor.

3 types of zones (colors): "forbid" (red), "cost" (yellow),
"allow" (green). Each cell (col, row) belongs to AT MOST ONE
color. Painting red over a yellow cell removes the yellow.

JSON format (v1):

    {
      "version": 1,
      "cell_size": 8,
      "bb_anchor": {"x": 30, "y": 30},
      "bb_svg": "assets/wiring/breadboards/mini.svg",
      "cost_value": 60,
      "cells": {
        "forbid": [[col, row], ...],
        "cost":   [[col, row], ...],
        "allow":  [[col, row], ...]
      }
    }

bb_anchor: canvas position (BB-local) of the first hole (V+_left row 1).
Used to align the editor grid on the centers of the BB holes. The grid
is offset by `offset = (anchor - cs/2) mod cs` so that the holes
fall at the center of the cells. For the standard BB (mini.svg) anchor
is (30, 30). Since the BB holes are at canvas_x = anchor + k*14, any
cell_size dividing 14 (= 1, 2, 7, 14) aligns ALL the holes
perfectly. cs=4, 8, 28 align partially.

Cells sorted and deduplicated on save (git diff idempotence).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

Color = str  # "forbid" | "cost" | "allow"
Cell = tuple[int, int]  # (col, row)

COLORS: tuple[Color, ...] = ("forbid", "cost", "allow")

# Default = 7: divides 14 (= effective pitch between BB holes counting the
# grooves), so ALL the holes fall at the center of their cell. Other
# "ideal" values: 1, 2, 14. cs=4, 8, 28 don't divide 14 and only align
# part of the holes (1 hole out of 2 or 1 out of 7) — visually visible.
DEFAULT_CELL_SIZE = 7
DEFAULT_COST_VALUE = 60
DEFAULT_BB_SVG = "assets/wiring/breadboards/mini.svg"
# Canvas position (BB-local) of the first hole (V+_left row 1) for mini.svg.
# = BODY_X (5) + INNER_MARGIN (25) = 30 on X and Y.
DEFAULT_BB_ANCHOR: tuple[float, float] = (30.0, 30.0)

JSON_VERSION = 1


def grid_origin_offset(anchor: tuple[float, float],
                        cell_size: int) -> tuple[float, float]:
    """Computes the offset (ox, oy) such that the BB holes fall at the center
    of the editor grid cells.

    Formula: offset = (anchor - cs/2) mod cs.
    """
    cs = float(cell_size)
    ox = (float(anchor[0]) - cs / 2.0) % cs
    oy = (float(anchor[1]) - cs / 2.0) % cs
    return ox, oy


@dataclass
class Action:
    """Atomic action: a batch of cells modified between mouseDown
    and mouseUp. Stores for each cell (prev_color, new_color)."""
    changes: dict[Cell, tuple[Optional[Color], Optional[Color]]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.changes


class ZoneStore:
    """In-memory model of the set of cells painted by color.

    State:
      - cells[color]: set[Cell]
      - cell_size: int (px)
      - cost_value: int (penalty value for the yellow cells)
      - bb_svg: str (path of the edited BB SVG, sanity check)

    Undo: 2 stacks of Action (undo_stack, redo_stack). An atomic Action
    represents the batch of edits made between mouseDown and mouseUp.
    """

    def __init__(self, cell_size: int = DEFAULT_CELL_SIZE,
                 cost_value: int = DEFAULT_COST_VALUE,
                 bb_svg: str = DEFAULT_BB_SVG,
                 bb_anchor: tuple[float, float] = DEFAULT_BB_ANCHOR):
        self.cell_size = cell_size
        self.cost_value = cost_value
        self.bb_svg = bb_svg
        self.bb_anchor = (float(bb_anchor[0]), float(bb_anchor[1]))
        self.cells: dict[Color, set[Cell]] = {c: set() for c in COLORS}
        self.undo_stack: list[Action] = []
        self.redo_stack: list[Action] = []
        self._current_action: Optional[Action] = None
        self._dirty = False

    # ─── Batch editing (mouseDown / move / mouseUp) ──────────────────
    def begin_action(self) -> None:
        """Starts a new batch (= 1 undo entry). Clears redo_stack."""
        self._current_action = Action()
        self.redo_stack.clear()

    def paint(self, cell: Cell, color: Optional[Color]) -> bool:
        """Applies `color` (or None to erase) on the cell.

        Returns True if the cell actually changed state (useful
        to avoid redundant ops during a drag).

        Must be called within the context of a begin_action().
        """
        if color is not None and color not in COLORS:
            raise ValueError(f"color invalide : {color!r}")
        prev = self._cell_color(cell)
        if prev == color:
            return False
        # Don't lose the initial state if the same cell is repainted
        # several times in the same action.
        if self._current_action is None:
            self.begin_action()
        if cell in self._current_action.changes:
            initial, _ = self._current_action.changes[cell]
            self._current_action.changes[cell] = (initial, color)
        else:
            self._current_action.changes[cell] = (prev, color)
        self._apply_cell(cell, prev, color)
        self._dirty = True
        return True

    def end_action(self) -> None:
        """Ends the current batch: push into undo_stack if non-empty."""
        if self._current_action is not None and not self._current_action.is_empty():
            self.undo_stack.append(self._current_action)
        self._current_action = None

    # ─── Undo / redo ─────────────────────────────────────────────────────
    def undo(self) -> Optional[Action]:
        """Undoes the last action. Returns the undone Action to
        allow the widget to re-render only the impacted
        cells. Returns None if nothing to undo."""
        if not self.undo_stack:
            return None
        action = self.undo_stack.pop()
        for cell, (prev, new) in action.changes.items():
            self._apply_cell(cell, new, prev)
        self.redo_stack.append(action)
        self._dirty = True
        return action

    def redo(self) -> Optional[Action]:
        """Replays the last undone action."""
        if not self.redo_stack:
            return None
        action = self.redo_stack.pop()
        for cell, (prev, new) in action.changes.items():
            self._apply_cell(cell, prev, new)
        self.undo_stack.append(action)
        self._dirty = True
        return action

    # ─── Internal helpers ────────────────────────────────────────────────
    def _cell_color(self, cell: Cell) -> Optional[Color]:
        for c in COLORS:
            if cell in self.cells[c]:
                return c
        return None

    def _apply_cell(self, cell: Cell, prev: Optional[Color],
                    new: Optional[Color]) -> None:
        """Switches the cell from prev to new in the sets (without
        touching the undo/dirty tracking)."""
        if prev is not None:
            self.cells[prev].discard(cell)
        if new is not None:
            self.cells[new].add(cell)

    # ─── Public lookups ─────────────────────────────────────────────────
    def color_at(self, cell: Cell) -> Optional[Color]:
        return self._cell_color(cell)

    def total_painted(self) -> int:
        return sum(len(s) for s in self.cells.values())

    def is_dirty(self) -> bool:
        return self._dirty

    # ─── Full (re)set ─────────────────────────────────────────────────
    def clear_all(self) -> None:
        """Clears everything (with undo push)."""
        self.begin_action()
        for color in COLORS:
            for cell in list(self.cells[color]):
                self._current_action.changes[cell] = (color, None)
                self.cells[color].discard(cell)
        self.end_action()
        self._dirty = True

    # ─── JSON serialization ──────────────────────────────────────────────
    def to_dict(self) -> dict:
        out_cells: dict[str, list[list[int]]] = {}
        for color in COLORS:
            sorted_cells = sorted(self.cells[color])
            out_cells[color] = [[c, r] for (c, r) in sorted_cells]
        return {
            "version": JSON_VERSION,
            "cell_size": self.cell_size,
            "bb_anchor": {"x": self.bb_anchor[0], "y": self.bb_anchor[1]},
            "bb_svg": self.bb_svg,
            "cost_value": self.cost_value,
            "cells": out_cells,
        }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self._dirty = False

    @classmethod
    def load(cls, path: Path) -> "ZoneStore":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != JSON_VERSION:
            raise ValueError(
                f"version JSON inconnue : {data.get('version')} "
                f"(attendu {JSON_VERSION})"
            )
        anchor_in = data.get("bb_anchor") or {}
        anchor = (
            float(anchor_in.get("x", DEFAULT_BB_ANCHOR[0])),
            float(anchor_in.get("y", DEFAULT_BB_ANCHOR[1])),
        )
        store = cls(
            cell_size=int(data.get("cell_size", DEFAULT_CELL_SIZE)),
            cost_value=int(data.get("cost_value", DEFAULT_COST_VALUE)),
            bb_svg=str(data.get("bb_svg", DEFAULT_BB_SVG)),
            bb_anchor=anchor,
        )
        cells_in = data.get("cells", {})
        for color in COLORS:
            for entry in cells_in.get(color, []):
                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue
                col, row = int(entry[0]), int(entry[1])
                store.cells[color].add((col, row))
        store._dirty = False
        return store
