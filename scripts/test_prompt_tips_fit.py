"""#108 : une astuce trop longue etait COUPEE, en silence.

Le champ de saisie du chat a une hauteur FIXE (80 px) et son placeholder est
peint a la main (`_ChatInput.paintEvent`) parce que Qt rend celui d'un
QTextEdit sur une seule ligne tronquee. Mais `drawText` peint dans un
RECTANGLE : ce qui depasse est coupe. Pas de barre de defilement -- un
placeholder n'en a pas --, pas d'ellipse. La troncature est donc invisible.

⚠️ **Le retour a la ligne avait ete ajoute sans revoir la hauteur** : le
correctif d'alors a transforme << une ligne coupee >> en << trois lignes dont
la derniere est coupee >>. Mieux, et le meme defaut.

MESURE du 2026-09-14, sur le widget tel qu'il vit DANS l'application :

    boite de texte reelle : 290 x 54 px, soit 3 lignes de 16 px
    astuces coupees       : 4 sur 76 -- la MEME, dans ses 4 traductions
                            (180 a 198 caracteres, 64 px pour 54 disponibles)
    apres raccourcissement: 0 sur 76, la plus longue tenant a 123 caracteres

⛔ **Trois mesures fausses avant la bonne, et la raison vaut d'etre retenue** :
un `_ChatInput` construit NU n'a pas la police que la feuille de l'application
lui donne, et sa boite fait 314 x 70 au lieu de 290 x 54 -- il concluait
<< aucune astuce coupee >> pendant qu'une capture du vrai panneau montrait la
coupure. La feuille est donc appliquee ci-dessous, et les dimensions viennent
du widget REEL, pas d'un widget de laboratoire.

Run: python scripts/test_prompt_tips_fit.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtCore import Qt, QRect  # noqa: E402
from PyQt6.QtGui import QFontMetrics  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

from ui.fonts import setup_fonts  # noqa: E402
setup_fonts(_APP)
from ui.theme import theme_manager, app_qss  # noqa: E402
_APP.setStyleSheet(app_qss(theme_manager.current))

from ui.chat.chat_view import (  # noqa: E402
    _ChatInput, _DEFAULT_WIDTH, _COLLAPSED_WIDTH)
from ui.i18n import TRANSLATIONS  # noqa: E402

_LANGUES = ("fr", "en", "es", "it")

# Boite de texte MESUREE sur le champ tel qu'il vit dans l'application
# (panneau de chat deplie, fenetre 1280x800) le 2026-09-14.
#
# ⚠️ C'est un RELEVE, pas un calcul : la largeur depend de la barre de
# defilement reservee et la hauteur du cadre pose par la feuille, deux choses
# qu'un widget construit a part ne reproduit pas. Pour la refaire : ouvrir la
# fenetre, deplier le chat, lire `viewport().width()/height()` moins deux fois
# `document().documentMargin()`.
#
# Les deux constantes qui la PRODUISENT sont verrouillees juste en dessous :
# si l'une bouge, ce releve est perime et le test le dit, au lieu de mesurer
# contre une boite qui n'existe plus.
LARGEUR_TEXTE = 290
HAUTEUR_TEXTE = 54

_DRAPEAUX = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap)


def _metriques() -> QFontMetrics:
    """Metriques du champ AVEC la feuille de l'application -- sans elle, la
    police n'est pas celle de l'app et toute la mesure est fausse."""
    champ = _ChatInput()
    champ.show()
    _APP.processEvents()
    return QFontMetrics(champ.font())


def _hauteur(texte: str) -> int:
    return _metriques().boundingRect(
        QRect(0, 0, LARGEUR_TEXTE, 10_000), _DRAPEAUX, texte).height()


def _trop_longues() -> list[tuple[str, int, int, str]]:
    """(langue, longueur, hauteur, texte) des astuces qui debordent."""
    out = []
    for lg in _LANGUES:
        for t in TRANSLATIONS[lg].prompt_tips:
            h = _hauteur(t)
            if h > HAUTEUR_TEXTE:
                out.append((lg, len(t), h, t))
    return out


# ── LE test ───────────────────────────────────────────────────────────────

def test_no_tip_is_silently_cut():
    """Aucune astuce ne doit depasser la boite. La troncature n'a ni barre de
    defilement ni ellipse : rien ne la signale, ni a l'utilisateur ni a
    celui qui redige l'astuce."""
    fautives = _trop_longues()
    # Le texte n'entre PAS dans le message : il contient des accents que la
    # console Windows ne sait pas toujours encoder, et le lanceur mourrait
    # sur le message au lieu de rapporter le defaut.
    resume = [(lg, n, h) for lg, n, h, _ in fautives]
    assert not fautives, resume


def test_the_four_languages_are_all_measured():
    """L'italien est la langue qui MORD (198 caracteres contre 190 en
    francais) : un budget verifie sur le seul francais laisserait passer
    exactement le cas d'origine."""
    comptes = {lg: len(TRANSLATIONS[lg].prompt_tips) for lg in _LANGUES}
    assert len(set(comptes.values())) == 1, comptes
    assert all(n > 0 for n in comptes.values()), comptes


def test_the_measured_box_still_matches_its_constants():
    """⚠️ La garde de la garde. La boite ci-dessus est un RELEVE ; il est
    valable tant que la largeur du panneau et la hauteur du champ n'ont pas
    bouge. Si l'une change, ce test rougit -- et il faut RE-MESURER, pas
    ajuster les chiffres au jugé."""
    assert _DEFAULT_WIDTH == 340, _DEFAULT_WIDTH
    champ = _ChatInput()
    assert champ.height() == 80, champ.height()
    assert _COLLAPSED_WIDTH < _DEFAULT_WIDTH


def test_the_stylesheet_is_what_fixes_the_font():
    """⛔ La lecon des trois mesures fausses, verrouillee : sans la feuille de
    l'application, la police du champ n'est pas celle de l'app. Un futur test
    qui oublierait `setStyleSheet` mesurerait une autre boite et conclurait
    faux -- exactement ce qui est arrive."""
    metriques = _metriques()
    assert metriques.lineSpacing() == 16, metriques.lineSpacing()
    # 3 lignes tiennent, 4 ne tiennent pas : c'est ce qui rend le budget
    # serre et l'astuce d'origine hors limites.
    assert HAUTEUR_TEXTE // metriques.lineSpacing() == 3


def test_a_deliberately_long_tip_is_caught():
    """Verification PAR MUTATION, dans le test lui-meme : la mesure doit
    savoir dire non. Sans ca, un `_hauteur` casse rendrait toujours 0 et le
    test passerait au vert sur n'importe quel texte."""
    trop = ("Astuce : " + "un texte deliberement tres long " * 8).strip()
    assert _hauteur(trop) > HAUTEUR_TEXTE, _hauteur(trop)


TESTS = [
    test_no_tip_is_silently_cut,
    test_the_four_languages_are_all_measured,
    test_the_measured_box_still_matches_its_constants,
    test_the_stylesheet_is_what_fixes_the_font,
    test_a_deliberately_long_tip_is_caught,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
