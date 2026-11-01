"""Welcome tutorial — coachmark overlay (spotlight + green arrow + bubble).

Carousel of steps: each step points a **green arrow** at a UI element
and shows a **white sentence** in a bubble, with "Next" / "Skip"
and a counter. The background is **dimmed** except for a halo (spotlight) around
the targeted element.

Generic: the steps (target + i18n key) are provided by MainWindow, which
knows the widgets. The overlay is a full-screen child of the central area
(`_center`), so it covers sidebar + topbar + studio + chat.
"""
from __future__ import annotations

import math
from typing import Callable, NamedTuple

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .i18n import lang_manager
from .theme import theme_manager, primary_button_qss, secondary_button_qss


class TutorialStep(NamedTuple):
    """A step: target widget getter + i18n key of the sentence + optional
    `on_enter` action played when the step becomes active (e.g. navigate to
    a tab to show it behind the spotlight)."""
    target: Callable[[], "QWidget | None"]
    text_attr: str
    on_enter: "Callable[[], None] | None" = None
    placement: "str | None" = None   # None = auto; "right_top" = right, top


_DIM_ALPHA = 150     # opacity of the dark veil (0-255)
_SPOT_PAD = 8        # spotlight padding around the widget
_SPOT_RADIUS = 8
_BUBBLE_W = 420      # assez large pour la rangée compteur + 3 boutons
                     # (« Précédent » / « Passer » / « Suivant » sans troncature)
_GAP = 28            # space bubble <-> spotlight (room for the arrow)
_MARGIN = 14         # min margin of the bubble to the window edge


def _visible(w) -> bool:
    return w is not None and w.isVisible() and w.width() > 0 and w.height() > 0


def _edge_point(rect: QRect, toward: QPoint) -> QPoint:
    """Point on the edge of `rect` closest to `toward`."""
    x = max(rect.left(), min(toward.x(), rect.right()))
    y = max(rect.top(), min(toward.y(), rect.bottom()))
    dl, dr = abs(x - rect.left()), abs(x - rect.right())
    dt, db = abs(y - rect.top()), abs(y - rect.bottom())
    m = min(dl, dr, dt, db)
    if m == dl:
        x = rect.left()
    elif m == dr:
        x = rect.right()
    elif m == dt:
        y = rect.top()
    else:
        y = rect.bottom()
    return QPoint(x, y)


class TutorialOverlay(QWidget):
    """Carousel overlay. `start(steps)` launches, `closed` is emitted at the end."""

    closed = pyqtSignal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._steps: list[TutorialStep] = []
        self._index = 0
        self._spot = QRect()

        # Bubble: opaque panel (white sentence + counter + buttons).
        self._bubble = QFrame(self)
        self._bubble.setObjectName("TutoBubble")
        bl = QVBoxLayout(self._bubble)
        bl.setContentsMargins(16, 14, 16, 12)
        bl.setSpacing(10)
        self._lbl = QLabel(self._bubble)
        self._lbl.setObjectName("TutoText")
        self._lbl.setWordWrap(True)
        # Fixed label width = the sizeHint reflects the WRAPPED text (otherwise
        # adjustSize() takes a 1-line height -> truncated sentence).
        self._lbl.setFixedWidth(_BUBBLE_W - 32)
        bl.addWidget(self._lbl)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._counter = QLabel(self._bubble)
        self._counter.setObjectName("TutoCounter")
        row.addWidget(self._counter)
        row.addStretch(1)
        self._btn_back = QPushButton(self._bubble)
        self._btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_back.setAutoDefault(False)
        self._btn_back.clicked.connect(self._back)
        row.addWidget(self._btn_back)
        self._btn_skip = QPushButton(self._bubble)
        self._btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_skip.setAutoDefault(False)
        self._btn_skip.clicked.connect(self._skip)
        row.addWidget(self._btn_skip)
        self._btn_next = QPushButton(self._bubble)
        self._btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_next.setAutoDefault(False)
        self._btn_next.clicked.connect(self._next)
        row.addWidget(self._btn_next)
        bl.addLayout(row)
        self._bubble.setFixedWidth(_BUBBLE_W)

        theme_manager.changed.connect(lambda _c: self._apply_style())
        lang_manager.changed.connect(lambda _s: self._refresh_texts())
        self._apply_style()
        self.hide()

    # ── Public API ─────────────────────────────────────────────
    def start(self, steps: list[TutorialStep]) -> None:
        """Starts the carousel on the steps whose target is visible.
        Shows nothing (and doesn't emit `closed`) if no target is visible."""
        self._steps = [s for s in steps if _visible(s.target())]
        if not self._steps:
            return
        self._index = 0
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._goto(0)

    def reposition(self) -> None:
        if not self.isVisible():
            return
        self.setGeometry(self.parentWidget().rect())
        self._layout_current()
        self.raise_()   # stay on top (e.g. chevrons re-raise on tab switch)
        self.update()

    # ── Navigation ─────────────────────────────────────────────
    def _next(self) -> None:
        if self._index + 1 >= len(self._steps):
            self._finish()
        else:
            self._goto(self._index + 1)

    def _back(self) -> None:
        if self._index > 0:
            self._goto(self._index - 1)

    def _skip(self) -> None:
        self._finish()

    def _finish(self) -> None:
        self.hide()
        self.closed.emit()

    def _goto(self, idx: int) -> None:
        self._index = idx
        step = self._steps[idx]
        if step.on_enter is not None:
            step.on_enter()
        self._refresh_texts()
        self._layout_current()
        self.update()
        # Let a possible tab change settle before re-measuring.
        QTimer.singleShot(0, self.reposition)

    # ── Layout of the current step ─────────────────────────────
    def _layout_current(self) -> None:
        if not self._steps:
            return
        step = self._steps[self._index]
        w = step.target()
        if not _visible(w):
            self._next()
            return
        top = self.parentWidget()
        tl = w.mapTo(top, QPoint(0, 0))
        spot = QRect(tl, w.size()).adjusted(-_SPOT_PAD, -_SPOT_PAD,
                                            _SPOT_PAD, _SPOT_PAD)
        self._spot = spot.intersected(self.rect())
        self._place_bubble()

    def _place_bubble(self) -> None:
        self._bubble.adjustSize()
        bw, bh = self._bubble.width(), self._bubble.height()
        area = self.rect()
        spot = self._spot

        def clamp(r: QRect) -> QRect:
            r.moveLeft(max(_MARGIN, min(r.left(), area.right() - bw - _MARGIN)))
            r.moveTop(max(_MARGIN, min(r.top(), area.bottom() - bh - _MARGIN)))
            return r

        placement = self._steps[self._index].placement if self._steps else None
        if placement == "right_top":
            # Frame to the RIGHT of the target, anchored at the TOP (tabs tour).
            r = clamp(QRect(QPoint(spot.right() + _GAP, _MARGIN),
                            self._bubble.size()))
            self._bubble.move(r.topLeft())
            self._bubble.raise_()
            return

        cands = [
            QPoint(spot.center().x() - bw // 2, spot.bottom() + _GAP),    # below
            QPoint(spot.center().x() - bw // 2, spot.top() - _GAP - bh),  # above
            QPoint(spot.right() + _GAP, spot.center().y() - bh // 2),     # right
            QPoint(spot.left() - _GAP - bw, spot.center().y() - bh // 2),  # left
        ]
        chosen = None
        for p in cands:
            r = QRect(p, self._bubble.size())
            r.moveLeft(max(_MARGIN, min(r.left(), area.right() - bw - _MARGIN)))
            r.moveTop(max(_MARGIN, min(r.top(), area.bottom() - bh - _MARGIN)))
            if not r.intersects(spot.adjusted(-6, -6, 6, 6)):
                chosen = r
                break
        if chosen is None:
            r = QRect(cands[0], self._bubble.size())
            r.moveLeft(max(_MARGIN, min(r.left(), area.right() - bw - _MARGIN)))
            r.moveTop(max(_MARGIN, min(r.top(), area.bottom() - bh - _MARGIN)))
            chosen = r
        self._bubble.move(chosen.topLeft())
        self._bubble.raise_()

    # ── Texts / style ──────────────────────────────────────────
    def _refresh_texts(self) -> None:
        if not self._steps:
            return
        s = lang_manager.current
        step = self._steps[self._index]
        self._lbl.setText(getattr(s, step.text_attr, step.text_attr))
        self._counter.setText(f"{self._index + 1}/{len(self._steps)}")
        last = self._index + 1 >= len(self._steps)
        self._btn_next.setText(
            getattr(s, "tutorial_finish" if last else "tutorial_next", "OK"))
        self._btn_skip.setText(getattr(s, "tutorial_skip", "Passer"))
        self._btn_skip.setVisible(not last)
        self._btn_back.setText(getattr(s, "tutorial_back", "Précédent"))
        self._btn_back.setVisible(self._index > 0)
        self._bubble.adjustSize()

    def _apply_style(self) -> None:
        c = theme_manager.current
        self._bubble.setStyleSheet(
            f"#TutoBubble {{ background:{c.surface}; "
            f"border:1px solid {c.signal_ok}; border-radius:10px; }}"
            f"#TutoText {{ color:#ffffff; font-size:11pt; background:transparent; }}"
            f"#TutoCounter {{ color:{c.text_secondary}; font-size:9pt; "
            f"background:transparent; }}"
        )
        self._btn_next.setStyleSheet(primary_button_qss(c))
        self._btn_skip.setStyleSheet(secondary_button_qss(c))
        self._btn_back.setStyleSheet(secondary_button_qss(c))

    # ── Painting: veil (by subtraction) + outline + arrow ──────
    def paintEvent(self, _e) -> None:
        if not self._steps:
            return
        c = theme_manager.current
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        spot = self._spot
        # Veil everywhere EXCEPT the spotlight: we never paint the hole -> it
        # stays transparent and lets the widget below show through (proven
        # pattern, cf _ChevronOverlay, without CompositionMode).
        dim = QPainterPath()
        dim.addRect(QRectF(self.rect()))
        if spot.isValid() and not spot.isEmpty():
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(spot), _SPOT_RADIUS, _SPOT_RADIUS)
            dim = dim.subtracted(hole)
        p.fillPath(dim, QColor(0, 0, 0, _DIM_ALPHA))

        if spot.isValid() and not spot.isEmpty():
            pen = QPen(QColor(c.signal_ok))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(spot), _SPOT_RADIUS, _SPOT_RADIUS)
            self._draw_arrow(p, QColor(c.signal_ok))
        p.end()

    @staticmethod
    def _spot_edge_midpoint(spot: QRect, bub: QRect) -> QPoint:
        """Milieu du CÔTÉ du spotlight qui fait face à la bulle : mi-largeur pour
        un bord haut/bas, mi-hauteur pour un bord gauche/droit."""
        sc = spot.center()
        if bub.top() >= spot.bottom():          # bulle en dessous
            return QPoint(sc.x(), spot.bottom())
        if bub.bottom() <= spot.top():          # bulle au-dessus
            return QPoint(sc.x(), spot.top())
        if bub.left() >= spot.right():          # bulle à droite
            return QPoint(spot.right(), sc.y())
        if bub.right() <= spot.left():          # bulle à gauche
            return QPoint(spot.left(), sc.y())
        # Chevauchement / ambigu : axe dominant du décalage des centres.
        bc = bub.center()
        dx, dy = bc.x() - sc.x(), bc.y() - sc.y()
        if abs(dx) >= abs(dy):
            return QPoint(spot.right() if dx >= 0 else spot.left(), sc.y())
        return QPoint(sc.x(), spot.bottom() if dy >= 0 else spot.top())

    def _draw_arrow(self, p: QPainter, color: QColor) -> None:
        spot = self._spot
        bub = self._bubble.geometry()
        # Pointe = MILIEU du côté du spotlight face à la bulle (mi-hauteur ou
        # mi-largeur du bord du composant), pas le point le plus proche.
        end = self._spot_edge_midpoint(spot, bub)
        # Départ = point du bord de la bulle le plus proche de cette pointe.
        start = _edge_point(bub, end)
        pen = QPen(color)
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(start, end)
        # Arrowhead at the tip (spotlight side).
        s, e = QPointF(start), QPointF(end)
        ang = math.atan2(e.y() - s.y(), e.x() - s.x())
        size = 11.0
        p1 = QPointF(e.x() + size * math.cos(ang + math.radians(150)),
                     e.y() + size * math.sin(ang + math.radians(150)))
        p2 = QPointF(e.x() + size * math.cos(ang - math.radians(150)),
                     e.y() + size * math.sin(ang - math.radians(150)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF([e, p1, p2]))
