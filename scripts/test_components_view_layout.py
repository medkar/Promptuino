"""QA G1 (2026-08-08) : la grille de l'onglet « Composants » debordait
horizontalement a la taille minimale de la fenetre.

Cause mesuree : `minimumSizeHint == sizeHint` sur chaque carte -- un QLabel
ordinaire annonce le texte entier comme largeur MINIMALE, donc les cartes ne
pouvaient pas retrecir du tout. La grille exigeait 1191 px la ou l'onglet en
offre ~1050 a la taille minimale de fenetre (1280x700, sidebar deduite).

Le cap `DESC_MAX_CHARS` ne pouvait rien y faire : il borne des CARACTERES, pas
des pixels -- meme famille d'erreur que le budget de 13 caracteres des noms de
composants.

Run : python scripts/test_components_view_layout.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.components_view import ComponentsView, _ElidedLabel, GRID_COLS

# Largeur reellement disponible pour l'onglet quand la fenetre est a son
# minimum (main_window : setMinimumSize(1280, 700)), sidebar deployee et
# marges deduites -- volontairement pessimiste.
NARROWEST_TAB_WIDTH = 980


def _view():
    v = ComponentsView()
    v.refresh()
    v.show()
    return v


def test_the_grid_fits_at_the_smallest_window():
    v = _view()
    v.resize(NARROWEST_TAB_WIDTH, 700)
    _APP.processEvents()
    need = v._grid_host.minimumSizeHint().width()
    avail = v._scroll.viewport().width()
    assert need <= avail, (
        f"la grille exige {need} px pour {avail} px disponibles "
        f"-> debordement horizontal")


def test_no_card_imposes_its_full_text_width():
    """Le vrai invariant : une carte doit pouvoir RETRECIR. Sans ca le
    correctif tiendrait par chance (des noms courts) et casserait au premier
    composant au nom long."""
    v = _view()
    v.resize(1400, 700)
    _APP.processEvents()
    budget = v._scroll.viewport().width() // GRID_COLS
    offenders = []
    for i in range(v._grid_layout.count()):
        w = v._grid_layout.itemAt(i).widget()
        if w is None:
            continue
        if w.minimumSizeHint().width() > budget:
            offenders.append((w.minimumSizeHint().width(),
                              getattr(getattr(w, "_info", None), "name", "?")))
    assert not offenders, f"{len(offenders)} carte(s) trop larges : {offenders[:3]}"


def _shown(text: str, width: int) -> _ElidedLabel:
    """Un libelle AFFICHE a la largeur voulue. Le `show()` n'est pas
    decoratif : Qt ne delivre pas l'evenement de redimensionnement a un
    widget jamais affiche, donc un `resize()` seul laisse le texte intact et
    le test se croirait rouge pour rien."""
    lbl = _ElidedLabel(text)
    lbl.resize(width, 20)
    lbl.show()
    _APP.processEvents()
    return lbl


def test_elided_label_reports_no_minimum_width():
    lbl = _ElidedLabel("un nom de composant particulierement long a afficher")
    assert lbl.minimumSizeHint().width() == 0
    # ... mais sa largeur SOUHAITEE reste celle du texte entier, sinon la
    # pastille « perso » se collerait au bord droit meme en fenetre large.
    assert lbl.sizeHint().width() > 0


def test_the_wanted_width_survives_being_elided():
    """Sinon le repli serait a SENS UNIQUE : une fois coupe, le libelle ne
    demanderait plus que la largeur de ce qu'il affiche, et reelargir la
    fenetre ne lui rendrait jamais la place."""
    full = "capteur de temperature et humidite haute precision"
    wanted = _ElidedLabel(full).sizeHint().width()
    lbl = _shown(full, 60)
    assert lbl.text() != full                      # bien elide
    assert lbl.sizeHint().width() == wanted        # veut toujours tout


def test_elided_label_keeps_the_full_text_available():
    """Elider replie l'information, ne la perd pas."""
    full = "capteur de temperature et humidite haute precision"
    lbl = _shown(full, 60)
    assert lbl.fullText() == full
    assert lbl.text() != full          # affichage coupe
    assert lbl.text().endswith("…"), lbl.text()


def test_long_names_are_elided_not_truncated_by_count():
    """Deux textes de MEME longueur en caracteres mais de largeurs
    differentes doivent etre coupes differemment -- c'est ce qu'un cap en
    caracteres ne peut pas faire."""
    narrow = _shown("i" * 40, 80)
    wide = _shown("W" * 40, 80)
    assert len(narrow.text()) > len(wide.text()), (narrow.text(), wide.text())


def test_the_custom_badge_is_promptuino_green():
    """La pastille dit « c'est toi qui l'as decrit », pas « attention » :
    l'ambre est reserve aux reserves et aux avertissements."""
    from ui.theme import theme_manager
    from ui.component_index import ORIGIN_DECLARED
    v = _view()
    c = theme_manager.current
    badges = 0
    for i in range(v._grid_layout.count()):
        w = v._grid_layout.itemAt(i).widget()
        info = getattr(w, "_info", None)
        if w is None or info is None or info.origin != ORIGIN_DECLARED:
            continue
        badge = getattr(w, "_lbl_badge", None)
        if badge is None:
            continue
        badges += 1
        qss = badge.styleSheet()
        assert c.signal_ok in qss, qss
        assert c.signal_warn not in qss, qss
    # Pas d'assertion sur `badges > 0` : la bibliotheque de la machine peut
    # etre vide. Le style lui-meme est verifie ci-dessous sans dependre d'elle.
    #
    # La recette a DEMENAGE dans theme.py le 2026-08-12 (la card de la modale
    # d'ambiguite affiche la meme pastille ; deux recettes locales divergent).
    # On asserte donc la sortie du helper -- ce qui est plus solide que
    # l'ancienne recherche du litteral dans la source de components_view :
    # une reindentation la faisait rougir, et un helper renomme la laissait
    # verte.
    from ui.theme import DARK, LIGHT, perso_badge_qss
    for scheme in (DARK, LIGHT):
        qss = perso_badge_qss(scheme)
        assert f"color: {scheme.signal_ok}" in qss, qss
        assert f"border: 1px solid {scheme.signal_ok}" in qss, qss
        assert scheme.signal_warn not in qss, qss


TESTS = [
    test_the_grid_fits_at_the_smallest_window,
    test_no_card_imposes_its_full_text_width,
    test_elided_label_reports_no_minimum_width,
    test_the_wanted_width_survives_being_elided,
    test_elided_label_keeps_the_full_text_available,
    test_long_names_are_elided_not_truncated_by_count,
    test_the_custom_badge_is_promptuino_green,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
