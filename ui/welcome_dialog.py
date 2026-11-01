"""First-launch wizard.

Asks the user where to store their projects and libraries.
Appears as long as `session.is_workspace_root_configured()` is False.
Cancel = closing the application (you cannot work without a
workspace).
"""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QFileDialog,
)

from .theme import (
    ColorScheme, theme_manager, primary_button_qss, secondary_button_qss,
)
from .i18n import lang_manager, Strings
from .session import session


class WelcomeDialog(QDialog):
    """Modal dialog shown on the first startup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumSize(520, 320)
        self.resize(560, 340)

        # Selected path (default: the session's default path)
        self._chosen: Path = session.default_workspace_root()
        # Flag to suspend the auto-close during the QFileDialog
        self._suppress_close = False

        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)

    # ── Construction ──────────────────────────────────────────

    def _build(self):
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.CustomizeWindowHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(10)

        self._heading = QLabel()
        root.addWidget(self._heading)

        self._description = QLabel()
        self._description.setWordWrap(True)
        root.addWidget(self._description)

        root.addSpacing(8)

        self._lbl_folder = QLabel()
        root.addWidget(self._lbl_folder)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self._path_display = QLabel()
        self._path_display.setWordWrap(True)
        self._path_display.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        path_row.addWidget(self._path_display, stretch=1)

        self._btn_browse = QPushButton()
        self._btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_browse.setFixedHeight(32)
        # « Parcourir… » est le premier widget focusable de la modale (le label
        # du chemin ne l'est pas), et un QPushButton autoDefault qui prend le
        # focus s'attribue le rôle de bouton par défaut — ce qui écrasait le
        # `setDefault(True)` posé plus bas sur « Continuer ». Entrée ouvrait
        # donc le sélecteur de dossier au lieu de valider.
        self._btn_browse.setAutoDefault(False)
        self._btn_browse.clicked.connect(self._on_browse)
        path_row.addWidget(self._btn_browse)
        root.addLayout(path_row)

        root.addSpacing(4)
        self._hint = QLabel()
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        root.addStretch()

        # Confirmation button at the bottom right
        bottom = QHBoxLayout()
        bottom.addStretch()
        self._btn_confirm = QPushButton()
        self._btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_confirm.setFixedHeight(34)
        self._btn_confirm.setMinimumWidth(120)
        self._btn_confirm.setDefault(True)
        self._btn_confirm.clicked.connect(self._on_confirm)
        bottom.addWidget(self._btn_confirm)
        root.addLayout(bottom)

        self._refresh_path()

    # ── Actions ───────────────────────────────────────────────

    def _refresh_path(self):
        self._path_display.setText(str(self._chosen))

    def _on_browse(self):
        s = lang_manager.current
        start = str(self._chosen)
        # Suspend close-on-deactivation during the native file dialog
        self._suppress_close = True
        try:
            chosen = QFileDialog.getExistingDirectory(
                self, s.settings_storage_picker_title, start
            )
        finally:
            self._suppress_close = False
        if not chosen:
            return
        self._chosen = Path(chosen).expanduser().resolve()
        self._refresh_path()

    def _on_confirm(self):
        default_root = session.default_workspace_root()
        if self._chosen == default_root:
            # Empty string -> stores the "default" marker
            session.workspace_root = ""
        else:
            session.workspace_root = str(self._chosen)
        self.accept()

    # ── Closing: if the user closes the window without confirming,
    # we reject. main.py treats reject as an app-stop signal.

    def closeEvent(self, event):
        if self.result() != QDialog.DialogCode.Accepted:
            self.reject()
        super().closeEvent(event)

    # ── Theme ─────────────────────────────────────────────────

    @staticmethod
    def _set_bg(widget: QWidget, hex_color: str):
        p = widget.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(hex_color))
        widget.setPalette(p)
        widget.setAutoFillBackground(True)

    def apply_theme(self, c: ColorScheme):
        self._set_bg(self, c.main_bg)
        self._heading.setStyleSheet(
            f"font-size: 15pt; font-weight: 700; color: {c.text_primary};"
        )
        self._description.setStyleSheet(
            f"font-size: 10pt; color: {c.text_secondary};"
        )
        self._lbl_folder.setStyleSheet(
            f"font-size: 10pt; font-weight: 600; color: {c.text_primary};"
        )
        self._path_display.setStyleSheet(f"""
            QLabel {{
                background-color: {c.sidebar_bg};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: 6px;
                padding: 8px 10px;
                font-family: Consolas, monospace;
                font-size: 10pt;
            }}
        """)
        self._hint.setStyleSheet(
            f"font-size: 9pt; color: {c.text_secondary}; font-style: italic;"
        )
        # « Parcourir » = secondary (outlined), « Confirmer » = primary (filled),
        # agreed-upon centralized style (green on hover). cf theme.*_button_qss.
        self._btn_browse.setStyleSheet(secondary_button_qss(c, padding="4px 14px"))
        self._btn_confirm.setStyleSheet(primary_button_qss(c, padding="4px 22px"))

    # ── Lang ──────────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        self.setWindowTitle(s.welcome_title)
        self._heading.setText(s.welcome_heading)
        self._description.setText(s.welcome_description)
        self._lbl_folder.setText(s.welcome_folder_label)
        self._btn_browse.setText(s.welcome_browse)
        self._btn_confirm.setText(s.welcome_confirm)
        self._hint.setText(s.welcome_hint)
