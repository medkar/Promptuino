"""About dialog: app identity, developer, and open-source credits.

The developer block is intentionally driven by the two constants below so it
is trivial to update — in particular if the Windows installer later gets a
code-signing certificate (Individual Validation), whose *validated* identity
is what Windows shows as the "Verified publisher". That identity comes from
the signing step (signtool / Inno Setup), not from this dialog; keep the name
here consistent with it.
"""
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPalette, QColor, QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QSizePolicy,
)

from .theme import ColorScheme, theme_manager, selection_bg
from .i18n import lang_manager, Strings
from .sidebar import APP_VERSION
from .updates import PAGE_RELEASES, check as check_updates
from . import icons as IC

# Display name (the repo is "PromptuinoUI"; the product is "Promptuino").
_APP_NAME = "Promptuino"
_DEVELOPER = "Mehdi KARIM"
_COPYRIGHT = "© 2026 Mehdi KARIM"
# Links shown under the developer block.
# Le depot public est en ligne depuis le 2026-08-28 (TODO #75). ⚠️ C'est
# `Promptuino` et non `PromptuinoUI` : le second est le depot de TRAVAIL, prive,
# qui porte en plus le TODO, les specs et les mesures. Ne pas le nommer ici.
_SOURCE_URL = "https://github.com/medkar/Promptuino"
_PATREON_URL = "https://patreon.com/Promptuino"

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

        # ── Mise a jour (TODO #77) ──────────────────────────────────
        # A LA DEMANDE ici ; le controle du demarrage, lui, est
        # silencieux. La difference est voulue : quelqu'un qui CLIQUE
        # attend une reponse, meme mauvaise (<< impossible de verifier
        # pour l'instant >>), alors qu'au demarrage un poste hors ligne
        # ne doit rien voir du tout.
        maj_col = QVBoxLayout()
        maj_col.setSpacing(4)
        self._btn_update = QPushButton(lang_manager.current.update_check)
        self._btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_update.setAutoDefault(False)
        self._btn_update.clicked.connect(self._on_check_updates)
        maj_col.addWidget(self._btn_update)
        self._lbl_update = QLabel("")
        self._lbl_update.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_update.setOpenExternalLinks(True)
        self._lbl_update.setWordWrap(True)
        maj_col.addWidget(self._lbl_update)
        header.addLayout(maj_col)
        self._maj_worker = None
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
        self._lbl_source.setOpenExternalLinks(True)
        gh_row.addWidget(self._lbl_source, alignment=Qt.AlignmentFlag.AlignVCenter)
        gh_row.addStretch()
        root.addLayout(gh_row)

        pat_row = QHBoxLayout()
        pat_row.setSpacing(6)
        self._lbl_pat_icon = QLabel()
        self._lbl_pat_icon.setFixedSize(15, 15)
        pat_row.addWidget(self._lbl_pat_icon, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._lbl_support = QLabel()
        self._lbl_support.setOpenExternalLinks(True)
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
        self._lbl_source.setText(
            self._link_html(lang_manager.current.about_source, _SOURCE_URL, c))
        self._lbl_pat_icon.setPixmap(
            IC.make_icon(IC.PATREON, c.accent, 15).pixmap(15, 15)
        )
        self._lbl_pat_icon.setStyleSheet("background: transparent;")
        self._lbl_support.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 9pt;"
        )
        self._lbl_support.setText(
            self._link_html(lang_manager.current.about_support, _PATREON_URL, c))
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

    @staticmethod
    def _link_html(libelle: str, url: str, c: ColorScheme) -> str:
        """« Libellé : <lien cliquable> ».

        ⚠️ La couleur d'un `<a>` NE SUIT PAS le `color:` de la feuille du
        QLabel — il faut la poser sur la balise. Le texte depend donc a la fois
        de la LANGUE et du THEME, d'ou l'appel depuis `apply_lang` ET
        `apply_theme`. Meme montage que `_lbl_credits` juste en dessous, qui
        avait deja ce besoin.
        """
        return (f'{libelle} : <a href="{url}" style="color: {c.accent};'
                f' text-decoration: none;">{url}</a>')

    # ── Mise a jour ───────────────────────────────────────────
    def _on_check_updates(self):
        """Lance la verification dans un THREAD.

        ⚠️ Jamais sur le fil graphique : l'appel reseau a un delai de 6 s, et
        une fenetre figee pendant 6 s serait pire que pas de bouton du tout.
        """
        if self._maj_worker is not None and self._maj_worker.isRunning():
            return
        s = lang_manager.current
        self._btn_update.setEnabled(False)
        self._lbl_update.setText(s.update_checking)

        class _Worker(QThread):
            fini = pyqtSignal(object)

            def run(self):
                self.fini.emit(check_updates())

        self._maj_worker = _Worker(self)
        self._maj_worker.fini.connect(self._on_update_result)
        self._maj_worker.start()

    def _on_update_result(self, tag):
        """`tag` = version plus recente, ou None.

        ⚠️ None ne veut PAS dire << a jour >> : il couvre aussi le hors-ligne
        et un build de developpement. On ne peut donc pas afficher << vous avez
        la derniere version >> sans mentir une fois sur deux. D'ou le second
        appel, qui distingue les deux cas.
        """
        from .updates import fetch_latest

        s = lang_manager.current
        self._btn_update.setEnabled(True)
        if tag:
            url = PAGE_RELEASES
            txt = s.update_available.format(v=tag.lstrip("v"))
            self._lbl_update.setText(
                f'{txt} <a href="{url}" style="color: '
                f'{theme_manager.current.accent};">{s.update_download}</a>')
            return
        # Pas de version plus recente : est-ce parce qu'on est a jour, ou
        # parce qu'on n'a pas pu demander ? Les deux se ressemblent et ne
        # veulent pas dire la meme chose -- d'ou le drapeau `joignable`.
        _, joignable = fetch_latest()
        self._lbl_update.setText(
            s.update_up_to_date if joignable else s.update_failed)

    # ── Lang ──────────────────────────────────────────────────
    def apply_lang(self, s: Strings):
        self.setWindowTitle(s.mn_about)
        self._lbl_desc.setText(s.mn_about_msg)
        self._lbl_dev_head.setText(s.about_developer)
        c = theme_manager.current
        self._lbl_source.setText(self._link_html(s.about_source, _SOURCE_URL, c))
        self._lbl_support.setText(
            self._link_html(s.about_support, _PATREON_URL, c))
        self._btn_update.setText(s.update_check)
        self._lbl_credits_head.setText(s.about_credits_title)
        self._lbl_credits_intro.setText(s.about_credits_intro)
        self._lbl_credits.setText(self._credits_html(theme_manager.current))
