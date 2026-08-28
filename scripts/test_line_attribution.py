"""Tests de l'attribution lignes->fonctionnalite (TODO #29).

Partie 1 : assemble_with_map (carte exacte de l'assembleur).
Partie 2 (Task 2) : transfer_map / match_contributions / single_feature_map.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.feature_model import Feature, FeatureFunction
from ui.generation.assembler import assemble, assemble_with_map
from ui.generation.line_attribution import (
    normalize, is_trivial, transfer_map, match_contributions,
    single_feature_map,
)
from ui.generation import line_attribution as _la


def _led():
    return Feature(id="f1", prompt="led", summary="LED",
                   includes=["#include <Arduino.h>"],
                   global_lines=["const int PIN_LED = 5;"],
                   setup_lines=["pinMode(PIN_LED, OUTPUT);"],
                   loop_lines=["digitalWrite(PIN_LED, HIGH);", "delay(500);"])


def _buzzer():
    return Feature(id="f2", prompt="buzzer", summary="Buzzer",
                   includes=["#include <Arduino.h>"],   # dupliqué -> dédup
                   global_lines=["const int PIN_BUZZER = 9;"],
                   setup_lines=["pinMode(PIN_BUZZER, OUTPUT);"],
                   loop_lines=["tone(PIN_BUZZER, 440);"],
                   functions=[FeatureFunction(
                       name="beep",
                       code="void beep() {\n  tone(PIN_BUZZER, 880);\n}")])


def test_assemble_unchanged_output():
    # assemble() reste byte-identique a l'existant (wrapper).
    feats = [_led(), _buzzer()]
    code, _ = assemble_with_map(feats)
    assert assemble(feats) == code


def test_map_length_matches_lines():
    code, owners = assemble_with_map([_led(), _buzzer()])
    assert len(owners) == len(code.split("\n")), (len(owners), len(code.split("\n")))


def test_owners_by_section():
    code, owners = assemble_with_map([_led(), _buzzer()])
    lines = code.split("\n")
    def owner_of(snippet):
        for i, ln in enumerate(lines):
            if snippet in ln:
                return owners[i]
        raise AssertionError(f"{snippet!r} absent de l'assemblage")
    assert owner_of("PIN_LED = 5") == "f1"
    assert owner_of("PIN_BUZZER = 9") == "f2"
    assert owner_of("pinMode(PIN_LED") == "f1"
    assert owner_of("pinMode(PIN_BUZZER") == "f2"
    assert owner_of("digitalWrite(PIN_LED") == "f1"
    assert owner_of("tone(PIN_BUZZER, 440)") == "f2"
    assert owner_of("void beep()") == "f2"          # corps de fonction entier
    assert owner_of("tone(PIN_BUZZER, 880)") == "f2"


def test_scaffolding_is_unowned():
    code, owners = assemble_with_map([_led()])
    lines = code.split("\n")
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s in ("", "}") or s.startswith("void setup()") or s.startswith("void loop()"):
            assert owners[i] is None, f"ligne {i} {ln!r} devrait etre None"


def test_dedup_include_owned_by_first_emitter():
    code, owners = assemble_with_map([_led(), _buzzer()])
    lines = code.split("\n")
    idxs = [i for i, ln in enumerate(lines) if "#include <Arduino.h>" in ln]
    assert len(idxs) == 1                     # dédupliqué
    assert owners[idxs[0]] == "f1"            # 1ere feature émettrice


def test_trivial_and_scaffold_lines():
    for ln in ("", "   ", "}", "  } ", "{", "};", "void setup() {", "  void loop()  {"):
        assert is_trivial(ln), ln
    for ln in ("delay(500);", "#include <X.h>", "int a = 1;", "// commentaire"):
        assert not is_trivial(ln), ln


def test_transfer_preserves_untouched_regions():
    old = ["int a;", "int b;", "int c;", "int d;"]
    old_map = ["f1", "f1", "f2", "f2"]
    # Une ligne insérée au milieu + une ligne modifiée (c -> cc).
    new = ["int a;", "int nouveau;", "int b;", "int cc;", "int d;"]
    got = transfer_map(old, old_map, new)
    assert got == ["f1", None, "f1", None, "f2"], got


def test_match_sequences_reattributes():
    f1 = Feature(id="f1", prompt="led",
                 loop_lines=["digitalWrite(PIN_LED, HIGH);", "delay(500);"])
    lines = ["void loop() {",
             "  digitalWrite(PIN_LED, HIGH);",
             "  delay(500);",
             "}"]
    got = match_contributions(lines, [f1], [None] * 4)
    assert got == [None, "f1", "f1", None], got


def test_match_ambiguous_singleton_not_attributed():
    # "delay(500);" présent dans DEUX features -> jamais attribué seul.
    f1 = Feature(id="f1", prompt="a", loop_lines=["delay(500);"])
    f2 = Feature(id="f2", prompt="b", loop_lines=["delay(500);"])
    lines = ["delay(500);"]
    got = match_contributions(lines, [f1, f2], [None])
    assert got == [None], got


def test_match_unique_singleton_attributed():
    f1 = Feature(id="f1", prompt="a", global_lines=["const int PIN_X = 7;"])
    lines = ["const int PIN_X = 7;"]
    got = match_contributions(lines, [f1], [None])
    assert got == ["f1"], got


def test_fuzzy_behind_kill_switch():
    # Cas littéral-only : seul le nombre diffère (mêmes identifiants), donc
    # éligible au fuzzy -> ne matche que si le flag est actif.
    f1 = Feature(id="f1", prompt="a", loop_lines=["delay(500);"])
    lines = ["delay(250);"]                      # proche mais != exact
    old_flag = _la._FUZZY_RESEED_ENABLED
    try:
        _la._FUZZY_RESEED_ENABLED = False
        assert match_contributions(lines, [f1], [None]) == [None]
        _la._FUZZY_RESEED_ENABLED = True
        assert match_contributions(lines, [f1], [None]) == ["f1"]
    finally:
        _la._FUZZY_RESEED_ENABLED = old_flag


def test_fuzzy_never_crosses_identifiers():
    # Même API (digitalWrite), broche différente (PIN_LED vs PIN_BUZZER) ->
    # identifiants différents -> jamais attribué, même flag ON (garde revue
    # finale #29 : la classe "même API, autre broche" est éliminée).
    f1 = Feature(id="f1", prompt="led",
                 loop_lines=["digitalWrite(PIN_LED, HIGH);"])
    f2 = Feature(id="f2", prompt="buzzer", loop_lines=["tone(PIN_BUZZER, 440);"])
    lines = ["digitalWrite(PIN_BUZZER, HIGH);"]
    assert _la._FUZZY_RESEED_ENABLED
    assert match_contributions(lines, [f1, f2], [None]) == [None]


def test_single_feature_map_marks_all_but_scaffolding():
    code = "int a;\n\nvoid setup() {\n  pinMode(1, OUTPUT);\n}\n"
    got = single_feature_map(code, "f1")
    assert got == ["f1", None, None, "f1", None, None], got


TESTS = [test_assemble_unchanged_output, test_map_length_matches_lines,
         test_owners_by_section, test_scaffolding_is_unowned,
         test_dedup_include_owned_by_first_emitter,
         test_trivial_and_scaffold_lines, test_transfer_preserves_untouched_regions,
         test_match_sequences_reattributes, test_match_ambiguous_singleton_not_attributed,
         test_match_unique_singleton_attributed, test_fuzzy_behind_kill_switch,
         test_fuzzy_never_crosses_identifiers,
         test_single_feature_map_marks_all_but_scaffolding]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t(); print("OK  ", t.__name__)
        except AssertionError as e:
            failed += 1; print("FAIL", t.__name__, e)
    print(f"\n{len(TESTS)-failed}/{len(TESTS)} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
