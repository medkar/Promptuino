"""Lancer une fonction hors du fil graphique et recevoir son resultat.

⛔ Une `QThread` detruite pendant qu'elle tourne fait planter l'app. Une tache
peut durer (charger un gros modele LM Studio : jusqu'a 300 s ; attendre une
connexion ChatGPT : jusqu'a 5 min) et la fenetre qui l'a lancee peut etre
fermee entre-temps : la reference vit donc ICI, pas dans la fenetre, et ne
disparait qu'a la fin du fil. Le resultat est emis vers une methode liee d'un
QObject, que PyQt deconnecte d'elle-meme si ce QObject est detruit.

Utilise par la gestion des modeles LM Studio et la connexion ChatGPT
(TODO #121, #122).
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

_EN_VOL: set = set()


class Tache(QThread):
    fini = pyqtSignal(object)            # (etiquette, resultat)

    def __init__(self, etiquette: str, fn):
        super().__init__()
        self._etiquette = etiquette
        self._fn = fn

    def run(self):
        try:
            resultat = self._fn()
        except Exception as e:           # par prudence : le slot recoit l'erreur
            resultat = e
        self.fini.emit((self._etiquette, resultat))


def lancer_en_fond(etiquette: str, fn, slot) -> Tache:
    """Lance `fn()` dans un fil ; `slot((etiquette, resultat))` a la fin."""
    tache = Tache(etiquette, fn)
    tache.fini.connect(slot)
    _EN_VOL.add(tache)
    tache.finished.connect(lambda t=tache: _EN_VOL.discard(t))
    tache.start()
    return tache
