"""Zone editor sidebar: tools, cell_size, cost, zoom.

Emits signals that the editor_widget consumes:
  - tool_changed(str)        : "forbid" | "cost" | "allow" | "erase"
  - cell_size_changed(int)   : px per cell (recomputes the grid)
  - cost_value_changed(int)  : penalty value for the yellow cells
  - zoom_in / zoom_out / zoom_reset : pure signals (the editor handles the view)
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

TOOL_COLORS: dict[str, str] = {
    "forbid": "#d62728",   # red
    "cost":   "#f0c000",   # yellow
    "allow":  "#28a745",   # green
    "erase":  "#888888",   # gray (eraser)
}

TOOL_LABELS: dict[str, str] = {
    "forbid": "Rouge\n(forbid)",
    "cost":   "Jaune\n(cost)",
    "allow":  "Vert\n(allow)",
    "erase":  "Eff.",
}


class ToolButton(QPushButton):
    """Checkable button with a visible color dot."""

    def __init__(self, tool: str):
        super().__init__(TOOL_LABELS[tool])
        self.tool = tool
        self.setCheckable(True)
        self.setMinimumHeight(54)
        self._apply_style(TOOL_COLORS[tool])

    def _apply_style(self, color_hex: str) -> None:
        # The "active" button receives a colored border + a translucent
        # background to distinguish the tool color. QPushButton via stylesheet.
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: #2a2a2a;
                color: #e0e0e0;
                border: 2px solid #444;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                padding: 4px;
            }}
            QPushButton:checked {{
                background: {color_hex};
                color: #000;
                border: 2px solid #fff;
            }}
            QPushButton:hover:!checked {{
                background: #3a3a3a;
                border-color: {color_hex};
            }}
            """
        )


class ZoneToolbar(QWidget):
    tool_changed = pyqtSignal(str)
    cell_size_changed = pyqtSignal(int)
    cost_value_changed = pyqtSignal(int)
    zoom_in = pyqtSignal()
    zoom_out = pyqtSignal()
    zoom_reset = pyqtSignal()

    def __init__(self, cell_size: int = 8, cost_value: int = 60):
        super().__init__()
        self.setFixedWidth(110)
        self._apply_palette()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Tools ──────────────────────────────────────────────────────
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.buttons: dict[str, ToolButton] = {}
        for tool in ("forbid", "cost", "allow", "erase"):
            btn = ToolButton(tool)
            self.buttons[tool] = btn
            self.button_group.addButton(btn)
            btn.clicked.connect(lambda _checked, t=tool: self._on_tool(t))
            layout.addWidget(btn)
        # Default: forbid active
        self.buttons["forbid"].setChecked(True)

        layout.addSpacing(6)
        layout.addWidget(self._hline())

        # ── Cell size ───────────────────────────────────────────────────
        layout.addWidget(self._label("cell px"))
        self.cell_spin = QSpinBox()
        self.cell_spin.setRange(1, 64)
        self.cell_spin.setValue(cell_size)
        self.cell_spin.valueChanged.connect(self.cell_size_changed)
        layout.addWidget(self.cell_spin)

        # ── Cost value ──────────────────────────────────────────────────
        layout.addWidget(self._label("cost"))
        self.cost_spin = QSpinBox()
        self.cost_spin.setRange(1, 255)
        self.cost_spin.setValue(cost_value)
        self.cost_spin.valueChanged.connect(self.cost_value_changed)
        layout.addWidget(self.cost_spin)

        layout.addSpacing(6)
        layout.addWidget(self._hline())

        # ── Zoom ────────────────────────────────────────────────────────
        layout.addWidget(self._label("zoom"))
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(2)
        zoom_minus = QPushButton("-")
        zoom_minus.setFixedSize(28, 24)
        zoom_minus.clicked.connect(self.zoom_out)
        zoom_plus = QPushButton("+")
        zoom_plus.setFixedSize(28, 24)
        zoom_plus.clicked.connect(self.zoom_in)
        zoom_row.addWidget(zoom_minus)
        zoom_row.addWidget(zoom_plus)
        layout.addLayout(zoom_row)
        zoom_reset_btn = QPushButton("100%")
        zoom_reset_btn.setFixedHeight(22)
        zoom_reset_btn.clicked.connect(self.zoom_reset)
        layout.addWidget(zoom_reset_btn)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setStyleSheet("color: #aaa; font-size: 10px;")
        layout.addWidget(self.zoom_label)

        layout.addStretch(1)

        # ── Stats counter ──────────────────────────────────────────────
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #888; font-size: 9px;")
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)

    # ─── Public API ────────────────────────────────────────────────────
    def current_tool(self) -> str:
        for tool, btn in self.buttons.items():
            if btn.isChecked():
                return tool
        return "forbid"

    def set_zoom_pct(self, pct: float) -> None:
        self.zoom_label.setText(f"{int(round(pct))}%")

    def set_stats(self, forbid: int, cost: int, allow: int) -> None:
        self.stats_label.setText(
            f"forbid: {forbid}\ncost: {cost}\nallow: {allow}"
        )

    def set_cell_size(self, value: int) -> None:
        self.cell_spin.blockSignals(True)
        self.cell_spin.setValue(value)
        self.cell_spin.blockSignals(False)

    def set_cost_value(self, value: int) -> None:
        self.cost_spin.blockSignals(True)
        self.cost_spin.setValue(value)
        self.cost_spin.blockSignals(False)

    # ─── Helpers ─────────────────────────────────────────────────────────
    def _on_tool(self, tool: str) -> None:
        self.tool_changed.emit(tool)

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #aaa; font-size: 10px;")
        return lbl

    def _hline(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444;")
        return line

    def _apply_palette(self) -> None:
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0e0"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
