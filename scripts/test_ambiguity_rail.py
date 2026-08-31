"""Le rail des decisions de la modale d'ambiguite (TODO #73).

Avant ce rail, les sections etaient empilees dans UN defileur : a trois
broches ambigues les deux tiers du contenu etaient hors ecran, et rien nulle
part ne disait combien de decisions attendaient -- il fallait faire defiler
pour le decouvrir. Ces tests verrouillent les deux promesses du remplacement :

1. **on voit ce qui reste** : une ligne de rail par decision, un compte, et un
   etat par ligne qui distingue ce que le DETECTEUR propose de ce que
   l'UTILISATEUR a confirme ;
2. **le retour en arriere vit la ou les broches sont apparues** : degrouper un
   moteur pose ses broches en sous-lignes SOUS lui, avec le bouton qui les y
   regroupe -- l'annulation existait deja, mais dans la section restee tout en
   haut, a deux ecrans des broches qu'elle venait de faire apparaitre.

⚠️ Le test le plus important de ce fichier n'est aucun des deux : c'est
`test_every_section_is_built_even_when_only_one_is_visible`. La pile ne montre
qu'une page a la fois, mais toutes les sections doivent rester CONSTRUITES --
c'est ce qui remplit `_pickers` et, par la pre-selection, `_chosen_type`. Une
construction paresseuse rendrait « Valider » definitivement gris, sans que rien
a l'ecran ne dise pourquoi.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# QApplication conservee au niveau module : sans reference gardee, l'app
# temporaire est GC-ee et construire un QWidget ensuite crashe le process
# (0xC0000409) sous Windows.
from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

from PyQt6.QtGui import QCursor  # noqa: E402
from PyQt6.QtWidgets import QDialogButtonBox  # noqa: E402

import ui.declared_components as declared_components  # noqa: E402

# La bibliotheque declaree vient de la MEMOIRE : un test ne lit jamais le
# ~/Documents/Promptuino de la machine.
declared_components.set_registry([])
# Offscreen, `QCursor.pos()` est fige a (10,10) et force le :hover sur tout
# widget proche de l'origine (piege memorise le 2026-08-11).
QCursor.setPos(2000, 2000)

_VIVANTS: list = []


# ── fabriques ─────────────────────────────────────────────────────────────

def _led(ref: str, net: str, **attrs):
    from ui.wiring.netlist import Component, Pin
    base = {"category": "single_output", "_confidence": "low"}
    base.update(attrs)
    return Component(ref=ref, type="led",
                     pins=[Pin("A", net), Pin("K", "GND")], attributes=base)


def _dialog(comps, **kw):
    from ui.wiring.netlist import Netlist
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    nl = Netlist(board_id="", components=list(comps))
    dlg = AmbiguityDialog(list(comps), netlist=nl, **kw)
    _VIVANTS.append(dlg)
    return dlg


def _deux_moteurs_et_deux_broches():
    """Le scenario du ticket : le detecteur a groupe 2 moteurs supposes et
    laisse 2 sorties nues. Six decisions une fois un moteur degroupe."""
    return [
        _led("M1", "D3", _grouped_pwm_pin="D3", _grouped_dir_pins=["D4", "D5"]),
        _led("M2", "D9", _grouped_pwm_pin="D9",
             _grouped_dir_pins=["D10", "D11"]),
        _led("L1", "D6"),
        _led("L2", "D7"),
    ]


def _clic_card(dlg, ref: str, type_id: str):
    """Clique une card comme l'utilisateur, par le chemin REEL.

    Passer par `_on_type_toggled` + `_on_user_picked` a la main testerait mon
    cablage plutot que le sien : c'est precisement ce qui avait laisse passer
    le defaut de la card DEJA selectionnee, ou aucun de ces deux appels ne se
    produit.
    """
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    card = dlg._pickers[ref].card_for(type_id)
    assert card is not None, f"pas de card {type_id} pour {ref}"
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5),
                     QPointF(5, 5), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(card, ev)


def _ok(dlg):
    """Le bouton « Valider » COURANT.

    ⚠️ Ne jamais garder une reference : `_build()` recree le
    `QDialogButtonBox`, donc toute variable capturee avant une reconstruction
    (cocher un moteur en declenche une) pointe sur un widget orphelin dont
    l'etat ne veut plus rien dire. Piege paye a l'ecriture de ces tests.
    """
    return dlg._buttons.button(QDialogButtonBox.StandardButton.Ok)


def _titres(dlg):
    return [r._lbl_title.text() for r in dlg._rail_rows]


def _valeurs(dlg):
    return [r._lbl_value.text() for r in dlg._rail_rows]


# ── 1. ce que le rail montre ──────────────────────────────────────────────

def test_one_rail_row_per_decision_and_one_page_per_row():
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    # 1 section consolidee « 2 moteurs » + 2 broches nues.
    assert dlg._stack.count() == 3, dlg._stack.count()
    assert len(dlg._rail_rows) == 3, len(dlg._rail_rows)
    assert len(dlg._entries) == 3
    titres = _titres(dlg)
    assert "2" in titres[0], titres
    assert "6" in titres[1] and "7" in titres[2], titres


def test_the_rail_says_how_many_decisions_remain():
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    # C'est LE manque du ticket : le compte n'existait nulle part.
    assert "3" in dlg._rail_title.text(), dlg._rail_title.text()
    assert "3" in dlg._rail_sub.text(), dlg._rail_sub.text()
    ref = dlg._entries[1]["component"].ref
    dlg._pickers[ref].select("buzzer")
    dlg._on_type_toggled(ref, "buzzer")
    dlg._on_user_picked(ref)
    assert "2" in dlg._rail_sub.text(), dlg._rail_sub.text()


def test_nothing_is_preselected_when_the_detector_is_unsure():
    """Retour utilisateur du 2026-08-29 : ne pas pre-selectionner la LED.

    `_confidence == "low"` veut dire que `c.type` est un DEFAUT -- toute
    sortie numerique nue sort en « led » --, pas une deduction. Cocher cette
    card ferait passer une ignorance pour une reponse.
    """
    from ui.wiring.visual_ambiguity_catalog import dialog_label
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    attente = dialog_label("rail_undecided", "fr")
    propose = dialog_label("rail_proposed", "fr").split("{")[0].strip()

    for i in (1, 2):                       # les deux broches nues
        ref = dlg._entries[i]["component"].ref
        assert dlg._pickers[ref].current_type_id() is None, ref
        assert ref not in dlg._chosen_type, ref
        assert _valeurs(dlg)[i] == attente, _valeurs(dlg)[i]
    assert not any(r.is_done() for r in dlg._rail_rows)

    # La ligne des MOTEURS, elle, a bien une valeur a proposer : le detecteur
    # a groupe des broches, ce n'est pas un defaut.
    assert propose in _valeurs(dlg)[0], _valeurs(dlg)[0]

    _clic_card(dlg, dlg._entries[1]["component"].ref, "relay")
    assert dlg._rail_rows[1].is_done()
    assert attente not in _valeurs(dlg)[1], _valeurs(dlg)[1]


def test_a_confidently_detected_component_keeps_its_type():
    """L'engrenage ouvert sur un composant LU DANS LE CODE : la retenue
    ci-dessus ne s'applique pas -- son type est une information."""
    comp = _led("K1", "D8")
    comp.type = "relay"
    comp.attributes["_confidence"] = "high"
    dlg = _dialog([comp])
    assert dlg._pickers["K1"].current_type_id() == "relay"
    assert dlg._chosen_type.get("K1") == "relay"


def test_picking_a_card_moves_to_the_next_unconfirmed_decision():
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    dlg._select_decision(1)
    assert dlg._stack.currentIndex() == 1
    ref = dlg._entries[1]["component"].ref
    dlg._pickers[ref].select("buzzer")
    dlg._on_type_toggled(ref, "buzzer")
    dlg._on_user_picked(ref)
    assert dlg._stack.currentIndex() == 2, dlg._stack.currentIndex()
    # ... et l'avance ne fait PAS le tour : sur la derniere, on ne repart pas
    # au debut, ce qui arracherait l'utilisateur a l'endroit ou il travaille.
    ref2 = dlg._entries[2]["component"].ref
    dlg._pickers[ref2].select("relay")
    dlg._on_type_toggled(ref2, "relay")
    dlg._on_user_picked(ref2)
    assert dlg._stack.currentIndex() == 2, dlg._stack.currentIndex()


def test_clicking_a_rail_row_shows_that_decision():
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    dlg._rail_rows[2].click()
    assert dlg._stack.currentIndex() == 2
    assert dlg._rail_rows[2].is_active()
    assert not dlg._rail_rows[0].is_active()


def test_a_placeholder_rail_line_shows_the_component_name():
    """Releve en QA le 2026-08-29 : un placeholder a nets VIDES donnait une
    ligne de rail au titre vide -- « Broche  », illisible.

    `_section_net` ne peut rien rendre d'utile sur un composant dont aucune
    broche n'est cablee ; c'est le NOM du composant qui porte l'information.
    """
    from ui.wiring.netlist import Component, Pin
    ph = Component(ref="U9", type="l298n", fn_id="fn-1",
                   pins=[Pin("1", ""), Pin("2", "")],
                   attributes={"unrecognized": True, "header": "L298N.h"})
    dlg = _dialog([ph, _led("L1", "D6")])
    titre = dlg._rail_rows[0]._lbl_title.text().strip()
    assert titre not in ("", "Broche", "Broche ?"), repr(titre)
    assert "298" in titre or "driver" in titre.lower(), titre


def test_a_wired_component_still_shows_its_pin():
    """Contre-epreuve : le titre reste la BROCHE des qu'il y en a une -- c'est
    elle qui situe la decision dans le schema."""
    dlg = _dialog([_led("L1", "D6"), _led("L2", "D7")])
    assert "6" in dlg._rail_rows[0]._lbl_title.text(),         dlg._rail_rows[0]._lbl_title.text()


def test_a_single_decision_still_gets_a_rail():
    """⚠️ CONTRAT INVERSE LE 2026-08-29 (QA X4).

    Le rail etait masque quand il n'y avait qu'une decision -- une ligne
    n'apprend rien et coute 244 px au picker. Mais la modale changeait alors
    de FORME selon la porte : l'engrenage (« Modifier ce composant... »)
    n'ouvre qu'un composant et donnait une fenetre sans rien de commun avec
    celle de la generation. Une seule mise en page, quelle que soit la porte.
    """
    dlg = _dialog([_led("Z1", "D8")])
    assert dlg._rail_host is not None, "le rail doit rester, meme a 1 ligne"
    assert dlg._stack.count() == 1
    assert len(dlg._rail_rows) == 1
    assert "1" in dlg._rail_title.text(), dlg._rail_title.text()


def test_the_rail_does_not_tick_a_motor_whose_driver_is_missing():
    """QA X4, 2026-08-29 : le rail affichait ✓ sur « N moteurs DC » des que
    l'utilisateur touchait une case, alors que le PILOTE pouvait manquer.
    « Valider » restait gris pendant que le rail annoncait tout regle, et rien
    a l'ecran ne disait ou etait le manque.
    """
    dlg = _dialog(_deux_moteurs_et_deux_broches())     # aucun driver suggere
    dlg._toggle_motor_grouping("D9", keep=True)        # l'utilisateur touche
    assert dlg._motors_decided, "le geste a bien ete enregistre"
    assert not dlg._rail_rows[0].is_done(),         "pas de ✓ tant que le pilote manque"
    assert not _ok(dlg).isEnabled()

    # Le pilote choisi, la ligne peut passer au vert.
    for c in dlg._ambiguous:
        if c.attributes.get("_grouped_pwm_pin"):
            dlg._on_driver_toggled(c.ref, "l298n")
    dlg._refresh_rail()
    assert dlg._rail_rows[0].is_done(), "pilote choisi : la ligne est reglee"


def test_choosing_the_driver_ticks_the_motor_line_immediately():
    """QA X4, 2026-08-29 (2e passe) : le pilote choisi, « Valider » s'activait
    mais le rail ne bougeait pas.

    Les deux gestionnaires de pilote appelaient `_update_ok_state()` et JAMAIS
    `_refresh_rail()` -- et choisir un pilote ne comptait pour aucune
    decision. Le geste appartient pourtant a la ligne « moteurs ».
    """
    dlg = _dialog(_deux_moteurs_et_deux_broches())      # aucun pilote suggere
    assert not dlg._rail_rows[0].is_done()
    assert not dlg._motors_decided

    # Le chemin REEL : la card du pilote partage de la section consolidee.
    refs = [c.ref for c in dlg._ambiguous
            if c.attributes.get("_grouped_pwm_pin")]
    dlg._on_shared_driver_toggled(refs, "l298n")

    assert dlg._motors_decided, "choisir un pilote EST une decision"
    assert dlg._rail_rows[0].is_done(),         "le rail doit se mettre a jour tout de suite"
    # « Valider » reste gris a juste titre : les deux broches nues de ce
    # montage n'ont toujours pas de reponse. C'est la ligne des MOTEURS qui
    # est reglee, pas la modale entiere.
    assert not _ok(dlg).isEnabled()
    assert not dlg._rail_rows[1].is_done()


def test_the_solo_driver_also_refreshes_the_rail():
    """Meme trou sur le sous-menu d'UNE broche requalifiee en moteur DC."""
    dlg = _dialog([_led("Z1", "D8"), _led("Z2", "D9")])
    _clic_card(dlg, "Z1", "dc_motor")
    assert not dlg._rail_rows[0].is_done(), "pilote encore inconnu"
    dlg._on_driver_toggled("Z1", "drv8833")
    assert dlg._rail_rows[0].is_done(), "le rail doit suivre"


def test_all_ticks_implies_validate_is_active():
    """La garde de fond : un ✓ partout DOIT vouloir dire « Valider » actif.

    ⚠️ C'est une IMPLICATION, pas une equivalence, et l'asymetrie est voulue.
    Le sens interdit est celui que la QA X4 a trouve : le rail annoncait tout
    regle pendant que « Valider » restait gris, sans que rien ne dise ou etait
    le manque. Le sens inverse -- « Valider » actif sans que tout soit coche --
    est LEGITIME : quand le prompt a suggere le pilote, la proposition est
    applicable telle quelle, et le rail dit honnetement « propose : ... » en
    attendant que l'utilisateur la confirme ou la change.

    Les deux repondaient a cette question par deux chemins differents ; ils
    partagent desormais `_is_complete`.
    """
    dlg = _dialog(_deux_moteurs_et_deux_broches(),
                  suggested_dc_driver="l298n")
    dlg._toggle_motor_grouping("D9", keep=True)
    for i in (1, 2):
        _clic_card(dlg, dlg._entries[i]["component"].ref, "relay")
    tout_coche = all(r.is_done() for r in dlg._rail_rows)
    assert tout_coche, "tout est repondu"
    assert _ok(dlg).isEnabled(), "tout coche mais Valider gris : le rail ment"

    # Et le sens interdit, teste par mutation du reel : on retire le pilote,
    # la ligne des moteurs DOIT perdre son ✓ en meme temps que Valider.
    dlg._chosen_driver.clear()
    dlg._refresh_rail()
    dlg._update_ok_state()
    assert not dlg._rail_rows[0].is_done(), "✓ sur une decision incomplete"
    assert not _ok(dlg).isEnabled()


# ── 2. l'invariant que la pile ne doit pas casser ────────────────────────

def test_every_section_is_built_even_when_only_one_is_visible():
    """Le test qui garde le reste honnete.

    La pile ne montre qu'une page a la fois, mais `_update_ok_state` interroge
    le picker de CHAQUE composant : ne construire que la page courante le
    priverait de tout ce qui n'a pas encore ete affiche, et « Valider »
    deviendrait actif au-dessus de questions jamais posees.
    """
    comps = _deux_moteurs_et_deux_broches()
    dlg = _dialog(comps)
    for c in comps:
        if c.attributes.get("_grouped_pwm_pin"):
            continue          # les moteurs groupes n'ont pas de picker
        assert c.ref in dlg._pickers, f"{c.ref} sans picker"


def test_validate_stays_grey_until_every_pin_is_answered():
    """Consequence directe de la suppression de la pre-selection, et c'est le
    sens meme d'une modale d'ambiguite : on ne valide pas des questions
    auxquelles personne n'a repondu."""
    dlg = _dialog(_deux_moteurs_et_deux_broches(),
                  suggested_dc_driver="l298n")
    assert not _ok(dlg).isEnabled(), "rien n'est choisi, Valider doit etre gris"

    for i in (1, 2):
        _clic_card(dlg, dlg._entries[i]["component"].ref, "relay")
    assert _ok(dlg).isEnabled(), "tout est repondu, Valider doit s'activer"

    # Regle Q9 : une recherche qui masque le choix rend NON validable, meme
    # sur une page qui n'est pas affichee.
    ref = dlg._entries[2]["component"].ref
    dlg._pickers[ref].set_query("zzzzzz")
    dlg._update_ok_state()
    assert not _ok(dlg).isEnabled(), "un picker vide, meme cache, doit gater"


# ── 3. degrouper, puis revenir en arriere ────────────────────────────────

def test_ungrouping_a_motor_puts_its_pins_under_it_in_the_rail():
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    dlg._toggle_motor_declared("D9", is_motor=False)
    assert dlg._stack.count() == 6, dlg._stack.count()
    sous = [e["sub_of"] for e in dlg._entries]
    assert sous == [None, "D9", "D9", "D9", None, None], sous
    # Les trois broches liberees sont indentees, les autres non.
    assert dlg._rail_rows[1].layout().contentsMargins().left() > \
        dlg._rail_rows[4].layout().contentsMargins().left()


def test_the_regroup_button_sits_with_the_freed_pins():
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    assert dlg._regroup_buttons == []
    dlg._toggle_motor_declared("D9", is_motor=False)
    assert len(dlg._regroup_buttons) == 1, dlg._regroup_buttons
    # Il vit dans le RAIL, pas dans la section consolidee restee en haut.
    assert dlg._regroup_buttons[0].parent() is not None
    assert dlg._rail_host.isAncestorOf(dlg._regroup_buttons[0])


def test_the_regroup_button_undoes_the_ungrouping():
    """Le scenario mot pour mot du ticket : un moteur oui, l'autre non, on
    choisit des composants pour les 3 broches, puis on veut regrouper."""
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    dlg._toggle_motor_declared("D9", is_motor=False)
    for e in dlg._entries:
        if e["sub_of"] != "D9":
            continue
        ref = e["component"].ref
        dlg._pickers[ref].select("relay")
        dlg._on_type_toggled(ref, "relay")
        dlg._on_user_picked(ref)
    assert dlg._stack.count() == 6

    dlg._regroup_buttons[0].click()
    assert dlg._stack.count() == 3, dlg._stack.count()
    assert [e["sub_of"] for e in dlg._entries] == [None, None, None]
    assert dlg._regroup_buttons == []


def test_regrouping_restores_the_wiring_not_just_the_nature():
    """Decocher « c'est un moteur » retirait la broche de
    `_currently_kept_pwms` et rien ne l'y remettait : le moteur revenait
    reconnu mais silencieusement ABSENT du schema. Annuler doit tout rendre."""
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    assert "D9" in dlg._currently_kept_pwms
    dlg._toggle_motor_declared("D9", is_motor=False)
    assert "D9" not in dlg._currently_kept_pwms
    dlg._toggle_motor_declared("D9", is_motor=True)
    assert "D9" in dlg._currently_kept_pwms, sorted(dlg._currently_kept_pwms)


def test_a_lone_motor_can_also_be_regrouped():
    """Un moteur UNIQUE n'a pas de section consolidee : une fois degroupe,
    sa section disparaissait et il n'existait AUCUN chemin de retour."""
    comps = [
        _led("M1", "D3", _grouped_pwm_pin="D3", _grouped_dir_pins=["D4", "D5"]),
        _led("L1", "D6"),
    ]
    dlg = _dialog(comps)
    dlg._toggle_motor_declared("D3", is_motor=False)
    assert len(dlg._regroup_buttons) == 1, dlg._regroup_buttons
    dlg._regroup_buttons[0].click()
    assert any(c.attributes.get("_grouped_pwm_pin") == "D3"
               for c in dlg._ambiguous)


def test_an_erased_choice_is_no_longer_shown_as_confirmed():
    """`_decided` suit `_chosen_type` : regrouper efface le choix pose sur
    les broches liberees, le rail ne doit plus les dire confirmees."""
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    dlg._toggle_motor_declared("D9", is_motor=False)
    refs = [e["component"].ref for e in dlg._entries if e["sub_of"] == "D9"]
    for ref in refs:
        dlg._pickers[ref].select("relay")
        dlg._on_type_toggled(ref, "relay")
        dlg._on_user_picked(ref)
    assert all(r in dlg._decided for r in refs)
    dlg._toggle_motor_declared("D9", is_motor=True)
    assert not (set(refs) & dlg._decided), sorted(set(refs) & dlg._decided)


def test_a_rebuild_keeps_the_user_on_the_same_decision():
    """La decision courante est retenue par CLE : une reconstruction change
    la longueur de la liste, un index survivrait en pointant ailleurs."""
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    dlg._select_decision(2)                     # « Broche numerique 7 »
    cle = dlg._current_key
    dlg._toggle_motor_declared("D9", is_motor=False)   # +3 lignes AVANT elle
    assert dlg._current_key == cle, (dlg._current_key, cle)
    courant = dlg._entries[dlg._stack.currentIndex()]
    assert dlg._entry_key(courant) == cle


def test_clicking_an_already_chosen_card_still_counts_as_a_gesture():
    """`card_clicked` dit le CLIC, `type_chosen` dit le CHANGEMENT.

    Depuis la suppression de la pre-selection, un premier clic change toujours
    quelque chose -- mais RE-cliquer la card deja choisie n'emet aucun
    `type_chosen`, et ce geste doit rester un geste. C'est aussi ce qui fait
    marcher le chemin de l'engrenage, ou le composant arrive pre-selectionne
    sur son type lu dans le code.
    """
    comp = _led("K1", "D8")
    comp.type = "relay"
    comp.attributes["_confidence"] = "high"
    dlg = _dialog([comp])
    assert dlg._pickers["K1"].current_type_id() == "relay"
    assert "K1" not in dlg._decided

    _clic_card(dlg, "K1", "relay")       # on clique CE QUI EST DEJA choisi

    assert "K1" in dlg._decided, "un clic est un clic"


def test_clicking_another_card_still_changes_the_choice():
    """Le garde-fou du correctif precedent : ajouter un signal de CLIC ne doit
    pas casser le chemin normal, ou le choix change vraiment."""
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    dlg._select_decision(1)
    ref = dlg._entries[1]["component"].ref
    _clic_card(dlg, ref, "relay")
    assert dlg._chosen_type[ref] == "relay", dlg._chosen_type.get(ref)
    assert dlg._rail_rows[1].is_done()
    assert "relais" in dlg._rail_rows[1]._lbl_value.text().lower()


def test_previous_choices_come_back_in_the_modal():
    """« Modifier mes choix » rejoue TOUTES les ambiguites sans appliquer les
    resolutions sauvegardees -- c'est voulu. Mais la modale rouvrait sur les
    valeurs par defaut et l'utilisateur PERDAIT ce qu'il avait deja tranche
    (retour utilisateur, 2026-08-29)."""
    dlg = _dialog(_deux_moteurs_et_deux_broches(),
                  initial_choices={"L1": "relay", "L2": "buzzer"})
    assert dlg._pickers["L1"].current_type_id() == "relay"
    assert dlg._pickers["L2"].current_type_id() == "buzzer"
    # Il a vraiment choisi : le rail ne le lui redemande pas.
    assert dlg._rail_rows[1].is_done() and dlg._rail_rows[2].is_done()
    assert "relais" in _valeurs(dlg)[1].lower(), _valeurs(dlg)[1]


def test_a_restored_motor_choice_ticks_the_motor_line():
    """QA, 2026-08-29 : a la reouverture de « Modifier les choix », la ligne
    « N moteurs DC » restait grise alors que tout etait deja choisi -- il
    fallait RE-cliquer le pilote deja selectionne pour la faire passer au
    vert.

    Deux causes, l'une derriere l'autre : un moteur groupe n'a pas de ligne a
    lui (il vit dans la section consolidee, qui lit `_motors_decided`), donc
    le marquer dans `_decided` ne servait a rien ; et `_motors_decided` etait
    initialise APRES la restitution, ecrasant ce qu'elle venait de poser.
    """
    comps = _deux_moteurs_et_deux_broches()
    dlg = _dialog(comps,
                  initial_choices={"M1": "dc_motor", "M2": "dc_motor",
                                   "L1": "relay", "L2": "buzzer"},
                  suggested_dc_driver="l298n")
    assert dlg._motors_decided, "un moteur restitue n'a pas ete marque"
    assert all(r.is_done() for r in dlg._rail_rows),         [(r._lbl_title.text(), r.is_done()) for r in dlg._rail_rows]
    assert _ok(dlg).isEnabled()
    # Et le rail ne dit pas « propose » sur ce qui a deja ete tranche.
    from ui.wiring.visual_ambiguity_catalog import dialog_label
    marque = dialog_label("rail_proposed", "fr").split("{")[0].strip()
    assert not any(marque in v for v in _valeurs(dlg)), _valeurs(dlg)


def test_a_real_choice_beats_a_prompt_suggestion():
    """Precedence : ce que l'utilisateur a tranche prime sur une deduction."""
    comps = _deux_moteurs_et_deux_broches()
    comps[2].attributes["_prompt_suggested_type"] = "buzzer"
    dlg = _dialog(comps, initial_choices={"L1": "relay"})
    assert dlg._chosen_type["L1"] == "relay", dlg._chosen_type["L1"]


# ── 4. le clavier, et le piege maison de la touche Entree ────────────────

def test_no_rail_widget_is_autodefault():
    """Sans ca, Entree dans la recherche du picker remonte au premier bouton
    autoDefault de la fenetre -- qui serait une ligne de rail, donc un saut de
    page au lieu d'une validation (`test_dialog_enter_key.py`)."""
    dlg = _dialog(_deux_moteurs_et_deux_broches())
    dlg._toggle_motor_declared("D9", is_motor=False)
    for w in list(dlg._rail_rows) + list(dlg._regroup_buttons):
        assert not w.autoDefault(), w
        assert not w.isDefault(), w


TESTS = [
    test_one_rail_row_per_decision_and_one_page_per_row,
    test_the_rail_says_how_many_decisions_remain,
    test_nothing_is_preselected_when_the_detector_is_unsure,
    test_a_confidently_detected_component_keeps_its_type,
    test_picking_a_card_moves_to_the_next_unconfirmed_decision,
    test_clicking_a_rail_row_shows_that_decision,
    test_a_placeholder_rail_line_shows_the_component_name,
    test_a_wired_component_still_shows_its_pin,
    test_a_single_decision_still_gets_a_rail,
    test_the_rail_does_not_tick_a_motor_whose_driver_is_missing,
    test_choosing_the_driver_ticks_the_motor_line_immediately,
    test_the_solo_driver_also_refreshes_the_rail,
    test_all_ticks_implies_validate_is_active,
    test_every_section_is_built_even_when_only_one_is_visible,
    test_validate_stays_grey_until_every_pin_is_answered,
    test_ungrouping_a_motor_puts_its_pins_under_it_in_the_rail,
    test_the_regroup_button_sits_with_the_freed_pins,
    test_the_regroup_button_undoes_the_ungrouping,
    test_regrouping_restores_the_wiring_not_just_the_nature,
    test_a_lone_motor_can_also_be_regrouped,
    test_an_erased_choice_is_no_longer_shown_as_confirmed,
    test_a_rebuild_keeps_the_user_on_the_same_decision,
    test_clicking_an_already_chosen_card_still_counts_as_a_gesture,
    test_previous_choices_come_back_in_the_modal,
    test_a_restored_motor_choice_ticks_the_motor_line,
    test_a_real_choice_beats_a_prompt_suggestion,
    test_clicking_another_card_still_changes_the_choice,
    test_no_rail_widget_is_autodefault,
]


def main():
    passed = 0
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    # Sous Windows + Qt offscreen, detruire plusieurs AmbiguityDialog pendant
    # le teardown Qt statique crashe le process (0xC0000409) APRES que les
    # assertions ont deja tranche. On sort par os._exit pour que le code de
    # retour reflete les assertions, pas le crash de teardown.
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
