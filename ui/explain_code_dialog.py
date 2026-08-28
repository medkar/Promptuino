"""
"Explain selected lines" dialog (AI tool of the Tools panel).

Layout:
  ┌─────────────────────────────────────────────────────────┐
  │ Code                           │ Explication           │
  │ ┌───────────────────────────┐  │ ┌────────────────────┐│
  │ │ code editable + selection │  │ │ reponse IA / hint  ││
  │ └───────────────────────────┘  │ └────────────────────┘│
  │                                                        │
  │                [Expliquer]              [Fermer]       │
  └─────────────────────────────────────────────────────────┘

The user can edit the code and change the selection, then re-run
the analysis via "Expliquer". No change is propagated to the
main editor — this dialog is an isolated scratchpad.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QEvent, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QFont, QPalette, QColor, QTextBlockFormat, QTextCharFormat, QTextCursor,
)
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QTextEdit, QSizePolicy, QStackedWidget, QWidget,
)

from .code_editor import CodeEditor, ArduinoHighlighter
from .i18n import lang_manager, Strings
from .robot_loader import RobotLoader, LoaderLabel
from .theme import (
    ColorScheme, theme_manager, primary_button_qss, secondary_button_qss,
)


class _MarkdownCodeHighlighter(ArduinoHighlighter):
    """Applies Arduino/C++ coloring + bold ONLY to the fragments
    in monospace font produced by `QTextEdit.setMarkdown()`: this
    covers both the fenced code blocks (```...```) AND the inline
    backticks (`code`) buried in an explanation paragraph.

    The explanatory text stays unchanged. Syntax coloring is
    applied fragment by fragment: we extract the monospace range,
    set it to bold, then apply to it the regex rules inherited
    from ArduinoHighlighter with the correct offset.
    """

    # List of monospace fonts ordered by preference. "Consolas" exists
    # on Windows/Office, "Menlo" on macOS, "DejaVu Sans Mono" on
    # most Linux. The last entry is a generic hint.
    _MONO_FAMILIES = [
        "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New", "monospace",
    ]

    def highlightBlock(self, text: str):
        if not text:
            return
        block = self.currentBlock()
        it = block.begin()
        bold = QTextCharFormat()
        bold.setFontFamilies(self._MONO_FAMILIES)
        bold.setFontWeight(QFont.Weight.Bold)
        while not it.atEnd():
            frag = it.fragment()
            it += 1
            if not frag.charFormat().fontFixedPitch():
                continue
            # Offset of the fragment within the block: QTextFragment.position()
            # is absolute to the document, we subtract the block position.
            start = frag.position() - block.position()
            length = frag.length()
            frag_text = text[start:start + length]
            # 1) Bold over the whole code range (inline or fenced). We
            # also force the monospace family: on some systems,
            # the default font chosen by setMarkdown has no
            # visible bold variant (Courier New notably).
            self.setFormat(start, length, bold)
            # 2) Syntax coloring via the ArduinoHighlighter rules,
            # mapped with the fragment offset.
            for pattern, fmt in self._rules:
                for m in pattern.finditer(frag_text):
                    g = 1 if pattern.groups else 0
                    sub_start = start + m.start(g)
                    sub_len = m.end(g) - m.start(g)
                    merged = QTextCharFormat(fmt)
                    merged.setFontFamilies(self._MONO_FAMILIES)
                    merged.setFontWeight(QFont.Weight.Bold)
                    self.setFormat(sub_start, sub_len, merged)


class _ExplainWorker(QThread):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, backend, code: str, selection: str,
                 language: str, board_name: str):
        super().__init__()
        self._backend    = backend
        self._code       = code
        self._selection  = selection
        self._language   = language
        self._board_name = board_name

    def run(self):
        try:
            text = self._backend.explain_code(
                self._code, self._selection, self._language, self._board_name,
            )
            self.finished.emit(text)
        except Exception as e:
            self.error.emit(str(e))


class ExplainCodeDialog(QDialog):
    """2-column modal dialog for the "Explain lines" tool.

    Args:
        backend : AIBackend instance (must be is_available()).
        code : current content of the Studio editor.
        selection : text selected in the editor (empty if nothing).
        board_name : name of the current board ("Arduino Uno" for ex.).
    """

    def __init__(self, backend, code: str, selection: str, board_name: str,
                 parent=None):
        super().__init__(parent)
        self._backend = backend
        self._board_name = board_name
        self._worker: _ExplainWorker | None = None
        self._initial_selection = selection

        self.setModal(True)
        self.setMinimumSize(900, 520)
        self._build(code, selection)
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

        # Automatically triggers the analysis if a selection already exists —
        # the user sees the response without any additional action.
        if selection.strip():
            self._trigger_explain()

    # ── Construction ─────────────────────────────────────────────
    def _build(self, code: str, selection: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        cols = QHBoxLayout()
        cols.setSpacing(12)
        root.addLayout(cols, stretch=1)

        # ── Left column: editable code ───────────────────────
        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        self._lbl_code = QLabel()
        left_col.addWidget(self._lbl_code)
        # CodeEditor = QPlainTextEdit + ArduinoHighlighter + line numbers.
        # Manages its own theme via theme_manager, so no need to
        # apply a stylesheet to it here. setReadOnly keeps the selection
        # (mouse + keyboard), only modifications are blocked.
        self._code_edit = CodeEditor()
        self._code_edit.setPlainText(code)
        self._code_edit.setReadOnly(True)
        self._code_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        # Captures Enter / Return in the editor: if a selection exists,
        # we trigger the AI analysis — keyboard shortcut equivalent to clicking
        # on "Expliquer".
        self._code_edit.installEventFilter(self)
        left_col.addWidget(self._code_edit, stretch=1)
        cols.addLayout(left_col, stretch=1)

        # ── Right column: AI response ──────────────────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        self._lbl_result = QLabel()
        right_col.addWidget(self._lbl_result)
        self._result_view = QTextEdit()
        self._result_view.setReadOnly(True)
        self._result_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        # Syntax coloring for the ``` code blocks of the rendered markdown.
        # The highlighter does not touch the normal explanation text: it
        # triggers only on the blocks in monospace font.
        self._result_highlighter = _MarkdownCodeHighlighter(
            self._result_view.document()
        )

        # Loading zone: spinner + label centered vertically. Replaces
        # the AI response during a backend call. Switches via a
        # QStackedWidget so that the reserved size stays constant.
        self._loading_page = QWidget()
        loading_layout = QVBoxLayout(self._loading_page)
        loading_layout.setContentsMargins(0, 0, 0, 0)
        loading_layout.setSpacing(8)
        loading_layout.addStretch(1)
        self._robot = RobotLoader(point_size=18)
        loading_layout.addWidget(self._robot, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._lbl_loading_text = LoaderLabel(point_size=10)
        self._lbl_loading_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(self._lbl_loading_text)
        loading_layout.addStretch(1)

        self._result_stack = QStackedWidget()
        self._result_stack.addWidget(self._result_view)     # index 0
        self._result_stack.addWidget(self._loading_page)    # index 1
        right_col.addWidget(self._result_stack, stretch=1)

        cols.addLayout(right_col, stretch=1)

        # ── Actions bar ──────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._btn_explain = QPushButton()
        self._btn_explain.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_explain.clicked.connect(self._trigger_explain)
        actions.addWidget(self._btn_explain)
        actions.addStretch(1)
        self._btn_close = QPushButton()
        self._btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_close.clicked.connect(self.reject)
        actions.addWidget(self._btn_close)
        root.addLayout(actions)

        # Reproduces the initial selection in the dialog's QPlainTextEdit
        # so that the user sees what we are talking about.
        if selection.strip():
            self._select_substring(code, selection)

    def _select_substring(self, haystack: str, needle: str):
        """Positions the code_edit selection on the 1st occurrence of
        `needle` in `haystack`. Used to replay the selection of
        the main editor."""
        idx = haystack.find(needle)
        if idx < 0:
            return
        cursor = self._code_edit.textCursor()
        cursor.setPosition(idx)
        cursor.setPosition(idx + len(needle), QTextCursor.MoveMode.KeepAnchor)
        self._code_edit.setTextCursor(cursor)

    # ── AI trigger ───────────────────────────────────────────
    def _trigger_explain(self):
        if self._worker is not None and self._worker.isRunning():
            return
        code = self._code_edit.toPlainText()
        cursor = self._code_edit.textCursor()
        selection = cursor.selectedText().replace(" ", "\n")
        self._btn_explain.setEnabled(False)
        self._set_spinner_visible(True)
        self._worker = _ExplainWorker(
            self._backend, code, selection,
            lang_manager.ai_lang_name(), self._board_name,
        )
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, text: str):
        # setMarkdown: Qt renders the lists, **bold**, ``backticks``, headings
        # and fenced code blocks, clearly more readable than a setPlainText.
        self._result_view.setMarkdown(text.strip())
        self._space_list_items()
        self._btn_explain.setEnabled(True)
        self._set_spinner_visible(False)

    def _space_list_items(self):
        """Increases the vertical spacing between list items.

        By default Qt sticks the `-` markdown items to one another;
        we add a top/bottom margin on each block belonging to a
        QTextList to air out the rendering.
        """
        doc = self._result_view.document()
        spacing = QTextBlockFormat()
        spacing.setTopMargin(8)
        spacing.setBottomMargin(8)
        cursor = QTextCursor(doc)
        block = doc.firstBlock()
        while block.isValid():
            if block.textList() is not None:
                cursor.setPosition(block.position())
                cursor.mergeBlockFormat(spacing)
            block = block.next()

    def _on_error(self, msg: str):
        self._result_view.setPlainText(f"⚠ {msg}")
        self._btn_explain.setEnabled(True)
        self._set_spinner_visible(False)

    # ── Loader ────────────────────────────────────────────────────
    def _set_spinner_visible(self, visible: bool):
        if visible:
            self._result_stack.setCurrentWidget(self._loading_page)
            self._robot.start()
            self._lbl_loading_text.start()
        else:
            self._robot.stop()
            self._lbl_loading_text.stop()
            self._result_stack.setCurrentWidget(self._result_view)

    # ── Event filter: Enter on selection → analysis ───────────
    def eventFilter(self, obj, ev):
        if obj is self._code_edit and ev.type() == QEvent.Type.KeyPress:
            if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                cursor = self._code_edit.textCursor()
                if cursor.hasSelection():
                    self._trigger_explain()
                    return True
        return super().eventFilter(obj, ev)

    # ── Theme / Language ───────────────────────────────────────────
    def apply_theme(self, c: ColorScheme):
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        self.setPalette(p)
        self.setAutoFillBackground(True)
        lbl_style = (
            f"font-size: 10pt; font-weight: 600; color: {c.text_primary};"
            "background: transparent;"
        )
        self._lbl_code.setStyleSheet(lbl_style)
        self._lbl_result.setStyleSheet(lbl_style)
        # AI response (QTextEdit): we style it directly. For the code
        # (CodeEditor), we leave its own theme/font handling: no
        # stylesheet here, otherwise we break the line numbering and the
        # syntax coloring.
        self._result_view.setStyleSheet(f"""
            QTextEdit {{
                background-color: {c.sidebar_bg};
                color: {c.text_primary};
                border: none;
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 10pt;
            }}
        """)
        # Centralized style (green on hover). cf theme.*_button_qss.
        # « Expliquer » = primary (main affirmative action),
        # « Fermer » = secondary (outlined).
        self._btn_explain.setStyleSheet(primary_button_qss(c, padding="6px 16px"))
        self._btn_close.setStyleSheet(secondary_button_qss(c, padding="6px 16px"))
        # Spinner + label "Analyse en cours..." at the center of the
        # explanation zone during a backend call.
        # Spinner + loading text: phosphor GREEN (signal_ok), not
        # nav_active_bg which is nearly invisible (very dark/pale green).
        self._robot.set_color(c.signal_ok)
        self._lbl_loading_text.set_color(c.signal_ok)
        # Background of the loading page: same color as the result_view for
        # a homogeneous visual switch. No border.
        self._loading_page.setStyleSheet(
            f"background-color: {c.sidebar_bg};"
            "border-radius: 6px;"
        )

    def apply_lang(self, s: Strings):
        self.setWindowTitle(s.studio_explain_title)
        self._lbl_code.setText(s.studio_explain_code_label)
        self._lbl_result.setText(s.studio_explain_result_label)
        self._btn_explain.setText(s.studio_explain_btn)
        self._btn_close.setText(s.studio_explain_close)
        self._lbl_loading_text.set_text(s.studio_explain_loading)
        # Initial placeholder: if no starting selection, we invite
        # the user to make one rather than leaving an empty zone.
        if not self._initial_selection.strip() and not self._result_view.toPlainText():
            self._result_view.setPlainText(s.studio_explain_hint_select)
