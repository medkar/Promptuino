"""
Collapsible side navigation panel (full height).
- Expanded : 200 px — logo + version, then icon + label
- Collapsed:  72 px — logo only (version hidden), then icons only
  (wide enough to keep the logo visible)
"""
from PyQt6.QtCore import (
    Qt, pyqtSignal, QSize, QRectF, QPropertyAnimation, QEasingCurve,
    QParallelAnimationGroup,
)
from pathlib import Path
from PyQt6.QtGui import QPalette, QColor, QPainter, QPainterPath, QIcon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy,
)

from .theme import ColorScheme, theme_manager, HEADER_H
from .i18n import lang_manager, Strings
from .session import session
from . import icons as IC

EXPANDED_W  = 200
COLLAPSED_W = 72   # wide enough to keep the logo (56 px) centered once collapsed
ICON_SIZE   = 18
LOGO_SIZE   = 56   # logo visible expanded AND collapsed -> we make it big
                   # (header 64 px -> ~4 px of top/bottom margin)
HEADER_MARGIN_EXPANDED  = 12
HEADER_MARGIN_COLLAPSED = (COLLAPSED_W - LOGO_SIZE) // 2   # centers the collapsed logo
# La version vit dans `ui/version.py` : une seule source, reecrite par la
# CI avec le tag. Ce ré-export garde les appelants historiques
# (`about_dialog`) qui l'importaient d'ici.
from .version import display_version
APP_VERSION = display_version()

# Nav tab: card + accent bar drawn with QPainter (Qt's QSS renders
# border-radius + thick border-left poorly → smeared corners). cf. spec § 3 « A: paintEvent ».
NAV_RADIUS = 6   # corner radius of the active/hovered card
NAV_BAR_W  = 3   # width of the phosphor bar of the active item

# (tab_id, svg_str, label_key) — label_key is an attribute of Strings
NAV_ITEMS: list[tuple[str, str, str]] = [
    ("console",      IC.TERMINAL,         "nav_studio"),
    ("composants",   IC.LAYERS,           "nav_composants"),
    ("projets",      IC.FOLDER,           "nav_projets"),
    ("carte",        IC.CPU,              "nav_carte"),
    ("ia",           IC.SPARKLES,         "nav_ia"),
]


class NavButton(QPushButton):
    """Navigation button with dynamically colored SVG icon."""

    def __init__(self, svg: str, label_key: str, parent=None):
        super().__init__(parent)
        self._svg       = svg
        self._label_key = label_key
        self._active    = False
        self._icon_only = False
        self._hover     = False

        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.apply_theme(theme_manager.current)
        lang_manager.changed.connect(self.apply_lang)

    def _label(self) -> str:
        return getattr(lang_manager.current, self._label_key)

    def set_active(self, active: bool):
        self._active = active
        self.apply_theme(theme_manager.current)

    def set_icon_only(self, icon_only: bool):
        self._icon_only = icon_only
        self.setFixedHeight(40 if icon_only else 44)   # 44 expanded / 40 collapsed (spec)
        self.apply_theme(theme_manager.current)

    def apply_lang(self, _s: Strings):
        self.apply_theme(theme_manager.current)

    def apply_theme(self, c: ColorScheme):
        # The QSS carries ONLY the text/font/padding; the active card's
        # background and its phosphor bar are painted in paintEvent (sharp rendering).
        # Hover NO LONGER lays down a background: it colors the text + icon green.
        label = self._label()
        if self._active:
            color = c.nav_active_text
        elif self._hover:
            color = c.signal_ok            # hover -> green text + icon
        else:
            color = c.nav_text
        self.setIcon(IC.make_icon(self._svg, color, ICON_SIZE))
        self.setToolTip(label)

        if self._icon_only:
            self.setText("")
            align, padding = "center", "0"
        else:
            self.setText(f"  {label}")
            # The bar is painted (out of flow) → same padding active/inactive,
            # the icons stay aligned (the bar passes under the left margin).
            align, padding = "left", "0 14px"

        weight = 600 if self._active else 500
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {color};
                font-size: 10pt; font-weight: {weight};
                text-align: {align}; padding: {padding};
            }}
            QPushButton:disabled {{ color: {c.disabled_text}; }}
        """)
        self.update()   # redraws card + bar

    def enterEvent(self, e):
        self._hover = True
        self.apply_theme(theme_manager.current)   # recolors text + icon green
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.apply_theme(theme_manager.current)   # restores the normal color
        super().leaveEvent(e)

    def paintEvent(self, e):
        c = theme_manager.current
        # The ACTIVE item is marked ONLY by the green phosphor bar on its left
        # (user 2026-07-08: no more filled background). Hover shows as green
        # text/icon; the active state adds the brighter nav_active_text + bar.
        if self._active:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            card = QRectF(self.rect())
            # The bar keeps the rounded ends of the (now invisible) card so it
            # reads as a soft liseret rather than a hard rectangle.
            path = QPainterPath()
            path.addRoundedRect(card, NAV_RADIUS, NAV_RADIUS)
            p.setClipPath(path)
            p.fillRect(
                QRectF(card.left(), card.top(), NAV_BAR_W, card.height()),
                QColor(c.nav_active_border),
            )
            p.end()
        super().paintEvent(e)   # icon + text on top


class Sidebar(QWidget):
    """Side navigation panel — full height."""

    tab_changed  = pyqtSignal(str)
    width_changed = pyqtSignal(int)  # emitted on collapse/expand
    expanded_changed = pyqtSignal(bool)  # emitted when the expanded/collapsed state changes
    settings_requested = pyqtSignal()  # Settings button at the bottom of the navbar

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded  = True
        self._active_id = NAV_ITEMS[0][0]
        self._buttons: dict[str, NavButton] = {}
        self._build()
        self.setFixedWidth(EXPANDED_W)

        # Collapse/expand animation: min+maxWidth, 180 ms, OutCubic (spec § 3).
        # Kept on self so it isn't collected before it finishes.
        self._anim = QParallelAnimationGroup(self)
        self._anim_min = QPropertyAnimation(self, b"minimumWidth")
        self._anim_max = QPropertyAnimation(self, b"maximumWidth")
        for a in (self._anim_min, self._anim_max):
            a.setDuration(180)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.addAnimation(a)
        # The topbar's mode selector follows the width during the animation.
        self._anim_max.valueChanged.connect(lambda v: self.width_changed.emit(int(v)))
        # Expand: show the labels AFTER the animation finishes (otherwise they
        # cram together during the growth); on collapse they are hidden beforehand
        # (cf toggle_expand). Spec Phase 3 §2.
        self._anim.finished.connect(self._on_anim_finished)

        theme_manager.changed.connect(self.apply_theme)
        # Restore the persisted collapsed state (without animation).
        if session.sidebar_collapsed:
            self._restore_collapsed_no_anim()

    # ── Construction ──────────────────────────────────────────

    def _build(self):
        c = theme_manager.current

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header: logo + name + version ─────────────────────
        self._header = QWidget()
        self._header.setFixedHeight(HEADER_H)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(10)

        # Logo (CPU icon for now)
        self._logo_btn = QPushButton()
        self._logo_btn.setFixedSize(LOGO_SIZE, LOGO_SIZE)
        self._logo_btn.setIconSize(QSize(LOGO_SIZE, LOGO_SIZE))
        self._logo_btn.setStyleSheet("background: transparent; border: none;")
        self._logo_btn.setCursor(Qt.CursorShape.ArrowCursor)

        # Texts: only the version. The « Promptuino » name is removed: the
        # logo (« Prompt>uino » icon) already carries it -> redundant text.
        self._text_widget = QWidget()
        text_layout = QVBoxLayout(self._text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        self._lbl_version = QLabel(APP_VERSION)
        self._lbl_version.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 8pt; border: none;"
        )

        text_layout.addWidget(self._lbl_version)

        # Width to content (no expansion): combined with the two stretches
        # below, the logo + version block is CENTERED in the header.
        self._text_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        # Collapse/expand toggle button — REPLACED by the chevron centered on the
        # separation bar (cf MainWindow._CollapseHandle). We keep it
        # built (apply_theme still references it) but hidden.
        self._btn_toggle = QPushButton()
        self._btn_toggle.setFixedSize(28, 28)
        self._btn_toggle.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_toggle.clicked.connect(self.toggle_expand)
        self._btn_toggle.hide()

        # Stretches on either side -> logo + version block centered in the
        # header cell (expanded). Collapsed (version hidden): the logo alone
        # stays centered by the same stretches.
        header_layout.addStretch(1)
        header_layout.addWidget(self._logo_btn)
        header_layout.addWidget(self._text_widget)
        header_layout.addStretch(1)
        header_layout.addWidget(self._btn_toggle)
        root.addWidget(self._header)

        # ── Separator ────────────────────────────────────────
        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.HLine)
        self._sep.setFixedHeight(1)
        root.addWidget(self._sep)
        root.addSpacing(8)

        # ── Navigation items ───────────────────────────────
        nav_container = QWidget()
        nav_container.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(8, 0, 8, 0)
        nav_layout.setSpacing(2)

        for tab_id, svg, label in NAV_ITEMS:
            btn = NavButton(svg, label)
            btn.set_active(tab_id == self._active_id)
            btn.clicked.connect(lambda _, tid=tab_id: self._on_click(tid))
            self._buttons[tab_id] = btn
            nav_layout.addWidget(btn)

        root.addWidget(nav_container)
        root.addStretch()

        # ── Settings: at the bottom of the navbar (moved from the topbar) ──
        bottom = QWidget()
        bottom.setStyleSheet("background: transparent;")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(8, 0, 8, 8)
        bottom_layout.setSpacing(2)
        self._settings_btn = NavButton(IC.SETTINGS, "topbar_settings")
        self._settings_btn.clicked.connect(lambda: self.settings_requested.emit())
        bottom_layout.addWidget(self._settings_btn)
        root.addWidget(bottom)

        self.apply_theme(c)

    # ── Theme ─────────────────────────────────────────────────

    @staticmethod
    def _set_bg(widget: QWidget, hex_color: str):
        p = widget.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(hex_color))
        widget.setPalette(p)
        widget.setAutoFillBackground(True)

    def _update_toggle_icon(self):
        c = theme_manager.current
        svg = IC.PANEL_LEFT_CLOSE if self._expanded else IC.PANEL_LEFT_OPEN
        self._btn_toggle.setIcon(IC.make_icon(svg, c.topbar_btn_text, ICON_SIZE))

    def apply_theme(self, c: ColorScheme):
        self._set_bg(self, c.sidebar_bg)
        self._set_bg(self._header, c.sidebar_bg)
        self._sep.setStyleSheet(f"background-color: {c.border}; border: none;")
        # Real logo (« Prompt>uino » icon, multicolor) — variant depending on the
        # theme. Rendered as-is via QIcon (not make_icon which re-colorizes to mono).
        _variant = "dark" if theme_manager.is_dark else "light"
        _logo = (Path(__file__).resolve().parent.parent / "assets" / "logo"
                 / f"icon-transparent-{_variant}.svg")
        self._logo_btn.setIcon(QIcon(str(_logo)))
        self._lbl_version.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 8pt; border: none;"
        )
        self._btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {c.border};
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {c.nav_hover_bg}; }}
        """)
        self._update_toggle_icon()
        for btn in self._buttons.values():
            btn.apply_theme(c)
        self._settings_btn.apply_theme(c)

    # ── Toggle expand/collapse ─────────────────────────────────

    def is_expanded(self) -> bool:
        return self._expanded

    def toggle_expand(self):
        self._expanded = not self._expanded
        session.sidebar_collapsed = not self._expanded
        self._update_toggle_icon()
        self.expanded_changed.emit(self._expanded)
        if not self._expanded:
            # Collapse: hide the labels BEFORE shrinking.
            self._apply_label_visibility(False)
        # Expand: the labels will be shown at the end of the animation
        # (_on_anim_finished), so as not to cram them during the growth.
        end = EXPANDED_W if self._expanded else COLLAPSED_W
        self._anim.stop()
        for a in (self._anim_min, self._anim_max):
            a.setStartValue(self.width())
            a.setEndValue(end)
        self._anim.start()

    def _apply_label_visibility(self, visible: bool):
        """Version + nav labels: visible (expanded) or hidden (collapsed,
        icons only). The logo, for its part, stays ALWAYS visible — it is just
        re-centered when collapsing (tightened header margins)."""
        self._text_widget.setVisible(visible)
        margin = HEADER_MARGIN_EXPANDED if visible else HEADER_MARGIN_COLLAPSED
        self._header.layout().setContentsMargins(margin, 0, margin, 0)
        for btn in self._buttons.values():
            btn.set_icon_only(not visible)
        self._settings_btn.set_icon_only(not visible)

    def _on_anim_finished(self):
        # On expand only: we reveal the labels once the room has been made.
        if self._expanded:
            self._apply_label_visibility(True)

    def _restore_collapsed_no_anim(self):
        """Applies the collapsed state at startup, without animation."""
        self._expanded = False
        self._update_toggle_icon()
        self._apply_label_visibility(False)
        self.setFixedWidth(COLLAPSED_W)

    # ── Internal ──────────────────────────────────────────────

    def _on_click(self, tab_id: str):
        if tab_id == self._active_id:
            return
        self._buttons[self._active_id].set_active(False)
        self._active_id = tab_id
        self._buttons[tab_id].set_active(True)
        self.tab_changed.emit(tab_id)

    # ── Public API ────────────────────────────────────────────

    def set_active_tab(self, tab_id: str):
        if tab_id in self._buttons and tab_id != self._active_id:
            self._buttons[self._active_id].set_active(False)
            self._active_id = tab_id
            self._buttons[tab_id].set_active(True)
