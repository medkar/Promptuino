"""Renderer v2: composes the final SVG from a PlacedScene + Wires.

Z-order:
1. White background
2. Breadboard(s)
3. Board (Arduino)
4. Wires (Manhattan paths, rounded corners)
5. Hole highlights (connected holes colored by the wire)
6. Components (on top so pin circles stay visible)
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterable

from ..component_names import short_name
from .breadboard_connectivity import BreadboardConnectivity
from .breadboard_generator import TIESTRIP_LETTERS
from .layout import PlacedComponent, PlacedScene
from .routing import Wire
from .svg_component_loader import ComponentSVGLoader

NS = {"svg": "http://www.w3.org/2000/svg"}

CORNER_RADIUS = 4             # px: arc radius at Manhattan corners.
# At 4 px the radius fits within a 1-cell segment of the v3 grid
# (cell_size=8 -> min seg = 8 px). Guarantees that ALL corners have the
# same radius (visual consistency) and that no arc overflows its segment.
HIGHLIGHTED_HOLE_R = 4.5      # px: radius of colored BB holes (covers HOLE_R=3.5)
HIGHLIGHTED_BOARD_PIN_R = 5   # px: radius of Arduino terminals (covers pin r=3 + stroke)
HIGHLIGHTED_COMP_PIN_R = 5    # px: radius of component terminals (covers pin r=2 + stroke)


# ── SVG IDs exposed to the interactive consumer (SchemaView Level 1) ───────
# These constants/helpers are the source of truth: if the renderer changes
# an id, the consumer (ui/wiring/wiring_diagram_dialog.py) follows automatically.
BACKGROUND_ID = "background"
BOARD_INSTANCE_ID = "board-instance"
WIRES_GROUP_ID = "wires"
HIGHLIGHTS_GROUP_ID = "highlights"

def breadboard_instance_id(idx: int) -> str:
    return f"breadboard-{idx}-instance"

def component_id(idx: int, ref: str) -> str:
    return f"component-{idx}-{ref}"

def wire_id(idx: int) -> str:
    return f"wire-{idx}"

def highlight_wire_id(idx: int) -> str:
    """ID of the highlight-circle subgroup emitted by the wire at index
    `idx`. Lets the interactive UI dim the circles per-wire."""
    return f"highlight-wire-{idx}"


class SceneRenderer:
    def __init__(self, scene: PlacedScene, wires: list[Wire],
                 lang: str = "fr"):
        self.scene = scene
        self.wires = wires
        # Language of the names drawn inside the boxes. Keyword with a
        # default so the twelve existing call sites (ten smoke scripts, one
        # test, the pipeline) keep working untouched.
        self.lang = lang
        self._component_loaders: dict[str, ComponentSVGLoader] = {}
        # Inverted index canvas (cx,cy) -> (bb_idx, col_id, row) for highlight
        self._hole_index = self._build_hole_index()

    def render(self) -> str:
        canvas_w, canvas_h = self.scene.canvas_size

        L: list[str] = []
        L.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
        L.append(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
            'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            f'width="{canvas_w}" height="{canvas_h}" '
            f'viewBox="0 0 {canvas_w} {canvas_h}" version="1.1">'
        )
        L.append(f'  <rect id="{BACKGROUND_ID}" width="{canvas_w}" height="{canvas_h}" fill="#ffffff"/>')

        # 1. Breadboards
        for i, (bb, (tx, ty)) in enumerate(zip(
            self.scene.breadboards, self.scene.breadboard_translates,
        )):
            inner = self._extract_inner(bb.render(), "breadboard")
            L.append(f'  <g id="{breadboard_instance_id(i)}" transform="translate({tx},{ty})">{inner}</g>')

        # 2. Board
        L.append('  ' + self.scene.board_loader.render(
            translate=self.scene.board_translate, instance_id=BOARD_INSTANCE_ID,
        ))

        # 3. OFF-BB components BEFORE the wires: for drivers (ULN2003,
        #    L298N, ...) whose pins are INSIDE the body bbox, the
        #    wire starts at the canvas pin and crosses part of the body before
        #    exiting it. Rendering the off-BB first leaves the wire on top
        #    (= jumper laid on the PCB). The on-BB components are rendered
        #    AFTER the wires (step 5) to cleanly hide the wires
        #    that should not pass over them.
        for i, placed in enumerate(self.scene.placed_components):
            if placed.breadboard_idx >= 0:
                continue   # on-BB: rendered after the wires

            tx, ty = self._compute_component_translate(placed)
            loader = self._loader_for(placed)
            loader.set_name(short_name(placed.component_type, self.lang,
                                       fallback=placed.catalog_entry.name))
            loader.set_pin_labels(placed.catalog_entry.display_pin_labels)
            # For resistors: recolor the 4 bands according to the value
            # (asset horizontal/2pins.svg). No-op for vertical R's
            # (single-row asset without band ids).
            if placed.component_type == "resistor":
                loader.set_resistor_value(placed.attributes.get("value", ""))
            # For battery_external: replace the voltage label with the
            # range computed from the powered components.
            if placed.component_type == "battery_external":
                from .layout import compute_battery_voltage_range
                from .component_catalog import format_voltage_range
                rng = compute_battery_voltage_range(
                    self.scene.netlist_components, placed.component_ref)
                if rng is not None:
                    loader.set_voltage_label(format_voltage_range(*rng))
            L.append('  ' + loader.render(
                translate=(tx, ty),
                instance_id=component_id(i, placed.component_ref),
                mirror=placed.mirrored,
            ))

        # 4. Wires (rounded corners) - rendered BETWEEN off-BB and on-BB. The
        #    off-BB are below (wires visible even intra-body). The
        #    on-BB are rendered AFTER the wires (step 5), which lets them
        #    hide the wire segment that would pass over them (e.g.
        #    a wire running along a BB row where a component is placed).
        L.append(f'  <g id="{WIRES_GROUP_ID}">')
        for k, w in enumerate(self.wires):
            d = self._path_d_rounded(w.path, CORNER_RADIUS)
            L.append(
                f'    <path id="{wire_id(k)}" d="{d}" fill="none" stroke="{w.color}" '
                f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round" '
                f'data-net="{w.net}"/>'
            )
        L.append('  </g>')

        # 5. ON-BB components AFTER the wires: their body visually hides
        #    the wire if it ventures underneath (R1b normally blocks
        #    but the R4 arrival + stub can stay close to the body). By
        #    rendering on-BB on top, we get a clean visual as if the
        #    component were laid on the BB over the jumpers.
        for i, placed in enumerate(self.scene.placed_components):
            if placed.breadboard_idx < 0:
                continue   # off-BB: already rendered in step 3
            tx, ty = self._compute_component_translate(placed)
            loader = self._loader_for(placed)
            loader.set_name(short_name(placed.component_type, self.lang,
                                       fallback=placed.catalog_entry.name))
            loader.set_pin_labels(placed.catalog_entry.display_pin_labels)
            if placed.component_type == "resistor":
                loader.set_resistor_value(placed.attributes.get("value", ""))
            L.append('  ' + loader.render(
                translate=(tx, ty),
                instance_id=component_id(i, placed.component_ref),
                mirror=placed.mirrored,
            ))

        # 6. Highlights (on top of everything: board terminals, BB holes,
        #    component pins). Grouped by emitter wire so the
        #    interactive UI (Level 1) can dim per-wire the circles
        #    of a non-highlighted wire.
        L.append(f'  <g id="{HIGHLIGHTS_GROUP_ID}">')
        highlights_by_wire = self._compute_highlights_by_wire()
        for k in range(len(self.wires)):
            circles = highlights_by_wire.get(k, [])
            if not circles:
                continue
            L.append(f'    <g id="{highlight_wire_id(k)}">')
            for xy, color, radius in circles:
                L.append(f'      <circle cx="{xy[0]}" cy="{xy[1]}" r="{radius}" fill="{color}"/>')
            L.append('    </g>')
        L.append('  </g>')

        L.append('</svg>')
        return "\n".join(L) + "\n"

    # ─── Internal helpers ────────────────────────────────────────────
    def _loader_for(self, placed: PlacedComponent) -> ComponentSVGLoader:
        # Cache key: (path, scale). Two catalog entries can share
        # the same SVG asset with different scales — so we cache per
        # (path, scale) pair.
        scale = getattr(placed.catalog_entry, "render_scale", 1.0)
        cache_key = (str(placed.catalog_entry.asset_path), scale)
        if cache_key not in self._component_loaders:
            self._component_loaders[cache_key] = ComponentSVGLoader(
                placed.catalog_entry.asset_path, scale=scale
            )
        return self._component_loaders[cache_key]

    def _compute_component_translate(self, placed: PlacedComponent) -> tuple[float, float]:
        # Off-BB components (battery_external): direct canvas translate,
        # no pin_to_hole.
        if placed.breadboard_idx < 0:
            return placed.translate
        loader = self._loader_for(placed)
        pin1_local = loader.pin_positions()[1]
        col_id, row = placed.pin_to_hole[1]
        bb = self.scene.breadboards[placed.breadboard_idx]
        hole_local = bb.hole_position(col_id, row)
        bb_tx, bb_ty = self.scene.breadboard_translates[placed.breadboard_idx]
        # For mirrored components: scale(-1) flips pin-1 SVG cx -> -cx,
        # so tx must be adjusted: tx = target_cx + pin1_cx (instead of target - pin1)
        sign = 1 if placed.mirrored else -1
        return (
            hole_local[0] + bb_tx + sign * pin1_local[0],
            hole_local[1] + bb_ty - pin1_local[1],
        )

    def _extract_inner(self, svg_str: str, group_id: str) -> str:
        root = ET.fromstring(svg_str)
        g = root.find(f".//svg:g[@id='{group_id}']", NS)
        return ET.tostring(g, encoding="unicode") if g is not None else ""

    def _build_hole_index(self) -> dict[tuple[int, int], tuple[int, str, int]]:
        """Map rounded canvas (cx, cy) -> (bb_idx, col_id, row)."""
        index: dict[tuple[int, int], tuple[int, str, int]] = {}
        col_ids = ["V+_left", "GND_left", *TIESTRIP_LETTERS, "V+_right", "GND_right"]
        for bb_idx, (bb, (tx, ty)) in enumerate(zip(
            self.scene.breadboards, self.scene.breadboard_translates,
        )):
            for col_id in col_ids:
                for row in range(1, bb.rows + 1):
                    cx, cy = bb.hole_position(col_id, row)
                    key = (round(cx + tx), round(cy + ty))
                    index[key] = (bb_idx, col_id, row)
        return index

    def _hole_at_canvas(self, xy: tuple[float, float]
                        ) -> tuple[int, str, int] | None:
        """Finds the hole (bb_idx, col_id, row) at a canvas position."""
        return self._hole_index.get((round(xy[0]), round(xy[1])))

    def _compute_highlights_by_wire(
        self,
    ) -> dict[int, list[tuple[tuple[float, float], str, float]]]:
        """Returns {wire_idx: [(xy_canvas, color, radius), ...]}: the
        highlight circles grouped by emitter wire. Lets the
        interactive UI (Level 1) dim per-wire the circles of a
        non-highlighted wire.

        Deduplication by position: a circle is emitted by the FIRST
        wire that touches its position; subsequent wires landing at the
        same spot skip it (rare case of several wires sharing
        a hole — they are electrically equivalent so visually
        we get only a single circle).
        """
        by_wire: dict[int, list[tuple[tuple[float, float], str, float]]] = {}
        seen: set[tuple[int, int]] = set()

        for k, w in enumerate(self.wires):
            by_wire[k] = []

            def _add(xy: tuple[float, float], color: str,
                     radius: float, _k=k) -> None:
                key = (round(xy[0]), round(xy[1]))
                if key in seen:
                    return
                seen.add(key)
                by_wire[_k].append((xy, color, radius))

            for endpoint in (w.path[0], w.path[-1]):
                hole = self._hole_at_canvas(endpoint)
                if hole is not None:
                    # It's a breadboard hole
                    _add(endpoint, w.color, HIGHLIGHTED_HOLE_R)
                    # Color all component pins on the same tie-strip
                    bb_idx, col_id, row = hole
                    self._highlight_tiestrip_pins(
                        bb_idx, col_id, row, w.color, _add,
                    )
                else:
                    # Not a BB hole: it's probably an Arduino terminal
                    _add(endpoint, w.color, HIGHLIGHTED_BOARD_PIN_R)
        return by_wire

    def _highlight_tiestrip_pins(self,
                                  bb_idx: int,
                                  target_col: str,
                                  target_row: int,
                                  color: str,
                                  _add,
                                  visited_h_refs: set | None = None,
                                  ) -> None:
        """Colors all component pins on the tie-strip (target_col,
        target_row) with `color`. If a horizontal (paired) R is touched,
        propagates the color via its other pin to the opposite tie-strip — this
        is what allows coloring the electrically equivalent main pin
        (internal NET side between R and LED for example).

        `visited_h_refs` prevents infinite recursion: once we have
        propagated through a horizontal R, we no longer re-traverse that R
        if we land back on it from the other side.
        """
        if target_col not in ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j"):
            return
        if visited_h_refs is None:
            visited_h_refs = set()
        target_side = "left" if target_col in ("a", "b", "c", "d", "e") else "right"
        bb = self.scene.breadboards[bb_idx]
        tx, ty = self.scene.breadboard_translates[bb_idx]

        for placed in self.scene.placed_components:
            if placed.breadboard_idx != bb_idx:
                continue
            for pin_idx, (col_id, row) in placed.pin_to_hole.items():
                if row != target_row:
                    continue
                pin_side = "left" if col_id in ("a", "b", "c", "d", "e") else "right"
                if pin_side != target_side:
                    continue
                cx, cy = bb.hole_position(col_id, row)
                _add((cx + tx, cy + ty), color, HIGHLIGHTED_COMP_PIN_R)
                # Propagation via paired horizontal R, only when
                # `propagate_color_through` is True (= series R with
                # internal NET_* net). For pull-up R's (Btn/DHT) the 2 sides
                # are electrically distinct so no propagation.
                if (placed.propagate_color_through
                        and placed.component_ref not in visited_h_refs):
                    visited_h_refs.add(placed.component_ref)
                    other_pin_idx = 2 if pin_idx == 1 else 1
                    other_col, other_row = placed.pin_to_hole[other_pin_idx]
                    self._highlight_tiestrip_pins(
                        bb_idx, other_col, other_row, color, _add,
                        visited_h_refs=visited_h_refs,
                    )

    # ─── Manhattan path with rounded corners ─────────────────────────
    def _path_d_rounded(self, points: list[tuple[float, float]], radius: float) -> str:
        """Converts a list of Manhattan points into an SVG `d` with rounded corners."""
        if len(points) < 2:
            return ""
        if len(points) == 2:
            p0, p1 = points
            return f"M {p0[0]} {p0[1]} L {p1[0]} {p1[1]}"

        cmds: list[str] = [f"M {points[0][0]} {points[0][1]}"]
        for i in range(1, len(points) - 1):
            p_prev = points[i - 1]
            p_curr = points[i]
            p_next = points[i + 1]
            approach, exit_pt, sweep, r = self._round_corner(p_prev, p_curr, p_next, radius)
            cmds.append(f"L {approach[0]} {approach[1]}")
            # `r` is the radius clamped to min(radius, seg_in/2, seg_out/2).
            # We use it for the SVG arc too (not the fixed `radius`) otherwise
            # arcs on short segments are drawn incorrectly.
            cmds.append(f"A {r} {r} 0 0 {sweep} {exit_pt[0]} {exit_pt[1]}")
        cmds.append(f"L {points[-1][0]} {points[-1][1]}")
        return " ".join(cmds)

    def _round_corner(self,
                      p_prev: tuple[float, float],
                      p_curr: tuple[float, float],
                      p_next: tuple[float, float],
                      radius: float,
                      ) -> tuple[tuple[float, float], tuple[float, float], int]:
        """Computes the approach/exit points of a Manhattan corner, and the arc direction.

        Returns (approach_xy, exit_xy, sweep_flag).
        Limits the radius to half the shortest adjacent segment.
        """
        dx_in = p_curr[0] - p_prev[0]
        dy_in = p_curr[1] - p_prev[1]
        dx_out = p_next[0] - p_curr[0]
        dy_out = p_next[1] - p_curr[1]

        seg_in = abs(dx_in) + abs(dy_in)   # axis-aligned, so one of the two is 0
        seg_out = abs(dx_out) + abs(dy_out)
        r = min(radius, seg_in / 2, seg_out / 2)

        # Incoming unit direction (axis-aligned)
        if dx_in != 0:
            ux_in = 1 if dx_in > 0 else -1
            uy_in = 0
        else:
            ux_in = 0
            uy_in = 1 if dy_in > 0 else -1

        # Outgoing unit direction
        if dx_out != 0:
            ux_out = 1 if dx_out > 0 else -1
            uy_out = 0
        else:
            ux_out = 0
            uy_out = 1 if dy_out > 0 else -1

        approach = (p_curr[0] - ux_in * r, p_curr[1] - uy_in * r)
        exit_pt  = (p_curr[0] + ux_out * r, p_curr[1] + uy_out * r)

        # Sweep flag: cross product to determine clockwise/counter-clockwise direction
        # In SVG y-down: cross > 0 -> counter-clockwise (sweep=0), cross < 0 -> clockwise (sweep=1)
        cross = ux_in * uy_out - uy_in * ux_out
        sweep = 1 if cross > 0 else 0
        return approach, exit_pt, sweep, r
