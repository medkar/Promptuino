"""A* on OccupancyGrid with turn cost.

A* state: (col, row, incoming_direction). We include the arrival direction
into the cell in the state to correctly penalize direction
changes (turn cost > lateral cost).

Encoded directions (0..4):
    0 = none (source cell)
    1 = arrival from the top     (movement +y)
    2 = arrival from the bottom  (movement -y)
    3 = arrival from the left    (movement +x)
    4 = arrival from the right   (movement -x)

The returned path is a list of cells (col, row) from source to target,
without direction.
"""
from __future__ import annotations

import heapq
from typing import Iterable

from .grid import OccupancyGrid


# Movement and "arrival from" direction:
#   neighbor (dc, dr, incoming_dir)
_NEIGHBORS: tuple[tuple[int, int, int], ...] = (
    (0, -1, 2),   # goes up    -> we arrive "from the bottom" in the cell
    (0, 1, 1),    # goes down  -> we arrive "from the top"
    (-1, 0, 4),   # goes left  -> we arrive "from the right"
    (1, 0, 3),    # goes right -> we arrive "from the left"
)


def _manhattan_min(col: int, row: int,
                   targets: Iterable[tuple[int, int]]) -> int:
    """Admissible heuristic: minimum Manhattan to any target."""
    return min(abs(col - tc) + abs(row - tr) for tc, tr in targets)


def astar(grid: OccupancyGrid,
          sources: list[tuple[int, int]],
          targets: list[tuple[int, int]],
          net_id: int,
          turn_penalty: int = 8,
          max_expansions: int | None = None,
          extra_blocked: set[tuple[int, int]] | None = None,
          ) -> list[tuple[int, int]] | None:
    """Finds the shortest path on the grid from source to target.

    `sources` and `targets`: lists of cells (col, row). All the
    source cells start at g=0. The search ends as soon as we
    reach a target cell.

    `net_id`: id of the current net (passed to grid.is_blocked / cell_cost).

    `turn_penalty`: additional cost when changing direction
    (encourages straight wires).

    `max_expansions`: safeguard against infinite loops (None = no
    limit). If exceeded, returns None.

    `extra_blocked`: set of cells (col, row) forbidden in addition to the
    standard blockings (body_mask, pin_owner != self, wires). Used
    to prevent A* from crossing pin_owner=self holes that are
    NOT the target endpoint (= force "come from above": we block
    all the other cells of the rail EXCEPT the endpoint cell, which pushes
    A* to pass through the free lane above/below the BB). The sources and
    targets remain allowed even if they appear in extra_blocked
    (defensively; in practice we don't put them there).

    Returns: list of cells from the chosen source to the reached target,
    inclusive of both endpoints. None if no path found.
    """
    if not sources or not targets:
        return None

    target_set = set(targets)
    # If a source is already a target -> trivial path.
    for s in sources:
        if s in target_set:
            return [s]

    # came_from: (col, row, dir) -> (prev_col, prev_row, prev_dir) | None for sources
    came_from: dict[tuple[int, int, int], tuple[int, int, int] | None] = {}
    # g_score: (col, row, dir) -> best known cost
    g_score: dict[tuple[int, int, int], int] = {}

    open_heap: list[tuple[int, int, int, int, int]] = []
    # Initialize from each source with direction 0 (= free, no initial turn penalty)
    h0 = _manhattan_min
    for sc, sr in sources:
        if grid.is_blocked(sc, sr, net_id):
            # Source blocked: skip. (If all sources blocked -> final failure.)
            continue
        state = (sc, sr, 0)
        g_score[state] = 0
        came_from[state] = None
        heapq.heappush(open_heap, (h0(sc, sr, target_set), 0, sc, sr, 0))

    expansions = 0

    while open_heap:
        if max_expansions is not None and expansions >= max_expansions:
            return None
        expansions += 1

        f, g, col, row, direction = heapq.heappop(open_heap)
        state = (col, row, direction)

        # Stale entry (a better g has been found since)
        if g_score.get(state, -1) != g:
            continue

        if (col, row) in target_set:
            # Path reconstruction
            return _reconstruct(came_from, state)

        for dc, dr, new_dir in _NEIGHBORS:
            nc, nr = col + dc, row + dr
            is_target = (nc, nr) in target_set
            # Movement axis: V if dr != 0 (vertical movement), H otherwise.
            # is_blocked checks the corresponding axis to allow a
            # perpendicular wire to share the cell (crossing allowed).
            move_axis = "V" if dr != 0 else "H"
            if not is_target and grid.is_blocked(nc, nr, net_id, axis=move_axis):
                continue
            # For the targets: just check the bounds
            if is_target and not (0 <= nc < grid.cols and 0 <= nr < grid.rows):
                continue
            # Additional blockings (= "come from above": force the
            # path to go around the pin_owner=self cells that are not
            # the target endpoint). Targets remain allowed.
            if (extra_blocked is not None
                    and not is_target
                    and (nc, nr) in extra_blocked):
                continue

            step = 1
            if not is_target:
                step += grid.cell_cost(nc, nr, net_id)
            if direction != 0 and direction != new_dir:
                step += turn_penalty

            new_g = g + step
            new_state = (nc, nr, new_dir)
            if new_g < g_score.get(new_state, 10**9):
                g_score[new_state] = new_g
                came_from[new_state] = state
                heapq.heappush(open_heap,
                               (new_g + h0(nc, nr, target_set),
                                new_g, nc, nr, new_dir))

    return None


def _reconstruct(came_from: dict, end_state: tuple[int, int, int]
                 ) -> list[tuple[int, int]]:
    """Reconstructs the path (col, row) by walking back came_from."""
    path: list[tuple[int, int]] = []
    state: tuple[int, int, int] | None = end_state
    while state is not None:
        col, row, _dir = state
        path.append((col, row))
        state = came_from.get(state)
    path.reverse()
    return path


def compress_collinear(path: list[tuple[int, int]]
                        ) -> list[tuple[int, int]]:
    """Reduces the path to only the direction-change points.

    A* produces a cell-by-cell list. For the Wire.path rendering
    we only want the corners. Keeps the first and last cell.
    """
    if len(path) <= 2:
        return list(path)
    out = [path[0]]
    for i in range(1, len(path) - 1):
        prev_c, prev_r = path[i - 1]
        cur_c, cur_r = path[i]
        next_c, next_r = path[i + 1]
        dc1, dr1 = cur_c - prev_c, cur_r - prev_r
        dc2, dr2 = next_c - cur_c, next_r - cur_r
        if (dc1, dr1) != (dc2, dr2):
            out.append(path[i])
    out.append(path[-1])
    return out
