"""Preference de bibliotheque pour un composant devine (TODO #39).

Quand un part-number est hors corpus, `registry_lookup` cherche au registre
Arduino, y trouve souvent PLUSIEURS libs et en choisit une par heuristique.
Ce module retient la reponse de l'utilisateur quand la devinette est fausse.

Run: python scripts/test_component_libs.py
"""
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui.component_libs as cl
import ui.declared_components as dc
from ui.lib_choice_dialog import choices_for


def _use_temp_store(text: str | None = None) -> Path:
    """Point _LIBRARY_PATH at a throwaway file (optionally pre-filled), and
    clear BOTH registries -- 4 tests reach ui.declared_components through
    preferred_lib_for, and without this reset a test inserted between them
    could silently inherit whatever the previous one left behind."""
    d = Path(tempfile.mkdtemp(prefix="promptuino-libs-"))
    p = d / "component-libs.json"
    if text is not None:
        p.write_text(text, encoding="utf-8")
    cl._LIBRARY_PATH = p
    cl.set_registry({})
    dc.set_registry([])
    return p


def _declared(name: str, lib: str) -> "dc.DeclaredComponent":
    return dc.DeclaredComponent(
        id=name.lower().replace(" ", "-"), name=name, headers=(), pins=(),
        lib=lib, keywords=(name,))


class _R:
    """Stand-in for a `registry_lookup.RegistryLookupResult` -- only the two
    attributes `_preference_was_overridden` actually reads. Avoids pulling in
    `registry_lookup` (and the dataclass's other required fields) just to
    exercise a function that only ever looks at `.token` and `.lib_name`."""

    def __init__(self, token, lib_name):
        self.token = token
        self.lib_name = lib_name


def test_roundtrip_save_load():
    _use_temp_store()
    cl.save({"as7341": "DFRobot AS7341"})
    assert cl.load() == {"as7341": "DFRobot AS7341"}


def test_missing_file_is_empty_not_an_error():
    d = Path(tempfile.mkdtemp(prefix="promptuino-libs-"))
    cl._LIBRARY_PATH = d / "nope.json"
    assert cl.load() == {}


def test_corrupt_file_is_ignored():
    _use_temp_store("{ not json at all")
    assert cl.load() == {}


def test_unknown_version_is_ignored():
    _use_temp_store(json.dumps({"version": 99,
                                "preferences": {"as7341": "X"}}))
    assert cl.load() == {}


def test_non_string_values_are_dropped_not_fatal():
    """A hand-edited file must not take the whole store down."""
    _use_temp_store(json.dumps({"version": 1, "preferences": {
        "as7341": "DFRobot AS7341", "bad": 42, "empty": "  "}}))
    assert cl.load() == {"as7341": "DFRobot AS7341"}


def test_set_and_clear_a_preference():
    _use_temp_store()
    cl.set_preference("as7341", "DFRobot AS7341")
    assert cl.preference_for("as7341") == "DFRobot AS7341"
    assert cl.load() == {"as7341": "DFRobot AS7341"}      # persisted
    cl.clear_preference("as7341")
    assert cl.preference_for("as7341") == ""
    assert cl.load() == {}


def test_set_preference_normalizes_the_key():
    """The token arrives already lowercase from detect_unknown_part_tokens,
    but a caller reading a UI field must not create a second entry."""
    _use_temp_store()
    cl.set_preference("  AS7341 ", "DFRobot AS7341")
    assert cl.preference_for("as7341") == "DFRobot AS7341"


def test_preference_for_unknown_token_is_empty():
    _use_temp_store()
    assert cl.preference_for("nope") == ""
    assert cl.preference_for("") == ""


def test_failed_write_does_not_erase_an_earlier_in_session_choice():
    """Reproduces the durability bug: a save() that fails must not be
    reported as success, and a LATER successful set_preference for a
    DIFFERENT token must not silently drop the first one from memory (seeding
    the mutation from load() alone would: it would seed from a disk that
    never saw the first write)."""
    _use_temp_store()
    cl.set_preference("a", "X")
    assert cl.preference_for("a") == "X"

    real_save = cl.save
    cl.save = lambda prefs: False
    try:
        ok = cl.set_preference("b", "Y")
    finally:
        cl.save = real_save
    assert ok is False
    assert cl.preference_for("a") == "X"      # NOT silently reverted
    assert cl.preference_for("b") == "Y"      # still applied in memory


def test_write_success_is_reported_accurately():
    """set_preference reports True on a normal write; save reports False when
    the target directory cannot be created (a file sits where a directory is
    expected) instead of pretending the write landed."""
    _use_temp_store()
    assert cl.set_preference("as7341", "DFRobot AS7341") is True

    d = Path(tempfile.mkdtemp(prefix="promptuino-libs-"))
    blocker = d / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    cl._LIBRARY_PATH = blocker / "component-libs.json"
    assert cl.save({"as7341": "X"}) is False


def test_blank_token_is_never_written_by_the_mutators():
    """A blank token must never reach disk: preference_for("") and
    preferred_lib_for("") already both answer "" for it, and persisting a
    ""-keyed entry would make preference_for("") start disagreeing with
    preferred_lib_for("") on the same input."""
    _use_temp_store()
    assert cl.set_preference("  ", "X") is False
    assert cl.load() == {}
    assert cl.preference_for("") == ""

    cl.set_preference("as7341", "Y")
    assert cl.clear_preference("   ") is False
    assert cl.preference_for("as7341") == "Y"     # untouched


def test_failed_clear_does_not_come_back_from_the_dead_on_a_later_write():
    """A dict merge can express "new value wins" but never "this key is
    gone": seeding a mutation from disk could leave memory correct right
    after a failed clear, then resurrect the cleared entry on the NEXT,
    unrelated, successful write, because that write re-merged the stale disk
    content back in. Failure happens inside the real save() (os.replace
    patched to raise) rather than by stubbing save() itself, to exercise the
    real exception path."""
    _use_temp_store()
    cl.set_preference("a", "X")
    assert cl.preference_for("a") == "X"

    real_replace = os.replace

    def _boom(*_a, **_kw):
        raise OSError("simulated disk failure")

    os.replace = _boom
    try:
        ok = cl.clear_preference("a")
    finally:
        os.replace = real_replace
    assert ok is False
    assert cl.preference_for("a") == ""        # cleared in memory regardless

    assert cl.set_preference("b", "Y") is True
    assert cl.preference_for("a") == ""        # must NOT come back from the dead
    assert cl.preference_for("b") == "Y"


def test_fresh_process_mutation_does_not_wipe_a_file_it_never_read():
    """The case the disk fallback exists for: a mutation running before
    startup's set_registry(load()) call must still seed from disk, or it
    would silently wipe every preference the file already held."""
    _use_temp_store(json.dumps({"version": 1, "preferences": {"a": "X"}}))
    cl._REGISTRY = {}
    cl._REGISTRY_LOADED = False

    assert cl.set_preference("b", "Y") is True
    assert cl.preference_for("a") == "X"       # not wiped
    assert cl.preference_for("b") == "Y"


def test_preferred_lib_for_reads_the_file_when_not_declared():
    _use_temp_store()
    dc.set_registry([])
    cl.set_preference("as7341", "DFRobot AS7341")
    assert cl.preferred_lib_for("as7341") == "DFRobot AS7341"


def test_preferred_lib_for_reads_the_declared_entry_when_it_exists():
    """One source per component: a declared entry answers with its OWN field,
    never the file — which is why there is no precedence rule to write."""
    _use_temp_store()
    dc.set_registry([_declared("AS7341", "Adafruit AS7341")])
    cl.set_preference("as7341", "DFRobot AS7341")
    assert cl.preferred_lib_for("as7341") == "Adafruit AS7341"


def test_preferred_lib_for_declared_without_lib_is_empty_not_the_file():
    """A declared entry with no lib yet means "still to determine" — falling
    back to the file would resurrect a preference the user replaced by
    declaring the component."""
    _use_temp_store()
    dc.set_registry([_declared("AS7341", "")])
    cl.set_preference("as7341", "DFRobot AS7341")
    assert cl.preferred_lib_for("as7341") == ""


def test_preferred_lib_for_matches_the_declared_token_rule():
    """Same derivation as studio_view._declared_lookup_token: the entry NAME,
    stripped and lowercased. Diverging would make the lookup miss."""
    _use_temp_store()
    dc.set_registry([_declared("Grove Moisture Sensor", "Grove Moisture")])
    assert cl.preferred_lib_for("grove moisture sensor") == "Grove Moisture"


# ── studio_view._preference_was_overridden (TODO #39, task 4 follow-up) ──────
# Module-level pure function -- testable without a QApplication (verified:
# `from ui.studio_view import ...` succeeds headless once
# QT_QPA_PLATFORM=offscreen is set, which this file already does at the top).
# It gates the banner's ONLY way back for the user when a stored preference
# silently failed to resolve, so a regression here either hides that recourse
# again or offers it where nothing was actually overridden.

# ── studio_view._lib_was_already_decided (QA G3, 2026-08-08) ────────────────
# La banniere annonce une DEVINETTE. Repetee a chaque generation alors que la
# lib etait deja decidee, elle devient du decor -- et un decor ne se lit plus
# le jour ou il dit quelque chose d'important.

def test_a_guess_is_announced():
    _use_temp_store()
    from ui.studio_view import _lib_was_already_decided
    assert _lib_was_already_decided(_R("veml7700", "DevLab_VEML7700")) is False


def test_a_recorded_decision_is_not_announced_again():
    _use_temp_store()
    from ui.studio_view import _lib_was_already_decided
    cl.set_preference("as7341", "Adafruit AS7341")
    assert _lib_was_already_decided(_R("as7341", "Adafruit AS7341")) is True


def test_a_contradicted_decision_is_still_announced():
    """Une preference qui existe mais ne correspond PAS n'est pas « deja
    decide » : c'est un choix contredit, et celui-la doit se dire. Les deux
    helpers lisent le meme `preferred_lib_for`, donc ils ne peuvent pas se
    contredire -- annoncer « ton choix a ete ecrase » en masquant la banniere
    qui le repare serait pire que de se taire."""
    _use_temp_store()
    from ui.studio_view import (_lib_was_already_decided,
                                _preference_was_overridden)
    cl.set_preference("as7341", "DFRobot AS7341")
    r = _R("as7341", "Adafruit AS7341")
    assert _lib_was_already_decided(r) is False
    assert _preference_was_overridden(r) == "DFRobot AS7341"


def test_already_decided_compares_through_norm_lib_name():
    _use_temp_store()
    from ui.studio_view import _lib_was_already_decided
    cl.set_preference("as7341", "Adafruit  AS7341")     # double espace
    assert _lib_was_already_decided(_R("as7341", "Adafruit AS7341")) is True


def test_preference_was_overridden_no_preference_is_empty():
    _use_temp_store()
    from ui.studio_view import _preference_was_overridden
    assert _preference_was_overridden(_R("as7341", "Adafruit AS7341")) == ""


def test_preference_was_overridden_matching_preference_is_empty():
    """A preference that resolved to the exact library used is not an
    override -- nothing to announce, nothing to fix."""
    _use_temp_store()
    from ui.studio_view import _preference_was_overridden
    cl.set_preference("as7341", "Adafruit AS7341")
    assert _preference_was_overridden(_R("as7341", "Adafruit AS7341")) == ""


def test_preference_was_overridden_returns_the_preference_when_different():
    _use_temp_store()
    from ui.studio_view import _preference_was_overridden
    cl.set_preference("as7341", "DFRobot AS7341")
    assert _preference_was_overridden(
        _R("as7341", "Adafruit AS7341")) == "DFRobot AS7341"


def test_preference_was_overridden_compares_through_norm_lib_name():
    """A plain == would read the double space as a real divergence and fire a
    false "your choice was overridden" message on every single generation --
    the same whitespace trap `choices_for`'s dedup already guards against."""
    _use_temp_store()
    from ui.studio_view import _preference_was_overridden
    cl.set_preference("as7341", "Adafruit  AS7341")      # double space
    assert _preference_was_overridden(_R("as7341", "Adafruit AS7341")) == ""


def test_preference_was_overridden_follows_the_declared_entry():
    """preferred_lib_for answers from a DECLARED entry's own `lib` field, not
    the file, for a declared token -- this helper must go through that same
    source (it calls preferred_lib_for, never the file directly), or an
    override on a declared component would go undetected."""
    _use_temp_store()
    from ui.studio_view import _preference_was_overridden
    dc.set_registry([_declared("AS7341", "DFRobot AS7341")])
    assert _preference_was_overridden(
        _R("as7341", "Adafruit AS7341")) == "DFRobot AS7341"


def test_choices_put_the_current_lib_first_without_duplicating_it():
    """The retained lib must be offered AND pre-checkable, but the registry
    returns it inside `alternatives` too -- listing it twice would show two
    identical radios."""
    assert choices_for("Adafruit AS7341",
                       ["Adafruit AS7341", "DFRobot AS7341"]) == [
        "Adafruit AS7341", "DFRobot AS7341"]


def test_choices_add_the_current_lib_when_absent_from_alternatives():
    assert choices_for("Adafruit AS7341", ["DFRobot AS7341"]) == [
        "Adafruit AS7341", "DFRobot AS7341"]


def test_choices_ignore_case_and_padding_when_deduplicating():
    """Registry names round-trip through JSON and a cache; a stray space or a
    different case must not create a SECOND radio for the same library --
    this asserts both that the dedup triggers (one surviving entry for
    as7341, not two) AND which spelling survives: `choices_for` keeps the
    CURRENT lib's own text (stripped, not case-folded), never the
    alternative's -- first-seen-wins, the same rule proven by
    test_choices_dedup_uses_the_projects_own_library_name_key, whose double-
    space case would break if a collision instead adopted the alternative's
    spelling."""
    assert choices_for(" adafruit as7341 ",
                       ["Adafruit AS7341", "DFRobot AS7341"]) == [
        "adafruit as7341", "DFRobot AS7341"]


def test_choices_survive_an_empty_current_lib_or_no_alternatives():
    assert choices_for("", ["DFRobot AS7341"]) == ["DFRobot AS7341"]
    assert choices_for("Adafruit AS7341", []) == ["Adafruit AS7341"]
    assert choices_for("", []) == []


def test_choices_dedup_uses_the_projects_own_library_name_key():
    """Dedup goes through registry_lookup.norm_lib_name, the key this project
    ALREADY uses to compare library names -- it collapses internal whitespace
    too, which a plain .strip().lower() would miss, leaving two radios for one
    library."""
    assert choices_for("Adafruit  AS7341", ["Adafruit AS7341"]) == [
        "Adafruit  AS7341"]


def test_lib_choice_labels_exist_in_all_languages():
    from ui.i18n import TRANSLATIONS
    keys = ("lib_choice_title", "lib_choice_body",
            "lib_choice_search_placeholder",
            "lib_choice_search_empty", "lib_choice_search_unavailable",
            "lib_choice_ok", "lib_choice_cancel", "registry_change_lib",
            "registry_pref_not_found",
            # Refonte 2026-08-12 : cards, etats du bloc et card epinglee.
            "lib_choice_let_app_decide", "lib_choice_let_app_decide_hint",
            "lib_choice_loading", "lib_choice_count", "lib_choice_count_one",
            "lib_choice_count_capped", "lib_choice_badge_in_use",
            "lib_choice_badge_retired", "lib_choice_badge_incompatible",
            "lib_choice_meta_all_boards", "lib_choice_meta_requires")
    # TRANSLATIONS[lg] is a `Strings` dataclass instance, not a dict -- plain
    # attribute access (getattr), not .get()/[...], the same convention every
    # other i18n-completeness test in this suite already uses.
    for lg in ("fr", "en", "es", "it"):
        s = TRANSLATIONS[lg]
        for k in keys:
            assert (getattr(s, k, "") or "").strip(), (lg, k)
        # Le bouton « Chercher » n'existe plus : la liste suit la frappe.
        assert not getattr(s, "lib_choice_search_button", ""), lg
    for lg in ("fr", "en", "es", "it"):
        s = TRANSLATIONS[lg]
        body = s.lib_choice_body
        assert "{part}" in body and "{lib}" in body, lg
        # The fallback message must name all three: what the user asked for,
        # for which part, and what was used instead. Dropping one would make
        # it unactionable.
        warn = s.registry_pref_not_found
        for ph in ("{pref}", "{part}", "{lib}"):
            assert ph in warn, (lg, ph)
    for lg in ("fr", "en", "es", "it"):
        s = TRANSLATIONS[lg]
        # Les comptes portent un nombre, la version plafonnee en porte deux :
        # sans eux le message ne dirait pas ce qu'il est cense dire.
        assert "{n}" in s.lib_choice_count, lg
        for ph in ("{total}", "{shown}"):
            assert ph in s.lib_choice_count_capped, (lg, ph)
        assert "{q}" in s.lib_choice_search_empty, lg
        assert "{deps}" in s.lib_choice_meta_requires, lg


def test_features_using_includes_matches_on_the_header_only():
    """Which features must be regenerated after a library change. Matching is
    on the HEADER FILE, not the library name: two libraries for the same chip
    routinely ship the same include, and the library name never appears in the
    generated code at all."""
    from ui.studio_view import _features_using_includes

    class _F:
        def __init__(self, fid, includes):
            self.id = fid
            self.includes = includes

    feats = [_F("fn-1", ["#include <Adafruit_AS7341.h>", "#include <Wire.h>"]),
             _F("fn-2", ["#include <Servo.h>"]),
             _F("fn-3", ["Adafruit_AS7341.h"])]
    assert _features_using_includes(feats, ["Adafruit_AS7341.h"]) == {"fn-1", "fn-3"}
    assert _features_using_includes(feats, ["Servo.h"]) == {"fn-2"}
    assert _features_using_includes(feats, ["Nope.h"]) == set()
    assert _features_using_includes(feats, []) == set()
    assert _features_using_includes([], ["Servo.h"]) == set()


def test_features_using_includes_ignores_case_and_path():
    """Includes round-trip through the model and the cache; a case or folder
    difference must not make the match miss and silently skip a regeneration."""
    from ui.studio_view import _features_using_includes

    class _F:
        def __init__(self, fid, includes):
            self.id = fid
            self.includes = includes

    feats = [_F("fn-1", ["#include <Adafruit/ADAFRUIT_AS7341.H>"])]
    assert _features_using_includes(feats, ["adafruit_as7341.h"]) == {"fn-1"}


def test_features_using_includes_skips_non_string_entries_without_raising():
    """The registry cache is a hand-editable JSON file (see
    `_after_lib_preference_changed`'s own docstring): a stray number or null
    in "headers" must not crash the click handler that reads it -- which runs
    AFTER the preference write has already landed on disk, so there is no
    "abort the write" to fall back to on a crash."""
    from ui.studio_view import _features_using_includes

    class _F:
        def __init__(self, fid, includes):
            self.id = fid
            self.includes = includes

    feats = [_F("fn-1", [123, None, "#include <Bar.h>"])]
    assert _features_using_includes(feats, ["Bar.h"]) == {"fn-1"}
    assert _features_using_includes(feats, [123, None, "Bar.h"]) == {"fn-1"}


def test_lib_swap_regen_labels_exist_in_all_languages():
    from ui.i18n import TRANSLATIONS
    for lg in ("fr", "en", "es", "it"):
        for k in ("lib_swap_regen_title", "lib_swap_regen_body",
                  "lib_swap_regen_body_cleared",
                  "lib_swap_regen_yes", "lib_swap_regen_no"):
            assert (getattr(TRANSLATIONS[lg], k, "") or "").strip(), (lg, k)
        body = getattr(TRANSLATIONS[lg], "lib_swap_regen_body")
        assert "{old}" in body and "{new}" in body, lg


def test_lib_swap_regen_body_cleared_never_names_a_new_library():
    """The « Laisser l'app decider » sibling of `lib_swap_regen_body`: a
    clear has no new library to report, so this key must never claim one --
    only `{old}` (what the code still uses), never `{new}`."""
    from ui.i18n import TRANSLATIONS
    for lg in ("fr", "en", "es", "it"):
        body = getattr(TRANSLATIONS[lg], "lib_swap_regen_body_cleared")
        assert "{old}" in body, lg
        assert "{new}" not in body, lg


def test_lib_swap_unchecked_label_exists_in_all_languages():
    """`_warn_lib_swap_unchecked`'s message: a changed preference whose
    affected features could not be determined (cache record evicted) must
    still be sayable in every language."""
    from ui.i18n import TRANSLATIONS
    for lg in ("fr", "en", "es", "it"):
        v = getattr(TRANSLATIONS[lg], "lib_swap_unchecked", "") or ""
        assert v.strip(), lg
        assert "{part}" in v and "{new}" in v, lg


TESTS = [
    test_roundtrip_save_load,
    test_missing_file_is_empty_not_an_error,
    test_corrupt_file_is_ignored,
    test_unknown_version_is_ignored,
    test_non_string_values_are_dropped_not_fatal,
    test_set_and_clear_a_preference,
    test_set_preference_normalizes_the_key,
    test_preference_for_unknown_token_is_empty,
    test_failed_write_does_not_erase_an_earlier_in_session_choice,
    test_write_success_is_reported_accurately,
    test_blank_token_is_never_written_by_the_mutators,
    test_failed_clear_does_not_come_back_from_the_dead_on_a_later_write,
    test_fresh_process_mutation_does_not_wipe_a_file_it_never_read,
    test_preferred_lib_for_reads_the_file_when_not_declared,
    test_preferred_lib_for_reads_the_declared_entry_when_it_exists,
    test_preferred_lib_for_declared_without_lib_is_empty_not_the_file,
    test_preferred_lib_for_matches_the_declared_token_rule,
    test_a_guess_is_announced,
    test_a_recorded_decision_is_not_announced_again,
    test_a_contradicted_decision_is_still_announced,
    test_already_decided_compares_through_norm_lib_name,
    test_preference_was_overridden_no_preference_is_empty,
    test_preference_was_overridden_matching_preference_is_empty,
    test_preference_was_overridden_returns_the_preference_when_different,
    test_preference_was_overridden_compares_through_norm_lib_name,
    test_preference_was_overridden_follows_the_declared_entry,
    test_choices_put_the_current_lib_first_without_duplicating_it,
    test_choices_add_the_current_lib_when_absent_from_alternatives,
    test_choices_ignore_case_and_padding_when_deduplicating,
    test_choices_survive_an_empty_current_lib_or_no_alternatives,
    test_choices_dedup_uses_the_projects_own_library_name_key,
    test_lib_choice_labels_exist_in_all_languages,
    test_features_using_includes_matches_on_the_header_only,
    test_features_using_includes_ignores_case_and_path,
    test_features_using_includes_skips_non_string_entries_without_raising,
    test_lib_swap_regen_labels_exist_in_all_languages,
    test_lib_swap_regen_body_cleared_never_names_a_new_library,
    test_lib_swap_unchecked_label_exists_in_all_languages,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
