"""
Scrollbars auto-masquees : invisibles au repos, visibles pendant un scroll
+ 1.5 s, puis s'effacent. L'espace de la scrollbar reste reserve (la policy
est forcee a `AlwaysOn`) pour eviter tout redimensionnement au
passage debordement / pas de debordement.

Usage global (recommande) :

    from .auto_hide_scrollbar import install_global_auto_hide
    install_global_auto_hide(app)

Installe un event filter sur la QApplication qui equipe automatiquement
chaque QScrollArea / QPlainTextEdit / QTextEdit de l'application au
moment de leur premier affichage (event Polish).
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtWidgets import (
    QAbstractScrollArea, QApplication, QPlainTextEdit, QScrollArea,
    QScrollBar, QTextEdit,
)


_HIDE_DELAY_MS = 1500
_INSTALLED_KEY = "_auto_hide_installed"

# Classes auxquelles on applique l'auto-hide. Limiter aux zones de scroll
# "utilisateur" evite de toucher aux scroll areas internes de widgets
# composes comme QComboBox (vue deroulante) ou autres surprises.
_TARGET_TYPES = (QScrollArea, QPlainTextEdit, QTextEdit)

# Stylesheet local applique au repos : la poignee devient transparente.
# Bascule via setStyleSheet (pas QGraphicsOpacityEffect) — l'effet
# graphique provoquait des SIGSEGV intermittents a la destruction.
_HIDDEN_QSS = (
    "QScrollBar::handle:vertical { background: transparent; }"
    "QScrollBar::handle:horizontal { background: transparent; }"
)


class _AutoHideController(QObject):
    """Cache la poignee d'une QScrollBar au repos en superposant un
    stylesheet local qui la rend transparente. Au scroll (valueChanged),
    on revient au stylesheet global ; apres `_HIDE_DELAY_MS` sans
    nouveau scroll, on rebascule en mode cache.

    NB : le hover seul ne reveille PAS la scrollbar — seul un scroll
    le fait. Une fois visible, l'utilisateur peut cliquer/glisser la
    poignee (le timer reste arme et se reinitialise a chaque
    valueChanged genere par le drag).
    """

    def __init__(self, scrollbar: QScrollBar):
        super().__init__(scrollbar)
        self._bar = scrollbar

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_HIDE_DELAY_MS)
        self._timer.timeout.connect(self._hide)

        scrollbar.valueChanged.connect(self._show)
        self._hide()

    def _show(self):
        # setStyleSheet("") revient au stylesheet global de l'app, qui
        # restaure la couleur normale de la poignee.
        self._bar.setStyleSheet("")
        self._timer.start()

    def _hide(self):
        self._bar.setStyleSheet(_HIDDEN_QSS)


def install_auto_hide(scroll_area: QAbstractScrollArea):
    """Equipe les scrollbars verticales de `scroll_area` de l'auto-hide.

    La policy verticale est forcee a `AlwaysOn` pour que l'espace soit
    toujours reserve (pas de redimensionnement). La scrollbar horizontale
    n'est pas touchee : on respecte la policy choisie par le widget.
    """
    if scroll_area.property(_INSTALLED_KEY):
        return
    scroll_area.setProperty(_INSTALLED_KEY, True)
    scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    _AutoHideController(scroll_area.verticalScrollBar())


class _GlobalInstaller(QObject):
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Polish and isinstance(obj, _TARGET_TYPES):
            install_auto_hide(obj)
        return super().eventFilter(obj, ev)


_installer_singleton: _GlobalInstaller | None = None


def install_global_auto_hide(app: QApplication):
    """Active l'auto-hide des scrollbars sur toute l'application.

    Equipe retroactivement les scroll areas deja creees ET installe un
    event filter pour equiper les prochains au moment de leur Polish.
    """
    global _installer_singleton
    if _installer_singleton is None:
        _installer_singleton = _GlobalInstaller()
        app.installEventFilter(_installer_singleton)
    # Retroactif : certains widgets existent deja et ne recevront plus de
    # Polish. On les equipe maintenant.
    for w in app.allWidgets():
        if isinstance(w, _TARGET_TYPES):
            install_auto_hide(w)
