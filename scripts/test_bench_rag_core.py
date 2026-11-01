"""Tests for the pure core of the RAG bench -- NO ONNX model required.

The core is separated from `bench_rag.py` precisely for that: the model
weighs 470 MB, it is git-ignored, and classification logic that can only be
tested by loading it would end up tested by nobody.

Run: python scripts/test_bench_rag_core.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import bench_rag_core as core


def _case(**over):
    base = {"prompt": "lis un DHT22", "lang": "fr", "band": "named",
            "expect": ["dht-sensor-library"], "added": "2026-08-18",
            "source": "hand"}
    base.update(over)
    return base


def test_a_valid_case_has_no_problem():
    assert core.validate_case(_case()) == []


def test_lang_must_be_lowercase_and_known():
    assert core.validate_case(_case(lang="FR"))
    assert core.validate_case(_case(lang="de"))


def test_band_must_be_known():
    assert core.validate_case(_case(band="describe"))


def test_specificity_is_required_for_described_and_forbidden_elsewhere():
    assert core.validate_case(_case(band="described", expect=["servo"]))
    assert core.validate_case(
        _case(band="described", specificity="vague", expect=["servo"])) == []
    assert core.validate_case(_case(band="named", specificity="vague"))


def test_generic_may_have_an_empty_expect():
    assert core.validate_case(
        _case(band="generic", expect=[])) == []


def test_expect_must_be_a_list_not_a_string():
    assert core.validate_case(_case(expect="dht-sensor-library"))


def test_case_identity_is_prompt_and_lang():
    assert core.case_identity(_case()) == ("lis un DHT22", "fr")


def test_identity_separates_the_same_sentence_in_two_languages():
    a = _case(prompt="scanner i2c", lang="fr")
    b = _case(prompt="scanner i2c", lang="en")
    assert core.case_identity(a) != core.case_identity(b)


def test_load_battery_rejects_an_invalid_file_loudly():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.json"
        p.write_text(json.dumps([_case(lang="FR")]), encoding="utf-8")
        try:
            core.load_battery(p)
        except ValueError as e:
            assert "lang" in str(e), f"le message doit nommer le champ : {e}"
        else:
            raise AssertionError("une batterie invalide doit lever, pas passer")


def test_load_battery_reads_a_valid_file():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.json"
        p.write_text(json.dumps([_case()]), encoding="utf-8")
        assert len(core.load_battery(p)) == 1


_N2I = {"DHT sensor library": "dht-sensor-library",
        "Adafruit SSD1306": "adafruit-ssd1306"}

_CTX_DHT = """Relevant Arduino libraries — reference these exact APIs.

### DHT sensor library
Headers: `DHT.h`
Example:
```cpp
#include <DHT.h>
```"""


def test_injected_names_reads_the_block_titles():
    assert core.injected_names(_CTX_DHT) == ["DHT sensor library"]


def test_injected_names_on_an_empty_context():
    assert core.injected_names("") == []


def test_injected_names_finds_several_blocks():
    ctx = _CTX_DHT + "\n\n### Adafruit SSD1306\nHeaders: `x.h`\n"
    assert core.injected_names(ctx) == ["DHT sensor library", "Adafruit SSD1306"]


def test_a_name_absent_from_the_corpus_stays_itself():
    """The Wire case: `_WIRE_I2C_SCANNER_REF` has NO `id` key."""
    out = core.resolve_to_ids(["Wire (I2C core library)"], _N2I)
    assert out == ["Wire (I2C core library)"]


def test_resolve_to_ids_maps_known_names():
    assert core.resolve_to_ids(["DHT sensor library"], _N2I) == \
        ["dht-sensor-library"]


def test_classify_silent_on_empty_context():
    assert core.classify("", ["dht-sensor-library"], _N2I) == "silent"


def test_classify_correct_when_one_expected_id_is_injected():
    assert core.classify(_CTX_DHT, ["dht-sensor-library", "bme280"],
                         _N2I) == "correct"


def test_classify_wrong_when_none_of_the_expected_is_injected():
    assert core.classify(_CTX_DHT, ["bme280"], _N2I) == "wrong"


def test_any_injection_is_wrong_when_expect_is_empty():
    """Generic band: an empty `expect` means "nothing is acceptable"."""
    assert core.classify(_CTX_DHT, [], _N2I) == "wrong"
    assert core.classify("", [], _N2I) == "silent"


def test_silent_is_never_confused_with_wrong():
    """The project's doctrine: silence is acceptable, falsehood is not.

    A binary pass/fail would mix them together, and the number we watch
    (the WRONG injection rate) would become useless.
    """
    assert core.classify("", ["bme280"], _N2I) == "silent"
    assert core.classify(_CTX_DHT, ["bme280"], _N2I) == "wrong"


def test_resolve_expected_prefers_the_exact_id():
    """"sd" is contained in adafruit-ssd1306, sd and ssd1351 -- the exact match must win."""
    ids = ["adafruit-ssd1306", "sd", "ssd1351"]
    assert core.resolve_expected("sd", ids) == ["sd"]


def test_resolve_expected_falls_back_to_substring_matches():
    ids = ["dht-sensor-library", "bme280"]
    assert core.resolve_expected("dht", ids) == ["dht-sensor-library"]


def test_resolve_expected_raises_when_nothing_matches():
    try:
        core.resolve_expected("zzzz", ["bme280"])
    except ValueError:
        pass
    else:
        raise AssertionError(
            "une sous-chaine qui ne resout vers rien est une erreur de "
            "migration, pas un cas a ignorer")


BATTERY = ROOT / "scripts" / "bench_rag_prompts.json"


def test_the_real_battery_is_valid():
    """The real battery file loads and has the expected total case count."""
    cases = core.load_battery(BATTERY)
    assert len(cases) == 164, f"164 cas attendus, vu {len(cases)}"


def test_the_battery_covers_the_four_languages_evenly():
    """Each of the four languages carries the exact same number of cases."""
    from collections import Counter
    cases = core.load_battery(BATTERY)
    per_lang = Counter(c["lang"] for c in cases)
    assert set(per_lang) == set(core.LANGS), per_lang
    assert len(set(per_lang.values())) == 1, (
        f"les 4 langues doivent avoir le meme nombre de cas : {per_lang}")


def test_the_generic_band_covers_its_three_forms():
    """Three forms that the code handles DIFFERENTLY.

    Without all three, the band would only test a third of the behavior:
    the basic component is stopped by `_prompt_is_basic_component`, the I2C
    scanner by its own special case, and the component-less utility by the
    FLOOR ALONE — which makes it the form most sensitive to corpus growth.
    """
    cases = core.load_battery(BATTERY)
    generic = [c for c in cases if c["band"] == "generic"]
    assert len(generic) == 12, f"12 generiques attendus, vu {len(generic)}"
    avec_wire = [c for c in generic if c["expect"]]
    assert len(avec_wire) == 4, (
        "un scanner I2C par langue, seul generique dont l'injection est voulue")
    for c in avec_wire:
        assert c["expect"] == ["Wire (I2C core library)"], c


def test_every_named_case_expects_something():
    """A "named" case names a component; it must always expect a library."""
    cases = core.load_battery(BATTERY)
    for c in cases:
        if c["band"] == "named":
            assert c["expect"], f"cas nomme sans expect : {c['prompt']!r}"


def test_band_label_splits_described_by_specificity():
    assert core.band_label({"band": "generic"}) == "generic"
    assert core.band_label({"band": "named"}) == "named"
    assert core.band_label(
        {"band": "described", "specificity": "vague"}) == "described/vague"


def test_summarize_counts_the_three_outcomes_per_band_and_lang():
    results = [
        {"band_label": "named", "lang": "fr", "outcome": "correct"},
        {"band_label": "named", "lang": "fr", "outcome": "wrong"},
        {"band_label": "named", "lang": "en", "outcome": "correct"},
        {"band_label": "generic", "lang": "fr", "outcome": "silent"},
    ]
    s = core.summarize(results)
    assert s["named"]["_all"] == {"correct": 2, "silent": 0, "wrong": 1}
    assert s["named"]["fr"] == {"correct": 1, "silent": 0, "wrong": 1}
    assert s["generic"]["_all"] == {"correct": 0, "silent": 1, "wrong": 0}


def test_summarize_is_empty_but_well_formed_on_no_results():
    assert core.summarize([]) == {}


def test_battery_drift_reports_additions_and_removals():
    base = [("a", "fr"), ("b", "fr")]
    cur = [("b", "fr"), ("c", "en")]
    ajouts, retraits = core.battery_drift(base, cur)
    assert ajouts == [("c", "en")]
    assert retraits == [("a", "fr")]


def test_battery_drift_is_silent_when_nothing_moved():
    ids = [("a", "fr")]
    assert core.battery_drift(ids, list(ids)) == ([], [])


def test_a_removal_is_reported_not_hidden():
    """Removing an inconvenient prompt is the cheat the bench must surface."""
    ajouts, retraits = core.battery_drift([("a", "fr"), ("b", "fr")],
                                          [("a", "fr")])
    assert retraits == [("b", "fr")]


def test_format_deltas_marks_a_worsening_wrong_count():
    base = {"named": {"_all": {"correct": 10, "silent": 0, "wrong": 0}}}
    cur = {"named": {"_all": {"correct": 8, "silent": 0, "wrong": 2}}}
    lignes = "\n".join(core.format_deltas(cur, base))
    assert "+2" in lignes, lignes
    assert "⚠" in lignes, "une hausse des injections FAUSSES doit etre signalee"


def test_format_deltas_is_quiet_when_nothing_changed():
    s = {"named": {"_all": {"correct": 10, "silent": 0, "wrong": 0}}}
    lignes = "\n".join(core.format_deltas(s, dict(s)))
    assert "⚠" not in lignes


def test_check_baseline_schema_rejects_a_baseline_without_a_version():
    try:
        core.check_baseline_schema({"cases": []})
    except ValueError as e:
        assert "schema_version" in str(e), e
    else:
        raise AssertionError(
            "une reference sans schema_version doit etre refusee, pas lue "
            "comme si elle avait la forme actuelle")


def test_check_baseline_schema_rejects_a_stale_version():
    try:
        core.check_baseline_schema({"schema_version": 1})
    except ValueError:
        pass
    else:
        raise AssertionError("schema_version=1 est perime, doit lever")


def test_check_baseline_schema_accepts_the_current_version():
    core.check_baseline_schema({"schema_version": core.SCHEMA_VERSION})


def test_common_identities_is_the_intersection():
    a = [("x", "fr"), ("y", "en")]
    b = [("y", "en"), ("z", "it")]
    assert core.common_identities(a, b) == {("y", "en")}


def test_restrict_to_common_drops_cases_outside_the_set():
    results = [
        {"prompt": "a", "lang": "fr", "band_label": "named", "outcome": "correct"},
        {"prompt": "b", "lang": "fr", "band_label": "named", "outcome": "wrong"},
    ]
    kept = core.restrict_to_common(results, {("a", "fr")})
    assert kept == [results[0]]


def test_deltas_restricted_to_common_cases_do_not_reward_deleting_a_wrong_case():
    """The cheat C1 exists to close: dropping a case that used to be `wrong`
    must not read as an improvement.

    Without restricting to the intersection, comparing raw totals across two
    different populations reports "wrong -1" -- an improvement manufactured
    by deleting the inconvenient case. Restricted to the surviving common
    case, the delta must read `(=)`, and the band that lost its only case
    must not print a fabricated "0 -> 0" line either.
    """
    baseline_results = [
        {"prompt": "sonde bruit", "lang": "fr", "band_label": "generic",
         "outcome": "wrong"},
        {"prompt": "lis un DHT22", "lang": "fr", "band_label": "named",
         "outcome": "correct"},
    ]
    current_results = [
        {"prompt": "lis un DHT22", "lang": "fr", "band_label": "named",
         "outcome": "correct"},
    ]

    # The naive comparison DOES show a fake improvement -- this is the bug
    # C1 fixes, reproduced here so the test bites before the fix exists.
    naive = "\n".join(core.format_deltas(
        core.summarize(current_results), core.summarize(baseline_results)))
    assert "-1" in naive, (
        "ce test doit d'abord reproduire la triche qu'il verifie ensuite "
        "corrigee")

    common = core.common_identities(
        [(r["prompt"], r["lang"]) for r in baseline_results],
        [(r["prompt"], r["lang"]) for r in current_results])
    restricted = "\n".join(core.format_deltas(
        core.summarize(core.restrict_to_common(current_results, common)),
        core.summarize(core.restrict_to_common(baseline_results, common))))
    assert "-1" not in restricted, restricted
    assert "generic" not in restricted, (
        "le cas retire ne doit laisser AUCUNE trace, meme un faux (=)")


def test_max_ceiling_restricts_to_the_given_identities():
    by_case = {("a", "fr"): 0.5, ("b", "fr"): 0.9}
    assert core.max_ceiling(by_case, {("a", "fr")}) == 0.5


def test_max_ceiling_is_zero_when_nothing_matches():
    assert core.max_ceiling({}, {("a", "fr")}) == 0.0


def test_format_ceiling_deltas_marks_a_case_that_moved():
    cur = {("clignoter une led", "fr"): 0.52}
    base = {("clignoter une led", "fr"): 0.225}
    lignes = "\n".join(core.format_ceiling_deltas(cur, base))
    assert "0.225" in lignes and "0.520" in lignes
    assert "+0.295" in lignes


def test_format_ceiling_deltas_is_quiet_when_nothing_moved():
    s = {("scanner i2c", "en"): 0.3}
    lignes = "\n".join(core.format_ceiling_deltas(s, dict(s)))
    assert "(=)" in lignes


def test_stray_libs_lists_injected_ids_outside_expect():
    assert core.stray_libs(_CTX_DHT, ["bme280"], _N2I) == ["dht-sensor-library"]


def test_stray_libs_is_empty_when_everything_injected_is_expected():
    assert core.stray_libs(_CTX_DHT, ["dht-sensor-library"], _N2I) == []


def test_stray_summary_counts_cases_and_ids():
    results = [
        {"prompt": "a", "lang": "fr", "outcome": "correct", "stray": ["x"]},
        {"prompt": "b", "lang": "fr", "outcome": "correct", "stray": ["y", "z"]},
        {"prompt": "c", "lang": "fr", "outcome": "correct", "stray": []},
    ]
    assert core.stray_summary(results) == {"cases": 2, "ids": 3}


def test_name_to_id_map_reads_name_and_id():
    entries = [{"name": "DHT sensor library", "id": "dht-sensor-library"}]
    assert core.name_to_id_map(entries) == {
        "DHT sensor library": "dht-sensor-library"}


def test_name_collisions_is_empty_on_a_true_bijection():
    entries = [{"name": "A", "id": "a"}, {"name": "B", "id": "b"}]
    assert core.name_collisions(entries) == {}


def test_name_collisions_flags_a_shared_name():
    entries = [{"name": "A", "id": "a1"}, {"name": "A", "id": "a2"}]
    assert core.name_collisions(entries) == {"A": ["a1", "a2"]}


def test_validate_expect_ids_accepts_known_ids():
    cases = [_case(expect=["dht-sensor-library"])]
    assert core.validate_expect_ids(cases, {"dht-sensor-library"}) == []


def test_validate_expect_ids_accepts_the_wire_special_case():
    cases = [_case(band="generic", expect=["Wire (I2C core library)"])]
    assert core.validate_expect_ids(cases, {"dht-sensor-library"}) == []


def test_validate_expect_ids_flags_a_typo():
    cases = [_case(expect=["dth-sensor-library"])]
    problems = core.validate_expect_ids(cases, {"dht-sensor-library"})
    assert len(problems) == 1
    assert "dth-sensor-library" in problems[0]


TESTS = [
    test_a_valid_case_has_no_problem,
    test_lang_must_be_lowercase_and_known,
    test_band_must_be_known,
    test_specificity_is_required_for_described_and_forbidden_elsewhere,
    test_generic_may_have_an_empty_expect,
    test_expect_must_be_a_list_not_a_string,
    test_case_identity_is_prompt_and_lang,
    test_identity_separates_the_same_sentence_in_two_languages,
    test_load_battery_rejects_an_invalid_file_loudly,
    test_load_battery_reads_a_valid_file,
    test_injected_names_reads_the_block_titles,
    test_injected_names_on_an_empty_context,
    test_injected_names_finds_several_blocks,
    test_a_name_absent_from_the_corpus_stays_itself,
    test_resolve_to_ids_maps_known_names,
    test_classify_silent_on_empty_context,
    test_classify_correct_when_one_expected_id_is_injected,
    test_classify_wrong_when_none_of_the_expected_is_injected,
    test_any_injection_is_wrong_when_expect_is_empty,
    test_silent_is_never_confused_with_wrong,
    test_resolve_expected_prefers_the_exact_id,
    test_resolve_expected_falls_back_to_substring_matches,
    test_resolve_expected_raises_when_nothing_matches,
    test_the_real_battery_is_valid,
    test_the_battery_covers_the_four_languages_evenly,
    test_the_generic_band_covers_its_three_forms,
    test_every_named_case_expects_something,
    test_band_label_splits_described_by_specificity,
    test_summarize_counts_the_three_outcomes_per_band_and_lang,
    test_summarize_is_empty_but_well_formed_on_no_results,
    test_battery_drift_reports_additions_and_removals,
    test_battery_drift_is_silent_when_nothing_moved,
    test_a_removal_is_reported_not_hidden,
    test_format_deltas_marks_a_worsening_wrong_count,
    test_format_deltas_is_quiet_when_nothing_changed,
    test_check_baseline_schema_rejects_a_baseline_without_a_version,
    test_check_baseline_schema_rejects_a_stale_version,
    test_check_baseline_schema_accepts_the_current_version,
    test_common_identities_is_the_intersection,
    test_restrict_to_common_drops_cases_outside_the_set,
    test_deltas_restricted_to_common_cases_do_not_reward_deleting_a_wrong_case,
    test_max_ceiling_restricts_to_the_given_identities,
    test_max_ceiling_is_zero_when_nothing_matches,
    test_format_ceiling_deltas_marks_a_case_that_moved,
    test_format_ceiling_deltas_is_quiet_when_nothing_moved,
    test_stray_libs_lists_injected_ids_outside_expect,
    test_stray_libs_is_empty_when_everything_injected_is_expected,
    test_stray_summary_counts_cases_and_ids,
    test_name_to_id_map_reads_name_and_id,
    test_name_collisions_is_empty_on_a_true_bijection,
    test_name_collisions_flags_a_shared_name,
    test_validate_expect_ids_accepts_known_ids,
    test_validate_expect_ids_accepts_the_wire_special_case,
    test_validate_expect_ids_flags_a_typo,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} test(s) au vert")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
