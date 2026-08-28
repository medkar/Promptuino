"""Entree ne doit jamais declencher une action DESTRUCTIVE (2026-08-11).

Motif Qt, deja connu du depot : dans une modale, un QPushButton `autoDefault`
qui prend le focus (ou simplement le PREMIER du layout) devient le bouton par
defaut, et Entree le clique — meme si le champ de saisie a son propre
`returnPressed`, car l'evenement poursuit sa route quand le slot ne ferme pas
la modale.

L'audit du 2026-08-11 a trouve trois modales sur les six qui posent la
question, plus une quatrieme par symetrie, puis une CINQUIEME (« Code
repare ») que la garde generale laissait passer -- voir plus bas :

- « Nouveau projet » : « Annuler » etant ajoute AVANT « Creer », Entree sur un
  nom invalide fermait la modale sans que le message d'erreur soit vu. Le
  chemin est realiste : `_NAME_RE` refuse accents, apostrophes et points,
  soit « Reveil », « l'alarme », « v1.2 ».
- modale de cablage DEBUTANT : le bouton d'aide « ? » etait le seul
  autoDefault du fichier, donc Entree valait « annule tous mes choix et
  demande de l'aide » -- `_on_help` emet puis appelle `reject()`.
- modale de cablage AVANCEE : meme omission dans sa propre fabrique.
- premier lancement : « Parcourir… », premier widget focusable, s'attribuait
  le role de bouton par defaut et ecrasait le `setDefault(True)` de
  « Continuer ».

⚠️ Ces tests FRAPPENT vraiment la touche (QTest.keyClick) au lieu de lire des
drapeaux : `autoDefault` est une intention, `isDefault` au runtime est le
resultat, et c'est le second qui decide. Le cas « premier lancement » etait
precisement une modale ou l'intention etait bonne et le resultat faux.

--- 2026-08-11, second passage : le trou de la garde generale ---

`RepairCodeDialog` (« Code repare ») n'etait pas balaye, et son bouton par
defaut -- « Fermer » -- n'etait dans aucune liste : la garde interdisait
annuler/supprimer/« ? », pas fermer. Mesure sans le correctif, une fois la
reponse IA arrivee :

    [('Fermer', auto=True, DEFAUT=True, actif),
     ('Appliquer', auto=True, False, actif)]
    Entree -> apply_requested = []  |  visible=False  |  result=Rejected

Entree JETAIT donc une correction deja calculee et deja affichee, sans jamais
passer par « Appliquer ». La seule chose qui limitait les degats etait un
accident : le focus initial tombe sur le panneau de code d'origine, un
QPlainTextEdit en lecture seule qui avale Entree lui-meme. Tout autre etat de
focus atteignait le bouton par defaut.

⚠️ Piege de conception, et raison pour laquelle la garde n'est PAS un
bannissement du mot « fermer » : sur une modale purement informative, avoir la
fermeture par defaut est CORRECT et souhaitable. Les deux formulations ont ete
mesurees sur les modales concernees :

    modale                     defaut          ban-« fermer »   regle retenue
    repair (IA repondue)       'fermer' *      ROUGE            ROUGE
    repair (lecture seule)     'fermer'        ROUGE (faux!)    vert
    lint                       'relancer…'     vert             vert
    explain                    'expliquer'     vert             vert
    add-comments               'appliquer'     vert             vert
    about                      (aucun)         vert             vert
    a4988-vref (pedago)        "j'ai compris"  vert             vert
    (* avant correctif)

Le bannissement aveugle fait rougir le mode LECTURE SEULE de la modale meme
qu'il est cense proteger (« corrections deja appliquees » : rien a appliquer,
« Fermer » est la seule action, il DOIT etre le defaut). Une garde qui rougit
sur du code correct se fait desactiver. La regle retenue dit donc ce qu'on veut
vraiment dire : **une modale qui porte un resultat EN ATTENTE -- c.-a-d. qui
offre un bouton d'application visible ET actif -- ne doit pas avoir la
fermeture comme bouton par defaut**, parce que « Fermer » y veut dire « jette ».

Run : python scripts/test_dialog_enter_key.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton, QDialog

_APP = QApplication.instance() or QApplication([])
_VIVANTS = []

_CODE = "void setup() {\n  pinMode(13, OUTPUT);\n}\nvoid loop() {}\n"
_CORRIGE = "void setup() {\n  pinMode(13, INPUT);\n}\nvoid loop() {}\n"

# Un bouton qui ANNULE ou SUPPRIME : jamais le bouton par defaut, nulle part.
# « ? » ouvre l'aide en appelant reject() dans les modales de cablage.
_DESTRUCTIFS = {"annuler", "cancel", "cancelar", "annulla",
                "supprimer", "delete", "?"}
# Un bouton qui FERME : legitime par defaut sur une modale informative,
# fautif des qu'une application est en attente (cf. l'en-tete du fichier).
_FERMETURES = {"fermer", "close", "cerrar", "chiudi"}
# Un bouton qui VALIDE un resultat : sa presence active fait de la modale une
# modale « a resultat en attente ».
_APPLICATIONS = {"appliquer", "apply", "aplicar", "applica",
                 "creer", "créer", "crear", "creare", "create",
                 "enregistrer", "save", "guardar", "salva"}


class _FauxBackend:
    """Backend IA factice : repond instantanement, ne leve rien (un worker qui
    explose rendrait le balayage bruyant sans rien prouver de plus)."""
    def lint_code(self, *a, **k): return "- rien a signaler"
    def explain_code(self, *a, **k): return "- ce code allume une LED"
    def add_comments(self, *a, **k): return _CODE
    def repair_code(self, *a, **k): return (_CORRIGE, "- corrige la broche")


def _defaut(dlg) -> str:
    """Le bouton que Qt a REELLEMENT promu par defaut, apres affichage."""
    for b in dlg.findChildren(QPushButton):
        if b.isDefault():
            return b.text()
    return ""


def _application_en_attente(dlg) -> bool:
    """La modale porte-t-elle un resultat qu'on peut PERDRE ? = elle offre un
    bouton d'application visible et actif."""
    return any(b.text().strip().lower() in _APPLICATIONS
               and b.isVisible() and b.isEnabled()
               for b in dlg.findChildren(QPushButton))


def _repair_avec_reponse_ia():
    """La modale « Code repare » dans l'etat qui compte : la correction est
    arrivee et attend « Appliquer ». Mode `deferred` + appel direct du slot que
    le worker branche (`finished` -> `_on_done`) : aucun thread, donc aucun
    alea de planification dans un test."""
    from ui.repair_code_dialog import RepairCodeDialog
    dlg = RepairCodeDialog(None, _CODE, "Arduino Uno", deferred=True)
    dlg.show()
    _APP.processEvents()
    dlg._on_done(_CORRIGE, "- corrige le mode de la broche 13")
    _APP.processEvents()
    return dlg


def test_new_project_enter_creates_it_does_not_cancel():
    from ui.projects_view import _NewProjectDialog
    dlg = _NewProjectDialog()
    dlg.show()
    _APP.processEvents()
    _VIVANTS.append(dlg)
    assert _defaut(dlg) == dlg._btn_create.text(), (
        f"bouton par defaut = {_defaut(dlg)!r}, attendu « Creer »")


def test_new_project_enter_on_an_invalid_name_keeps_the_dialog_open():
    """LE cas signale. Un nom accentue est invalide ; la modale doit RESTER
    ouverte et montrer l'erreur, pas se fermer en silence."""
    from ui.projects_view import _NewProjectDialog
    dlg = _NewProjectDialog()
    dlg.show()
    _APP.processEvents()
    _VIVANTS.append(dlg)
    dlg._edit.setText("Réveil")
    dlg._edit.setFocus()
    QTest.keyClick(dlg._edit, Qt.Key.Key_Return)
    _APP.processEvents()
    assert dlg.isVisible(), "la modale s'est fermee sur un nom invalide"
    assert dlg._err.isVisible(), "le message d'erreur n'a pas ete montre"


def test_the_advanced_wiring_dialog_help_button_is_not_default():
    from ui.wiring.netlist import Netlist, Component, Pin
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D5"), Pin("K", "GND")],
                    attributes={"category": "single_output",
                                "_confidence": "low"})
    dlg = AmbiguityDialog([led], netlist=Netlist(board_id="uno_r3",
                                                components=[led]))
    dlg.show()
    _APP.processEvents()
    _VIVANTS.append(dlg)
    for b in dlg.findChildren(QPushButton):
        if b.text() == "?":
            assert not b.autoDefault(), "le « ? » avance est encore autoDefault"


def test_the_advanced_wiring_dialog_search_field_does_not_validate():
    """Le picker de composants a introduit un CHAMP DE SAISIE dans cette modale
    (2026-08-13) : c'est exactement la configuration du bug QA C2 — Entree dans
    un champ de recherche remonte au bouton par defaut et FERME la fenetre
    pendant qu'on cherche.

    La garde vit dans `AmbiguityDialog.keyPressEvent`, qui avale Entree quel
    que soit le widget qui a le focus ; neutraliser la boite de boutons ne
    suffit pas (Qt remet `isDefault` sur OK a chaque show)."""
    from ui.wiring.netlist import Netlist, Component, Pin
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D5"), Pin("K", "GND")],
                    attributes={"category": "single_output",
                                "_confidence": "low"})
    dlg = AmbiguityDialog([led], netlist=Netlist(board_id="uno_r3",
                                                components=[led]))
    dlg.show()
    _APP.processEvents()
    _VIVANTS.append(dlg)
    champ = dlg._pickers["D1"]._search
    champ.setFocus()
    QTest.keyClicks(champ, "buz")
    QTest.keyClick(champ, Qt.Key.Key_Return)
    _APP.processEvents()
    assert dlg.isVisible(), "Entree dans la recherche a ferme la modale"
    assert dlg.result() != QDialog.DialogCode.Accepted.value, \
        "Entree dans la recherche a VALIDE la modale"


def test_the_welcome_dialog_enter_confirms_it_does_not_browse():
    """L'intention etait deja bonne (`setDefault(True)` sur « Continuer ») ;
    c'est le RESULTAT qui etait faux, parce que « Parcourir… » prenait le
    focus en premier. D'ou la verification sur isDefault et non autoDefault."""
    from ui.welcome_dialog import WelcomeDialog
    dlg = WelcomeDialog()
    dlg.show()
    _APP.processEvents()
    _VIVANTS.append(dlg)
    assert _defaut(dlg) == dlg._btn_confirm.text(), (
        f"bouton par defaut = {_defaut(dlg)!r}, attendu « Continuer »")
    assert not dlg._btn_browse.autoDefault()


def test_the_repair_dialog_enter_does_not_discard_a_ready_fix():
    """LE cas du second passage. La correction IA est arrivee et affichee ;
    Entree ne doit pas la jeter par « Fermer ».

    On frappe la touche sur la MODALE : le focus initial repose sur le panneau
    de code d'origine, un QPlainTextEdit qui avale Entree tout seul -- une
    protection accidentelle, pas un choix, et qui saute des que le focus est
    ailleurs (bouton clique, focus perdu, outil d'accessibilite)."""
    dlg = _repair_avec_reponse_ia()
    _VIVANTS.append(dlg)
    assert dlg._btn_apply.isEnabled(), (
        "« Appliquer » inactif : l'etat teste n'est pas le bon")
    assert _defaut(dlg) == dlg._btn_apply.text(), (
        f"bouton par defaut = {_defaut(dlg)!r}, attendu « Appliquer »")

    applique = []
    dlg.apply_requested.connect(applique.append)
    dlg.setFocus()
    QTest.keyClick(dlg, Qt.Key.Key_Return)
    _APP.processEvents()
    ferme_sans_appliquer = (not dlg.isVisible()) and not applique
    assert not ferme_sans_appliquer, (
        "Entree a ferme la modale en jetant la correction "
        f"(apply_requested={applique!r})")
    assert applique == [_CORRIGE], (
        f"Entree devait appliquer la correction, apply_requested={applique!r}")
    assert dlg.result() != QDialog.DialogCode.Rejected.value, (
        "la modale s'est terminee en Rejected malgre l'application")


def test_the_repair_dialog_read_only_mode_still_closes_on_enter():
    """Le pendant du precedent, et la raison pour laquelle la garde ne bannit
    pas le mot « fermer » : en mode LECTURE SEULE (corrections deja appliquees
    automatiquement), « Appliquer » est cache, il n'y a rien a perdre, et
    « Fermer » doit rester le bouton par defaut. Un correctif aveugle qui
    neutraliserait « Fermer » en toutes circonstances laisserait cette modale
    sans aucune action sur Entree."""
    from ui.repair_code_dialog import RepairCodeDialog
    dlg = RepairCodeDialog(None, _CODE, "Arduino Uno",
                           applied=(_CORRIGE, "- corrections automatiques"))
    dlg.show()
    _APP.processEvents()
    _VIVANTS.append(dlg)
    assert not dlg._btn_apply.isVisible(), (
        "« Appliquer » visible en lecture seule : l'etat teste n'est pas le bon")
    assert _defaut(dlg) == dlg._btn_close.text(), (
        f"bouton par defaut = {_defaut(dlg)!r}, attendu « Fermer »")
    dlg.setFocus()
    QTest.keyClick(dlg, Qt.Key.Key_Return)
    _APP.processEvents()
    assert not dlg.isVisible(), "Entree n'a rien fait sur une modale de lecture"


def test_no_dialog_lets_a_destructive_button_be_default():
    """La garde generale, en DEUX etages (cf. l'en-tete du fichier) :

    1. un bouton qui ANNULE ou SUPPRIME n'est jamais le bouton par defaut ;
    2. un bouton qui FERME ne l'est pas non plus des que la modale porte un
       resultat en attente -- sinon Entree veut dire « jette ». Sur une modale
       informative, « Fermer » par defaut reste correct et reste vert."""
    from ui.projects_view import _NewProjectDialog
    from ui.welcome_dialog import WelcomeDialog
    from ui.lib_choice_dialog import LibChoiceDialog
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    from ui.lint_code_dialog import LintCodeDialog
    from ui.explain_code_dialog import ExplainCodeDialog
    from ui.add_comments_dialog import AddCommentsDialog
    from ui.repair_code_dialog import RepairCodeDialog
    from ui.about_dialog import AboutDialog
    fautifs = []
    for nom, fab in (
        ("new-project", _NewProjectDialog),
        ("welcome", WelcomeDialog),
        ("lib-choice", lambda: LibChoiceDialog(
            token="as7341", current_lib="Adafruit AS7341",
            alternatives=["Adafruit AS7341", "DFRobot_AS7341"])),
        ("declare-component", lambda: DeclareComponentDialog(
            board_nets=["5V", "GND", "D2"], lang="fr")),
        # Les modales d'action sur le code : ce sont elles qui portent un
        # resultat a appliquer, donc elles qui peuvent le PERDRE.
        ("repair-code (IA repondue)", _repair_avec_reponse_ia),
        ("repair-code (lecture seule)", lambda: RepairCodeDialog(
            None, _CODE, "Arduino Uno", applied=(_CORRIGE, "- resume"))),
        ("add-comments", lambda: AddCommentsDialog(
            _FauxBackend(), _CODE, "Arduino Uno")),
        ("lint-code", lambda: LintCodeDialog(
            _FauxBackend(), _CODE, "Arduino Uno")),
        ("explain-code", lambda: ExplainCodeDialog(
            _FauxBackend(), _CODE, "", "Arduino Uno")),
        # Temoin informatif : rien a appliquer, la fermeture y est legitime.
        ("about", AboutDialog),
    ):
        dlg = fab()
        dlg.show()
        _APP.processEvents()
        _VIVANTS.append(dlg)
        d = _defaut(dlg).strip().lower()
        if d in _DESTRUCTIFS:
            fautifs.append(f"{nom} -> {d!r} (bouton destructif par defaut)")
        elif d in _FERMETURES and _application_en_attente(dlg):
            fautifs.append(f"{nom} -> {d!r} alors qu'une application est prete "
                           "(Entree jetterait le resultat)")
    assert not fautifs, fautifs


TESTS = [
    test_new_project_enter_creates_it_does_not_cancel,
    test_new_project_enter_on_an_invalid_name_keeps_the_dialog_open,
    test_the_advanced_wiring_dialog_help_button_is_not_default,
    test_the_advanced_wiring_dialog_search_field_does_not_validate,
    test_the_welcome_dialog_enter_confirms_it_does_not_browse,
    test_the_repair_dialog_enter_does_not_discard_a_ready_fix,
    test_the_repair_dialog_read_only_mode_still_closes_on_enter,
    test_no_dialog_lets_a_destructive_button_be_default,
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
