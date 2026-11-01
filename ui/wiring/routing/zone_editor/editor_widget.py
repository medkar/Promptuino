"""Main editor view: QGraphicsView with BB SVG as background +
grid overlay + interactive painted cells.

Responsibilities:
  - Loads the BB SVG and displays it transparently (opacity 0.5)
  - Draws the grid (thin lines) and the BB markers (rail/tie-strip
    separations + numbering every 5 cols)
  - Keeps the painted rects synchronized with the ZoneStore
  - Handles mouse interactions (click / drag-paint / wheel zoom)
  - Forwards the undo/redo/save actions to the store (or the window)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QWheelEvent,
)
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from .toolbar import TOOL_COLORS
from .zone_store import Cell, Color, ZoneStore, grid_origin_offset

# ─── BB geometric constants: single source = breadboard_generator ────
from ui.wiring.layout.breadboard_generator import (
    OUTER_MARGIN as BB_OUTER_MARGIN,
    INNER_MARGIN_X as BB_INNER_MARGIN_X,
    INNER_MARGIN_Y as BB_INNER_MARGIN_Y,
    PITCH as BB_PITCH,
    LEFT_RAIL_OFFSETS,
    LEFT_TS_OFFSETS,
    RIGHT_TS_OFFSETS,
    RIGHT_RAIL_OFFSETS,
)

# Z-values for the render order
Z_BG_BB = 0
Z_GRID = 1
Z_MARKERS = 2
Z_CELLS = 3
Z_CURSOR = 4


class ZoneEditorView(QGraphicsView):
    """Interactive view that draws and edits the zones."""

    cell_painted = pyqtSignal()      # a cell changed (to update stats)
    zoom_changed = pyqtSignal(float)  # current pct (100 = 1.0)

    def __init__(self, bb_svg_path: Path, store: ZoneStore):
        super().__init__()
        self.bb_svg_path = bb_svg_path
        self.store = store
        self.current_tool: str = "forbid"

        self._scene = QGraphicsScene()
        self.setScene(self._scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setMouseTracking(True)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setBackgroundBrush(QBrush(QColor("#181818")))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # ── Loads the BB SVG ────────────────────────────────────────────
        self._svg_item: Optional[QGraphicsSvgItem] = None
        self._bb_w: float = 466.0
        self._bb_h: float = 508.0
        self._load_bb_svg()

        # ── Overlay layers ────────────────────────────────────────────
        self._grid_items: list[QGraphicsItem] = []
        self._marker_items: list[QGraphicsItem] = []
        self._cell_items: dict[Cell, QGraphicsRectItem] = {}

        # Ghost cursor (1 cell)
        self._cursor_rect = QGraphicsRectItem()
        self._cursor_rect.setZValue(Z_CURSOR)
        self._cursor_rect.setPen(QPen(QColor("#ffffff"), 1.5))
        self._cursor_rect.setBrush(QBrush(Qt.GlobalColor.transparent))
        self._scene.addItem(self._cursor_rect)
        self._update_cursor_color()

        # Scene bbox (used for clip and fitInView)
        self._scene.setSceneRect(QRectF(0, 0, self._bb_w, self._bb_h))

        # Drag state
        self._drag_active = False
        self._last_cell: Optional[Cell] = None
        self._action_started = False

        self._build_grid()
        self._build_markers()
        self._refresh_all_cells_from_store()

        # Initial zoom: fit to the window
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # ─── BB loading ───────────────────────────────────────────────────
    def _load_bb_svg(self) -> None:
        if not self.bb_svg_path.exists():
            print(f"[zone-editor] BB SVG introuvable : {self.bb_svg_path}")
            return
        renderer = QSvgRenderer(str(self.bb_svg_path))
        size = renderer.defaultSize()
        self._bb_w = float(size.width())
        self._bb_h = float(size.height())
        self._svg_item = QGraphicsSvgItem(str(self.bb_svg_path))
        self._svg_item.setOpacity(0.5)
        self._svg_item.setZValue(Z_BG_BB)
        self._scene.addItem(self._svg_item)

    # ─── Grid / markers construction ───────────────────────────────────
    def _grid_origin(self) -> tuple[float, float]:
        """Offset (canvas px) of the top-left corner of cell (0, 0).

        Computed to align the BB holes with the center of the editor cells.
        See grid_origin_offset() in zone_store.
        """
        return grid_origin_offset(self.store.bb_anchor, self.store.cell_size)

    def _build_grid(self) -> None:
        for item in self._grid_items:
            self._scene.removeItem(item)
        self._grid_items.clear()

        cs = float(self.store.cell_size)
        ox, oy = self._grid_origin()
        pen = QPen(QColor(200, 200, 200, 50))
        pen.setWidth(0)  # cosmetic pen (zoom-invariant thickness)

        # Vertical lines (offset by ox)
        x = ox
        while x <= self._bb_w + 0.5:
            line = self._scene.addLine(x, 0, x, self._bb_h, pen)
            line.setZValue(Z_GRID)
            self._grid_items.append(line)
            x += cs
        # Horizontal lines (offset by oy)
        y = oy
        while y <= self._bb_h + 0.5:
            line = self._scene.addLine(0, y, self._bb_w, y, pen)
            line.setZValue(Z_GRID)
            self._grid_items.append(line)
            y += cs

    def _build_markers(self) -> None:
        """Draws the BB markers: rail/tie-strip separations + row numbering
        every 5 + letter labels a/e/f/j on the main cols."""
        for item in self._marker_items:
            self._scene.removeItem(item)
        self._marker_items.clear()

        body_x = BB_OUTER_MARGIN + BB_INNER_MARGIN_X
        body_y = BB_OUTER_MARGIN + BB_INNER_MARGIN_Y

        # Dark dashed pen
        pen = QPen(QColor(255, 120, 120, 140))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(0)

        # The grooves (channels) are already visible in the SVG, we don't
        # duplicate them. We rather mark the rail/tie-strip boundaries and the
        # marker columns.

        # Vertical lines at the tie-strip/rail boundaries
        # Absolute cols (canvas) for each hole center:
        col_x = [body_x + off for off in
                 LEFT_RAIL_OFFSETS + LEFT_TS_OFFSETS
                 + RIGHT_TS_OFFSETS + RIGHT_RAIL_OFFSETS]
        # We don't draw one line per col (too cluttered), only
        # the boundaries between groups. Indices:
        #   [0,1]   left rail (V+, GND)
        #   [2..6]  tie-strip left a..e
        #   [7..11] tie-strip right f..j
        #   [12,13] right rail (V+, GND)
        # Group boundary: between indices 1-2, 6-7, 11-12
        for boundary_idx in (1, 6, 11):
            x_mid = (col_x[boundary_idx] + col_x[boundary_idx + 1]) / 2.0
            line = self._scene.addLine(x_mid, 0, x_mid, self._bb_h, pen)
            line.setZValue(Z_MARKERS)
            self._marker_items.append(line)

        # Row numbering every 5 (the BB SVG already includes row
        # labels, but they are very small; we add more
        # visible markers on the left/right).
        font = QFont("Arial", 6)
        # Number of visible rows: depends on the SVG
        # We extrapolate from body_y and the available height
        max_row_y = self._bb_h - body_y
        row = 1
        while True:
            y = body_y + (row - 1) * BB_PITCH
            if y > max_row_y:
                break
            if row == 1 or row % 5 == 0:
                pen_h = QPen(QColor(120, 120, 255, 80))
                pen_h.setStyle(Qt.PenStyle.DotLine)
                pen_h.setWidth(0)
                hline = self._scene.addLine(0, y, self._bb_w, y, pen_h)
                hline.setZValue(Z_MARKERS)
                self._marker_items.append(hline)
                # Row label
                txt = QGraphicsSimpleTextItem(str(row))
                txt.setFont(font)
                txt.setBrush(QBrush(QColor("#9090ff")))
                txt.setPos(2, y - 5)
                txt.setZValue(Z_MARKERS)
                self._scene.addItem(txt)
                self._marker_items.append(txt)
            row += 1

        # Letters a..j above the body
        ts_labels = list("abcdefghij")
        ts_offsets = LEFT_TS_OFFSETS + RIGHT_TS_OFFSETS
        for letter, off in zip(ts_labels, ts_offsets):
            txt = QGraphicsSimpleTextItem(letter)
            txt.setFont(font)
            txt.setBrush(QBrush(QColor("#ff9090")))
            txt.setPos(body_x + off - 3, 2)
            txt.setZValue(Z_MARKERS)
            self._scene.addItem(txt)
            self._marker_items.append(txt)
        # Rail labels
        for label, off in zip(
            ("V+", "GND", "GND", "V+"),
            LEFT_RAIL_OFFSETS + RIGHT_RAIL_OFFSETS,
        ):
            txt = QGraphicsSimpleTextItem(label)
            txt.setFont(font)
            txt.setBrush(QBrush(QColor("#ffd060")))
            txt.setPos(body_x + off - 6, 14)
            txt.setZValue(Z_MARKERS)
            self._scene.addItem(txt)
            self._marker_items.append(txt)

    # ─── Sync cells <-> store ─────────────────────────────────────────
    def _refresh_all_cells_from_store(self) -> None:
        # Remove old ones
        for item in self._cell_items.values():
            self._scene.removeItem(item)
        self._cell_items.clear()
        for color, cells in self.store.cells.items():
            for cell in cells:
                self._add_cell_item(cell, color)

    def _add_cell_item(self, cell: Cell, color: Color) -> None:
        cs = float(self.store.cell_size)
        ox, oy = self._grid_origin()
        col, row = cell
        rect = QGraphicsRectItem(ox + col * cs, oy + row * cs, cs, cs)
        rect.setPen(QPen(Qt.GlobalColor.transparent))
        qc = QColor(TOOL_COLORS[color])
        qc.setAlpha(180)
        rect.setBrush(QBrush(qc))
        rect.setZValue(Z_CELLS)
        self._scene.addItem(rect)
        self._cell_items[cell] = rect

    def _remove_cell_item(self, cell: Cell) -> None:
        item = self._cell_items.pop(cell, None)
        if item is not None:
            self._scene.removeItem(item)

    def _update_cell_visual(self, cell: Cell) -> None:
        """Re-renders a cell according to its current state in the store."""
        new_color = self.store.color_at(cell)
        self._remove_cell_item(cell)
        if new_color is not None:
            self._add_cell_item(cell, new_color)

    # ─── Tool / cell size / cost setters ─────────────────────────────────
    def set_tool(self, tool: str) -> None:
        self.current_tool = tool
        self._update_cursor_color()

    def set_cell_size(self, size: int) -> None:
        if size == self.store.cell_size:
            return
        # We keep the cells in logical coordinates (col, row) — but
        # changing cell_size changes their canvas position. We re-render everything.
        self.store.cell_size = size
        self._build_grid()
        self._refresh_all_cells_from_store()

    # ─── Mouse interactions ─────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = True
            self._action_started = False
            self._last_cell = None
            self._paint_at_event_pos(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pt = self.mapToScene(event.position().toPoint())
        # Ghost cursor update
        cell = self._scene_to_cell(scene_pt)
        if cell is not None:
            cs = float(self.store.cell_size)
            ox, oy = self._grid_origin()
            self._cursor_rect.setRect(ox + cell[0] * cs, oy + cell[1] * cs, cs, cs)
            self._cursor_rect.setVisible(True)
        else:
            self._cursor_rect.setVisible(False)
        # Drag-paint
        if self._drag_active and (event.buttons() & Qt.MouseButton.LeftButton):
            self._paint_at_event_pos(event.position())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = False
            if self._action_started:
                self.store.end_action()
                self._action_started = False
            self._last_cell = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._cursor_rect.setVisible(False)
        super().leaveEvent(event)

    def _paint_at_event_pos(self, pos_f: QPointF) -> None:
        scene_pt = self.mapToScene(pos_f.toPoint())
        cell = self._scene_to_cell(scene_pt)
        if cell is None or cell == self._last_cell:
            return
        self._last_cell = cell
        if not self._action_started:
            self.store.begin_action()
            self._action_started = True
        color = None if self.current_tool == "erase" else self.current_tool
        if self.store.paint(cell, color):
            self._update_cell_visual(cell)
            self.cell_painted.emit()

    def _scene_to_cell(self, scene_pt: QPointF) -> Optional[Cell]:
        x, y = scene_pt.x(), scene_pt.y()
        if x < 0 or y < 0 or x >= self._bb_w or y >= self._bb_h:
            return None
        cs = float(self.store.cell_size)
        ox, oy = self._grid_origin()
        col = int((x - ox) // cs)
        row = int((y - oy) // cs)
        return (col, row)

    # ─── Zoom ────────────────────────────────────────────────────────────
    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        self.scale(factor, factor)
        self._emit_zoom()
        event.accept()

    def zoom_in(self) -> None:
        self.scale(1.15, 1.15)
        self._emit_zoom()

    def zoom_out(self) -> None:
        self.scale(1.0 / 1.15, 1.0 / 1.15)
        self._emit_zoom()

    def zoom_reset(self) -> None:
        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._emit_zoom()

    def _emit_zoom(self) -> None:
        # transform().m11() = current X scale factor
        pct = self.transform().m11() * 100.0
        self.zoom_changed.emit(pct)

    # ─── Undo/redo (delegation to the store + re-render of the affected cells) ─
    def undo(self) -> None:
        action = self.store.undo()
        if action is None:
            return
        for cell in action.changes.keys():
            self._update_cell_visual(cell)
        self.cell_painted.emit()

    def redo(self) -> None:
        action = self.store.redo()
        if action is None:
            return
        for cell in action.changes.keys():
            self._update_cell_visual(cell)
        self.cell_painted.emit()

    # ─── Cursor color ────────────────────────────────────────────────────
    def _update_cursor_color(self) -> None:
        if self.current_tool == "erase":
            color = QColor(255, 255, 255, 200)
        else:
            color = QColor(TOOL_COLORS[self.current_tool])
            color.setAlpha(220)
        self._cursor_rect.setPen(QPen(color, 1.8))
