"""Listes et curseurs qui ne volent pas la molette (audit du 2026-11-06).

Une QComboBox ou un QSlider SANS focus change de valeur a la molette, et la
page ne defile plus : sur l'onglet « Modele IA » (une carte defilante), faire
rouler la page au-dessus de la liste « Moteur » basculait le moteur actif et
l'ENREGISTRAIT, sans rien dire -- idem pour le fournisseur et le modele du
cloud, le modele Ollama / LM Studio / ChatGPT, et les curseurs de contexte et
de reflexion (qui, eux, recreent le moteur).

Regle : un controle sans focus IGNORE la molette -- l'evenement remonte au
parent, la page defile. Il faut l'avoir clique (focus) pour la molette agisse.
`StrongFocus` (et non le `WheelFocus` par defaut) : la molette ne donne plus
le focus d'elle-meme.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QSlider


class ComboSansMolette(QComboBox):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if not self.hasFocus():
            event.ignore()              # la page defile, rien ne change
            return
        super().wheelEvent(event)


class SliderSansMolette(QSlider):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)
