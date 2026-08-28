"""Garde-fou des groupes de clarification multi-familles (ui/clarification_groups).

Forcing function couche 2 (cf. test_disambiguation_candidates_have_keywords,
test_rag_corpus_sync) :
  - DUR : tout `corpus_id` cité par un groupe EXISTE dans corpus.json (anti-typo /
    anti-suppression — un id absent = candidat silencieusement ignoré).
  - DUR : groupes bien formés (clés uniques, ≥1 candidat, labels non vides).
  - DUR : `match_group` route correctement quelques prompts repères + respecte
    l'ordre spécifique→général (7 segments ≠ écran, co2 ≠ qualité d'air).
  - SOFT (info) : liste les composants des catégories ambiguës (Display/Sensors)
    NON couverts par un groupe → rappel « ce composant devrait peut-être
    rejoindre/former un groupe ».

Pur : ni Qt ni ONNX. Tourne avec la suite de tests à chaque modif des groupes.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_CORPUS = ROOT / "assets" / "rag" / "corpus.json"
_AMBIGUOUS_CATEGORIES = {"Display", "Sensors", "Sensor"}


def _corpus_ids() -> set[str]:
    corpus = json.load(_CORPUS.open(encoding="utf-8"))
    return {e["id"] for e in corpus if e.get("id")}


def test_all_candidate_ids_exist_in_corpus():
    from ui.clarification_groups import CLARIFY_GROUPS
    ids = _corpus_ids()
    missing = []
    for g in CLARIFY_GROUPS:
        for c in g.candidates:
            if c.corpus_id not in ids:
                missing.append(f"{g.key}:{c.corpus_id}")
    assert not missing, (
        f"corpus_id cités mais ABSENTS de corpus.json : {missing} "
        f"(typo, ou entrée à ajouter ; lance build_rag_embeddings.py après ajout)"
    )
    print(f"  OK — tous les corpus_id des groupes existent ({len(ids)} entrées corpus)")


def test_groups_wellformed():
    from ui.clarification_groups import CLARIFY_GROUPS
    keys = [g.key for g in CLARIFY_GROUPS]
    assert len(keys) == len(set(keys)), f"clés de groupe dupliquées : {keys}"
    for g in CLARIFY_GROUPS:
        assert g.candidates, f"groupe '{g.key}' sans candidat"
        assert g.keywords, f"groupe '{g.key}' sans mot-clé"
        for c in g.candidates:
            assert c.corpus_id.strip(), f"candidat sans corpus_id dans '{g.key}'"
            assert c.label.strip(), f"candidat '{c.corpus_id}' sans label dans '{g.key}'"
    print(f"  OK — {len(keys)} groupes bien formés")


def test_match_group_routing():
    from ui.clarification_groups import match_group
    cases = {
        "lis la température": "temperature",
        "affiche sur un écran oled": "ecran",
        "branche une matrice de led": "matrice_led",
        "un afficheur 7 segments": "sept_segments",   # PAS ecran (ordre)
        "mesure le co2 ambiant": "co2",                # PAS air_quality (ordre)
        "mesure la distance": "distance",
        "lis l'humidité": "humidite",
        "lecteur rfid": "rfid",
        "pilote un moteur en i2c": "moteur_i2c",   # I2C motor driver exception
        "deux moteurs DC en i2c": "moteur_i2c",            # co-occurrence (no phrase)
        "fais tourner mon moteur avec le shield grove": "moteur_i2c",  # motor + grove
    }
    for prompt, expected in cases.items():
        g = match_group(prompt)
        assert g is not None and g.key == expected, (
            f"{prompt!r} -> {None if g is None else g.key} (attendu {expected})"
        )
    # A prompt with no ambiguous family matches no group.
    assert match_group("fais clignoter une led") is None
    assert match_group("fais tourner un moteur dc") is None  # GPIO motor, no I2C/Grove cue
    assert match_group("") is None
    print(f"  OK — match_group route {len(cases)} prompts repères + ordre respecté")


def test_basic_no_lib_guard():
    """Composants de base (LED simple, bouton, buzzer…) ne déclenchent pas la modale.

    La garde _prompt_is_basic_component doit intercepter avant le filet auto
    (étape 2) — indépendamment de la disponibilité du modèle ONNX."""
    from ui.rag import _prompt_is_basic_component, detect_lib_ambiguity

    # Positive cases: components without a lib → active guard → detect returns None.
    basic = [
        "fais clignoter une LED",
        "allume une led",
        "branche des leds",
        "allume un bouton",
        "appuie sur un button",
        "fais biper un buzzer",
        "branche un potentiomètre",
        "ajoute une résistance",
        "conecta un led",         # ES
        "fai lampeggiare un led", # IT
    ]
    for prompt in basic:
        assert _prompt_is_basic_component(prompt), \
            f"{prompt!r} → garde inactive (attendu True)"
        assert detect_lib_ambiguity(prompt) is None, \
            f"{prompt!r} → detect_lib_ambiguity != None (attendu None)"

    # Negative cases: complex variants -> guard inactive.
    complex_ = [
        "bande de led",
        "ruban led",
        "anneau de leds",
        "led ring",
        "matrice de leds",
        "neopixel ring",
    ]
    for prompt in complex_:
        assert not _prompt_is_basic_component(prompt), \
            f"{prompt!r} → garde active à tort (attendu False)"

    print(f"  OK — {len(basic)} cas de base supprimés, {len(complex_)} variants complexes non supprimés")


def test_match_all_groups_multifamily():
    """match_all_groups renvoie TOUTES les familles d'un prompt (vs match_group)."""
    from ui.clarification_groups import match_all_groups, match_group
    p = "mesure la température avec un capteur et affiche sur un écran"
    keys = [g.key for g in match_all_groups(p)]
    assert "temperature" in keys and "ecran" in keys, \
        f"température + écran attendus, obtenu {keys}"
    # match_group (singular) returns only the first (temperature, declared first).
    assert match_group(p).key == "temperature"
    print(f"  OK — match_all_groups({p!r}) -> {keys}")


def test_detect_lib_ambiguities_multifamily():
    """detect_lib_ambiguities clarifie 2 familles distinctes (température + écran)
    mais une seule pour un concept à mots-clés chevauchants (co2 ⊂ air_quality)."""
    from ui.rag import detect_lib_ambiguities, detect_lib_ambiguity

    # 2 DISJOINT families -> 2 clarifications, none auto-forced.
    to_clarify, auto = detect_lib_ambiguities("mesure la température et affiche sur un oled")
    assert len(to_clarify) == 2, f"2 familles attendues, obtenu {len(to_clarify)}"
    assert not auto, f"aucune puce nommée -> auto-forcées vide, obtenu {auto}"
    ids = [{c.get('id') for c in fam} for fam in to_clarify]
    assert ids[0] & {"dht-sensor-library", "dallas-temperature"}, "1re famille = température"
    assert ids[1] & {"adafruit-ssd1306", "sh1106", "liquidcrystal-i2c"}, "2e famille = écran"
    assert not (ids[0] & ids[1]), "familles disjointes"

    # co2 matche aussi air_quality (chevauchement) -> UNE seule famille.
    co2_clarify, _ = detect_lib_ambiguities("mesure le co2 ambiant")
    assert len(co2_clarify) == 1, f"co2 = 1 seule famille (pas de re-clarif), obtenu {len(co2_clarify)}"

    # Compat: the singular returns the 1st family to clarify.
    first = detect_lib_ambiguity("mesure la température et affiche sur un oled")
    assert first is not None and (
        {c.get('id') for c in first} & {"dht-sensor-library", "dallas-temperature"}), \
        "detect_lib_ambiguity = 1re famille (température)"
    print("  OK — multi-familles : température+écran=2, co2=1, singulier=1re")


def test_named_chip_resolves_family_keeps_others():
    """Nommer la puce d'une famille la RÉSOUT (auto-forcée, pas de modale) sans
    empêcher de clarifier les autres familles (VMA335 → BME280 + écran clarifié)."""
    from ui.rag import detect_lib_ambiguities

    # VMA335 = BME280 alias: temperature auto-resolved, screen to clarify.
    to_clarify, auto = detect_lib_ambiguities(
        "mesure la température avec un vma335 et affiche sur un oled")
    auto_ids = {c.get("id") for c in auto}
    assert "adafruit-bme280" in auto_ids, f"vma335 -> BME280 auto-forcé, obtenu {auto_ids}"
    assert len(to_clarify) == 1, f"seul l'écran reste à clarifier, obtenu {len(to_clarify)}"
    assert {c.get('id') for c in to_clarify[0]} & {"adafruit-ssd1306", "sh1106"}, \
        "la famille restante = écran"

    # BME280 named directly (no screen): auto-forced, no modal.
    to_clarify2, auto2 = detect_lib_ambiguities("mesure la température avec un bme280")
    assert not to_clarify2 and {c.get("id") for c in auto2} == {"adafruit-bme280"}, \
        "bme280 nommé seul -> auto-forcé, pas de modale"
    print("  OK — VMA335/BME280 nommé -> température auto-forcée, écran clarifié")


def test_named_chip_not_falsely_grouped():
    """Une puce nommée ne doit pas déclencher la modale (garde lexicale)."""
    # match_group can match the generic word, but detect_lib_ambiguity cuts
    # AVANT via prompt_names_a_chip. On teste ce comportement de bout en bout.
    from ui.rag import detect_lib_ambiguity
    assert detect_lib_ambiguity("utilise un capteur ssd1306") is None, \
        "ssd1306 nommé -> pas de modale"
    assert detect_lib_ambiguity("capteur dht22") is None, "dht22 nommé -> pas de modale"
    print("  OK — puce nommée (ssd1306/dht22) -> pas de clarification")


def test_coverage_info():
    """SOFT : signale les composants Display/Sensors non couverts par un groupe."""
    from ui.clarification_groups import CLARIFY_GROUPS
    covered = {c.corpus_id for g in CLARIFY_GROUPS for c in g.candidates}
    corpus = json.load(_CORPUS.open(encoding="utf-8"))
    uncovered = sorted(
        e["id"] for e in corpus
        if e.get("category") in _AMBIGUOUS_CATEGORIES and e.get("id") not in covered
    )
    if uncovered:
        print("  INFO — composants Display/Sensors hors groupe (ok si vraiment "
              "uniques en leur genre, sinon créer/compléter un groupe) :")
        for cid in uncovered:
            print(f"        - {cid}")
    else:
        print("  INFO — toutes les entrées Display/Sensors sont couvertes")


def test_functional_taxonomy_helpers():
    from ui.clarification_groups import (
        functions_of_component, candidates_of_function, functions_in_prompt)
    # Le netlist travaille en TYPE WIRING (svg_type), ex 'oled_ssd1306'.
    assert "ecran" in functions_of_component("oled_ssd1306")
    # Robustesse : le corpus_id doit aussi matcher.
    assert "ecran" in functions_of_component("adafruit-ssd1306")
    # Appartenance MULTIPLE (le meme composant sert plusieurs fonctions).
    fbme = functions_of_component("bme280")   # svg_type de adafruit-bme280
    assert {"temperature", "pression", "humidite"} <= fbme, fbme
    assert functions_of_component("adafruit-bme280") == fbme  # corpus_id == meme resultat
    # Candidats d'une fonction = TYPES WIRING.
    screens = candidates_of_function("ecran")
    assert "oled_ssd1306" in screens and "sh1106" in screens and len(screens) >= 5, screens
    # Fonction inconnue -> vide.
    assert functions_of_component("led") == set()
    assert candidates_of_function("inexistant") == []
    # Depuis le prompt.
    assert functions_in_prompt("affiche du texte sur un ecran") == ["ecran"]
    fp = functions_in_prompt("mesure la temperature et affiche sur un ecran")
    assert "temperature" in fp and "ecran" in fp, fp
    print(f"  OK - taxonomie fonctionnelle (bme280 -> {sorted(fbme)})")


TESTS = [
    test_all_candidate_ids_exist_in_corpus,
    test_groups_wellformed,
    test_match_group_routing,
    test_match_all_groups_multifamily,
    test_detect_lib_ambiguities_multifamily,
    test_named_chip_resolves_family_keeps_others,
    test_basic_no_lib_guard,
    test_named_chip_not_falsely_grouped,
    test_coverage_info,
    test_functional_taxonomy_helpers,
]


def main():
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
