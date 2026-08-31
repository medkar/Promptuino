"""L'onglet Composants ne construit sa grille qu'au premier affichage.

Releve en QA le 2026-08-29 : << le changement de theme est tres long >>.
Mesure a l'appui, et la cause n'etait pas celle qu'on croit.

- Une bascule de theme coutait **1756 ms**, dont **963 ms** pour le seul
  `app.setStyleSheet`.
- Ce n'est PAS le contenu de la feuille : appliquer une feuille **vide**
  coutait 963 ms aussi. `QApplication.setStyleSheet` fait re-polir a Qt
  l'arbre ENTIER, et son cout suit le NOMBRE DE WIDGETS.
- Or l'onglet Composants pesait **1943 objets Qt sur 2841** -- 68 % de la
  fenetre -- pour une grille d'environ 213 cards que l'utilisateur n'avait
  peut-etre jamais ouverte.

Rendu differe : 2841 -> 930 objets, et la bascule tombe a **469 ms**.

⚠️ Aucun cout n'est deplace vers l'ouverture de l'onglet : `main_window.
_switch_tab` appelait DEJA `refresh()` a l'activation, donc la grille se
reconstruisait de toute facon a chaque visite. Seule la facture du DEMARRAGE
disparait.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

import ui.declared_components as declared_components  # noqa: E402
declared_components.set_registry([])

_VIVANTS: list = []


def _vue():
    from ui.components_view import ComponentsView
    v = ComponentsView()
    _VIVANTS.append(v)
    return v


def test_the_grid_is_not_built_at_construction():
    from ui.components_view import _ComponentCardWidget
    v = _vue()
    assert v._rendered is False, "la grille a ete rendue trop tot"
    assert not v.findChildren(_ComponentCardWidget), \
        len(v.findChildren(_ComponentCardWidget))


def test_showing_the_tab_builds_it():
    from ui.components_view import _ComponentCardWidget
    v = _vue()
    v.show()
    _APP.processEvents()
    assert v._rendered is True
    assert v.findChildren(_ComponentCardWidget), \
        "la grille est restee vide apres affichage"


def test_showing_twice_does_not_rebuild():
    """`_rendered` garde le filet de `showEvent` et l'appel de `_switch_tab`
    d'agir tous les deux : un seul des deux rend, jamais les deux."""
    v = _vue()
    v.refresh()                      # ce que fait `_switch_tab`
    assert v._rendered is True
    rendus = []
    vrai_render = v._render
    v._render = lambda: rendus.append(1) or vrai_render()
    v.show()
    _APP.processEvents()
    assert rendus == [], "showEvent a re-rendu une grille deja construite"


def test_a_construction_stays_cheap():
    """La garde chiffree : construire la vue sans l'afficher doit rester d'un
    ordre de grandeur SOUS la grille rendue. Le seuil est large a dessein --
    on verrouille l'ordre de grandeur, pas un compte exact qui bougerait a
    chaque composant ajoute au registre."""
    v = _vue()
    a_vide = len(v.findChildren(object))
    v.show()
    _APP.processEvents()
    rendue = len(v.findChildren(object))
    assert a_vide < 100, a_vide
    assert rendue > 10 * a_vide, (a_vide, rendue)


TESTS = [
    test_the_grid_is_not_built_at_construction,
    test_showing_the_tab_builds_it,
    test_showing_twice_does_not_rebuild,
    test_a_construction_stays_cheap,
]


def main() -> None:
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    # Teardown Qt statique apres plusieurs vues : os._exit reflete les
    # assertions, pas un crash de destruction.
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
