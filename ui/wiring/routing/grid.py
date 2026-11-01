"""Occupancy grid for the v3 router.

Model: 4 parallel 2D numpy arrays, each cell = CELL_SIZE px of the canvas.

Layers:
  - body_mask  : 0 free, 1 component body (forbidden), 2 margin (not
                 hard-blocked but expensive in cost_map)
  - pin_owner  : 0 = not a pin, N>0 = cell belongs to the pin of net N
                 (allowed only as an endpoint for net N)
  - wire_owner : 0 = no wire laid, N>0 = cell already occupied by a wire
                 of net N (allowed only for net N)
  - cost_map   : additional cost per cell (uint8, 0-255). Used to
                 penalize without forbidding (BB zones, power zones, etc.)

numpy indexing: arrays[row, col] (row = y, col = x).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


DEFAULT_CELL_SIZE = 6


@dataclass
class GridStats:
    """Snapshot of a grid's statistics (debug / benchmark)."""
    cols: int
    rows: int
    cell_size: int
    blocked_cells: int
    pinned_cells: int
    wired_cells: int
    total_cells: int

    @property
    def free_ratio(self) -> float:
        return 1.0 - (self.blocked_cells + self.wired_cells) / max(1, self.total_cells)


class OccupancyGrid:
    """2D grid modeling the canvas space for the v3 router.

    Coordinates conversion:
        canvas (x, y) [px]  <->  cell (col, row) [index]
        col = floor(x / cell_size),  row = floor(y / cell_size)

    All the `blit_*` / `set_*` / `add_*` helpers clamp to the grid bounds
    (silently) to avoid blowups on components partially outside the
    canvas.
    """

    def __init__(self, canvas_w: float, canvas_h: float,
                 cell_size: int = DEFAULT_CELL_SIZE):
        if cell_size <= 0:
            raise ValueError(f"cell_size doit etre > 0 (recu {cell_size})")
        self.cell_size = cell_size
        self.cols = max(1, int(math.ceil(canvas_w / cell_size)))
        self.rows = max(1, int(math.ceil(canvas_h / cell_size)))

        shape = (self.rows, self.cols)
        self.body_mask = np.zeros(shape, dtype=np.uint8)
        self.pin_owner = np.zeros(shape, dtype=np.int16)
        # Wire occupation per AXIS: a horizontal wire laid marks wire_h,
        # a vertical wire laid marks wire_v. A wire that turns in a
        # cell marks it on both axes. Allows wires to CROSS
        # (perpendicular) without OVERLAPPING (same axis).
        self.wire_h = np.zeros(shape, dtype=np.int16)
        self.wire_v = np.zeros(shape, dtype=np.int16)
        # Kept for API (debug/rip-up): net_id of the occupying wire (any axis)
        self.wire_owner = np.zeros(shape, dtype=np.int16)
        self.cost_map = np.zeros(shape, dtype=np.uint8)

    # ─── Coordinate conversions ──────────────────────────────────────────
    def canvas_to_cell(self, x: float, y: float) -> tuple[int, int]:
        """Canvas (x, y) -> cell (col, row), clamped to bounds."""
        col = max(0, min(self.cols - 1, int(x // self.cell_size)))
        row = max(0, min(self.rows - 1, int(y // self.cell_size)))
        return col, row

    def cell_to_canvas(self, col: int, row: int) -> tuple[float, float]:
        """Cell (col, row) -> canvas (x, y) at the center of the cell."""
        x = col * self.cell_size + self.cell_size / 2.0
        y = row * self.cell_size + self.cell_size / 2.0
        return x, y

    # ─── Blitting helpers (rectangular canvas regions) ──────────────
    def _canvas_rect_to_cell_slice(
        self, x: float, y: float, w: float, h: float
    ) -> tuple[slice, slice] | None:
        """Converts a canvas rectangle into a clamped (row_slice, col_slice).

        End-exclusive convention: a rectangle (x, y, w, h) covers the
        cells whose center is strictly *inside* the rectangle. For
        (0, 0, 8, 8) with cell_size=4: cells (0, 0) and (1, 1) but not
        (2, *) because the right edge at x=8 is the boundary of cell 2.
        Returns None if entirely outside the grid or rectangle empty.
        """
        if w <= 0 or h <= 0:
            return None
        col_lo = max(0, int(math.floor(x / self.cell_size)))
        row_lo = max(0, int(math.floor(y / self.cell_size)))
        col_hi = min(self.cols, int(math.ceil((x + w) / self.cell_size)))
        row_hi = min(self.rows, int(math.ceil((y + h) / self.cell_size)))
        if col_hi <= col_lo or row_hi <= row_lo:
            return None
        return slice(row_lo, row_hi), slice(col_lo, col_hi)

    def blit_body(self, x: float, y: float, w: float, h: float,
                  value: int = 1) -> None:
        """Marks body_mask = value in the canvas rectangle (x, y, w, h)."""
        sl = self._canvas_rect_to_cell_slice(x, y, w, h)
        if sl is None:
            return
        self.body_mask[sl] = value

    def add_cost(self, x: float, y: float, w: float, h: float,
                 cost: int) -> None:
        """Adds `cost` to cost_map in the canvas rectangle (clamped 0-255)."""
        sl = self._canvas_rect_to_cell_slice(x, y, w, h)
        if sl is None:
            return
        region = self.cost_map[sl].astype(np.int32) + int(cost)
        self.cost_map[sl] = np.clip(region, 0, 255).astype(np.uint8)

    def set_max_cost(self, x: float, y: float, w: float, h: float,
                      cost: int) -> None:
        """Sets cost_map = max(existing, cost) on the rectangle.

        Used for the HOLE_LINE_COST bands: the band intersections
        must NOT add up (otherwise the cells at the
        intersections cost 2x or 3x the HOLE_LINE_COST, which forces
        A* into absurd paths to avoid them — staircases, detours).
        """
        sl = self._canvas_rect_to_cell_slice(x, y, w, h)
        if sl is None:
            return
        self.cost_map[sl] = np.maximum(self.cost_map[sl], int(cost))

    def set_pin(self, x: float, y: float, net_id: int,
                radius_cells: int = 0) -> None:
        """Marks the canvas cell (x, y) as a pin of net `net_id`.

        `radius_cells > 0`: also marks a disk (Manhattan) around it to
        widen the endpoint (useful when the pin position falls near a
        cell boundary).

        Cells marked as pins are automatically cleared from the
        body_mask: a pin must always be reachable by A* (otherwise
        a pin on the edge of a blocked body would become inaccessible).
        """
        col, row = self.canvas_to_cell(x, y)
        for dr in range(-radius_cells, radius_cells + 1):
            for dc in range(-radius_cells, radius_cells + 1):
                if abs(dr) + abs(dc) > radius_cells:
                    continue
                rr, cc = row + dr, col + dc
                if 0 <= rr < self.rows and 0 <= cc < self.cols:
                    self.pin_owner[rr, cc] = net_id
                    self.body_mask[rr, cc] = 0

    def set_pin_cells(self, cells: list[tuple[int, int]],
                      net_id: int) -> None:
        """Marks a list of cells (col, row) as pins of net `net_id`."""
        for col, row in cells:
            if 0 <= col < self.cols and 0 <= row < self.rows:
                self.pin_owner[row, col] = net_id

    def carve_channel(self, x0: float, y0: float, x1: float, y1: float,
                      half_width: int = 0) -> None:
        """Forces body_mask = 0 along a canvas segment (x0,y0)->(x1,y1).

        Used to "drill" a free channel from the edge of a component
        body toward the position of a pin marker buried in the body.
        `half_width` extends the channel by N cells on each side.
        """
        c0, r0 = self.canvas_to_cell(x0, y0)
        c1, r1 = self.canvas_to_cell(x1, y1)
        # Simple Bresenham
        dx = abs(c1 - c0)
        dy = abs(r1 - r0)
        sx = 1 if c0 < c1 else -1
        sy = 1 if r0 < r1 else -1
        err = dx - dy
        col, row = c0, r0
        while True:
            for dr in range(-half_width, half_width + 1):
                for dc in range(-half_width, half_width + 1):
                    rr, cc = row + dr, col + dc
                    if 0 <= rr < self.rows and 0 <= cc < self.cols:
                        self.body_mask[rr, cc] = 0
            if col == c1 and row == r1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                col += sx
            if e2 < dx:
                err += dx
                row += sy

    # ─── Per-cell lookups (used by A*) ─────────────────────────────
    def is_blocked(self, col: int, row: int, net_id: int,
                    axis: str | None = None) -> bool:
        """True if the cell is forbidden for routing net `net_id`.

        Rule "wires may cross but not overlap":
          - 2 wires may share a cell IF their axes are
            perpendicular (clean "+" crossing)
          - 2 wires may NOT share a cell on the same axis
            (continuous overlap, unreadable) — NO EXCEPTION, even
            for 2 wires of the same net. The criterion is visual, not electrical.

        `axis="H"` or `"V"`: checks the corresponding axis. An incoming H
        wire is blocked if another wire has already marked wire_h here. Allows
        perpendicular crossing.

        `axis=None`: skip the wire check (useful for A* SOURCES — we don't
        check the axis at the starting point, A* will test
        each outgoing move).
        """
        if not (0 <= col < self.cols and 0 <= row < self.rows):
            return True
        if self.body_mask[row, col] == 1:
            return True
        po = int(self.pin_owner[row, col])
        if po != 0 and po != net_id:
            return True
        if axis == "H":
            wh = int(self.wire_h[row, col])
            if wh != 0:
                return True
        elif axis == "V":
            wv = int(self.wire_v[row, col])
            if wv != 0:
                return True
        # axis=None: no wire check (A* source cell)
        return False

    def cell_cost(self, col: int, row: int, net_id: int) -> int:
        """Cost to enter the cell (assumes `is_blocked` False).

        Returns `cost_map[row, col]` with no exception. Before, the
        pin_owner=net_id cells returned 0 (= "the clean rail is free"),
        which made A* prefer to transit VERTICALLY along
        the rail rather than passing ABOVE-BB. Result: the
        R6 descent (which must be "vertical from the top of the BB") was
        replaced by a LATERAL entry into the rail + vertical
        traversal over 20+ cells of clean holes.

        With a normal cost_map (= HOLE_LINE_COST=60 in the bands), the
        clean rails cost as much as the other bands: A* no longer
        prefers them for transit, and the R6/R7 corner descents are
        built OUTSIDE A* (via prepend/append) on a col parallel to the
        rail (not the rail itself), with a final 1-cell jog to
        enter the endpoint hole.
        """
        return int(self.cost_map[row, col])

    # ─── Laying / removing wires (rip-up support) ─────────────────────────
    def mark_wire(self, cells: list[tuple[int, int]], net_id: int) -> None:
        """Marks the cells as occupied by the wire of net `net_id`.

        For each cell of the path, we determine the axis (H/V) traversed by
        looking at the prev/next neighbors in the sequence:
          - straight segment H: wire_h marked
          - straight segment V: wire_v marked
          - TURN cell: H and V marked (turn cell blocked on both
            axes for the other wires)
          - endpoint (single neighbor): only the neighbor's axis is marked
        """
        for i, (col, row) in enumerate(cells):
            if not (0 <= col < self.cols and 0 <= row < self.rows):
                continue
            self.wire_owner[row, col] = net_id
            axes: set[str] = set()
            if i > 0:
                pc, pr = cells[i - 1]
                if pc != col:
                    axes.add("H")
                elif pr != row:
                    axes.add("V")
            if i < len(cells) - 1:
                nc, nr = cells[i + 1]
                if nc != col:
                    axes.add("H")
                elif nr != row:
                    axes.add("V")
            if "H" in axes:
                self.wire_h[row, col] = net_id
            if "V" in axes:
                self.wire_v[row, col] = net_id

    def unmark_wire(self, cells: list[tuple[int, int]], net_id: int) -> None:
        """Removes the wire marking (only if it matches the given net)."""
        for col, row in cells:
            if 0 <= col < self.cols and 0 <= row < self.rows:
                if int(self.wire_owner[row, col]) == net_id:
                    self.wire_owner[row, col] = 0
                if int(self.wire_h[row, col]) == net_id:
                    self.wire_h[row, col] = 0
                if int(self.wire_v[row, col]) == net_id:
                    self.wire_v[row, col] = 0

    # ─── Stats / debug ────────────────────────────────────────────────────
    def stats(self) -> GridStats:
        return GridStats(
            cols=self.cols,
            rows=self.rows,
            cell_size=self.cell_size,
            blocked_cells=int(np.count_nonzero(self.body_mask == 1)),
            pinned_cells=int(np.count_nonzero(self.pin_owner)),
            wired_cells=int(np.count_nonzero(self.wire_owner)),
            total_cells=self.rows * self.cols,
        )
