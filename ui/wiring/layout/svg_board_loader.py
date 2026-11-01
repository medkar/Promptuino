"""SVG board loader (Arduino, ESP, STM board, etc.).

SVG convention (cf. memory `project_wiring_svg_boards_convention.md`):
- Root `<g id="board">`
- `id="board-body"`         : <rect> of the PCB
- `id="board-name"`         : <text> model name (fixed text)
- `id="pin-<FN>-pos"`       : <circle> electrical anchor of the FN function pin
                              (FN = D0, D7, A3, 5V, GND1, V3V3, AREF, SDA, SCL...)
- `id="pin-<FN>-label"`     : <text> visible label (fixed text, not a placeholder)

Diverges from components: the pins have known FUNCTIONS (no dynamic
replacement), and the index is not sequential.

Usage:
    loader = BoardSVGLoader(Path("assets/wiring/boards/arduino/uno_r3.svg"))
    pins = loader.pin_positions()                     # {FN: (cx, cy)}
    pos_d7 = loader.pin_position("D7")                # (cx, cy)
    svg_fragment = loader.render(translate=(50, 100)) # SVG <g> placed at (50,100)
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

NS = {
    "svg":      "http://www.w3.org/2000/svg",
    "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
    "inkscape": "http://www.inkscape.org/namespaces/inkscape",
}
ET.register_namespace("",         NS["svg"])
ET.register_namespace("sodipodi", NS["sodipodi"])
ET.register_namespace("inkscape", NS["inkscape"])

_PIN_ID_RE = re.compile(r"^pin-(.+)-pos$")


@dataclass
class BoardSVGLoader:
    """Loads a board SVG and exposes pin positions by function.

    The SVG file is read once, the positions are extracted at
    construction and kept in cache.
    """

    svg_path: Path

    def __post_init__(self):
        self._tree = ET.parse(self.svg_path)
        root = self._tree.getroot()
        board = root.find(".//svg:g[@id='board']", NS)
        if board is None:
            raise ValueError(
                f"<g id='board'> introuvable dans {self.svg_path} — "
                "le SVG ne respecte pas la convention boards."
            )
        self._board = board

        # ViewBox
        vb = root.get("viewBox", "0 0 100 100").split()
        self._viewbox = (float(vb[0]), float(vb[1]), float(vb[2]), float(vb[3]))

        # Read all the pin-<FN>-pos anchors
        self._pin_positions_local: dict[str, tuple[float, float]] = {}
        for circle in self._board.findall(".//svg:circle", NS):
            cid = circle.get("id", "")
            m = _PIN_ID_RE.match(cid)
            if not m:
                continue
            fn = m.group(1)
            cx = float(circle.get("cx", "0"))
            cy = float(circle.get("cy", "0"))
            self._pin_positions_local[fn] = (cx, cy)

        if not self._pin_positions_local:
            raise ValueError(
                f"Aucune ancre `pin-<FN>-pos` trouvee dans {self.svg_path}"
            )

        # Read the PCB body (rect#board-body) to get the real PCB bbox
        # (not the viewBox which includes margins/USB/jack protrusions)
        body = self._board.find(".//svg:rect[@id='board-body']", NS)
        if body is not None:
            bx = float(body.get("x", "0"))
            by = float(body.get("y", "0"))
            bw = float(body.get("width", str(self._viewbox[2])))
            bh = float(body.get("height", str(self._viewbox[3])))
            self._body_bbox_local = (bx, by, bw, bh)
        else:
            # Fallback: uses the viewBox
            self._body_bbox_local = (0.0, 0.0, self._viewbox[2], self._viewbox[3])

    # ─── Introspection ────────────────────────────────────────────────
    @property
    def viewbox(self) -> tuple[float, float, float, float]:
        """SVG ViewBox: (min_x, min_y, width, height)."""
        return self._viewbox

    @property
    def size(self) -> tuple[float, float]:
        """(width, height) of the board in SVG coords (= viewBox)."""
        return (self._viewbox[2], self._viewbox[3])

    def body_bbox(self,
                  translate: tuple[float, float] = (0.0, 0.0),
                  ) -> tuple[float, float, float, float]:
        """BBox of the PCB body (without the viewBox margin / USB/jack protrusions).

        Returns (x_min, y_min, x_max, y_max) in canvas coords (after translate).
        """
        bx, by, bw, bh = self._body_bbox_local
        tx, ty = translate
        return (bx + tx, by + ty, bx + bw + tx, by + bh + ty)

    @property
    def pin_count(self) -> int:
        return len(self._pin_positions_local)

    @property
    def pin_names(self) -> list[str]:
        """List of available pin functions (D0, D7, 5V, GND1, ...)."""
        return list(self._pin_positions_local.keys())

    def has_pin(self, fn: str) -> bool:
        return fn in self._pin_positions_local

    def pin_position(self,
                     fn: str,
                     translate: tuple[float, float] = (0.0, 0.0),
                     ) -> tuple[float, float]:
        """Canvas position (cx, cy) of a pin by function."""
        if fn not in self._pin_positions_local:
            raise KeyError(
                f"Pin '{fn}' inconnue dans {self.svg_path.name}. "
                f"Disponibles : {sorted(self._pin_positions_local)}"
            )
        cx, cy = self._pin_positions_local[fn]
        tx, ty = translate
        return (cx + tx, cy + ty)

    def pin_positions(self,
                      translate: tuple[float, float] = (0.0, 0.0),
                      ) -> dict[str, tuple[float, float]]:
        """All pin positions in canvas coords."""
        tx, ty = translate
        return {
            fn: (cx + tx, cy + ty)
            for fn, (cx, cy) in self._pin_positions_local.items()
        }

    # ─── Rendering ────────────────────────────────────────────────────────
    def render(self,
               translate: tuple[float, float] = (0.0, 0.0),
               instance_id: str | None = None,
               ) -> str:
        """Produces the SVG fragment of the board, placed via translate."""
        board_xml = ET.tostring(self._board, encoding="unicode")
        tx, ty = translate
        wrapper_id = f' id="{instance_id}"' if instance_id else ""
        return (
            f'<g{wrapper_id} transform="translate({tx},{ty})">'
            f'{board_xml}'
            f'</g>'
        )
