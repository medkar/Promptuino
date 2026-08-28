"""
Segmented control dark/light — pill style with SVG icons.
Two segments: Sun (light) | Moon (dark).
The active item has a rounded colored background.
"""
from PyQt6.QtCore import Qt, QSize, QRectF, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QPainterPath
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton

from .theme import ColorScheme, theme_manager
from .i18n import lang_manager, Strings
from . import icons as IC

_ICON_SIZE = 16
_PAD       = 3    # inner padding (pill)
_SEG_W     = 28   # largeur d'un segment
_SEG_H     = 26   # hauteur d'un segment → pilule 62 × 32 (spec § 3)


class _SegmentBtn(QPushButton):
    def __init__(self, svg: str, tooltip: str, parent=None):
        super().__init__(parent)
        self._svg = svg
        self._normal_color = "#000000"
        self._hovered = False
        self._active = False
        self.setFixedSize(_SEG_W, _SEG_H)
        self.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setStyleSheet("background: transparent; border: none;")

    def set_active(self, active: bool, c: ColorScheme):
        self._active = active
        self._normal_color = c.btn_primary_text if active else c.topbar_btn_text
        self._refresh_icon()
        # The background (active pill) is painted in ThemeToggle; hover (GREEN
        # icon) is handled in enterEvent/leaveEvent — QSS cannot recolor a QIcon.
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def _refresh_icon(self) -> None:
        # Green on hover ONLY on the NON-active segment (not on the already
        # selected mode — user request).
        green = self._hovered and not self._active
        color = theme_manager.current.signal_ok if green else self._normal_color
        self.setIcon(IC.make_icon(self._svg, color, _ICON_SIZE))

    def enterEvent(self, e):
        self._hovered = True
        self._refresh_icon()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self._refresh_icon()
        super().leaveEvent(e)


class ThemeToggle(QWidget):
    """
    Segmented control: ☀ (light) | 🌙 (dark).
    Dark pill background, active item on animated accent background.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = theme_manager.is_dark   # True = sombre actif

        # Animated position of the selection background (0.0 = left, 1.0 = right)
        self._sel_pos: float = 1.0 if self._checked else 0.0

        self._anim = QPropertyAnimation(self, b"sel_pos", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.setFixedSize(_SEG_W * 2 + _PAD * 2, _SEG_H + _PAD * 2)   # 62 × 32 (spec § 3)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_PAD, _PAD, _PAD, _PAD)
        layout.setSpacing(0)

        s = lang_manager.current
        self._btn_sun  = _SegmentBtn(IC.SUN,  s.theme_light)
        self._btn_moon = _SegmentBtn(IC.MOON, s.theme_dark)
        # Any click flips the theme — including on the already-active segment
        # (user 2026-07-08). With two modes, "change the active mode" means go
        # to the other one, so both segments simply toggle.
        self._btn_sun.clicked.connect(lambda: self._toggle())
        self._btn_moon.clicked.connect(lambda: self._toggle())

        layout.addWidget(self._btn_sun)
        layout.addWidget(self._btn_moon)

        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self._apply_lang)

    def _apply_lang(self, s: Strings):
        self._btn_sun.setToolTip(s.theme_light)
        self._btn_moon.setToolTip(s.theme_dark)

    # ── Animated property ────────────────────────────────────

    @pyqtProperty(float)
    def sel_pos(self) -> float:
        return self._sel_pos

    @sel_pos.setter
    def sel_pos(self, value: float):
        self._sel_pos = value
        self.update()

    # ── Peinture ──────────────────────────────────────────────

    def paintEvent(self, event):
        c = theme_manager.current
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Pill container = surface (spec § 3)
        p.setBrush(QColor(c.surface))
        p.setPen(Qt.PenStyle.NoPen)
        radius = self.height() / 2
        p.drawRoundedRect(QRectF(self.rect()), radius, radius)

        # Selected item background = primary button (pill), slides L↔R
        slot_w = _SEG_W
        x = _PAD + self._sel_pos * slot_w
        sel_rect = QRectF(x, _PAD, _SEG_W, _SEG_H)
        p.setBrush(QColor(c.btn_primary_bg))
        p.drawRoundedRect(sel_rect, _SEG_H / 2, _SEG_H / 2)

        p.end()

    # ── Selection ─────────────────────────────────────────────

    def _toggle(self):
        if theme_manager.is_dark:
            theme_manager.apply_light()
        else:
            theme_manager.apply_dark()

    def apply_theme(self, c: ColorScheme):
        self._checked = theme_manager.is_dark
        target = 1.0 if self._checked else 0.0

        self._anim.stop()
        self._anim.setStartValue(self._sel_pos)
        self._anim.setEndValue(target)
        self._anim.start()

        self._btn_sun.set_active(not self._checked, c)
        self._btn_moon.set_active(self._checked, c)
        self.update()
