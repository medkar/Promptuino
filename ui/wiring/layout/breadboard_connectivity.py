"""Electrical connectivity model of a breadboard.

For each hole (col_id, row), determines which "net" it sits on.
Two holes on the same net are electrically connected.

Layout (cf. `breadboard_generator.py`):
- Tie-strips: for each row, 5 left holes (a-e) connected together,
  5 right holes (f-j) connected together. So 2 tie-strip nets per row.
- Power rails: each rail (V+_left, GND_left, V+_right, GND_right) connects
  ALL the holes of its column. 4 rail nets in total.

Reused by:
- The placer (Phase 2): to validate that a component occupies distinct nets
  or to identify the net of a placed pin.
- The router (Phase 3): to avoid routing a wire between 2 holes already
  connected by the breadboard.
- The click-to-highlight (future Phase, interactive editor): to highlight
  all the holes on the same net as a clicked hole.

Usage:
    conn = BreadboardConnectivity(rows=17)
    net = conn.net_of("a", 5)              # 'ts_left_5'
    net = conn.net_of("V+_left", 10)       # 'V+_left'
    same = conn.are_connected(("a", 5), ("c", 5))  # True (same tie-strip)
    holes = conn.holes_on_net("ts_left_5") # [(a,5), (b,5), (c,5), (d,5), (e,5)]
"""
from __future__ import annotations

from dataclasses import dataclass

# Letters of the tie-strip cols (left and right of the central channel)
_LEFT_TS_LETTERS  = ("a", "b", "c", "d", "e")
_RIGHT_TS_LETTERS = ("f", "g", "h", "i", "j")
_RAIL_IDS = ("V+_left", "GND_left", "V+_right", "GND_right")


@dataclass
class BreadboardConnectivity:
    """Connectivity model for a breadboard of N rows."""

    rows: int

    def __post_init__(self):
        if self.rows < 1:
            raise ValueError(f"rows={self.rows} doit etre >= 1")

    # ─── Net identification ────────────────────────────────────────
    def net_of(self, col_id: str, row: int) -> str:
        """Unique identifier of the net a hole belongs to.

        Returns:
            - 'ts_left_<row>'  for the left tie-strips (a-e)
            - 'ts_right_<row>' for the right tie-strips (f-j)
            - 'V+_left' / 'GND_left' / 'V+_right' / 'GND_right' for the rails
        """
        if not (1 <= row <= self.rows):
            raise ValueError(f"row={row} hors limites [1, {self.rows}]")

        if col_id in _LEFT_TS_LETTERS:
            return f"ts_left_{row}"
        if col_id in _RIGHT_TS_LETTERS:
            return f"ts_right_{row}"
        if col_id in _RAIL_IDS:
            # Rail connected over its whole height, regardless of the row
            return col_id
        raise ValueError(f"col_id inconnu: {col_id}")

    # ─── Connectivity tests ────────────────────────────────────────
    def are_connected(self,
                      hole1: tuple[str, int],
                      hole2: tuple[str, int],
                      ) -> bool:
        """True if the 2 holes are on the same net (electrically linked)."""
        return self.net_of(*hole1) == self.net_of(*hole2)

    # ─── Enumeration of a net's holes ───────────────────────────────
    def holes_on_net(self, net_id: str) -> list[tuple[str, int]]:
        """List of all holes on the specified net."""
        if net_id.startswith("ts_left_"):
            row = int(net_id.removeprefix("ts_left_"))
            self._check_row(row)
            return [(letter, row) for letter in _LEFT_TS_LETTERS]
        if net_id.startswith("ts_right_"):
            row = int(net_id.removeprefix("ts_right_"))
            self._check_row(row)
            return [(letter, row) for letter in _RIGHT_TS_LETTERS]
        if net_id in _RAIL_IDS:
            return [(net_id, row) for row in range(1, self.rows + 1)]
        raise ValueError(f"net_id inconnu: {net_id}")

    def all_nets(self) -> list[str]:
        """List of all nets available on the breadboard."""
        nets: list[str] = []
        for row in range(1, self.rows + 1):
            nets.append(f"ts_left_{row}")
            nets.append(f"ts_right_{row}")
        nets.extend(_RAIL_IDS)
        return nets

    # ─── Helpers ──────────────────────────────────────────────────────
    def _check_row(self, row: int) -> None:
        if not (1 <= row <= self.rows):
            raise ValueError(f"row={row} hors limites [1, {self.rows}]")
