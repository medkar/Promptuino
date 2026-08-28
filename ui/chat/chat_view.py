"""Permanent chat panel integrated into the main window.

Vertical 3-zone layout:
- Header (40px): title + turn counter + 'New conversation' button
- Conversation (flex): scrollable, ChatMessage bubbles
- Input: rounded bar — multi-line QTextEdit (Enter = send, no
  send button) + toolbar (attach a doc, model label, Stop button
  shown only during streaming)

The widget hooks into the ChatController. Project context update
triggered by the caller (MainWindow) via set_project_context().
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    Qt, pyqtSignal, QThread, QTimer, QRectF,
    QPropertyAnimation, QParallelAnimationGroup, QEasingCurve,
)
from PyQt6.QtGui import QColor, QKeyEvent, QPalette, QPainter, QFont
from PyQt6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

from .. import icons as IC
from ..board_manager import board_manager
from ..i18n import lang_manager
from ..message_box import ask_yes_no
from ..robot_loader import RobotLoader, LoaderLabel
from ..session import session
from ..theme import (theme_manager, selection_bg, install_icon_hover,
                     chip_button_qss)
from ..fonts import mono_caps_font
from .chat_controller import (
    ChatController, ChatTurnResult, ChatTurnKind, StreamingRequired,
)
from .chat_message import ChatMessage


_DEFAULT_WIDTH = 340
_COLLAPSED_WIDTH = 48
# Soft watchdog: at 60s without a chunk we show a 1st non-blocking
# warning bubble, at 180s a 2nd more insistent one. NO auto-kill --
# the user decides via the Stop button (already wired to cancel()).
# Why no auto-kill: we can't distinguish on the client side
# "slow backend that will respond" vs "broken backend"; an auto-kill
# too early loses the legitimate response of a model that is thinking.
# The backend already has its own timeouts (Claude CLI 120s, Ollama
# 300s, etc.) -> as a last resort the exception bubbles up via
# _on_stream_error which shows the friendly message from Fix 6.
_STREAM_SOFT_WARN_MS = 60_000
_STREAM_HARD_WARN_MS = 180_000


_CHIP_LABEL_MAX_W = 140   # max width of the chip label (px) -> truncation …


def _single_local_file_path(event) -> str | None:
    """Path of a SINGLE local file carried by a drag/drop event, otherwise
    None (text, multi-files, remote URL)."""
    md = event.mimeData()
    if not md.hasUrls():
        return None
    urls = md.urls()
    if len(urls) != 1:
        return None
    u = urls[0]
    if not u.isLocalFile():
        return None
    return u.toLocalFile()


class _ChatInput(QTextEdit):
    """Multi-line QTextEdit with Enter = send, Shift+Enter = newline.

    Also accepts dropping a single local file (`file_dropped`): the
    document becomes the context shared with the prompt. Other drops
    (text, multi-files) fall back to the QTextEdit's native behavior.
    """

    send_requested = pyqtSignal()
    file_dropped = pyqtSignal(str)   # local path of a dropped file

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.setFixedHeight(80)
        self.setAcceptDrops(True)
        # Placeholder painted by hand (cf. paintEvent): Qt renders a QTextEdit's
        # placeholder on a SINGLE clipped line -> long tips get
        # truncated. We draw it ourselves with line wrapping.
        self._placeholder = ""

    def setPlaceholderText(self, text: str) -> None:  # type: ignore[override]
        # We capture the text and neutralize Qt's single-line rendering
        # (empty placeholder on Qt's side) to paint it wrapped in paintEvent.
        self._placeholder = text or ""
        super().setPlaceholderText("")
        self.viewport().update()

    def paintEvent(self, e) -> None:  # type: ignore[override]
        super().paintEvent(e)
        if self._placeholder and not self.toPlainText():
            painter = QPainter(self.viewport())
            painter.setPen(
                self.palette().color(QPalette.ColorRole.PlaceholderText))
            painter.setFont(self.font())
            m = int(self.document().documentMargin())
            rect = self.viewport().rect().adjusted(m, m, -m, -m)
            painter.drawText(
                rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                    | Qt.TextFlag.TextWordWrap),
                self._placeholder,
            )
            painter.end()

    def keyPressEvent(self, e: QKeyEvent) -> None:  # type: ignore[override]
        if (e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self.send_requested.emit()
            return
        super().keyPressEvent(e)

    def dragEnterEvent(self, event):  # type: ignore[override]
        if _single_local_file_path(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # type: ignore[override]
        if _single_local_file_path(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # type: ignore[override]
        path = _single_local_file_path(event)
        if path is not None:
            event.acceptProposedAction()
            self.file_dropped.emit(path)
            return
        super().dropEvent(event)


class _VerticalLabel(QWidget):
    """Text label painted vertically (-90° rotation) for the chat's collapsed
    strip (Phase 3 §7). Qt QSS can't rotate text -> paintEvent.
    Clickable (emits `clicked`): when collapsed, clicking the title expands the chat."""

    clicked = pyqtSignal()
    hover_changed = pyqtSignal(bool)   # title hover (to link to the bar's chevron)

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._text = text
        self._color = "#7d8898"
        self._hover_color = "#00d9a0"   # phosphor green on hover
        self._hover = False
        self._linked = False   # hover of the LINKED widget (chat bar chevron)
        # Fills the whole collapsed strip -> the text painted at the center is
        # centered H AND V (cf collapsed_body). No more fixed width.
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, e) -> None:  # type: ignore[override]
        if (e.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(e.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def enterEvent(self, e) -> None:  # type: ignore[override]
        self._hover = True
        self.hover_changed.emit(True)
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # type: ignore[override]
        self._hover = False
        self.hover_changed.emit(False)
        self.update()
        super().leaveEvent(e)

    def set_linked_hover(self, hovered: bool) -> None:
        """The linked widget (chat bar chevron) is hovered -> we light up
        too (title + chevron green together)."""
        if hovered != self._linked:
            self._linked = hovered
            self.update()

    def set_text(self, t: str) -> None:
        self._text = t
        self.update()

    def set_color(self, c: str) -> None:
        self._color = c
        self.update()

    def set_hover_color(self, c: str) -> None:
        self._hover_color = c
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # SAME font as the Studio section titles (mono-caps 8 pt).
        p.setFont(mono_caps_font(8))
        hovered = self._hover or self._linked
        p.setPen(QColor(self._hover_color if hovered else self._color))
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(-90)
        p.drawText(
            QRectF(-self.height() / 2, -self.width() / 2,
                   self.height(), self.width()),
            int(Qt.AlignmentFlag.AlignCenter), self._text,
        )
        p.end()


class _TypingIndicator(QWidget):
    """Robot loader ('the assistant is writing…') shown before the 1st chunk.
    Replaces the old 3-dot indicator. Purely visual."""

    def __init__(self, *, dark: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(5)
        self._robot = RobotLoader(
            point_size=12, color=theme_manager.current.signal_ok)
        lay.addWidget(self._robot)
        # "Thinking…" label: mono (JetBrains), green, animated dots.
        # Since the robot has a fixed reserved width, this text doesn't move.
        self._lbl = LoaderLabel(
            lang_manager.current.chat_thinking, point_size=9,
            color=theme_manager.current.signal_ok)
        lay.addWidget(self._lbl)
        lay.addStretch(1)

    def start(self) -> None:
        self._robot.start()
        self._lbl.start()

    def stop(self) -> None:
        self._lbl.stop()
        self._robot.stop()

    # ── Theme / language ─────────────────────────────────────────
    # The robot and its label freeze the color and the text they are built
    # with. The indicator lives across a whole stream (up to 3 min), so a
    # theme or language switch made meanwhile must reach it — same
    # `set_color(c.signal_ok)` pattern as the 5 other RobotLoader users
    # (add_comments / explain_code / lint_code / repair_code dialogs,
    # studio/code_panel).
    def apply_theme(self, c) -> None:
        self._robot.set_color(c.signal_ok)
        self._lbl.set_color(c.signal_ok)

    def apply_lang(self, s) -> None:
        # LoaderLabel.set_text re-renders while keeping the dot animation.
        self._lbl.set_text(s.chat_thinking)


class _StreamWorker(QThread):
    """Worker thread that consumes backend.chat_stream() and emits the
    chunks to the UI thread. Keeps the accumulated text in a buffer so it
    can be restored in case of error or stop."""

    # Emitted on each chunk: payload = accumulated buffer (not the chunk alone).
    # Simplifies rendering on the UI side (no need to accumulate there).
    chunk_received = pyqtSignal(str)
    # Emitted when the stream ends normally (incl. stop): full text.
    stream_finished = pyqtSignal(str)
    # Emitted in case of an exception: (error_message, partial_text).
    stream_error = pyqtSignal(str, str)

    def __init__(self, backend, system_prompt: str,
                 messages: list[dict], parent: QWidget | None = None):
        super().__init__(parent)
        self._backend = backend
        self._system = system_prompt
        self._messages = messages
        self._stop_requested = False
        self._buffer = ""

    def request_stop(self) -> None:
        """Requests the stop. The iteration will exit at the next chunk."""
        self._stop_requested = True

    def run(self) -> None:
        try:
            for chunk in self._backend.chat_stream(
                    self._system, self._messages):
                if self._stop_requested:
                    break
                if not chunk:
                    continue
                self._buffer += chunk
                self.chunk_received.emit(self._buffer)
            self.stream_finished.emit(self._buffer)
        except Exception as e:
            self.stream_error.emit(str(e), self._buffer)


class ChatView(QWidget):
    """Persistent chat panel, placed between sidebar and main stack."""

    # Emitted when the user clicks the "Open in workshop" button
    # (after a generation intent is detected).
    open_in_atelier_requested = pyqtSignal(str)   # user_text

    # Bouton « Modifier dans le Studio » : ouvre le flux Modifier pré-staged
    # (prompt rempli + modale Modifier + fonction pré-cochée). Remplace l'ancien
    # préfixe magique « CORRECTION … » émis via open_in_atelier_requested.
    request_modify_in_studio = pyqtSignal(str)   # seed propre (sans préfixe)

    # Emitted after each LLM_REPLY turn to notify MainWindow to save.
    history_changed = pyqtSignal()

    # Emitted when the user clicks the model label (-> AI Model tab).
    open_model_settings_requested = pyqtSignal()

    # Emitted during the collapse/expand animation (current width): lets the
    # topbar re-center the mode selector.
    width_changed = pyqtSignal(int)

    # Emitted when the collapsed/expanded state changes (in-chat OR topbar toggle OR restore)
    # -> MainWindow syncs the topbar's chat button.
    collapsed_changed = pyqtSignal(bool)

    # Hover of the vertical « _ASSISTANT IA » title (collapsed) -> MainWindow lights
    # up the chat bar chevron too (they are visually linked).
    title_hover_changed = pyqtSignal(bool)

    # Attachment shared with the "Generate a feature" prompt: the
    # chat no longer stores its own document, it routes the drop/removal to the
    # project's context file (via MainWindow -> StudioView).
    attach_file_requested = pyqtSignal(str)   # chosen/dropped local path
    detach_file_requested = pyqtSignal()      # chip's ✕

    def __init__(self,
                 controller: ChatController,
                 parent: QWidget | None = None):
        super().__init__(parent)
        # File drop accepted over the ENTIRE chat window (not just the
        # input): zones that don't capture drops (user bubbles,
        # scroll, margins) propagate the event up to here; the input and the
        # assistant bubbles (QTextBrowser, neutralized drops) route the same file.
        self.setAcceptDrops(True)
        self.controller = controller
        # F2-5 net: context of the correction in progress (None outside the net).
        # Set by preload_correction, consumed/cleared at resolution.
        self._pending_correction = None
        # Selected board -> controller (auto-inject of specs into the chat).
        self.controller.board_model = board_manager.model
        board_manager.changed.connect(self._on_board_changed)
        # Optional hook called just before each user send to the LLM.
        # Lets MainWindow push a fresh project context (live editor
        # code) without depending on deferred signals.
        self.pre_send_hook = None   # type: ignore
        # Streaming state (cf _StreamWorker + _start_stream).
        self._worker: _StreamWorker | None = None
        self._streaming_bubble: ChatMessage | None = None
        self._streaming_user_text: str = ""
        # Sub-project 2: correction intent of the current turn (remembered
        # from StreamingRequired) -> additive « Corriger dans Studio » button
        # added after the response, outside an armed net session.
        self._streaming_correction_intent: bool = False
        self._last_buffer: str = ""
        self._rerender_pending: bool = False
        # Auto-scroll pin: True = we follow the bottom on each layout update
        # (streaming chunks, new bubbles). Becomes False when the user
        # scrolls up manually (= "I'm reading", don't jump). Back to True when
        # they scroll back down to < 50px from the bottom OR on an explicit action (send /
        # project load / reset / stream start) via force=True.
        self._auto_scroll_pinned = True
        # Soft watchdog: 2 single-shot timers reset on each received chunk.
        # Soft fire (60s) -> gentle warning bubble. Hard fire (180s) ->
        # more insistent bubble. NO auto-kill.
        self._stream_soft_warn_timer = QTimer(self)
        self._stream_soft_warn_timer.setSingleShot(True)
        self._stream_soft_warn_timer.timeout.connect(
            self._on_stream_soft_warn
        )
        self._stream_hard_warn_timer = QTimer(self)
        self._stream_hard_warn_timer.setSingleShot(True)
        self._stream_hard_warn_timer.timeout.connect(
            self._on_stream_hard_warn
        )
        # Ref to the active warning bubble (auto-removed at the
        # next chunk or at the end of the stream). Only one at a time:
        # the hard warn replaces the soft one.
        self._active_warning_bubble: ChatMessage | None = None
        # "the assistant is writing…" indicator shown before the 1st chunk.
        self._typing_indicator = None   # type: ignore
        # True when a theme switch happened while a stream was running: the
        # conversation re-theme was deliberately skipped then (cf _apply_theme)
        # and has to be caught up when the stream ends.
        self._theme_catchup_pending = False
        # Workers detached on Stop click: their UI callbacks are cut and
        # they finish in the background (request_stop/cancel already emitted). We
        # keep them referenced here until their `finished` signal (otherwise the
        # Python QThread would be GC'd while the C++ thread is still running).
        # Lets us reactivate the UI IMMEDIATELY on click, without waiting for the
        # worker's actual exit nor risking a double-worker (its
        # signals no longer re-enter the view).
        self._detached_workers: list = []
        # User text of the last send -- used by the "Open in
        # Studio" button on GENERATION_REDIRECT bubbles to pre-fill
        # the workshop prompt.
        self._last_user_text: str = ""
        # Collapse (48px strip) + unread message counter (Phase 3 §7).
        self._collapsed = False
        self._unread = 0
        self.setFixedWidth(_DEFAULT_WIDTH)
        self._build()
        # Subscribes to language changes (refresh labels).
        lang_manager.changed.connect(self._apply_lang)
        self._apply_lang()
        # Subscribes to theme changes. The chat panel was not
        # wired to the ThemeManager: it therefore inherited the system palette
        # (Base role) instead of the app theme, hence a white background in
        # dark theme on machines whose Windows is in light mode.
        theme_manager.changed.connect(self._apply_theme)
        self._apply_theme()

        # Collapse animation (min+maxWidth simultaneously, 180ms OutCubic) — same
        # mechanism as the sidebar (Phase 3 §7).
        self._anim = QParallelAnimationGroup(self)
        self._anim_min = QPropertyAnimation(self, b"minimumWidth")
        self._anim_max = QPropertyAnimation(self, b"maximumWidth")
        for a in (self._anim_min, self._anim_max):
            a.setDuration(180)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.addAnimation(a)
        self._anim_max.valueChanged.connect(lambda v: self.width_changed.emit(int(v)))
        # Marks messages as unread if a response arrives while collapsed.
        self.history_changed.connect(self._note_unread_if_collapsed)
        # Restores the persisted collapsed state (without animation).
        if session.chat_collapsed:
            self.set_collapsed(True, animate=False)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ─── Header (64px): collapse + title + counter + new conversation ─
        self._header = QFrame()
        self._header.setFixedHeight(64)
        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(10, 0, 8, 0)
        h_lay.setSpacing(6)
        # Collapse button REPLACED by the chevron centered on the separator bar
        # to the left of the chat (cf MainWindow._CollapseHandle). Kept built
        # (apply_theme still references it) but hidden.
        self._collapse_btn = QPushButton()
        self._collapse_btn.setFixedSize(28, 28)
        self._collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._collapse_btn.clicked.connect(self.toggle_collapsed)
        self._collapse_btn.hide()
        h_lay.addWidget(self._collapse_btn)
        h_lay.addStretch(1)   # centers the title horizontally (user request)
        self._title_lbl = QLabel("")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_lay.addWidget(self._title_lbl)
        h_lay.addStretch(1)
        h_lay.addSpacing(4)
        self._reset_btn = QPushButton()
        self._reset_btn.setFixedSize(24, 24)
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # New-conversation button: counter-clockwise arrow, no chrome,
        # white at rest -> green on hover (install_icon_hover does the icon
        # recolor that QSS cannot apply to a QIcon).
        # The app's BARE variant rather than a local copy: measured identical
        # at rest and on hover, in both themes. The variant also recolors the
        # TEXT on hover, which is a no-op here (icon-only button) -- the icon
        # recolor is `install_icon_hover`'s job just below, since QSS cannot
        # repaint a QIcon.
        self._reset_btn.setProperty("variant", "bare")
        self._reset_icon_hover = install_icon_hover(
            self._reset_btn, IC.REFRESH, 16, normal_role="text_primary"
        )
        self._reset_btn.clicked.connect(self._on_reset_clicked)
        h_lay.addWidget(self._reset_btn)
        outer.addWidget(self._header)

        # ─── « Expanded » body (conversation + input) — hidden when collapsed ─
        self._expanded_body = QWidget()
        eb = QVBoxLayout(self._expanded_body)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(0)

        # Separator under the header (title) — user request.
        self._header_sep = QFrame()
        self._header_sep.setFixedHeight(1)
        eb.addWidget(self._header_sep)

        # ─── Conversation scroll ──────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self._conv_container = QWidget()
        self._conv_lay = QVBoxLayout(self._conv_container)
        self._conv_lay.setContentsMargins(0, 8, 0, 8)
        self._conv_lay.setSpacing(2)
        self._conv_lay.addStretch(1)
        self._scroll.setWidget(self._conv_container)
        eb.addWidget(self._scroll, stretch=1)
        # Auto-scroll: flushes deferred layout updates (QTextBrowser
        # takes several cycles to stabilize its height -> rangeChanged can
        # fire 2-3 times after an insertWidget). As long as `_auto_scroll_pinned`
        # is True, each rangeChanged brings it back to the bottom.
        vsb = self._scroll.verticalScrollBar()
        vsb.rangeChanged.connect(self._on_scroll_range_changed)
        vsb.valueChanged.connect(self._on_scroll_value_changed)

        # ─── Input (rounded bar, no send button) ──────────
        input_frame = QFrame()
        input_frame.setObjectName("ChatInputFrame")
        input_lay = QVBoxLayout(input_frame)
        input_lay.setContentsMargins(8, 8, 8, 8)
        input_lay.setSpacing(6)

        # Attachment chip (hidden as long as no doc). Built here but PLACED
        # in the bottom toolbar, to the right of the « Joindre » button.
        self._attach_chip = QFrame()
        self._attach_chip.setObjectName("ChatAttachChip")
        chip_lay = QHBoxLayout(self._attach_chip)
        chip_lay.setContentsMargins(8, 2, 4, 2)
        chip_lay.setSpacing(4)
        self._chip_lbl = QLabel("")
        chip_lay.addWidget(self._chip_lbl)
        self._chip_remove_btn = QPushButton("✕")
        self._chip_remove_btn.setFixedSize(18, 18)
        self._chip_remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chip_remove_btn.clicked.connect(self._clear_attachment)
        chip_lay.addWidget(self._chip_remove_btn)
        self._attach_chip.setVisible(False)

        self._input = _ChatInput()
        self._input.send_requested.connect(self._on_send_clicked)
        # File drop on the input -> shared context (via MainWindow).
        self._input.file_dropped.connect(self.attach_file_requested.emit)
        # Rotating tips in the placeholder (every 10 s, cf #24) —
        # started only when a backend is active (cf _refresh_input_state).
        from ..prompt_tips import PromptTipRotator
        self._tips = PromptTipRotator(self._input)
        input_lay.addWidget(self._input)

        # Bottom toolbar: + (left) | model label + Stop (right).
        tool_row = QHBoxLayout()
        tool_row.setContentsMargins(0, 0, 0, 0)
        self._attach_btn = QPushButton("")   # « + Attach » label via _apply_lang
        self._attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._attach_btn.clicked.connect(self._on_attach_clicked)
        tool_row.addWidget(self._attach_btn)
        # Attachment chip just to the right of the « Joindre » button (user request).
        tool_row.addWidget(self._attach_chip)
        tool_row.addStretch(1)
        self._model_lbl = QPushButton("")
        self._model_lbl.setFlat(True)
        self._model_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model_lbl.clicked.connect(self.open_model_settings_requested.emit)
        tool_row.addWidget(self._model_lbl)
        self._stop_btn = QPushButton("■")
        self._stop_btn.setFixedSize(28, 28)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn.setVisible(False)
        tool_row.addWidget(self._stop_btn)
        input_lay.addLayout(tool_row)

        eb.addWidget(input_frame)
        outer.addWidget(self._expanded_body, stretch=1)

        # ─── « Collapsed » body (48px strip): ONLY the vertical
        # « _ASSISTANT IA » label, centered H+V (user request: no more chat icon
        # button nor badge — expansion happens via the separator bar's
        # chevron). Hidden when expanded (Phase 3 §7). ─
        self._collapsed_body = QWidget()
        cb = QHBoxLayout(self._collapsed_body)
        cb.setContentsMargins(0, 0, 0, 0)
        cb.setSpacing(0)
        # The vertical label FILLS the whole strip (without alignment, which disables
        # the fill) -> its text, painted at the center, is centered H AND V.
        self._vertical_label = _VerticalLabel("")
        # When collapsed, clicking the title expands the chat (the bar chevron stays
        # the other way). When expanded, the label is hidden -> not clickable.
        self._vertical_label.clicked.connect(lambda: self.set_collapsed(False))
        # Hover linked to the chat bar chevron (both light up together).
        self._vertical_label.hover_changed.connect(self.title_hover_changed)
        cb.addWidget(self._vertical_label)
        self._collapsed_body.setVisible(False)
        outer.addWidget(self._collapsed_body, stretch=1)

        self._refresh_input_state()
        self._refresh_model_label()

    # ─── Collapse / expand (Phase 3 §7) ───────────────────────────────────────

    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_title_linked_hover(self, hovered: bool) -> None:
        """The chat bar chevron is hovered -> also lights up the vertical
        « _ASSISTANT IA » title (both are linked)."""
        self._vertical_label.set_linked_hover(hovered)

    def set_collapsed(self, collapsed: bool, *, animate: bool = True) -> None:
        """Collapses (48px strip) / expands (340px) the chat panel. Persisted state.
        On expand, the unread badge is reset to zero."""
        self._collapsed = collapsed
        session.chat_collapsed = collapsed
        self._apply_collapsed_ui()
        target = _COLLAPSED_WIDTH if collapsed else _DEFAULT_WIDTH
        if animate:
            self._anim.stop()
            for a in (self._anim_min, self._anim_max):
                a.setStartValue(self.width())
                a.setEndValue(target)
            self._anim.start()
        else:
            self.setFixedWidth(target)
        if not collapsed:
            self._unread = 0
            self._update_collapsed_unread()
        self.collapsed_changed.emit(collapsed)

    def _apply_collapsed_ui(self) -> None:
        collapsed = self._collapsed
        self._expanded_body.setVisible(not collapsed)
        self._collapsed_body.setVisible(collapsed)
        # When collapsed, the header (64px) no longer contains anything visible -> we
        # hide it so the collapsed body occupies the ENTIRE panel height:
        # the vertical title then centers at the same height as the separator
        # bar's chevron (otherwise it was centered under the header => offset).
        self._header.setVisible(not collapsed)
        self._title_lbl.setVisible(not collapsed)
        self._reset_btn.setVisible(not collapsed)
        self._refresh_collapse_icon()
        self._update_collapsed_unread()

    def _refresh_collapse_icon(self) -> None:
        c = theme_manager.current
        svg = IC.PANEL_RIGHT_OPEN if self._collapsed else IC.PANEL_RIGHT_CLOSE
        self._collapse_btn.setIcon(IC.make_icon(svg, c.text_secondary, 18))

    def _note_unread_if_collapsed(self) -> None:
        """A response arrived: if the chat is collapsed, increments the
        unread counter (shown as a badge on the icon)."""
        if self._collapsed:
            self._unread += 1
            self._update_collapsed_unread()

    def _update_collapsed_unread(self) -> None:
        # The unread badge was removed along with the chat icon from the collapsed strip
        # (user request). The `_unread` counter is still tracked (without display).
        return

    def _apply_lang(self) -> None:
        s = lang_manager.current
        # #10/#11: « _ » prefix like the Studio titles (« _ASSISTANT IA »).
        self._title_lbl.setText(f"_{s.chat_title}")
        # Same prefix on the collapsed chat's vertical label (user request).
        self._vertical_label.set_text(f"_{s.chat_title}")
        self._stop_btn.setToolTip(s.chat_stop_button)
        self._attach_btn.setText(s.studio_attach)
        self._attach_btn.setToolTip(s.chat_attach_tooltip)
        self._model_lbl.setToolTip(s.chat_model_label_tooltip)
        self._reset_btn.setToolTip(s.chat_new_conversation)
        # Built on the fly at each stream, absent the rest of the time.
        if self._typing_indicator is not None:
            self._typing_indicator.apply_lang(s)
        self._refresh_input_state()

    def _is_dark_theme(self) -> bool:
        return theme_manager.is_dark

    @staticmethod
    def _paint_bg(widget: QWidget, hex_color: str) -> None:
        """Force the background via QPalette (Window AND Base roles) + autoFill.

        We set Base in addition to Window because scrollable areas
        (QScrollArea.viewport) and text fields (QTextEdit) paint
        their background with the Base role, not Window — without this, the viewport
        falls back to the system palette's Base color (white in light
        Windows mode)."""
        pal = widget.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(hex_color))
        pal.setColor(QPalette.ColorRole.Base, QColor(hex_color))
        widget.setPalette(pal)
        widget.setAutoFillBackground(True)

    def _apply_theme(self, c=None) -> None:
        """Aligns the chat panel with the app theme. Called at init
        and on each theme switch."""
        c = c or theme_manager.current
        # Chat panel background = sidebar_bg (dark panel distinct from the content,
        # spec §3). Header + input frame (QFrame without autoFill) inherit it.
        self._paint_bg(self, c.sidebar_bg)
        # Conversation area: under the app's global stylesheet, the
        # palette background of a QScrollArea's viewport (with setWidget)
        # is NOT painted reliably -- the QStyleSheetStyle takes
        # over and the viewport falls back to the system Base color
        # (white in light Windows mode). So we force it via a QSS scope
        # by objectName, which IS respected. The container fills the
        # viewport (setWidgetResizable=True) so it covers it entirely.
        self._scroll.setObjectName("ChatScroll")
        self._conv_container.setObjectName("ChatConv")
        self._scroll.setStyleSheet(
            f"#ChatScroll, #ChatScroll > QWidget {{ background: {c.sidebar_bg}; "
            f"border: none; }}"
        )
        self._conv_container.setStyleSheet(
            f"#ChatConv {{ background: {c.sidebar_bg}; }}"
        )
        # Input field: same constraint as the conversation area
        # (the QTextEdit's Base palette isn't painted reliably
        # under the global stylesheet). We force it via QSS objectName.
        self._input.setObjectName("ChatInput")
        self._input.setStyleSheet(
            f"#ChatInput {{ background: {c.input_bg}; "
            f"color: {c.text_primary}; "
            f"border: 1px solid {c.border}; border-radius: 6px; "
            # Padding >= radius: otherwise the QTextEdit's rectangular viewport
            # overlaps the rounded corners and « cuts » the border (text side).
            f"padding: 8px 12px; "
            f"selection-background-color: {selection_bg(c)}; "
            f"selection-color: {c.text_primary}; }} "
            # Green border when the field is active (like the feature prompt).
            f"#ChatInput:focus {{ border: 1px solid {c.signal_ok}; }}"
        )
        # Header title « _ASSISTANT IA »: SAME style as the Studio section
        # titles (mono-caps 8 pt font + text_primary), instead of a separate
        # style. cf studio_view (loop over the section's _ElidingLabel).
        self._title_lbl.setFont(mono_caps_font(8))
        self._title_lbl.setStyleSheet(
            f"color: {c.text_primary}; background: transparent;"
        )
        # Header collapse button (hidden — replaced by the bar chevron):
        # style kept for consistency should it reappear.
        _round_sec = (
            f"QPushButton {{ background: transparent; "
            f"border: 1px solid {c.border}; border-radius: 6px; }} "
            f"QPushButton:hover {{ background: {c.border}; }}"
        )
        self._collapse_btn.setStyleSheet(_round_sec)
        self._refresh_collapse_icon()
        # Collapsed strip's vertical label: WHITE (text_primary), GREEN on hover.
        self._vertical_label.set_color(c.text_primary)
        self._vertical_label.set_hover_color(c.signal_ok)
        # Separator under the chat header (between title and conversation).
        self._header_sep.setStyleSheet(f"background: {c.border}; border: none;")
        # The "writing…" indicator (robot + label) also freezes its color at
        # construction, and it survives a whole stream: it only exists between
        # _show_typing_indicator and _remove_typing_indicator.
        if self._typing_indicator is not None:
            self._typing_indicator.apply_theme(c)
        # The bubbles freeze their dark/light color at construction:
        # we rebuild them to reflect the new theme. We avoid this
        # during an active stream (the in-progress bubble is referenced).
        if self._worker is None:
            self._rebuild_conversation()
        else:
            # Deferred to the end of the stream, otherwise the conversation
            # stays frozen in the previous theme until the next toggle made
            # outside a stream (cf _catch_up_theme_after_stream).
            self._theme_catchup_pending = True
        self._style_input_bar(c)

    def _style_input_bar(self, c) -> None:
        """Styling of the input bar elements (chip, buttons, label)."""
        self._attach_chip.setStyleSheet(
            "#ChatAttachChip { background:transparent; border:none; }"
        )
        chip_font = self._chip_lbl.font()
        chip_font.setPixelSize(10)
        self._chip_lbl.setFont(chip_font)
        self._chip_lbl.setMaximumWidth(_CHIP_LABEL_MAX_W)
        self._chip_lbl.setStyleSheet(f"color:{c.text_primary};")
        # `padding: 0` is load-bearing: this button has a FIXED size and its
        # content is a TEXT glyph (■). Without it the application default
        # (`7px 18px`, theme.app_qss) pushes the square out of the frame and
        # only the circle is drawn -- measured, 272 ink px instead of 304.
        round_btn = (
            f"QPushButton {{ background:transparent; color:{c.text_primary}; "
            f"border:1px solid {c.border}; border-radius:14px; padding:0; }} "
            f"QPushButton:hover {{ background:{c.border}; }}"
        )
        # Same « + Attach » element as the prompt field (Lot 3), and now
        # literally the same recipe. `bg=c.surface`: this one sits on the chat
        # bar, the Studio's twin sits on the prompt field (`code_bg`).
        # The helper's `:disabled` is what makes the button LOOK switched off
        # while a streaming answer is running -- without it the sheet repainted
        # every state identically (measured 0 % difference).
        self._attach_btn.setStyleSheet(chip_button_qss(c, bg=c.surface))
        self._stop_btn.setStyleSheet(round_btn)
        # `padding: 0`, same reason as `round_btn` above and even worse here:
        # measured at 0 ink pixels, i.e. the ✕ was drawn NOWHERE inside the
        # 18x18 frame -- the only way to remove an attachment was invisible.
        self._chip_remove_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{c.text_secondary}; "
            f"border:none; padding:0; }} "
            f"QPushButton:hover {{ color:{c.text_primary}; }}"
        )
        self._model_lbl.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{c.text_secondary}; "
            f"border:none; font-size:11px; }} "
            f"QPushButton:hover {{ color:{c.signal_ok}; }}"
        )

    def _rebuild_conversation(self) -> None:
        """Rebuilds the bubbles from self.controller.history."""
        # Empties the layout (keeps the final stretch).
        while self._conv_lay.count() > 1:
            it = self._conv_lay.takeAt(0)
            w = it.widget() if it is not None else None
            if w is not None:
                w.deleteLater()
        dark = self._is_dark_theme()
        for i, m in enumerate(self.controller.history):
            role = (m.get("role") if isinstance(m, dict) else None) or "assistant"
            text = (m.get("content") if isinstance(m, dict) else None) or ""
            try:
                bubble = ChatMessage(
                    role=role, text=str(text),
                    dark_theme=dark,
                )
                # Inserts BEFORE the stretch (= second to last).
                self._conv_lay.insertWidget(
                    self._conv_lay.count() - 1, bubble,
                )
            except Exception as e:
                # A bubble that crashes (malformed markdown, exotic
                # content, etc.) must NOT break the whole panel.
                # Log to the console for diagnosis + skip the bubble.
                print(
                    f"[chat] Skipping bubble {i} (role={role!r}): {e}",
                    flush=True,
                )
                continue
        # Project load or reset -> we want to see the end of the conversation.
        self._scroll_to_bottom(force=True)

    def _catch_up_theme_after_stream(self) -> None:
        """Applies the conversation re-theme that _apply_theme skipped while a
        stream was running. Idempotent: does nothing (and costs nothing) when
        no theme switch was missed.

        Re-themes the bubbles IN PLACE instead of calling
        _rebuild_conversation, which only knows `controller.history`: the
        bubbles that live outside the history (backend error bubble, Studio
        redirect and its buttons) are appended by the very callers that then
        end the stream — rebuilding would delete them right after showing
        them. A bubble freezes its dark/light colors at construction and has
        no re-theme API, so we swap it for an identical one built in the
        current theme, at the same position."""
        if not self._theme_catchup_pending:
            return
        self._theme_catchup_pending = False
        dark = self._is_dark_theme()
        stale = []
        for i in range(self._conv_lay.count()):
            it = self._conv_lay.itemAt(i)
            w = it.widget() if it is not None else None
            if not isinstance(w, ChatMessage) or w._dark == dark:
                continue
            # Defensive: never swap a bubble still referenced elsewhere (both
            # callers already dropped these refs, so this is a no-op there).
            if w is self._streaming_bubble or w is self._active_warning_bubble:
                continue
            stale.append((i, w))
        for i, old in stale:
            fresh = ChatMessage(
                role=old.role, text=old.text, is_error=old.is_error,
                dark_theme=dark, action=(list(old._actions) or None),
            )
            # insertWidget pushes `old` one slot further: the indexes
            # collected above stay valid as long as we remove right after.
            self._conv_lay.insertWidget(i, fresh)
            self._conv_lay.removeWidget(old)
            old.deleteLater()

    def _scroll_to_bottom(self, *, force: bool = False) -> None:
        """Requests a scroll to the bottom. If `force=True`, re-arms the auto-scroll
        even if the user had scrolled up (explicit action: send, load,
        reset, stream start). The implementation is in
        `_on_scroll_range_changed` which flushes on the next layout update
        (necessary because QTextBrowser takes several cycles to stabilize
        its height -> scrollbar.maximum() is stale just after
        insertWidget)."""
        if force:
            self._auto_scroll_pinned = True
        sb = self._scroll.verticalScrollBar()
        # Immediate attempt (case where layout already settled, range stable).
        # If maximum is stale, _on_scroll_range_changed will catch up.
        if self._auto_scroll_pinned:
            sb.setValue(sb.maximum())

    def _on_scroll_range_changed(self, _min: int, _max: int) -> None:
        """The scroll range changed -> layout was just updated.
        If we're pinned to the bottom, we follow."""
        if self._auto_scroll_pinned:
            sb = self._scroll.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_scroll_value_changed(self, value: int) -> None:
        """Scrollbar position update: if the user (or we ourselves)
        scrolled to less than 50px from the bottom, we stay pinned; otherwise we
        unpin (= the user is reading a message above, don't disturb them)."""
        sb = self._scroll.verticalScrollBar()
        self._auto_scroll_pinned = (sb.maximum() - value < 50)

    def _append_temp_bubble(self, role: str, text: str,
                              is_error: bool = False,
                              action: tuple | None = None) -> None:
        """Adds a bubble without touching controller.history (e.g.
        for heuristic redirect / off-scope responses).

        `action`: `(label, callable)` to render a button under the
        text. Used by GENERATION_REDIRECT for "Open in Studio".
        """
        bubble = ChatMessage(
            role=role, text=text,
            is_error=is_error, dark_theme=self._is_dark_theme(),
            action=action,
        )
        self._conv_lay.insertWidget(self._conv_lay.count() - 1, bubble)
        # Explicit action (user send / instant heuristic response /
        # error bubble) -> force the scroll to make it visible.
        self._scroll_to_bottom(force=True)

    def _on_send_clicked(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        # Refresh project context (live read of editor code, etc.)
        # before the LLM call.
        if self.pre_send_hook is not None:
            try:
                self.pre_send_hook()
            except Exception:
                pass   # a hook that crashes must not break the chat
        # Remembers the user text for the "Open in Studio" button
        # on GENERATION_REDIRECT bubbles (cf _handle_immediate_result).
        self._last_user_text = text
        # Append immediate user bubble (before resolve).
        self._append_temp_bubble("user", text)

        decision = self.controller.evaluate_turn(text)
        if isinstance(decision, ChatTurnResult):
            self._handle_immediate_result(decision)
            return
        # StreamingRequired -> launches the worker.
        self._start_stream(decision)

    def _answer_anyway(self, text: str) -> None:
        """« Répondre quand même » on a generation-redirect bubble: replay the
        turn with the redirect disabled.

        The user's message is NOT re-appended -- it is already in the
        conversation, above the redirect bubble; showing it twice would read
        as if he had asked twice.
        """
        decision = self.controller.evaluate_turn(text, force_answer=True)
        if isinstance(decision, ChatTurnResult):
            self._handle_immediate_result(decision)
            return
        self._start_stream(decision)

    def _handle_immediate_result(self, result: ChatTurnResult) -> None:
        """Non-streamable response (heuristic, no_backend, error).
        Displays the bubble immediately."""
        if result.kind == ChatTurnKind.GENERATION_REDIRECT:
            # "Open in Studio" button: sends the user text to the
            # parent (MainWindow) which switches to the Studio tab +
            # pre-fills the prompt field.
            s = lang_manager.current
            user_text = self._last_user_text
            self._append_temp_bubble(
                "assistant", result.text,
                action=[
                    (s.chat_open_in_studio,
                     lambda: self.open_in_atelier_requested.emit(user_text)),
                    # Échappatoire : aucune heuristique d'intention ne sera
                    # exacte sur une phrase courte, alors on rend l'erreur
                    # réparable plutôt que de courir après la précision. Sans
                    # ce bouton, une question mal classée n'était JAMAIS
                    # répondue (QA D2, 2026-08-08).
                    (s.chat_answer_anyway,
                     lambda: self._answer_anyway(user_text)),
                ],
            )
        elif result.kind == ChatTurnKind.OFFSCOPE_REFUSAL:
            self._append_temp_bubble("assistant", result.text)
        elif result.kind == ChatTurnKind.NO_BACKEND:
            self._append_temp_bubble("assistant", result.text,
                                       is_error=True)
        elif result.kind == ChatTurnKind.ERROR:
            self._append_temp_bubble("assistant", result.text,
                                       is_error=True)

    def _start_stream(self, decision: StreamingRequired) -> None:
        """Launches _StreamWorker and shows the 'writing…' indicator."""
        # No empty bubble: we first show the "writing…" indicator.
        # The real bubble is created at the 1st chunk (cf _on_chunk).
        self._show_typing_indicator()
        self._scroll_to_bottom(force=True)
        self._streaming_bubble = None
        self._streaming_user_text = decision.user_text
        self._streaming_correction_intent = getattr(
            decision, "correction_intent", False
        )
        self._last_buffer = ""
        self._rerender_pending = False
        self._clear_warning_bubble()   # safety in case a warning bubble lingered

        self._set_streaming_ui(True)

        self._worker = _StreamWorker(
            self.controller.backend,
            decision.system_prompt,
            decision.messages,
            parent=self,
        )
        self._worker.chunk_received.connect(self._on_chunk)
        self._worker.stream_finished.connect(self._on_stream_done)
        self._worker.stream_error.connect(self._on_stream_error)
        self._worker.start()
        # Soft watchdog: 2 cumulative timers (soft 60s + hard 180s)
        # since the stream started. Each chunk resets them (cf _on_chunk).
        self._stream_soft_warn_timer.start(_STREAM_SOFT_WARN_MS)
        self._stream_hard_warn_timer.start(_STREAM_HARD_WARN_MS)

    def _on_chunk(self, buffer_text: str) -> None:
        """Receives a chunk from the worker. Stores it and debounces the
        markdown re-render at ~80ms to avoid jank.

        Each chunk = sign of life from the backend -> resets the 2 warning
        timers AND removes any visible warning bubble (the model has
        resumed responding, no need to warn anymore)."""
        self._last_buffer = buffer_text
        if self._streaming_bubble is None:
            self._remove_typing_indicator()
            self._streaming_bubble = ChatMessage(
                role="assistant", text="",
                dark_theme=self._is_dark_theme(),
            )
            self._conv_lay.insertWidget(
                self._conv_lay.count() - 1, self._streaming_bubble,
            )
        self._stream_soft_warn_timer.start(_STREAM_SOFT_WARN_MS)
        self._stream_hard_warn_timer.start(_STREAM_HARD_WARN_MS)
        self._clear_warning_bubble()
        if self._rerender_pending:
            return
        self._rerender_pending = True
        QTimer.singleShot(80, self._do_rerender)

    def _on_stream_soft_warn(self) -> None:
        """Soft watchdog (60s without a chunk): non-blocking warning
        bubble. The user can wait or click Stop. NO auto-kill (the model
        may just be thinking for a long time)."""
        if self._worker is None:
            return
        self._show_warning_bubble(
            lang_manager.current.chat_stream_soft_warn
        )

    def _on_stream_hard_warn(self) -> None:
        """Hard watchdog (180s without a chunk): 2nd more insistent bubble,
        replaces the soft one. Still no auto-kill -- the user decides via
        Stop. As a last resort, the backend has its own timeouts (Claude
        CLI 120s, Ollama 300s, HTTP API 120s)."""
        if self._worker is None:
            return
        self._show_warning_bubble(
            lang_manager.current.chat_stream_hard_warn
        )

    def _show_typing_indicator(self) -> None:
        """Inserts the 'writing…' indicator before the 1st chunk."""
        self._remove_typing_indicator()
        self._typing_indicator = _TypingIndicator(dark=self._is_dark_theme())
        self._conv_lay.insertWidget(
            self._conv_lay.count() - 1, self._typing_indicator,
        )
        self._typing_indicator.start()
        self._scroll_to_bottom(force=True)

    def _remove_typing_indicator(self) -> None:
        if self._typing_indicator is not None:
            self._typing_indicator.stop()
            self._typing_indicator.deleteLater()
            self._typing_indicator = None

    def _show_warning_bubble(self, text: str) -> None:
        """Shows a non-blocking warning under the stream bubble.
        Replaces the previous warning if there is one. Auto-removed at the
        next chunk or at the end of the stream (cf _clear_warning_bubble).
        Text expected in italic markdown for a rendering visually distinct
        from a real assistant response."""
        self._clear_warning_bubble()
        bubble = ChatMessage(
            role="assistant", text=text,
            is_error=False, dark_theme=self._is_dark_theme(),
        )
        self._conv_lay.insertWidget(self._conv_lay.count() - 1, bubble)
        self._active_warning_bubble = bubble
        self._scroll_to_bottom(force=True)

    def _clear_warning_bubble(self) -> None:
        """Removes the active warning bubble if it exists."""
        if self._active_warning_bubble is not None:
            self._active_warning_bubble.deleteLater()
            self._active_warning_bubble = None

    def _do_rerender(self) -> None:
        self._rerender_pending = False
        if self._streaming_bubble is None:
            return
        self._streaming_bubble.update_text(self._last_buffer)
        self._scroll_to_bottom()

    def _on_stream_done(self, full_text: str) -> None:
        """Stream finished normally (incl. after stop). If full_text is
        empty (stop before the 1st chunk), removes the empty assistant
        bubble. Otherwise forces a last synchronous re-render + commits history.

        F2-5 net: if a correction is armed (_pending_correction) and the
        model concluded with `CORRECTION: <id>`, the marker is stripped
        from the displayed text and a redirect bubble to the Studio is
        added (same mechanism as the generation redirect)."""
        self._stream_soft_warn_timer.stop()
        self._stream_hard_warn_timer.stop()
        self._clear_warning_bubble()
        self._remove_typing_indicator()
        if not full_text.strip():
            if self._streaming_bubble is not None:
                self._streaming_bubble.deleteLater()
            self._teardown_stream()
            return

        marker = None
        if self._pending_correction is not None:
            from .correction import parse_correction_marker
            marker = parse_correction_marker(full_text)

        display_text = full_text
        if marker is not None:
            from .correction import strip_correction_marker
            display_text = strip_correction_marker(full_text)

        if self._streaming_bubble is not None:
            self._streaming_bubble.update_text(display_text)
            self._scroll_to_bottom()
        self.controller.commit_streamed_turn(
            self._streaming_user_text, display_text,
        )
        self.history_changed.emit()

        if marker is not None:
            self._append_correction_redirect(marker)

        # Sub-project 2: correction intent detected in the free chat
        # -> additive button. Removed if an armed net session is in progress
        # (the net already handles its own redirect via the marker).
        if self._streaming_correction_intent and self._pending_correction is None:
            self._append_correction_studio_offer(self._streaming_user_text)

        self._teardown_stream()

    def _append_correction_redirect(self, marker) -> None:
        """Bulle de redirection vers le Studio (filet « mauvais composant ») :
        message court + bouton qui ouvre le flux Modifier pré-staged avec un
        seed nommant le vrai composant + sa broche (sans préfixe CORRECTION)."""
        from .correction import human_component_name, build_modify_seed
        s = lang_manager.current
        ctx = self._pending_correction or {}
        seed = build_modify_seed(ctx.get("pins", ""), marker)
        name = human_component_name(marker)
        self._append_temp_bubble(
            "assistant",
            s.chat_correction_redirect.format(name=name),
            action=(
                s.chat_correction_to_studio,
                lambda: self._on_modify_to_studio_clicked(seed),
            ),
        )

    def _append_correction_studio_offer(self, user_text: str) -> None:
        """Bulle additive (chat libre) : la réponse normale est déjà affichée,
        on ajoute un message + bouton qui amène le texte de l'élève dans le
        Studio et ouvre le flux Modifier (sans préfixe). N'identifie pas un
        composant précis : on route les mots bruts de l'élève."""
        s = lang_manager.current
        self._append_temp_bubble(
            "assistant",
            s.chat_correction_studio_offer,
            action=(
                s.chat_correction_to_studio,
                lambda: self.request_modify_in_studio.emit(user_text),
            ),
        )

    def _on_modify_to_studio_clicked(self, seed: str) -> None:
        """Ouvre le flux Modifier pré-staged dans le Studio puis désarme le
        filet de correction en cours."""
        self.request_modify_in_studio.emit(seed)
        self._pending_correction = None
        self.controller.system_extras_sticky = ""

    def _on_stream_error(self, error_message: str,
                          partial_text: str) -> None:
        self._stream_soft_warn_timer.stop()
        self._stream_hard_warn_timer.stop()
        self._clear_warning_bubble()
        self._remove_typing_indicator()
        if partial_text.strip() and self._streaming_bubble is not None:
            # Commit the partial then add a separate error bubble.
            self._streaming_bubble.update_text(partial_text)
            self.controller.commit_streamed_turn(
                self._streaming_user_text, partial_text,
            )
            self.history_changed.emit()
        else:
            # No partial: remove the empty bubble created at send.
            if self._streaming_bubble is not None:
                self._streaming_bubble.deleteLater()
        self._append_temp_bubble(
            "assistant",
            self._friendly_backend_error(error_message),
            is_error=True,
        )
        self._teardown_stream()

    def _friendly_backend_error(self, raw: str) -> str:
        """Translates a raw backend error into a user-readable message.

        Backend exceptions (subprocess.CalledProcessError, raw stderr,
        RuntimeError("Package X non installe"), urllib URLError,
        Anthropic/Gemini SDK errors) are generally technical and
        cropped -- uninterpretable for a student. Here we detect common
        patterns and return a clear message in FR. The raw text is kept
        as a short suffix if not recognized.
        """
        # Backend raises its own timeout (Claude CLI 120s, etc.) or a
        # network timeout surfaces a clearly identifiable exception.
        # The soft watchdog Fix 7 does NOT lead here (it no longer auto-kills).
        low = raw.lower()
        s = lang_manager.current

        # Watchdog / backend timeout (network, slow model).
        if ("timeout" in low or "timed out" in low
                or "n'a pas repondu" in low or "delai imparti" in low):
            return s.chat_backend_timeout

        # Invalid / unknown MODEL (distinct from a missing backend): the
        # adapter reports e.g. "Modèle ou URL introuvable…" on a 404. Checked
        # FIRST so a model typo doesn't get mislabeled as a missing backend.
        if (("modèle" in low or "modele" in low or "model" in low)
                and ("introuvable" in low or "not found" in low
                     or "404" in low or "invalid" in low
                     or "does not exist" in low)):
            return (
                "Le modèle sélectionné est invalide ou introuvable. "
                "Vérifie-le dans l'onglet « Modèle IA »."
            )

        # Backend not found (claude CLI not installed, package not
        # installed, ollama not running).
        if ("introuvable" in low or "not found" in low
                or "non installé" in low or "non installe" in low
                or "no such" in low):
            return (
                "Le backend IA est introuvable ou non configuré. "
                "Vérifie l'onglet « Modèle IA »."
            )

        # API key / authentication.
        if ("api key" in low or "api_key" in low or "apikey" in low
                or "clé api" in low or "cle api" in low
                or "unauthorized" in low or "401" in low
                or "invalid_request_error" in low):
            return "Vérifie la clé API dans l'onglet « Modèle IA »."

        # Quota / rate limit.
        if ("quota" in low or "rate limit" in low or "rate_limit" in low
                or "429" in low or "too many requests" in low):
            return (
                "Limite de quota atteinte. Réessaye plus tard ou change "
                "de backend."
            )

        # Ollama: local server not running. Port 11434 = strong
        # signature (= always Ollama, never another service). Otherwise
        # detection via "ollama" + a sign of failed connection
        # (OllamaBackend re-raises with "Ollama n'est pas lance" in the
        # RuntimeError message, so we match that too).
        if "11434" in low or (
                "ollama" in low and (
                    "n'est pas lancé" in low or "n'est pas lance" in low
                    or "connection refused" in low
                    or "ne repond pas" in low)):
            return (
                "Ollama n'est pas accessible. Vérifie qu'il est lancé "
                "(commande : ollama serve)."
            )

        # Anthropic: 5xx / server-side overload (529 specific to
        # Anthropic = overloaded). Different from the quota (429) which is on
        # your account, and from the API key (401) which is on auth.
        if "anthropic" in low and (
                "overload" in low or "500" in low or "502" in low
                or "503" in low or "504" in low or "529" in low
                or "service unavailable" in low
                or "internal server error" in low):
            return (
                "Le serveur Anthropic est en panne ou surchargé. "
                "Réessaye plus tard ou change de backend."
            )

        # Generic AI server down (Gemini, other). Same patterns as
        # Anthropic but without the "anthropic" filter -- placed after
        # so as not to mask the dedicated Anthropic message.
        if ("overload" in low or "service unavailable" in low
                or "internal server error" in low
                or "500" in low or "502" in low
                or "503" in low or "504" in low):
            return (
                "Le serveur du backend IA est en panne ou surchargé. "
                "Réessaye plus tard ou change de backend."
            )

        # Network / server unavailable (generic case, fallback after
        # the specific Ollama/5xx detections above).
        if ("urlerror" in low or "connection refused" in low
                or "connection reset" in low or "name or service"
                in low or "getaddrinfo" in low or "n'est pas accessible"
                in low or "ne repond pas" in low):
            return (
                "Impossible de joindre le backend IA (réseau coupé ou "
                "serveur indisponible). Vérifie ta connexion ou la "
                "configuration du backend."
            )

        # Claude Code subprocess stopped without a message (cancel + crash).
        if ("claude.exe" in low or "claude.cmd" in low
                or "claude code s'est arrete" in low
                or "command '['" in low):
            return "Vérifie ta connexion internet."

        # Fallback: short message + truncated to 200 chars max.
        short = raw.strip()
        if len(short) > 200:
            short = short[:197] + "…"
        return f"Erreur du backend IA : {short}"

    def _on_stop_clicked(self) -> None:
        if self._worker is None:
            return
        self._worker.request_stop()
        # For blocking subprocesses (Claude Code CLI), we call
        # backend.cancel() to terminate the child process -- otherwise the
        # cooperative flag is never read and the subprocess continues
        # until its native timeout (~2 min). Streaming backends
        # (Anthropic/Gemini/Ollama) break at the next chunk (<1s).
        backend = self.controller.backend
        if backend is not None:
            try:
                backend.cancel()
            except Exception:
                pass
        self._stream_soft_warn_timer.stop()
        self._stream_hard_warn_timer.stop()
        self._clear_warning_bubble()
        self._remove_typing_indicator()
        # ─── INSTANT stop (UI rendered right away) ───────────────
        # We freeze + commit the partial already received, then DETACH the
        # worker (its UI callbacks are cut, it finishes in the background). This
        # way the input + the attach button are reactivated IMMEDIATELY, without
        # waiting for the worker's actual exit, and without risk of a double
        # commit / error bubble (its signals no longer re-enter).
        partial = self._last_buffer
        if partial.strip() and self._streaming_bubble is not None:
            self._streaming_bubble.update_text(partial)
            self.controller.commit_streamed_turn(
                self._streaming_user_text, partial,
            )
            self.history_changed.emit()
        elif self._streaming_bubble is not None:
            # No content received: remove the empty bubble.
            self._streaming_bubble.deleteLater()
        self._streaming_bubble = None
        self._streaming_user_text = ""
        self._detach_worker()
        self._set_streaming_ui(False)
        self._input.setFocus()
        # Stop does NOT go through _teardown_stream (it detaches the worker
        # instead of waiting for it), so the postponed theme is caught up here
        # too — same end of stream for the user.
        self._catch_up_theme_after_stream()

    def _detach_worker(self) -> None:
        """Detaches the current worker: cuts its UI callbacks and lets it
        finish in the background (request_stop/cancel already emitted before
        the call). Lets us reactivate the UI immediately. The worker is kept
        referenced until its `finished` signal (avoids a GC while the thread
        is running), then `deleteLater`."""
        w = self._worker
        self._worker = None
        if w is None:
            return
        for sig in (w.chunk_received, w.stream_finished, w.stream_error):
            try:
                sig.disconnect()
            except TypeError:
                pass   # no connection -> nothing to cut
        self._detached_workers.append(w)

        def _reap() -> None:
            try:
                self._detached_workers.remove(w)
            except ValueError:
                pass
            w.deleteLater()

        w.finished.connect(_reap)

    def _teardown_stream(self) -> None:
        """Reset UI after the stream ends (success, stop or error).
        Stops the warning timers + removes any warning bubble as a
        safety (the callers _on_stream_done/error already do it but we
        keep a defensive redundancy)."""
        self._stream_soft_warn_timer.stop()
        self._stream_hard_warn_timer.stop()
        self._clear_warning_bubble()
        self._remove_typing_indicator()   # defensive: no direct path,
        # but avoids a leak if teardown is called without going through done/error
        if self._worker is not None:
            self._worker.wait(2000)   # max 2s, avoids a zombie thread
            self._worker.deleteLater()
            self._worker = None
        self._streaming_bubble = None
        self._streaming_user_text = ""
        self._streaming_correction_intent = False
        self._set_streaming_ui(False)
        self._input.setFocus()
        # A theme switch made during the stream was postponed: apply it now
        # that no bubble is referenced anymore.
        self._catch_up_theme_after_stream()

    def _on_reset_clicked(self) -> None:
        if not self.controller.history:
            return
        s = lang_manager.current
        if not ask_yes_no(self, s.chat_new_conversation,
                          s.chat_new_conversation + " ?"):
            return
        self.controller.reset()
        self._pending_correction = None
        self._rebuild_conversation()
        # The shared context file is tied to the PROJECT, not the
        # conversation: we don't remove it when starting over (the chip stays,
        # driven by set_project_context).
        self.history_changed.emit()

    def load_project_history(self, history: list[dict]) -> None:
        """Loads a project's history and refreshes the UI."""
        self.controller.load_history(history)
        self._pending_correction = None
        self._rebuild_conversation()

    def _on_board_changed(self, env: str, model: str) -> None:
        """Updates the controller's current board (board_manager signal)."""
        self.controller.board_model = model

    def set_project_context(self,
                              *,
                              code: str = "",
                              wiring_summary: list[str] | None = None,
                              original_prompt: str = "",
                              user_material: str = "",
                              context_name: str = "",
                              last_compile_error: str = "") -> None:
        """Updates the controller's project context. To be called by
        MainWindow when the current project or its code changes.

        `user_material` carries the content of the shared context file and
        `context_name` its name: the chat chip reflects this same file (also
        visible in the prompt badge)."""
        self.controller.code = code
        self.controller.wiring_summary = wiring_summary or []
        self.controller.original_prompt = original_prompt
        self.controller.user_material = user_material
        self.controller.last_compile_error = last_compile_error
        self._set_attachment_chip(context_name)

    def set_backend(self,
                     backend: Optional["object"]) -> None:
        """Changes the controller's backend (when switching in AI Model)."""
        self.controller.backend = backend
        self._refresh_input_state()

    def _refresh_input_state(self) -> None:
        """Enables/disables the input depending on whether the controller has a backend."""
        has_backend = self.controller.backend is not None
        self._input.setEnabled(has_backend)
        self._attach_btn.setEnabled(has_backend)
        self._refresh_model_label()
        s = lang_manager.current
        if has_backend:
            # Rotating tips (the placeholder is only visible when the field is empty).
            self._tips.start()
        else:
            self._tips.stop()
            self._input.setPlaceholderText(s.chat_no_backend)

    def _set_streaming_ui(self, active: bool) -> None:
        """Toggles the UI between idle and streaming: Stop visible + input/attach
        disabled during the stream. Replaces the old send/stop toggle."""
        self._stop_btn.setVisible(active)
        self._input.setEnabled(not active)
        self._attach_btn.setEnabled(not active)

    def _refresh_model_label(self) -> None:
        b = self.controller.backend
        name = getattr(b, "name", None) if b is not None else None
        self._model_lbl.setText(name or lang_manager.current.chat_no_model_label)

    def _on_attach_clicked(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        s = lang_manager.current
        path, _ = QFileDialog.getOpenFileName(
            self, s.chat_attach_tooltip, "",
            "Texte (*.txt *.md *.ino *.cpp *.c *.h *.csv *.log)",
        )
        if not path:
            return
        # Routing to the project's shared context: it's StudioView that
        # reads/copies the file and re-pushes the chip via set_project_context.
        self.attach_file_requested.emit(path)

    def _set_attachment_chip(self, name: str) -> None:
        """Reflects the shared context file in the chip (driven by
        set_project_context). Empty `name` -> chip hidden. The label is
        truncated (…) to a max width so as not to distort the toolbar; full
        name in the tooltip."""
        if name:
            from PyQt6.QtGui import QFontMetrics
            fm = QFontMetrics(self._chip_lbl.font())
            self._chip_lbl.setText(
                fm.elidedText(f"📄 {name}", Qt.TextElideMode.ElideRight,
                              _CHIP_LABEL_MAX_W))
            self._chip_lbl.setToolTip(name)
            self._attach_chip.setVisible(True)
        else:
            self._chip_lbl.setText("")
            self._chip_lbl.setToolTip("")
            self._attach_chip.setVisible(False)

    def _clear_attachment(self) -> None:
        # The chip's ✕ removes the SHARED context file: we route it to
        # StudioView (badge + chip disappear together). Immediate hiding
        # for responsiveness; the source of truth stays the project.
        self._attach_chip.setVisible(False)
        self.detach_file_requested.emit()

    # ── Drag & drop over the WHOLE chat window ─────────────────────────
    # Events not captured by a child (user QLabel bubbles, scroll, margins)
    # bubble up to here; dropping a single local file attaches it as
    # shared context, wherever it's dropped in the panel.

    def dragEnterEvent(self, event):  # type: ignore[override]
        if _single_local_file_path(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # type: ignore[override]
        if _single_local_file_path(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # type: ignore[override]
        path = _single_local_file_path(event)
        if path is not None:
            event.acceptProposedAction()
            self.attach_file_requested.emit(path)
            return
        super().dropEvent(event)

    def set_user_mode(self, user_mode: str) -> None:
        """Changes the controller's user mode."""
        self.controller.user_mode = user_mode

    def preload(self, prefix_text: str,
                *, system_extras: str = "",
                focus_input: bool = True) -> None:
        """Pre-fills the input field (visible to the user, editable before
        Send) and optionally injects an additional context block into the
        system prompt of the next LLM turn (invisible, not persisted in
        chat_history).

        Used by the contextual bridges (F2 step 4) to bring the user into
        the chat with their question already phrased and the relevant
        technical context (code, error, ambiguity) already anchored on the
        model side.

        prefix_text: visible text placed in the send field. The user can
            edit/complete it before Send.
        system_extras: structured context added to the system prompt of the
            NEXT LLM turn only. Consumed after injection.
        focus_input: gives focus to the input field (default True).
        """
        # Any new preload (classic "?" bridge) cancels a possibly armed
        # but abandoned correction (F2-5 net).
        self._pending_correction = None
        self.controller.system_extras_sticky = ""
        self._input.setPlainText(prefix_text)
        cursor = self._input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self.controller.system_extras_once = system_extras
        if focus_input:
            self._input.setFocus()

    def preload_correction(self, prefix_text: str, *,
                            system_extras: str = "",
                            correction_context=None) -> None:
        """Like preload, but arms the MULTI-TURN correction net: the
        contract is injected on EVERY turn (sticky) as long as the correction
        is not resolved/reset, and every assistant message is scanned for a
        CORRECTION: marker at the end of the stream (cf _on_stream_done).

        The field is pre-filled with a simple REFERENCE to the component (e.g.
        "Composant D1 (servo) : ") and focus is given: the user writes their
        question after the "： " then sends it themselves (no automatic
        send)."""
        self.preload(prefix_text, system_extras="", focus_input=True)
        self.controller.system_extras_sticky = system_extras
        self._pending_correction = correction_context
