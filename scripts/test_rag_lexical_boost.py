"""Tests du boost lexical du RAG : un composant NOMMÉ explicitement dans le
prompt (token numéro-de-pièce, ex. INA3221) doit ressortir EN TÊTE, et le
relative_gate doit alors évacuer le bruit hors-sujet.

Régression du smoke test : « Mesure trois tensions avec un capteur INA3221 en
I2C » retrouvait OneWire + L293D (driver moteur !) DEVANT INA3221.

Charge le vrai modèle ONNX (~1-2 s)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.rag import retrieve_libs, _signature_tokens, build_lib_context


def test_named_ina3221_first_and_noise_dropped():
    r = retrieve_libs("Mesure trois tensions avec un capteur INA3221 en I2C.",
                      k=3, threshold=0.25)
    names = [l["name"] for l in r]
    assert names, "aucune lib retrouvée"
    assert "INA3221" in names[0], f"INA3221 pas en tête : {names}"
    assert "OneWire" not in names, f"bruit OneWire présent : {names}"
    assert "L293D" not in names, f"bruit L293D présent : {names}"


def test_named_dht11_first():
    r = retrieve_libs("affiche la temperature avec un capteur DHT11",
                      k=3, threshold=0.25)
    assert r and "DHT" in r[0]["name"], f"DHT pas en tête : {[l['name'] for l in r]}"


def test_named_l298n_first():
    r = retrieve_libs("pilote un moteur DC avec un L298N", k=3, threshold=0.25)
    assert r and r[0]["name"] == "L298N", f"L298N pas en tête : {[l['name'] for l in r]}"


def test_no_partnumber_does_not_crash():
    # Prompt with no part-number token: no boost, normal semantic retrieval.
    r = retrieve_libs("lis une valeur analogique simple", k=3, threshold=0.25)
    assert isinstance(r, list)


def test_signature_tokens_extracts_part_numbers():
    e = {"name": "Adafruit INA3221",
         "keywords": ["INA3221", "capteur de courant", "I2C 0x40 power monitor"]}
    toks = _signature_tokens(e)
    assert "ina3221" in toks          # part number
    assert "courant" not in toks      # generic word without digit → excluded
    assert "i2c" not in toks          # < 4 characters → excluded


def test_basic_component_injects_no_lib():
    # Basic component with no named chip (simple LED, button) -> NO lib
    # injected. Before: "led sur D10" retrieved DallasTemperature / PCF8574 /
    # MCP23017 (threshold 0.25 too low) polluting the generation prompt.
    assert build_lib_context("led sur d10") == ""
    assert build_lib_context("allume une led sur la broche 9") == ""
    assert build_lib_context("bouton sur d2") == ""


def test_basic_component_with_named_chip_still_retrieves():
    # A NAMED chip (DHT11) disables the guard -> lib is retrieved despite
    # the presence of the word "led".
    ctx = build_lib_context("fais clignoter une led et lis un capteur dht11")
    assert "DHT" in ctx, f"DHT absent du contexte : {ctx[:120]!r}"


def test_generic_prompt_injects_no_lib():
    """Code-gen injection floor (_CODEGEN_MIN_SCORE=0.50). A generic / no-lib
    prompt clusters as flat noise ~0.42-0.48 (no leader the relative_gate can
    drop) -> below the floor -> NOTHING injected. Before, the threshold (0.25)
    let this noise through and derailed the SLM."""
    for p in ("fais un chronometre sur le moniteur serie",
              "fais un compteur qui s'incremente chaque seconde"):
        assert build_lib_context(p) == "", f"lib parasite injectée pour : {p!r}"


def test_named_component_still_injected_above_floor():
    """A NAMED component (the contract) clears the floor and is injected."""
    assert "DHT" in build_lib_context("affiche la temperature avec un dht11")
    assert "SSD1306" in build_lib_context("affiche du texte sur un oled ssd1306")


def test_i2c_scanner_injects_wire_example():
    """I2C scanner: inject the canonical Wire (core lib) sketch deterministically
    so a weak SLM writes `#include <Wire.h>` instead of hallucinating the
    non-existent `#include <TwoWire.h>` (TwoWire = class IN Wire.h)."""
    for p in ("fais un scanner I2C", "fais un scanner d'adresses I2C"):
        ctx = build_lib_context(p)
        assert "Wire.h" in ctx, (p, ctx[:160])
        assert "Wire.begin" in ctx, (p, ctx[:160])
        assert "TwoWire.h" not in ctx, (p, ctx[:160])


def test_signature_tokens_skips_short_and_alpha():
    e = {"name": "DHT sensor library", "keywords": ["DHT22", "temperature", "d13"]}
    toks = _signature_tokens(e)
    assert "dht22" in toks
    assert "temperature" not in toks  # no digit
    assert "d13" not in toks          # < 4 characters


TESTS = [
    test_named_ina3221_first_and_noise_dropped,
    test_named_dht11_first,
    test_named_l298n_first,
    test_no_partnumber_does_not_crash,
    test_basic_component_injects_no_lib,
    test_basic_component_with_named_chip_still_retrieves,
    test_generic_prompt_injects_no_lib,
    test_named_component_still_injected_above_floor,
    test_i2c_scanner_injects_wire_example,
    test_signature_tokens_extracts_part_numbers,
    test_signature_tokens_skips_short_and_alpha,
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
