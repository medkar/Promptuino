"""Tests du gating des règles de génération (ui/ai_backends/codegen_rules.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.ai_backends.codegen_rules import (
    mentions_motor, build_wiring_addendum,
    _HARDWARE_RULE, _DISAMBIGUATION_RULE, _MOTOR_RULES,
)


# ── mentions_motor : vrais positifs (FR/EN/ES/IT + chips) ──────────────
def test_motor_fr():
    assert mentions_motor("fais tourner un moteur DC") is True

def test_motor_en():
    assert mentions_motor("spin a small motor") is True

def test_motor_it():
    assert mentions_motor("controlla un motore") is True

def test_motor_es():
    assert mentions_motor("controla los motores") is True

def test_motor_fan():
    assert mentions_motor("allume un ventilateur") is True

def test_motor_fan_en():
    assert mentions_motor("turn on the fan") is True

def test_motor_robot():
    assert mentions_motor("un robot qui avance") is True

def test_motor_stepper():
    assert mentions_motor("drive a stepper") is True

def test_motor_pas_a_pas():
    assert mentions_motor("un moteur pas a pas") is True

def test_motor_driver_chip():
    assert mentions_motor("avec un L298N") is True

def test_motor_accent_insensitive():
    assert mentions_motor("contrôle l'hélice") is True


# ── mentions_motor: true negatives + collisions to avoid ───────────────
def test_no_motor_ina():
    assert mentions_motor("lis le capteur INA3221") is False

def test_no_motor_oled():
    assert mentions_motor("affiche un smiley sur l'écran OLED") is False

def test_no_motor_led():
    assert mentions_motor("fais clignoter une LED sur D13") is False

def test_no_motor_empty():
    assert mentions_motor("") is False

def test_no_motor_none_like():
    assert mentions_motor(None) is False

def test_no_motor_collision_car_fr():
    # "car" (FR conjunction) must NOT trigger (not in the lexicon)
    assert mentions_motor("allume la LED car il fait nuit") is False

def test_no_motor_collision_coche():
    # "coche" (FR: checkbox) must NOT trigger
    assert mentions_motor("coche la case puis lis le bouton") is False

def test_no_motor_substring_enfant():
    # "fan" must NOT match inside "enfant" (word boundaries)
    assert mentions_motor("un jeu pour enfant") is False


# ── build_wiring_addendum : composition ────────────────────────────────
def test_addendum_always_has_p1_p2():
    out = build_wiring_addendum("lis le capteur INA3221")
    assert _HARDWARE_RULE in out
    assert _DISAMBIGUATION_RULE in out

def test_addendum_excludes_p3_when_no_motor():
    out = build_wiring_addendum("lis le capteur INA3221")
    assert "MOTOR RULES START" not in out
    assert _MOTOR_RULES not in out

def test_addendum_includes_p3_when_motor():
    # ⚠️ Le prompt d'origine nommait « un L298N » : depuis la scission du
    # 2026-08-31, nommer un driver A BIBLIOTHEQUE selectionne la variante
    # `_MOTOR_RULES_LIB` (testee plus bas). Ce test-ci garde le contrat
    # historique sur un prompt moteur SANS lib nommee.
    out = build_wiring_addendum("fais tourner un moteur DC")
    assert "MOTOR RULES START" in out
    assert _MOTOR_RULES in out

def test_addendum_p3_last():
    # P3 doit venir APRÈS P1 et P2.
    out = build_wiring_addendum("moteur")
    assert out.index(_HARDWARE_RULE) < out.index(_MOTOR_RULES)
    assert out.index(_DISAMBIGUATION_RULE) < out.index(_MOTOR_RULES)


# ── P3 a deux variantes : la lib pilote quand elle est nommee ───────────
# Mesure A/B du 2026-08-31 (QA AB2 du #82, gemma4:e2b, 6 generations/bras) :
# sans bloc MOTOR 0/6 chimeres, avec lui 3/6 -- le pattern broches-nues
# contredisait l'API de la lib L298N injectee imperativement, et le modele
# epissait les deux. Ces tests exigent le prompt BRUT (le gating de l'app
# passe rules_prompt=prompt brut, precisement pour ca).

def test_a_named_lib_driver_swaps_the_pattern_for_the_library():
    a = build_wiring_addendum("2 moteurs DC avec un L298N")
    assert "LIBRARY context" in a, a[-400:]
    assert "void setMotor" not in a, (
        "le helper broches-nues ne doit plus etre ordonne quand la lib "
        "est injectee")
    # La PROSE (nommer le driver, jamais << to motor pin >>) vaut dans les
    # deux mondes et reste.
    assert "name the driver chip" in a
    assert "MOTOR RULES START" in a and "MOTOR RULES END" in a


def test_a_generic_motor_prompt_keeps_the_bare_pattern():
    b = build_wiring_addendum("deux moteurs DC")
    assert "void setMotor" in b
    assert "LIBRARY context" not in b


def test_a_driver_without_a_corpus_lib_keeps_the_bare_pattern():
    """La distinction fine : « TB6612 » nomme un driver, mais son entree
    corpus n'a PAS de bibliotheque -- le pattern broches-nues reste le bon,
    il n'y a aucune API a contredire."""
    c = build_wiring_addendum("un moteur avec un TB6612")
    assert "void setMotor" in c
    assert "LIBRARY context" not in c


TESTS = [
    test_motor_fr, test_motor_en, test_motor_it, test_motor_es,
    test_motor_fan, test_motor_fan_en, test_motor_robot, test_motor_stepper,
    test_motor_pas_a_pas, test_motor_driver_chip, test_motor_accent_insensitive,
    test_no_motor_ina, test_no_motor_oled, test_no_motor_led, test_no_motor_empty,
    test_no_motor_none_like, test_no_motor_collision_car_fr,
    test_no_motor_collision_coche, test_no_motor_substring_enfant,
    test_addendum_always_has_p1_p2, test_addendum_excludes_p3_when_no_motor,
    test_addendum_includes_p3_when_motor, test_addendum_p3_last,
    test_a_named_lib_driver_swaps_the_pattern_for_the_library,
    test_a_generic_motor_prompt_keeps_the_bare_pattern,
    test_a_driver_without_a_corpus_lib_keeps_the_bare_pattern,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
