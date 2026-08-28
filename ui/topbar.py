"""
Top bar of the main window.
Left    : button to collapse/expand the sidebar.
Center  : mode selector (Beginner / Intermediate / Advanced).
Right   : animated dark/light toggle + settings button.
"""
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRectF
from PyQt6.QtGui import QPalette, QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QSizePolicy
from .theme import ColorScheme, theme_manager, HEADER_H, install_icon_hover
from .i18n import lang_manager, Strings
from .toggle_switch import ThemeToggle
from . import icons as IC

TOPBAR_H  = HEADER_H
ICON_SIZE = 18

MODES = ["beginner", "intermediate", "advanced"]

# Mode selector: MODERATE rounded corners (rounded rect), not a pill
# (the ends must not be half-circles). Container aligned with the
# border-radius of the topbar icon buttons (gear/chat) = 6 px.
SELECTOR_RADIUS     = 6    # container corners (= topbar icon buttons)
SELECTOR_SEG_RADIUS = 6    # active segment corners


# ── Mode selector ──────────────────────────────────────────────────────────────

class ModeSelector(QWidget):
    """
    Segmented control with 3 text segments: Beginner | Intermediate | Advanced.
    Same pill style as ThemeToggle, background painted via paintEvent.
    """

    mode_changed = pyqtSignal(str)   # emits the mode id ("beginner", …)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = "beginner"
        # Veto optionnel du changement de mode (callback(mode_id) -> bool).
        # Le studio l'utilise pour bloquer le switch pendant une génération /
        # un upload (sinon on masque/vide une opération en cours).
        self._can_switch = None
        self._btns: dict[str, QPushButton] = {}
        self._build()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        for mode_id in MODES:
            btn = QPushButton()
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, m=mode_id: self._select(m))
            self._btns[mode_id] = btn
            layout.addWidget(btn)
        self.setFixedHeight(36)
        # Free width: FR/EN/ES/IT labels of varying lengths (spec § 3).
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.apply_lang(lang_manager.current)

    def _select(self, mode_id: str):
        if mode_id == self._active:
            return
        # Veto (ex. génération/upload en cours) : on refuse AVANT de changer
        # l'état -> pas de repaint ni de signal, le bouton reste sur le mode
        # courant.
        if self._can_switch is not None and not self._can_switch(mode_id):
            return
        self._active = mode_id
        self.apply_theme(theme_manager.current)
        self.mode_changed.emit(mode_id)

    @property
    def active_mode(self) -> str:
        return self._active

    def paintEvent(self, event):
        # Container AND active pill painted with QPainter: Qt's QSS renders the
        # rounded corners poorly (smeared/misaligned pill). cf. spec § 3 « A: paintEvent ».
        c = theme_manager.current
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(c.input_bg))
        p.setPen(QPen(QColor(c.border), 1))
        p.drawRoundedRect(r, SELECTOR_RADIUS, SELECTOR_RADIUS)
        # Active segment background (inverted primary button), concentric corners.
        btn = self._btns.get(self._active)
        if btn is not None:
            g = QRectF(btn.geometry())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c.btn_primary_bg))
            p.drawRoundedRect(g, SELECTOR_SEG_RADIUS, SELECTOR_SEG_RADIUS)
        p.end()

    def apply_theme(self, c: ColorScheme):
        # The QSS only carries text/font/padding; the active pill is painted
        # in paintEvent (crisp rendering). Active text = btn_primary_text.
        self.update()
        for mode_id, btn in self._btns.items():
            active = (mode_id == self._active)
            color = c.btn_primary_text if active else c.nav_text
            hover = "" if active else f"QPushButton:hover {{ color: {c.signal_ok}; }}"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {color};
                    font-size: 10pt; font-weight: 600;
                    padding: 0 18px;
                }}
                {hover}
            """)

    def apply_lang(self, s: Strings):
        labels = {
            "beginner":     s.mode_beginner,
            "intermediate": s.mode_intermediate,
            "advanced":     s.mode_advanced,
        }
        for mode_id, btn in self._btns.items():
            btn.setText(labels[mode_id])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_btn(tooltip: str) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(36, 36)
    btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(tooltip)
    return btn


class TopBar(QWidget):
    # (The chat button was removed; settings are moved into the sidebar.)

    undo_clicked = pyqtSignal()
    redo_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(TOPBAR_H)
        self._build()
        theme_manager.changed.connect(self.apply_theme)

    # ── Construction ──────────────────────────────────────────

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 12, 0)
        layout.setSpacing(8)

        layout.addStretch()

        # Right side: only the theme toggle. The chat button was removed
        # (the collapse happens in the chat panel) and settings are moved
        # to the bottom of the sidebar.
        self._theme_toggle = ThemeToggle()
        layout.addWidget(self._theme_toggle)

        # Mode selector: parented to the topbar but positioned manually
        # to be centered relative to the main window (and not to the
        # topbar alone, which is offset by the sidebar).
        self._mode_selector = ModeSelector(self)
        self._mode_selector.setVisible(False)
        self._sidebar_ref: QWidget | None = None

        # Undo/redo arrows, just left of the mode selector (Studio only —
        # same visibility as the selector). Positioned manually alongside
        # it in _position_mode_selector. NoFocus: a click must not steal
        # the focus from the editor/prompt (StudioView.undo() delegates to
        # the focused text widget).
        self._btn_undo = _make_btn("")
        self._btn_redo = _make_btn("")
        for btn in (self._btn_undo, self._btn_redo):
            btn.setParent(self)
            btn.setVisible(False)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; }"
            )
        # Keep the hover filters alive (gray at rest -> green on hover).
        self._undo_hover = install_icon_hover(self._btn_undo, IC.UNDO, ICON_SIZE)
        self._redo_hover = install_icon_hover(self._btn_redo, IC.REDO, ICON_SIZE)
        self._btn_undo.clicked.connect(self.undo_clicked.emit)
        self._btn_redo.clicked.connect(self.redo_clicked.emit)

        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        lang_manager.changed.connect(self.apply_lang)
        # When the language changes, the mode selector labels
        # change width: we must reposition/resize.
        lang_manager.changed.connect(lambda _s: self._position_mode_selector())

    @property
    def mode_selector(self) -> ModeSelector:
        return self._mode_selector

    def set_sidebar(self, sidebar: QWidget):
        """Lets the topbar know the current sidebar width
        in order to center the mode selector relative to the window."""
        self._sidebar_ref = sidebar
        self._position_mode_selector()

    def set_mode_visible(self, visible: bool):
        self._mode_selector.setVisible(visible)
        self._btn_undo.setVisible(visible)
        self._btn_redo.setVisible(visible)
        if visible:
            self._position_mode_selector()

    def _position_mode_selector(self):
        if not self._mode_selector.isVisible():
            return
        sel_w = self._mode_selector.sizeHint().width()
        sel_h = self._mode_selector.sizeHint().height()
        # Centered WITHIN the topbar = exactly the space between the right of the
        # sidebar and the left of the assistant (the topbar occupies this space, the
        # chat being a full-height strip to its right). So we do NOT take
        # the chat width into account: centering on the local topbar.
        x = max(0, (self.width() - sel_w) // 2)
        y = (self.height() - sel_h) // 2
        self._mode_selector.setGeometry(x, y, sel_w, sel_h)
        self._mode_selector.raise_()
        # Undo/redo arrows anchored at the LEFT edge of the topbar
        # (same 8px margin as the layout): [undo][redo] ... selector.
        btn_w = self._btn_undo.width()
        by = (self.height() - self._btn_undo.height()) // 2
        self._btn_undo.move(8, by)
        self._btn_redo.move(8 + btn_w + 2, by)
        self._btn_undo.raise_()
        self._btn_redo.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._position_mode_selector()

    def apply_lang(self, s: Strings):
        self._btn_undo.setToolTip(s.topbar_undo_tip)
        self._btn_redo.setToolTip(s.topbar_redo_tip)

    # ── Theme ─────────────────────────────────────────────────

    def apply_theme(self, c: ColorScheme):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(c.topbar_bg))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        # No more icon buttons in the topbar (chat removed, settings in
        # sidebar); the theme toggle manages its own style.
