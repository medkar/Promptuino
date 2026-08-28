"""Projection of the three component populations onto a single descriptor.

The "Composants" tab aggregates: the components DECLARED by the user
(editable), the curated component REGISTRY (`ui/component_registry.py`,
~90 entries, each entry pointing at the corpus documents -- if any -- that
describe it), and the components the app had to GUESS a library for (the
registry lookup cache unioned with the user's own choices). Projecting
heterogeneous sources is exactly where bugs hide -- a field missing from one
source, two entries for the SAME chip -- hence this pure module, tested
headless.

Run: python scripts/test_component_index.py
"""
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui.declared_components as dc
import ui.registry_lookup as rl
from ui.component_index import (
    ORIGIN_CORPUS, ORIGIN_DECLARED, ORIGIN_WIRING,
    build_index, filter_components,
)
from ui.rag import all_corpus_entries

# Hermetic baseline for the WHOLE file, installed once at import time (not
# inside a test): `build_index()` now reads the registry lookup cache
# (component_index._looked_up_components), a REAL file under the developer's
# Documents folder in production. Without this, every test below -- not just
# the four that know about looked-up components -- would silently depend on
# that machine's own registry-cache.json. Concretely: a developer uses the
# "change library" feature once, the file gains an `as7341` entry, and
# test_index_is_registry_plus_declared (len(infos) == len(reg_registry()) + 1)
# starts failing on THAT machine only, with no code change -- passing today is
# luck (the file happens not to exist here), not determinism.
#
# `{}`, not `None`: this file has no per-test setup/teardown, so whichever
# tests below touch the override are the only thing standing between the rest
# of the file and the real disk -- and `None` means "no override, read the
# real file". Restoring `None` in a `finally` would silently reopen that gap
# for every test after them. `{}` is the value that keeps the whole file
# hermetic regardless of test order or future additions.
rl.set_cache_for_tests({})


def _use_temp_index_library() -> Path:
    """Redirects the declared-components library file to a throwaway temp
    dir, so write-back tests never touch the real ~/Documents/Promptuino
    file."""
    d = Path(tempfile.mkdtemp(prefix="promptuino-idx-"))
    dc._LIBRARY_PATH = d / "components.json"
    return dc._LIBRARY_PATH


def _grove():
    return dc.DeclaredComponent(
        id="grove-moisture-sensor", name="Grove Moisture Sensor",
        lib="", keywords=("Grove Moisture Sensor",), headers=(),
        pins=(dc.DeclaredPin("VCC", "vcc", "5V"),
              dc.DeclaredPin("GND", "gnd", "GND"),
              dc.DeclaredPin("SIG", "signal", "A0")))


def _by_origin(components, origin):
    return [c for c in components if c.origin == origin]


def test_index_contains_the_three_origins():
    dc.set_registry([_grove()])
    components = build_index()
    assert _by_origin(components, ORIGIN_DECLARED), "no declared component"
    assert _by_origin(components, ORIGIN_CORPUS), "no corpus component"
    assert _by_origin(components, ORIGIN_WIRING), "no wiring-only component"


def test_declared_component_fields():
    dc.set_registry([_grove()])
    info = next(c for c in build_index() if c.origin == ORIGIN_DECLARED)
    assert info.name == "Grove Moisture Sensor"
    assert info.editable is True
    assert info.pin_count == 3
    assert info.wiring == "known"
    assert info.library == "unknown"        # empty lib -> "library still unknown"
    assert info.keywords == ("Grove Moisture Sensor",)


def test_corpus_components_are_read_only_and_library_state_mirrors_the_doc():
    """Registry entries with a document are read-only, and their `library`
    state mirrors the DEFAULT document's `arduino_lib_name` -- `known` when
    it is set, `none` when the document exists but carries no library --
    UNLESS the registry entry overrides it (2026-08-12, tache 3 of #44).

    That exception is not a loophole, it is the arbitration: the corpus is
    frozen (embeddings aligned by position), so a wrong value there can only
    be corrected from the registry. `sd_card` is the case -- `arduino_lib_name:
    null` on a component that needs `#include <SD.h>`. Entries carrying an
    override are therefore checked against the REGISTRY field here, and the
    doc-mirroring rule keeps its full force on all the others.

    Measured on assets/rag/corpus.json (2026-07-30): 13 of the 91 entries
    have no `arduino_lib_name` -- sd/stepper/eeprom/softwareserial ship with
    the Arduino core (nothing to install), and pir-motion-sensor/mq135/
    drv8833/l293d/dc_motor/stepper_28byj48/nema17/ldr/buzzer are pure
    hardware (no library exists for them at all). Expectations are derived
    from the corpus + registry directly (not a hand-copied id list): the two
    catalogs speak different id spaces (document id vs registry id) and a
    static list would silently rot the moment either one is edited.
    """
    from ui.component_registry import by_id as reg_by_id
    dc.set_registry([])
    docs = {str(e.get("id")): e for e in all_corpus_entries() if e.get("id")}
    corpus = _by_origin(build_index(), ORIGIN_CORPUS)
    assert len(corpus) >= 60, len(corpus)
    overrides = 0
    for c in corpus:
        assert c.editable is False
        comp = reg_by_id(c.key)
        assert comp is not None and comp.documents, c.key
        doc = docs[comp.default_document]
        if comp.lib_name or comp.lib_to_determine:
            overrides += 1
            if comp.lib_name:
                assert c.library == "known" and c.lib == comp.lib_name, c.name
            else:
                assert c.library == "unknown" and not c.lib, c.name
            continue
        expected_lib = str(doc.get("arduino_lib_name") or "").strip()
        if expected_lib:
            assert c.library == "known" and c.lib == expected_lib, c.name
        else:
            assert c.library == "none" and not c.lib, c.name
    # The override path must stay EXERCISED: if `sd_card` ever loses its
    # `lib_name`, the branch above would silently stop being tested here.
    assert overrides >= 1, "aucune entree corpus n'exerce la precedence registre"
    assert any(c.description for c in corpus)


def test_wiring_only_components_state_their_own_library():
    """ORIGIN_WIRING is the registry entries with NO document at all --
    "button" moved OUT of this population in task 2 (the registry attaches
    `onebutton` to it, since a document describing an EXISTING catalog
    component is exactly what the old alias table could not express);
    "potentiometer" has no document either side and stays a fair witness.

    Renamed from `test_wiring_only_components_have_no_lib` on 2026-08-12
    (tache 3, #44). "No library" was true of this population only as long as
    it held bare-pin parts. Task 1 added `lib_name` / `lib_to_determine`
    precisely because the blanket "none" LIED for a bus component with no
    corpus document (a BMP180 announcing "aucune librairie a installer"), and
    task 3 filled 34 such entries in. Asserting `library == "none"` for all of
    them would now lock the very bug the field was introduced to fix, so the
    check mirrors `_library_state` per entry instead: the card must say
    exactly what the registry entry declares, and the three witnesses that ARE
    bare-pin parts (led, potentiometer, relay) must still say "none".

    Having a pin count does NOT hold for all either: since 2026-07-31 this
    population also holds the types `markers` emits without a catalog entry
    (`relay`, `thermistor`, `microphone`, `ky018`) -- wired by the app, drawn
    generic, so `pin_count` is 0 by design. The pin-count assertion is
    therefore scoped to the drawable ones, which is where it says something.

    ⚠️ The "known" liveness witness moved OUT on 2026-08-21 (lot #60, task 6):
    every documentless entry that used to carry a `lib_name` (48 of them,
    `bmp085`/`bmp180`/`tmp102`... ) received its own corpus `documents` that
    day, which is the entire point of that chantier -- it is meant to shrink
    this exact population to zero on that branch. There is currently no
    PRODUCTION registry entry left that is both documentless and has a
    `lib_name`, so asserting `any(...)` here would either lock in a stale
    witness or go permanently unreachable. The "known" branch of
    `_library_state` staying wired end-to-end is instead covered on synthetic
    data by `test_a_documentless_known_library_reaches_the_card_via_build_index`
    below, which does not depend on today's registry contents.
    """
    from ui.component_registry import by_id as reg_by_id
    dc.set_registry([])
    wiring = _by_origin(build_index(), ORIGIN_WIRING)
    names = {c.key for c in wiring}
    assert "led" in names and "potentiometer" in names, sorted(names)[:20]
    assert "relay" in names, sorted(names)[:20]
    # Bare-pin witnesses: nothing to install, and the card must keep saying so.
    for key in ("led", "potentiometer", "relay"):
        info = next(c for c in wiring if c.key == key)
        assert info.library == "none" and info.lib == "", key
    # Liveness on the "unknown" branch, otherwise this test would go on
    # passing if that field stopped reaching the card at all. ("known"
    # liveness: see the synthetic test below, cf. docstring above.)
    assert any(c.library == "unknown" for c in wiring), \
        "no documentless entry says 'library to determine' (lib_to_determine never reaches the card)"
    for c in wiring:
        assert c.editable is False
        comp = reg_by_id(c.key)
        assert comp is not None and not comp.documents, c.key
        if comp.lib_name:
            assert c.library == "known" and c.lib == comp.lib_name, c.key
        elif comp.lib_to_determine:
            assert c.library == "unknown" and c.lib == "", c.key
        else:
            assert c.library == "none" and c.lib == "", c.key
        if c.wiring == "known":
            assert c.pin_count > 0, c.key
        else:
            assert c.pin_count == 0, c.key


def test_a_documentless_known_library_reaches_the_card_via_build_index():
    """The "known" liveness witness `test_wiring_only_components_state_their_own_library`
    used to carry (any documentless registry entry with a `lib_name`) no
    longer exists in PRODUCTION data since lot #60 (task 6, 2026-08-21) gave
    every such entry its own corpus `documents` -- the chantier's entire
    point. Rather than assert on today's registry contents (which would lock
    in whichever entry happens to still be documentless, or go permanently
    unreachable), this exercises the same end-to-end path
    (`build_index` -> `_registry_components` -> `_library_state`) on a
    synthetic entry that stays documentless by construction, the same
    registry-patching pattern already used by
    `test_registry_description_reaches_the_card_when_no_doc` and neighbours."""
    import ui.component_registry as cr
    comp = cr.Component(id="x_test_known_no_doc", function="sensor",
                        mounting="breadboard", wiring="unknown",
                        lib_name="Fake Test Library")
    dc.set_registry([])
    orig = cr.registry
    try:
        cr.registry = lambda: (comp,)
        wiring = _by_origin(build_index(), ORIGIN_WIRING)
    finally:
        cr.registry = orig
    info = next(c for c in wiring if c.key == "x_test_known_no_doc")
    assert info.library == "known" and info.lib == "Fake Test Library"


def test_index_is_registry_plus_declared():
    dc.set_registry([_grove()])
    from ui.component_registry import registry as reg_registry
    infos = build_index()
    assert len(infos) == len(reg_registry()) + 1
    assert any(i.origin == ORIGIN_DECLARED for i in infos)


def test_the_two_halves_are_one_component():
    """The duplicate that started this chantier: the corpus knew the library
    (no pinout), the catalog knew the pinout (no library). ONE entry now."""
    dc.set_registry([])
    by_key = {i.key: i for i in build_index()}
    ssd = by_key["oled_ssd1306"]
    assert ssd.wiring == "known" and ssd.library == "known"
    assert ssd.lib and ssd.pin_count > 0
    assert "adafruit-ssd1306" not in by_key      # absorbed, not shown alone


def test_a_component_needing_no_library_says_so():
    """The filter used to over-promise: it said "the app can code this", it
    meant "a library entry exists". An LDR needs none -- `analogRead` is enough."""
    dc.set_registry([])
    by_key = {i.key: i for i in build_index()}
    assert by_key["led"].library == "none"
    assert by_key["ldr"].library == "none"       # its document has no lib


def test_an_undrawable_component_says_unknown_not_absent():
    # `ccs811` reste hors des deux lots Fritzing du 2026-08-19 (TODO #57) --
    # `bme280`, cite ici jusqu'a ce jour, est passe en wiring="known" et ne
    # convient plus d'exemple. Meme choix stable que
    # `test_component_registry.test_the_unknown_pinout_debt_is_real_and_bounded`.
    dc.set_registry([])
    by_key = {i.key: i for i in build_index()}
    assert by_key["ccs811"].wiring == "unknown"
    assert by_key["eeprom"].wiring == "none"


def test_declared_component_without_a_lib_is_pending():
    dc.set_registry([_grove()])
    info = next(i for i in build_index() if i.origin == ORIGIN_DECLARED)
    assert info.library == "unknown"            # "lib à déterminer"
    assert info.editable is True


def test_module_generic_is_not_a_component_you_look_up():
    """`module_generic` is a detector FALLBACK, not a component anyone
    searches for: bare label ("module"/"modulo"), 2 pins named "1" and "2",
    no description. Same status as `resistor` and `battery_external`."""
    dc.set_registry([])
    keys = {c.key for c in build_index()}
    assert "module_generic" not in keys, "module_generic is offered as a component"


def test_declared_entry_shadows_a_catalog_type_of_the_same_key():
    """If the user declares a component whose id collides with a catalog type,
    THEIR entry (editable) must win -- otherwise they can no longer edit it."""
    clash = dc.DeclaredComponent(
        id="led", name="Ma LED speciale", lib="", keywords=("Ma LED speciale",),
        headers=(), pins=(dc.DeclaredPin("A", "signal", "D9"),))
    dc.set_registry([clash])
    components = [c for c in build_index() if c.key in ("led", "custom:led")]
    assert len(components) == 1, [(c.key, c.origin) for c in components]
    assert components[0].origin == ORIGIN_DECLARED
    assert components[0].editable is True


def test_filter_by_kind():
    dc.set_registry([_grove()])
    components = build_index()
    assert all(c.editable for c in filter_components(components, kind="declared"))
    assert all(c.library == "known"
               for c in filter_components(components, kind="with_library"))
    assert all(c.wiring == "known"
               for c in filter_components(components, kind="drawable"))
    assert len(filter_components(components, kind="all")) == len(components)


def test_filter_by_query_matches_name_and_lib_and_keywords():
    dc.set_registry([_grove()])
    components = build_index()
    assert any(c.origin == ORIGIN_DECLARED
               for c in filter_components(components, query="moisture"))
    assert any(c.origin == ORIGIN_DECLARED
               for c in filter_components(components, query="GROVE"))     # case-insensitive
    assert filter_components(components, query="zzzzz-inexistant") == []


def test_filter_folds_accents_both_ways():
    """Taper « température » doit trouver « capteur de temperature ».

    Mesure du 2026-08-18, AVANT le correctif : « température » rendait 6
    composants, « temperature » en rendait 16. Les NOMS affiches sont traduits
    et portent leurs accents, donc la requete accentuee les touchait ; les 1311
    mots-cles du registre, eux, sont ecrits sans accent par convention et
    restaient hors d'atteinte.

    Le defaut n'etait donc pas une recherche vide mais une recherche
    SILENCIEUSEMENT PARTIELLE — plus trompeuse qu'un echec visible, puisque 6
    resultats plausibles passent pour la reponse complete.
    """
    dc.set_registry([])
    components = build_index()
    accentue = filter_components(components, query="température")
    nu = filter_components(components, query="temperature")
    assert nu, "pre-condition : la requete sans accent trouve des composants"
    assert {c.key for c in accentue} == {c.key for c in nu}, (
        "« température » et « temperature » doivent rendre le meme ensemble"
    )
    # Le repli couvre aussi la casse ET les accents ensemble, dans les deux
    # sens : ce sont trois ecritures de la meme requete.
    reference = {c.key for c in filter_components(components, query="temperature")}
    for variante in ("TEMPÉRATURE", "Température", "TEMPERATURE"):
        assert ({c.key for c in filter_components(components, query=variante)}
                == reference), f"{variante!r} doit rendre le meme ensemble"


def test_filter_combines_query_and_kind():
    dc.set_registry([_grove()])
    components = build_index()
    out = filter_components(components, query="moisture", kind="declared")
    assert len(out) == 1 and out[0].origin == ORIGIN_DECLARED
    assert filter_components(components, query="moisture", kind="with_library") == []


def test_index_survives_an_empty_registry():
    dc.set_registry([])
    assert build_index()          # corpus + wiring are enough on their own


def test_nav_and_view_labels_exist_in_all_languages():
    from ui.i18n import lang_manager
    keys = ("nav_composants", "components_search_placeholder",
            "components_filter_all", "components_filter_declared",
            "components_filter_with_library", "components_filter_drawable",
            "components_declare_button", "components_lib_unknown",
            "components_wiring_unknown", "components_wiring_none",
            "components_library_none",
            "components_custom_badge_tip", "components_empty",
            "components_pin_count", "components_change_lib")
    for lg in ("fr", "en", "es", "it"):
        lang_manager.set_language(lg)
        s = lang_manager.current
        for k in keys:
            assert getattr(s, k, "").strip(), (lg, k)
    lang_manager.set_language("fr")


def test_wiring_component_name_follows_the_lang_argument():
    """`build_index(lang=...)` must localize wiring-only component names --
    they used to be hardcoded to "fr" ("bouton-poussoir" shown to an English
    user). "button" is a good witness: its fr/en labels genuinely differ
    (ui/wiring/instructions.py: fr "bouton-poussoir" vs en "push-button"),
    unlike e.g. "led" whose label is the same string in every language."""
    dc.set_registry([])
    names_fr = {c.key: c.name for c in build_index(lang="fr")}
    names_en = {c.key: c.name for c in build_index(lang="en")}
    assert names_fr["button"] == "bouton-poussoir", names_fr["button"]
    assert names_en["button"] == "push-button", names_en["button"]
    assert names_fr["button"] != names_en["button"]


# ── Lib et description côté registre (tâche 1, modale unifiée #44) ──────────
# Une entrée SANS document corpus doit pouvoir dire sa lib (BMP180) ou avouer
# qu'elle est à déterminer, au lieu du mensonge « aucune librairie à
# installer » — le corpus ne doit PAS grossir pour ça (embeddings alignés par
# position).

def test_a_registry_component_can_carry_its_own_lib_name():
    """Un composant bus sans document corpus doit pouvoir dire sa lib.
    Avant : doc absent => "aucune librairie a installer", mensonge pour
    un BMP180."""
    from ui.component_registry import Component
    from ui.component_index import _library_state
    comp = Component(id="x_test", function="sensor", mounting="breadboard",
                     wiring="unknown", lib_name="Adafruit BMP085 Library")
    assert _library_state(comp, None) == ("known", "Adafruit BMP085 Library")


def test_a_registry_component_can_say_lib_to_determine():
    from ui.component_registry import Component
    from ui.component_index import _library_state
    comp = Component(id="x_test", function="sensor", mounting="breadboard",
                     wiring="unknown", lib_to_determine=True)
    assert _library_state(comp, None) == ("unknown", "")


def test_without_lib_fields_the_none_state_is_preserved():
    """Les entrees existantes (led, relay...) ne changent pas d'etat."""
    from ui.component_registry import Component
    from ui.component_index import _library_state
    comp = Component(id="x_test", function="output", mounting="breadboard",
                     wiring="known")
    assert _library_state(comp, None) == ("none", "")


def test_registry_description_reaches_the_card_when_no_doc():
    import ui.component_registry as cr
    import ui.component_index as ci
    comp = cr.Component(id="x_test", function="sensor", mounting="breadboard",
                        wiring="unknown", description="Capteur de test.")
    orig = cr.registry
    try:
        cr.registry = lambda: (comp,)
        infos = ci._registry_components("fr")
    finally:
        cr.registry = orig
    assert infos[0].description == "Capteur de test."


def test_a_registry_lib_name_overrides_the_document():
    """Arbitration settled on 2026-08-12 (tache 3, #44): when both sources
    speak, the REGISTRY field wins over the corpus document.

    Found on `sd_card`: the `sd` document carries `arduino_lib_name: null`,
    so its card said "aucune librairie a installer" -- but `SD` exists in the
    Arduino index and `#include <SD.h>` is required. The corpus is wrong AND
    frozen (its embedding matrix is aligned by position, so a value cannot be
    corrected in place), which leaves the registry as the only place to say
    the truth. Without this precedence the field would be dead code for every
    component that HAS a document, and the tab would keep repeating a defect
    nobody is allowed to fix at the source.
    """
    from ui.component_registry import Component
    from ui.component_index import _library_state
    comp = Component(id="x_test", function="storage", mounting="breadboard",
                     wiring="unknown", documents=("x_doc",), lib_name="SD")
    assert _library_state(comp, {"arduino_lib_name": None}) == ("known", "SD")
    # ... and it also beats a document that names a DIFFERENT library, which
    # is the same defect one degree worse.
    assert _library_state(
        comp, {"arduino_lib_name": "Perimee"}) == ("known", "SD")


def test_a_registry_description_overrides_the_document():
    """Same precedence, same reason, on the other field the card shows."""
    from ui.component_registry import Component
    import ui.component_registry as cr
    import ui.component_index as ci
    comp = Component(id="sd_card", function="storage", mounting="breadboard",
                     wiring="unknown", documents=("sd",),
                     description="Description du registre.")
    orig = cr.registry
    try:
        cr.registry = lambda: (comp,)
        infos = ci._registry_components("fr")
    finally:
        cr.registry = orig
    assert infos[0].description == "Description du registre."


def test_scraped_type_name_falls_back_to_replacement_catalog():
    """Un type absent de _TYPE_LABEL mais present au catalogue de
    remplacement prend son libelle cure, jamais l'id brut. Compare a
    `label_of` plutot qu'a la chaine en dur : reformuler le libelle du
    catalogue ne doit pas casser ce test, seul le slug brut est la
    regression a attraper.

    `atlas_ph` plutot que `bmp180` (2026-08-19) : bmp180 a rejoint
    `_TYPE_LABEL` au lot Fritzing #2 (TODO #57) et n'exerce donc plus le
    CHEMIN DE REPLI que ce test verrouille -- il faut un id absent des deux
    tables pour de vrai. atlas_ph n'a de brochage dans aucun des deux lots.
    """
    import ui.component_registry as cr
    import ui.component_index as ci
    from ui.wiring.replacement_catalog import label_of
    comp = cr.Component(id="atlas_ph", function="sensor", mounting="breadboard",
                        wiring="unknown")
    orig = cr.registry
    try:
        cr.registry = lambda: (comp,)
        infos = ci._registry_components("fr")
    finally:
        cr.registry = orig
    assert infos[0].name == label_of("atlas_ph"), infos[0].name
    assert infos[0].name != "atlas_ph"


# ── Generation trigger + write-back (task 5, spec 2026-07-30) ────────────────
# `studio_view._declared_lookup_request` / `_write_back_declared_lib` are
# module-level pure functions -- testable without a QApplication (verified:
# `import ui.studio_view` succeeds headless once QT_QPA_PLATFORM=offscreen is
# set, which this file already does at the top).

def test_declared_lookup_request_uses_the_entry_name_not_a_part_token():
    """The easiest point to miss: `detect_unknown_part_tokens` requires
    digits AND letters, so "Grove Moisture Sensor" never triggers it -- and
    that is precisely the component that got the shape rule dropped in the
    first place. For a declared entry, the trigger is a keyword match and
    the search runs on the entry's NAME."""
    from ui.registry_lookup import detect_unknown_part_tokens
    from ui.studio_view import _declared_lookup_request
    prompt = "lis l'humidite avec mon Grove Moisture Sensor"
    assert detect_unknown_part_tokens(prompt) == []      # the detector is blind here
    dc.set_registry([_grove()])
    req = _declared_lookup_request(prompt)
    assert req is not None
    token, preferred = req
    assert "grove" in token.lower()
    assert preferred == ""            # _grove() has no lib


def test_declared_lookup_request_passes_a_known_lib_as_preferred():
    from ui.studio_view import _declared_lookup_request
    entry = dc.DeclaredComponent(
        id="as7341", name="AS7341", lib="Adafruit AS7341",
        keywords=("AS7341",), headers=(),
        pins=(dc.DeclaredPin("VCC", "vcc", "5V"),))
    dc.set_registry([entry])
    req = _declared_lookup_request("code pour l'AS7341")
    assert req is not None and req[1] == "Adafruit AS7341"


def test_declared_lookup_request_none_on_collision_or_no_match():
    """The brief's own fixture for this test would not actually collide:
    `_grove()` only carries the full phrase "Grove Moisture Sensor" as
    keyword (asserted verbatim by `test_declared_component_fields`, so it must
    not be widened here), not the bare word "moisture". Building `other`
    with "moisture" alone would make it the ONLY entry matching a
    "moisture"-only prompt -- no collision, and the test would prove the
    opposite of its own name. Build the collision on a phrase BOTH entries
    claim instead; the intent (two entries triggered -> no injection, no
    write-back) is unchanged."""
    from ui.studio_view import _declared_lookup_request
    other = dc.DeclaredComponent(
        id="autre", name="Autre", lib="", keywords=("Grove Moisture Sensor",),
        headers=(), pins=(dc.DeclaredPin("S", "signal", ""),))
    dc.set_registry([_grove(), other])
    assert _declared_lookup_request("lis mon Grove Moisture Sensor") is None
    dc.set_registry([_grove()])
    assert _declared_lookup_request("fais clignoter une led") is None


def test_write_back_records_lib_and_headers_on_the_entry():
    from ui.studio_view import _write_back_declared_lib

    class _Res:
        token = "grove moisture sensor"
        lib_name = "Grove Moisture Sensor"
        entry = {"arduino_lib_name": "Grove Moisture Sensor",
                 "headers": ["Grove_Moisture_Sensor.h"]}

    _use_temp_index_library()
    dc.set_registry([_grove()])
    dc.save([_grove()])
    _write_back_declared_lib("lis mon Grove Moisture Sensor", [_Res()])
    back = dc.load()
    assert len(back) == 1
    assert back[0].lib == "Grove Moisture Sensor"
    assert "grove_moisture_sensor.h" in back[0].headers


def test_write_back_does_nothing_on_collision():
    """Same arbitration as the collision test above: the colliding keyword
    must be the phrase `_grove()` actually carries."""
    from ui.studio_view import _write_back_declared_lib

    class _Res:
        token = "grove moisture sensor"
        lib_name = "Whatever"
        entry = {"arduino_lib_name": "Whatever", "headers": ["W.h"]}

    other = dc.DeclaredComponent(
        id="autre", name="Autre", lib="", keywords=("Grove Moisture Sensor",),
        headers=(), pins=(dc.DeclaredPin("S", "signal", ""),))
    _use_temp_index_library()
    dc.set_registry([_grove(), other])
    dc.save([_grove(), other])
    _write_back_declared_lib("lis mon Grove Moisture Sensor", [_Res()])
    assert all(c.lib == "" for c in dc.load())


def test_write_back_picks_the_result_matching_its_own_token_not_the_first():
    """Regression: a prompt can name BOTH an unrelated unknown part-number
    AND a declared component in the same generation (the declared token is
    APPENDED to `unknown` in `_start_generation`, never replacing it), so
    `results` legitimately holds several entries. Picking "the first result
    with a non-None `.entry`" -- the original brief code -- would silently
    attach the unrelated chip's library (and its #include) to the declared
    entry whenever the registry happens to resolve the unrelated token
    first, which is exactly the cross-chip substitution this whole pipeline
    exists to forbid. The selection must be by TOKEN, not by position."""
    from ui.studio_view import _write_back_declared_lib

    class _Unrelated:
        token = "xyz1234"
        lib_name = "SomeUnrelatedSensor"
        entry = {"arduino_lib_name": "SomeUnrelatedSensor",
                 "headers": ["SomeUnrelatedSensor.h"]}

    class _Grove:
        token = "grove moisture sensor"
        lib_name = "Grove Moisture Sensor"
        entry = {"arduino_lib_name": "Grove Moisture Sensor",
                 "headers": ["Grove_Moisture_Sensor.h"]}

    _use_temp_index_library()
    dc.set_registry([_grove()])
    dc.save([_grove()])
    # Unrelated result FIRST, declared component's own result SECOND -- the
    # exact ordering `_start_generation` produces (unknown tokens first,
    # declared token appended last).
    _write_back_declared_lib("branche un XYZ1234 et lis mon Grove Moisture Sensor",
                             [_Unrelated(), _Grove()])
    back = dc.load()
    assert len(back) == 1
    assert back[0].lib == "Grove Moisture Sensor", back[0].lib
    assert "grove_moisture_sensor.h" in back[0].headers
    assert "someunrelatedsensor.h" not in back[0].headers


def test_write_back_refuses_an_unreadable_library():
    """Second write path, same guard as the form's `_on_save`: components.json
    exists but this build cannot parse it (newer schema version, or corrupt),
    so `load()` degrades to [] on purpose -- and saving would replace the whole
    library with this single entry. Unreachable today ONLY because an
    unreadable file yields an empty registry, i.e. an implicit invariant, not a
    check: the second write path must carry the first one's protection."""
    from ui.studio_view import _write_back_declared_lib

    class _Res:
        token = "grove moisture sensor"
        lib_name = "Grove Moisture Sensor"
        entry = {"arduino_lib_name": "Grove Moisture Sensor",
                 "headers": ["Grove_Moisture_Sensor.h"]}

    p = _use_temp_index_library()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 999, "components": []}),
                 encoding="utf-8")
    dc.set_registry([_grove()])          # in-memory registry NOT empty
    _write_back_declared_lib("lis mon Grove Moisture Sensor", [_Res()])
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["version"] == 999, \
        f"the unreadable library was overwritten: {on_disk}"


# ── Looked-up components (TODO #39 task 5, spec 2026-08-03) ─────────────────
# Third origin: a component the app had to GUESS a library for (the registry
# lookup cache, unioned with the user's own choices in `component_libs`), so
# it has a durable home in the "Composants" tab instead of existing only in
# the ephemeral info banner.
#
# `rl.set_cache_for_tests(...)` installs a MODULE-LEVEL override in
# `ui.registry_lookup`. The whole file is kept hermetic by the module-level
# `rl.set_cache_for_tests({})` call above (see its comment): every test below
# that needs its OWN cache content sets the override, and MUST restore it to
# `{}` -- the file's hermetic baseline -- not `None`, which means "no
# override, read the real file" and would silently reopen that gap for every
# test running after it. try/finally guarantees the restore even when an
# assertion fails midway.

def test_looked_up_components_appear_in_the_index():
    """Third origin. Without it a guessed component appears NOWHERE — it is
    neither declared nor in the registry — so there is no card to come back to
    and the tab cannot be the durable home the design promises."""
    import ui.component_libs as cl
    from ui.component_index import ORIGIN_LOOKED_UP
    dc.set_registry([])
    cl.set_registry({})
    rl.set_cache_for_tests({"as7341": {
        "lib_name": "Adafruit AS7341",
        "entry": {"id": "as7341", "name": "AS7341",
                  "arduino_lib_name": "Adafruit AS7341",
                  "description": "Spectral sensor"},
        "alternatives": ["Adafruit AS7341", "DFRobot AS7341"]}})
    try:
        infos = {c.key: c for c in build_index()}
        assert "as7341" in infos
        info = infos["as7341"]
        assert info.origin == ORIGIN_LOOKED_UP
        assert info.lib == "Adafruit AS7341"
        assert info.library == "known"
        assert info.wiring == "unknown"        # guessed: no catalog footprint
        assert info.editable is False
    finally:
        rl.set_cache_for_tests({})


def test_a_declared_component_does_not_double_with_its_own_lookup():
    """QA G3 (2026-08-08) : declarer « Grove Ultrasonic Ranger » puis generer
    donnait DEUX fiches pour le meme composant -- une declaree (editable) et
    une devinee.

    Les cles ne different que par le SEPARATEUR : l'entree declaree porte un
    slug (`grove-ultrasonic-ranger`), la recherche est memorisee sous le token
    du prompt (`grove ultrasonic ranger`). L'egalite de chaine les laissait
    passer toutes les deux."""
    import ui.component_libs as cl
    from ui.component_index import ORIGIN_DECLARED
    dc.set_registry([dc.DeclaredComponent(
        id="grove-ultrasonic-ranger", name="Grove Ultrasonic Ranger",
        headers=("ultrasonic.h",),
        pins=(dc.DeclaredPin("1", "signal", ""),),
        lib="Grove Ultrasonic Ranger",
        keywords=("Grove Ultrasonic Ranger",))])
    cl.set_registry({})
    rl.set_cache_for_tests({"grove ultrasonic ranger": {
        "lib_name": "Grove Ultrasonic Ranger",
        "entry": {"id": "grove ultrasonic ranger",
                  "name": "Grove Ultrasonic Ranger",
                  "arduino_lib_name": "Grove Ultrasonic Ranger"},
        "alternatives": []}})
    try:
        idx = build_index()
        hits = [c for c in idx if "ultrasonic ranger" in c.name.lower()]
        assert len(hits) == 1, [(c.key, c.origin) for c in hits]
        # ... et c'est la DECLAREE qui survit : sinon l'utilisateur perdrait
        # le crayon sur un composant qu'il a decrit lui-meme.
        assert hits[0].origin == ORIGIN_DECLARED, hits[0].origin
        assert hits[0].editable is True
    finally:
        rl.set_cache_for_tests({})
        dc.set_registry([])


def test_a_chosen_lib_survives_without_the_cache():
    """The durability the design promises: once CHOSEN the entry lives in the
    preferences file, which never evicts — unlike the cache."""
    import ui.component_libs as cl
    dc.set_registry([])
    rl.set_cache_for_tests({})
    try:
        cl.set_registry({"as7341": "DFRobot AS7341"})
        infos = {c.key: c for c in build_index()}
        assert "as7341" in infos
        assert infos["as7341"].lib == "DFRobot AS7341"
    finally:
        rl.set_cache_for_tests({})


def test_a_chosen_lib_wins_over_the_cached_guess():
    import ui.component_libs as cl
    dc.set_registry([])
    rl.set_cache_for_tests({"as7341": {
        "lib_name": "Adafruit AS7341",
        "entry": {"id": "as7341", "name": "AS7341",
                  "arduino_lib_name": "Adafruit AS7341"},
        "alternatives": ["Adafruit AS7341", "DFRobot AS7341"]}})
    try:
        cl.set_registry({"as7341": "DFRobot AS7341"})
        infos = {c.key: c for c in build_index()}
        assert infos["as7341"].lib == "DFRobot AS7341"
    finally:
        rl.set_cache_for_tests({})


def test_a_declared_entry_still_shadows_a_looked_up_one():
    """Precedence already asserted for declared vs registry; the third origin
    must not break it — the user must keep editing what they declared."""
    import ui.component_libs as cl
    from ui.component_index import ORIGIN_DECLARED
    rl.set_cache_for_tests({"grove-moisture-sensor": {
        "lib_name": "Whatever", "entry": {"id": "x", "name": "X"},
        "alternatives": []}})
    try:
        cl.set_registry({})
        dc.set_registry([_grove()])
        infos = {c.key: c for c in build_index()}
        assert infos["grove-moisture-sensor"].origin == ORIGIN_DECLARED
    finally:
        rl.set_cache_for_tests({})


def test_index_does_not_read_the_machines_cache_file():
    """build_index() must never depend on the developer's own
    registry-cache.json: a real entry accumulating there would change counts
    and break unrelated tests on one machine only.

    Proves the hermetic baseline itself (the module-level
    `rl.set_cache_for_tests({})` above), not just that a test CAN override the
    cache -- points `_CACHE_PATH` at a temp file holding a real-looking entry
    (simulating "the machine's cache is not empty") and confirms it stays
    invisible: the override must win before `_cache_load` ever touches the
    path, so nothing here needs to actually be readable for the assertion to
    hold, but writing real, parseable content is what would catch a regression
    that reordered or dropped the override check.
    """
    real_path = rl._CACHE_PATH
    tmp_dir = Path(tempfile.mkdtemp(prefix="promptuino-cache-"))
    tmp_path = tmp_dir / "registry-cache.json"
    tmp_path.write_text(json.dumps({"v": 1, "entries": {"realchip": {
        "lib_name": "SomeRealLookingLib",
        "entry": {"id": "realchip", "name": "REALCHIP"},
        "alternatives": []}}}), encoding="utf-8")
    rl._CACHE_PATH = tmp_path
    dc.set_registry([])
    try:
        rl.set_cache_for_tests({})     # the hermetic override: must win over the file
        infos = {c.key: c for c in build_index()}
        assert "realchip" not in infos, (
            "build_index() read the file on disk instead of honouring the "
            "cache override -- the whole file is no longer hermetic")
    finally:
        rl._CACHE_PATH = real_path
        rl.set_cache_for_tests({})


TESTS = [
    test_index_contains_the_three_origins,
    test_declared_component_fields,
    test_corpus_components_are_read_only_and_library_state_mirrors_the_doc,
    test_wiring_only_components_state_their_own_library,
    test_a_documentless_known_library_reaches_the_card_via_build_index,
    test_index_is_registry_plus_declared,
    test_the_two_halves_are_one_component,
    test_a_component_needing_no_library_says_so,
    test_an_undrawable_component_says_unknown_not_absent,
    test_declared_component_without_a_lib_is_pending,
    test_module_generic_is_not_a_component_you_look_up,
    test_write_back_refuses_an_unreadable_library,
    test_declared_entry_shadows_a_catalog_type_of_the_same_key,
    test_filter_by_kind,
    test_filter_by_query_matches_name_and_lib_and_keywords,
    test_filter_folds_accents_both_ways,
    test_filter_combines_query_and_kind,
    test_index_survives_an_empty_registry,
    test_nav_and_view_labels_exist_in_all_languages,
    test_wiring_component_name_follows_the_lang_argument,
    test_a_registry_component_can_carry_its_own_lib_name,
    test_a_registry_component_can_say_lib_to_determine,
    test_without_lib_fields_the_none_state_is_preserved,
    test_registry_description_reaches_the_card_when_no_doc,
    test_a_registry_lib_name_overrides_the_document,
    test_a_registry_description_overrides_the_document,
    test_scraped_type_name_falls_back_to_replacement_catalog,
    test_declared_lookup_request_uses_the_entry_name_not_a_part_token,
    test_declared_lookup_request_passes_a_known_lib_as_preferred,
    test_declared_lookup_request_none_on_collision_or_no_match,
    test_write_back_records_lib_and_headers_on_the_entry,
    test_write_back_does_nothing_on_collision,
    test_write_back_picks_the_result_matching_its_own_token_not_the_first,
    test_looked_up_components_appear_in_the_index,
    test_a_declared_component_does_not_double_with_its_own_lookup,
    test_a_chosen_lib_survives_without_the_cache,
    test_a_chosen_lib_wins_over_the_cached_guess,
    test_a_declared_entry_still_shadows_a_looked_up_one,
    test_index_does_not_read_the_machines_cache_file,
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
