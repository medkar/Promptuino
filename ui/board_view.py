"""
Target board selection view (first sidebar tab).
Two sections with radio buttons:
  - Automatic detection (selected by default)
  - Manual selection (grayed out until activated)
"""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QRadioButton, QButtonGroup,
    QScrollArea,
)

from .theme import (
    ColorScheme, theme_manager, radio_checkbox_qss, install_icon_hover, combo_qss,
    primary_button_qss,
)
from .i18n import lang_manager, Strings
from .board_manager import (
    BOARDS, BoardState, board_manager, COMING_SOON_ENVS, detect_board,
)
from . import icons as IC


# ── Environment button ─────────────────────────────────────────────────────────

class _EnvBtn(QPushButton):

    def __init__(self, env_id: str, label: str, parent=None,
                 coming_soon: bool = False):
        super().__init__(label, parent)
        self.env_id    = env_id
        self._selected = False
        self._coming_soon = coming_soon
        self.setFixedHeight(48)
        # Coming soon (ESP32): stays ENABLED (for the hover tooltip) but
        # not selectable (cf _on_env_select) and rendered grayed out.
        self.setCursor(Qt.CursorShape.PointingHandCursor if not coming_soon
                       else Qt.CursorShape.ArrowCursor)
        self._refresh()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._refresh()

    def _refresh(self):
        c = theme_manager.current
        if self._coming_soon:
            # Grayed out "coming soon": no hover, not selectable.
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {c.disabled_text};
                    border: 1px solid {c.border};
                    border-radius: 6px;
                    font-size: 10pt;
                    font-weight: 600;
                }}
            """)
            return
        if self._selected:
            # Selected: SAME style as hover (GREEN border + text, transparent
            # background — no more greenish nav_active background). Bold to
            # distinguish it from a plain hover (user request).
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {c.signal_ok};
                    border: 1px solid {c.signal_ok};
                    border-radius: 6px;
                    font-size: 10pt; font-weight: 700;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {c.text_primary};
                    border: 1px solid {c.border};
                    border-radius: 6px;
                    font-size: 10pt;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    color: {c.signal_ok};
                    border-color: {c.signal_ok};
                }}
                QPushButton:disabled {{
                    color: {c.text_secondary};
                    border-color: {c.border};
                }}
            """)

    def apply_theme(self):
        self._refresh()


# ── Main view ──────────────────────────────────────────────────────────────────

class BoardView(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._env_btns: dict[str, _EnvBtn] = {}
        self._had_connection = False
        self._build()
        self._sync_from_manager()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)
        board_manager.state_changed.connect(self._on_state_changed)

    # ── Construction ──────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll)

        self._card = QWidget()
        self._card.setFixedWidth(540)
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self._card, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._scroll.setWidget(container)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(0, 40, 0, 40)
        layout.setSpacing(0)

        # ── AUTO radio button ─────────────────────────────────
        self._radio_auto = QRadioButton()
        self._radio_auto.setChecked(True)
        self._radio_auto.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._radio_auto)
        layout.addSpacing(6)

        # Auto section content (indented)
        self._auto_content = QWidget()
        auto_layout = QVBoxLayout(self._auto_content)
        auto_layout.setContentsMargins(28, 0, 0, 0)
        auto_layout.setSpacing(0)

        self._lbl_auto_subtitle = QLabel()
        self._lbl_auto_subtitle.setWordWrap(True)
        auto_layout.addWidget(self._lbl_auto_subtitle)
        auto_layout.addSpacing(12)

        self._auto_status = QLabel()
        self._auto_status.setTextFormat(Qt.TextFormat.RichText)
        auto_layout.addWidget(self._auto_status)

        layout.addWidget(self._auto_content)
        layout.addSpacing(32)

        # ── Separator ─────────────────────────────────────────
        self._sep = QWidget()
        self._sep.setFixedHeight(1)
        layout.addWidget(self._sep)
        layout.addSpacing(32)

        # ── MANUAL radio button ───────────────────────────────
        self._radio_manual = QRadioButton()
        self._radio_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._radio_manual)
        layout.addSpacing(6)

        # Manual section content (indented, grayed out by default)
        self._manual_content = QWidget()
        self._manual_content.setEnabled(False)
        manual_layout = QVBoxLayout(self._manual_content)
        manual_layout.setContentsMargins(28, 0, 0, 0)
        manual_layout.setSpacing(0)

        self._lbl_manual_subtitle = QLabel()
        self._lbl_manual_subtitle.setWordWrap(True)
        manual_layout.addWidget(self._lbl_manual_subtitle)
        manual_layout.addSpacing(20)

        # Environment
        self._lbl_env = QLabel()
        manual_layout.addWidget(self._lbl_env)
        manual_layout.addSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(10)
        for i, env_id in enumerate(BOARDS.keys()):
            soon = env_id in COMING_SOON_ENVS
            btn = _EnvBtn(env_id, BOARDS[env_id]["label"], coming_soon=soon)
            if soon:
                btn.setToolTip(lang_manager.current.board_coming_soon)
            else:
                btn.clicked.connect(lambda _, e=env_id: self._on_env_select(e))
            self._env_btns[env_id] = btn
            grid.addWidget(btn, i // 2, i % 2)
        manual_layout.addLayout(grid)
        manual_layout.addSpacing(20)

        # Model — container hidden as long as no environment is selected.
        self._model_box = QWidget()
        mbox = QVBoxLayout(self._model_box)
        mbox.setContentsMargins(0, 0, 0, 0)
        mbox.setSpacing(8)
        self._lbl_model = QLabel()
        mbox.addWidget(self._lbl_model)
        self._combo = QComboBox()
        self._combo.setFixedHeight(40)
        self._combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._combo.currentIndexChanged.connect(self._update_validate_visibility)
        mbox.addWidget(self._combo)
        manual_layout.addWidget(self._model_box)
        manual_layout.addSpacing(16)

        # Serial port — container hidden as long as no environment is
        # selected (before: only the Model field was hidden).
        self._port_box = QWidget()
        pbox = QVBoxLayout(self._port_box)
        pbox.setContentsMargins(0, 0, 0, 0)
        pbox.setSpacing(8)
        port_header = QHBoxLayout()
        port_header.setContentsMargins(0, 0, 0, 0)
        self._lbl_port = QLabel()
        port_header.addWidget(self._lbl_port)
        port_header.addStretch()
        self._btn_refresh_port = QPushButton()
        self._btn_refresh_port.setFixedSize(28, 28)
        self._btn_refresh_port.setIconSize(QSize(14, 14))
        self._btn_refresh_port.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refresh_port.clicked.connect(self._refresh_ports)
        # « relancer » icon: gray at rest, GREEN on hover (QSS does not
        # recolor a QIcon). The border turns green via the QSS :hover.
        install_icon_hover(self._btn_refresh_port, IC.REFRESH, 14,
                           normal_role="text_secondary")
        port_header.addWidget(self._btn_refresh_port)
        pbox.addLayout(port_header)
        self._combo_port = QComboBox()
        self._combo_port.setFixedHeight(40)
        self._combo_port.setCursor(Qt.CursorShape.PointingHandCursor)
        self._combo_port.currentIndexChanged.connect(self._update_validate_visibility)
        pbox.addWidget(self._combo_port)
        manual_layout.addWidget(self._port_box)
        manual_layout.addSpacing(20)

        # Validate
        self._btn_validate = QPushButton()
        self._btn_validate.setFixedHeight(40)
        self._btn_validate.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_validate.setVisible(False)
        self._btn_validate.clicked.connect(self._on_validate)
        manual_layout.addWidget(self._btn_validate)
        manual_layout.addSpacing(8)

        self._manual_status = QLabel()
        self._manual_status.setTextFormat(Qt.TextFormat.RichText)
        manual_layout.addWidget(self._manual_status)

        layout.addWidget(self._manual_content)
        layout.addStretch()

        # Radio button group (mutual exclusion)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._radio_auto, 0)
        self._mode_group.addButton(self._radio_manual, 1)
        self._radio_auto.clicked.connect(self._on_mode_changed)
        self._radio_manual.clicked.connect(self._on_mode_changed)

        self._update_model_visibility()

    # ── Auto / manual mode ────────────────────────────────────

    def _on_mode_changed(self):
        manual = self._radio_manual.isChecked()
        self._manual_content.setEnabled(manual)
        if manual:
            self._refresh_ports()
        else:
            self._switch_to_auto()

    def _switch_to_auto(self):
        """Return to automatic detection: resets the manual selection
        (deselects the board, clears the combos, removes the orange indicator) then
        relaunches a USB detection."""
        for btn in self._env_btns.values():
            btn.set_selected(False)
        self._combo.setCurrentIndex(-1)
        self._combo_port.setCurrentIndex(-1)
        self._manual_status.setText("")
        self._btn_validate.setVisible(False)
        self._update_model_visibility()   # hide model/port (no env chosen)
        # Relaunch auto detection (synchronous USB scan, like _refresh_ports).
        try:
            result = detect_board()
        except Exception:
            result = None
        if result:
            env, model = result
            board_manager.set_board_connected(env, model)   # -> green status
        else:
            board_manager.set_connected(False)              # -> « aucune carte » state

    # ── Initial state sync ────────────────────────────────────

    def _sync_from_manager(self):
        state = board_manager.state
        env   = board_manager.env
        model = board_manager.model

        if state == BoardState.CONNECTED and env and model:
            self._had_connection = True
            env_label = BOARDS.get(env, {}).get("label", env)
            s = lang_manager.current
            self._auto_status.setText(
                f'<span style="color:{theme_manager.current.signal_ok};">&#9679;</span>'
                f' {s.board_connected} : {env_label} — {model}'
            )
        elif state == BoardState.MANUAL and env and model:
            self._radio_manual.setChecked(True)
            self._manual_content.setEnabled(True)
            for eid, btn in self._env_btns.items():
                btn.set_selected(eid == env)
            self._populate_combo(env)
            self._combo.blockSignals(True)
            idx = self._combo.findText(model)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
            self._combo.blockSignals(False)
            self._refresh_ports()
            s = lang_manager.current
            env_label = BOARDS.get(env, {}).get("label", env)
            self._manual_status.setText(
                f'<span style="color:{theme_manager.current.signal_warn};">&#9679;</span>'
                f' {s.board_manual_confirmed} : {env_label} — {model}'
            )

        self._update_model_visibility()

    # ── Reactions to state changes ────────────────────────────

    def _on_state_changed(self, state: str):
        s     = lang_manager.current
        env   = board_manager.env
        model = board_manager.model

        if state == BoardState.CONNECTED:
            self._had_connection = True
            self._radio_auto.setChecked(True)
            self._manual_content.setEnabled(False)
            env_label = BOARDS.get(env, {}).get("label", env)
            self._auto_status.setText(
                f'<span style="color:{theme_manager.current.signal_ok};">&#9679;</span>'
                f' {s.board_connected} : {env_label} — {model}'
            )

        elif state == BoardState.NONE:
            if self._had_connection:
                self._auto_status.setText(
                    f'<span style="color:{theme_manager.current.signal_error};">&#9679;</span>'
                    f' {s.board_disconnected}'
                )

    # ── Manual section interactions ───────────────────────────

    def _on_env_select(self, env_id: str):
        if env_id in COMING_SOON_ENVS:
            return   # ESP32 "coming soon": not selectable
        for eid, btn in self._env_btns.items():
            btn.set_selected(eid == env_id)
        self._populate_combo(env_id)
        self._combo.setCurrentIndex(-1)
        self._manual_status.setText("")
        self._update_model_visibility()

    def _on_validate(self):
        env  = self._current_env()
        model = self._combo.currentText()
        if not env or not model:
            return
        board_manager.set_board_manual(env, model)
        s = lang_manager.current
        env_label = BOARDS.get(env, {}).get("label", env)
        port = self._combo_port.currentData() or self._combo_port.currentText()
        board_manager.set_port(port)
        suffix = f" — {port}" if port else ""
        self._manual_status.setText(
            f'<span style="color:{theme_manager.current.signal_warn};">&#9679;</span>'
            f' {s.board_manual_confirmed} : {env_label} — {model}{suffix}'
        )

    # ── Helpers ───────────────────────────────────────────────

    def _current_env(self) -> str:
        for env_id, btn in self._env_btns.items():
            if btn._selected:
                return env_id
        return ""

    def _populate_combo(self, env_id: str):
        models = BOARDS.get(env_id, {}).get("models", [])
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(models)
        self._combo.blockSignals(False)

    def _refresh_ports(self):
        try:
            from serial.tools import list_ports
            usb_ports = [p for p in list_ports.comports() if p.vid is not None]
        except ImportError:
            usb_ports = []
        self._combo_port.blockSignals(True)
        self._combo_port.clear()
        for p in usb_ports:
            desc = p.description or p.device
            label = f"{p.device} — {desc}" if desc != p.device else p.device
            self._combo_port.addItem(label, userData=p.device)
        self._combo_port.blockSignals(False)
        self._update_validate_visibility()

    def _update_model_visibility(self):
        has_env = bool(self._current_env())
        # Model AND Serial port hidden as long as no environment is chosen.
        self._model_box.setVisible(has_env)
        self._port_box.setVisible(has_env)
        self._update_validate_visibility()

    def _update_validate_visibility(self):
        has_selection = bool(self._current_env()) and self._combo.currentIndex() >= 0
        self._btn_validate.setVisible(has_selection)

    # ── Theme ─────────────────────────────────────────────────

    def apply_theme(self, c: ColorScheme):
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        self.setPalette(p)
        self.setAutoFillBackground(True)
        self._scroll.setStyleSheet("background: transparent; border: none;")
        self._scroll.widget().setStyleSheet(f"background: {c.main_bg};")

        # Radios (board selection): agreed centralized style (wireframe indicator
        # white/gray -> GREEN on hover AND checked) + bold preserved.
        radio_style = radio_checkbox_qss(c, font_pt=14, font_weight=700)
        self._radio_auto.setStyleSheet(radio_style)
        self._radio_manual.setStyleSheet(radio_style)

        self._lbl_auto_subtitle.setStyleSheet(
            f"font-size: 9pt; color: {c.text_secondary};"
        )
        self._auto_status.setStyleSheet(
            f"font-size: 9pt; color: {c.text_secondary};"
        )
        self._sep.setStyleSheet(f"background-color: {c.border};")
        self._lbl_manual_subtitle.setStyleSheet(
            f"font-size: 9pt; color: {c.text_secondary};"
        )
        self._lbl_env.setStyleSheet(
            f"font-size: 9pt; font-weight: 600; color: {c.text_secondary};"
        )
        self._lbl_model.setStyleSheet(
            f"font-size: 9pt; font-weight: 600; color: {c.text_secondary};"
        )
        self._lbl_port.setStyleSheet(
            f"font-size: 9pt; font-weight: 600; color: {c.text_secondary};"
        )
        # Centralized style (cf theme.combo_qss): Model + Port share the
        # same rendering as the modal combos.
        combo_style = combo_qss(c)
        self._combo.setStyleSheet(combo_style)
        self._combo_port.setStyleSheet(combo_style)

        # Icon managed by install_icon_hover (gray -> green on hover). GREEN
        # border on hover via QSS.
        self._btn_refresh_port.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {c.border};
                border-radius: 6px;
            }}
            QPushButton:hover {{ border-color: {c.signal_ok}; }}
        """)
        # Centralized style: this WAS `primary_button_qss` rewritten by hand.
        # Rest and hover are pixel-identical at the geometry it actually gets
        # (height from setFixedHeight(40), width from the layout), so the
        # helper's larger sizeHint never binds. Its `:disabled` rule is new --
        # latent, since the button is hidden whenever `_manual_content` is off.
        self._btn_validate.setStyleSheet(primary_button_qss(c))
        self._manual_status.setStyleSheet(
            f"font-size: 9pt; color: {c.text_secondary};"
        )
        for btn in self._env_btns.values():
            btn.apply_theme()

    # ── Language ──────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        self._radio_auto.setText(s.board_auto_title)
        self._lbl_auto_subtitle.setText(s.board_auto_subtitle)
        self._radio_manual.setText(s.board_manual_title)
        self._lbl_manual_subtitle.setText(s.board_manual_subtitle)
        self._lbl_env.setText(s.board_env)
        self._lbl_model.setText(s.board_model)
        self._combo.setPlaceholderText(s.board_model_placeholder)
        self._lbl_port.setText(s.board_port)
        self._combo_port.setPlaceholderText(s.board_port_placeholder)
        self._btn_validate.setText(s.board_validate)
        # Bouton icone-seule : sans infobulle, sa fonction n'est devinable
        # nulle part. Posee ici plutot qu'a la construction pour suivre la
        # langue, comme le reste de cette methode.
        self._btn_refresh_port.setToolTip(s.tip_refresh_ports)
        # « Bientot disponible » (ESP32) etait posee A LA CONSTRUCTION et
        # jamais reactualisee : elle restait en francais dans les 3 autres
        # langues, alors que 84 autres infobulles de l'app suivent bien.
        for b in self.findChildren(_EnvBtn):
            if getattr(b, "_coming_soon", False):
                b.setToolTip(s.board_coming_soon)
