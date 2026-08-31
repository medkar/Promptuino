"""Le silence de l'auto-resolution moteur EXIGE un driver nomme.

Decision utilisateur du **2026-08-31**, prise en QA AB1 du #82 sur un cas
reel : « deux moteurs DC » genere du code aux identifiants `motor...`, la
suggestion `_prompt_suggested_type=dc_motor` se pose SANS pilote, et le
schema affichait un **L298N que personne n'a nomme**, sans modale et sans un
mot -- le defaut par defaut de l'inference (« historical behavior
preserved »). Le #82 venait pourtant d'acter que le choix du driver
appartient a la MODALE.

Desormais : moteur nomme + driver nomme -> silence (inchange) ; moteur nomme
SANS driver -> la modale s'ouvre, moteurs deja coches, et ne pose que LA
question restante.

⚠️ Un seul StudioView par process (contrainte Qt) : les tests partagent
l'instance et l'ordre de `TESTS` compte.
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

BOARD = "arduino_uno_r3"
# La forme REELLE du defaut : gemma nomme ses variables `motor...` des que le
# prompt parle de moteurs, et c'est CE nommage qui pose la suggestion.
CODE_MOTOR_IDS = """
const int motor1Speed = 5;
const int motor1In1 = 2;
const int motor1In2 = 3;
const int motor2Speed = 6;
const int motor2In1 = 4;
const int motor2In2 = 7;
void setup() {
  pinMode(motor1Speed, OUTPUT); pinMode(motor1In1, OUTPUT); pinMode(motor1In2, OUTPUT);
  pinMode(motor2Speed, OUTPUT); pinMode(motor2In1, OUTPUT); pinMode(motor2In2, OUTPUT);
}
void loop() {
  digitalWrite(motor1In1, HIGH); digitalWrite(motor1In2, LOW); analogWrite(motor1Speed, 200);
  digitalWrite(motor2In1, HIGH); digitalWrite(motor2In2, LOW); analogWrite(motor2Speed, 150);
}
"""
_STUDIO: list = []


def _studio():
    if not _STUDIO:
        from ui.studio_view import StudioView
        _STUDIO.append(StudioView())
    return _STUDIO[0]


def _resoudre(sv, prompt, *, exec_fn):
    from ui.wiring import ambiguity_dialog as ad
    vrai = ad.AmbiguityDialog.exec
    ad.AmbiguityDialog.exec = exec_fn
    try:
        return sv._resolve_wiring_netlist(CODE_MOTOR_IDS, BOARD, prompt,
                                          "", {})
    finally:
        ad.AmbiguityDialog.exec = vrai


def test_a_motor_without_named_driver_OPENS_the_modal():
    """LE cas d'AB1. Avant : aucun appel, L298N silencieux."""
    sv = _studio()
    sv._wiring_resolutions.clear()
    vus: list = []

    def _exec(self):
        vus.append(sorted(c.ref for c in self._ambiguous))
        return self.DialogCode.Rejected

    _resoudre(sv, "deux moteurs DC", exec_fn=_exec)
    assert vus, "la modale doit s'ouvrir : personne n'a nomme le driver"
    assert len(vus[0]) == 2, ("les DEUX moteurs y sont, vue consolidee "
                              "coherente (ce0ca54)", vus)


def test_the_motors_arrive_PRE_CHECKED_with_only_the_driver_to_pick():
    """La modale ne repose pas la question deja tranchee (« est-ce un
    moteur ? ») : les candidats arrivent groupes et coches, seule la grille
    de drivers attend un choix -- « Valider » reste gris sans lui."""
    from ui.wiring import ambiguity_dialog as ad
    sv = _studio()
    sv._wiring_resolutions.clear()
    etats: list = []

    def _exec(self):
        groupes = [c for c in self._ambiguous
                   if c.attributes.get("_grouped_pwm_pin")]
        etats.append({
            "groupes": len(groupes),
            "valider_bloque_sans_driver": not all(
                self._is_complete(c) for c in self._ambiguous),
        })
        return self.DialogCode.Rejected

    # `_is_complete` est le point de verite unique de « Valider » (X4) ;
    # s'il disparait, ce test doit rougir plutot que deviner.
    if not hasattr(ad.AmbiguityDialog, "_is_complete"):
        raise AssertionError("_is_complete a disparu : reprendre ce test "
                             "sur le nouveau point de verite")
    _resoudre(sv, "deux moteurs DC", exec_fn=_exec)
    assert etats and etats[0]["groupes"] == 2, etats
    assert etats[0]["valider_bloque_sans_driver"], (
        "sans driver choisi, la validation doit rester bloquee", etats)


def test_naming_the_chip_keeps_the_silence():
    """Le contrat historique, intact : moteur + driver nommes -> pas de
    modale, resolution ET driver persistes."""
    sv = _studio()
    sv._wiring_resolutions.clear()
    vus: list = []

    def _exec(self):
        vus.append([c.ref for c in self._ambiguous])
        return self.DialogCode.Rejected

    nl = _resoudre(sv, "deux moteurs DC avec un L298N", exec_fn=_exec)
    assert not vus, ("le driver est nomme : aucune question a poser", vus)
    assert nl is not None
    types = sorted({c.type for c in nl.components})
    assert "dc_motor" in types and "l298n" in types, types
    drivers = [v for k, v in sv._wiring_resolutions.items()
               if k[1].endswith("::_driver")]
    assert drivers and all(d == "l298n" for d in drivers), \
        sv._wiring_resolutions


def test_the_modal_choice_is_persisted_and_replayed():
    """Choisir le driver dans la modale ecrit la resolution ; la reouverture
    est silencieuse et garde le driver choisi -- pas le defaut historique."""
    sv = _studio()
    sv._wiring_resolutions.clear()

    def _choisir(self):
        refs = [c.ref for c in self._ambiguous
                if c.attributes.get("_grouped_pwm_pin")]
        self._on_shared_driver_toggled(refs, "tb6612fng")
        return self.DialogCode.Accepted

    nl = _resoudre(sv, "deux moteurs DC", exec_fn=_choisir)
    assert nl is not None
    assert "tb6612fng" in {c.type for c in nl.components}, \
        sorted({c.type for c in nl.components})

    vus: list = []

    def _espion(self):
        vus.append(True)
        return self.DialogCode.Rejected

    nl2 = _resoudre(sv, "deux moteurs DC", exec_fn=_espion)
    assert not vus, "la question tranchee ne se repose pas"
    assert nl2 is not None
    assert "tb6612fng" in {c.type for c in nl2.components}, \
        sorted({c.type for c in nl2.components})


def test_a_driver_named_in_the_global_prompt_reaches_motor_typed_pins():
    """Le bug PREEXISTANT que la modale a fait remonter (niveau markers).

    Le type vient de l'extrait CODE (`motor1Speed`), et le driver n'etait
    cherche que dans CET extrait -- le TB6612 du prompt global n'etait jamais
    consulte, et le repli global de b4748e6 est saute des qu'un extrait par
    broche existe. Resultat d'avant : resolution silencieuse avec le defaut
    L298N alors que le prompt nommait un TB6612. Un schema faux, sans un mot.
    """
    from ui.wiring.markers import extract_netlist
    nl = extract_netlist(CODE_MOTOR_IDS, BOARD,
                         prompt="deux moteurs DC avec un TB6612", context="")
    groupes = [c for c in nl.components
               if c.attributes.get("_grouped_pwm_pin")]
    assert groupes, [c.type for c in nl.components]
    for c in groupes:
        assert c.attributes.get("_prompt_suggested_driver") == "tb6612fng",             (c.ref, c.attributes)


def test_a_legacy_driverless_resolution_reopens_the_modal_once():
    """La deuxieme passe d'AB1 : « toujours pas de modale ».

    L'ancienne auto-resolution silencieuse persistait `dc_motor` SANS
    `::_driver` — tout projet moteur cree avant le 2026-08-31 porte cet
    heritage, et il silenciait la nouvelle modale : le saved rejouait avec
    driver=None et l'inference posait son L298N. Mesure sur les resolutions
    exactes qu'ecrivait l'ancien code.

    L'heritage incomplet retourne a la modale UNE fois ; l'acceptation ecrit
    le driver, et le silence revient — legitime cette fois.
    """
    from ui.wiring import ambiguity_dialog as ad
    sv = _studio()
    sv._wiring_resolutions.clear()
    sv._wiring_resolutions.update({("", "D5"): "dc_motor",
                                   ("", "D6"): "dc_motor"})

    def _choisir(self):
        refs = [c.ref for c in self._ambiguous
                if c.attributes.get("_grouped_pwm_pin")]
        assert len(refs) == 2, ("les DEUX moteurs reviennent ensemble — un "
                                "saved incomplet ne retient pas ses freres",
                                refs)
        self._on_shared_driver_toggled(refs, "drv8833")
        return self.DialogCode.Accepted

    nl_ = _resoudre(sv, "deux moteurs DC", exec_fn=_choisir)
    assert nl_ is not None
    assert "drv8833" in {c.type for c in nl_.components},         sorted({c.type for c in nl_.components})
    drivers = [v for k, v in sv._wiring_resolutions.items()
               if k[1].endswith("::_driver")]
    assert drivers and all(d == "drv8833" for d in drivers),         sv._wiring_resolutions

    # Et le silence revient : la question a ete tranchee POUR DE VRAI.
    vus: list = []
    nl2 = _resoudre(sv, "deux moteurs DC",
                    exec_fn=lambda self: (vus.append(True),
                                          self.DialogCode.Rejected)[1])
    assert not vus, "l'heritage gueri ne repose plus la question"
    assert nl2 is not None and "drv8833" in {c.type for c in nl2.components}


# Le sketch REEL de la troisieme passe d'AB1 (abrege, structure intacte) :
# helper setMotor + commentaires de gemma qui citent « (e.g., L298N ENA) ».
CODE_COMMENTAIRES_L298N = """
const int PIN_M1_PWM = 9;  // PWM speed control for Motor 1 (e.g., L298N ENA)
const int PIN_M1_IN1 = 7;  // Direction pin 1 for Motor 1
const int PIN_M1_IN2 = 8;  // Direction pin 2 for Motor 1
const int PIN_M2_PWM = 10; // PWM speed control for Motor 2 (e.g., L298N ENA)
const int PIN_M2_IN1 = 5;  // Direction pin 1 for Motor 2
const int PIN_M2_IN2 = 6;
void setup() {
  pinMode(PIN_M1_PWM, OUTPUT); pinMode(PIN_M1_IN1, OUTPUT);
  pinMode(PIN_M1_IN2, OUTPUT); pinMode(PIN_M2_PWM, OUTPUT);
  pinMode(PIN_M2_IN1, OUTPUT); pinMode(PIN_M2_IN2, OUTPUT);
}
void loop() {
  setMotor(PIN_M1_PWM, PIN_M1_IN1, PIN_M1_IN2, 150);
  setMotor(PIN_M2_PWM, PIN_M2_IN1, PIN_M2_IN2, -50);
}
// Helper function to control a DC motor via an H-bridge driver (e.g., L298N)
void setMotor(uint8_t pwmPin, uint8_t in1Pin, uint8_t in2Pin, int speed) {
  digitalWrite(in1Pin, speed >= 0 ? HIGH : LOW);
  digitalWrite(in2Pin, speed >= 0 ? LOW  : HIGH);
  analogWrite(pwmPin, abs(speed));
}
"""


def test_a_driver_named_only_in_AI_comments_does_NOT_count():
    """Le sketch REEL de la troisieme passe d'AB1 : « toujours pas de
    modale ».

    Gemma commente « (e.g., L298N ENA) », l'extrait de code par broche
    incluait les commentaires, et la cascade y trouvait un driver --
    suggestion complete, silence, L298N que personne n'a demande.

    ⛔ **La regle est generale, pas propre aux moteurs** (enoncee par
    l'utilisateur sur ce cas) : les commentaires ne sont pas du code, et le
    cablage est etabli depuis le code. `strip_comments` depouille a l'entree
    d'`extract_netlist`, pour TOUTE la detection -- cf.
    `test_comment_stripping.py` pour les autres retombees (#86 (c) compris).
    """
    from ui.wiring.markers import extract_netlist
    nl = extract_netlist(CODE_COMMENTAIRES_L298N, BOARD,
                         prompt="deux moteurs DC", context="")
    groupes = [c for c in nl.components
               if c.attributes.get("_grouped_pwm_pin")]
    assert len(groupes) == 2, [(c.ref, c.type) for c in nl.components]
    for c in groupes:
        assert c.attributes.get("_prompt_suggested_driver") is None,             (c.ref, c.attributes)


def test_the_users_own_words_still_beat_the_AI_comment():
    """Contre-epreuve : le meme sketch commente « L298N », mais l'UTILISATEUR
    ecrit TB6612 -- c'est lui qui gagne, et en silence (sa puce est
    nommee)."""
    from ui.wiring.markers import extract_netlist
    nl = extract_netlist(CODE_COMMENTAIRES_L298N, BOARD,
                         prompt="deux moteurs DC avec un TB6612", context="")
    groupes = [c for c in nl.components
               if c.attributes.get("_grouped_pwm_pin")]
    assert groupes
    for c in groupes:
        assert c.attributes.get("_prompt_suggested_driver") == "tb6612fng",             (c.ref, c.attributes)


def test_all_three_code_shapes_open_the_modal_without_a_named_driver():
    """Les trois formes de code qui ont successivement defait AB1, ensemble :
    identifiants `motor...`, helper `setMotor` anonyme, commentaires IA citant
    un driver. Aucune ne doit silencier la question du pilote."""
    sv = _studio()
    from ui.wiring import ambiguity_dialog as ad
    vrai = ad.AmbiguityDialog.exec
    for nom, code in (("identifiants motor", CODE_MOTOR_IDS),
                      ("commentaires L298N", CODE_COMMENTAIRES_L298N)):
        sv._wiring_resolutions.clear()
        vus: list = []
        ad.AmbiguityDialog.exec = lambda self, _v=vus: (
            _v.append(True), self.DialogCode.Rejected)[1]
        try:
            sv._resolve_wiring_netlist(code, BOARD, "deux moteurs DC", "", {})
        finally:
            ad.AmbiguityDialog.exec = vrai
        assert vus, f"pas de modale sur la forme : {nom}"


# La forme NIVEAU 1 : le code appelle la bibliotheque L298N.
CODE_LIB_L298N = """
#include <L298N.h>
const unsigned int EN_A = 9, IN1_A = 7, IN2_A = 8;
const unsigned int EN_B = 10, IN1_B = 6, IN2_B = 5;
L298N motorA(EN_A, IN1_A, IN2_A);
L298N motorB(EN_B, IN1_B, IN2_B);
void setup() { motorA.setSpeed(200); motorB.setSpeed(150); }
void loop() { motorA.forward(); motorB.backward(); }
"""


def test_level1_motors_get_ONE_grouped_section_with_driver_cards():
    """QA AB2 (2026-08-31, photo) : « Modifier les composants » sur un sketch
    L298N ouvrait DEUX pages jumelles « Broche numerique 9 » — les broches
    des deux moteurs remontent au MEME signal Arduino (la clef degeneree du
    #86 (a)) — avec un picker offrant de les requalifier en LED, alors que le
    code appelle la lib. Une seule section pour le lot, cards de drivers,
    courant pre-selectionne, pas de picker."""
    from ui.wiring import inference
    from ui.wiring.ambiguity_dialog import (AmbiguityDialog,
                                            collect_all_editable)
    from ui.wiring.markers import extract_netlist
    nl_ = extract_netlist(CODE_LIB_L298N, BOARD, prompt="", context="")
    inference.apply_rules(nl_)
    tous = collect_all_editable(nl_, set())
    moteurs = [c for c in tous if c.type == "dc_motor"]
    assert len(moteurs) == 2, [(c.ref, c.type) for c in tous]
    dlg = AmbiguityDialog(tous, netlist=nl_)
    # UNE page pour les deux moteurs, pas deux pages jumelles.
    pages_moteur = [e for e in dlg._entries
                    if e["component"] is not None
                    and e["component"].type == "dc_motor"]
    assert len(pages_moteur) == 1, [
        (e["component"].ref if e["component"] else None,
         e["kind"]) for e in dlg._entries]
    # Le titre du rail dit le LOT, pas une broche.
    titre = dlg._entry_title(pages_moteur[0])
    assert "2" in titre and "roche" not in titre, titre
    # Cards des 5 drivers, courant (l298n) pre-selectionne, pas de picker.
    ancre = pages_moteur[0]["component"].ref
    cards = dlg._driver_cards.get(ancre) or {}
    assert len(cards) == 5, sorted(cards)
    assert [t for t, c in cards.items()
            if getattr(c, "_selected", False)] == ["l298n"]
    assert all(c.ref not in dlg._pickers for c in moteurs)
    # La page nait complete : le driver courant est une certitude.
    assert dlg._entry_done(pages_moteur[0]), "la ligne du rail nait cochee"


def test_level1_driver_change_offers_regen_and_writes_NOTHING():
    """Valider un changement de driver sur du niveau 1 : l'offre de
    regeneration part (le code est la source, c'est lui qui change), et
    AUCUNE resolution n'est ecrite — la clef est degeneree, ecrire dessous
    ferait heriter moteurs et driver du meme type (#86 (a))."""
    from ui.wiring import ambiguity_dialog as ad
    sv = _studio()
    sv._wiring_resolutions.clear()
    sv._features = [type("F", (), {"id": "fn-1"})()]
    demandes: list = []
    sv._confirm_regen_after_swap = (
        lambda a, b: (demandes.append((a, b)), True)[1])
    sv._pending_regen_swap = None

    def _choisir(self):
        moteurs = [c for c in self._ambiguous if c.type == "dc_motor"]
        assert moteurs, "pre-condition"
        for c in moteurs:
            self._chosen_driver[c.ref] = "drv8833"
        return self.DialogCode.Accepted

    vrai = ad.AmbiguityDialog.exec
    ad.AmbiguityDialog.exec = _choisir
    try:
        sv._resolve_wiring_netlist(CODE_LIB_L298N, BOARD, "", "", {},
                                   force_remodal=True)
    finally:
        ad.AmbiguityDialog.exec = vrai
        sv._pending_regen_swap = None
        sv._features = []
    assert demandes == [("l298n", "drv8833")], (
        "UNE offre, du driver courant vers le choisi", demandes)
    assert sv._wiring_resolutions == {}, (
        "RIEN ne doit s'ecrire sous la clef degeneree",
        sv._wiring_resolutions)


def test_level1_keeping_the_driver_stays_silent_and_writes_nothing():
    from ui.wiring import ambiguity_dialog as ad
    sv = _studio()
    sv._wiring_resolutions.clear()
    demandes: list = []
    sv._confirm_regen_after_swap = (
        lambda a, b: (demandes.append((a, b)), True)[1])

    vrai = ad.AmbiguityDialog.exec
    ad.AmbiguityDialog.exec = lambda self: self.DialogCode.Accepted
    try:
        sv._resolve_wiring_netlist(CODE_LIB_L298N, BOARD, "", "", {},
                                   force_remodal=True)
    finally:
        ad.AmbiguityDialog.exec = vrai
    assert demandes == [], demandes
    assert sv._wiring_resolutions == {}, sv._wiring_resolutions


TESTS = [
    test_a_motor_without_named_driver_OPENS_the_modal,
    test_the_motors_arrive_PRE_CHECKED_with_only_the_driver_to_pick,
    test_naming_the_chip_keeps_the_silence,
    test_the_modal_choice_is_persisted_and_replayed,
    test_a_driver_named_in_the_global_prompt_reaches_motor_typed_pins,
    test_a_legacy_driverless_resolution_reopens_the_modal_once,
    test_a_driver_named_only_in_AI_comments_does_NOT_count,
    test_the_users_own_words_still_beat_the_AI_comment,
    test_all_three_code_shapes_open_the_modal_without_a_named_driver,
    test_level1_motors_get_ONE_grouped_section_with_driver_cards,
    test_level1_driver_change_offers_regen_and_writes_NOTHING,
    test_level1_keeping_the_driver_stays_silent_and_writes_nothing,
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
    # Teardown Qt statique apres un StudioView : os._exit reflete les
    # assertions, pas un crash de destruction.
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
