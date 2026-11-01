"""Le constructeur d'une bibliotheque de driver NOMME les broches d'un moteur.

⚠️ **CE FICHIER A CHANGE DE CONTRAT LE 2026-08-29**, le lendemain de sa
creation. Il faut les deux moities de l'histoire pour comprendre le code.

**Le defaut d'origine (#83).** Prompt << 2 moteurs DC avec L298N >>, code
genere utilisant la bibliotheque L298N -> **six moteurs detectes**. Les trois
strategies de groupement (S1 `analogWrite` direct, S2 helper a parametres, S3
dispatch par variable locale) cherchent toutes un `analogWrite` pour designer
la broche de vitesse. Un sketch qui pilote via la BIBLIOTHEQUE n'en ecrit
aucun -- la vitesse passe par `moteur.setSpeed(...)`. Mesure sur le code
signale : `analogWrite -> AUCUN`. Sans broche PWM, aucun groupement, six
sorties nues la ou le code declare deux moteurs.

**Ce que le premier correctif faisait, et pourquoi il ne suffisait pas.** Il
fabriquait des GROUPES heuristiques a partir du constructeur : des LED
`_confidence=low` annotees `_grouped_pwm_pin`. Le compte devenait juste, mais
le resultat restait une DEVINETTE -- la modale s'ouvrait, et on pouvait
decocher << C'est bien un moteur >> sur un moteur que le code declare noir sur
blanc. Il laissait aussi le placeholder de l'`#include` cote a cote avec le
driver reel de l'inference : DEUX boites L298N, dont une vide (le << pin
fantome >> signale en QA).

**Le contrat actuel (spec << certitude d'abord >>).** Une signature de
bibliotheque est du NIVEAU 1 : on construit des composants CERTAINS des la
detection, le placeholder de l'en-tete est consomme, et la machinerie
d'ambiguite n'est jamais atteinte. Le groupage/degroupage survit uniquement au
niveau 3, sur des broches nues -- la ou l'incertitude est reelle (4 drivers DC
sur 5 n'ont aucune signature).

Le chemin A4988 (`AccelStepper(DRIVER, STEP, DIR)`) fait cela depuis toujours :
ce contrat generalise un motif eprouve, il n'invente rien.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.ambiguity_dialog import collect_ambiguous  # noqa: E402
from ui.wiring.markers import extract_netlist  # noqa: E402

BOARD = "arduino_uno_r3"

# Le code de l'utilisateur, reduit a ce qui compte : deux constructeurs L298N,
# aucune trace d'`analogWrite`, la vitesse passant par la bibliotheque.
CODE_BIBLIOTHEQUE = """
#include <L298N.h>

const uint8_t PIN_M1_PWM = 9;
const uint8_t PIN_M1_IN1 = 7;
const uint8_t PIN_M1_IN2 = 8;
const uint8_t PIN_M2_PWM = 10;
const uint8_t PIN_M2_IN1 = 6;
const uint8_t PIN_M2_IN2 = 5;
L298N motor1(PIN_M1_PWM, PIN_M1_IN1, PIN_M1_IN2);
L298N motor2(PIN_M2_PWM, PIN_M2_IN1, PIN_M2_IN2);

void setup() {
  pinMode(PIN_M1_PWM, OUTPUT); pinMode(PIN_M1_IN1, OUTPUT);
  pinMode(PIN_M1_IN2, OUTPUT); pinMode(PIN_M2_PWM, OUTPUT);
  pinMode(PIN_M2_IN1, OUTPUT); pinMode(PIN_M2_IN2, OUTPUT);
  motor1.stop(); motor2.stop();
}

void setMotor(L298N& m, uint8_t in1Pin, uint8_t in2Pin, unsigned short speed) {
  digitalWrite(in1Pin, (speed >= 0) ? HIGH : LOW);
  digitalWrite(in2Pin, (speed >= 0) ? LOW : HIGH);
  m.setSpeed(abs(speed));
}

void loop() {
  setMotor(motor1, PIN_M1_IN1, PIN_M1_IN2, 200);
  setMotor(motor2, PIN_M2_IN1, PIN_M2_IN2, -150);
  delay(3000);
}
"""


def _detecte(code: str, prompt: str = ""):
    """La netlist telle que le DETECTEUR la rend, avant inference."""
    return extract_netlist(code, BOARD, prompt=prompt, context="")


def _pipeline(code: str, prompt: str = ""):
    """Detection PUIS inference : c'est le schema FINAL qui compte.

    Le detecteur ne pose que le contrat (`_control_pin`, `_aux_dir_pins`,
    `_chosen_driver`) ; c'est `inference.apply_rules` qui construit le driver
    cable, apparie les deux moteurs sur un seul pont en H et ajoute la
    batterie. Tester l'un sans l'autre laisserait passer un contrat mal pose.
    """
    from ui.wiring import inference
    nl = _detecte(code, prompt)
    inference.apply_rules(nl)
    return nl


def test_two_constructors_give_two_certain_motors_and_ONE_driver():
    """Le cas signale, de bout en bout."""
    nl = _pipeline(CODE_BIBLIOTHEQUE)
    moteurs = [c for c in nl.components if c.type == "dc_motor"]
    drivers = [c for c in nl.components if c.type == "l298n"]
    assert len(moteurs) == 2, [(c.ref, c.type) for c in nl.components]
    assert len(drivers) == 1, (
        "UNE seule boite L298N : le placeholder de l'#include doit avoir ete "
        "consomme par la detection de signature -- deux boites, dont une "
        "vide, sont le << pin fantome >> signale en QA : %r"
        % ([(c.ref, c.type) for c in nl.components],))
    assert any(p.net for p in drivers[0].pins), \
        "la boite restante est le driver CABLE, pas le placeholder vide"


def test_a_motor_is_designated_M_not_U():
    """Le designateur visible dans les instructions. `dc_motor` retombait sur
    le defaut "U" (circuits integres), rendant le moteur indiscernable de son
    driver -- << Wire the DC motor U1 >> a cote de << L298N driver U3 >>."""
    nl = _pipeline(CODE_BIBLIOTHEQUE)
    moteurs = [c for c in nl.components if c.type == "dc_motor"]
    assert all(c.ref.startswith("M") for c in moteurs),         [c.ref for c in moteurs]


def test_a_signature_motor_never_reaches_the_modal():
    """Niveau 1 : aucune ambiguite, donc aucune modale, donc aucun
    degroupage possible sur un moteur que le code declare."""
    assert collect_ambiguous(_detecte(CODE_BIBLIOTHEQUE)) == []


def test_no_phantom_box_is_left_behind():
    """La garde directe du fantome : plus aucun composant `unrecognized`."""
    nl = _pipeline(CODE_BIBLIOTHEQUE)
    fantomes = [c for c in nl.components
                if c.attributes.get("unrecognized")]
    assert fantomes == [], [(c.ref, c.type) for c in fantomes]


def test_the_wiring_comes_from_the_constructor():
    """Chaque moteur recoit EXACTEMENT les broches de son constructeur.

    C'est ce qui separe une signature d'une heuristique : le moteur 2 est
    (10, 6, 5), des numeros qui ne se suivent pas et que le repli par
    proximite numerique aurait melanges avec ceux du moteur 1.
    """
    nl = _pipeline(CODE_BIBLIOTHEQUE)
    drv = next(c for c in nl.components if c.type == "l298n")
    par_nom = {p.name: p.net for p in drv.pins}
    assert par_nom.get("ENA") == "D9", par_nom
    assert par_nom.get("IN1") == "D7" and par_nom.get("IN2") == "D8", par_nom
    assert par_nom.get("ENB") == "D10", par_nom
    assert par_nom.get("IN3") == "D6" and par_nom.get("IN4") == "D5", par_nom


def test_the_control_pins_are_not_left_as_bare_outputs():
    """Les six broches sont REVENDIQUEES : sans cela le repli generique les
    reprendrait en LED ambigues, et on retrouverait le compte de six."""
    nl = _detecte(CODE_BIBLIOTHEQUE)
    leds = [c for c in nl.components if c.type == "led"]
    assert leds == [], [(c.ref, [p.net for p in c.pins]) for c in leds]


def test_an_include_without_constructor_keeps_the_honest_placeholder():
    """`#include <L298N.h>` seul : le code ne revele RIEN de plus.

    Le filet du 2026-07-29 (boite non cablee + warning) reste -- et il n'y a
    pas de double boite, puisque rien d'autre ne cree le driver. Consommer
    l'en-tete ici rendrait l'app MUETTE sur un include qu'elle ne sait pas
    cabler.
    """
    code = "#include <L298N.h>\nvoid setup(){}\nvoid loop(){}\n"
    nl = _detecte(code)
    boites = [c for c in nl.components if c.type == "l298n"]
    assert len(boites) == 1, [(c.ref, c.type) for c in nl.components]
    assert boites[0].attributes.get("unrecognized"), boites[0].attributes


def test_a_two_argument_constructor_is_left_alone():
    """`L298N(IN1, IN2)` n'a pas de broche de vitesse. Le modele de l'app est
    << une broche PWM + 1-2 broches de sens >> ; en inventer une ferait dire
    au schema ce que le code ne dit pas. On prefere ne rien affirmer.

    ⚠️ Ce test garde le RESULTAT, pas une ligne. Mutation executee en revue
    (2026-08-29) : remplacer `if len(args) < 3:` par `if False:` laisse toute
    la suite VERTE, parce que `len(set(broches)) != 3` tranche deja le meme
    cas -- `args[:3]` d'une liste de deux rend deux elements. Le `len(args)`
    explicite reste pour la lisibilite (il porte le commentaire qui explique
    POURQUOI on s'abstient), mais le croire seul garant serait faux. Meme
    remarque pour `any(b in claimed ...)` : redondant lui aussi."""
    code = CODE_BIBLIOTHEQUE.replace(
        "L298N motor1(PIN_M1_PWM, PIN_M1_IN1, PIN_M1_IN2);",
        "L298N motor1(PIN_M1_IN1, PIN_M1_IN2);")
    nl = _pipeline(code)
    moteurs = [c for c in nl.components if c.type == "dc_motor"]
    assert len(moteurs) == 1, [(c.ref, c.type) for c in nl.components]


def test_the_analogwrite_path_still_works():
    """Contre-epreuve : le NIVEAU 3 n'a pas bouge. Meme montage, mais pilote
    en `analogWrite` sans bibliotheque -> deux candidats GROUPES, donc
    incertains, donc la modale et le degroupage restent disponibles."""
    code = """
const int ENA = 3;
const int IN1 = 4;
const int IN2 = 5;
const int ENB = 9;
const int IN3 = 10;
const int IN4 = 11;
void setup() {
  pinMode(ENA, OUTPUT); pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(ENB, OUTPUT); pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
}
void moteurA(int v){ digitalWrite(IN1,HIGH); digitalWrite(IN2,LOW); analogWrite(ENA,v); }
void moteurB(int v){ digitalWrite(IN3,HIGH); digitalWrite(IN4,LOW); analogWrite(ENB,v); }
void loop(){ moteurA(200); moteurB(150); }
"""
    ambigus = collect_ambiguous(_detecte(code))
    groupes = [c for c in ambigus if c.attributes.get("_grouped_pwm_pin")]
    assert len(groupes) == 2, [c.ref for c in ambigus]


# ── La limite editoriale de 2 moteurs (revue du 2026-08-29) ─────────────

_CODE_QUATRE = """
#include <L298N.h>
L298N frontLeft(3, 2, 4);
L298N frontRight(5, 7, 8);
L298N rearLeft(6, 9, 10);
L298N rearRight(11, 12, 13);
void setup(){}
void loop(){ frontLeft.forward(); frontRight.forward();
             rearLeft.forward(); rearRight.forward(); }
"""


def test_more_than_two_motors_still_draws_a_schematic():
    """⚠️ REGRESSION mesuree en revue : quatre constructeurs rendaient un
    schema VIDE.

    `inference` posait `too_many_dc_motors`, et le dialogue COUPE le rendu SVG
    dessus (`load_svg(b"")` puis `return`) -- pour eviter un schema a moitie
    juste. Avant le niveau 1, ces broches sortaient en LED ambigues, aucun
    moteur n'etait compte, et le schema se dessinait : la detection par
    signature avait donc rendu ce cas PIRE, pas meilleur.

    La limite s'applique maintenant a la detection : les deux premiers sont
    cables, les suivants marques `_skip_wiring` -- reconnus, listes dans les
    instructions, mais pas dessines. C'est ce que la spec demande.
    """
    netlist = _pipeline(_CODE_QUATRE)
    codes = [w.code for w in netlist.warnings]
    assert "too_many_dc_motors" not in codes, (
        "ce warning coupe le rendu du schema : %r" % (codes,))
    moteurs = [c for c in netlist.components if c.type == "dc_motor"]
    assert len(moteurs) == 2, [(c.ref, c.type) for c in netlist.components]
    drivers = [c for c in netlist.components if c.type == "l298n"]
    assert len(drivers) == 1, "un pont en H DOUBLE porte les deux moteurs"


def test_the_motors_left_out_are_named_not_silently_dropped():
    """Un moteur que le code declare ne doit pas disparaitre sans un mot : il
    est liste avec ses broches, et l'explication dit d'ou il vient."""
    netlist = _pipeline(_CODE_QUATRE)
    laisses = netlist.metadata.get("_skipped_motors") or []
    assert len(laisses) == 2, laisses
    assert {m["control_pin"] for m in laisses} == {"D6", "D11"}, laisses
    assert all(m.get("from_code") for m in laisses), (
        "ils viennent du CODE, et le texte affiche en depend", laisses)


def test_the_advice_does_not_send_them_to_a_modal_they_are_absent_from():
    """Le texte par defaut dit << ouvre Modifier les composants et
    decoche >>. Un moteur NOMME par le code n'apparait dans aucune modale --
    ce conseil serait une porte morte, exactement le defaut qu'on vient de
    corriger sur l'engrenage d'un TMC2209 UART."""
    from ui.wiring.instructions import render_instructions
    texte = render_instructions(_pipeline(_CODE_QUATRE), mode="avance",
                                lang="fr")
    assert "Modifier les choix" not in texte, texte[-600:]
    assert "change les moteurs déclarés dans le code" in texte, texte[-600:]


TESTS = [
    test_two_constructors_give_two_certain_motors_and_ONE_driver,
    test_a_motor_is_designated_M_not_U,
    test_a_signature_motor_never_reaches_the_modal,
    test_no_phantom_box_is_left_behind,
    test_the_wiring_comes_from_the_constructor,
    test_the_control_pins_are_not_left_as_bare_outputs,
    test_an_include_without_constructor_keeps_the_honest_placeholder,
    test_a_two_argument_constructor_is_left_alone,
    test_the_analogwrite_path_still_works,
    test_more_than_two_motors_still_draws_a_schematic,
    test_the_motors_left_out_are_named_not_silently_dropped,
    test_the_advice_does_not_send_them_to_a_modal_they_are_absent_from,
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
