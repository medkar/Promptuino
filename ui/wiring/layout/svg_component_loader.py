"""Component SVG loader: loads an asset (single-row or DIP), replaces the
placeholders (component name, pin labels) and exposes the anchor positions
(`pin-N-pos`) for wire routing.

SVG convention (see memo `project_wiring_svg_components_convention.md`):
- Root `<g id="component">`
- `id="component-body"`        : <rect> of the outline
- `id="component-name"`        : <text> with a single <tspan> = name placeholder
- `id="pin-N-pos"` (N=1,2,...) : <circle> electrical anchor
- `id="pin-N-label"`           : <text> with a single <tspan> = label placeholder

The loader also detects 2-sided components (DIP) by clustering the pin cx
values (2 unique values expected for DIP, 1 for single-row).

Usage:
    loader = ComponentSVGLoader(Path("assets/wiring/components/single-row/2pins.svg"))
    loader.set_name("LED")
    loader.set_pin_label(1, "A")
    loader.set_pin_label(2, "K")
    svg_fragment = loader.render(translate=(100, 50))   # SVG <g> placed at (100,50)
    pin_positions = loader.pin_positions(translate=(100, 50))
    # -> {1: (cx, cy), 2: (cx, cy), ...}  in canvas coords
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# SVG / Inkscape namespaces (required to parse the SVGs produced by
# Inkscape; the sodipodi/inkscape attributes are preserved along the way).
NS = {
    "svg":      "http://www.w3.org/2000/svg",
    "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
    "inkscape": "http://www.inkscape.org/namespaces/inkscape",
}
ET.register_namespace("",         NS["svg"])
ET.register_namespace("sodipodi", NS["sodipodi"])
ET.register_namespace("inkscape", NS["inkscape"])


# ─── Resistor color code ──────────────────────────────────────────────────
# Mapping value → 4 bands (digit1, digit2, multiplier, tolerance).
# Covers every value produced by `ui/wiring/inference.py` plus the common
# values the user can declare in markers.
# Unknowns fall back to 4 grey bands (see set_resistor_value).
_RESISTOR_BANDS: dict[str, tuple[str, str, str, str]] = {
    "100":  ("brown",  "black",  "brown",  "gold"),
    "220":  ("red",    "red",    "brown",  "gold"),
    "330":  ("orange", "orange", "brown",  "gold"),
    "470":  ("yellow", "violet", "brown",  "gold"),
    "1k":   ("brown",  "black",  "red",    "gold"),
    "2.2k": ("red",    "red",    "red",    "gold"),
    "4.7k": ("yellow", "violet", "red",    "gold"),
    "10k":  ("brown",  "black",  "orange", "gold"),
    "47k":  ("yellow", "violet", "orange", "gold"),
    "100k": ("brown",  "black",  "yellow", "gold"),
    "1m":   ("brown",  "black",  "green",  "gold"),
}

# Corresponding hex colors (saturated palette, legible at small size).
_BAND_COLOR_HEX: dict[str, str] = {
    "black":  "#1a1a1a",
    "brown":  "#6b3e1a",
    "red":    "#c52828",
    "orange": "#e07a16",
    "yellow": "#e6c12a",
    "green":  "#2c8c3a",
    "blue":   "#2c5fbb",
    "violet": "#7a3aaa",
    "grey":   "#7a7a7a",
    "white":  "#f0f0f0",
    "gold":   "#d4af37",
    "silver": "#c0c0c0",
}

# Color code for the digits (index = digit 0..9)
_DIGIT_COLORS: list[str] = [
    "black", "brown", "red", "orange", "yellow",
    "green", "blue", "violet", "grey", "white",
]

# Color code for the multiplier (power of 10 → color)
_MULT_COLORS: dict[int, str] = {
    -2: "silver", -1: "gold",
    0: "black", 1: "brown", 2: "red", 3: "orange", 4: "yellow",
    5: "green", 6: "blue", 7: "violet", 8: "grey", 9: "white",
}


def _value_to_bands_algorithmic(value: str) -> tuple[str, str, str, str] | None:
    """Compute the 4 bands of a resistor from its parseable ohmic value.
    Accepted suffixes: 'k'/'K' (kilo), 'm'/'M' (mega),
    'r'/'R' or 'Ω' (explicit ohm). Returns None if unparseable.

    Algorithm: 2 significant digits + multiplier (standard 4-band).
    Tolerance fixed to gold (5%) — pedagogical convention.

    Examples:
      '33'    → (orange, orange, black,  gold)
      '220'   → (red,    red,    brown,  gold)
      '1.5k'  → (brown,  green,  red,    gold)
      '4.7k'  → (yellow, violet, red,    gold)
      '470k'  → (yellow, violet, yellow, gold)
      '1m'    → (brown,  black,  green,  gold)
    """
    s = (value or "").strip().lower()
    # Strip trailing ohm symbols
    for suffix in ("ohms", "ohm", "ω"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
            break
    # Multiplier from suffix
    multiplier = 1.0
    if s.endswith("k"):
        multiplier = 1_000
        s = s[:-1].strip()
    elif s.endswith("m"):
        multiplier = 1_000_000
        s = s[:-1].strip()
    elif s.endswith("r"):
        s = s[:-1].strip()   # "220R" notation = 220 ohms
    try:
        ohms = float(s) * multiplier
    except ValueError:
        return None
    if ohms <= 0:
        return None

    # 2 significant digits + multiplier
    mult_exp = int(math.floor(math.log10(ohms))) - 1
    digits_2 = int(round(ohms / (10 ** mult_exp)))
    # Guard against float imprecision (e.g. 0.99 instead of 1.0)
    if digits_2 < 10:
        mult_exp -= 1
        digits_2 = int(round(ohms / (10 ** mult_exp)))
    elif digits_2 > 99:
        mult_exp += 1
        digits_2 = int(round(ohms / (10 ** mult_exp)))
    if not (10 <= digits_2 <= 99) or mult_exp not in _MULT_COLORS:
        return None
    d1, d2 = divmod(digits_2, 10)
    return (_DIGIT_COLORS[d1], _DIGIT_COLORS[d2], _MULT_COLORS[mult_exp], "gold")


@dataclass
class ComponentSVGLoader:
    """Loads and customizes a component SVG (single-row or DIP).

    The SVG file is read once at construction. The modifications
    (set_name, set_pin_label) are applied to the tree AND in memory,
    `render()` produces the final SVG fragment.

    `scale`: uniform scale factor applied to the render (`scale(s) ...`)
    AND to the returned pin_positions. Used to shrink an oversized SVG
    asset (e.g. NEMA17 originally 153x241 → scale 0.6).
    """

    svg_path: Path
    scale: float = 1.0

    def __post_init__(self):
        self._tree = ET.parse(self.svg_path)
        root = self._tree.getroot()
        component = root.find(".//svg:g[@id='component']", NS)
        if component is None:
            raise ValueError(
                f"<g id='component'> introuvable dans {self.svg_path} — "
                "le SVG ne respecte pas la convention composants."
            )
        self._component = component
        # Capture the `<defs>` located at the SVG root (gradients, patterns,
        # filters). The component geometry references them via
        # `fill="url(#id)"`. Without this capture, render() only extracts
        # `<g id='component'>` and the refs become invalid → the whole
        # component rendered white/transparent.
        self._defs_elements = list(root.findall("svg:defs", NS))
        # Read the anchor positions (cx, cy) once and for all.
        # RECURSIVE search (.//): some assets wrap their content in
        # a <g transform=...> to apply a global rotation, which
        # puts the pin-N-pos as indirect descendants of <g id="component">.
        # The cx/cy read stay in the final frame as long as the pin-pos
        # themselves carry a counter-rotation (= visual = (cx, cy) in
        # final canvas).
        self._pin_positions_local: dict[int, tuple[float, float]] = {}
        idx = 1
        while True:
            circle = self._component.find(
                f".//svg:circle[@id='pin-{idx}-pos']", NS)
            if circle is None:
                break
            cx = float(circle.get("cx", "0"))
            cy = float(circle.get("cy", "0"))
            self._pin_positions_local[idx] = (cx, cy)
            idx += 1

    # ─── Introspection ────────────────────────────────────────────────
    @property
    def pin_count(self) -> int:
        """Number of pins detected in the asset."""
        return len(self._pin_positions_local)

    @property
    def is_dip(self) -> bool:
        """True if the asset is a DIP (2 unique cx values), False if single-row."""
        cxs = {round(cx) for cx, _ in self._pin_positions_local.values()}
        return len(cxs) == 2

    def pin_positions(self,
                      translate: tuple[float, float] = (0.0, 0.0),
                      ) -> dict[int, tuple[float, float]]:
        """Returns the anchor positions in canvas coords (after translate).

        Args:
            translate: offset (tx, ty) applied to each anchor.
        Returns:
            {pin_index: (cx_canvas, cy_canvas)}
        """
        tx, ty = translate
        s = self.scale
        return {
            n: (cx * s + tx, cy * s + ty)
            for n, (cx, cy) in self._pin_positions_local.items()
        }

    # ─── Mutations ────────────────────────────────────────────────────
    def set_name(self, name: str) -> None:
        """Replaces the component name placeholder (e.g. 'Composant' -> 'LED')."""
        text = self._component.find("svg:text[@id='component-name']", NS)
        if text is None:
            return
        tspans = text.findall("svg:tspan", NS)
        if tspans:
            tspans[0].text = name
            # If the original asset has several tspans (multi-line), remove
            # the extras to keep only one line.
            for extra in tspans[1:]:
                text.remove(extra)

    def set_pin_label(self, pin_index: int, label: str) -> None:
        """Replaces the visible label of a pin (e.g. 'pin1' -> 'A')."""
        text = self._component.find(
            f"svg:text[@id='pin-{pin_index}-label']", NS
        )
        if text is None:
            return
        tspans = text.findall("svg:tspan", NS)
        if tspans:
            tspans[0].text = label
            for extra in tspans[1:]:
                text.remove(extra)

    def set_pin_labels(self, labels: dict[int, str]) -> None:
        """Helper: applies several labels at once."""
        for n, label in labels.items():
            self.set_pin_label(n, label)

    def set_voltage_label(self, text: str) -> None:
        """Replaces the content of <text id='component-voltage'> (asset
        battery_external). No-op if the asset does not have it."""
        text_elem = self._component.find(
            "svg:text[@id='component-voltage']", NS)
        if text_elem is None:
            return
        tspans = text_elem.findall("svg:tspan", NS)
        if tspans:
            tspans[0].text = text
            for extra in tspans[1:]:
                text_elem.remove(extra)
        else:
            text_elem.text = text

    def set_resistor_value(self, value: str) -> None:
        """Updates the fills of a resistor's 4 color bands
        (asset `horizontal/2pins.svg`) according to the value.

        Cascade strategy:
          1. table of known values `_RESISTOR_BANDS` (fast, override).
          2. algorithmic fallback `_value_to_bands_algorithmic` which parses
             the value and applies the standard color code.
          3. unparseable value → 4 grey bands (visually signals
             that we could not decode it).

        No-op if the asset does not have the band ids (case of the standard
        vertical resistor).
        """
        normalized = (value or "").strip().lower()
        bands = (
            _RESISTOR_BANDS.get(normalized)
            or _value_to_bands_algorithmic(value)
            or ("grey", "grey", "grey", "grey")
        )
        for band_id, color_name in zip(
            ("band-1", "band-2", "band-3", "band-tolerance"), bands,
        ):
            rect = self._component.find(f"svg:rect[@id='{band_id}']", NS)
            if rect is not None:
                rect.set("fill", _BAND_COLOR_HEX.get(color_name, "#888"))

    # ─── Render ───────────────────────────────────────────────────────
    def render(self,
               translate: tuple[float, float] = (0.0, 0.0),
               instance_id: str | None = None,
               mirror: bool = False,
               ) -> str:
        """Produces the SVG fragment of the component, placed via translate.

        Args:
            translate:   (tx, ty) offset of the component.
            instance_id: optional id for the <g> container.
            mirror:      if True, applies scale(-1, 1) to the component and
                         corrects the text positions so they stay legible
                         at the mirrored position.
        """
        if mirror:
            component_to_render = self._build_mirrored_component()
        else:
            component_to_render = self._component

        # Emit the `<defs>` first (gradients/patterns referenced by the
        # geometry via `url(#id)`), then the component. Without the defs, the
        # gradients do not resolve and the fills fall back to white.
        defs_xml = "".join(
            ET.tostring(d, encoding="unicode") for d in self._defs_elements
        )
        component_xml = ET.tostring(component_to_render, encoding="unicode")
        # Suffix the inner <rect>'s "component-body" id with the instance_id
        # so it is unique in the global scene. Lets callers query the bounds
        # of the visible body via QSvgRenderer.boundsOnElement (useful to
        # position interactive overlays precisely on the body, without
        # including pins / labels that would overflow the bbox of the
        # entire group).
        if instance_id:
            component_xml = component_xml.replace(
                'id="component-body"',
                f'id="component-body-{instance_id}"',
            )
        tx, ty = translate
        wrapper_id = f' id="{instance_id}"' if instance_id else ""
        # Mirror=True: the scale(-1, 1) is applied internally on the geometry
        # only (see _build_mirrored_component), so the outer wrapper carries
        # only a translate. The texts are kept in the non-scaled component
        # frame and undergo no chain of transforms.
        # If scale != 1.0, prepend the uniform scale in the transform
        # (applies after translate, which scales around the point (tx,ty)).
        if self.scale != 1.0:
            transform = f"translate({tx},{ty}) scale({self.scale})"
        else:
            transform = f"translate({tx},{ty})"
        return f'<g{wrapper_id} transform="{transform}">{defs_xml}{component_xml}</g>'

    def _build_mirrored_component(self) -> ET.Element:
        """Returns a mirrored copy of the component, with a split strategy:

        - **Geometry** (rect, circle, path, line, ellipse, polygon, polyline):
          moved into an inner-group `<g transform="scale(-1, 1)">`, which
          mirrors the shapes visually without touching their coordinates.
        - **Texts** (`<text>` and their `<tspan>`): kept at the component
          root, in a non-scaled frame. Their `x` attribute is negated
          (analytic mirror) and their `text-anchor` is flipped (start<->end,
          implicit start -> end). No chained transform on the texts,
          so direct legible rendering without depending on the SVG composition.

        This strategy eliminates the fragility of chained `transform`s on the
        texts (the implicit text-anchor bug for example).
        """
        import copy
        component = copy.deepcopy(self._component)

        # 1. Separate texts (stay at root) and geometry (goes into inner-group)
        geometry_children: list[ET.Element] = []
        text_children: list[ET.Element] = []
        text_tag = f"{{{NS['svg']}}}text"
        for child in list(component):
            component.remove(child)
            (text_children if child.tag == text_tag else geometry_children).append(child)

        # 2. Inner-group that mirrors the geometry
        inner = ET.SubElement(component, f"{{{NS['svg']}}}g")
        inner.set("id", "component-mirrored-geometry")
        inner.set("transform", "scale(-1, 1)")
        for geom in geometry_children:
            inner.append(geom)

        # 3. Texts: negate x + flip anchor, without chained transform
        for text_elem in text_children:
            self._mirror_x_attribute(text_elem)
            self._flip_text_anchor(text_elem)
            for tspan in text_elem.findall("svg:tspan", NS):
                self._mirror_x_attribute(tspan)
                # tspan inherits text-anchor from the parent <text>, no individual flip
            component.append(text_elem)

        return component

    @staticmethod
    def _mirror_x_attribute(elem: ET.Element) -> None:
        """Negates the `x` attribute of an element (if it exists)."""
        x_str = elem.get("x")
        if x_str is None:
            return
        try:
            elem.set("x", str(-float(x_str)))
        except ValueError:
            pass

    @staticmethod
    def _flip_text_anchor(elem: ET.Element) -> None:
        """Flips text-anchor start <-> end in the `style` or `text-anchor` attributes.

        If no text-anchor is specified (implicit SVG default = "start"),
        adds text-anchor="end" so the text grows toward the inside of the
        component after mirroring instead of overflowing to the right.
        """
        # Look in the `style` attribute (CSS-like)
        style = elem.get("style", "")
        has_in_style = "text-anchor" in style
        if has_in_style:
            for src, dst in (("text-anchor:start", "text-anchor:_END_TMP_"),
                             ("text-anchor:end", "text-anchor:start"),
                             ("text-anchor:_END_TMP_", "text-anchor:end")):
                style = style.replace(src, dst)
            elem.set("style", style)
        # Also look in the direct text-anchor attribute
        anchor = elem.get("text-anchor")
        has_in_attr = anchor is not None
        if anchor == "start":
            elem.set("text-anchor", "end")
        elif anchor == "end":
            elem.set("text-anchor", "start")
        # Implicit case: no text-anchor specified ⇒ SVG default = "start",
        # which must become "end" after mirroring.
        if not has_in_style and not has_in_attr:
            elem.set("text-anchor", "end")
