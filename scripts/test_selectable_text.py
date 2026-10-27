"""Le texte INFORMATIF se copie ; les cards restent cliquables (TODO #95).

Ne d'un besoin concret pendant la QA du 2026-09-07 : « je ne peux pas te
copier-coller le texte de la banniere ». Mesure alors : 238 `QLabel` dans
`ui/`, dont 4 selectionnables.

⛔ Ce fichier verrouille surtout le PIEGE. L'interrupteur global tient en une
ligne et couvre meme le code futur -- mais un label selectionnable CAPTE le
clic, qui n'atteint plus le widget parent. Les cards cliquables (Composants,
projets, modale d'ambiguite, choix de bibliotheque) deviendraient inertes sur
toute leur zone de texte. La moitie qui compte de ces tests n'est donc pas
« le texte se copie » mais « les cards n'ont PAS ete touchees ».

Run : python scripts/test_selectable_text.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QLabel

# QApplication gardee au niveau module (piege 0xC0000409 sous Windows).
_APP = QApplication.instance() or QApplication(sys.argv)

from ui.selectable_text import is_selectable, make_selectable

# ⚠️ Reference gardee sur CHAQUE widget construit, meme motif que `_APP` juste
# au-dessus mais un cran plus bas. Un widget sans parent est ramasse par le GC
# des la fin de la fonction ; Qt le detruit alors sous ses propres pieds, et la
# construction SUIVANTE d'un widget de haut niveau fait mourir le process --
# sans trace, la sortie restant dans le tampon. Mesure : les tests passaient un
# a un et le fichier entier mourait au troisieme.
_VIVANTS: list = []


def _garde(widget):
    """Construit et retient. Tout widget de test passe par ici."""
    _VIVANTS.append(widget)
    return widget

# Modules dont les widgets sont faits pour etre CLIQUES, pas lus. Aucun ne
# doit rendre ses labels selectionnables.
_MODULES_DE_CARDS = (
    "ui/wiring/ambiguity_cards.py",
    "ui/components_view.py",
    "ui/projects_view.py",
    "ui/lib_choice_dialog.py",
    "ui/wiring/component_picker.py",
)


def test_the_amber_banner_can_be_copied():
    """LE cas signale : la banniere porte des noms de bibliotheque et des
    messages d'erreur de fournisseur -- exactement ce qu'on veut coller dans
    une recherche ou dans un signalement."""
    from ui.nudge_banner import NudgeBanner
    for variante in ("ok", "info"):
        banniere = _garde(NudgeBanner(variant=variante))
        assert is_selectable(banniere._lbl), variante


def test_the_wiring_modals_can_be_copied():
    """Elles sont faites pour etre LUES : prescriptions de cavaliers, loi
    d'Ohm, courants, tableau des micro-pas."""
    from ui.wiring.wiring_diagram_dialog import (_A4988VrefInfoDialog,
                                                 _BuzzerSeriesValueDialog,
                                                 _LedSeriesValueDialog)
    cas = [
        (_A4988VrefInfoDialog, dict(ref="U1")),
        (_BuzzerSeriesValueDialog,
         dict(ref="LS1", current_value="100", comp_type="speaker")),
        (_LedSeriesValueDialog, dict(ref="D1", current_value="220")),
    ]
    for cls, kw in cas:
        dlg = _garde(cls(None, **kw))
        make_selectable(dlg)
        labels = dlg.findChildren(QLabel)
        assert labels, f"{cls.__name__} n'a aucun label a tester"
        non = [l.text()[:30] for l in labels if not is_selectable(l)]
        assert not non, f"{cls.__name__} : labels non copiables {non}"


def test_the_status_bar_and_ai_screen_can_be_copied():
    """2e lot (2026-09-08) : les deux ecrans qui portent de l'information.

    La barre d'etat nomme le MODELE et la CARTE ; l'ecran Modele IA porte les
    messages bruts des fournisseurs -- le #92 a rendu visible « This model is
    no longer available… Please update your code to use … », un texte fait
    pour etre colle dans une recherche et qu'on ne pouvait pas selectionner.

    ⚠️ On exige TOUS les labels porteurs de texte, pas un echantillon : c'est
    ce qui attrape un label ajoute plus tard dans un de ces ecrans.
    """
    from ui.ia_view import IAView
    from ui.statusbar import StatusBar

    for nom, widget in (("barre d'etat", _garde(StatusBar())),
                        ("ecran Modele IA", _garde(IAView()))):
        labels = [l for l in widget.findChildren(QLabel) if (l.text() or "").strip()]
        assert labels, f"{nom} : aucun label a tester, le test ne conclurait rien"
        non = [l.text()[:40] for l in labels if not is_selectable(l)]
        assert not non, f"{nom} : {len(non)} label(s) non copiable(s) {non}"


def test_the_journal_and_instructions_were_already_copiable():
    """Ce qu'il ne fallait PAS refaire, verifie plutot que suppose.

    Le ticket pariait que le journal et les instructions etaient deja
    copiables « autrement ». C'est vrai : ce sont des zones de texte en
    lecture seule (`QTextEdit` / `QTextBrowser`), selectionnables par nature.
    Les couvrir avec le helper aurait ete du travail pour rien -- et ce test
    empeche qu'on les rende un jour NON copiables sans s'en apercevoir.
    """
    from PyQt6.QtCore import Qt
    from ui.studio_view import StudioView

    v = _garde(StudioView())
    for nom, zone in (("journal", v._console.log._text),
                      ("moniteur serie", v._serial_monitor._display)):
        assert zone.isReadOnly(), f"{nom} doit rester en lecture seule"
        assert zone.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse, (
            f"{nom} n'est plus selectionnable")


def test_the_clickable_cards_are_left_alone():
    """⛔ LA garde du ticket, verifiee a l'EXECUTION.

    Un label selectionnable capte le clic. Si une card en contenait un, sa
    zone de texte cesserait de reagir -- et aucun test de « le texte se
    copie » ne le verrait.
    """
    from ui.wiring.ambiguity_cards import ComponentCard
    card = _garde(ComponentCard(None, type_id="led", name="LED"))
    labels = card.findChildren(QLabel)
    assert labels, "la card n'a aucun label : le test ne conclurait rien"
    fautifs = [l.text()[:30] for l in labels if is_selectable(l)]
    assert not fautifs, (
        f"une card cliquable a des labels selectionnables {fautifs} : ils "
        f"capteront le clic destine a la card")


def test_no_card_module_calls_make_selectable():
    """La meme regle, enoncee a la SOURCE plutot que deduite d'un cas.

    Le test ci-dessus n'exerce qu'une card ; celui-ci couvre tous les modules
    de cards, y compris ceux qu'on ne sait pas construire a bon compte.
    """
    fautifs = []
    for chemin in _MODULES_DE_CARDS:
        f = ROOT / chemin
        if not f.exists():
            continue
        arbre = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "make_selectable":
                fautifs.append(f"{chemin}:{n.lineno}")
    assert not fautifs, (
        f"un module de cards rend son texte selectionnable {fautifs} : le "
        f"label capterait le clic destine a la card")


def test_the_helper_reports_what_it_touched():
    """`make_selectable` rend un COMPTE, et les tests s'en servent.

    Sans lui, une garde pourrait passer en appelant le helper sur un
    conteneur vide -- elle verifierait l'appel, pas l'effet.
    """
    from PyQt6.QtWidgets import QVBoxLayout, QWidget
    conteneur = _garde(QWidget())
    lay = QVBoxLayout(conteneur)
    for i in range(3):
        lay.addWidget(QLabel(f"ligne {i}"))
    assert make_selectable(conteneur) == 3
    assert make_selectable(QWidget()) == 0, "un conteneur vide rend zero"
    # Un label passe directement se compte lui-meme.
    assert make_selectable(QLabel("seul")) == 1


def test_selection_does_not_break_the_links():
    """Un texte selectionnable ne doit pas perdre ses liens cliquables.

    Plusieurs modales pedagogiques portent des `<a href>`. Poser le seul
    drapeau `TextSelectableByMouse` les aurait rendus inertes -- c'est
    pourquoi le helper pose aussi `LinksAccessibleByMouse`.
    """
    from PyQt6.QtCore import Qt
    label = _garde(QLabel('<a href="https://exemple">lien</a>'))
    make_selectable(label)
    drapeaux = label.textInteractionFlags()
    assert drapeaux & Qt.TextInteractionFlag.LinksAccessibleByMouse, (
        "les liens des modales pedagogiques doivent rester cliquables")
    assert drapeaux & Qt.TextInteractionFlag.TextSelectableByKeyboard, (
        "sans la selection clavier, Ctrl+A / Ctrl+C ne marchent pas")


TESTS = [
    test_the_amber_banner_can_be_copied,
    test_the_wiring_modals_can_be_copied,
    test_the_status_bar_and_ai_screen_can_be_copied,
    test_the_journal_and_instructions_were_already_copiable,
    test_the_clickable_cards_are_left_alone,
    test_no_card_module_calls_make_selectable,
    test_the_helper_reports_what_it_touched,
    test_selection_does_not_break_the_links,
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
