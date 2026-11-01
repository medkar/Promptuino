"""FeatureTransferDialog — bidirectional feature transfer popup (IA <-> stable).

View over a TransferStaging (spec 2026-07-06): two columns of cards (IA left,
stable right), inline trash per card (delayed deletion, restorable), live
recap line, "Transfer all" shortcut, Apply -> recap confirmation -> the
studio reads `result()`. Nothing touches the studio before Apply.

This module covers Task 4 of the plan (columns/cards/trash/recap, transfers
driven by `_do_transfer`). Drag & drop (Task 5) and drawn dependency links
(Task 6) plug into the same rebuild pipeline.
"""
from __future__ import annotations

import re

from PyQt6.QtCore import QEvent, QMimeData, QPoint, QRect, Qt
from PyQt6.QtGui import (
    QColor, QDrag, QFont, QPainter, QPainterPath, QPen, QPixmap, QRegion,
)
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from .feature_transfer import TransferStaging
from .feature_dropdown import _dot_icon, _InstantTip
from .fonts import mono_caps_font
from .generation.feature_links import providers
from .generation.gen_prompts import feature_combo_label, feature_combo_tooltip
from .generation.feature_model import MANUAL_ID
from .theme import (
    ColorScheme, theme_manager, feature_color, install_icon_hover,
    primary_button_qss, secondary_button_qss,
)
from .i18n import lang_manager, Strings
from . import icons as IC

_DOT = 10
_LABEL_MAX = 40
# Drag payload: "<fid>|<side>" under this custom mime type.
_MIME = "application/x-promptuino-feature"
# Horizontal bulge of the dependency Bezier links. Each column reserves a
# gutter of this width on its OUTER side (left for IA, right for stable) so the
# links — hooked on the outer card edges — bulge INSIDE the boxed card area.
_LINK_BULGE = 14
_HOST_SIDE_MARGIN = _LINK_BULGE + 4
# The boxed card container scrolls past this height (spec 2026-07-08).
_BOX_MAX_H = 280


class _LinksOverlay(QWidget):
    """Transparent layer spanning the columns host: draws a Bezier link for
    every intra-column dependency edge (provider -> consumer). Mouse events
    pass through; the "why" of a link lives in the card tooltips."""

    def __init__(self, host: QWidget, dialog: "FeatureTransferDialog"):
        super().__init__(host)
        self._dialog = dialog
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        host.installEventFilter(self)
        self.setGeometry(host.rect())

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Resize:
            self.setGeometry(obj.rect())
        return False

    def edge_pairs(self) -> list[tuple[str, str, str]]:
        """(side, provider_fid, consumer_fid) for every edge whose two cards
        are displayed in the same column."""
        pairs = []
        for side in ("ia", "stable"):
            present = {c.fid for c in self._dialog._cards[side]}
            deps = self._dialog.staging.deps(side)
            for consumer in sorted(deps):
                for provider in sorted(deps[consumer]):
                    if consumer in present and provider in present:
                        pairs.append((side, provider, consumer))
        return pairs

    def link_points(self, side: str, a, b) -> tuple[float, float, float,
                                                    float, float]:
        """(x1, y1, ctrl_x, x2, y2) of the Bezier for cards a (provider) and
        b (consumer), in host coordinates. Card positions are mapped to the
        host with `mapTo` so the math survives the cards living inside a
        scrolled box (spec 2026-07-08); the bulge hooks on the OUTER card edge
        and arcs into the column's reserved gutter, staying inside the box."""
        host = self.parentWidget()
        ya = a.mapTo(host, QPoint(0, a.height() // 2)).y()
        yb = b.mapTo(host, QPoint(0, b.height() // 2)).y()
        if side == "ia":
            x1 = a.mapTo(host, QPoint(0, 0)).x()
            x2 = b.mapTo(host, QPoint(0, 0)).x()
            ctrl = min(x1, x2) - _LINK_BULGE
        else:
            x1 = a.mapTo(host, QPoint(a.width(), 0)).x()
            x2 = b.mapTo(host, QPoint(b.width(), 0)).x()
            ctrl = max(x1, x2) + _LINK_BULGE
        return float(x1), float(ya), float(ctrl), float(x2), float(yb)

    def _clip_region(self) -> QRegion:
        """Union of the two card boxes (host coords) so a link whose card is
        scrolled out of its box does not bleed over the titles/buttons."""
        host = self.parentWidget()
        region = QRegion()
        for box in self._dialog._boxes.values():
            tl = box.mapTo(host, QPoint(0, 0))
            region += QRegion(QRect(tl, box.size()))
        return region

    def paintEvent(self, ev):
        pairs = self.edge_pairs()
        if not pairs:
            return
        c = theme_manager.current
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setClipRegion(self._clip_region())
        pen = QPen(QColor(c.text_secondary))
        pen.setWidthF(1.5)
        p.setPen(pen)
        cards = {(side, card.fid): card
                 for side in ("ia", "stable")
                 for card in self._dialog._cards[side]}
        for side, provider, consumer in pairs:
            a = cards.get((side, provider))
            b = cards.get((side, consumer))
            if a is None or b is None:
                continue
            x1, y1, ctrl, x2, y2 = self.link_points(side, a, b)
            path = QPainterPath()
            path.moveTo(x1, y1)
            path.cubicTo(ctrl, y1, ctrl, y2, x2, y2)
            p.drawPath(path)
        p.end()


class _ColumnWidget(QWidget):
    """One feature column (header + cards + stretch). Drop target: computes
    the insertion index from the cursor y and delegates to the dialog."""

    def __init__(self, side: str, dialog: "FeatureTransferDialog"):
        super().__init__(dialog)
        self.side = side
        self._dialog = dialog
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        # Reserve a gutter on the OUTER side (left for IA, right for stable) so
        # the dependency links bulge inside the boxed area, not over the border.
        gutter = _LINK_BULGE + 2
        if side == "ia":
            lay.setContentsMargins(gutter, 6, 4, 6)
        else:
            lay.setContentsMargins(4, 6, gutter, 6)
        lay.setSpacing(4)
        lay.addStretch(1)
        self.lay = lay

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(_MIME):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if not ev.mimeData().hasFormat(_MIME):
            return
        ev.acceptProposedAction()
        idx = self._dialog._drop_index_for(self.side, int(ev.position().y()))
        self._dialog._show_drop_indicator(self.side, idx)

    def dragLeaveEvent(self, ev):
        self._dialog._hide_drop_indicator()

    def dropEvent(self, ev):
        if not ev.mimeData().hasFormat(_MIME):
            return
        fid, from_side = bytes(ev.mimeData().data(_MIME)).decode().split("|")
        idx = self._dialog._drop_index_for(self.side, int(ev.position().y()))
        self._dialog._hide_drop_indicator()
        self._dialog._handle_drop(fid, from_side, self.side, idx)
        ev.acceptProposedAction()


class _FeatureCard(QFrame):
    """One feature row: drag handle + color dot + elided label + trash."""

    def __init__(self, fid: str, side: str, label: str, color: str,
                 tooltip: str, deleted: bool, dialog: "FeatureTransferDialog"):
        super().__init__(dialog)
        self.fid = fid
        self.side = side
        self.color = color
        self.deleted = deleted
        self._dialog = dialog
        self.setObjectName("featureCard")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 6, 4)
        lay.setSpacing(6)
        self._handle = QLabel("⠇", self)     # braille dots drag handle
        self._handle.setCursor(Qt.CursorShape.OpenHandCursor)
        lay.addWidget(self._handle)
        dot = QLabel(self)
        dot.setPixmap(_dot_icon(color).pixmap(_DOT, _DOT))
        lay.addWidget(dot)
        self._lbl = QLabel(label, self)
        if deleted:
            f = QFont(self._lbl.font())
            f.setStrikeOut(True)
            self._lbl.setFont(f)
        lay.addWidget(self._lbl, stretch=1)
        self._btn_trash = QPushButton(self)
        self._btn_trash.setFixedSize(24, 22)
        self._btn_trash.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_trash.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_trash.setAutoDefault(False)
        self._btn_trash.setProperty("variant", "bare")
        s = lang_manager.current
        self._btn_trash.setToolTip(
            s.feature_transfer_restore if deleted else s.feature_action_delete)
        self._btn_trash._icon_hover = install_icon_hover(
            self._btn_trash, IC.REFRESH if deleted else IC.TRASH, 14)
        self._btn_trash.clicked.connect(
            lambda _=False: dialog._toggle_delete(self.fid, self.side))
        self._btn_trash.installEventFilter(dialog._tip)
        lay.addWidget(self._btn_trash)
        self.setToolTip(tooltip)
        self._press_pos = None

    # ── Drag source ────────────────────────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and not self.deleted:
            self._press_pos = ev.position().toPoint()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if (self._press_pos is None
                or not (ev.buttons() & Qt.MouseButton.LeftButton)):
            return
        dist = (ev.position().toPoint() - self._press_pos).manhattanLength()
        if dist < QApplication.startDragDistance():
            return
        self._press_pos = None
        self._dialog._start_drag(self)

    def mouseReleaseEvent(self, ev):
        self._press_pos = None
        super().mouseReleaseEvent(ev)


class FeatureTransferDialog(QDialog):
    def __init__(self, features_ia, features_stable, *,
                 dirty_ia: bool = False, dirty_stable: bool = False,
                 parent=None):
        super().__init__(parent)
        self.staging = TransferStaging(features_ia, features_stable)
        self._dirty = {"ia": dirty_ia, "stable": dirty_stable}
        self._tip = _InstantTip(self)
        self._cards: dict[str, list[_FeatureCard]] = {"ia": [], "stable": []}
        self.setMinimumSize(680, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # Two columns side by side inside a shared host (the links overlay
        # spans this host). Each column: a main-window-styled title, a boxed
        # scroll area owning the drop-target `_ColumnWidget` (its cards), then a
        # centered « transfer all » button. The `_ColumnWidget` stays the DROP
        # target and owns its cards (y coords drive the drop index).
        self._columns_host = QWidget(self)
        cols = QHBoxLayout(self._columns_host)
        cols.setContentsMargins(_HOST_SIDE_MARGIN, 0, _HOST_SIDE_MARGIN, 0)
        cols.setSpacing(24)
        self._columns: dict[str, _ColumnWidget] = {}
        self._col_headers: dict[str, QLabel] = {}
        self._col_lays: dict[str, QVBoxLayout] = {}
        self._boxes: dict[str, QFrame] = {}
        self._scrolls: dict[str, QScrollArea] = {}
        self._transfer_btns: dict[str, QPushButton] = {}
        for side in ("ia", "stable"):
            container = QVBoxLayout()
            container.setContentsMargins(0, 0, 0, 0)
            container.setSpacing(6)

            header = QLabel(self)
            self._col_headers[side] = header
            container.addWidget(header)

            colw = _ColumnWidget(side, self)
            self._columns[side] = colw
            self._col_lays[side] = colw.lay
            box = QFrame(self)
            box.setObjectName("featureBox")
            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(1, 1, 1, 1)
            box_lay.setSpacing(0)
            scroll = QScrollArea(box)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(colw)
            box_lay.addWidget(scroll)
            box.setMaximumHeight(_BOX_MAX_H)
            self._boxes[side] = box
            self._scrolls[side] = scroll
            container.addWidget(box, stretch=1)

            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            btn = QPushButton(self)
            btn.setAutoDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # stable→IA transfers back; IA→stable is the default direction.
            src, dst = ("stable", "ia") if side == "stable" else ("ia", "stable")
            btn.clicked.connect(lambda *_a, s=src, d=dst: self._transfer_all(s, d))
            self._transfer_btns[side] = btn
            btn_row.addWidget(btn)
            btn_row.addStretch(1)
            container.addLayout(btn_row)

            cols.addLayout(container, stretch=1)
        root.addWidget(self._columns_host, stretch=1)

        # Insertion indicator (thin line), reparented to the hovered column.
        self._drop_indicator = QFrame(self)
        self._drop_indicator.setObjectName("dropIndicator")
        self._drop_indicator.setFixedHeight(2)
        self._drop_indicator.hide()

        # Dependency links drawn over the columns (clipped to the boxes).
        self._links_overlay = _LinksOverlay(self._columns_host, self)

        self._lbl_recap = QLabel("", self)
        root.addWidget(self._lbl_recap)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self._btn_cancel = QPushButton(self)
        self._btn_cancel.setAutoDefault(False)
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self._btn_cancel)
        self._btn_apply = QPushButton(self)
        self._btn_apply.setAutoDefault(False)
        self._btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_apply.clicked.connect(self._on_apply)
        btns.addWidget(self._btn_apply)
        root.addLayout(btns)

        self.apply_lang(lang_manager.current)
        self.apply_theme(theme_manager.current)
        self._rebuild_columns()

    @staticmethod
    def _feat_label(f, s) -> str:
        """Card label: the i18n « Manual edits » for the manual bucket (it has
        no prompt/summary, so feature_combo_label would fall back to the raw id
        « manual »), else the usual feature combo label."""
        if f.id == MANUAL_ID:
            return s.studio_manual_feature_label
        return feature_combo_label(f, max_len=_LABEL_MAX)

    # ── Columns ────────────────────────────────────────────────
    def _rebuild_columns(self):
        """Recreate every card from the staging (single source of truth)."""
        s = lang_manager.current
        for side in ("ia", "stable"):
            lay = self._col_lays[side]
            for card in self._cards[side]:
                lay.removeWidget(card)
                card.setParent(None)
                card.deleteLater()
            self._cards[side] = []
            feats = self.staging.features(side)
            deps = self.staging.deps(side)
            labels = {f.id: self._feat_label(f, s) for f in feats}
            by_id = {f.id: f for f in feats}
            for f in feats:
                # ID-derived color: reordering must never recolor a card.
                color = feature_color(f.id)
                tooltip = self._card_tooltip(f, deps, by_id, labels, s)
                card = _FeatureCard(
                    f.id, side, labels[f.id], color, tooltip,
                    self.staging.is_deleted(f.id, side), self)
                # Insert before the trailing stretch (last layout item).
                lay.insertWidget(lay.count() - 1, card)
                self._cards[side].append(card)
        self.apply_theme(theme_manager.current)
        self._update_recap()
        self._links_overlay.raise_()
        self._links_overlay.update()

    def _card_tooltip(self, f, deps, by_id, labels, s: Strings) -> str:
        """Base tooltip + one link line per dependency edge touching `f`."""
        base = (s.studio_manual_feature_label if f.id == MANUAL_ID
                else feature_combo_tooltip(f))
        lines = [base]
        text = f.all_text()
        for pid in sorted(deps.get(f.id, ())):
            provider = by_id.get(pid)
            if provider is None:
                continue
            names = [n for n in sorted(providers(provider))
                     if re.search(rf"\b{re.escape(n)}\b", text)]
            if names:
                lines.append("\U0001F517 " + s.feature_link_uses.format(
                    name=names[0], label=labels.get(pid, pid)))
        for cid, pids in deps.items():
            if f.id in pids and cid in by_id:
                consumer_text = by_id[cid].all_text()
                names = [n for n in sorted(providers(f))
                         if re.search(rf"\b{re.escape(n)}\b", consumer_text)]
                if names:
                    lines.append("\U0001F517 " + s.feature_link_provides.format(
                        name=names[0], label=labels.get(cid, cid)))
        return "\n".join(lines)

    # ── Actions ────────────────────────────────────────────────
    def _toggle_delete(self, fid: str, side: str):
        self.staging.toggle_delete(fid, side)
        self._rebuild_columns()

    def _do_transfer(self, fid: str, to_side: str, index: int):
        from_side = "ia" if to_side == "stable" else "stable"
        self.staging.transfer(fid, from_side, to_side, index)
        self._rebuild_columns()

    def _transfer_all(self, src: str = "ia", dst: str = "stable"):
        self.staging.transfer_all(src, dst)
        self._rebuild_columns()

    def result(self):
        return self.staging.result()

    # ── Drag & drop ────────────────────────────────────────────
    def _drop_index_for(self, side: str, y: int) -> int:
        """Insertion index in `side` from a y position (column coords):
        number of cards whose vertical center sits above y."""
        idx = 0
        for card in self._cards[side]:
            if y > card.y() + card.height() / 2:
                idx += 1
        return idx

    def _handle_drop(self, fid: str, from_side: str, to_side: str,
                     index: int) -> None:
        """Route a drop: cross-column = transfer (copy + closure), same
        column = constrained reorder. `index` is the DISPLAY insertion index
        (the dragged card is still shown) -> shift by one when dropping
        below its own position."""
        if from_side == to_side:
            ids = [f.id for f in self.staging.features(to_side)]
            if fid not in ids:
                return
            cur = ids.index(fid)
            self.staging.reorder(fid, index - 1 if index > cur else index,
                                 to_side)
        else:
            self.staging.transfer(fid, from_side, to_side, index)
        self._rebuild_columns()

    def _group_pixmap(self, fid: str, side: str) -> QPixmap:
        """Composite drag pixmap: the dragged card + its dependency closure
        stacked vertically (slightly translucent)."""
        group = set(self.staging.group_for(fid, side))
        cards = [c for c in self._cards[side] if c.fid in group]
        if not cards:
            return QPixmap()
        gap = 4
        w = max(c.width() for c in cards)
        h = sum(c.height() for c in cards) + gap * (len(cards) - 1)
        pm = QPixmap(max(w, 1), max(h, 1))
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setOpacity(0.85)
        y = 0
        for c in cards:
            p.drawPixmap(0, y, c.grab())
            y += c.height() + gap
        p.end()
        return pm

    def _start_drag(self, card: "_FeatureCard") -> None:
        c = theme_manager.current
        group = set(self.staging.group_for(card.fid, card.side))
        # Highlight the whole travelling group while dragging.
        for other in self._cards[card.side]:
            if other.fid in group:
                other.setStyleSheet(
                    f"QFrame#featureCard {{ background-color: {c.main_bg};"
                    f" border: 1px solid {c.signal_ok};"
                    f" border-radius: 6px; }}")
        drag = QDrag(card)
        mime = QMimeData()
        mime.setData(_MIME, f"{card.fid}|{card.side}".encode())
        drag.setMimeData(mime)
        drag.setPixmap(self._group_pixmap(card.fid, card.side))
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        # Drop (if any) already rebuilt; rebuild again to clear the
        # highlight when the drag was cancelled.
        self._hide_drop_indicator()
        self._rebuild_columns()

    def _show_drop_indicator(self, side: str, index: int) -> None:
        colw = self._columns[side]
        self._drop_indicator.setParent(colw)
        cards = self._cards[side]
        if not cards:
            y = 2                       # top of the (header-less) column
        elif index >= len(cards):
            y = cards[-1].y() + cards[-1].height() + 1
        else:
            y = max(0, cards[index].y() - 3)
        self._drop_indicator.setGeometry(4, y, colw.width() - 8, 2)
        self._drop_indicator.show()
        self._drop_indicator.raise_()

    def _hide_drop_indicator(self) -> None:
        self._drop_indicator.hide()

    # ── Recap / apply ──────────────────────────────────────────
    def _recap_parts(self, s: Strings) -> list[str]:
        r = self.staging.recap()
        parts = []
        if r.transfers:
            parts.append(s.feature_transfer_recap_transfers.format(n=r.transfers))
        if r.deletions:
            parts.append(s.feature_transfer_recap_deletes.format(n=r.deletions))
        if r.reordered_ia or r.reordered_stable:
            parts.append(s.feature_transfer_recap_reorder)
        return parts

    def _update_recap(self):
        self._lbl_recap.setText(
            " · ".join(self._recap_parts(lang_manager.current)))

    def _on_apply(self):
        # Apply directly — no recap confirmation for a routine transfer (the
        # live recap label already previews the batch, and the drag/drop edits
        # are deliberate). EXCEPTION (user 2026-07-07): when applying carries a
        # real risk — a transferred/kept feature will use a deleted variable, or
        # a hand-edited window would be overwritten — confirm ONLY then, listing
        # the risk (never lose hand edits silently). Nothing to apply -> close.
        if not self.staging.has_changes():
            self.reject()
            return
        warnings = self._risk_warnings(lang_manager.current)
        if warnings and not self._confirm_risk(warnings):
            return
        self.accept()

    def _risk_warnings(self, s: Strings) -> list[str]:
        """Warning lines for the RISKY cases only — a transferred/kept feature
        depending on a deleted one, or a hand-edited window about to be
        rewritten. Empty => the batch is safe to apply without confirmation."""
        r = self.staging.recap()
        lines: list[str] = []
        labels = {side: {f.id: self._feat_label(f, s)
                         for f in self.staging.features(side)}
                  for side in ("ia", "stable")}
        for side, consumer, _provider in r.warnings:
            lines.append("⚠ " + s.feature_transfer_deleted_dep_warn.format(
                label=labels[side].get(consumer, consumer)))
        win_names = {"ia": s.studio_window_ai, "stable": s.studio_window_stable}
        for side in ("ia", "stable"):
            if self._dirty[side] and self._side_changed(side):
                lines.append("⚠ " + s.feature_transfer_dirty_warn.format(
                    win=win_names[side]))
        return lines

    def _confirm_risk(self, warning_lines: list[str]) -> bool:
        """Confirmation shown ONLY when the batch carries a risk (see
        _risk_warnings): lists the warnings + Confirmer / Annuler."""
        s = lang_manager.current
        c = theme_manager.current
        dlg = QDialog(self)
        dlg.setWindowTitle(s.feature_transfer_recap_title)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(12)
        lbl = QLabel("\n".join(warning_lines), dlg)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        row = QHBoxLayout()
        row.addStretch(1)
        b_cancel = QPushButton(s.gen_modal_cancel, dlg)
        b_cancel.setAutoDefault(False)
        b_cancel.setStyleSheet(secondary_button_qss(c, radius=8,
                                                    padding="6px 16px"))
        b_cancel.clicked.connect(lambda: dlg.done(0))
        b_ok = QPushButton(s.feature_transfer_confirm, dlg)
        b_ok.setDefault(True)
        b_ok.setStyleSheet(primary_button_qss(c, radius=8, padding="6px 16px"))
        b_ok.clicked.connect(lambda: dlg.done(1))
        row.addWidget(b_cancel)
        row.addWidget(b_ok)
        lay.addLayout(row)
        dlg.setStyleSheet(f"QDialog {{ background-color: {c.sidebar_bg}; }} "
                          f"QLabel {{ background: transparent; "
                          f"color: {c.text_primary}; }}")
        return dlg.exec() == 1

    def _side_changed(self, side: str) -> bool:
        """True if applying would rewrite this window's code."""
        r = self.staging.recap()
        reordered = r.reordered_ia if side == "ia" else r.reordered_stable
        return bool(self.staging._deleted[side] or reordered
                    or side in self.staging._transferred_all
                    or any(d == side for d, _ in self.staging._transferred))

    # ── Theme / lang ───────────────────────────────────────────
    def apply_lang(self, s: Strings):
        self.setWindowTitle(s.feature_transfer_title)
        # Titles mirror the main window section headers («_» prefix + the
        # mono-caps font applied in apply_theme).
        self._col_headers["ia"].setText("_" + s.studio_window_ai)
        self._col_headers["stable"].setText("_" + s.studio_window_stable)
        self._transfer_btns["ia"].setText(s.feature_transfer_all)
        self._transfer_btns["stable"].setText(s.feature_transfer_all_back)
        self._btn_cancel.setText(s.gen_modal_cancel)
        self._btn_apply.setText(s.feature_transfer_apply)

    def apply_theme(self, c: ColorScheme):
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c.sidebar_bg}; }}
            QLabel {{ background: transparent; color: {c.text_primary}; }}
            QFrame#featureBox {{
                background-color: {c.input_bg};
                border: 1px solid {c.border};
                border-radius: 8px;
            }}
            QFrame#featureBox QScrollArea {{
                background: transparent; border: none;
            }}
            /* Le VIEWPORT, explicitement. Le fond etait pose sur sa palette
               juste en dessous, et Qt l'annulait : poser une QSS sur un
               ancetre remet `autoFillBackground` du viewport a False et
               rabat sa palette. Mesure au pixel : input_bg couvrait 0,0 % de
               la zone, dans les deux themes — l'effet « cartes en creux »
               recherche etait nul, seul le lisere 1 px distinguait une carte
               du fond. Ici la couleur passe par le meme mecanisme que celui
               qui l'effacait, donc elle tient. */
            QFrame#featureBox QScrollArea > QWidget > QWidget {{
                background-color: {c.input_bg};
            }}
            QFrame#featureCard {{
                background-color: {c.main_bg};
                border: 1px solid {c.border};
                border-radius: 6px;
            }}
            QFrame#dropIndicator {{ background-color: {c.signal_ok}; }}
        """)
        # (Le fond du viewport est desormais dans la feuille ci-dessus. Le
        # poser par la palette ici etait un no-op mesure : la QSS de l'ancetre
        # l'effacait a chaque application du theme.)
        # Titles: identical look to the main window section headers.
        for hdr in self._col_headers.values():
            hdr.setFont(mono_caps_font(8))
            hdr.setStyleSheet(
                f"color: {c.text_primary}; background: transparent;")
        self._lbl_recap.setStyleSheet(
            f"color: {c.text_secondary}; background: transparent;")
        self._btn_cancel.setStyleSheet(
            secondary_button_qss(c, radius=8, padding="4px 14px"))
        self._btn_apply.setStyleSheet(
            primary_button_qss(c, radius=8, padding="4px 14px"))
        for btn in self._transfer_btns.values():
            btn.setStyleSheet(
                secondary_button_qss(c, radius=8, padding="4px 14px"))
        for cards in self._cards.values():
            for card in cards:
                card._lbl.setStyleSheet(
                    f"color: {c.text_secondary if card.deleted else c.text_primary};"
                    f" background: transparent;")
                card._handle.setStyleSheet(
                    f"color: {c.text_secondary}; background: transparent;")
