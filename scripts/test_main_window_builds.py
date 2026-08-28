"""La fenetre principale se construit-elle ENTIEREMENT ?

⛔ **Pourquoi ce fichier existe.** Le 2026-08-28, une insertion de methodes au
mauvais endroit a termine `_build_ui` prematurement : tout ce qui suivait --
la zone centrale, la barre d'etat, `setCentralWidget` -- est devenu du code
mort dans une methode qui ne s'executait plus. L'application se serait ouverte
sur une **fenetre vide**.

**Les 217 tests sont restes verts.** Aucun ne construisait `MainWindow` : la
suite ne pouvait pas voir qu'elle etait cassee. Ce fichier ferme ce trou, et
il est volontairement grossier -- il ne juge pas l'apparence, il verifie que
les pieces STRUCTURELLES sont la.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtWidgets import QApplication          # noqa: E402

_app = QApplication.instance() or QApplication([])


def _window():
    from ui.main_window import MainWindow
    return MainWindow()


def test_the_window_has_a_central_widget():
    """Le symptome exact du defaut de 2026-08-28 : `_build_ui` s'arretait
    avant `setCentralWidget`, et la fenetre s'ouvrait vide."""
    w = _window()
    assert w.centralWidget() is not None, "aucun widget central"


def test_the_structural_pieces_are_all_present():
    """Une methode tronquee laisse les attributs suivants non crees.

    On les nomme un par un : si `_build_ui` se coupe quelque part, le premier
    manquant dit OU."""
    w = _window()
    for nom in ("_sidebar", "_topbar", "_right_panel", "_chat_view",
                "_update_banner", "_root_widget"):
        assert hasattr(w, nom), f"attribut manquant : {nom}"


def test_the_update_banner_starts_hidden_and_can_be_shown():
    """Le bandeau de mise a jour (#77) ne doit rien annoncer par defaut.

    Le silence est un resultat VALIDE : hors ligne, aucune Release publiee,
    build de developpement -- dans tous ces cas il reste invisible."""
    w = _window()
    assert not w._update_banner.isVisibleTo(w), "visible sans raison au demarrage"

    w._on_update_found(None)
    assert not w._update_banner.isVisibleTo(w), "un resultat vide l'a affiche"

    w._on_update_found("v9.9.9")
    assert w._update_banner.isVisibleTo(w), "une version plus recente ne l'affiche pas"
    assert "9.9.9" in w._update_banner._lbl.text()


TESTS = [
    test_the_window_has_a_central_widget,
    test_the_structural_pieces_are_all_present,
    test_the_update_banner_starts_hidden_and_can_be_shown,
]


def main() -> int:
    rate = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except Exception as e:                     # noqa: BLE001
            rate += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - rate}/{len(TESTS)} tests passed")
    return 1 if rate else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    # ⛔ `os._exit` et non `sys.exit` : la destruction de Qt en fin de
    # processus fait planter NATIVEMENT (0xC0000409) une fenetre principale
    # complete avec ses fils. Le test passait SEUL et echouait sous le
    # lanceur -- le pire des deux mondes. Meme sortie brutale que
    # `scripts/screenshot_modals.py`, pour la meme raison.
    os._exit(code)
