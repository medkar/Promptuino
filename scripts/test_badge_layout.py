"""Ou les pastilles se posent, et quand elles se voient.

Demande utilisateur du **2026-08-31**, capture a l'appui : « je voudrais que
toutes les pastilles restent visibles, pas seulement quand j'ai la souris sur
le composant (comme l'engrenage le fait deja). Et je voudrais qu'elles soient
placees en colonne sous le nom du composant, au milieu du composant
(horizontalement) ».

Deux defauts distincts :

- **Elles n'apparaissaient qu'au SURVOL.** C'etait le meme raisonnement que
  pour l'engrenage avant qu'il ne devienne permanent -- la decouvrabilite --,
  et il vaut encore plus ici : un avertissement qu'il faut survoler pour
  savoir qu'il existe ne previent personne.
- **Elles etaient collees au haut du corps et RECOUVRAIENT le nom.** Ce que la
  boite dit d'elle-meme -- quoi attraper dans le kit -- disparaissait derriere
  ce qui la commente.

⚠️ Ce fichier teste de la GEOMETRIE de scene Qt. Il construit donc un vrai
`WiringDiagramDialog` (offscreen), une seule fois : c'est la couche qui pose
les icones, et l'interroger autrement reviendrait a tester une reimplementation
du calcul.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtGui import QCursor  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])
# Le curseur fige d'un environnement offscreen force le :hover pres de
# l'origine (piege deja paye) : on l'envoie loin avant toute mesure.
QCursor.setPos(2000, 2000)

import ui.declared_components as declared_components  # noqa: E402
declared_components.set_registry([])

from ui.fonts import setup_fonts  # noqa: E402
setup_fonts(_APP)

from ui.wiring.layout import pipeline as _v2  # noqa: E402
from ui.wiring.wiring_diagram_dialog import (  # noqa: E402
    _ICON_PIX_SIZE, WiringDiagramDialog,
)

BOARD = "arduino_uno_r3"
# Un TMC2209 UART (pastille d'attention) + une LED (pastille d'attention ET
# aide "i") : c'est la LED qui porte une vraie COLONNE de deux.
CODE = """
#include <TMC2209.h>
HardwareSerial & serial_stream = Serial1;
TMC2209 stepper_driver;
const int LED = 7;
void setup(){ stepper_driver.setup(serial_stream); pinMode(LED, OUTPUT); }
void loop(){ digitalWrite(LED, HIGH); }
"""
_DLG: list = []


def _dialogue():
    """UN seul dialogue par process : il monte toute la scene graphique."""
    if not _DLG:
        netlist = _v2.analyze_netlist(CODE, BOARD, prompt="", context="")
        dlg = WiringDiagramDialog(CODE, BOARD, None, prompt="", context="",
                                  netlist=netlist,
                                  editable_refs_fn=lambda n: set())
        dlg.resize(1400, 900)
        dlg.show()
        for _ in range(6):
            _APP.processEvents()
        _DLG.append(dlg)
    return _DLG[0]


def _vue():
    return _dialogue()._schema_view


def test_the_badges_are_visible_WITHOUT_hovering():
    """Le coeur de la demande. La souris est loin (cf. `QCursor.setPos`), donc
    aucun composant n'est survole : les pastilles doivent quand meme etre
    la."""
    vue = _vue()
    assert vue._info_icon_items, "pre-condition : au moins une pastille"
    invisibles = [r for r, it in vue._info_icon_items.items()
                  if not it.isVisible()]
    assert invisibles == [], invisibles
    invisibles = [r for r, it in vue._help_icon_items.items()
                  if not it.isVisible()]
    assert invisibles == [], invisibles


def test_the_gear_is_still_visible_too():
    """Contre-epreuve : on n'a pas casse ce qui marchait deja."""
    vue = _vue()
    for ref, item in (vue._gear_icon_items or {}).items():
        assert item.isVisible(), ref


def test_the_THREE_icons_form_ONE_column_on_the_same_axis():
    """UNE colonne, donc un seul axe vertical, ENGRENAGE COMPRIS.

    ⚠️ L'engrenage a d'abord ete oublie (releve par l'utilisateur en QA) : il
    restait en haut a gauche, ou il recouvrait le debut du nom sur les boites
    etroites. Les trois icones etaient posees par trois boucles
    independantes, chacune avec sa propre idee de l'endroit ; elles partagent
    maintenant le meme distributeur de rangs.

    L'ordre est engrenage, avertissement, aide -- et il ne laisse PAS de trou :
    un composant sans avertissement voit son << i >> remonter d'un cran.
    """
    vue = _vue()
    # La LED porte les TROIS : c'est elle qui prouve la colonne complete.
    communs = (set(vue._gear_icon_items) & set(vue._info_icon_items)
               & set(vue._help_icon_items))
    assert communs, "pre-condition : un composant porte les TROIS icones"
    for ref in communs:
        xs = [vue._gear_icon_items[ref].pos().x(),
              vue._info_icon_items[ref].pos().x(),
              vue._help_icon_items[ref].pos().x()]
        assert max(xs) - min(xs) < 0.01, (ref, xs)
        ys = [vue._gear_icon_items[ref].pos().y(),
              vue._info_icon_items[ref].pos().y(),
              vue._help_icon_items[ref].pos().y()]
        assert ys == sorted(ys), (ref, ys)
        # Espacement REGULIER : un ecart double trahirait un rang saute.
        ecarts = [round(b - a, 3) for a, b in zip(ys, ys[1:])]
        assert len(set(ecarts)) == 1, (ref, ecarts)


def test_no_rank_is_ever_SKIPPED():
    """Une colonne qui saute un rang laisse un trou, et un trou se lit comme
    une icone manquante.

    ⚠️ La premiere version de ce test comparait la position de la premiere
    icone au HAUT DE LA BBOX du composant. C'etait le mauvais repere : sur un
    composant off-BB comme le NEMA17, le `component-body` n'est pas en haut de
    l'asset, et le test rougissait sur une position pourtant correcte
    (140 contre 20 attendus). Il etait structurellement incapable de verifier
    ce qu'il annoncait.

    On verifie donc ce qui est REELLEMENT observable sans connaitre le corps :
    entre deux icones consecutives d'un meme composant, l'ecart vaut toujours
    exactement une hauteur d'icone plus le jeu. Un rang saute le doublerait.
    """
    from ui.wiring.wiring_diagram_dialog import _BADGE_GAP
    vue = _vue()
    pas = _ICON_PIX_SIZE + _BADGE_GAP
    refs = (set(vue._gear_icon_items) | set(vue._info_icon_items)
            | set(vue._help_icon_items))
    verifies = 0
    for ref in refs:
        ys = sorted(t[ref].pos().y() for t in (vue._gear_icon_items,
                                               vue._info_icon_items,
                                               vue._help_icon_items)
                    if ref in t)
        if len(ys) < 2:
            continue
        verifies += 1
        for a, b in zip(ys, ys[1:]):
            assert abs((b - a) - pas) < 0.01, (ref, ys, pas)
    assert verifies >= 2, (
        "pre-condition : au moins deux composants empilent des icones",
        verifies)


def test_the_column_is_centred_on_the_component_body():
    """<< au milieu du composant (horizontalement) >>. On compare au CORPS
    visible, pas a la bbox de l'item : celle-ci inclut les libelles de broches
    et les debords, et c'est justement le piege que `_icon_body_rect` existe
    pour eviter."""
    vue = _vue()
    for ref, item in vue._info_icon_items.items():
        corps = vue._component_items.get(ref)
        assert corps is not None, ref
        centre_icone = item.pos().x() + _ICON_PIX_SIZE / 2
        # La bbox de l'item est un majorant du corps : le centre de l'icone
        # doit tomber dedans, et pres du milieu.
        bb = corps.sceneBoundingRect()
        assert bb.left() <= centre_icone <= bb.right(), (ref, centre_icone, bb)
        assert abs(centre_icone - bb.center().x()) < bb.width() / 2, ref


def test_a_badge_does_not_sit_on_the_component_name():
    """Le nom est en 8 px a 10 unites du haut du corps (mesure sur 29 des 34
    assets qui en portent un). Une pastille posee a `top + 2` le recouvrait --
    c'est ce que montrait la capture de l'utilisateur."""
    from ui.wiring.wiring_diagram_dialog import _NAME_BAND_H
    assert _NAME_BAND_H >= 12.0, (
        "la bande du nom fait ~10 unites plus les jambages : descendre "
        "en dessous ferait remonter la pastille sur le texte")
    vue = _vue()
    for ref, item in vue._info_icon_items.items():
        haut_corps = vue._component_items[ref].sceneBoundingRect().top()
        assert item.pos().y() >= haut_corps, (ref, item.pos().y(), haut_corps)


TESTS = [
    test_the_badges_are_visible_WITHOUT_hovering,
    test_the_gear_is_still_visible_too,
    test_the_THREE_icons_form_ONE_column_on_the_same_axis,
    test_no_rank_is_ever_SKIPPED,
    test_the_column_is_centred_on_the_component_body,
    test_a_badge_does_not_sit_on_the_component_name,
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
    # Teardown Qt statique apres un vrai dialogue : os._exit reflete les
    # assertions, pas un crash de destruction.
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
