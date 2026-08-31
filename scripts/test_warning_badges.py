"""Tout warning affiche dans les instructions pose sa PASTILLE.

Demande utilisateur du **2026-08-31**, en QA de la section AA : « je voudrais
que le warning apparaisse via une pastille sur le composant [...] dans tous
les cas ou il y a un warning dans les instructions ».

**Le defaut de fond.** La pastille etait pilotee par une liste d'attributs et
de types tenue A LA MAIN (`_INFO_TYPES` + `unrecognized` + `presumed_*`...).
Chaque nouveau filet d'honnetete devait penser a s'y ajouter -- et celui du
TMC2209 UART, pose la veille, ne l'avait pas fait : le panneau de droite
disait « STEP et DIR ne sont pas cables », la boite ne disait rien. C'est la
meme classe de defaut que les huit composants cables mais introuvables dans
l'onglet << Composants >> (2026-07-31) : deux mecanismes qui decrivent le meme
fait et qu'aucune garde ne force a s'accorder.

⚠️ **Le sens ajoute est UNIQUEMENT warning -> pastille.** L'autre reste : un
L298N porte sa nuance pedagogique SANS aucun warning. Ce test ne doit donc pas
verifier une equivalence, seulement l'implication.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

import ui.declared_components as declared_components  # noqa: E402
declared_components.set_registry([])

from ui.wiring import inference  # noqa: E402
from ui.wiring.markers import extract_netlist  # noqa: E402
from ui.wiring.netlist import SEVERITY_INFO  # noqa: E402
from ui.wiring.wiring_diagram_dialog import WiringDiagramDialog  # noqa: E402

BOARD = "arduino_uno_r3"

CODE_TMC_UART = """
#include <TMC2209.h>
HardwareSerial & serial_stream = Serial1;
TMC2209 stepper_driver;
void setup(){ stepper_driver.setup(serial_stream); }
void loop(){}
"""
CODE_TROIS_LED = """
const int L1 = 5, L2 = 6, L3 = 7;
void setup(){ pinMode(L1,OUTPUT); pinMode(L2,OUTPUT); pinMode(L3,OUTPUT); }
void loop(){ digitalWrite(L1,HIGH); digitalWrite(L2,HIGH); digitalWrite(L3,HIGH); }
"""
CODE_INCONNU = """
#include <MaLibInconnue.h>
MaLibInconnue capteur(5, 6);
void setup(){ capteur.begin(); }
void loop(){}
"""
CODE_ANALOG = """
const int CAPTEUR = A0;
void setup(){ Serial.begin(9600); }
void loop(){ Serial.println(analogRead(CAPTEUR)); }
"""


class _Sonde(WiringDiagramDialog):
    """On n'instancie PAS le dialogue -- il construit toute la scene
    graphique. On reutilise ses methodes sur une netlist posee a la main :
    c'est la couche qui DECIDE de la pastille, pas la plus simple a
    interroger."""

    def __init__(self, netlist):
        self._netlist = netlist
        self._mode = "avance"


def _schema(code: str):
    nl = extract_netlist(code, BOARD, prompt="", context="")
    inference.apply_rules(nl)
    return nl


def _pastilles(netlist):
    sonde = _Sonde(netlist)
    refs = sonde._compute_info_refs()
    return refs, sonde._compute_info_tooltips(refs)


def _nu(html: str) -> str:
    return (html or "").replace("<br>", " ").replace("<b>", "") \
                       .replace("</b>", "")


# ── l'invariant demande ──────────────────────────────────────────────────

def test_every_warning_puts_a_badge_on_the_component_it_names():
    """L'invariant, sur quatre montages qui couvrent les filets d'honnetete.

    Un warning qui NOMME un composant doit le marquer. La reciproque n'est
    PAS testee : un L298N porte sa nuance sans warning.
    """
    for nom, code in (("TMC2209 UART", CODE_TMC_UART),
                      ("3 LED", CODE_TROIS_LED),
                      ("include inconnu", CODE_INCONNU),
                      ("broche analogique nue", CODE_ANALOG)):
        netlist = _schema(code)
        refs, _ = _pastilles(netlist)
        sans_pastille = {c.ref for c in netlist.components
                         if c.type == "resistor"}
        attendus = {r for w in netlist.warnings
                    for r in (getattr(w, "refs", None) or [])} - sans_pastille
        assert attendus, (nom, "pre-condition : au moins un warning nomme")
        assert attendus <= refs, (nom, sorted(attendus - refs))


def test_the_tmc2209_says_on_its_box_what_the_panel_says():
    """LE cas signale en QA. Le panneau disait que STEP/DIR ne sont pas
    cables ; la boite ne disait rien."""
    netlist = _schema(CODE_TMC_UART)
    drv = next(c for c in netlist.components if c.type == "tmc2209")
    refs, tips = _pastilles(netlist)
    assert drv.ref in refs, sorted(refs)
    texte = _nu(tips[drv.ref])
    assert "UART" in texte, texte
    # ⛔ Surtout pas le texte generique : il inviterait a cliquer pour
    # apprendre ce que l'infobulle est censee DIRE (decision 2026-08-08).
    assert "clic pour comprendre" not in texte, texte


def test_a_series_resistor_gets_no_badge_of_its_own():
    """`led_series_resistor` nomme la LED **et** sa resistance. Celle-ci est
    un passif implicite -- elle n'a deja ni engrenage ni menu ; lui donner une
    pastille doublerait chaque avertissement de LED a l'ecran."""
    netlist = _schema(CODE_TROIS_LED)
    refs, _ = _pastilles(netlist)
    resistances = {c.ref for c in netlist.components if c.type == "resistor"}
    assert resistances, "pre-condition : il y a des resistances"
    assert not (resistances & refs), sorted(resistances & refs)
    leds = {c.ref for c in netlist.components if c.type == "led"}
    assert leds <= refs, sorted(leds - refs)


def test_several_warnings_on_one_component_are_numbered():
    """Deux phrases collees se lisent comme une seule : le survol perdait
    justement l'information qu'il y en avait deux."""
    netlist = _schema(CODE_INCONNU)
    ref = netlist.components[0].ref
    netlist.add_warning(code="undrawable_component", severity=SEVERITY_INFO,
                        message="second point", refs=[ref],
                        params={"ref": ref, "pin_count": 9})
    _refs, tips = _pastilles(netlist)
    html = tips[ref]
    assert "1." in html and "2." in html, html
    # Le TITRE dit le compte : garder celui d'un seul des deux codes serait un
    # choix arbitraire, et mentirait sur ce que la pastille porte.
    assert "2" in _nu(html).split("  ")[0], _nu(html)[:80]
    # Et les deux points sont SEPARES, pas colles sur la meme ligne repliee.
    assert "<br>2." in html, html


def test_a_single_warning_keeps_its_own_title():
    """Un seul point garde le titre de SON code -- << Composant non reconnu >>
    dit plus que << 1 point d'attention >>."""
    netlist = _schema(CODE_INCONNU)
    ref = netlist.components[0].ref
    _refs, tips = _pastilles(netlist)
    titre = _nu(tips[ref]).split("  ")[0]
    assert "point" not in titre.lower(), titre


def test_a_component_with_no_warning_keeps_its_pedagogical_badge():
    """Le sens WARNING -> pastille s'AJOUTE, il ne remplace rien. Un L298N
    porte sa nuance pedagogique sans qu'aucun warning ne le nomme."""
    code = """
#include <L298N.h>
L298N fl(3, 2, 4);
void setup(){}
void loop(){ fl.forward(); }
"""
    netlist = _schema(code)
    drv = next(c for c in netlist.components if c.type == "l298n")
    nomme = {r for w in netlist.warnings
             for r in (getattr(w, "refs", None) or [])}
    assert drv.ref not in nomme, "pre-condition : aucun warning ne le nomme"
    refs, _ = _pastilles(netlist)
    assert drv.ref in refs, sorted(refs)


def test_the_four_languages_have_the_count_title():
    """Garde de derive : un titre manquant afficherait une cle brute."""
    from ui.wiring.wiring_diagram_dialog import _DIALOG_LABELS
    entree = _DIALOG_LABELS["info_title_several"]
    assert set(entree) >= {"fr", "en", "es", "it"}, sorted(entree)
    for lang, txt in entree.items():
        assert "{n}" in txt, (lang, txt)


# ── Ou et comment un avertissement se montre (QA AA6 / AA7.1) ──────────

def test_what_is_not_wiring_comes_FIRST_in_the_panel():
    """Demande en QA AA6 : les avertissements et la liste des moteurs non
    cables etaient en BAS, apres toutes les etapes de branchement.

    Sur un montage a plusieurs composants il fallait donc faire defiler tout
    le panneau pour apprendre qu'une partie du schema etait une devinette, ou
    qu'un moteur declare n'y figurait pas. Ce qui conditionne la lecture du
    reste doit se lire d'abord.
    """
    from ui.wiring.instructions import render_instructions
    code = """
#include <L298N.h>
L298N fl(3, 2, 4);
L298N fr(5, 7, 8);
L298N rl(6, 9, 10);
L298N rr(11, 12, 13);
void setup(){}
void loop(){ fl.forward(); }
"""
    md = render_instructions(_schema(code), mode="avance", lang="fr")
    titres = [ligne for ligne in md.splitlines() if ligne.startswith("## ")]
    assert len(titres) >= 3, titres
    # Les deux sections hors cablage, puis les composants.
    assert "Avertissements" in titres[0], titres
    assert "non câblés" in titres[1], titres
    assert all("Avertissements" not in t and "non câblés" not in t
               for t in titres[2:]), titres


def test_the_click_shows_AS_MANY_points_as_the_hover():
    """Releve en QA AA7.1 : le survol annoncait << 2 points d'attention >>,
    le clic n'en montrait qu'UN.

    ⚠️ C'est la DEUXIEME fois que ces deux chemins divergent. La premiere
    (#45) : le survol disait la contradiction, le clic ressortait un
    `pin_double_use` perime -- chacun avait sa propre regle de priorite. Ils
    lisent desormais la MEME source (`_warnings_by_ref`) ; recopier la regle
    une troisieme fois la ferait diverger une troisieme fois.
    """
    from PyQt6.QtWidgets import QMessageBox
    netlist = _schema(CODE_INCONNU)
    ref = netlist.components[0].ref
    netlist.add_warning(code="undrawable_component", severity=SEVERITY_INFO,
                        message="second point", refs=[ref],
                        params={"ref": ref, "pin_count": 9})
    sonde = _Sonde(netlist)
    vus = []
    original = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: vus.append(a))
    try:
        sonde._show_warning_info(ref)
    finally:
        QMessageBox.information = original
    assert vus, "le clic n'a rien ouvert"
    titre, corps = vus[0][1], vus[0][2]
    assert "2" in titre, titre
    assert "1." in corps and "2." in corps, corps
    # Et le survol dit la MEME chose -- c'est la parite qui est verrouillee,
    # pas deux textes independants qui se trouvent d'accord aujourd'hui.
    tips = sonde._compute_info_tooltips(sonde._compute_info_refs())
    assert titre in _nu(tips[ref]), (titre, _nu(tips[ref])[:80])


def test_a_single_point_opens_with_its_own_title_on_click():
    """Un seul point garde le titre de SON code, au clic comme au survol."""
    from PyQt6.QtWidgets import QMessageBox
    netlist = _schema(CODE_INCONNU)
    ref = netlist.components[0].ref
    vus = []
    original = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: vus.append(a))
    try:
        _Sonde(netlist)._show_warning_info(ref)
    finally:
        QMessageBox.information = original
    assert vus, "le clic n'a rien ouvert"
    assert "point" not in vus[0][1].lower(), vus[0][1]


# ── Ce qu'un avertissement ne doit PAS dire (trouve par l'affichage) ────

def test_a_shared_battery_rail_is_not_a_pin_conflict():
    """Deux composants alimentes par la MEME pile, c'est a quoi sert un rail.

    `BAT_5V` n'etait ni dans `_POWER_NETS` ni exclu autrement, donc le driver
    et la pile se denoncaient mutuellement en severite ERREUR : << Pin BAT_5V
    utilisee par plusieurs composants : U1, BAT1. >>

    ⚠️ Ca s'affichait DEJA dans le panneau ; c'est de l'avoir pose sur les
    boites qui l'a rendu impossible a ignorer. Meme histoire que le net VIDE,
    trouve le meme jour et par le meme moyen -- deux faux avertissements que
    la parite panneau/pastille a fait sortir du bois.
    """
    netlist = _schema(CODE_TMC_UART)
    rails = {p.net for c in netlist.components for p in c.pins
             if (p.net or "").startswith("BAT_")}
    assert rails, "pre-condition : ce montage a bien un rail de pile"
    codes = [w.code for w in netlist.warnings]
    assert "pin_double_use" not in codes, (
        "un rail d'alimentation partage n'est pas un conflit : %r" % (codes,))


def test_a_real_pin_conflict_is_still_reported():
    """Contre-epreuve : on n'a pas eteint le detecteur, seulement retire deux
    nets qui ne sont pas des signaux."""
    from ui.wiring.inference import _is_signal_net
    assert _is_signal_net("D5") is True
    assert _is_signal_net("A0") is True
    for muet in ("", "GND", "5V", "NET_A", "BAT_5V", "BAT_5V_2"):
        assert _is_signal_net(muet) is False, muet


TESTS = [
    test_every_warning_puts_a_badge_on_the_component_it_names,
    test_the_tmc2209_says_on_its_box_what_the_panel_says,
    test_a_series_resistor_gets_no_badge_of_its_own,
    test_several_warnings_on_one_component_are_numbered,
    test_a_single_warning_keeps_its_own_title,
    test_a_component_with_no_warning_keeps_its_pedagogical_badge,
    test_the_four_languages_have_the_count_title,
    test_what_is_not_wiring_comes_FIRST_in_the_panel,
    test_the_click_shows_AS_MANY_points_as_the_hover,
    test_a_single_point_opens_with_its_own_title_on_click,
    test_a_shared_battery_rail_is_not_a_pin_conflict,
    test_a_real_pin_conflict_is_still_reported,
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
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
