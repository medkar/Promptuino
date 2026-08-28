"""Journal de compilation/upload enrichi (extrait de studio_view.py,
Prompt 1 du plan PATHFINDER-2026-07-05).

`phase_div_html` / `phase_title_html` factorisent le bloc HTML « phase »
(padding + barre latérale colorée) qui était dupliqué 4× dans LogWidget et
2× dans studio_view (_tick_loader, _stop_gen_loader_ready)."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCursor, QTextCharFormat
from PyQt6.QtWidgets import (
    QPushButton, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

from ..fonts import MONO_CSS
from ..i18n import Strings, lang_manager
from ..theme import ColorScheme, theme_manager


def phase_div_html(inner: str, color: str) -> str:
    """Bloc « phase » du journal : padding + barre latérale 3px `color`.
    `inner` est du HTML déjà échappé."""
    return (f'<div style="padding: 4px 10px; margin: 0; '
            f'border-left: 3px solid {color};">{inner}</div>')


def phase_title_html(title: str, color: str) -> str:
    """Variante titre (gras 10pt coloré) — begin_phase, bannières ✓/✗,
    « Code prêt »."""
    return phase_div_html(
        f'<b style="font-size: 10pt; color: {color};">{title}</b>', color)


class LogWidget(QWidget):
    """
    Enriched compile/upload log.
    - Colored separators between phases (Compilation, Upload, Correction…)
    - Automatic coloring of errors (red), warnings (orange),
      raw text (discreet gray)
    """

    # F2 step 4 — contextual "?" bridge: emitted when the user clicks
    # the "Demander de l'aide sur cette erreur" button that appears
    # after a set_done(False, message). Payload = raw error text.
    help_with_error_requested = pyqtSignal(str)
    # Emitted when the user clicks an action link inserted in the log
    # (e.g. « voir les corrections automatiques »). Payload = link href.
    action_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._muted_color = "#888888"
        self._last_error_text: str = ""
        # Anchor position of a « live line » (animated loader updated in
        # place, cf. set_live_line). None = no live line in progress.
        self._live_anchor: int | None = None
        self._auto_scroll = True   # driven by the « défilement auto » checkbox
        self._bottom_overlay = None   # fixed control strip at the bottom of the log
        # The frame (border + background) is carried by THE WIDGET (not the QTextEdit):
        # this way the scrolling text area AND the fixed control strip both live
        # INSIDE the frame, and the strip is not part of the scrolling.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._build()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        # Refresh the error-help button label on a language change.
        lang_manager.changed.connect(self._apply_lang)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # "Demander de l'aide sur cette erreur" button — hidden by default,
        # revealed only when set_done(False, message) is called.
        # Placed at the top of the widget to stay visible even if the output
        # scrolls at the bottom.
        self._help_btn = QPushButton(
            lang_manager.current.chat_help_error_button
        )
        self._help_btn.setVisible(False)
        self._help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._help_btn.clicked.connect(self._on_help_clicked)
        layout.addWidget(self._help_btn)

        # « voir les corrections automatiques » button — hidden by default,
        # revealed after a compilation that triggered auto repairs.
        # Stays visible after the upload (consultable on demand).
        self._repairs_btn = QPushButton()
        self._repairs_btn.setVisible(False)
        self._repairs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._repairs_btn.clicked.connect(
            lambda: self.action_clicked.emit("repairs")
        )
        layout.addWidget(self._repairs_btn)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._text, stretch=1)

    # ── Fixed control strip (bottom of the log, outside scrolling) ─

    def set_bottom_bar(self, widget):
        """Add `widget` as a FIXED strip at the bottom of the log, BELOW the
        scrolling text area. This strip is NOT in the QTextEdit: only the area
        above scrolls. The log frame (border carried by the widget)
        encloses the text AND the strip -> the log stays bottom-aligned with
        the editor, but the scroll covers only the text."""
        self._bottom_overlay = widget
        if widget.layout() is not None:
            # Reduced margins to leave max room for the serial controls
            # (everything must fit on one line, « Baud » label included).
            widget.layout().setContentsMargins(4, 5, 4, 7)
        self.layout().addWidget(widget)

    # ── Public API ──────────────────────────────────────────

    def clear(self):
        self._text.clear()
        # F2 step 4: reset the error-help button on each new cycle.
        self._help_btn.setVisible(False)
        # Reset the « corrections automatiques » button (new compile cycle).
        self._repairs_btn.setVisible(False)
        self._last_error_text = ""
        self._live_anchor = None

    def hide_actions(self):
        """Hide the action buttons (error-help, corrections) WITHOUT touching the
        log text — to add a message below the existing one (e.g. a
        pre-flight error below « Code prêt »), without clearing everything or leaving a
        stale button."""
        self._help_btn.setVisible(False)
        self._repairs_btn.setVisible(False)
        self._last_error_text = ""

    def set_live_line(self, html: str):
        """Display/UPDATE IN PLACE a single « live line » at the bottom of the
        log (an animated loader, e.g.): the 1st call anchors it, the following
        ones replace its content without stacking lines. Use only when
        nothing else writes to the log at the same time (otherwise the anchor
        comes loose). `commit_live_line` freezes it; `clear_live_line` removes it."""
        cursor = self._text.textCursor()
        if self._live_anchor is None:
            cursor.movePosition(QTextCursor.MoveOperation.End)
            if not self._text.document().isEmpty():
                cursor.insertBlock()          # fresh line for the live line
            self._live_anchor = cursor.position()
        cursor.setPosition(self._live_anchor)
        cursor.movePosition(QTextCursor.MoveOperation.End,
                            QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertHtml(html)
        self._scroll_bottom()

    def commit_live_line(self):
        """Freeze the live line (it becomes permanent content; the next
        begin_phase/append will be added AFTER)."""
        self._live_anchor = None

    def clear_live_line(self):
        """Remove the live line from the log (no-op if there is none)."""
        if self._live_anchor is None:
            return
        cursor = self._text.textCursor()
        cursor.setPosition(self._live_anchor)
        cursor.movePosition(QTextCursor.MoveOperation.End,
                            QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self._live_anchor = None

    def begin_phase(self, title: str, color: str = "#3b82f6"):
        """Insert a visual phase separator into the log."""
        if not self._text.document().isEmpty():
            self._insert_newline()
        self._insert_html(phase_title_html(title, color))
        self._scroll_bottom()

    def append_raw(self, text: str):
        """Append the raw output with automatic line coloring."""
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            ll = stripped.lower()
            if "error:" in ll or "erreur" in ll:
                color, weight = "#ef4444", "600"
            elif "warning:" in ll or "avertissement" in ll:
                color, weight = "#f59e0b", "normal"
            else:
                color, weight = self._muted_color, "normal"
            esc = (stripped
                   .replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;"))
            self._insert_html(
                f'<div style="font-family: Consolas, monospace; font-size: 9pt; '
                f'color: {color}; font-weight: {weight}; margin: 0; line-height: 1.4;">'
                f'{esc}</div>'
            )
        self._scroll_bottom()

    def show_repairs_action(self, label: str):
        """Reveal the « voir les corrections automatiques » button with `label`.
        The click emits `action_clicked("repairs")`."""
        self._repairs_btn.setText(label)
        self._repairs_btn.setVisible(True)

    def append_serial(self, text: str):
        """Append serial data into the SAME console as the compile
        log (merged STDOUT, spec Phase 3 §5).

        Insert the RAW stream while preserving line breaks via
        insertText (≠ append_raw which colorizes the build with one <div> per line).
        The serial stream arrives in chunks NOT aligned on lines: wrapping
        each chunk in a <div> broke `println` (end of line lost /
        concatenated fragments). insertText naturally re-glues the fragments and
        a \\n creates a new block. We normalize the Arduino line endings
        (\\r\\n, \\r) to \\n to avoid stray characters."""
        norm = text.replace("\r\n", "\n").replace("\r", "\n")
        sb = self._text.verticalScrollBar()
        saved = sb.value()
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._muted_color))
        fmt.setFontFamilies(["Consolas", "monospace"])
        fmt.setFontPointSize(9)
        cursor.insertText(norm, fmt)
        if self._auto_scroll:
            sb.setValue(sb.maximum())
        else:
            sb.setValue(saved)

    def begin_serial_section(self, title: str, color: str):
        """Separate the compile/upload log from the serial output (Phase 3 §5) with
        a phase header, SAME style as begin_phase / set_done (10 pt bold +
        left bar) but a dedicated color. Preceded by an EMPTY LINE to
        detach it clearly, then the serial starts on a fresh line (otherwise its 1st
        character would attach to the end of the header)."""
        if not self._text.document().isEmpty():
            self._insert_newline()   # terminate the current line
            self._insert_newline()   # empty line = visual gap before the header
        self._insert_html(phase_title_html(title, color))
        self._insert_newline()
        self._scroll_bottom()

    def append_explanation(self, text: str):
        """Display an AI explanation in natural language (non-monospace, readable)."""
        if not text.strip():
            return
        esc = (text.strip()
               .replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
               .replace("\n", "<br>"))
        self._insert_html(
            f'<div style="font-size: 9pt; color: {self._muted_color}; '
            f'margin: 4px 0; line-height: 1.6;">{esc}</div>'
        )
        self._scroll_bottom()

    def set_done(self, success: bool, label: str = ""):
        """Add a result banner at the end of the log on success.

        F2 step 4: on failure with a non-empty message, expose the
        "Demander de l'aide sur cette erreur" button that lets the student
        relay the error text to the AI chat.
        """
        if success and label:
            ok = theme_manager.current.signal_ok   # « ça marche » = phosphor (spec §1)
            self._insert_newline()
            self._insert_html(phase_title_html(f"✓ {label}", ok))
            self._scroll_bottom()
            # Success: make sure the error-help button is hidden.
            self._help_btn.setVisible(False)
            self._last_error_text = ""
        elif not success and label:
            # Failure with a message: make the button accessible and
            # store the error text for the contextual bridge.
            self._last_error_text = label
            self._help_btn.setVisible(True)

    def set_failed(self, label: str):
        """Explicit failure banner (red ✗) at the end of the log. Symmetric
        with the success banner: without it, a failed upload showed only the
        (NL) explanation, which — combined with the serial monitor reconnecting
        and the OLD firmware still printing — looked like a success."""
        if not label:
            return
        err = theme_manager.current.signal_error
        self._insert_newline()
        self._insert_html(phase_title_html(f"✗ {label}", err))
        self._scroll_bottom()

    def _on_help_clicked(self):
        """User click on "Demander de l'aide sur cette erreur":
        relays the last error text to StudioView via signal."""
        if self._last_error_text:
            self.help_with_error_requested.emit(self._last_error_text)

    def _apply_lang(self, s: Strings):
        """Refresh the button label on a language change."""
        self._help_btn.setText(s.chat_help_error_button)

    def apply_theme(self, c: ColorScheme):
        self._muted_color = c.text_secondary
        # The FRAME (code_bg background spec §3 + border + radius) is on the widget,
        # not on the QTextEdit: the fixed control strip (set_bottom_bar) thus lives
        # INSIDE the frame, below the scrolling area.
        self.setStyleSheet(f"""
            LogWidget {{
                background-color: {c.code_bg};
                border: 1px solid {c.border};
                border-radius: 6px;
            }}
        """)
        # QTextEdit: transparent and borderless (the frame is carried by the
        # widget). This is the ONLY scrolling area.
        self._text.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                color: {c.text_primary};
                border: none;
                padding: 6px 8px;
                font-family: {MONO_CSS};
                font-size: 10pt;
            }}
        """)
        # Log action buttons (« voir les corrections », « demander de l'aide »):
        # styled by theme.log_action_button_qss via the `logAction` variant, so
        # the theme change is handled by the application sheet.
        for b in (self._repairs_btn, self._help_btn):
            b.setProperty("variant", "logAction")

    # ── Helpers ───────────────────────────────────────────────

    def set_auto_scroll(self, on: bool):
        """Auto-scroll of the merged console (driven by the
        « défilement auto » checkbox of the serial monitor, Phase 3 §5). Unchecked: the view
        stays frozen even when new lines (compile OR serial) arrive,
        to re-read history. Re-checked: jump to the bottom immediately."""
        self._auto_scroll = on
        if on:
            self._scroll_bottom()

    def _insert_newline(self):
        sb = self._text.verticalScrollBar()
        saved = sb.value()
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text.setTextCursor(cursor)
        cursor.insertText("\n")
        if not self._auto_scroll:
            sb.setValue(saved)

    def _insert_html(self, html: str):
        sb = self._text.verticalScrollBar()
        saved = sb.value()
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text.setTextCursor(cursor)
        self._text.insertHtml(html)
        if not self._auto_scroll:
            sb.setValue(saved)

    def _scroll_bottom(self):
        if not self._auto_scroll:
            return
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())
