"""Le reglage de la taille de contexte : LE MEME widget sur les pages Ollama et
LM Studio (decision de l'auteur, 2026-11-06).

Un curseur du plancher (`contexte.CTX_PROMPTUINO`) au maximum du modele
choisi, par pas de `contexte.PAS` -- comme le curseur de LM Studio, et non plus
les cinq paliers 2 048..32 768 de l'ancien curseur d'Ollama.

`valeur_validee` part au RELACHEMENT de la souris (ou a chaque pas au
clavier), jamais pendant un glisser : chaque valeur enregistree ecrit la
configuration, et chez Ollama un autre contexte recharge le modele.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from . import contexte as cx
from .i18n import Strings
from .molette import SliderSansMolette
from .theme import ColorScheme, slider_qss


def tokens(n: int) -> str:
    """`16384` -> `16 384 tokens`. Espace insecable NORMALE : l'espace fine
    (U+202F) ne s'affichait pas avec la police de l'app (capture 2026-11-06)."""
    return f"{n:,}".replace(",", " ") + " tokens"


class CurseurContexte(QWidget):
    valeur_validee = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._lbl_titre = QLabel()
        lay.addWidget(self._lbl_titre)
        rang = QHBoxLayout()
        rang.setContentsMargins(0, 0, 0, 0)
        rang.setSpacing(8)
        self._slider = SliderSansMolette(Qt.Orientation.Horizontal)
        self._slider.setSingleStep(1)          # en pas de `cx.PAS`
        self._slider.setPageStep(4)
        self._slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._slider.valueChanged.connect(self._bouge)
        self._slider.sliderReleased.connect(self._relache)
        rang.addWidget(self._slider, 1)
        self._lbl_valeur = QLabel()
        self._lbl_valeur.setMinimumWidth(110)
        rang.addWidget(self._lbl_valeur)
        lay.addLayout(rang)
        self._lbl_aide = QLabel()
        self._lbl_aide.setWordWrap(True)
        lay.addWidget(self._lbl_aide)
        self.regler(None, cx.CTX_PROMPTUINO)

    # ── API ──────────────────────────────────────────────────
    def regler(self, ctx_max: "int | None", valeur: int) -> int:
        """Bornes du modele choisi ; rend la valeur RAMENEE dans la plage.
        N'emet rien : seul un geste de l'utilisateur enregistre."""
        bas, haut = cx.plage(ctx_max)
        v = cx.ramener(valeur, ctx_max)
        self._slider.blockSignals(True)
        self._slider.setRange(bas // cx.PAS, haut // cx.PAS)
        self._slider.setValue(v // cx.PAS)
        self._slider.blockSignals(False)
        self._slider.setEnabled(True)
        self._lbl_valeur.setText(tokens(v))
        return v

    def bloquer(self, ctx_max: int):
        """Modele inutilisable : on montre son maximum, sans rien proposer."""
        self._slider.blockSignals(True)
        self._slider.setRange(0, 0)
        self._slider.blockSignals(False)
        self._slider.setEnabled(False)
        self._lbl_valeur.setText(tokens(ctx_max))

    def valeur(self) -> int:
        return self._slider.value() * cx.PAS

    # ── Interne ──────────────────────────────────────────────
    def _bouge(self, _v: int):
        self._lbl_valeur.setText(tokens(self.valeur()))
        if not self._slider.isSliderDown():     # clavier, molette, clic de page
            self.valeur_validee.emit(self.valeur())

    def _relache(self):
        self.valeur_validee.emit(self.valeur())

    # ── Theme / langue ───────────────────────────────────────
    def apply_theme(self, c: ColorScheme):
        self._lbl_titre.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt; font-weight: 600;")
        self._lbl_valeur.setStyleSheet(f"color: {c.text_primary}; font-size: 9pt;")
        self._lbl_aide.setStyleSheet(f"color: {c.text_secondary}; font-size: 9pt;")
        self._slider.setStyleSheet(slider_qss(c))

    def apply_lang(self, s: Strings):
        self._lbl_titre.setText(s.ia_ollama_ctx_label)     # « Taille de contexte »
        self._lbl_aide.setText(s.ctx_help.format(min=tokens(cx.CTX_PROMPTUINO)))
