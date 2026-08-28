"""
"Code repare" dialog shown when clicking the AI tool "Reparer le code".

The dialog opens immediately on click and launches the AI call in the
background:
  - left column: initially the original code; replaced by the
    repaired code as soon as the AI responds, with the modified lines
    highlighted in accent color;
  - right column: loading page (spinner + label) during the call,
    then the markdown summary of the repairs once it arrives.

The new code is not applied by the dialog: an `apply_requested(str)`
signal is emitted on success; it is StudioView that
replaces the editor content and logs the summary in the journal.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPalette, QColor, QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTextEdit, QSizePolicy, QStackedWidget, QWidget,
)

from .diff_utils import _DiffCodeView, build_side_by_side_diff, link_scrollbars
from .explain_code_dialog import _MarkdownCodeHighlighter
from .i18n import lang_manager, Strings
from .robot_loader import RobotLoader, LoaderLabel
from .theme import (
    ColorScheme, theme_manager, primary_button_qss, secondary_button_qss,
)


class _RepairWorker(QThread):
    finished = pyqtSignal(str, str)  # (code, summary)
    error    = pyqtSignal(str)

    def __init__(self, backend, code: str, errors: str, language: str,
                 board_name: str, review_call=None):
        super().__init__()
        self._backend    = backend
        self._code       = code
        self._errors     = errors
        self._language   = language
        self._board_name = board_name
        # Optional override: a zero-arg callable returning (code, summary).
        # Used for the CONFORMANCE review (layer C) instead of repair_code.
        self._review_call = review_call

    def run(self):
        try:
            if self._review_call is not None:
                code, summary = self._review_call()
            else:
                code, summary = self._backend.repair_code(
                    self._code, self._errors, self._language, self._board_name,
                )
            self.finished.emit(code, summary)
        except Exception as e:
            self.error.emit(str(e))


class RepairCodeDialog(QDialog):
    """Modal dialog that launches the AI repair on opening."""

    apply_requested = pyqtSignal(str)  # new code to apply to the editor
    summary_ready   = pyqtSignal(str)  # summary for the journal log

    def __init__(self, backend, code: str, board_name: str, parent=None,
                 review_call=None, deferred=False, applied=None):
        super().__init__(parent)
        self._backend = backend
        self._original_code = code
        self._new_code = ""
        self._summary = ""
        self._board_name = board_name
        # Conformance review (layer C) : a zero-arg callable -> (code, summary)
        # used instead of the antipattern audit (backend.repair_code(code,"")).
        self._review_call = review_call
        # Deferred mode: the dialog opens IMMEDIATELY with the spinner and the
        # caller drives it later (compile-first happens behind the open modal,
        # then start_deferred() runs the review). Avoids the lag where the
        # modal only appeared AFTER a silent console compile.
        self._deferred = deferred
        # Summary of the fixes applied BEFORE the review (the compile cascade):
        # shown ABOVE the review summary so the modal lists BOTH sets of fixes.
        # The diff column already shows both (its baseline stays the TRUE
        # original — we never rebase it to the post-cascade code).
        self._pre_summary = ""
        # Read-only mode: display repairs ALREADY applied (auto compile/upload)
        # as (final_code, summary) — no worker, no « Appliquer » (nothing to
        # apply). Same modal as the manual repair, in a display-only mode
        # (TODO #32, replaces the old stepper RepairHistoryDialog).
        self._applied = applied
        self._worker: _RepairWorker | None = None

        self.setModal(True)
        self.setMinimumSize(1320, 600)   # 3 columns: original | diff | analysis
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

        if self._applied is not None:
            self._render_applied()            # read-only, already applied
        elif self._deferred:
            self._set_spinner_visible(True)   # open now; caller drives later
        else:
            self._trigger_repair()

    # ── Deferred driving (compile-first behind the open modal) ────
    def set_pre_summary(self, text: str):
        """Fixes applied by the compile cascade BEFORE the review — listed
        above the review summary in the modal (the diff already shows them)."""
        self._pre_summary = text or ""

    def start_deferred(self, review_call=None):
        """Run the review now (deferred mode): the modal is already open with
        its spinner."""
        if review_call is not None:
            self._review_call = review_call
        self._trigger_repair()

    def show_compile_failure(self, message: str):
        """Compile failed and could not be repaired -> no review to show;
        display the diagnostic in place of the spinner, keep Apply disabled."""
        self._set_spinner_visible(False)
        self._result_view.setPlainText(message or "")
        self._btn_apply.setEnabled(False)

    def _render_applied(self):
        """Read-only display of repairs ALREADY applied (auto compile/upload):
        the consolidated original -> final diff + the cascade explanation, no
        worker, no « Appliquer » (TODO #32). Same 3-column modal as the manual
        repair, in a display-only mode."""
        final_code, summary = self._applied
        final_code = (final_code or "").rstrip() + "\n"
        self._new_code = final_code
        self._summary = summary or ""
        old_removed, new_added = build_side_by_side_diff(
            self._original_code, final_code)
        self._orig_view.set_diff(old_removed, set())       # red on the left
        self._diff_view.setPlainText(final_code)
        self._diff_view.set_diff(set(), new_added)          # green in the center
        self._populate_summary(self._summary)
        self._set_spinner_visible(False)
        self._btn_apply.setVisible(False)                   # already applied
        # Nothing is pending in this read-only mode, so closing throws nothing
        # away: « Fermer » legitimately takes back the default button (an
        # invisible default button would leave Enter with nothing to do).
        self._btn_close.setAutoDefault(True)
        self._btn_close.setDefault(True)

    # ── Construction ─────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        cols = QHBoxLayout()
        cols.setSpacing(12)
        root.addLayout(cols, stretch=1)

        # ── Left column: ORIGINAL code (never modified) ─────
        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        self._lbl_orig = QLabel()
        left_col.addWidget(self._lbl_orig)
        self._orig_view = _DiffCodeView()
        self._orig_view.setPlainText(self._original_code)
        self._orig_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        left_col.addWidget(self._orig_view, stretch=1)
        cols.addLayout(left_col, stretch=1)

        # ── Center column: corrected code as DIFF (red/green) ─
        diff_col = QVBoxLayout()
        diff_col.setSpacing(4)
        self._lbl_diff = QLabel()
        diff_col.addWidget(self._lbl_diff)
        self._diff_view = _DiffCodeView()
        self._diff_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        diff_col.addWidget(self._diff_view, stretch=1)
        cols.addLayout(diff_col, stretch=1)

        # Parallel scrolling of the two code panels (original ↔ corrected).
        link_scrollbars(self._orig_view, self._diff_view)

        # ── Right column: loading / summary ──────────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        self._lbl_result = QLabel()
        right_col.addWidget(self._lbl_result)

        self._result_view = QTextEdit()
        self._result_view.setReadOnly(True)
        self._result_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        self._result_highlighter = _MarkdownCodeHighlighter(
            self._result_view.document()
        )

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

        self._right_stack = QStackedWidget()
        self._right_stack.addWidget(self._result_view)   # 0
        self._right_stack.addWidget(self._loading_page)  # 1
        right_col.addWidget(self._right_stack, stretch=1)
        cols.addLayout(right_col, stretch=1)


        # ── Action bar ─────────────────────────────────────
        # « Appliquer » (primary) offers explicit application of the
        # corrected code; disabled until the AI has responded. « Fermer »
        # (secondary) closes without applying anything.
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)
        self._btn_close = QPushButton()
        self._btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_close.clicked.connect(self.reject)
        actions.addWidget(self._btn_close)
        self._btn_apply = QPushButton()
        self._btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_apply.setEnabled(False)
        self._btn_apply.clicked.connect(self._on_apply)
        actions.addWidget(self._btn_apply)
        # Enter must never THROW AWAY a repair that is ready. « Fermer » is
        # added to the layout before « Appliquer », so without this Qt promotes
        # IT to default button (first autoDefault button wins when nothing is
        # set): once the AI has answered, pressing Enter ran `reject()` and the
        # corrected code was lost without the user ever choosing. While the AI
        # is still working, « Appliquer » is disabled, and a disabled default
        # button makes Enter a no-op — which is exactly what we want.
        self._btn_close.setAutoDefault(False)
        self._btn_close.setDefault(False)
        self._btn_apply.setAutoDefault(True)
        self._btn_apply.setDefault(True)
        root.addLayout(actions)

    # ── AI trigger ───────────────────────────────────────────
    def _trigger_repair(self):
        self._set_spinner_visible(True)
        self._worker = _RepairWorker(
            self._backend, self._original_code, "",
            lang_manager.ai_lang_name(), self._board_name,
            review_call=self._review_call,
        )
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, new_code: str, summary: str):
        new_code = new_code.rstrip() + "\n"
        self._new_code = new_code
        self._summary = summary
        # Side-by-side diff: left = ORIGINAL verbatim, removed/modified lines
        # highlighted in RED; center = CORRECTED verbatim, added/
        # modified lines highlighted in GREEN.
        old_removed, new_added = build_side_by_side_diff(
            self._original_code, new_code,
        )
        self._orig_view.set_diff(old_removed, set())     # red on the left
        self._diff_view.setPlainText(new_code)
        self._diff_view.set_diff(set(), new_added)        # green in the center
        # Right column shows BOTH the cascade fixes (pre-summary) and the review
        # summary; but `summary_ready` (journal) emits only the REVIEW part —
        # the cascade already has its own « voir les corrections » entry.
        display = (f"{self._pre_summary}\n\n{summary}".strip()
                   if self._pre_summary else summary)
        self._populate_summary(display)
        self._set_spinner_visible(False)
        # The code is NOT applied automatically: we enable the
        # « Appliquer » button to let the user decide.
        self._btn_apply.setEnabled(True)

    def _on_apply(self):
        """Applies the proposal: StudioView replaces the editor code
        and logs the summary in the journal, then we close."""
        self.apply_requested.emit(self._new_code)
        self.summary_ready.emit(self._summary)
        self.accept()

    def _on_error(self, msg: str):
        s = lang_manager.current
        self._result_view.setPlainText(
            s.studio_repair_error.format(msg=msg)
        )
        self._set_spinner_visible(False)

    def _populate_summary(self, summary: str):
        text = (summary or "").strip()
        if text:
            self._result_view.setMarkdown(text)
            spacing = QTextBlockFormat()
            spacing.setTopMargin(8)
            spacing.setBottomMargin(8)
            cursor = QTextCursor(self._result_view.document())
            block = self._result_view.document().firstBlock()
            while block.isValid():
                if block.textList() is not None:
                    cursor.setPosition(block.position())
                    cursor.mergeBlockFormat(spacing)
                block = block.next()
        else:
            s = lang_manager.current
            self._result_view.setPlainText(s.studio_repair_no_summary)

    # ── Loader ────────────────────────────────────────────────────
    def _set_spinner_visible(self, visible: bool):
        if visible:
            self._right_stack.setCurrentWidget(self._loading_page)
            self._robot.start()
            self._lbl_loading_text.start()
        else:
            self._robot.stop()
            self._lbl_loading_text.stop()
            self._right_stack.setCurrentWidget(self._result_view)

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
        self._lbl_orig.setStyleSheet(lbl_style)
        self._lbl_diff.setStyleSheet(lbl_style)
        self._lbl_result.setStyleSheet(lbl_style)
        # Refreshes the diff colors (red/green derived from the theme).
        self._orig_view._rebuild_extra_selections()
        self._diff_view._rebuild_extra_selections()
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
        # « Appliquer » = primary (solid, green on hover), « Fermer » =
        # secondary. Centralized styles. cf theme.*_button_qss.
        self._btn_apply.setStyleSheet(primary_button_qss(c, padding="6px 16px"))
        self._btn_close.setStyleSheet(secondary_button_qss(c, padding="6px 16px"))
        # Spinner + loading text: phosphor GREEN (signal_ok), not
        # nav_active_bg which is nearly invisible (very dark/pale green).
        self._robot.set_color(c.signal_ok)
        self._lbl_loading_text.set_color(c.signal_ok)
        self._loading_page.setStyleSheet(
            f"background-color: {c.sidebar_bg}; border-radius: 6px;"
        )

    def apply_lang(self, s: Strings):
        # Read-only « already applied » mode reuses the auto-fixes title.
        self.setWindowTitle(s.studio_repair_history_title if self._applied
                            is not None else s.studio_repair_dialog_title)
        self._lbl_orig.setText(s.studio_repair_original_label)
        self._lbl_diff.setText(s.studio_repair_code_label)
        self._lbl_result.setText(s.studio_repair_summary_label)
        self._btn_apply.setText(s.studio_repair_apply)
        self._btn_close.setText(s.studio_explain_close)
        self._lbl_loading_text.set_text(s.studio_repairing)
