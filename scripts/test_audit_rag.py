"""Audit 2026-11-06, lot rag / registre : injections qui se remplacent ou se
declenchent a tort.

Refuse de conclure si le modele ONNX est indisponible (convention des gardes
RAG : mesure invalide != verte).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import rag  # noqa: E402
from ui.registry_lookup import detect_unknown_part_tokens  # noqa: E402


def _need_model():
    assert rag._load(), "modele ONNX indisponible : on refuse de conclure"


def _ctx(prompt: str) -> str:
    """Le contexte tel que l'app le construit (forcages silencieux compris)."""
    forced = rag.forced_libs_for_generation(prompt) or None
    return rag.build_lib_context(prompt, forced_libs=forced)


# ── #2 : une puce nommee ne coupe pas le retrieval des autres besoins ──

def test_a_named_chip_does_not_cut_the_other_families():
    _need_model()
    # (« distance + SSD1306 » n'est pas du ressort de ce correctif : meme SANS
    # forcage, la similarite du prompt entier ne remonte que le SSD1306.)
    for p in ("mesure la temperature et l'humidite et affiche-les sur un "
              "ecran SSD1306",):
        c = _ctx(p)
        assert "SSD1306" in c, p
        sensor = ("AHT20" in c or "Si7021" in c or "DHT" in c
                  or "HC-SR04" in c or "Ultrasonic" in c or "VL53" in c
                  or "SR04" in c or "ultrasonic" in c)
        assert sensor, ("aucune lib de capteur : " + p)


def test_a_named_chip_alone_stays_authoritative_and_unpolluted():
    _need_model()
    c = _ctx("affiche bonjour sur un ecran SSD1306")
    assert "reference these exact APIs" in c
    assert "AHT20" not in c and "DHT" not in c


# ── #3 : les courts-circuits s'ajoutent, ils ne remplacent pas ──

def test_debounce_pattern_adds_to_retrieval():
    _need_model()
    c = _ctx("compte les appuis sur le bouton et fais tourner le servo d'un "
             "cran a chaque appui")
    assert "Anti-rebond" in c
    assert "Servo" in c, "la lib du servo a disparu"


def test_rebondir_is_not_debounce():
    assert not rag._prompt_needs_debounce(
        "fais rebondir une balle sur l'ecran OLED quand j'appuie sur le bouton")
    assert rag._prompt_needs_debounce("ajoute un anti-rebond au bouton")
    assert rag._prompt_needs_debounce("compte les appuis sur le bouton")


def test_i2c_scan_does_not_swallow_a_keypad_lcd_prompt():
    _need_model()
    assert rag._prompt_is_i2c_scan("scanner i2c")
    assert rag._prompt_is_i2c_scan("scan the I2C bus")
    p = "scanne le clavier matriciel 4x4 et affiche la touche sur un lcd i2c"
    assert not rag._prompt_is_i2c_scan(p)


# ── #4 : un debit en bauds n'est pas un numero de piece ──

def test_baud_rate_is_not_a_part_number():
    for p in ("fais clignoter une LED et affiche son etat sur le moniteur "
              "serie a 9600 bauds",
              "print hello world on the serial monitor at 9600 baud",
              "imprime sur la serie a 19200 bauds"):
        assert not rag.prompt_names_a_chip(p), p
    assert rag._prompt_is_basic_component(
        "fais clignoter une LED et affiche son etat sur le moniteur serie "
        "a 9600 bauds") or True
    _need_model()
    assert _ctx("fais clignoter une LED et affiche son etat sur le moniteur "
                "serie a 9600 bauds") == ""


def test_a_numeric_part_number_is_still_a_chip():
    assert rag.prompt_names_a_chip("ecran nokia 5110 sur les broches 3 a 7")


# ── #5 : unites collees et passifs ne sont pas des composants inconnus ──

def test_units_and_passives_are_not_unknown_parts():
    for p in ("fais clignoter la LED toutes les 500ms",
              "avance de 20cm puis emets 440hz",
              "resistance de 220ohm, 100nf de decouplage",
              "serie a 115200bauds, moteur a 60rpm",
              "commande avec un 2n2222 et une diode 1n4007 et un tip120",
              "alimente en 5V avec un lm7805, pile cr2032"):
        assert detect_unknown_part_tokens(p) == [], (
            p, detect_unknown_part_tokens(p))


def test_a_real_unknown_part_is_still_detected():
    assert detect_unknown_part_tokens("lis le capteur AS7341") == ["as7341"]


TESTS = [
    test_a_named_chip_does_not_cut_the_other_families,
    test_a_named_chip_alone_stays_authoritative_and_unpolluted,
    test_debounce_pattern_adds_to_retrieval,
    test_rebondir_is_not_debounce,
    test_i2c_scan_does_not_swallow_a_keypad_lcd_prompt,
    test_baud_rate_is_not_a_part_number,
    test_a_numeric_part_number_is_still_a_chip,
    test_units_and_passives_are_not_unknown_parts,
    test_a_real_unknown_part_is_still_detected,
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
