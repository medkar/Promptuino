"""Confrontation des broches declarees au code (TODO #45, 2026-08-27).

Le mal d'origine : la fiche declaree remplace le placeholder et DETRUIT la
seule preuve de ce que le code fait (`constructor_pins`, vide par
SAFETY_NET_ATTRS) au moment precis ou l'utilisateur gagne le droit de la
contredire. La declaration se rejouant par en-tete a chaque ouverture, une
divergence survivait a toutes les regenerations sans jamais etre dite.

Le correctif ne stocke RIEN : markers recalcule la preuve a chaque analyse,
et `apply_library_to_netlist` la lit juste avant de l'ecraser. Une divergence
apparait quand elle nait et disparait quand elle se repare.

Tache 2 du meme ticket : la fiche est aussi confrontee au SCHEMA -- un net de
signal qu'elle cable et qu'un AUTRE composant porte deja
(`declared_pin_already_claimed`). Le principe qui gouverne ses exclusions est
le meme que celui de la divergence : on ne signale que ce qu'on SAIT etre une
collision (les rails, les nets a alias I2C et les labels de bus partage sont
des partages legitimes, donc du silence).

Run : python scripts/test_declared_pin_divergence.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level

import ui.declared_components as dc
from ui.declared_components import DeclaredComponent, DeclaredPin
from ui.wiring.declared_apply import apply_library_to_netlist
from ui.wiring.markers import extract_netlist
from ui.wiring.layout.pipeline import analyze_netlist
from ui.wiring.netlist import SEVERITY_WARNING
from ui.wiring.wiring_diagram_dialog import _t

# Sketch PROUVE par test_wiring_unknown_component.py : le filet produit un
# placeholder `unrecognized` avec constructor_pins == ["D5", "D6"].
_CODE_CTOR = ("#include <LibInconnue.h>\n"
              "LibInconnue capteur(5, 6);\n"
              "void setup(){}\n"
              "void loop(){}\n")

# Un constructeur dont les arguments ne sont PAS des broches (colonnes x
# lignes d'un ecran). `_constructor_pins_for` retient quand meme le 2.
_CODE_LCD = ("#include <MonEcran.h>\n"
             "MonEcran lcd(16, 2);\n"
             "void setup(){}\n"
             "void loop(){}\n")

# Meme include, aucun constructeur a broches : preuve VIDE.
_CODE_NO_CTOR = ("#include <LibInconnue.h>\n"
                 "void setup(){}\n"
                 "void loop(){}\n")

# Tache 2 (collision) -- meme constructeur, PLUS une sortie digitale nue sur
# D7 : le detecteur en fait une LED, donc un AUTRE composant du schema porte
# deja le net D7. Verifie a l'execution : la netlist sort `D1 led
# [('A','D7'), ('K','GND')]` -- pas de resistance serie inseree ici, l'adverse
# nomme est donc bien la LED.
_CODE_CTOR_LED = ("#include <LibInconnue.h>\n"
                  "LibInconnue capteur(5, 6);\n"
                  "void setup(){ pinMode(7, OUTPUT); }\n"
                  "void loop(){ digitalWrite(7, HIGH); }\n")

# Meme constructeur, PLUS une lecture analogique nue sur A4 : le filet
# `presumed_analog` en fait un potentiometre presume, qui porte donc le net
# A4 -- lequel est AUSSI le SDA de la carte. Vraie collision de nets, et
# pourtant du silence : c'est le sujet de test_collision_net_i2c.
_CODE_CTOR_A4 = ("#include <LibInconnue.h>\n"
                 "LibInconnue capteur(5, 6);\n"
                 "void setup(){}\n"
                 "void loop(){ int v = analogRead(A4); }\n")


# Revue finale du #45 (2026-08-27) -- DEUX composants non reconnus, chacun
# avec sa fiche, toutes deux cablees sur D7 : divergence ET collision des deux
# cotes. Ce decor est ce qui fait naitre le `pin_double_use` PERIME que
# l'infobulle affichait : il est emis dans `analyze_netlist`, AVANT que la
# declaration ne s'applique, quand les deux placeholders ont encore quatre
# broches a net VIDE -- et `_is_signal_net("")` rend True, donc ils
# « partagent » le net vide.
_CODE_DEUX_INCONNUS = ("#include <LibA.h>\n"
                       "#include <LibB.h>\n"
                       "LibA a(5, 6);\n"
                       "LibB b(8, 9);\n"
                       "void setup(){}\n"
                       "void loop(){}\n")

# Un adverse detecte AVEC CERTITUDE (signature `Servo.h`) et qui ne porte
# AUCUN warning a lui. C'est le cas courant, et celui que la tache 2 ratait :
# test et QA prenaient tous deux une LED, qui porte deja `led_series_resistor`
# et masquait le defaut.
_CODE_SERVO_ADVERSE = ("#include <Servo.h>\n"
                       "#include <LibInconnue.h>\n"
                       "Servo monServo;\n"
                       "LibInconnue capteur(5, 6);\n"
                       "void setup(){ monServo.attach(9); }\n"
                       "void loop(){ monServo.write(90); }\n")


def _fiche(*pins, header="libinconnue.h"):
    """Fiche declaree pour LibInconnue.h, broches passees en (label, net).

    L'en-tete est stocke NORMALISE (minuscules, sans chemin) : les deux
    chemins d'ecriture reels le normalisent -- le formulaire
    (`declare_component_dialog`, via `normalize_header`) et la relecture du
    disque (`_from_dict`). `find_by_header` normalise sa REQUETE puis compare
    verbatim a `headers`, donc une fiche ecrite « LibInconnue.h » ne serait
    jamais retrouvee et TOUS les tests de silence ci-dessous passeraient sans
    rien prouver.
    """
    return DeclaredComponent(
        id="mon-capteur", name="Mon capteur", headers=(header,),
        pins=tuple(DeclaredPin(label=l, role="signal" if n.startswith(("D", "A"))
                               else ("gnd" if n == "GND" else "vcc"), net=n)
                   for l, n in pins),
        lib="", keywords=("Mon capteur",))


def _apply(code, fiche, opt_outs=None, extra=None):
    """Le decor reel : extraction puis application de la bibliotheque.

    `extra` : composant injecte dans la netlist ENTRE l'extraction et
    l'application. Indispensable pour les deux tests de bus partage (tache
    2) : aucun sketch simple ne fait produire au detecteur un composant dont
    une broche s'appelle SCK, et le warning de collision est emis PENDANT
    `apply_library_to_netlist` -- ajouter l'adverse apres coup ne prouverait
    rien du tout.
    """
    dc.set_registry([fiche])
    try:
        nl = extract_netlist(code, "arduino_uno_r3", prompt="branche mon capteur")
        if extra is not None:
            nl.components.append(extra)
        apply_library_to_netlist(nl, opt_outs=opt_outs or {})
        return nl
    finally:
        dc.set_registry([])


def _fiche_nommee(cid, name, header, *pins):
    """Comme `_fiche`, mais id / nom / en-tete choisis : le scenario a DEUX
    composants non reconnus a besoin de deux fiches distinctes."""
    return DeclaredComponent(
        id=cid, name=name, headers=(header,),
        pins=tuple(DeclaredPin(label=l, role="signal" if n.startswith(("D", "A"))
                               else ("gnd" if n == "GND" else "vcc"), net=n)
                   for l, n in pins),
        lib="", keywords=(name,))


def _analyze_and_apply(code, fiches, prompt="branche mon capteur"):
    """Le VRAI chemin : `analyze_netlist` puis `apply_library_to_netlist`.

    ⚠️ `_apply` ci-dessus passe par `extract_netlist` SEUL, et ce raccourci
    est precisement ce qui a cache le defaut d'infobulle pendant tout le
    chantier : `pin_double_use` nait dans `inference.detect_conflicts`,
    appele par `analyze_netlist` et par personne d'autre. Un test qui
    court-circuite la couche ou naissent les warnings concurrents ne peut pas
    voir lequel gagne.
    """
    dc.set_registry(list(fiches))
    try:
        nl = analyze_netlist(code, "arduino_uno_r3", prompt=prompt)
        apply_library_to_netlist(nl)
        return nl
    finally:
        dc.set_registry([])


def _display(nl):
    """(info_refs, info_tooltips) tels que le dialogue les calculerait.

    Le dialogue entier n'est pas requis : ces deux methodes ne lisent que
    `self._netlist` et deux constantes de classe.
    """
    from ui.wiring.wiring_diagram_dialog import WiringDiagramDialog as W

    class _Stub:
        _netlist = nl
        _INFO_TYPES = W._INFO_TYPES
        _CONFRONTATION_CODES = W._CONFRONTATION_CODES
        _compute_info_refs = W._compute_info_refs
        _compute_info_tooltips = W._compute_info_tooltips

    stub = _Stub()
    refs = stub._compute_info_refs()
    return refs, stub._compute_info_tooltips(refs)


def _warnings(nl, code):
    return [w for w in nl.warnings if w.code == code]


def test_divergence_franche_est_signalee():
    """Le code utilise D5/D6, la fiche cable D9/D10 : les DEUX broches
    prouvees manquent, et le warning les nomme toutes les deux."""
    nl = _apply(_CODE_CTOR, _fiche(("VCC", "5V"), ("GND", "GND"),
                                   ("TRIG", "D9"), ("ECHO", "D10")))
    ws = _warnings(nl, "declared_pins_diverge_from_code")
    assert len(ws) == 1, [w.code for w in nl.warnings]
    w = ws[0]
    assert w.severity == SEVERITY_WARNING
    assert w.params.get("pins") == "D5, D6", w.params
    assert w.params.get("name") == "Mon capteur", w.params


def test_accord_reste_silencieux():
    nl = _apply(_CODE_CTOR, _fiche(("VCC", "5V"), ("GND", "GND"),
                                   ("TRIG", "D5"), ("ECHO", "D6")))
    assert _warnings(nl, "declared_pins_diverge_from_code") == []


def test_preuve_vide_reste_silencieuse():
    """Pas de constructeur a broches -> pas de preuve -> pas de warning.
    C'est la regle « on confronte ce qu'on sait, on se tait sinon » qui rend
    la preuve partielle inoffensive."""
    nl = _apply(_CODE_NO_CTOR, _fiche(("VCC", "5V"), ("OUT", "D9")))
    assert _warnings(nl, "declared_pins_diverge_from_code") == []


def test_sous_ensemble_ne_signale_que_les_manquantes():
    nl = _apply(_CODE_CTOR, _fiche(("VCC", "5V"), ("TRIG", "D5")))
    ws = _warnings(nl, "declared_pins_diverge_from_code")
    assert len(ws) == 1
    assert ws[0].params.get("pins") == "D6", ws[0].params


def test_l_inverse_n_est_pas_signale():
    """La fiche cable D9 que le code ne montre pas : PAS signale — la preuve
    etant partielle, le code peut utiliser D9 par un chemin invisible.
    (Ici D5/D6 sont cables donc rien ne manque ; D9 en plus est tolere.)"""
    nl = _apply(_CODE_CTOR, _fiche(("TRIG", "D5"), ("ECHO", "D6"),
                                   ("EXTRA", "D9")))
    assert _warnings(nl, "declared_pins_diverge_from_code") == []


def test_auto_guerison_au_rejeu():
    """Fiche corrigee -> l'analyse suivante ne pose plus le warning. Rien
    n'est stocke : la netlist fraiche fait foi."""
    nl1 = _apply(_CODE_CTOR, _fiche(("TRIG", "D9"), ("ECHO", "D10")))
    assert _warnings(nl1, "declared_pins_diverge_from_code")
    nl2 = _apply(_CODE_CTOR, _fiche(("TRIG", "D5"), ("ECHO", "D6")))
    assert _warnings(nl2, "declared_pins_diverge_from_code") == []


def test_opt_out_vers_un_type_non_declare_ne_confronte_pas():
    """Resolu vers `led` (pas une declaration) : plus l'affaire de ce module,
    meme regle que declared_unconnected_pins."""
    from ui.declared_components import normalize_header
    nl = _apply(_CODE_CTOR, _fiche(("TRIG", "D9"), ("ECHO", "D10")),
                opt_outs={normalize_header("LibInconnue.h"): "led"})
    assert _warnings(nl, "declared_pins_diverge_from_code") == []


def test_la_contradiction_passe_avant_la_reassurance():
    """Une fiche a la fois incomplete ET divergente emet les DEUX codes, la
    divergence EN PREMIER.

    La chaine complete, en DEUX maillons poses par ce meme ticket :

    1. `_compute_info_refs` (wiring_diagram_dialog) ne donnait de pastille
       d'attention qu'aux composants portant un attribut de filet
       (`unrecognized`, `presumed_wiring`...). Or une declaration les VIDE :
       un composant declare n'avait donc AUCUNE pastille, pas meme quand
       l'app constate que sa fiche contredit le code. La clause
       `_CONFRONTATION_CODES` la lui donne, depuis le warning lui-meme.
       Mesure : `info_refs` passe de 0 a 1 ref sur ce scenario.
    2. une fois la ref porteuse d'une pastille, `_compute_info_tooltips` ne
       retenait que le PREMIER warning par ref -- d'ou l'ordre.

    ⚠️ CE SECOND MAILLON A CHANGE (revue finale, 2026-08-27) et ce test ne
    l'affirme plus. La regle « premier warning par ref » dependait de l'ordre
    d'emission de TOUTE la netlist, pas seulement du notre : `pin_double_use`
    est emis dans `analyze_netlist`, donc bien avant `declared_apply`, et
    gagnait a tous les coups (cf.
    test_deux_fiches_la_contradiction_bat_le_double_usage_perime). Les codes
    de confrontation passent desormais devant, au survol comme au clic, quelle
    que soit leur position dans la liste.

    L'ordre reste du COMPORTEMENT, pour deux raisons qui subsistent : les
    LIGNES du panneau d'instructions, ou une reassurance « tu as laisse ces
    broches non connectees, c'est voulu » placee avant un constat actionnable
    inverserait la lecture ; et le depart entre DEUX confrontations portant la
    meme ref, ou c'est encore la premiere qui prend l'infobulle.
    """
    nl = _apply(_CODE_CTOR, _fiche(("VCC", "5V"), ("TRIG", "D9"),
                                   ("LIBRE", "")))
    codes = [w.code for w in nl.warnings
             if w.code in ("declared_pins_diverge_from_code",
                           "declared_unconnected_pins")]
    assert codes == ["declared_pins_diverge_from_code",
                     "declared_unconnected_pins"], codes


def test_un_litteral_qui_n_est_pas_une_broche_declenche_quand_meme():
    """`MonEcran lcd(16, 2)` : 16 et 2 sont des COLONNES et des LIGNES, pas
    des broches -- et le warning sort quand meme, sur « D2 ».

    LIMITE ACCEPTEE, PAS UN BUG A CORRIGER EN DOUCE.
    `markers._constructor_pins_for` retient tout litteral 0..13 de n'importe
    quel argument (16 tombe, hors plage ; 2 devient D2), et `markers` assume
    l'approximation la ou il pose l'attribut : « indice utile SANS inventer
    de cablage ». Le durcir demanderait de DEVINER quel argument est une
    broche -- exactement l'invention de cablage que le filet refuse.

    Le prix est paye sur le MESSAGE, pas sur le declenchement : il rapporte
    le fait verifiable (« le code passe D2 au constructeur ») au lieu
    d'affirmer un usage (« le code utilise D2 », qui serait faux ici et
    permanent), et il offre la sortie « ignore si ce ne sont pas des
    broches ». Ce test fige le comportement pour qu'il se lise comme une
    decision, pas comme une surprise.
    """
    nl = _apply(_CODE_LCD, _fiche(("VCC", "5V"), ("GND", "GND"),
                                  header="monecran.h"))
    ws = _warnings(nl, "declared_pins_diverge_from_code")
    assert len(ws) == 1, [w.code for w in nl.warnings]
    assert ws[0].params.get("pins") == "D2", ws[0].params
    # Le message ne doit RIEN affirmer sur l'usage : c'est ce qui rend le
    # faux positif supportable plutot que mensonger.
    assert "utilise" not in ws[0].message, ws[0].message
    assert "constructeur" in ws[0].message, ws[0].message


def test_la_pastille_d_attention_est_atteignable_pour_une_fiche_declaree():
    """Le composant declare porte bien la pastille, et son infobulle dit la
    CONTRADICTION -- pas la reassurance.

    Sans ce test, le maillon 1 decrit dans
    test_la_contradiction_passe_avant_la_reassurance ne serait affirme que
    par des commentaires. Il l'a deja ete a tort : la 1re version de ce
    ticket justifiait l'ordre d'emission par une collision d'infobulle qui ne
    pouvait PAS se produire, `_compute_info_refs` n'accordant de pastille
    qu'aux porteurs d'un attribut de filet -- attributs que la declaration
    vide. Mesure d'alors : `info_refs` valait set(), l'utilisateur ne voyait
    RIEN. On verrouille donc le mecanisme, pas seulement son effet.
    """
    nl = _apply(_CODE_CTOR, _fiche(("VCC", "5V"), ("TRIG", "D9"),
                                   ("LIBRE", "")))
    refs, tips = _display(nl)
    assert refs == {"U1"}, refs
    tip = tips["U1"]
    assert "constructeur" in tip, tip
    assert "non connect" not in tip, tip     # la reassurance ne gagne pas


# ─── Tache 2 : collision avec un autre composant du schema ──────────────

def test_collision_signal_est_signalee():
    """La fiche cable D7, et le detecteur y a deja mis une LED. Deux choses
    visibles du schema se disputent le meme trou de la carte : on le dit.

    Le warning porte les DEUX refs (la fiche et l'adverse) : le lien vers
    l'adverse a sa valeur dans le panneau d'instructions.

    ⚠️ IL NE DONNE PAS DE PASTILLE A L'ADVERSE, contrairement a ce que cette
    docstring a affirme jusqu'a la revue finale (2026-08-27) : le message est
    ecrit du point de vue de la FICHE, donc seule la 1re ref le recoit. Cf.
    test_l_adverse_ne_recoit_pas_la_pastille_de_la_fiche -- et noter que ce
    test-ci ne l'aurait jamais montre, son adverse etant une LED, qui porte
    deja `led_series_resistor` et masquait tout.
    """
    nl = _apply(_CODE_CTOR_LED, _fiche(("TRIG", "D5"), ("ECHO", "D6"),
                                       ("OUT", "D7")))
    ws = _warnings(nl, "declared_pin_already_claimed")
    assert len(ws) == 1, [w.code for w in nl.warnings]
    w = ws[0]
    assert w.severity == SEVERITY_WARNING
    assert w.params.get("net") == "D7", w.params
    assert len(w.refs) == 2, w.refs


def test_collision_rail_reste_silencieuse():
    """GND est partage PAR NATURE : la LED y a sa cathode, la fiche sa masse,
    et c'est exactement ce qu'on attend d'un montage. Signaler serait crier a
    chaque schema."""
    nl = _apply(_CODE_CTOR_LED, _fiche(("TRIG", "D5"), ("ECHO", "D6"),
                                       ("GND", "GND")))
    assert _warnings(nl, "declared_pin_already_claimed") == []


def test_collision_net_i2c_reste_silencieuse():
    """A4 est aussi le SDA de la carte : plusieurs esclaves I2C s'y branchent
    legitimement. L'exclusion passe par le predicat `i2c_alias_for_net`, pas
    par une liste ecrite a la main -- sinon les deux fichiers derivent le jour
    ou une carte nomme ses broches autrement.

    La collision est REELLE ici (le filet `presumed_analog` pose un
    potentiometre presume sur A4, avec le label « W » qui n'est pas un label
    de bus) : sans l'exclusion, ce test rougit.
    """
    nl = _apply(_CODE_CTOR_A4, _fiche(("TRIG", "D5"), ("ECHO", "D6"),
                                      ("SIG", "A4")))
    assert _warnings(nl, "declared_pin_already_claimed") == []


def test_collision_label_bus_adverse_reste_silencieuse():
    """Le predicat est un OU : c'est le composant ADVERSE qui porte le label
    de bus, et ca suffit a se taire. Partager un SCK entre plusieurs esclaves
    SPI est le fonctionnement normal du bus.

    ⚠️ Le caillou du ticket est ici : D13 vaut `['digital', 'sck']` dans les
    CAPACITES de la broche Uno (`_BUS_CAPS`, ui/generation/pin_reassign.py).
    Une capacite est une POSSIBILITE, pas un usage -- et D13 est justement la
    broche de la LED integree que tout sketch debutant pilote. C'est donc le
    LABEL du composant qui doit trancher, jamais la capacite de la broche :
    ici l'adverse s'appelle « SCK », voila la preuve.
    """
    from ui.wiring.netlist import Component, Pin
    adverse = Component(ref="U9", type="spi_thing", pins=[Pin("SCK", "D13")])
    nl = _apply(_CODE_CTOR_LED, _fiche(("TRIG", "D5"), ("ECHO", "D6"),
                                       ("OUT", "D13")), extra=adverse)
    assert _warnings(nl, "declared_pin_already_claimed") == []


def test_collision_label_bus_cote_fiche_reste_silencieuse():
    """Miroir du precedent : c'est la FICHE qui declare un SCK, et l'adverse
    porte un label quelconque (la LED detectee, dont l'anode s'appelle « A »).

    Sans ce test, un predicat qui ne regarderait qu'un seul cote passerait
    pour correct -- le OU ne se verifie qu'en deux exemplaires.
    """
    nl = _apply(_CODE_CTOR_LED, _fiche(("TRIG", "D5"), ("ECHO", "D6"),
                                       ("SCK", "D7")))
    assert _warnings(nl, "declared_pin_already_claimed") == []


def test_le_gabarit_collision_est_traduit():
    from ui.wiring.instructions import _WARNING_TEMPLATES
    entry = _WARNING_TEMPLATES.get("declared_pin_already_claimed")
    assert entry, "gabarit absent de _WARNING_TEMPLATES"
    for lang in ("fr", "en", "es", "it"):
        assert entry.get(lang), lang
        for token in ("{name}", "{net}", "{ref}"):
            assert token in entry[lang], (lang, token)


def test_le_gabarit_est_traduit_dans_les_quatre_langues():
    from ui.wiring.instructions import _WARNING_TEMPLATES
    entry = _WARNING_TEMPLATES.get("declared_pins_diverge_from_code")
    assert entry, "gabarit absent de _WARNING_TEMPLATES"
    for lang in ("fr", "en", "es", "it"):
        assert entry.get(lang), lang
        assert "{pins}" in entry[lang] and "{name}" in entry[lang], lang


def test_les_deux_codes_ont_un_titre_de_constat():
    """Les titres existants nomment des DEVINETTES (« non reconnu »,
    « presume ») ; ces deux codes sont des CONSTATS. Le repli
    « Point d'attention » (code absent de la table) serait trop faible pour
    une contradiction constatee — la spec exige la cle dediee."""
    from ui.wiring.wiring_diagram_dialog import (_DIALOG_LABELS,
                                                 _INFO_TITLE_BY_CODE)
    for code in ("declared_pins_diverge_from_code",
                 "declared_pin_already_claimed"):
        assert _INFO_TITLE_BY_CODE.get(code) == "info_title_conflict", code
    entry = _DIALOG_LABELS.get("info_title_conflict")
    assert entry, "titre absent de _DIALOG_LABELS"
    for lang in ("fr", "en", "es", "it"):
        assert entry.get(lang), lang


# ─── Revue finale : la couche d'affichage de la pastille ────────────────
#
# Les deux defauts ci-dessous naissent de la COMPOSITION -- la clause
# `_CONFRONTATION_CODES` de la tache 1 rencontrant `_detect_pin_double_use`
# (anterieur, autre fichier) et le `refs=[fiche, adverse]` de la tache 2.
# Aucune revue par tache ne pouvait les voir.

def test_deux_fiches_la_contradiction_bat_le_double_usage_perime():
    """DEUX composants non reconnus : l'infobulle dit la CONTRADICTION, pas
    le `pin_double_use` calcule sur des nets VIDES.

    Mesure de la revue finale, AVANT correctif -- les deux memes lignes pour
    les deux composants :

        TIP U1 -> Point d'attention  Pin  utilisee par plusieurs composants :
                  U1, U1, U1, U1, U2, U2, U2, U2.

    Les QUATRE warnings du #45 etaient bien emis, AUCUN n'atteignait la
    pastille. `_detect_pin_double_use` tourne DANS `analyze_netlist`, donc
    avant que la declaration ne s'applique : les placeholders ont encore
    quatre broches a net vide, `_is_signal_net("")` rend True, deux
    placeholders « partagent » donc le net vide et produisent un
    `pin_double_use` de severite ERREUR. Ce code n'est pas dans
    `_OBSOLETE_CODES`, il survit a la declaration, et il est ANTERIEUR aux
    warnings de #45 dans la liste : la regle « premier warning par ref » le
    faisait gagner a tous les coups. La seule chose que le ticket ajoutait a
    l'ecran montrait, sur ses propres composants, un message faux et date --
    sous le titre « Point d'attention » que la spec ecarte explicitement.

    ⚠️ CE TEST DOIT PASSER PAR `analyze_netlist`. `extract_netlist` seul ne
    lance pas `detect_conflicts` : c'est ce raccourci qui a cache le defaut.
    """
    nl = _analyze_and_apply(
        _CODE_DEUX_INCONNUS,
        [_fiche_nommee("cap-a", "Capteur A", "liba.h",
                       ("VCC", "5V"), ("GND", "GND"), ("OUT", "D7")),
         _fiche_nommee("cap-b", "Capteur B", "libb.h",
                       ("VCC", "5V"), ("GND", "GND"), ("OUT", "D7"))],
        prompt="branche mes capteurs")

    # Le decor doit vraiment produire le concurrent, sinon ce test passerait
    # pour la mauvaise raison -- et il doit le produire AVANT les notres.
    codes = [w.code for w in nl.warnings]
    assert "pin_double_use" in codes, codes
    assert (codes.index("pin_double_use")
            < codes.index("declared_pins_diverge_from_code")), codes

    refs, tips = _display(nl)
    assert refs == {"U1", "U2"}, refs
    for ref in ("U1", "U2"):
        tip = tips[ref]
        assert "constructeur" in tip, (ref, tip)
        assert "plusieurs composants" not in tip, (ref, tip)


def test_le_clic_montre_la_meme_chose_que_le_survol():
    """`_show_warning_info` (le clic sur la pastille) portait EXACTEMENT le
    meme « premier warning par ref » que l'infobulle.

    Le corriger d'un seul cote aurait fait se contredire le survol et le clic
    sur le meme composant : mesure d'avant correctif, le clic ouvrait
    « Point d'attention / Pin  utilisee par plusieurs composants : U1, U1... »
    pendant que le survol disait deja la contradiction.
    """
    from PyQt6.QtWidgets import QMessageBox
    from ui.wiring.wiring_diagram_dialog import WiringDiagramDialog as W

    nl = _analyze_and_apply(
        _CODE_DEUX_INCONNUS,
        [_fiche_nommee("cap-a", "Capteur A", "liba.h",
                       ("VCC", "5V"), ("GND", "GND"), ("OUT", "D7")),
         _fiche_nommee("cap-b", "Capteur B", "libb.h",
                       ("VCC", "5V"), ("GND", "GND"), ("OUT", "D7"))],
        prompt="branche mes capteurs")

    class _Stub:
        _netlist = nl
        _CONFRONTATION_CODES = W._CONFRONTATION_CODES
        _show_warning_info = W._show_warning_info

    seen = []
    original = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: seen.append(a))
    try:
        _Stub()._show_warning_info("U1")
    finally:
        QMessageBox.information = original
    assert seen, "le clic n'a rien ouvert"
    title, body = seen[0][1], seen[0][2]
    assert "constructeur" in body, body
    assert "plusieurs composants" not in body, body
    assert title != _t("info_title_generic", "fr"), title


def test_l_adverse_ne_recoit_pas_la_pastille_de_la_fiche():
    """La collision donne une pastille a la FICHE, pas a l'adverse.

    Le servo est detecte par signature (`Servo.h`), donc AVEC CERTITUDE ; il
    n'avait aucune pastille avant ce chantier. La clause de la tache 1 prenant
    TOUTES les refs du warning, et `declared_pin_already_claimed` portant
    `refs=[ref_fiche, other_ref]`, il en gagnait une -- portant une phrase
    redigee du point de vue de la fiche, qui le nommait lui-meme comme le
    coupable. Mesure de la revue finale : `info_refs: ['SV1', 'U1']`, et
    survoler le servo affichait « La fiche « Mon capteur » cable D9, deja
    utilisee par un autre composant du schema (SV1) ».

    ⚠️ L'ADVERSE DOIT ETRE UN SERVO, PAS UNE LED. Le test et la QA de la tache
    2 prenaient tous deux une LED : elle porte deja `led_series_resistor`, qui
    gagnait le premier-warning-par-ref et masquait le probleme. Un adverse
    SANS warning anterieur -- servo, bouton, ecran -- est le cas COURANT.

    `refs` garde ses deux entrees : c'est la PASTILLE qui se restreint.
    """
    nl = _analyze_and_apply(
        _CODE_SERVO_ADVERSE,
        [_fiche(("TRIG", "D5"), ("ECHO", "D6"), ("OUT", "D9"))],
        prompt="branche mon capteur et un servo")

    ws = _warnings(nl, "declared_pin_already_claimed")
    assert len(ws) == 1, [w.code for w in nl.warnings]
    assert ws[0].refs == ["U1", "SV1"], ws[0].refs   # le lien reste entier

    # L'adverse est bien la, detecte avec certitude, et sans aucun warning a
    # lui : sans cette verification le test passerait pour la mauvaise raison.
    servo = next(c for c in nl.components if c.ref == "SV1")
    assert servo.type == "servo", servo.type
    assert not [w for w in nl.warnings
                if w.code != "declared_pin_already_claimed"
                and "SV1" in (w.refs or [])], [w.code for w in nl.warnings]

    refs, tips = _display(nl)
    assert refs == {"U1"}, refs
    assert "SV1" not in tips, sorted(tips)


def _modale_change_la_fiche(nl, nouvelle):
    """Ce que fait la modale : la fiche change, puis `apply_choices`
    re-applique le MEME type au meme composant (`apply_saved_resolution`).

    C'est le geste exact du crayon d'une card -- le seul moment ou la fiche
    bouge APRES que `apply_library_to_netlist` a rendu son verdict.
    """
    from ui.wiring.ambiguity_dialog import apply_saved_resolution
    dc.set_registry([nouvelle])
    c = next(c for c in nl.components if c.type.startswith("custom:"))
    apply_saved_resolution(c, c.type, nl)


def test_le_verdict_suit_une_fiche_CORRIGEE_dans_la_modale():
    """Corriger les broches DANS la modale doit eteindre le message tout de
    suite, sans attendre une reouverture du schema.

    Defaut trouve en QA V1 (2026-08-27) : `_resolve_wiring_netlist` emettait
    la confrontation dans `apply_library_to_netlist`, donc AVANT d'ouvrir la
    modale -- or c'est DANS la modale que le crayon d'une card modifie la
    fiche. Le verdict avait un tour de retard : corriger laissait le message,
    revalider sans rien changer le faisait disparaitre.
    """
    from ui.wiring.declared_apply import refresh_declared_verdict
    faux = _fiche(("VCC", "5V"), ("GND", "GND"), ("TRIG", "D9"), ("ECHO", "D10"))
    juste = _fiche(("VCC", "5V"), ("GND", "GND"), ("TRIG", "D5"), ("ECHO", "D6"))
    dc.set_registry([faux])
    try:
        nl = analyze_netlist(_CODE_CTOR, "arduino_uno_r3",
                             prompt="branche mon capteur")
        apply_library_to_netlist(nl)
        assert _warnings(nl, "declared_pins_diverge_from_code"), \
            "la divergence doit exister AVANT la correction"
        _modale_change_la_fiche(nl, juste)
        refresh_declared_verdict(nl)
        assert not _warnings(nl, "declared_pins_diverge_from_code"), \
            "le verdict doit suivre la fiche corrigee, pas la precedente"
    finally:
        dc.set_registry([])


def test_le_verdict_suit_une_divergence_CREEE_dans_la_modale():
    """L'autre sens, et c'est le plus grave : casser les broches dans la
    modale ne disait RIEN.

    Le silence est pire que le message perime -- l'app dessinait une fiche
    que le code contredit sans jamais l'avouer, ce que tout le ticket #45
    existe pour supprimer.
    """
    from ui.wiring.declared_apply import refresh_declared_verdict
    juste = _fiche(("VCC", "5V"), ("GND", "GND"), ("TRIG", "D5"), ("ECHO", "D6"))
    faux = _fiche(("VCC", "5V"), ("GND", "GND"), ("TRIG", "D9"), ("ECHO", "D10"))
    dc.set_registry([juste])
    try:
        nl = analyze_netlist(_CODE_CTOR, "arduino_uno_r3",
                             prompt="branche mon capteur")
        apply_library_to_netlist(nl)
        assert not _warnings(nl, "declared_pins_diverge_from_code"), \
            "aucune divergence AVANT que l'utilisateur ne casse la fiche"
        _modale_change_la_fiche(nl, faux)
        refresh_declared_verdict(nl)
        w = _warnings(nl, "declared_pins_diverge_from_code")
        assert w, "la divergence creee dans la modale doit etre dite"
        assert w[0].params["pins"] == "D5, D6", w[0].params
    finally:
        dc.set_registry([])


def test_le_rafraichissement_ne_double_aucun_constat():
    """Rejouer le verdict le REMPLACE, il ne s'y ajoute pas.

    Le rafraichissement tourne a chaque resolution, y compris quand aucune
    modale ne s'ouvre. Sans retrait prealable, chaque ouverture empilerait
    un exemplaire de plus du meme message.
    """
    from ui.wiring.declared_apply import refresh_declared_verdict
    faux = _fiche(("VCC", "5V"), ("GND", "GND"), ("TRIG", "D9"), ("ECHO", "D10"))
    dc.set_registry([faux])
    try:
        nl = analyze_netlist(_CODE_CTOR, "arduino_uno_r3",
                             prompt="branche mon capteur")
        apply_library_to_netlist(nl)
        avant = len(_warnings(nl, "declared_pins_diverge_from_code"))
        refresh_declared_verdict(nl)
        refresh_declared_verdict(nl)
        assert avant == 1, avant
        assert len(_warnings(nl, "declared_pins_diverge_from_code")) == 1, \
            [w.message for w in nl.warnings]
        # La reassurance suit la meme regle -- elle est emise par la meme passe.
        assert len(_warnings(nl, "declared_unconnected_pins")) <= 1
    finally:
        dc.set_registry([])


def test_le_rafraichissement_epargne_les_warnings_des_autres():
    """Il ne retire QUE ses propres constats.

    `refresh_declared_verdict` filtre les warnings de la netlist ; viser
    trop large effacerait le travail du detecteur (resistance serie,
    conflits de broches...) a chaque ouverture de schema.
    """
    from ui.wiring.declared_apply import refresh_declared_verdict
    faux = _fiche(("VCC", "5V"), ("GND", "GND"), ("TRIG", "D9"), ("ECHO", "D10"))
    dc.set_registry([faux])
    try:
        nl = analyze_netlist(_CODE_CTOR_LED, "arduino_uno_r3",
                             prompt="branche mon capteur")
        apply_library_to_netlist(nl)
        etrangers = {w.code for w in nl.warnings
                     if not w.code.startswith("declared_")}
        assert etrangers, "il faut au moins un warning tiers pour prouver quoi que ce soit"
        refresh_declared_verdict(nl)
        restants = {w.code for w in nl.warnings
                    if not w.code.startswith("declared_")}
        assert restants == etrangers, sorted(etrangers ^ restants)
    finally:
        dc.set_registry([])


TESTS = [
    test_divergence_franche_est_signalee,
    test_accord_reste_silencieux,
    test_preuve_vide_reste_silencieuse,
    test_sous_ensemble_ne_signale_que_les_manquantes,
    test_l_inverse_n_est_pas_signale,
    test_auto_guerison_au_rejeu,
    test_opt_out_vers_un_type_non_declare_ne_confronte_pas,
    test_la_contradiction_passe_avant_la_reassurance,
    test_un_litteral_qui_n_est_pas_une_broche_declenche_quand_meme,
    test_la_pastille_d_attention_est_atteignable_pour_une_fiche_declaree,
    test_le_gabarit_est_traduit_dans_les_quatre_langues,
    # Tache 2 : collision avec un autre composant du schema.
    test_collision_signal_est_signalee,
    test_collision_rail_reste_silencieuse,
    test_collision_net_i2c_reste_silencieuse,
    test_collision_label_bus_adverse_reste_silencieuse,
    test_collision_label_bus_cote_fiche_reste_silencieuse,
    test_le_gabarit_collision_est_traduit,
    test_les_deux_codes_ont_un_titre_de_constat,
    # Revue finale : la couche d'affichage de la pastille.
    test_deux_fiches_la_contradiction_bat_le_double_usage_perime,
    test_le_clic_montre_la_meme_chose_que_le_survol,
    test_l_adverse_ne_recoit_pas_la_pastille_de_la_fiche,
    # QA V1 (2026-08-27) : le verdict doit decrire le schema que
    # l'utilisateur va VOIR, donc etre rendu APRES la modale.
    test_le_verdict_suit_une_fiche_CORRIGEE_dans_la_modale,
    test_le_verdict_suit_une_divergence_CREEE_dans_la_modale,
    test_le_rafraichissement_ne_double_aucun_constat,
    test_le_rafraichissement_epargne_les_warnings_des_autres,
]


def main() -> int:
    for t in TESTS:
        t()
        print(f"  OK {t.__name__}")
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
