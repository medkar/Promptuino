"""Les drivers de moteur pas-a-pas reconnus par leur SIGNATURE.

Le chemin A4988 (`AccelStepper(DRIVER, STEP, DIR)`) construit un driver
entierement cable depuis sa signature depuis toujours, sans modale ni
groupage. Trois autres drivers ont une signature aussi nette, une entree
corpus, et leur dessin AU CATALOGUE -- il ne manquait que la detection. Sans
elle, leur `#include` produisait une boite placeholder VIDE (le meme << pin
fantome >> que le L298N).

⚠️ **Le piege de ce lot, et la raison de son test dedie** : l'ordre des
arguments du DRV8825 est `begin(DIR, STEP)`, l'INVERSE d'AccelStepper. C'est
l'exemple officiel du corpus qui le dit (`DIRECTION_PIN = 4`, `STEP_PIN = 5`),
et c'est ce que le modele genere.

⚠️ **Et l'honnetete du TMC2209** : son exemple pilote par UART
(`d.setup(serial)`) et ne revele AUCUNE broche STEP/DIR. On dessine la boite,
son alimentation et son moteur -- mais on n'invente pas de broches de
commande. Un schema qui affirme plus que le code est precisement ce que les
filets de `markers.py` existent pour empecher.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.markers import extract_netlist  # noqa: E402

BOARD = "arduino_uno_r3"

# Les formes EXACTES des `example_code` du corpus : c'est ce que le modele
# ecrit, donc la seule verite sur ce que le detecteur verra.
CODE_DRV8825 = """
#include "DRV8825.h"

DRV8825 stepper;
const int DIRECTION_PIN = 4;
const int STEP_PIN = 5;

void setup() {
  Serial.begin(115200);
  stepper.begin(DIRECTION_PIN, STEP_PIN);
}
void loop() {
  stepper.setDirection(DRV8825_CLOCK_WISE);
  stepper.step();
}
"""

CODE_STSPIN220 = """
#include <Adafruit_STSPIN220.h>
const int stepsPerRevolution = 200;
const int DIR_PIN = 2;
const int STEP_PIN = 3;
Adafruit_STSPIN220 myStepper(stepsPerRevolution, STEP_PIN, DIR_PIN);
void setup() { myStepper.setSpeed(60); }
void loop() { myStepper.step(stepsPerRevolution); }
"""

CODE_STSPIN220_MODES = CODE_STSPIN220.replace(
    "Adafruit_STSPIN220 myStepper(stepsPerRevolution, STEP_PIN, DIR_PIN);",
    "Adafruit_STSPIN220 myStepper(stepsPerRevolution, STEP_PIN, DIR_PIN, 4, 5);")

CODE_TMC2209 = """
#include <TMC2209.h>
HardwareSerial & serial_stream = Serial1;
TMC2209 stepper_driver;
void setup() {
  Serial.begin(115200);
  stepper_driver.setup(serial_stream);
}
void loop() {}
"""


def _detecte(code: str):
    return extract_netlist(code, BOARD, prompt="", context="")


def _pipeline(code: str):
    from ui.wiring import inference
    nl = _detecte(code)
    inference.apply_rules(nl)
    return nl


def _broches(nl, type_id: str) -> dict:
    comp = next(c for c in nl.components if c.type == type_id)
    return {p.name: p.net for p in comp.pins}


def test_drv8825_begin_has_DIR_FIRST_then_STEP():
    """⚠️ L'erreur d'inattention la plus probable de tout ce chantier.

    `begin(DIR, STEP)` est l'INVERSE de `AccelStepper(DRIVER, STEP, DIR)`.
    Inverser les deux donnerait un schema faux mais plausible -- rien ne le
    signalerait a l'oeil.
    """
    p = _broches(_detecte(CODE_DRV8825), "drv8825")
    assert p["DIR"] == "D4", ("DIR est le PREMIER argument de begin()", p)
    assert p["STEP"] == "D5", ("STEP est le SECOND argument de begin()", p)


def test_drv8825_electrical_defaults_match_the_a4988_block():
    """Memes regles que l'A4988, dont ce driver est broche-a-broche
    compatible : logique en 5 V, moteur sur batterie, et les entrees actives
    a l'etat bas cablees explicitement (les clones n'ont pas toujours les
    tirages internes du Pololu d'origine)."""
    p = _broches(_detecte(CODE_DRV8825), "drv8825")
    assert p["VDD"] == "5V" and p["GND"] == "GND", p
    assert p["VMOT"] == "BAT_5V", p
    assert p["ENA"] == "GND", p
    assert p["RST"] == "5V" and p["SLP"] == "5V", p
    assert p["MS1"] == "GND" and p["MS2"] == "GND" and p["MS3"] == "GND", p


def test_stspin220_reads_step_and_dir_from_its_constructor():
    p = _broches(_detecte(CODE_STSPIN220), "stspin220")
    assert p["STEP"] == "D3" and p["DIR"] == "D2", p
    assert p["VDD"] == "5V" and p["VMOTOR"] == "BAT_5V", p


def test_stspin220_mode_pins_only_when_the_constructor_gives_them():
    """Sans MODE au constructeur, les broches vont a GND -- pas de
    micro-pas, le defaut sur et documente du bloc A4988. Les cabler vers
    l'Arduino sans que le code les nomme serait une invention."""
    sans = _broches(_detecte(CODE_STSPIN220), "stspin220")
    assert sans["MS1"] == "GND" and sans["MS2"] == "GND", sans
    avec = _broches(_detecte(CODE_STSPIN220_MODES), "stspin220")
    assert avec["MS1"] == "D4" and avec["MS2"] == "D5", avec


def test_tmc2209_invents_no_control_pin():
    """Le pilotage est UART : l'exemple ne revele aucune broche STEP/DIR.

    On dessine la boite et son alimentation -- affirmer des broches de
    commande serait plus grave qu'un dessin incomplet.
    """
    p = _broches(_detecte(CODE_TMC2209), "tmc2209")
    assert p["VDD"] == "5V" and p["VMOTOR"] == "BAT_5V", p
    assert p["GND"] == "GND", p
    for nom in ("STEP", "DIR", "UART", "MS1", "MS2"):
        assert p[nom] == "", (nom, p)


def test_tmc2209_says_that_it_did_not_wire_the_uart():
    """Un dessin incomplet DOIT se dire, sinon il se lit comme complet."""
    nl = _detecte(CODE_TMC2209)
    codes = [w.code for w in nl.warnings]
    assert "stepper_uart_not_wired" in codes, codes


def test_no_stepper_driver_leaves_a_phantom_box():
    """Le fantome du L298N, applique aux trois : leur `#include` ne doit plus
    poser de boite placeholder a cote du driver cable."""
    for code in (CODE_DRV8825, CODE_STSPIN220, CODE_TMC2209):
        nl = _pipeline(code)
        fantomes = [c for c in nl.components
                    if c.attributes.get("unrecognized")]
        assert fantomes == [], [(c.ref, c.type) for c in fantomes]


def test_each_driver_gets_exactly_one_nema17_after_inference():
    """Meme regle que l'A4988 : un driver pas-a-pas implique un moteur, et
    ses bobines rejoignent les sorties du driver par des nets internes."""
    from ui.wiring import inference
    bobines = {
        "drv8825": ("1A", "1B", "2A", "2B"),
        "stspin220": ("OUTA1", "OUTA2", "OUTB1", "OUTB2"),
        "tmc2209": ("OUT1A", "OUT1B", "OUT2A", "OUT2B"),
    }
    for type_id, code in (("drv8825", CODE_DRV8825),
                          ("stspin220", CODE_STSPIN220),
                          ("tmc2209", CODE_TMC2209)):
        nl = _detecte(code)
        inference.apply_rules(nl)
        nemas = [c for c in nl.components if c.type == "nema17"]
        assert len(nemas) == 1, (type_id,
                                 [(c.ref, c.type) for c in nl.components])
        p = _broches(nl, type_id)
        for nom in bobines[type_id]:
            assert p[nom].startswith("NET_"), (type_id, nom, p[nom])


def test_the_a4988_path_is_untouched():
    """Contre-epreuve : le chemin qui servait de modele n'a pas bouge."""
    code = ("#include <AccelStepper.h>\n"
            "AccelStepper stepper(AccelStepper::DRIVER, 2, 3);\n"
            "void setup(){ stepper.setMaxSpeed(1000); }\n"
            "void loop(){ stepper.run(); }\n")
    p = _broches(_detecte(code), "a4988")
    assert p["STEP"] == "D2" and p["DIR"] == "D3", p


TESTS = [
    test_drv8825_begin_has_DIR_FIRST_then_STEP,
    test_drv8825_electrical_defaults_match_the_a4988_block,
    test_stspin220_reads_step_and_dir_from_its_constructor,
    test_stspin220_mode_pins_only_when_the_constructor_gives_them,
    test_tmc2209_invents_no_control_pin,
    test_tmc2209_says_that_it_did_not_wire_the_uart,
    test_no_stepper_driver_leaves_a_phantom_box,
    test_each_driver_gets_exactly_one_nema17_after_inference,
    test_the_a4988_path_is_untouched,
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
