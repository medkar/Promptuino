"""Yes/No confirmations that speak the app's language.

`QMessageBox.question(...)` is convenient but its buttons are Qt's own
standard ones: Qt translates them from the SYSTEM locale, which has nothing to
do with the language chosen in the app. Four call sites used it, so four
dialogs answered « Yes » / « No » to a user reading French, Spanish or Italian.

The static form gives no handle on the buttons, so the fix cannot be a one-line
patch at each site: the box has to be built. `ask_yes_no` does it once, which
also removes the four copies of the same six lines.
"""
from PyQt6.QtWidgets import QMessageBox

from .i18n import lang_manager


def ask_yes_no(parent, title: str, text: str, *,
               default_yes: bool = False, warning: bool = False) -> bool:
    """Ask a yes/no question and return True on yes.

    `default_yes=False` on purpose: every current caller confirms a DELETION or
    a reset, and the safe answer must be the one a distracted Enter lands on.
    """
    box = QMessageBox(parent)
    # Style maison : sans lui, la boite garde les boutons natifs gris
    # (releve utilisateur du 2026-08-28 sur la suppression de modele).
    from .theme import messagebox_qss, theme_manager
    box.setStyleSheet(messagebox_qss(theme_manager.current))
    box.setIcon(QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton(lang_manager.current.btn_yes,
                        QMessageBox.ButtonRole.YesRole)
    no = box.addButton(lang_manager.current.btn_no,
                       QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(yes if default_yes else no)
    box.exec()
    return box.clickedButton() is yes
