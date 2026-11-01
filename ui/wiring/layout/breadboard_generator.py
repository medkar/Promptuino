"""Procedural generator for variable-height breadboards.

Produces a breadboard SVG following the convention established on `mini.svg`:
- Fixed horizontal layout: [V+ V-] channel [5 ts a-e] channel [5 ts f-j] channel [V- V+]
  (14 cols + 3 channels, body width 498 px)
- Variable height: between 17 (mini) and 63 (full-size) rows.

Placement convention: pitch 28 px, channels 14 px (adds 14 to the pitch
when crossing a channel, so 42 px col-to-col cross-channel).

Main API:
    bb = Breadboard(rows=30)
    svg_str = bb.render()
    cx, cy = bb.hole_position('a', row=5)   # tie-strip col 'a', row 5
    cx, cy = bb.hole_position('V+_left', row=10)
    width, height = bb.size                  # tuple (vb_w, vb_h)
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ─── Constants (consistent with mini.svg) ───────────────────────────────
PITCH = 28
SILLON_CENTRAL = 56   # 2 steps: central channel (e→f = 3 steps = 0.3", DIP footprint)
SILLON_RAIL    = 14   # rail↔tie-strip gaps (no real 0.1" constraint)
COLS_PER_TIESTRIP = 5
COLS_PER_RAIL = 2
HOLE_R = 3.5
INNER_MARGIN_X = 25
INNER_MARGIN_Y = 25
OUTER_MARGIN = 5
BODY_RY = 6
STRIPE_W = 2

ROWS_MIN = 17     # Nano size (mini.svg)
ROWS_MAX = 63     # full-size 830-tie-points size

# Horizontal offsets of the cols (from the left of the inner body)
LEFT_RAIL_OFFSETS  = [0, 28]
LEFT_TS_OFFSETS    = [70 + i * PITCH for i in range(COLS_PER_TIESTRIP)]
RIGHT_TS_OFFSETS   = [LEFT_TS_OFFSETS[-1] + PITCH + SILLON_CENTRAL + i * PITCH
                      for i in range(COLS_PER_TIESTRIP)]
RIGHT_RAIL_OFFSETS = [RIGHT_TS_OFFSETS[-1] + PITCH + SILLON_RAIL + i * PITCH
                      for i in range(COLS_PER_RAIL)]
ALL_OFFSETS = LEFT_RAIL_OFFSETS + LEFT_TS_OFFSETS + RIGHT_TS_OFFSETS + RIGHT_RAIL_OFFSETS

BODY_W = 2 * INNER_MARGIN_X + ALL_OFFSETS[-1]   # 498 (constant)
BODY_X = OUTER_MARGIN
BODY_Y = OUTER_MARGIN

# Colors
BODY_FILL    = "#ffffff"
BODY_STROKE  = "#a8a8a8"
CHANNEL_FILL = "#e8e8e8"
HOLE_FILL    = "#222222"
RAIL_RED     = "#d62728"
RAIL_BLUE    = "#1f77b4"
LABEL_GRAY   = "#666666"

# Mapping col-name -> offset
TIESTRIP_LETTERS = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
_COL_OFFSETS: dict[str, int] = {
    "V+_left":  LEFT_RAIL_OFFSETS[0],
    "GND_left": LEFT_RAIL_OFFSETS[1],
    **{letter: off for letter, off in zip(TIESTRIP_LETTERS[:5], LEFT_TS_OFFSETS)},
    **{letter: off for letter, off in zip(TIESTRIP_LETTERS[5:], RIGHT_TS_OFFSETS)},
    "V+_right":  RIGHT_RAIL_OFFSETS[0],
    "GND_right": RIGHT_RAIL_OFFSETS[1],
}


@dataclass
class Breadboard:
    """Procedural breadboard with parametrable height.

    `rows`: number of rows, between 17 and 63 inclusive.
    """
    rows: int

    # Computed at construction
    body_h: int = field(init=False)
    vb_w:   int = field(init=False)
    vb_h:   int = field(init=False)

    def __post_init__(self):
        if not (ROWS_MIN <= self.rows <= ROWS_MAX):
            raise ValueError(
                f"rows={self.rows} hors limites [{ROWS_MIN}, {ROWS_MAX}]"
            )
        self.body_h = 2 * INNER_MARGIN_Y + (self.rows - 1) * PITCH
        self.vb_w   = BODY_W + 2 * OUTER_MARGIN
        self.vb_h   = self.body_h + 2 * OUTER_MARGIN

    # ─── Position API ────────────────────────────────────────────────
    @property
    def size(self) -> tuple[int, int]:
        """(width, height) of the viewBox."""
        return (self.vb_w, self.vb_h)

    def hole_position(self, col_id: str, row: int) -> tuple[float, float]:
        """Canvas position (cx, cy) of a hole.

        Args:
            col_id : 'a'..'j' for the tie-strips, 'V+_left'/'GND_left'/
                     'V+_right'/'GND_right' for the rails.
            row    : 1-indexed (1..rows).
        """
        if col_id not in _COL_OFFSETS:
            raise ValueError(f"col_id inconnu: {col_id}")
        if not (1 <= row <= self.rows):
            raise ValueError(f"row={row} hors limites [1, {self.rows}]")
        cx = BODY_X + INNER_MARGIN_X + _COL_OFFSETS[col_id]
        cy = BODY_Y + INNER_MARGIN_Y + (row - 1) * PITCH
        return (cx, cy)

    def all_tiestrip_holes(self) -> dict[tuple[str, int], tuple[float, float]]:
        """All tie-strip hole positions: {(letter, row): (cx, cy)}."""
        return {
            (letter, row): self.hole_position(letter, row)
            for letter in TIESTRIP_LETTERS
            for row in range(1, self.rows + 1)
        }

    def all_rail_holes(self) -> dict[tuple[str, int], tuple[float, float]]:
        """All rail hole positions: {(rail_id, row): (cx, cy)}."""
        return {
            (rail_id, row): self.hole_position(rail_id, row)
            for rail_id in ("V+_left", "GND_left", "V+_right", "GND_right")
            for row in range(1, self.rows + 1)
        }

    # ─── SVG rendering ────────────────────────────────────────────────────
    def render(self) -> str:
        """Produces the complete breadboard SVG."""
        L: list[str] = []
        L.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
        L.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{self.vb_w}" height="{self.vb_h}" '
            f'viewBox="0 0 {self.vb_w} {self.vb_h}" version="1.1">'
        )
        L.append('  <g id="breadboard">')

        # Body
        L.append(
            f'    <rect id="breadboard-body" '
            f'x="{BODY_X}" y="{BODY_Y}" '
            f'width="{BODY_W}" height="{self.body_h}" '
            f'rx="{BODY_RY}" ry="{BODY_RY}" '
            f'style="fill:{BODY_FILL};stroke:{BODY_STROKE};stroke-width:1.5"/>'
        )

        # Channels (3): between left-rail and left-ts, central, between right-ts and right-rail
        L.append('    <g id="breadboard-channels">')
        channel_widths = (SILLON_RAIL, SILLON_CENTRAL, SILLON_RAIL)
        for i, (scx, w) in enumerate(zip(self._sillon_centers(), channel_widths)):
            sx = scx - w / 2
            L.append(
                f'      <rect id="breadboard-channel-{i+1}" '
                f'x="{sx}" y="{BODY_Y + 6}" '
                f'width="{w}" height="{self.body_h - 12}" '
                f'style="fill:{CHANNEL_FILL};stroke:none"/>'
            )
        L.append('    </g>')

        # Rail stripes (red V+ x2, blue GND x2)
        stripe_y = BODY_Y + 22
        stripe_h = self.body_h - 44
        v_plus_l_cx  = self.hole_position("V+_left",  1)[0]
        gnd_l_cx     = self.hole_position("GND_left", 1)[0]
        v_plus_r_cx  = self.hole_position("V+_right", 1)[0]
        gnd_r_cx     = self.hole_position("GND_right", 1)[0]
        red_left_x   = v_plus_l_cx - 9
        blue_left_x  = gnd_l_cx + 7
        red_right_x  = v_plus_r_cx - 9
        blue_right_x = gnd_r_cx + 7

        L.append('    <g id="breadboard-rail-stripes">')
        L.append(f'      <rect id="rail-Vplus-left"  x="{red_left_x}"   y="{stripe_y}" width="{STRIPE_W}" height="{stripe_h}" fill="{RAIL_RED}"/>')
        L.append(f'      <rect id="rail-GND-left"    x="{blue_left_x}"  y="{stripe_y}" width="{STRIPE_W}" height="{stripe_h}" fill="{RAIL_BLUE}"/>')
        L.append(f'      <rect id="rail-Vplus-right" x="{red_right_x}"  y="{stripe_y}" width="{STRIPE_W}" height="{stripe_h}" fill="{RAIL_RED}"/>')
        L.append(f'      <rect id="rail-GND-right"   x="{blue_right_x}" y="{stripe_y}" width="{STRIPE_W}" height="{stripe_h}" fill="{RAIL_BLUE}"/>')
        L.append('    </g>')

        # +/- labels (top/bottom of each stripe)
        top_label_y = BODY_Y + 14
        bot_label_y = BODY_Y + self.body_h - 7
        s_plus  = f'font-family:sans-serif;font-size:10px;font-weight:bold;fill:{RAIL_RED};text-anchor:middle'
        s_minus = f'font-family:sans-serif;font-size:11px;font-weight:bold;fill:{RAIL_BLUE};text-anchor:middle'
        L.append('    <g id="breadboard-rail-labels">')
        for x in [red_left_x + 1, red_right_x + 1]:
            L.append(f'      <text x="{x}" y="{top_label_y}" style="{s_plus}">+</text>')
            L.append(f'      <text x="{x}" y="{bot_label_y}" style="{s_plus}">+</text>')
        for x in [blue_left_x + 1, blue_right_x + 1]:
            L.append(f'      <text x="{x}" y="{top_label_y}" style="{s_minus}">−</text>')
            L.append(f'      <text x="{x}" y="{bot_label_y}" style="{s_minus}">−</text>')
        L.append('    </g>')

        # Letters a-j (top/bottom of the ts cols)
        s_letter = f'font-family:sans-serif;font-size:8px;fill:{LABEL_GRAY};text-anchor:middle'
        L.append('    <g id="breadboard-col-labels">')
        for letter in TIESTRIP_LETTERS:
            cx = self.hole_position(letter, 1)[0]
            L.append(f'      <text x="{cx}" y="{top_label_y}" style="{s_letter}">{letter}</text>')
            L.append(f'      <text x="{cx}" y="{bot_label_y}" style="{s_letter}">{letter}</text>')
        L.append('    </g>')

        # Row numbers (1, 5, 10, 15, ...) in the interior channels
        sillon_l_cx, _, sillon_r_cx = self._sillon_centers()
        s_num = f'font-family:sans-serif;font-size:8px;fill:{LABEL_GRAY};text-anchor:middle'
        L.append('    <g id="breadboard-row-labels">')
        for n in self._row_label_numbers():
            cy = self.hole_position("a", n)[1] + 3
            L.append(f'      <text x="{sillon_l_cx}" y="{cy}" style="{s_num}">{n}</text>')
            L.append(f'      <text x="{sillon_r_cx}" y="{cy}" style="{s_num}">{n}</text>')
        L.append('    </g>')

        # Holes
        L.append('    <g id="breadboard-holes">')
        for col_id in _COL_OFFSETS:
            for row in range(1, self.rows + 1):
                cx, cy = self.hole_position(col_id, row)
                L.append(f'      <circle cx="{cx}" cy="{cy}" r="{HOLE_R}" fill="{HOLE_FILL}"/>')
        L.append('    </g>')

        L.append('  </g>')
        L.append('</svg>')
        return "\n".join(L) + "\n"

    # ─── Internal helpers ─────────────────────────────────────────────
    def _sillon_centers(self) -> tuple[float, float, float]:
        """cx of the 3 channels: left (rail-ts), central (ts-ts), right (ts-rail)."""
        gnd_l_cx = self.hole_position("GND_left", 1)[0]
        a_cx     = self.hole_position("a",        1)[0]
        e_cx     = self.hole_position("e",        1)[0]
        f_cx     = self.hole_position("f",        1)[0]
        j_cx     = self.hole_position("j",        1)[0]
        v_plus_r = self.hole_position("V+_right", 1)[0]
        return (
            (gnd_l_cx + a_cx) / 2,
            (e_cx + f_cx) / 2,
            (j_cx + v_plus_r) / 2,
        )

    def _row_label_numbers(self) -> list[int]:
        """List of row numbers to label: 1 + multiples of 5."""
        return [1] + list(range(5, self.rows + 1, 5))
