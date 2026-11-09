"""Le niveau d'effort dans l'onglet Modele IA (choix P4 de l'auteur,
2026-11-07) : un curseur a crans, comme celui de ChatGPT.

TOUJOURS affiche sur les pages Ollama et LM Studio (decision de l'auteur,
meme jour : invisible, il passait pour un oubli). Actif pour un modele qui
ANNONCE des niveaux nommes (gpt-oss : low / medium / high, sous Ollama comme
sous LM Studio -- TODO #125) ; GRISE sinon,
avec une ligne qui dit pourquoi -- la meme logique que la pastille grisee.

Ecrit le reglage PARTAGE via `thinking_etat.choisir_niveau` : la pastille du
chat et celle de la generation suivent, et inversement (`regler`).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from .i18n import Strings, lang_manager
from .molette import SliderSansMolette
from .theme import ColorScheme, slider_qss

# Les crans montres quand le modele n'en a pas : la forme du reglage, grisee.
_CRANS_MONTRES = ("low", "medium", "high")


class CurseurNiveaux(QWidget):
    niveau_choisi = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._niveaux: tuple = ()
        self._montres: tuple = ()
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 4, 0, 0)
        self._lay.setSpacing(2)
        self._lbl = QLabel()
        self._lay.addWidget(self._lbl)
        self._curseur = SliderSansMolette(Qt.Orientation.Horizontal)
        self._curseur.setSingleStep(1)
        self._curseur.setPageStep(1)
        self._curseur.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._curseur.setTickInterval(1)
        self._curseur.valueChanged.connect(self._bouge)
        self._curseur.sliderReleased.connect(self._choisi)
        self._lay.addWidget(self._curseur)
        self._crans = QHBoxLayout()
        self._crans.setContentsMargins(0, 0, 3, 0)    # « Élevé » rogne sinon
        self._lay.addLayout(self._crans)
        self._lbl_aide = QLabel()
        self._lbl_aide.setWordWrap(True)
        self._lay.addWidget(self._lbl_aide)
        self._lbls: list = []
        self.regler((), "")

    # ── API ──────────────────────────────────────────────────
    def regler(self, niveaux: tuple, actuel: str):
        """Les niveaux du modele et celui en vigueur. N'emet rien. Sans
        niveaux : les trois crans habituels, grises, et la raison."""
        niveaux = tuple(niveaux or ())
        self._niveaux = niveaux
        montres = niveaux if len(niveaux) > 1 else _CRANS_MONTRES
        if montres != self._montres:
            self._montres = montres
            while self._crans.count():
                it = self._crans.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
            self._lbls = []
            for i, _n in enumerate(montres):
                if i:
                    self._crans.addStretch(1)
                lbl = QLabel()
                self._crans.addWidget(lbl)
                self._lbls.append(lbl)
            self._curseur.blockSignals(True)
            self._curseur.setRange(0, max(0, len(montres) - 1))
            self._curseur.blockSignals(False)
        actif = len(niveaux) > 1
        self._curseur.setEnabled(actif)
        self._curseur.setCursor(Qt.CursorShape.PointingHandCursor if actif
                                else Qt.CursorShape.ArrowCursor)
        self._curseur.blockSignals(True)
        if actuel in montres:
            self._curseur.setValue(montres.index(actuel))
        elif not actif:
            self._curseur.setValue(0)
        self._curseur.blockSignals(False)
        self.setVisible(True)
        self.apply_lang(lang_manager.current)
        from .theme import theme_manager
        self.apply_theme(theme_manager.current)

    def niveaux(self) -> tuple:
        return self._niveaux

    def est_actif(self) -> bool:
        return self._curseur.isEnabled()

    def aide(self) -> str:
        return self._lbl_aide.text()

    def valeur(self) -> str:
        return self._niveaux[self._curseur.value()] if len(self._niveaux) > 1 else ""

    # ── Interne ──────────────────────────────────────────────
    def _bouge(self, _v):
        if not self._curseur.isSliderDown():      # clavier, clic, molette
            self._choisi()

    def _choisi(self):
        if len(self._niveaux) > 1:
            self.niveau_choisi.emit(self.valeur())

    # ── Theme / langue ───────────────────────────────────────
    def apply_lang(self, s: Strings):
        from .thinking_pastille import libelle_niveau
        self._lbl.setText(s.think_level_label)
        for lbl, n in zip(self._lbls, self._montres):
            lbl.setText(libelle_niveau(n, s, "ollama"))
        self._lbl_aide.setText("" if len(self._niveaux) > 1
                               else s.think_level_none)
        self._lbl_aide.setVisible(bool(self._lbl_aide.text()))

    def apply_theme(self, c: ColorScheme):
        actif = len(self._niveaux) > 1
        texte = c.text_secondary if actif else c.disabled_text
        self._lbl.setStyleSheet(f"color: {texte}; font-size: 10pt;")
        self._curseur.setStyleSheet(slider_qss(c))
        for lbl in self._lbls:
            lbl.setStyleSheet(f"color: {texte}; font-size: 9pt;")
        self._lbl_aide.setStyleSheet(f"color: {c.text_secondary}; font-size: 9pt;")
