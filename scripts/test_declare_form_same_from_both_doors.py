"""Le formulaire de declaration doit se PEINDRE pareil par ses deux portes.

Constat utilisateur du 2026-08-12 : « ca devrait etre exactement la meme modale,
aucune raison de la construire differemment ». C'est bien la meme classe
(`DeclareComponentDialog`) et le meme code ; ce qui differait, c'est le PARENT.

`AmbiguityDialog._apply_control_styles` posait une feuille de style sur
elle-meme, contenant une regle sur le TYPE de widget :

    QScrollArea > QWidget > QWidget { background: transparent; }

En Qt, une feuille posee sur un widget s'applique a tous ses descendants — un
dialogue ENFANT compris. Le formulaire ouvert depuis le schema voyait donc son
bloc de broches rendu TRANSPARENT : plus de panneau, plus de cadre, les broches
flottant sur le fond. Mesure avant correctif : 35,5 % de la surface du
formulaire differait entre les deux portes, sur une bande de 301 px de haut —
exactement le bloc de broches.

Le correctif nomme le panneau defilant de la modale d'ambiguite
(`objectName = "ambiguityScroll"`) et restreint la regle a CE panneau.

Ce test construit une VRAIE `AmbiguityDialog` — donc la vraie feuille de style,
pas une copie qui se perimerait en silence — et compare les deux rendus.

Run : python scripts/test_declare_form_same_from_both_doors.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QDialog          # noqa: E402
from PyQt6.QtGui import QCursor, QImage                    # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level

from ui.fonts import setup_fonts                           # noqa: E402
setup_fonts(_APP)

from ui.theme import theme_manager, build_app_palette, app_qss   # noqa: E402
from ui.wiring.netlist import Component, Netlist, Pin            # noqa: E402
from ui.wiring.ambiguity_dialog import AmbiguityDialog           # noqa: E402
from ui.wiring.declare_component_dialog import DeclareComponentDialog  # noqa: E402
import ui.declared_components as declared_components             # noqa: E402

# Meme montage que `main.py` : sans la feuille applicative, on mesurerait un
# rendu qui n'existe nulle part.
_C = theme_manager.current
_APP.setPalette(build_app_palette(_C))
_APP.setStyleSheet(app_qss(_C))

# La bibliotheque de composants vient de la MEMOIRE, jamais du disque : on la
# vide pour que le test ne depende pas du ~/Documents/Promptuino de la machine.
declared_components.set_registry([])

# Piege memorise (2026-08-11) : en offscreen `QCursor.pos()` est fige a (10,10)
# et force le :hover sur tout widget proche de l'origine. On eloigne le curseur
# ET les fenetres, sinon deux rendus identiques peuvent differer par un survol.
QCursor.setPos(2000, 2000)

NETS = ["5V", "GND", "D2", "D3", "A0"]

# Les parents doivent SURVIVRE a la mesure : un QDialog temporaire est ramasse
# par le GC et emporte son enfant, ce qui donne « wrapped C/C++ object ... has
# been deleted » au moment du grab. On les retient ici.
_VIVANTS: list = []


def _neutral_parent() -> QDialog:
    """La porte « onglet Composants » : aucun ancetre ne stylise ces widgets."""
    p = QDialog()
    _VIVANTS.append(p)
    return p


def _ambiguity_parent() -> AmbiguityDialog:
    """Une vraie modale d'ambiguite, donc sa vraie feuille de style."""
    led = Component(
        ref="D1", type="led",
        pins=[Pin("A", "D5"), Pin("K", "GND")],
        attributes={"category": "single_output", "_confidence": "low"},
    )
    dlg = AmbiguityDialog([led], netlist=Netlist(board_id="",
                                                 components=[led]))
    _VIVANTS.append(dlg)
    return dlg


def _render(parent) -> QImage:
    dlg = DeclareComponentDialog(parent, board_nets=NETS, lang="fr")
    dlg.move(800, 800)
    dlg.resize(640, 620)
    dlg.show()
    _APP.processEvents()
    img = dlg.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
    dlg.hide()
    return img


def _differing_pixels(a: QImage, b: QImage) -> int:
    assert a.size() == b.size(), f"tailles differentes : {a.size()} / {b.size()}"
    return sum(1 for y in range(a.height()) for x in range(a.width())
               if a.pixel(x, y) != b.pixel(x, y))


def test_the_pin_block_keeps_its_panel_from_the_schema_door():
    """Le symptome exact : le bloc de broches perdait son fond opaque.

    Teste separement du plein cadre ci-dessous parce qu'il NOMME le defaut :
    un echec ici dit « le bloc a reperdu son panneau », pas « quelque chose a
    change quelque part »."""
    par_composants = DeclareComponentDialog(_neutral_parent(),
                                            board_nets=NETS, lang="fr")
    par_schema = DeclareComponentDialog(_ambiguity_parent(), board_nets=NETS,
                                        lang="fr")
    couleurs = []
    for dlg in (par_composants, par_schema):
        dlg.move(800, 800)
        dlg.resize(640, 620)
        dlg.show()
        _APP.processEvents()
        img = dlg._grid_host.grab().toImage()
        couleurs.append(img.pixelColor(img.width() // 2, 8).name())
        dlg.hide()
    assert couleurs[0] == couleurs[1], (
        f"le bloc de broches n'a pas le meme fond selon la porte : "
        f"onglet Composants {couleurs[0]}, schema {couleurs[1]}")


def test_the_whole_form_renders_identically_from_both_doors():
    """Le filet large : TOUTE la surface, pas seulement l'endroit soupconne.

    La feuille de la modale d'ambiguite porte aussi des regles QLabel,
    QGroupBox et QDialog, qui cascadent pareil. Aucune ne causait de difference
    mesurable au 2026-08-12, mais rien ne le garantissait — ce test le
    garantit."""
    a = _render(_neutral_parent())
    b = _render(_ambiguity_parent())
    n = _differing_pixels(a, b)
    total = a.width() * a.height()
    assert n == 0, (f"{n} pixels sur {total} ({100 * n / total:.1f} %) different "
                    f"entre les deux portes")


def test_the_ambiguity_sheet_no_longer_targets_a_bare_scrollarea():
    """Verrou par la source, pour NOMMER la cause si elle revient.

    Les deux tests ci-dessus attrapent le symptome ; celui-ci dit pourquoi.
    Une regle sur le type nu `QScrollArea` s'echappe du dialogue et repeint
    n'importe quel descendant — c'est la forme du defaut, pas cette occurrence
    precise."""
    dlg = _ambiguity_parent()
    feuille = dlg.styleSheet()
    assert "QScrollArea#ambiguityScroll" in feuille, \
        "la regle n'est plus restreinte au panneau de cette modale"
    # L'invariant est « TOUTE regle QScrollArea est restreinte par un
    # objectName », pas « il en existe une nommee ambiguityScroll ». La
    # premiere redaction codait ce nom en dur et refusait donc un SECOND
    # panneau correctement restreint (le rail des decisions, TODO #73) tout
    # en laissant passer... rien de plus : elle attrapait deja le type nu.
    # Elargie ici a sa vraie forme, elle couvre les deux panneaux et tous
    # ceux qui viendront.
    for ligne in feuille.splitlines():
        nu = ligne.strip()
        if not nu.startswith("QScrollArea"):
            continue
        selecteur = nu.split("{")[0].strip()
        if "#" not in selecteur:
            raise AssertionError(
                f"regle sur le type nu QScrollArea, elle s'echappera : {nu!r}")


TESTS = [
    test_the_pin_block_keeps_its_panel_from_the_schema_door,
    test_the_whole_form_renders_identically_from_both_doors,
    test_the_ambiguity_sheet_no_longer_targets_a_bare_scrollarea,
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
