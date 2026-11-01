"""
Settings window.
Structure: left panel (categories) | separator | right panel (content).
"""
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QEvent, QRectF
from PyQt6.QtGui import QPalette, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QWidget, QFileDialog, QStackedWidget,
    QRadioButton, QButtonGroup, QCheckBox,
)

from .theme import (
    ColorScheme, theme_manager, primary_button_qss, secondary_button_qss,
    radio_checkbox_qss,
)
from .i18n import lang_manager, LANGUAGE_NAMES, Strings
from .session import session
from .library_view import LibraryView
from . import icons as IC

_CATEGORY_W = 160
_ICON_SIZE   = 16
# Same constants as the sidebar nav (active card + phosphor bar).
_NAV_RADIUS = 6
_NAV_BAR_W  = 3


class _CategoryBtn(QPushButton):
    """Category button: SAME style as the sidebar nav — active card
    (background + phosphor bar on the left) painted with QPainter, GREEN text + icon on
    hover (the QSS only carries the text/font/padding; cf. sidebar.NavButton)."""

    def __init__(self, svg: str, label: str, parent=None):
        super().__init__(label, parent)
        self._svg    = svg
        self._active = False
        self._hover  = False
        self.setFixedHeight(40)
        self.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_theme(theme_manager.current)

    def set_active(self, active: bool):
        self._active = active
        self.apply_theme(theme_manager.current)

    def apply_theme(self, c: ColorScheme):
        if self._active:
            color = c.nav_active_text
        elif self._hover:
            color = c.signal_ok            # hover -> green text + icon
        else:
            color = c.nav_text
        self.setIcon(IC.make_icon(self._svg, color, _ICON_SIZE))
        weight = 700 if self._active else 600
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {color};
                font-size: 10pt; font-weight: {weight};
                text-align: left; padding: 0 12px;
            }}
        """)
        self.update()   # redraws card + bar

    def enterEvent(self, e):
        self._hover = True
        self.apply_theme(theme_manager.current)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.apply_theme(theme_manager.current)
        super().leaveEvent(e)

    def paintEvent(self, e):
        c = theme_manager.current
        # The ACTIVE item is marked ONLY by the green phosphor bar on its left
        # (user 2026-07-08: no filled background, cf. sidebar.NavButton); hover
        # is reflected only by the green text/icon.
        if self._active:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            card = QRectF(self.rect())
            path = QPainterPath()
            path.addRoundedRect(card, _NAV_RADIUS, _NAV_RADIUS)
            p.setClipPath(path)   # rounded ends -> soft liseret
            p.fillRect(
                QRectF(card.left(), card.top(), _NAV_BAR_W, card.height()),
                QColor(c.nav_active_border),
            )
            p.end()
        super().paintEvent(e)   # icon + text on top


def _compact_radio_style(c: ColorScheme) -> str:
    """Style of the radios on the Settings pages: same look as the AI model but
    compact — 10 pt font (= « Dossier actuel ») + reduced indicator (14 px)."""
    return radio_checkbox_qss(c, font_pt=10, font_weight=600, indicator_px=14)


def _compact_checkbox_style(c: ColorScheme) -> str:
    """Checkbox counterpart of `_compact_radio_style` — SAME recipe, same
    parameters. It was written inline twice (Privacy + Backstage pages) while
    the radio variant already had a name; giving it one is the whole point."""
    return radio_checkbox_qss(c, font_pt=10, font_weight=600, indicator_px=14)


class _LanguagePage(QWidget):
    """Language selection page: SAME radios as the AI model selection
    (real QRadioButton styled via radio_checkbox_qss — white/gray wireframe,
    green on hover and when checked)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._radios: dict[str, QRadioButton] = {}
        self._group = QButtonGroup(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        self._title = QLabel()
        layout.addWidget(self._title)
        layout.addSpacing(4)

        for code, name in LANGUAGE_NAMES.items():
            rb = QRadioButton(name)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(rb)
            self._radios[code] = rb
            rb.clicked.connect(lambda _checked=False, c=code: self._on_select(c))
            layout.addWidget(rb)

        layout.addStretch()

        self._radios[lang_manager.lang].setChecked(True)

        self.apply_lang(lang_manager.current)
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    def _on_select(self, code: str):
        lang_manager.set_language(code)

    def apply_lang(self, s: Strings):
        self._title.setText(s.settings_language)
        # Re-synchronize the checked radio (robustness if the language changes elsewhere).
        rb = self._radios.get(lang_manager.lang)
        if rb is not None:
            rb.setChecked(True)

    def apply_theme(self, c: ColorScheme):
        self._title.setStyleSheet(
            f"font-size: 13pt; font-weight: 700; margin-bottom: 8px;"
            f" color: {c.text_primary};"
        )
        radio_style = _compact_radio_style(c)
        for rb in self._radios.values():
            rb.setStyleSheet(radio_style)


class _ThemePage(QWidget):
    """Theme selection page (dark / light) — same compact radios as
    the Language page, wired to theme_manager (the choice is persisted in session
    via main._on_theme_changed)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._group = QButtonGroup(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        self._title = QLabel()
        layout.addWidget(self._title)
        layout.addSpacing(4)

        self._rb_dark  = QRadioButton()
        self._rb_light = QRadioButton()
        for rb in (self._rb_dark, self._rb_light):
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(rb)
            layout.addWidget(rb)
        self._rb_dark.clicked.connect(lambda: theme_manager.apply_dark())
        self._rb_light.clicked.connect(lambda: theme_manager.apply_light())

        layout.addStretch()

        self._sync()
        self.apply_lang(lang_manager.current)
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        theme_manager.changed.connect(lambda *_: self._sync())
        lang_manager.changed.connect(self.apply_lang)

    def _sync(self):
        """Checks the radio corresponding to the current theme."""
        (self._rb_dark if theme_manager.is_dark else self._rb_light).setChecked(True)

    def apply_lang(self, s: Strings):
        self._title.setText(s.settings_theme)
        self._rb_dark.setText(s.theme_dark)
        self._rb_light.setText(s.theme_light)

    def apply_theme(self, c: ColorScheme):
        self._title.setStyleSheet(
            f"font-size: 13pt; font-weight: 700; margin-bottom: 8px;"
            f" color: {c.text_primary};"
        )
        style = _compact_radio_style(c)
        self._rb_dark.setStyleSheet(style)
        self._rb_light.setStyleSheet(style)


class _StoragePage(QWidget):
    """Root folder selection page (projects + libraries)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        self._title = QLabel()
        layout.addWidget(self._title)

        self._description = QLabel()
        self._description.setWordWrap(True)
        layout.addWidget(self._description)

        layout.addSpacing(6)

        self._lbl_current = QLabel()
        layout.addWidget(self._lbl_current)

        # Current path: displays the absolute path, monospaced for
        # readability. Wordwrap for long paths.
        self._path_display = QLabel()
        self._path_display.setWordWrap(True)
        self._path_display.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._path_display)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_change = QPushButton()
        self._btn_change.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_change.setFixedHeight(32)
        self._btn_change.clicked.connect(self._on_change)
        btn_row.addWidget(self._btn_change)

        self._btn_reset = QPushButton()
        self._btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset.setFixedHeight(32)
        self._btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(self._btn_reset)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addSpacing(6)

        self._warning = QLabel()
        self._warning.setWordWrap(True)
        layout.addWidget(self._warning)

        layout.addStretch()

        self.apply_lang(lang_manager.current)
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)
        session.workspace_root_changed.connect(lambda _p: self._refresh_path())

    def _refresh_path(self):
        s = lang_manager.current
        path = session.workspace_root
        txt = str(path)
        if session.is_workspace_root_default():
            txt += s.settings_storage_default_suffix
        self._path_display.setText(txt)
        # The "Reinitialiser" button only makes sense if a custom path is active
        self._btn_reset.setEnabled(not session.is_workspace_root_default())

    def _on_change(self):
        s = lang_manager.current
        start = str(session.workspace_root)
        # Suspend the auto-close of the SettingsDialog while the
        # QFileDialog (Windows native) is shown, otherwise the loss of activation closes
        # the parent and destroys the file dialog.
        dlg = self.window()
        prev = getattr(dlg, "_suppress_close", False)
        if hasattr(dlg, "_suppress_close"):
            dlg._suppress_close = True
        try:
            chosen = QFileDialog.getExistingDirectory(
                self, s.settings_storage_picker_title, start
            )
        finally:
            if hasattr(dlg, "_suppress_close"):
                dlg._suppress_close = prev
        if not chosen:
            return
        session.workspace_root = chosen

    def _on_reset(self):
        # Reset = clears the custom value -> reverts to the default path
        session.workspace_root = ""

    def apply_lang(self, s: Strings):
        self._title.setText(s.settings_storage_title)
        self._description.setText(s.settings_storage_description)
        self._lbl_current.setText(s.settings_storage_current)
        self._btn_change.setText(s.settings_storage_change)
        self._btn_reset.setText(s.settings_storage_reset)
        self._warning.setText(s.settings_storage_warning)
        self._refresh_path()

    def apply_theme(self, c: ColorScheme):
        self._title.setStyleSheet(
            f"font-size: 13pt; font-weight: 700; margin-bottom: 8px;"
            f" color: {c.text_primary};"
        )
        self._description.setStyleSheet(
            f"font-size: 10pt; color: {c.text_secondary};"
        )
        self._lbl_current.setStyleSheet(
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
        # "Change" = primary (filled), "Reset" = secondary
        # (wireframe); agreed centralized style (green on hover).
        self._btn_change.setStyleSheet(primary_button_qss(c, padding="4px 14px"))
        self._btn_reset.setStyleSheet(secondary_button_qss(c, padding="4px 14px"))
        self._warning.setStyleSheet(
            f"font-size: 9pt; color: {c.text_secondary}; font-style: italic;"
        )


class _PrivacyPage(QWidget):
    """Confidentialité : une DECLARATION, plus un réglage.

    La case d'opt-out a disparu avec la télémétrie (TODO #72, 2026-08-28).
    La page reste : retirer la collecte ET la page laisserait l'utilisateur
    sans réponse à « qu'est-ce que ça envoie ? ». Elle dit maintenant que
    rien n'est collecté ni envoyé, ce qui est vérifiable dans le code."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        self._title = QLabel(lang_manager.current.settings_privacy)
        layout.addWidget(self._title)
        layout.addSpacing(4)

        self._desc = QLabel(lang_manager.current.settings_privacy_desc)
        self._desc.setWordWrap(True)
        layout.addWidget(self._desc)

        layout.addStretch()

        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        # Seule des 5 pages de ce fichier a ne pas avoir d'apply_lang : ses
        # 3 chaines etaient ecrites en dur, donc en francais dans les 4
        # langues. Meme branchement que ses voisines.
        lang_manager.changed.connect(self.apply_lang)

    def apply_lang(self, s: Strings):
        self._title.setText(s.settings_privacy)
        self._desc.setText(s.settings_privacy_desc)

    def apply_theme(self, c: ColorScheme):
        self._title.setStyleSheet(
            f"font-size: 13pt; font-weight: 700; margin-bottom: 8px;"
            f" color: {c.text_primary};"
        )
        self._desc.setStyleSheet(
            f"font-size: 10pt; color: {c.text_secondary};"
        )


class _BackstagePage(QWidget):
    """« Coulisses du prompt » (#42) — moved here from the Help menu.

    It used to be `mn_debug_prompt`, « Mode débug — afficher le prompt IA »,
    a checkable action in the Help menu whose state deliberately reset on every
    launch because it was a developer feature. It is not one: it shows the
    learner what the app builds out of what they wrote. The name went, and the
    non-persistence went with it — nobody re-ticks a working preference at
    every launch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        self._title = QLabel()
        layout.addWidget(self._title)
        layout.addSpacing(4)

        self._chk = QCheckBox()
        self._chk.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chk.setChecked(session.prompt_backstage)
        self._chk.toggled.connect(self._on_toggled)
        layout.addWidget(self._chk)

        self._desc = QLabel()
        self._desc.setWordWrap(True)
        layout.addWidget(self._desc)

        layout.addStretch()

        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    @staticmethod
    def _on_toggled(checked: bool):
        session.prompt_backstage = bool(checked)

    def apply_lang(self, s: Strings):
        self._title.setText(s.settings_backstage)
        self._chk.setText(s.backstage_enable)
        self._desc.setText(s.backstage_desc)

    def apply_theme(self, c: ColorScheme):
        self._title.setStyleSheet(
            f"font-size: 13pt; font-weight: 700; margin-bottom: 8px;"
            f" color: {c.text_primary};"
        )
        self._chk.setStyleSheet(_compact_checkbox_style(c))
        self._desc.setStyleSheet(f"font-size: 10pt; color: {c.text_secondary};")


class SettingsDialog(QDialog):
    """Modal settings window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Sized to host the embedded Library manager (list + search) while
        # staying a modal — the other pages just have more whitespace.
        self.setMinimumSize(560, 440)
        self.resize(640, 520)
        # Prevents the auto-close on deactivation while a sub-dialog
        # (e.g. QFileDialog Windows native) is open.
        self._suppress_close = False
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    # ── Construction ──────────────────────────────────────────

    def _build(self):
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel (categories) ───────────────────────
        self._left = QWidget()
        self._left.setFixedWidth(_CATEGORY_W)
        left_layout = QVBoxLayout(self._left)
        left_layout.setContentsMargins(8, 16, 8, 16)
        left_layout.setSpacing(2)

        self._btn_lang = _CategoryBtn(IC.GLOBE, lang_manager.current.settings_language)
        self._btn_lang.set_active(True)
        self._btn_lang.clicked.connect(lambda: self._switch_page(0))
        left_layout.addWidget(self._btn_lang)

        self._btn_theme = _CategoryBtn(IC.MOON, lang_manager.current.settings_theme)
        self._btn_theme.clicked.connect(lambda: self._switch_page(1))
        left_layout.addWidget(self._btn_theme)

        self._btn_storage = _CategoryBtn(IC.FOLDER, lang_manager.current.settings_storage)
        self._btn_storage.clicked.connect(lambda: self._switch_page(2))
        left_layout.addWidget(self._btn_storage)

        self._btn_libraries = _CategoryBtn(IC.LIBRARY, lang_manager.current.nav_bibliotheque)
        self._btn_libraries.clicked.connect(lambda: self._switch_page(3))
        left_layout.addWidget(self._btn_libraries)

        self._btn_privacy = _CategoryBtn(
            IC.EYE, lang_manager.current.settings_privacy)
        self._btn_privacy.clicked.connect(lambda: self._switch_page(4))
        left_layout.addWidget(self._btn_privacy)

        self._btn_backstage = _CategoryBtn(
            IC.TERMINAL, lang_manager.current.settings_backstage)
        self._btn_backstage.clicked.connect(lambda: self._switch_page(5))
        left_layout.addWidget(self._btn_backstage)

        left_layout.addStretch()

        root.addWidget(self._left)

        # ── Vertical separator ───────────────────────────────
        self._vsep = QWidget()
        self._vsep.setFixedWidth(1)
        root.addWidget(self._vsep)

        # ── Right panel (content) ───────────────────────────
        self._right = QWidget()
        right_layout = QVBoxLayout(self._right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._lang_page      = _LanguagePage()
        self._theme_page     = _ThemePage()
        self._storage_page   = _StoragePage()
        self._libraries_page = LibraryView(compact=True)
        self._privacy_page   = _PrivacyPage()
        self._backstage_page = _BackstagePage()
        self._stack.addWidget(self._lang_page)       # index 0
        self._stack.addWidget(self._theme_page)      # index 1
        self._stack.addWidget(self._storage_page)    # index 2
        self._stack.addWidget(self._libraries_page)  # index 3
        self._stack.addWidget(self._privacy_page)    # index 4
        self._stack.addWidget(self._backstage_page)  # index 5
        right_layout.addWidget(self._stack)

        # Changing the root folder (Storage page) moves the libraries workspace:
        # refresh the embedded list so it reflects the new location live.
        session.workspace_root_changed.connect(
            lambda _p: self._libraries_page.refresh()
        )

        root.addWidget(self._right, stretch=1)

    def _switch_page(self, index: int):
        self._stack.setCurrentIndex(index)
        self._btn_lang.set_active(index == 0)
        self._btn_theme.set_active(index == 1)
        self._btn_storage.set_active(index == 2)
        self._btn_libraries.set_active(index == 3)
        self._btn_privacy.set_active(index == 4)
        self._btn_backstage.set_active(index == 5)

    def showEvent(self, event):
        # Catch libraries installed elsewhere (e.g. a Studio compile) since the
        # dialog was last shown.
        super().showEvent(event)
        self._libraries_page.refresh()

    # ── Theme ─────────────────────────────────────────────────

    @staticmethod
    def _set_bg(widget: QWidget, hex_color: str):
        p = widget.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(hex_color))
        widget.setPalette(p)
        widget.setAutoFillBackground(True)

    def apply_theme(self, c: ColorScheme):
        self._set_bg(self, c.main_bg)
        self._set_bg(self._left, c.sidebar_bg)
        self._set_bg(self._right, c.main_bg)
        self._vsep.setStyleSheet(f"background-color: {c.border};")
        self._btn_lang.apply_theme(c)
        self._btn_theme.apply_theme(c)
        self._btn_storage.apply_theme(c)
        self._btn_libraries.apply_theme(c)
        self._btn_privacy.apply_theme(c)
        self._lang_page.apply_theme(c)
        self._theme_page.apply_theme(c)
        self._storage_page.apply_theme(c)
        self._libraries_page.apply_theme(c)
        self._privacy_page.apply_theme(c)

    # ── Close on outside click ───────────────────────────

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            if not self._suppress_close:
                self.close()
        super().changeEvent(event)

    # ── Lang ──────────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        self.setWindowTitle(s.settings_title)
        self._btn_lang.setText(s.settings_language)
        self._btn_theme.setText(s.settings_theme)
        self._btn_storage.setText(s.settings_storage)
        self._btn_libraries.setText(s.nav_bibliotheque)
        self._btn_privacy.setText(s.settings_privacy)
        self._btn_backstage.setText(s.settings_backstage)
        # Update the icons to keep the correct color after setText
        self._btn_lang.apply_theme(theme_manager.current)
        self._btn_theme.apply_theme(theme_manager.current)
        self._btn_storage.apply_theme(theme_manager.current)
        self._btn_libraries.apply_theme(theme_manager.current)
        self._btn_privacy.apply_theme(theme_manager.current)
        self._btn_backstage.apply_theme(theme_manager.current)
