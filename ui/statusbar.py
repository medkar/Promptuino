"""
Status bar at the bottom of the main window.
Displays on the right: AI Model | ● Board
"""
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QGraphicsDropShadowEffect,
)

from .theme import ColorScheme, theme_manager
from .i18n import lang_manager, Strings
from .board_manager import BOARDS, BoardState, board_manager
from .ai_config import ai_config
from .ai_status import KINDS_OK, KINDS_WARN, ai_status

_H = 26


class StatusBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_H)
        self._build()
        self._refresh()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)
        board_manager.changed.connect(self._refresh)
        board_manager.state_changed.connect(self._refresh)
        ai_config.changed.connect(self._refresh)
        ai_status.changed.connect(self._refresh)

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        layout.addStretch()

        # ── AI Model ─────────────────────────────────────────
        self._dot_ia = QLabel("●")
        self._dot_ia.setStyleSheet(
            f"color: {theme_manager.current.signal_error}; font-size: 8pt;"
        )
        self._lbl_ia_key = QLabel()
        self._lbl_ia_val = QLabel("—")
        layout.addWidget(self._dot_ia)
        layout.addSpacing(5)
        layout.addWidget(self._lbl_ia_key)
        layout.addSpacing(4)
        layout.addWidget(self._lbl_ia_val)

        # ── Vertical separator ───────────────────────────────
        layout.addSpacing(12)
        self._vsep = QLabel("|")
        layout.addWidget(self._vsep)
        layout.addSpacing(12)

        # ── Board ─────────────────────────────────────────────
        self._dot = QLabel("●")
        self._lbl_board_key = QLabel()
        self._lbl_board_val = QLabel()
        layout.addWidget(self._dot)
        layout.addSpacing(5)
        layout.addWidget(self._lbl_board_key)
        layout.addSpacing(4)
        layout.addWidget(self._lbl_board_val)

    # ── Update ────────────────────────────────────────────

    def _refresh(self, *_):
        """Re-reads board_manager and ai_config — independent of signal order."""
        # ── AI Model ─────────────────────────────────────────
        self._lbl_ia_val.setText(ai_config.display_name())
        # ⛔ La pastille etait VERTE EN DUR -- elle ne consultait rien et ne se
        # trompait que quand on avait besoin d'elle (TODO #80). Elle lit
        # desormais le dernier etat PUBLIE par l'onglet Modele IA, sans le
        # moindre appel reseau ici : `is_server_running()` coute 2 030 ms
        # serveur eteint, et _refresh tourne sur le fil graphique a chaque
        # signal. None = pas encore d'information -> GRIS, jamais vert.
        cur = theme_manager.current
        kind = ai_status.state
        if kind in KINDS_OK:
            color, glow = cur.signal_ok, True
        elif kind is None:
            color, glow = cur.text_secondary, False
        elif kind in KINDS_WARN:
            color, glow = cur.signal_warn, False
        else:
            color, glow = cur.signal_error, False
        self._dot_ia.setStyleSheet(f"color: {color}; font-size: 8pt;")
        self._set_glow(self._dot_ia, color, glow)

        # ── Board ─────────────────────────────────────────────
        env   = board_manager.env
        model = board_manager.model
        state = board_manager.state

        if state in (BoardState.CONNECTED, BoardState.MANUAL) and env and model:
            env_label = BOARDS.get(env, {}).get("label", env)
            self._lbl_board_val.setText(f"{env_label} — {model}")
        else:
            self._lbl_board_val.setText("—")

        if state == BoardState.CONNECTED:
            # ⚠️ `cur` et non un `ok` defini plus haut : la variable a ete
            # supprimee le 2026-08-28 avec le vert-en-dur de la pastille IA,
            # et cette branche -- qui ne tourne que CARTE BRANCHEE -- la
            # referencait encore. Un NameError dans un slot PyQt6 devient
            # un abort NATIF (0xC0000409) sans la moindre trace Python.
            color, glow = cur.signal_ok, True                         # "it works"
        elif state == BoardState.MANUAL:
            color, glow = theme_manager.current.signal_warn, False    # warning
        else:
            color, glow = theme_manager.current.signal_error, False   # error / disconnected
        self._dot.setStyleSheet(f"color: {color}; font-size: 8pt;")
        self._set_glow(self._dot, color, glow)   # glow only if OK (spec §5)

    def _set_glow(self, dot: QLabel, hex_color: str, on: bool):
        """Phosphor glow around a dot (spec §5) — reserved for "it works"
        states. QGraphicsDropShadowEffect, offset 0 = centered halo. Limited
        to the 2 critical statusbar indicators (perf cost kept under control)."""
        if on:
            eff = QGraphicsDropShadowEffect(dot)
            eff.setBlurRadius(8)
            eff.setOffset(0, 0)
            eff.setColor(QColor(hex_color))
            dot.setGraphicsEffect(eff)
        else:
            dot.setGraphicsEffect(None)

    # ── Theme ──────────────────────────────────────────────────

    def apply_theme(self, c: ColorScheme):
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.sidebar_bg))
        self.setPalette(p)
        self.setAutoFillBackground(True)

        base     = "font-size: 8pt;"
        base_key = "font-size: 8pt; font-weight: 700;"
        self._lbl_ia_key.setStyleSheet(base_key + f" color: {c.text_secondary};")
        self._lbl_ia_val.setStyleSheet(base    + f" color: {c.text_primary};")
        self._vsep.setStyleSheet(base          + f" color: {c.border};")
        self._lbl_board_key.setStyleSheet(base_key + f" color: {c.text_secondary};")
        self._lbl_board_val.setStyleSheet(base     + f" color: {c.text_primary};")
        self._refresh()   # recolors the OK dots (signal_ok depends on the theme)

    # ── Language ────────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        self._lbl_ia_key.setText(s.status_ia)
        self._lbl_board_key.setText(s.status_board)
        self._refresh()
