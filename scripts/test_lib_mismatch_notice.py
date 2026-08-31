"""Le code ne cite pas la bibliotheque du composant qu'on vient de choisir.

Question utilisateur du 2026-08-29 : passer une LED en servo ecrit un servo
dans le schema pendant que le code continue de faire clignoter la broche avec
`digitalWrite`, et rien ne le disait.

L'offre de regeneration existante (`_chip_swap_regen_target`) ne pouvait pas
couvrir ce cas, pour DEUX raisons mesurees ce jour-la :

- elle exige `signature_detected`, donc un composant LU dans le code, alors
  que la modale d'ambiguite ne traite QUE des composants incertains
  (`_confidence == "low"`, `signature_detected` faux) ;
- et sa correspondance type -> corpus passait par
  `clarification_groups.corpus_id_of_type` SEULE, qui derive sa table des
  `ClarifyGroup` -- lesquels EXCLUENT deliberement moteurs et servos. Mesure
  CE JOUR-LA : `_chip_swap_regen_target('led', 'servo')` rendait None,
  `('led', 'buzzer')` rendait 'buzzer'. Le buzzer ne marchait que par
  accident de perimetre.

D'ou un constat separe, qui lit la correspondance dans le REGISTRE de
composants et n'offre AUCUNE action : l'app signale, l'utilisateur decide.

⚠️ La SECONDE raison n'est PLUS VRAIE depuis #82, plus tard ce meme jour :
`_chip_swap_regen_target` route desormais sa correspondance par le registre
de composants avant `corpus_id_of_type`, et servo/neopixel/dc_motor y ont une
entree. Rejoue aujourd'hui : `_chip_swap_regen_target('led', 'servo')` rend
'servo', plus None. La PREMIERE raison, elle, tient seule et suffit a
justifier ce fichier : la modale d'ambiguite ne fournit jamais un composant
`signature_detected`, donc l'offre de regeneration ne peut structurellement
pas se declencher ici -- meme corrigee par #82. `missing_libs_for_resolved`
reste le seul mecanisme qui couvre ce cas.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.studio_view import missing_libs_for_resolved  # noqa: E402

CODE_LED = """
void setup() { pinMode(9, OUTPUT); }
void loop() { digitalWrite(9, HIGH); delay(500); digitalWrite(9, LOW); }
"""

CODE_SERVO = """
#include <Servo.h>
Servo monServo;
void setup() { monServo.attach(9); }
void loop() { monServo.write(90); }
"""


class _Faux:
    """Le predicat ne lit qu'un `.type` : pas besoin d'une vraie Netlist."""

    def __init__(self, type_id: str):
        self.type = type_id


def test_a_servo_without_its_library_is_reported():
    assert missing_libs_for_resolved(CODE_LED, [_Faux("servo")]) == [
        ("servo", "Servo")], missing_libs_for_resolved(CODE_LED, [_Faux("servo")])


def test_the_library_already_included_says_nothing():
    """Le cas NORMAL : le code pilote deja un servo, on se tait."""
    assert missing_libs_for_resolved(CODE_SERVO, [_Faux("servo")]) == []


def test_a_component_without_any_library_says_nothing():
    """LED, buzzer, relais, LDR : il n'y a rien a manquer, `digitalWrite`
    suffit. Les signaler serait du bruit sur le cas le plus courant."""
    for type_id in ("led", "buzzer", "relay", "ldr"):
        assert missing_libs_for_resolved(CODE_LED, [_Faux(type_id)]) == [], \
            type_id


def test_a_user_declared_component_says_nothing():
    """L'app ne connait pas le code d'une fiche declaree : l'accuser de ne pas
    correspondre serait une devinette."""
    assert missing_libs_for_resolved(CODE_LED, [_Faux("custom:monchip")]) == []


def test_the_cases_the_regeneration_offer_could_not_reach():
    """Servo, NeoPixel et moteur DC : les trois que `_chip_swap_regen_target`
    ne pouvait pas resoudre AVANT #82 (elle passait par `corpus_id_of_type`
    SEULE, qui exclut les `ClarifyGroup` moteurs/servos). #82 a corrige cette
    correspondance-la (routee par le registre depuis), mais le nom de ce test
    reste vrai pour l'AUTRE raison, inchangee (cf. docstring du fichier) : la
    modale d'ambiguite ne fournit jamais un composant `signature_detected`,
    donc l'offre ne peut de toute facon pas se declencher ici.
    `missing_libs_for_resolved` reste le seul mecanisme qui couvre ce cas."""
    trouves = dict(missing_libs_for_resolved(
        CODE_LED, [_Faux("servo"), _Faux("neopixel")]))
    assert trouves.get("servo") == "Servo", trouves
    assert "NeoPixel" in trouves.get("neopixel", ""), trouves


def test_the_same_type_is_reported_once():
    """Trois LED devenues servos ne font pas trois lignes dans le message."""
    resultat = missing_libs_for_resolved(
        CODE_LED, [_Faux("servo"), _Faux("servo"), _Faux("servo")])
    assert resultat == [("servo", "Servo")], resultat


def test_the_notice_exists_in_the_four_languages_and_takes_the_items():
    """Le message est un CONSTAT : il invite a regenerer a la main, il ne
    propose aucun bouton. On verifie aussi qu'il ne PROMET rien -- pas de
    « on va regenerer », l'app signale et s'arrete la."""
    from ui.i18n import LANGUAGE_NAMES, lang_manager
    vus = set()
    for code in LANGUAGE_NAMES:
        lang_manager.set_language(code)
        s = lang_manager.current
        titre = s.lib_mismatch_title
        corps = s.lib_mismatch_body
        assert titre and corps, code
        assert "{items}" in corps, (code, corps)
        rendu = corps.format(items="• <b>servomoteur</b> — <code>Servo</code>")
        assert "servomoteur" in rendu, code
        vus.add(titre)
    lang_manager.set_language("fr")
    assert len(vus) == len(LANGUAGE_NAMES), vus


TESTS = [
    test_a_servo_without_its_library_is_reported,
    test_the_library_already_included_says_nothing,
    test_a_component_without_any_library_says_nothing,
    test_a_user_declared_component_says_nothing,
    test_the_cases_the_regeneration_offer_could_not_reach,
    test_the_same_type_is_reported_once,
    test_the_notice_exists_in_the_four_languages_and_takes_the_items,
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
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
