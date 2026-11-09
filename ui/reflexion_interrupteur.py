"""L'interrupteur « Réfléchir avant de répondre » : LE MEME widget sur les
pages Ollama et LM Studio, sous la taille de contexte (TODO #123).

Desactive par defaut (decision de l'auteur, 2026-11-06). Grise quand le
modele choisi ne sait pas reflechir (decoche) ou reflechit toujours (coche),
et la ligne d'aide dit pourquoi. La regle vit dans `ui.reflexion` ; ce widget
ne fait que l'afficher.

`bascule` ne part que sur un geste de l'utilisateur, jamais quand la page
regle l'interrupteur : chaque bascule ecrit la configuration.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from . import reflexion
from .i18n import Strings, lang_manager
from .theme import ColorScheme, radio_checkbox_qss


class InterrupteurReflexion(QWidget):
    bascule = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._case = QCheckBox()
        self._case.setCursor(Qt.CursorShape.PointingHandCursor)
        self._case.toggled.connect(self._touche)
        lay.addWidget(self._case)
        self._lbl_aide = QLabel()
        self._lbl_aide.setWordWrap(True)
        lay.addWidget(self._lbl_aide)
        self._cap: "reflexion.Capacite | None" = None
        self._en_reglage = False
        self.regler(None, False)

    # ── API ──────────────────────────────────────────────────
    def regler(self, cap: "reflexion.Capacite | None", voulu: bool):
        """Ce que le modele permet, et le reglage enregistre. N'emet rien."""
        self._cap = cap
        actif, coche = reflexion.interrupteur(cap, voulu)
        self._en_reglage = True
        self._case.setChecked(coche)
        self._en_reglage = False
        self._case.setEnabled(actif)
        self._case.setCursor(Qt.CursorShape.PointingHandCursor if actif
                             else Qt.CursorShape.ArrowCursor)
        self._ecrire_aide(lang_manager.current)

    def est_coche(self) -> bool:
        return self._case.isChecked()

    def est_actif(self) -> bool:
        return self._case.isEnabled()

    def aide(self) -> str:
        return self._lbl_aide.text()

    # ── Interne ──────────────────────────────────────────────
    def _touche(self, coche: bool):
        if not self._en_reglage:
            self.bascule.emit(coche)

    def _ecrire_aide(self, s: Strings):
        cap = self._cap
        if cap is not None and not cap.peut_reflechir:
            texte = s.think_unavailable
        elif cap is not None and not cap.peut_couper:
            texte = s.think_always
        else:
            texte = s.think_help
        self._lbl_aide.setText(texte)

    # ── Theme / langue ───────────────────────────────────────
    def apply_theme(self, c: ColorScheme):
        self._case.setStyleSheet(radio_checkbox_qss(c))
        self._lbl_aide.setStyleSheet(f"color: {c.text_secondary}; font-size: 9pt;")

    def apply_lang(self, s: Strings):
        self._case.setText(s.think_label)
        self._ecrire_aide(s)
