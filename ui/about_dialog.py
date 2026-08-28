"""About dialog: app identity, developer, and open-source credits.

The developer block is intentionally driven by the two constants below so it
is trivial to update — in particular if the Windows installer later gets a
code-signing certificate (Individual Validation), whose *validated* identity
is what Windows shows as the "Verified publisher". That identity comes from
the signing step (signtool / Inno Setup), not from this dialog; keep the name
here consistent with it.
"""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor, QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QWidget, QFrame, QSizePolicy,
)

from .theme import ColorScheme, theme_manager, selection_bg
from .i18n import lang_manager, Strings
from .sidebar import APP_VERSION
from . import icons as IC

# Display name (the repo is "PromptuinoUI"; the product is "Promptuino").
_APP_NAME = "Promptuino"
_DEVELOPER = "Mehdi KARIM"
_COPYRIGHT = "© 2026 Mehdi KARIM"
# Links shown under the developer block — replace the placeholders with the
# real URLs (public repository / Patreon page) when they go live.
_SOURCE_URL = "[placeholder]"
_PATREON_URL = "[placeholder]"

# Open-source software & assets actually bundled in / used by the app.
# (name, license, vendor) — proper nouns + license identifiers: NOT translated.
_CREDITS: list[tuple[str, str, str]] = [
    ("PyQt6",                                  "GPL v3",       "Riverbank Computing"),
    ("Qt 6",                                   "LGPL v3",      "The Qt Company"),
    ("Python",                                 "PSF License",  "Python Software Foundation"),
    ("NumPy",                                  "BSD-3-Clause", ""),
    ("ONNX Runtime",                           "MIT",          "Microsoft"),
    ("Tokenizers",                             "Apache 2.0",   "Hugging Face"),
    ("pySerial",                               "BSD-3-Clause", ""),
    ("keyring",                                "MIT",          ""),
    ("Python-Markdown",                        "BSD-3-Clause", ""),
    ("Arduino CLI",                            "GPL v3",       "Arduino"),
    ("Lucide",                                 "ISC",          "icons"),
    ("Fritzing",                               "CC-BY-SA 3.0", "component graphics"),
    ("Geist",                                  "SIL OFL 1.1",  "Vercel"),
    ("JetBrains Mono",                         "SIL OFL 1.1",  "JetBrains"),
    ("paraphrase-multilingual-MiniLM-L12-v2",  "Apache 2.0",   "sentence-transformers"),
]


class AboutDialog(QDialog):
    """Modal "About" window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(440, 480)
        self.resize(500, 580)
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    # ── Construction ──────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(10)

        # Header: logo + (name / version)
        header = QHBoxLayout()
        header.setSpacing(12)
        self._logo = QLabel()
        self._logo.setFixedSize(48, 48)
        header.addWidget(self._logo, alignment=Qt.AlignmentFlag.AlignTop)

        name_col = QVBoxLayout()
        name_col.setSpacing(0)
        self._lbl_name = QLabel(_APP_NAME)
        self._lbl_version = QLabel(APP_VERSION)
        name_col.addWidget(self._lbl_name)
        name_col.addWidget(self._lbl_version)
        header.addLayout(name_col)
        header.addStretch()
        root.addLayout(header)

        # Short description (reuses the former About message)
        self._lbl_desc = QLabel()
        self._lbl_desc.setWordWrap(True)
        root.addWidget(self._lbl_desc)

        root.addSpacing(2)

        # Developer section (centered)
        self._lbl_dev_head = QLabel()
        self._lbl_dev_head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._lbl_dev_head)
        self._lbl_dev_name = QLabel(_DEVELOPER)
        self._lbl_dev_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._lbl_dev_name)
        self._lbl_copyright = QLabel(_COPYRIGHT)
        self._lbl_copyright.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._lbl_copyright)

        # Links (left-aligned): GitHub source code, then Patreon support.
        gh_row = QHBoxLayout()
        gh_row.setSpacing(6)
        self._lbl_gh_icon = QLabel()
        self._lbl_gh_icon.setFixedSize(15, 15)
        gh_row.addWidget(self._lbl_gh_icon, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._lbl_source = QLabel()
        gh_row.addWidget(self._lbl_source, alignment=Qt.AlignmentFlag.AlignVCenter)
        gh_row.addStretch()
        root.addLayout(gh_row)

        pat_row = QHBoxLayout()
        pat_row.setSpacing(6)
        self._lbl_pat_icon = QLabel()
        self._lbl_pat_icon.setFixedSize(15, 15)
        pat_row.addWidget(self._lbl_pat_icon, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._lbl_support = QLabel()
        pat_row.addWidget(self._lbl_support, alignment=Qt.AlignmentFlag.AlignVCenter)
        pat_row.addStretch()
        root.addLayout(pat_row)

        # Separator
        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.HLine)
        self._sep.setFixedHeight(1)
        root.addWidget(self._sep)

        # Credits section
        self._lbl_credits_head = QLabel()
        root.addWidget(self._lbl_credits_head)
        self._lbl_credits_intro = QLabel()
        self._lbl_credits_intro.setWordWrap(True)
        root.addWidget(self._lbl_credits_intro)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._credits_host = QWidget()
        host_layout = QVBoxLayout(self._credits_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        self._lbl_credits = QLabel()
        self._lbl_credits.setWordWrap(True)
        self._lbl_credits.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._lbl_credits.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        self._lbl_credits.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        host_layout.addWidget(self._lbl_credits)
        host_layout.addStretch()
        self._scroll.setWidget(self._credits_host)
        root.addWidget(self._scroll, stretch=1)

    # ── Rendering helpers ─────────────────────────────────────
    def _credits_html(self, c: ColorScheme) -> str:
        out = []
        for name, lic, vendor in _CREDITS:
            meta = lic + (f" · {vendor}" if vendor else "")
            out.append(
                f"<p style='margin:0 0 8px 0;'>"
                f"<span style='color:{c.text_primary}; font-weight:600;'>{name}</span><br>"
                f"<span style='color:{c.text_secondary};'>{meta}</span>"
                f"</p>"
            )
        return "".join(out)

    # ── Theme ─────────────────────────────────────────────────
    @staticmethod
    def _set_bg(widget: QWidget, hex_color: str):
        p = widget.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(hex_color))
        widget.setPalette(p)
        widget.setAutoFillBackground(True)

    def apply_theme(self, c: ColorScheme):
        self._set_bg(self, c.main_bg)

        # Themed app logo (same multicolor asset as the sidebar).
        variant = "dark" if theme_manager.is_dark else "light"
        logo_path = (Path(__file__).resolve().parent.parent / "assets" / "logo"
                     / f"icon-transparent-{variant}.svg")
        self._logo.setPixmap(QIcon(str(logo_path)).pixmap(48, 48))
        self._logo.setStyleSheet("background: transparent;")

        self._lbl_name.setStyleSheet(
            f"color: {c.text_primary}; font-size: 17pt; font-weight: 700;"
        )
        self._lbl_version.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt;"
        )
        self._lbl_desc.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt;"
        )
        head_qss = (
            f"color: {c.text_primary}; font-size: 11pt; font-weight: 700;"
            " margin-top: 4px;"
        )
        self._lbl_dev_head.setStyleSheet(head_qss)
        self._lbl_credits_head.setStyleSheet(head_qss)
        self._lbl_dev_name.setStyleSheet(
            f"color: {c.accent}; font-size: 11pt; font-weight: 600;"
        )
        self._lbl_copyright.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 9pt;"
        )
        self._lbl_gh_icon.setPixmap(
            IC.make_icon(IC.GITHUB, c.accent, 15).pixmap(15, 15)
        )
        self._lbl_gh_icon.setStyleSheet("background: transparent;")
        self._lbl_source.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 9pt;"
        )
        self._lbl_pat_icon.setPixmap(
            IC.make_icon(IC.PATREON, c.accent, 15).pixmap(15, 15)
        )
        self._lbl_pat_icon.setStyleSheet("background: transparent;")
        self._lbl_support.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 9pt;"
        )
        self._lbl_credits_intro.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 9pt;"
        )
        self._sep.setStyleSheet(f"background-color: {c.border}; border: none;")

        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self._set_bg(self._credits_host, c.surface)
        self._credits_host.setStyleSheet(
            f"background-color: {c.surface}; border: 1px solid {c.border};"
            " border-radius: 6px;"
        )
        vp = self._scroll.viewport()
        self._set_bg(vp, c.surface)
        self._lbl_credits.setStyleSheet(
            f"color: {c.text_primary}; font-size: 10pt; padding: 12px;"
            f" background: transparent;"
            f" selection-background-color: {selection_bg(c)};"
            f" selection-color: {c.text_primary};"
        )
        self._lbl_credits.setText(self._credits_html(c))

    # ── Lang ──────────────────────────────────────────────────
    def apply_lang(self, s: Strings):
        self.setWindowTitle(s.mn_about)
        self._lbl_desc.setText(s.mn_about_msg)
        self._lbl_dev_head.setText(s.about_developer)
        self._lbl_source.setText(f"{s.about_source} : {_SOURCE_URL}")
        self._lbl_support.setText(f"{s.about_support} : {_PATREON_URL}")
        self._lbl_credits_head.setText(s.about_credits_title)
        self._lbl_credits_intro.setText(s.about_credits_intro)
        self._lbl_credits.setText(self._credits_html(theme_manager.current))
