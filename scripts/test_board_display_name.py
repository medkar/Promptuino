"""« Uno » s'affiche « Uno R3 », mais reste « Uno » dans les fichiers.

Signale en QA le 2026-09-08 : la liste des cartes propose « Uno » a cote de
« Uno R4 Minima » et « Uno R4 WiFi ». Un « Uno » nu y est ambigu -- celui que
tout le monde a en main est une R3, et c'est d'ailleurs elle que le schema
dessine (`uno_r3.svg`).

⛔ MAIS le nom du modele n'est PAS qu'un libelle : c'est une CLE. Il indexe
`FQBN` et `_USB_IDS`, et surtout il est ECRIT DANS LES PROJETS
(`"board_model": "Uno"` dans le `.promptuino.json`). Le renommer casserait
tout projet deja enregistre -- exactement la distinction id/affichage etablie
deux fois cette semaine au catalogue de cablage (`pin_labels` contre
`pin_display_labels`).

D'ou `model_label()` : l'id dure, le libelle se lit. La moitie qui compte de
ces tests n'est donc pas « ca affiche Uno R3 » mais « la cle vaut toujours
Uno ».

Run : python scripts/test_board_display_name.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pathlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)
# Widgets retenus : un widget sans parent ramasse par le GC tue le process
# sans trace (piege documente dans test_selectable_text.py).
_VIVANTS: list = []


def _garde(w):
    _VIVANTS.append(w)
    return w


def test_the_identifier_never_changed():
    """⛔ LA garde. Un projet enregistre porte « Uno » ; il doit rester lisible.

    On verifie les TROIS tables indexees par ce nom, pas seulement une : le
    catalogue, les FQBN et les identifiants USB.
    """
    from ui.board_manager import BOARDS, FQBN, _KNOWN_DEVICES

    assert "Uno" in BOARDS["arduino"]["models"], (
        "l'identifiant a ete renomme : les projets enregistres ne se "
        "relieront plus a leur carte")
    assert FQBN[("arduino", "Uno")] == "arduino:avr:uno"
    assert ("arduino", "Uno R3") not in FQBN, (
        "le LIBELLE ne doit pas devenir une cle : il y aurait deux verites")
    assert any(v == ("arduino", "Uno") for v in _KNOWN_DEVICES.values()), (
        "la detection USB pointe encore sur l'identifiant")


def test_the_label_disambiguates_the_uno():
    """Ce que l'utilisateur lit, et pourquoi ca vaut la peine.

    La liste porte deja deux « Uno R4 » : un « Uno » nu n'y designe rien de
    precis pour un debutant qui compare sa carte a l'ecran.
    """
    from ui.board_manager import BOARDS, model_label

    assert model_label("arduino", "Uno") == "Uno R3"
    # Les autres ne bougent pas : le libelle n'existe que pour les cas qui en
    # ont besoin, comme `_TYPE_ARTICLE` au cablage.
    for m in BOARDS["arduino"]["models"]:
        if m != "Uno":
            assert model_label("arduino", m) == m, m
    # Et les deux R4 restent distincts de la R3.
    labels = [model_label("arduino", m) for m in BOARDS["arduino"]["models"]]
    assert len(labels) == len(set(labels)), f"deux cartes portent le meme nom : {labels}"


def test_every_visible_place_shows_the_label():
    """Les QUATRE endroits ou l'utilisateur lit le nom de sa carte.

    Signale par l'utilisateur lui-meme : « tous les affichages visibles par
    l'utilisateur doivent etre modifies ». Les enumerer ici est ce qui rend la
    reponse verifiable plutot que declarative.
    """
    from ui.board_manager import board_manager
    from ui.project_manager import Project
    from ui.projects_view import ProjectCard
    from ui.statusbar import StatusBar
    from ui.studio_view import StudioView

    board_manager.set_board_manual("arduino", "Uno")

    studio = _garde(StudioView())
    studio._update_board_badge()
    assert "Uno R3" in studio._lbl_board_badge.text(), (
        f"badge du Studio : {studio._lbl_board_badge.text()!r}")

    barre = _garde(StatusBar())
    barre._refresh()
    assert "Uno R3" in barre._lbl_board_val.text(), (
        f"barre d'etat : {barre._lbl_board_val.text()!r}")

    projet = Project(path=pathlib.Path("/tmp/x"), name="T", type="arduino",
                     mode="beginner", board_env="arduino", board_model="Uno")
    card = _garde(ProjectCard(projet))
    assert card._subtitle().startswith("Uno R3"), (
        f"card de projet : {card._subtitle()!r}")

    from ui.board_view import BoardView
    vue = _garde(BoardView())
    vue._populate_combo("arduino")
    textes = [vue._combo.itemText(i) for i in range(vue._combo.count())]
    assert "Uno R3" in textes and "Uno" not in textes, (
        f"liste des cartes : {textes}")


def test_the_combo_still_hands_back_the_identifier():
    """Le piege du libelle dans une liste deroulante.

    Sans `userData`, lire `currentText()` rendrait « Uno R3 » -- un libelle,
    pas une cle -- et ni `FQBN` ni les projets enregistres ne le
    reconnaitraient. La liste affiche le libelle et RESTITUE l'identifiant.
    """
    from ui.board_manager import BOARDS, FQBN
    from ui.board_view import BoardView

    vue = _garde(BoardView())
    vue._populate_combo("arduino")
    for i in range(vue._combo.count()):
        ident = vue._combo.itemData(i)
        assert ident in BOARDS["arduino"]["models"], (
            f"la liste rend {ident!r}, qui n'est pas un identifiant connu")
        assert ("arduino", ident) in FQBN, (
            f"{ident!r} n'a pas de FQBN : la compilation echouerait")
    assert vue._combo.itemData(0) == "Uno", vue._combo.itemData(0)


TESTS = [
    test_the_identifier_never_changed,
    test_the_label_disambiguates_the_uno,
    test_every_visible_place_shows_the_label,
    test_the_combo_still_hands_back_the_identifier,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}", flush=True)
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}", flush=True)
    print(f"\n{passed}/{len(TESTS)} tests passed", flush=True)
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
