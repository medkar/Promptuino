"""La pastille « thinking » : LE MEME widget dans le chat et dans la zone de
generation (decisions de l'auteur, 2026-11-07).

- activé       : pastille PLEINE, icone « ampoule » ;
- désactivé    : la meme pastille VIDE, icone barree ;
- pas de mode  : la meme pastille GRISEE, non cliquable ;
- toujours activé (ChatGPT, niveaux nommes d'Ollama) : pleine, atténuée ;
- moteur non reglable (cloud par cle) : grisee, son infobulle le dit.

Niveau d'effort (P3) : un clic fait DEFILER desactive -> bas -> moyen ->
eleve -> desactive (ou les seuls niveaux, en boucle, quand le modele ne se
coupe pas) ; un ANNEAU autour de la pastille montre le niveau (un tiers,
deux tiers, plein). Un modele sans niveaux bascule simplement oui / non.

Le reglage est PARTAGE (`thinking_etat`) : les autres pastilles et l'onglet
Modele IA suivent. Peinte au QPainter (convention du projet pour les formes
arrondies).
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QAbstractButton

from . import icons as IC
from .i18n import Strings, lang_manager
from .theme import theme_manager
from .thinking_etat import thinking_etat

TAILLE = 26
_ANNEAU = 2.0          # epaisseur de l'anneau de niveau


def libelle_niveau(niveau: str, s: Strings, moteur: str) -> str:
    """Le nom affiche d'un niveau : ceux de ChatGPT (« Instant / Moyen /
    Élevé ») pour ChatGPT, « Bas / Moyen / Élevé » ailleurs, le nom brut
    pour un niveau que l'app ne connait pas."""
    if moteur == "chatgpt":
        table = {"low": s.chatgpt_level_low, "medium": s.chatgpt_level_medium,
                 "high": s.chatgpt_level_high}
    else:
        table = {"low": s.think_level_low, "medium": s.think_level_medium,
                 "high": s.think_level_high}
    return table.get(niveau, niveau)


def infobulle(s: Strings) -> str:
    e = thinking_etat.etat()
    base = {
        "on": s.think_pill_on, "off": s.think_pill_off,
        "absent": s.think_pill_absent, "toujours": s.think_pill_always,
        "non_reglable": s.think_pill_engine,
    }.get(e, s.think_pill_off)
    niveau = thinking_etat.niveau()
    if niveau:
        from .ai_config import ai_config
        base += " · " + libelle_niveau(niveau, s, ai_config.backend_id)
    return base


class PastilleThinking(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(TAILLE, TAILLE)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(thinking_etat.basculer)
        thinking_etat.change.connect(self._rafraichir)
        theme_manager.changed.connect(lambda *_: self.update())
        lang_manager.changed.connect(lambda *_: self._rafraichir())
        self._survol = False
        self._rafraichir()

    def sizeHint(self) -> QSize:
        return QSize(TAILLE, TAILLE)

    def etat(self) -> str:
        return thinking_etat.etat()

    # ── Etat ──────────────────────────────────────────────────
    def _rafraichir(self):
        # Jamais setEnabled(False) : Qt n'affiche pas l'infobulle d'un widget
        # desactive, or la pastille grisee doit dire POURQUOI elle l'est. Les
        # clics sont filtres dans mousePressEvent.
        self.setToolTip(infobulle(lang_manager.current))
        self.setCursor(Qt.CursorShape.PointingHandCursor
                       if thinking_etat.cliquable()
                       else Qt.CursorShape.ArrowCursor)
        self.update()

    def mousePressEvent(self, ev):
        if thinking_etat.cliquable():
            super().mousePressEvent(ev)
        else:
            ev.ignore()

    def enterEvent(self, ev):
        self._survol = True
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._survol = False
        self.update()
        super().leaveEvent(ev)

    # ── Dessin ────────────────────────────────────────────────
    def paintEvent(self, _ev):
        c = theme_manager.current
        e = self.etat()
        niveaux = thinking_etat.niveaux()
        niveau = thinking_etat.niveau()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Avec des niveaux, l'anneau prend le bord : la pastille se resserre.
        marge = _ANNEAU + 2 if niveaux else 1
        r = QRectF(marge, marge, self.width() - 2 * marge,
                   self.height() - 2 * marge)
        pleine = e in ("on", "toujours")
        grise = e in ("absent", "non_reglable")
        if pleine:
            fond = QColor(c.accent)
            if e == "toujours":
                fond.setAlphaF(0.55)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fond)
            p.drawEllipse(r)
            couleur_icone = c.main_bg
        else:
            bord = QColor(c.disabled_text if grise else c.border)
            if self._survol and not grise:
                p.setBrush(QColor(c.border))
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(bord, 1))
            p.drawEllipse(r)
            # Désactivé : une icône GRISE, pas le blanc du texte (demande de
            # l'auteur, 2026-11-07). Pas la couleur exacte de la bordure : à
            # #1F2735 sur fond sombre, l'icône disparaissait (rendu vérifié).
            couleur_icone = c.disabled_text if grise else c.text_secondary
        if niveaux and not grise:
            self._anneau(p, c, niveaux, niveau)
        svg = IC.THINKING_OFF if e == "off" else IC.THINKING
        cote = 14 if niveaux else 16
        pix = IC.make_icon(svg, couleur_icone, cote).pixmap(cote, cote)
        p.drawPixmap(int((self.width() - cote) / 2),
                     int((self.height() - cote) / 2), pix)
        p.end()

    def _anneau(self, p: QPainter, c, niveaux: tuple, niveau: str):
        """Le niveau : la part de l'anneau en couleur d'accent, le reste en
        bordure. Desactive : l'anneau entier en bordure."""
        d = _ANNEAU / 2 + 0.5
        r = QRectF(d, d, self.width() - 2 * d, self.height() - 2 * d)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(c.border), _ANNEAU))
        p.drawEllipse(r)
        if niveau in niveaux:
            part = (niveaux.index(niveau) + 1) / len(niveaux)
            stylo = QPen(QColor(c.accent), _ANNEAU)
            stylo.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(stylo)
            # Depuis midi, dans le sens des aiguilles d'une montre.
            p.drawArc(r, 90 * 16, int(-360 * 16 * part))
