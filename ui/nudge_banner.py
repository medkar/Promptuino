"""Bandeau de nudge non-bloquant (progression de mode).

Petit bandeau inline : message en gras + bouton d'action (« Passer en … ») +
croix de fermeture. Fond vert + fondu à l'apparition pour le rendre bien
visible, mais non-bloquant ; masqué tant qu'aucun nudge n'est dû, montré une
seule fois (le drapeau « vu » est persisté app-wide, cf. session).

Pourquoi pas une ligne de journal : en mode débutant le journal est noyé par
la sortie compile+upload qui suit chaque génération -> la ligne était enterrée
et invisible. Un bandeau vert dédié reste visible et offre l'action directe.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect,
)

from .theme import theme_manager


class NudgeBanner(QFrame):
    """Bandeau « astuce » non-bloquant. `show_nudge(message, action_label)`
    l'affiche (avec un fondu) ; `action_requested` est émis au clic sur le
    bouton, `dismissed` au clic sur la croix.

    `variant` : "ok" (vert, nudge de progression) ou "info" (ambre,
    information — ex. composant hors-corpus résolu via le registre Arduino).
    Un `action_label` vide masque le bouton d'action (message + croix seuls)."""

    action_requested = pyqtSignal()
    action2_requested = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent=None, *, variant: str = "ok"):
        super().__init__(parent)
        self._variant = variant
        self.setObjectName("NudgeBanner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)

        self._lbl = QLabel("")
        self._lbl.setWordWrap(True)
        # RichText : les messages contiennent du <b> pour mettre en gras certains
        # mots (« Astuce », le nom du mode).
        self._lbl.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self._lbl, 1)

        self._btn = QPushButton("")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setAutoDefault(False)
        self._btn.clicked.connect(self.action_requested)
        lay.addWidget(self._btn)

        # Second action. A prompt can name two unknown parts, one resolved at
        # the registry and one not: the banner then carries BOTH messages, and
        # a single slot forced a choice between "changer de bibliothèque" and
        # "demander de l'aide" -- dropping one of the two ways out (QA A2,
        # 2026-08-08). Hidden unless `show_nudge` is given a second label.
        self._btn2 = QPushButton("")
        self._btn2.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn2.setAutoDefault(False)
        self._btn2.clicked.connect(self.action2_requested)
        self._btn2.setVisible(False)
        lay.addWidget(self._btn2)

        self._close = QPushButton("✕")
        self._close.setFixedSize(22, 22)
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.setAutoDefault(False)
        self._close.clicked.connect(self._on_close)
        lay.addWidget(self._close)

        # Fondu à l'apparition (met en évidence le bandeau quand il surgit).
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(350)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.setVisible(False)
        theme_manager.changed.connect(self._apply_theme)
        self._apply_theme()

    def _on_close(self) -> None:
        self.hide()
        self.dismissed.emit()

    def show_nudge(self, message: str, action_label: str = "",
                   action2_label: str = "") -> None:
        """Affiche le bandeau (avec fondu) avec son message et le libellé de
        ses boutons d'action (vide -> bouton masqué). Le second sert quand
        deux issues coexistent (cf. `action2_requested`)."""
        self._lbl.setText(message)
        self._btn.setText(action_label)
        self._btn.setVisible(bool(action_label))
        self._btn2.setText(action2_label)
        self._btn2.setVisible(bool(action2_label))
        self.setVisible(True)
        self._fade.stop()
        self._fade.start()

    def _apply_theme(self, *_) -> None:
        c = theme_manager.current
        # Fond plein (vert signal_ok pour "ok", ambre signal_warn pour "info")
        # pour une visibilité forte ; texte en gras dans la couleur qui
        # contraste (btn_primary_text : sombre sur les fonds vifs du thème
        # sombre, blanc sur les fonds plus foncés du thème clair — le couple
        # vif/sombre est le même pour signal_ok et signal_warn).
        bg = c.signal_ok if self._variant == "ok" else c.signal_warn
        self.setStyleSheet(
            f"#NudgeBanner {{ background: {bg}; border: none; "
            f"border-radius: 6px; }}"
        )
        self._lbl.setStyleSheet(
            f"color: {c.btn_primary_text}; background: transparent; "
            f"font-size: 9pt;"
        )
        # Bouton d'action : carte pleine contrastée (PAS de vert pour ne pas se
        # fondre dans le bandeau), texte contrasté.
        btn_qss = (
            f"QPushButton {{ background: {c.btn_primary_bg}; "
            f"color: {c.btn_primary_text}; border: none; border-radius: 4px; "
            f"padding: 4px 12px; font-size: 9pt; font-weight: 600; }} "
            f"QPushButton:hover {{ background: {c.btn_primary_hover}; }}"
        )
        self._btn.setStyleSheet(btn_qss)
        self._btn2.setStyleSheet(btn_qss)
        # `padding: 0` is load-bearing: fixed 22x22 size and a TEXT glyph (✕).
        # Without it the application default (`7px 18px`, theme.app_qss) pushes
        # the glyph out of the frame -- measured at 0 ink pixels, i.e. the
        # banner's dismiss button was drawing nothing at all.
        self._close.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; padding: 0; "
            f"color: {c.btn_primary_text}; font-size: 12px; font-weight: bold; }} "
            f"QPushButton:hover {{ color: {c.main_bg}; }}"
        )
