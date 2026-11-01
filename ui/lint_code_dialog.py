"""
"Detecter les antipatterns" dialog (AI tool of the Tools panel).

Layout identical to ExplainCodeDialog:
  - left column: the full code read-only (Arduino coloring),
  - right column: the list of warnings in markdown,
  - action bar: "Relancer l'inspection" button + "Fermer" button,
  - switches via QStackedWidget to a "loading" page centering a spinner
    + label during the call to the backend.

The dialog auto-launches the inspection on opening: the user has nothing
to select, the tool analyzes the entirety of the code.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPalette, QColor, QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTextEdit, QSizePolicy, QStackedWidget, QWidget,
)

from .code_editor import CodeEditor
from .explain_code_dialog import _MarkdownCodeHighlighter
from .robot_loader import RobotLoader, LoaderLabel
from .i18n import lang_manager, Strings
from .theme import (
    ColorScheme, theme_manager, primary_button_qss, secondary_button_qss,
)


class _LintWorker(QThread):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, backend, code: str, language: str, board_name: str):
        super().__init__()
        self._backend    = backend
        self._code       = code
        self._language   = language
        self._board_name = board_name

    def run(self):
        try:
            text = self._backend.lint_code(
                self._code, self._language, self._board_name,
            )
            self.finished.emit(text)
        except Exception as e:
            self.error.emit(str(e))


class LintCodeDialog(QDialog):
    """Modal dialog for the "Detecter les antipatterns" tool.

    Analyzes the entirety of the code provided as argument and displays the
    list of warnings in markdown. No modification is propagated to
    the main editor — the dialog is an isolated viewer.
    """

    def __init__(self, backend, code: str, board_name: str, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._code = code
        self._board_name = board_name
        self._worker: _LintWorker | None = None

        self.setModal(True)
        self.setMinimumSize(900, 520)
        self._build(code)
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

        # Auto-launch: no user selection required, we audit all
        # the code immediately on opening.
        self._trigger_lint()

    # ── Construction ─────────────────────────────────────────────
    def _build(self, code: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        cols = QHBoxLayout()
        cols.setSpacing(12)
        root.addLayout(cols, stretch=1)

        # ── Left column: read-only code ───────────────
        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        self._lbl_code = QLabel()
        left_col.addWidget(self._lbl_code)
        self._code_view = CodeEditor()
        self._code_view.setPlainText(code)
        self._code_view.setReadOnly(True)
        self._code_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        left_col.addWidget(self._code_view, stretch=1)
        cols.addLayout(left_col, stretch=1)

        # ── Right column: results ──────────────────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        self._lbl_result = QLabel()
        right_col.addWidget(self._lbl_result)

        self._result_view = QTextEdit()
        self._result_view.setReadOnly(True)
        self._result_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        # Same highlighter as for Explain: bolds + Arduino
        # coloring on the monospace fragments (blocks and backticks).
        self._result_highlighter = _MarkdownCodeHighlighter(
            self._result_view.document()
        )

        # Loading page: spinner + label centered.
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


        # ── Action bar ─────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._btn_rerun = QPushButton()
        self._btn_rerun.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_rerun.clicked.connect(self._trigger_lint)
        actions.addWidget(self._btn_rerun)
        actions.addStretch(1)
        self._btn_close = QPushButton()
        self._btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_close.clicked.connect(self.reject)
        actions.addWidget(self._btn_close)
        root.addLayout(actions)

    # ── AI trigger ───────────────────────────────────────────
    def _trigger_lint(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self._btn_rerun.setEnabled(False)
        self._set_spinner_visible(True)
        self._worker = _LintWorker(
            self._backend, self._code,
            lang_manager.ai_lang_name(), self._board_name,
        )
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, text: str):
        self._result_view.setMarkdown(text.strip())
        self._space_list_items()
        self._btn_rerun.setEnabled(True)
        self._set_spinner_visible(False)

    def _on_error(self, msg: str):
        self._result_view.setPlainText(f"⚠ {msg}")
        self._btn_rerun.setEnabled(True)
        self._set_spinner_visible(False)

    def _space_list_items(self):
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
        # « Relancer l'inspection » = primary, « Fermer » = secondary.
        self._btn_rerun.setStyleSheet(primary_button_qss(c, padding="6px 16px"))
        self._btn_close.setStyleSheet(secondary_button_qss(c, padding="6px 16px"))
        # Spinner + « Analyse en cours » text: phosphor GREEN (signal_ok),
        # not nav_active_bg which is nearly invisible (very dark/pale green).
        self._robot.set_color(c.signal_ok)
        self._lbl_loading_text.set_color(c.signal_ok)
        self._loading_page.setStyleSheet(
            f"background-color: {c.sidebar_bg};"
            "border-radius: 6px;"
        )

    def apply_lang(self, s: Strings):
        self.setWindowTitle(s.studio_lint_title)
        self._lbl_code.setText(s.studio_explain_code_label)
        self._lbl_result.setText(s.studio_lint_result_label)
        self._btn_rerun.setText(s.studio_lint_rerun_btn)
        self._btn_close.setText(s.studio_explain_close)
        self._lbl_loading_text.set_text(s.studio_lint_loading)
