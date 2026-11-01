"""Geometrie du formulaire « Decrire mon composant » (TODO #44).

Deux choses qu'aucune capture d'ecran ne montre et qu'aucun test existant ne
regardait :

1. **Une broche peut disparaitre.** La liste de broches est le seul element du
   formulaire a porter le facteur d'etirement : tout ce qui grandit ailleurs
   lui est pris. Mesure le 2026-08-12 : elargir la marge de 9 px faisait
   passer la 4e broche sous la barre de defilement, sur un formulaire qui en
   declarait 4. Et une legende plus longue produit exactement le meme effet —
   donc **le test balaie les 4 langues**, la ou une seule aurait laisse
   passer le cas qui a cause le defaut.

2. **Une legende doit appartenir a son champ.** Qt espace tout pareil par
   defaut (~6 px) : la legende se retrouve aussi loin du champ qu'elle
   explique que du champ suivant. Ce qui la rattache n'est pas une valeur
   absolue mais un ECART, donc c'est l'ecart qui est verifie, sur la
   geometrie reellement calculee.

Le second test est le garde-fou du premier : « faire tenir toutes les
broches » se corrige trivialement en laissant le formulaire grandir sans fin,
ce qui rend un composant a 40 broches indeclarable sur un portable.

Run : python scripts/test_declare_form_layout.py
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# QApplication gardee au niveau module : sans reference, une app temporaire
# GC-ee puis la construction d'un QWidget plante le process (0xC0000409)
# sous Windows. Meme motif que test_wiring_diagram_dialog_i18n_qt.py.
from PyQt6.QtWidgets import QApplication, QLabel, QScrollArea  # noqa: E402
_APP = QApplication.instance() or QApplication([])

from ui.fonts import setup_fonts  # noqa: E402
setup_fonts(_APP)

from ui.theme import theme_manager, build_app_palette  # noqa: E402
import ui.wiring.declare_component_dialog as dcd  # noqa: E402

LANGS = ("fr", "en", "es", "it")
NETS = ["5V", "3V3", "GND"] + [f"D{i}" for i in range(14)] + [f"A{i}" for i in range(6)]

# Plafond de hauteur : un portable 768 px doit pouvoir afficher le formulaire
# ENTIER, barre des taches comprise. C'est la contrainte que la liste de
# broches ne doit jamais faire sauter, quel que soit le nombre de broches.
MAX_DIALOG_HEIGHT = 700

# Marge minimale entre le contenu de la liste et les bords du bloc. 8 px : en
# dessous, ce qui se dessine sur le pourtour touche le contenu ou en sort.
MIN_CONTENT_CLEARANCE = 8


def _styled_app() -> None:
    """L'app telle que `main.py` la monte : style, feuille, barres auto-masquees.

    Les trois comptent, et deux ont ete apprises a la dure (2026-08-12) :

    - **La feuille de style** donne aux champs leur `padding` ; sans elle les
      hauteurs de ligne mesurees ne seraient pas celles que l'utilisateur voit.
    - **Le STYLE Qt** : sous `QT_QPA_PLATFORM=offscreen`, Qt retombe sur
      Fusion, alors que le bureau rend en `windows11`. Une mesure visuelle
      prise sous Fusion ne dit rien de ce que l'utilisateur a sous les yeux —
      c'est ce qui m'a fait chercher pendant une heure une bordure que je ne
      pouvais pas rendre.
    - **L'auto-masquage des barres** force `ScrollBarAlwaysOn` : la barre
      prend ses 10 px EN PERMANENCE. Sans l'installer, le test mesure un
      viewport plus large que le vrai et croit a une marge qui n'existe pas.
    """
    try:
        from PyQt6.QtWidgets import QStyleFactory
        base = QStyleFactory.create("windows11")
        if base is not None:
            _APP.setStyle(base)
        import main as _main
        _APP.setStyle(_main._GreenInfoStyle())
    except Exception:
        pass
    try:
        from ui.auto_hide_scrollbar import install_global_auto_hide
        install_global_auto_hide(_APP)
    except Exception:
        pass
    theme_manager.apply_dark()
    c = theme_manager.current
    _APP.setPalette(build_app_palette(c))
    try:
        import main as _main
        _APP.setStyleSheet(_main._app_style(c))
    except Exception:
        pass


def _dialog(pin_count: int, lang: str):
    dlg = dcd.DeclareComponentDialog(board_nets=NETS, lang=lang)
    dlg._count.setCurrentIndex(dlg._count.findData(pin_count))
    dlg.show()
    _APP.processEvents()
    dlg.adjustSize()
    _APP.processEvents()
    return dlg


def _label_with(dlg, text: str) -> QLabel:
    for lb in dlg.findChildren(QLabel):
        if lb.text() == text:
            return lb
    raise AssertionError(f"legende introuvable : {text!r}")


def _pin_list(dlg) -> QScrollArea:
    """La liste de broches, trouvee par son TYPE.

    Volontairement pas `dlg._scroll` : cet attribut est ne avec le correctif,
    donc un test qui le lit echouerait sur le code d'avant par
    `AttributeError` — sans jamais mesurer la geometrie qu'il pretend
    garder. Verifie : par le type, le test echoue bien sur les chiffres.
    """
    scroll = dlg.findChild(QScrollArea)
    assert scroll is not None, "pas de liste de broches dans le formulaire"
    return scroll


# ---------------------------------------------------------------------------
# 1. Aucune broche cachee
# ---------------------------------------------------------------------------

def test_no_pin_row_is_hidden_up_to_the_row_cap():
    """Jusqu'a PIN_LIST_MAX_ROWS broches, la liste les montre TOUTES.

    C'est le defaut mesure : la 4e broche d'un composant a 4 broches passait
    sous la barre de defilement, sur la taille naturelle du formulaire — donc
    celle que l'utilisateur voit, `exec()` n'imposant aucun redimensionnement.
    """
    _styled_app()
    failures = []
    for lang in LANGS:
        for n in (2, 4, 6, 8):
            dlg = _dialog(n, lang)
            visible = _pin_list(dlg).viewport().height()
            needed = dlg._grid_host.sizeHint().height()
            if needed > visible:
                failures.append(
                    f"{lang}/{n} broches : {needed} px de contenu pour "
                    f"{visible} px visibles")
            dlg.close()
    assert not failures, failures


# ---------------------------------------------------------------------------
# 2. ... mais le formulaire ne grandit pas sans fin pour autant
# ---------------------------------------------------------------------------

def test_beyond_the_cap_the_list_scrolls_instead_of_growing_forever():
    """Garde-fou du test precedent.

    « Faire tenir toutes les broches » se corrige trivialement en laissant le
    formulaire grandir sans limite — et un composant a 40 broches devient
    alors indeclarable sur un portable. Les deux tests ne valent que
    ensemble.
    """
    _styled_app()
    failures = []
    for lang in LANGS:
        for n in (16, 40):
            dlg = _dialog(n, lang)
            if dlg.height() > MAX_DIALOG_HEIGHT:
                failures.append(
                    f"{lang}/{n} broches : formulaire haut de {dlg.height()} px "
                    f"(plafond {MAX_DIALOG_HEIGHT})")
            if dlg._grid_host.sizeHint().height() <= _pin_list(dlg).viewport().height():
                failures.append(
                    f"{lang}/{n} broches : la liste ne defile pas alors "
                    f"qu'elle le devrait")
            dlg.close()
    assert not failures, failures


# ---------------------------------------------------------------------------
# 3. Une legende appartient au champ qu'elle explique
# ---------------------------------------------------------------------------

def test_a_hint_sits_closer_to_its_field_than_to_the_next_one():
    """Mesure sur la geometrie reelle, pas sur les constantes.

    Verifier `ROW_GAP < GROUP_GAP` ne prouverait rien : les deux valeurs
    peuvent etre justes pendant que la legende est posee dans la mauvaise
    colonne. Ici on lit les positions calculees par Qt.
    """
    _styled_app()
    failures = []
    for lang in LANGS:
        dlg = _dialog(4, lang)

        # Groupe « librairie » : champ -> sa legende -> champ suivant.
        hint = _label_with(dlg, dcd._t("lib_hint", lang))
        inside = hint.y() - (dlg._lib.y() + dlg._lib.height())
        outside = dlg._keywords.y() - (hint.y() + hint.height())
        if inside >= outside:
            failures.append(
                f"{lang}/librairie : legende a {inside} px de son champ et "
                f"{outside} px du suivant")

        # Groupe « nombre de broches » : combo -> sa legende -> liste.
        hint2 = _label_with(dlg, dcd._t("drawable", lang))
        inside2 = hint2.y() - (dlg._count.y() + dlg._count.height())
        outside2 = _pin_list(dlg).y() - (hint2.y() + hint2.height())
        if inside2 >= outside2:
            failures.append(
                f"{lang}/broches : legende a {inside2} px de son champ et "
                f"{outside2} px du suivant")
        dlg.close()
    assert not failures, failures


# ---------------------------------------------------------------------------
# 4. Le contenu ne touche pas les bords du bloc
# ---------------------------------------------------------------------------

def test_the_pin_block_content_is_never_flush_with_its_edges():
    """Defaut signale le 2026-08-12 : le bloc etait flush de tous les cotes.

    Contenu a 4 px de ses bords, et surtout dernier menu deroulant a 5 px de
    la barre de defilement — que l'auto-masquage force visible en permanence.
    Ce qui se dessine sur le pourtour du bloc (cadre, anneau de focus selon le
    style du bureau) n'avait alors nulle part ou aller et sortait ROGNE a
    droite et en bas.

    Le cote DROIT est le piege : il faut mesurer contre le viewport, pas
    contre le bloc, sinon on compte comme marge les 10 px que la barre occupe
    deja.
    """
    _styled_app()
    failures = []
    for lang in LANGS:
        dlg = _dialog(4, lang)
        view = _pin_list(dlg).viewport()
        first_le, _ = dlg._rows[0]
        last_le, last_cb = dlg._rows[-1]
        clearances = {
            "gauche": first_le.geometry().left(),
            "droite": view.width() - last_cb.geometry().right() - 1,
            "bas":    view.height() - last_le.geometry().bottom() - 1,
        }
        for side, px in clearances.items():
            if px < MIN_CONTENT_CLEARANCE:
                failures.append(
                    f"{lang}/{side} : {px} px entre le contenu et le bord du "
                    f"bloc (minimum {MIN_CONTENT_CLEARANCE})")
        dlg.close()
    assert not failures, failures


# ---------------------------------------------------------------------------
# 5. Aucun widget orphelin ne hante la liste
# ---------------------------------------------------------------------------

def test_no_orphan_widget_haunts_the_pin_list():
    """Le defaut le plus couteux du formulaire (2026-08-12).

    `_seed` changeait l'index du compteur AVANT que _rebuild_rows explicite ne
    tourne : le signal construisait une premiere fournee de lignes, la seconde
    les retirait par deleteLater — qui ne s'execute pas tant qu'une boucle
    d'evenements n'y passe pas. DIX widgets restaient vivants, visibles,
    enfants du conteneur, a leur geometrie de construction (0,0,640x480) : le
    champ geant couvrait tout le bloc, verdissait au survol (regle QSS
    globale) et son rectangle debordant sortait rogne a droite et en bas.

    Introuvable par toutes les sondes a captures : elles posaient le survol
    sur le bloc, jamais sur l'orphelin. Le test regarde donc la STRUCTURE,
    et il le fait SANS pomper la boucle d'evenements — c'est precisement
    l'etat dans lequel l'app ouvre le formulaire.
    """
    _styled_app()
    failures = []
    for existing in (None, "edit"):
        kw = {}
        if existing:
            from ui.declared_components import DeclaredComponent, DeclaredPin
            kw["existing"] = DeclaredComponent(
                id="t", name="T", headers=(),
                pins=(DeclaredPin("VCC", "power", "5V"),
                      DeclaredPin("GND", "ground", "GND"),
                      DeclaredPin("SDA", "i2c", "A4"),
                      DeclaredPin("SCL", "i2c", "A5")),
                lib="", keywords=("T",))
        dlg = dcd.DeclareComponentDialog(board_nets=NETS, lang="fr", **kw)
        in_layout = set()
        for i in range(dlg._grid.count()):
            w = dlg._grid.itemAt(i).widget()
            if w is not None:
                in_layout.add(id(w))
        from PyQt6.QtWidgets import QWidget
        orphans = [type(ch).__name__ for ch in dlg._grid_host.children()
                   if isinstance(ch, QWidget) and id(ch) not in in_layout]
        if orphans:
            failures.append(f"{'edition' if existing else 'creation'} : "
                            f"{len(orphans)} orphelins {orphans}")
        dlg.close()
    assert not failures, failures


# ---------------------------------------------------------------------------
# 6. Champ et combo d'une meme ligne : un seul gabarit
# ---------------------------------------------------------------------------

def test_pin_field_and_net_combo_share_the_same_footprint():
    """Demande utilisateur (2026-08-12) : sous « Connectée à », les memes
    dimensions que sous « Broche ».

    Le theme donne aux deux controles des paddings differents (champ 33 px de
    haut, combo 21) et seule la colonne des noms portait l'etirement : deux
    gabarits pour deux reponses de meme importance sur la meme ligne. Verifie
    sur la geometrie calculee : meme hauteur, meme largeur, meme y.
    """
    _styled_app()
    failures = []
    for lang in LANGS:
        dlg = _dialog(4, lang)
        for i, (le, cb) in enumerate(dlg._rows):
            g1, g2 = le.geometry(), cb.geometry()
            if g1.height() != g2.height():
                failures.append(f"{lang}/ligne {i} : hauteurs {g1.height()} "
                                f"vs {g2.height()}")
            if abs(g1.width() - g2.width()) > 1:
                failures.append(f"{lang}/ligne {i} : largeurs {g1.width()} "
                                f"vs {g2.width()}")
            if g1.y() != g2.y():
                failures.append(f"{lang}/ligne {i} : y {g1.y()} vs {g2.y()}")
        dlg.close()
    assert not failures, failures


TESTS = [
    test_no_pin_row_is_hidden_up_to_the_row_cap,
    test_beyond_the_cap_the_list_scrolls_instead_of_growing_forever,
    test_a_hint_sits_closer_to_its_field_than_to_the_next_one,
    test_the_pin_block_content_is_never_flush_with_its_edges,
    test_no_orphan_widget_haunts_the_pin_list,
    test_pin_field_and_net_combo_share_the_same_footprint,
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
    # Detruire plusieurs QDialog pendant le teardown Qt statique plante le
    # process sous Windows APRES que les assertions ont deja tranche.
    os._exit(0 if passed == len(TESTS) else 1)
