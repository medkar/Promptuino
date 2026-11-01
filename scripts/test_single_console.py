"""Une SEULE console pour les trois modes (TODO #99).

Contexte, signale en QA le 2026-09-08 pendant AL3 : « si je passe de int a
avance, le journal est le meme et ca ne coupe pas la console. Mais si je passe
de int a debutant, le journal change et ca coupe la console. »

Le diagnostic tenait en trois faits :
  - `_mount_editor_console` reparente UN SEUL widget console entre les
    conteneurs intermediaire et avance -- sa docstring promettait deja
    « aucun contenu/etat perdu au changement de mode » ;
  - le DEBUTANT avait sa propre `ConsolePanel`, donc son propre journal et son
    propre port serie ;
  - et `_on_mode_changed` fermait deliberement « le port de l'autre mode », ce
    qui ne fermait rien d'actif entre int et avance mais coupait la liaison en
    cours des qu'on passait en debutant.

Ce fichier verrouille l'unification ET les deux pieges que le ticket
signalait : l'habit doit changer sans que l'objet change, et la raison d'etre
du `close_port` (ne jamais ouvrir le port automatiquement) doit survivre.

Run : python scripts/test_single_console.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication

# QApplication gardee au niveau module : sans reference vivante, une app
# temporaire GC-ee puis la construction d'un QWidget plante le process sous
# Windows (0xC0000409) -- piege documente dans
# test_wiring_diagram_dialog_i18n_qt.py.
_APP = QApplication.instance() or QApplication(sys.argv)

_MODES = ("beginner", "intermediate", "advanced")


def _vue():
    from ui.studio_view import StudioView
    return StudioView()


def _dans(widget, conteneur) -> bool:
    """True si `widget` est quelque part sous `conteneur`."""
    p = widget
    while p is not None:
        if p is conteneur:
            return True
        p = p.parent()
    return False


def test_the_three_modes_share_one_console():
    """Le coeur du ticket : un seul objet, donc un seul journal et un seul port.

    Deux consoles, c'etaient deux transcriptions du meme projet et deux ports
    dont un se fermait a chaque bascule.
    """
    v = _vue()
    assert v._beg_console is v._adv_console, "deux consoles subsistent"
    assert v._beg_output_area is v._output_area, "deux journaux subsistent"
    assert v._serial_monitor_beg is v._serial_monitor, "deux moniteurs subsistent"


def test_the_console_travels_to_the_right_container():
    """Elle doit vraiment se DEPLACER, aller et retour.

    Un test qui ne verifierait que l'identite des objets passerait meme si la
    console restait coincee dans un conteneur cache.
    """
    v = _vue()
    slots = {
        "beginner": v._beg_console_slot,
        "intermediate": v._int_console_slot,
        "advanced": v._adv_console_slot,
    }
    # Aller, puis RETOUR au debutant : c'est le retour qui casserait si le
    # reparentage etait a sens unique.
    for mode in ("beginner", "intermediate", "advanced", "beginner"):
        v._on_mode_changed(mode)
        assert _dans(v._console_w, slots[mode]), (
            f"[{mode}] la console n'est pas dans son conteneur")


def test_the_outfit_changes_without_changing_the_object():
    """Ce que le ticket designait comme le vrai travail.

    Le debutant place ses controles serie dans sa ligne de titre et n'a pas de
    selecteur de baud ; l'int/avance les met sous le journal. C'est l'HABIT qui
    change, pas l'objet -- sinon on retombe sur deux consoles.
    """
    v = _vue()
    ctrl = v._serial_monitor.get_ctrl_widget()

    v._on_mode_changed("beginner")
    assert _dans(ctrl, v._beg_serial_slot), (
        "en debutant, les controles vont dans la ligne de titre")
    assert v._console.log._bottom_overlay is None, (
        "en debutant, pas de barre serie sous le journal")

    v._on_mode_changed("intermediate")
    assert not _dans(ctrl, v._beg_serial_slot)
    assert v._console.log._bottom_overlay is not None, (
        "en int/avance, la barre serie revient sous le journal")
    # Et c'est bien le MEME widget qui a voyage.
    assert v._serial_monitor.get_ctrl_widget() is ctrl


def test_changing_mode_never_closes_the_port():
    """LE symptome signale : la liaison serie tombait en passant en debutant.

    On ne peut pas ouvrir un vrai port dans un test ; on observe donc l'appel
    lui-meme, ce qui est plus strict -- il ne doit pas y en avoir du tout.
    """
    v = _vue()
    appels = []
    v._serial_monitor.close_port = lambda *a, **k: appels.append("close")
    for mode in ("beginner", "intermediate", "advanced", "beginner",
                 "intermediate", "beginner"):
        v._on_mode_changed(mode)
    assert not appels, (
        f"{len(appels)} fermeture(s) de port pendant des changements de mode")


def test_the_shared_journal_survives_a_mode_change():
    """Le second symptome : la transcription changeait avec le mode.

    ⚠️ Ce test a trouve un obstacle reel pendant le chantier :
    `_on_mode_changed` VIDAIT le journal avant d'y reecrire la ligne d'etat,
    pour eviter de l'empiler. Anodin quand chaque mode avait le sien ; avec un
    journal partage, ca effacait la transcription commune a chaque bascule et
    aurait annule tout l'interet du ticket.
    """
    v = _vue()
    v._console.log.append_raw("SORTIE DE COMPILATION")
    for mode in ("beginner", "intermediate", "advanced", "beginner"):
        v._on_mode_changed(mode)
    texte = v._console.log._text.toPlainText()
    assert "SORTIE DE COMPILATION" in texte, (
        "le journal partage a ete efface par un changement de mode")


def test_the_status_line_appears_once_and_only_once():
    """L'autre moitie : ne pas empiler non plus.

    `begin_phase` AJOUTE une ligne, il ne remplace pas -- c'est pour ca que le
    code vidait le journal. La ligne d'etat doit donc paraitre au demarrage
    (journal vide) et ne jamais se repeter aux bascules suivantes.
    """
    v = _vue()
    texte = v._console.log._text.toPlainText()
    assert texte.strip(), "la ligne d'etat doit paraitre au demarrage"
    for mode in ("beginner", "intermediate", "advanced", "beginner"):
        v._on_mode_changed(mode)
    final = v._console.log._text.toPlainText()
    assert final.count("Aucun code") <= 1, (
        f"ligne d'etat empilee : {final!r}")


def test_the_reason_behind_close_port_survives():
    """⛔ Le piege que le ticket signalait explicitement.

    Le `close_port` avait une raison DOCUMENTEE a cote : ne JAMAIS ouvrir le
    port automatiquement au changement de mode -- se connecter d'office
    risquait le mauvais debit et saturait la boucle de lecture (latences
    mesurees). Supprimer le bloc ne devait pas emporter cette regle avec lui.
    """
    v = _vue()
    ouvertures = []
    v._serial_monitor.open_port = lambda *a, **k: ouvertures.append("open")
    for mode in _MODES:
        v._on_mode_changed(mode)
    assert not ouvertures, (
        "le port ne doit JAMAIS s'ouvrir tout seul a un changement de mode")


def test_the_baud_label_follows_its_selector():
    """« Baud » ne doit pas rester seul quand le sélecteur est masqué.

    Signalé en QA AM3 (2026-09-08) : en Débutant, le mot « Baud » subsistait
    sans son sélecteur -- un libellé qui ne désigne plus rien. C'est un ORDRE
    D'APPEL : `set_compact()` force `_lbl_baud.setVisible(True)` en son sein,
    donc appelé APRÈS `set_baud_visible(False)` il annulait le masquage. Le
    dernier mot revient à l'appel qui exprime l'intention.

    ⚠️ On lit `isHidden()` et non `isVisible()` : hors écran, aucun widget
    n'est « visible » (la fenêtre n'est jamais montrée), donc `isVisible()`
    rendrait False partout et le test passerait pour de mauvaises raisons.
    """
    v = _vue()
    m = v._serial_monitor
    attendu = {"beginner": True, "intermediate": False, "advanced": False}
    # Aller-retour : c'est le RETOUR au débutant qui casserait si l'ordre
    # n'était corrigé que dans une branche.
    for mode in ("beginner", "intermediate", "advanced", "beginner"):
        v._on_mode_changed(mode)
        assert m._lbl_baud.isHidden() is attendu[mode], (
            f"[{mode}] libellé « Baud » masqué = {m._lbl_baud.isHidden()}")
        assert m._baud_combo.isHidden() is attendu[mode], (
            f"[{mode}] sélecteur de baud masqué = {m._baud_combo.isHidden()}")


def test_loading_a_project_writes_ONE_status_line():
    """Deux « Code prêt : … » s'empilaient en changeant de projet.

    Signalé en QA AM2 (2026-09-08) : ouvrir un projet A puis un projet B
    laissait les DEUX lignes, celle d'avant et celle d'après. C'est l'ordre de
    `load_project` : il vide le journal, PUIS change de mode, PUIS injecte le
    code, PUIS écrit la ligne. Le changement de mode trouvait un journal vide
    et écrivait une ligne décrivant le code du projet PRÉCÉDENT, encore dans
    l'éditeur à cet instant.

    Régression introduite par le #99 lui-même : avant, le changement de mode
    VIDAIT le journal, ce qui masquait le doublon.
    """
    import pathlib
    from ui import studio_view
    from ui.project_manager import Project

    v = _vue()
    codes = {"Projet A": "void setup(){}\nvoid loop(){digitalWrite(13,HIGH);}",
             "Projet B": "void setup(){}\nvoid loop(){analogRead(A0);}"}
    original = studio_view.project_manager.load_code
    studio_view.project_manager.load_code = lambda p: codes[p.name]
    try:
        for nom, mode in (("Projet A", "beginner"), ("Projet B", "intermediate"),
                          ("Projet A", "beginner"), ("Projet B", "advanced")):
            v.load_project(Project(path=pathlib.Path("/tmp") / nom, name=nom,
                                   type="arduino", mode=mode))
            texte = v._console.log._text.toPlainText()
            lignes = texte.count("Code prêt") + texte.count("Aucun code")
            assert lignes == 1, (
                f"apres « {nom} » : {lignes} lignes d'etat au lieu d'une "
                f"({texte.strip()!r})")
    finally:
        studio_view.project_manager.load_code = original


def test_the_autoscroll_sits_flush_right_in_beginner():
    """MESURE de mise en page, pas une supposition (QA AM3, 2026-09-08).

    Signale avec une capture : « Defilement auto » flottait au milieu de la
    ligne au lieu de longer le bord droit du journal. Deux causes empilees :

    1. le widget de controles prenait sa largeur NATURELLE dans son slot
       (pas de `stretch`), donc son ressort interne ne poussait qu'au bord de
       son propre contenu ;
    2. et surtout, `set_compact(False)` ne RESTAURAIT pas la disposition --
       seule la branche compacte reconstruisait. L'ordre compact survivait
       donc en Debutant, avec son ressort FINAL qui centre. Sans consequence
       tant que chaque mode avait sa barre ; fatal des qu'une seule console
       sert les trois modes.

    ⚠️ Ce test EXIGE une fenetre montree et dimensionnee : hors affichage,
    toutes les geometries valent zero et l'assertion passerait pour rien.
    """
    v = _vue()
    v.resize(1180, 800)
    v.show()
    _APP.processEvents()

    from PyQt6.QtWidgets import QStyle, QStyleOptionButton

    def bord_droit(w):
        return w.mapTo(v, w.rect().topRight()).x()

    def bord_visible_case(chk):
        """Bord droit du CARRE dessine, pas de la boite du widget.

        ⚠️ C'est la distinction qui m'a fait conclure « 0 px » a tort deux
        fois. Une QCheckBox SANS TEXTE reserve quand meme l'espacement
        indicateur↔libellé (`PM_CheckBoxLabelSpacing`, 8 px ici) : sa
        geometrie depasse de 8 px le carre que l'utilisateur voit. Mesurer le
        widget donnait donc « aligne » alors que l'oeil voyait un decalage.
        """
        opt = QStyleOptionButton()
        opt.initFrom(chk)
        ind = chk.style().subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator, opt, chk)
        return chk.mapTo(v, ind.topRight()).x()

    v._on_mode_changed("beginner")
    _APP.processEvents()
    ecart = (bord_droit(v._console.log)
             - bord_visible_case(v._serial_monitor._chk_autoscroll))
    # ZERO, pas « a peu pres ». Un premier correctif laissait 6 px -- l'espaceur
    # qui PRECEDE le libelle « Baud » masque, un espaceur n'etant pas un widget
    # il ne se masque pas avec lui. L'utilisateur l'a vu (QA AM3, 2e passe) :
    # « presque, mais le bord droit de la checkbox n'est pas aligne ». La
    # disposition se recalcule desormais depuis l'ETAT, et l'espaceur n'est
    # ajoute que si le groupe baud est visible.
    assert ecart == 0, (
        f"le carre de « Defilement auto » n'est pas aligne au bord droit du "
        f"journal : {ecart} px (mesures successives : 399 px, puis 6 px, puis "
        f"8 px de plus invisibles a la geometrie du widget)")


def test_the_compact_layout_is_undone_not_just_flagged():
    """La cause, enoncee -- sinon on ne verrait que son symptome.

    `set_compact(True)` reconstruit la ligne de controles ; `set_compact(False)`
    doit la RECONSTRUIRE aussi, pas se contenter de baisser un drapeau. On
    verifie l'ORDRE reel des widgets, pas le drapeau.
    """
    v = _vue()
    m = v._serial_monitor

    def ordre():
        lay = m.get_ctrl_widget().layout()
        out = []
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            out.append(type(w).__name__ if w is not None else "-")
        return out

    m.set_baud_visible(True)   # sinon les deux dispositions se ressemblent
    m.set_compact(True)
    compact = ordre()
    m.set_compact(False)
    normal = ordre()
    assert compact != normal, (
        "set_compact(False) n'a pas restaure la disposition : l'ordre compact "
        "survit, et son ressort final centre les controles")
    # En normal, la case d'auto-scroll est suivie du groupe baud (donc pas
    # d'un ressort qui la pousserait au centre).
    assert normal[-1] == "QComboBox", normal


TESTS = [
    test_the_three_modes_share_one_console,
    test_the_console_travels_to_the_right_container,
    test_the_outfit_changes_without_changing_the_object,
    test_changing_mode_never_closes_the_port,
    test_the_shared_journal_survives_a_mode_change,
    test_the_status_line_appears_once_and_only_once,
    test_the_reason_behind_close_port_survives,
    test_the_baud_label_follows_its_selector,
    test_loading_a_project_writes_ONE_status_line,
    test_the_autoscroll_sits_flush_right_in_beginner,
    test_the_compact_layout_is_undone_not_just_flagged,
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
