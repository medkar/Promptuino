"""Animated ASCII loader ("little robot") — replaces the circular spinner ◐
throughout the app (analysis/repair modals, "add comments" overlay, chat
typing indicator, loaders inside Studio buttons).

`RobotLoader` is a standalone QLabel that cycles text frames via a QTimer.
Minimal API: `start()` / `stop()`. Color and size are adjustable to match
the theme (callers pass `c.signal_ok`).

The `FRAMES` constant is also reused as-is by the loader painted INSIDE
Studio button text (`studio_view._paint_btn_spinner`).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QWidget

from .fonts import mono_font


class RobotLoader(QLabel):
    FRAMES = [
        ">", ">>", ">>>",
        "[>>]", "[--]",
        "[-_-]", "[o_o]", "[O_O]",
        "|[O_O]|", r"\[O_O]/",
        r"\[O_O]/", r"\[O_O]/",
    ]

    def __init__(self, parent: QWidget | None = None, *,
                 point_size: int = 12, color: str = "#00d9a0"):
        super().__init__(parent)
        self._point_size = point_size
        self._color = color
        self._apply_style()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._i = 0
        self._t = QTimer(self, interval=250, timeout=self._tick)

    # ── Style ────────────────────────────────────────────────────
    def _apply_style(self) -> None:
        # App's actual monospace font (JetBrains Mono / Cascadia / Consolas)
        # — required: all frames must have the same character width so the
        # robot does not "jiggle".
        self.setFont(mono_font(self._point_size))
        self.setStyleSheet(f"color: {self._color}; background: transparent;")
        # Reserved width = that of the widest frame (the robot is centered
        # inside it). This way any text placed to the right (e.g. "Thinking...")
        # does not shift between frames.
        widest = max(self.FRAMES, key=len)
        self.setFixedWidth(self.fontMetrics().horizontalAdvance(widest) + 4)

    def set_color(self, color: str) -> None:
        self._color = color
        self._apply_style()

    def set_point_size(self, point_size: int) -> None:
        self._point_size = point_size
        self._apply_style()

    # ── Animation ────────────────────────────────────────────────
    def start(self) -> None:
        self._i = 0
        self.setText(self.FRAMES[0])
        self.show()
        self._t.start()

    def stop(self) -> None:
        self._t.stop()
        self.hide()

    def _tick(self) -> None:
        self.setText(self.FRAMES[self._i % len(self.FRAMES)])
        self._i += 1


class LoaderLabel(QLabel):
    """Companion text for a loader (e.g. "Thinking...", "Analyzing...").
    Mono font (JetBrains Mono — same as the robot), loader color, and
    animated ellipsis: successive "..." dots in a loop.

    The width of the 3 dots is reserved (`ljust(3)` suffix + mono) -> the
    text does not shift during animation. `start()`/`stop()` drive the dots;
    `set_text()` changes the base label (trailing ellipsis is stripped — the
    animation provides it)."""

    def __init__(self, text: str = "", parent: QWidget | None = None, *,
                 point_size: int = 10, color: str = "#00d9a0",
                 bold: bool = True, interval: int = 400):
        super().__init__(parent)
        self._base = text.rstrip("…. ")
        self._color = color
        self._bold = bold
        self._point_size = point_size
        self._apply_style()
        self.setText(self._base)
        self._dots = 0
        self._t = QTimer(self, interval=interval, timeout=self._tick)

    def _apply_style(self) -> None:
        f = mono_font(self._point_size)
        f.setBold(self._bold)
        self.setFont(f)
        self.setStyleSheet(f"color: {self._color}; background: transparent;")

    def _render(self) -> None:
        if self._t.isActive():
            self.setText(self._base + ("." * self._dots).ljust(3))
        else:
            self.setText(self._base)

    def set_text(self, text: str) -> None:
        self._base = text.rstrip("…. ")
        self._render()

    def set_color(self, color: str) -> None:
        self._color = color
        self._apply_style()

    def start(self) -> None:
        self._dots = 0
        self.setText(self._base + " " * 3)   # reserves space for the 3 dots
        self._t.start()

    def stop(self) -> None:
        self._t.stop()
        self.setText(self._base)

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % 4
        self.setText(self._base + ("." * self._dots).ljust(3))
