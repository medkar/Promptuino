"""User-declared components library (TODO #38 point 5).

When the detector fails to recognise a component, it emits an unwired
placeholder box. The user can describe it themselves (name, pins, labels,
wiring); the declaration is indexed by #include HEADER, the only stable
key (a placeholder's nets are empty), and replayed across all projects.
"""
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui.declared_components as dc
from ui.wiring.layout.component_catalog import _GENERIC_BY_PIN_COUNT, lookup, role_of
from ui.wiring.netlist import Component, Netlist, Pin
from ui.wiring.ambiguity_dialog import apply_saved_resolution
from ui.wiring.replacement_ui import full_candidate_choices, is_user_declared
from ui.wiring.instructions import _label
from ui.wiring.declared_apply import apply_library_to_netlist
from ui.wiring.markers import _warn_unrenderable_components
from ui.wiring.netlist import SEVERITY_INFO
from ui.wiring.declare_component_dialog import (
    DECLARE_OPTION_ID, prefill_pins, filter_persistable_choices,
    resolve_board_nets,
)

# QApplication kept alive at module level: constructing a QDialog right
# after a throwaway `QApplication.instance() or QApplication([])` (no
# reference kept) crashes the process on Windows (0xC0000409) once the
# temporary app gets garbage-collected. Same pattern as
# scripts/test_ambiguity_dropdown_smoke.py.
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog  # noqa: E402
_APP = QApplication.instance() or QApplication([])

_NETS = ["5V", "3V3", "GND"] + [f"D{i}" for i in range(14)] + [f"A{i}" for i in range(6)]


def _as7341() -> "dc.DeclaredComponent":
    return dc.DeclaredComponent(
        id="as7341", name="AS7341",
        headers=("as7341.h", "adafruit_as7341.h"),
        pins=(dc.DeclaredPin("VCC", "vcc", "5V"),
              dc.DeclaredPin("GND", "gnd", "GND"),
              dc.DeclaredPin("SDA", "sda", "A4"),
              dc.DeclaredPin("SCL", "scl", "A5"),
              dc.DeclaredPin("INT", "signal", "")))


def _dip16() -> "dc.DeclaredComponent":
    pins = [dc.DeclaredPin("VCC", "vcc", "5V"), dc.DeclaredPin("GND", "gnd", "GND")]
    pins += [dc.DeclaredPin(f"IO{i}", "signal", "") for i in range(14)]
    return dc.DeclaredComponent(id="mondip", name="Mon DIP",
                                headers=("mondip.h",), pins=tuple(pins))


def _use_temp_library(text: str | None = None) -> Path:
    """Point _LIBRARY_PATH at a throwaway file (optionally pre-filled)."""
    d = Path(tempfile.mkdtemp(prefix="promptuino-lib-"))
    p = d / "components.json"
    if text is not None:
        p.write_text(text, encoding="utf-8")
    dc._LIBRARY_PATH = p
    return p


def test_type_id_uses_the_prefix():
    assert _as7341().type_id == "custom:as7341"
    assert dc.TYPE_PREFIX == "custom:"


def test_slugify_normalizes_and_dedups():
    assert dc.slugify("AS 7341!", set()) == "as-7341"
    assert dc.slugify("  Mon Capteur  ", set()) == "mon-capteur"
    assert dc.slugify("AS 7341!", {"as-7341"}) == "as-7341-2"
    assert dc.slugify("AS 7341!", {"as-7341", "as-7341-2"}) == "as-7341-3"
    # Name entirely non-alphanumeric -> fallback slug, never empty.
    assert dc.slugify("!!!", set()) == "composant"


def test_drawable_pin_counts_match_the_layout():
    # Must match _GENERIC_BY_PIN_COUNT: single-row 2-8 plus odd 9/11/13, DIP 10-40 even.
    assert set(_GENERIC_BY_PIN_COUNT) == dc.DRAWABLE_PIN_COUNTS
    # Explicit boundaries: detect drift if both change together.
    for n in (2, 3, 4, 5, 6, 7, 8, 9, 11, 13, 10, 12, 40):
        assert dc.is_drawable_pin_count(n), n
    # 15 is the first odd count above single-row max (13), so it guards the upper boundary.
    for n in (0, 1, 15, 41, 42):
        assert not dc.is_drawable_pin_count(n), n


def test_role_is_derived_from_net_then_label():
    # Net wins over label.
    assert dc.role_for("VCC", "5V") == "vcc"
    assert dc.role_for("V", "3V3") == "vcc"
    assert dc.role_for("GND", "GND") == "gnd"
    assert dc.role_for("SDA", "A4") == "sda"
    assert dc.role_for("SCL", "A5") == "scl"
    # If net is empty or unknown, fall back to label.
    assert dc.role_for("VCC", "") == "vcc"
    assert dc.role_for("GND", "") == "gnd"
    assert dc.role_for("SDA", "") == "sda"
    assert dc.role_for("SCL", "") == "scl"
    assert dc.role_for("INT", "D7") == "signal"
    assert dc.role_for("INT", "") == "signal"
    # Net still wins: a pin named VCC wired to D7 is a signal, not a rail
    # (router would otherwise pull an unwanted wire to 5V).
    assert dc.role_for("VCC", "D7") == "signal"


def test_normalize_header_drops_path_and_case():
    assert dc.normalize_header("Adafruit/AS7341.H") == "as7341.h"
    assert dc.normalize_header("AS7341.h") == "as7341.h"
    assert dc.normalize_header("lib\\\\Sub\\\\Thing.h") == "thing.h"


def test_roundtrip_save_load():
    _use_temp_library()
    dc.save([_as7341()])
    back = dc.load()
    assert len(back) == 1
    assert back[0] == _as7341()


def test_corrupt_file_is_ignored():
    _use_temp_library("{ not json at all")
    assert dc.load() == []


def test_invalid_utf8_bytes_are_ignored():
    # read_text(encoding="utf-8") raises UnicodeDecodeError (a ValueError) on
    # a stray non-UTF-8 byte -- load() must degrade to [] like any other
    # unreadable file, not propagate. Reproduced: this used to kill the app
    # at startup, before any window exists (main.py calls load() early).
    d = Path(tempfile.mkdtemp(prefix="promptuino-lib-"))
    p = d / "components.json"
    p.write_bytes(b'{"version": 1, "components": [{"bad": "\xe9"}]}')
    dc._LIBRARY_PATH = p
    assert dc.load() == []


def test_unknown_version_is_ignored():
    _use_temp_library(json.dumps({"version": 99, "components": [
        {"id": "x", "name": "X", "headers": ["x.h"], "pins": []}]}))
    assert dc.load() == []


def test_missing_file_is_empty_not_an_error():
    d = Path(tempfile.mkdtemp(prefix="promptuino-lib-"))
    dc._LIBRARY_PATH = d / "nope.json"
    assert dc.load() == []


def test_find_by_type_and_header():
    dc.set_registry([_as7341()])
    assert dc.find_by_type("custom:as7341") is not None
    assert dc.find_by_type("custom:nope") is None
    assert dc.find_by_header("Adafruit/AS7341.H") is not None
    assert dc.find_by_header("AS7341.h") is not None
    assert dc.find_by_header("Other.h") is None
    assert dc.find_by_header("") is None


def test_malformed_records_are_skipped():
    # A library with one good record and two malformed ones: load() returns
    # only the good one. Malformed: missing "id", non-list "pins".
    _use_temp_library(json.dumps({"version": 1, "components": [
        {"id": "as7341", "name": "AS7341", "headers": ["as7341.h"], "pins": []},
        {"name": "Bad1", "headers": ["bad1.h"], "pins": []},  # missing "id"
        {"id": "bad2", "name": "Bad2", "headers": ["bad2.h"], "pins": "not a list"},  # bad pins
    ]}))
    loaded = dc.load()
    assert len(loaded) == 1
    assert loaded[0].id == "as7341"


def test_lookup_resolves_a_declared_component():
    dc.set_registry([_as7341()])
    e = lookup("custom:as7341")
    assert e is not None
    assert e.name == "AS7341"
    assert e.pin_count == 5
    assert e.pin_labels == {1: "VCC", 2: "GND", 3: "SDA", 4: "SCL", 5: "INT"}
    assert e.pin_roles[1] == "vcc" and e.pin_roles[5] == "signal"
    assert e.is_dip is False            # 5 pins -> single row
    assert e.asset_path.exists()


def test_lookup_resolves_a_declared_dip():
    dc.set_registry([_dip16()])
    e = lookup("custom:mondip")
    assert e is not None and e.is_dip is True and e.pin_count == 16


def test_lookup_unknown_declared_type_is_none():
    dc.set_registry([])
    assert lookup("custom:nope") is None


def test_lookup_still_resolves_builtin_types():
    dc.set_registry([_as7341()])
    assert lookup("led") is not None


def test_role_of_works_for_declared_types():
    dc.set_registry([_as7341()])
    assert role_of("custom:as7341", 3) == "sda"
    assert role_of("custom:as7341", 5) == "signal"
    assert role_of("custom:nope", 1) is None


def _placeholder() -> "Component":
    return Component(
        ref="U1", type="as7341", fn_id="fn-1",
        pins=[Pin("1", ""), Pin("2", ""), Pin("3", ""), Pin("4", "")],
        attributes={"unrecognized": True, "header": "AS7341.h",
                    "constructor_pins": ["D5", "D6"]})


def test_applying_a_declaration_rewires_and_cleans_up():
    dc.set_registry([_as7341()])
    c = _placeholder()
    nl = Netlist(board_id="uno", components=[c])
    apply_saved_resolution(c, "custom:as7341", nl)
    assert c.type == "custom:as7341"
    assert [(p.name, p.net) for p in c.pins] == [
        ("VCC", "5V"), ("GND", "GND"), ("SDA", "A4"), ("SCL", "A5"), ("INT", "")]
    for gone in ("unrecognized", "presumed_wiring", "constructor_pins"):
        assert gone not in c.attributes, gone
    assert c.attributes.get("user_declared") is True
    # Une declaration n'est PAS "lue dans le code" : le drapeau reste faux.
    assert not c.attributes.get("signature_detected")
    # `header` est la cle de re-application (tache 4) : elle doit survivre.
    assert c.attributes["header"] == "AS7341.h"


def test_applying_an_unknown_declaration_leaves_the_component_alone():
    dc.set_registry([])
    c = _placeholder()
    nl = Netlist(board_id="uno", components=[c])
    apply_saved_resolution(c, "custom:as7341", nl)
    assert c.type == "as7341"
    assert c.attributes.get("unrecognized") is True


def test_a_declared_component_stays_editable():
    dc.set_registry([_as7341()])
    c = _placeholder()
    apply_saved_resolution(c, "custom:as7341", Netlist(board_id="uno", components=[c]))
    assert is_user_declared(c)
    ids = [t for t, _ in full_candidate_choices(c, "fr")]
    assert ids[0] == "custom:as7341"
    for promo in ("led", "buzzer", "servo", "dc_motor", "module_generic"):
        assert promo in ids, promo


def test_the_library_is_offered_on_an_ordinary_component():
    dc.set_registry([_as7341()])
    led = Component(ref="D1", type="led", fn_id="fn-1", pins=[Pin("A", "D3")])
    ids = [t for t, _ in full_candidate_choices(led, "fr")]
    assert ids[0] == "led"
    assert "custom:as7341" in ids
    labels = dict(full_candidate_choices(led, "fr"))
    assert labels["custom:as7341"] == "AS7341"


def test_a_non_replaceable_component_stays_empty():
    dc.set_registry([_as7341()])
    r = Component(ref="R1", type="resistor", fn_id="fn-1", pins=[Pin("A", "D3")])
    assert full_candidate_choices(r, "fr") == []


def test_going_back_from_declared_to_a_builtin_type():
    dc.set_registry([_as7341()])
    c = _placeholder()
    nl = Netlist(board_id="uno", components=[c])
    apply_saved_resolution(c, "custom:as7341", nl)
    apply_saved_resolution(c, "led", nl)
    assert c.type == "led"


def test_instructions_use_the_declared_name():
    dc.set_registry([_as7341()])
    assert _label("custom:as7341", "fr") == "AS7341"
    assert _label("custom:as7341", "en") == "AS7341"
    # Entree disparue de la bibliotheque : on ne plante pas, on retombe sur le type.
    dc.set_registry([])
    assert _label("custom:as7341", "fr") == "custom:as7341"


def _netlist_with_placeholder() -> "Netlist":
    c = _placeholder()
    nl = Netlist(board_id="uno", components=[c])
    nl.add_warning(code="unwired_unknown_component_pins", severity=SEVERITY_INFO,
                   message="...", refs=["U1"], params={"name": "AS7341",
                                                       "pins": "D5, D6"})
    return nl


def test_reapplication_by_header():
    dc.set_registry([_as7341()])
    nl = _netlist_with_placeholder()
    assert apply_library_to_netlist(nl) == ["U1"]
    c = nl.by_ref("U1")
    assert c.type == "custom:as7341"
    assert [p.net for p in c.pins] == ["5V", "GND", "A4", "A5", ""]


def test_reapplication_on_a_presumed_i2c_box():
    dc.set_registry([_as7341()])
    c = Component(ref="U1", type="as7341", fn_id="fn-1",
                  pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                        Pin("SDA", "A4"), Pin("SCL", "A5")],
                  attributes={"presumed_wiring": True, "header": "AS7341.h"})
    nl = Netlist(board_id="uno", components=[c])
    nl.add_warning(code="presumed_i2c_wiring", severity=SEVERITY_INFO,
                   message="...", refs=["U1"], params={"name": "AS7341"})
    assert apply_library_to_netlist(nl) == ["U1"]
    assert nl.by_ref("U1").type == "custom:as7341"
    assert [w.code for w in nl.warnings] == ["declared_unconnected_pins"]


def test_obsolete_warnings_are_dropped_and_open_pins_reported():
    dc.set_registry([_as7341()])
    nl = _netlist_with_placeholder()
    apply_library_to_netlist(nl)
    codes = [w.code for w in nl.warnings]
    assert "unwired_unknown_component_pins" not in codes
    # La fiche cable l'I2C (A4/A5) alors que le placeholder a vu D5/D6 dans le
    # constructeur : depuis le TODO #45 ce scenario emet AUSSI la confrontation
    # code/fiche. La liste reste verrouillee a l'exact — elle apprend le
    # nouveau code plutot que de s'assouplir. La contradiction sort EN PREMIER
    # (l'infobulle ne retient que le premier warning par ref) : l'ordre est
    # verrouille par test_declared_pin_divergence.py.
    assert codes == ["declared_pins_diverge_from_code",
                     "declared_unconnected_pins"]
    w = next(w for w in nl.warnings if w.code == "declared_unconnected_pins")
    assert w.severity == SEVERITY_INFO
    assert w.params["pins"] == "INT"
    assert w.params["name"] == "AS7341"


def test_a_fully_wired_declaration_reports_nothing():
    fully = dc.DeclaredComponent(
        id="as7341", name="AS7341", headers=("as7341.h",),
        pins=(dc.DeclaredPin("VCC", "vcc", "5V"),
              dc.DeclaredPin("GND", "gnd", "GND"),
              dc.DeclaredPin("SDA", "sda", "A4"),
              dc.DeclaredPin("SCL", "scl", "A5")))
    dc.set_registry([fully])
    nl = _netlist_with_placeholder()
    # Le sujet de ce test est « aucune broche ouverte -> aucun warning ». La
    # preuve du constructeur (D5/D6) que le placeholder partage avec les
    # autres tests contredirait cette fiche I2C et ferait tomber la
    # confrontation du TODO #45 — un AUTRE sujet, couvert par
    # scripts/test_declared_pin_divergence.py. On retire la preuve ici plutot
    # que d'assouplir l'assertion : sans preuve, il n'y a rien a confronter.
    nl.by_ref("U1").attributes.pop("constructor_pins", None)
    apply_library_to_netlist(nl)
    assert nl.warnings == []


def test_skip_refs_lets_the_project_resolution_win():
    """Mirrors StudioView._already_resolved_refs: a saved resolution can only
    win over the library when its key carries a REAL net. A "genuine" box
    (e.g. a presumed-I2C placeholder -- its pins DO have real nets) can be
    legitimately skipped. An `unrecognized` placeholder's key is DEGENERATE
    (empty net: it has no wired pin at all, indistinguishable from any other
    placeholder in the same function) -- even if it collides with something
    in `_wiring_resolutions`, it must NOT be skipped: the library is exactly
    the mechanism meant to fix these boxes up."""
    from ui.studio_view import StudioView

    dc.set_registry([_as7341()])
    genuine = Component(ref="U1", type="as7341", fn_id="fn-1",
                  pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                        Pin("SDA", "A4"), Pin("SCL", "A5")],
                  attributes={"presumed_wiring": True, "header": "AS7341.h"})
    placeholder = _placeholder()
    placeholder.ref = "U2"
    nl = Netlist(board_id="uno", components=[genuine, placeholder])

    genuine_key = StudioView._resolution_key_for(None, genuine, nl)
    placeholder_key = StudioView._resolution_key_for(None, placeholder, nl)
    assert genuine_key[1] != ""             # real net -> a legitimate key
    assert placeholder_key[1] == ""         # no wired pin -> degenerate key

    class _FakeSV:
        _resolution_key_for = StudioView._resolution_key_for
        _already_resolved_refs = StudioView._already_resolved_refs
    fake = _FakeSV()
    fake._wiring_resolutions = {genuine_key: "as7341", placeholder_key: "as7341"}
    already = fake._already_resolved_refs(nl)
    assert already == {"U1"}                # only the genuine key is trusted

    assert apply_library_to_netlist(nl, skip_refs=already) == ["U2"]
    assert nl.by_ref("U1").type == "as7341"            # skipped: project wins
    assert nl.by_ref("U2").type == "custom:as7341"     # library still applies


def test_unknown_header_changes_nothing():
    dc.set_registry([_as7341()])
    c = _placeholder()
    c.attributes["header"] = "Autre.h"
    nl = Netlist(board_id="uno", components=[c])
    assert apply_library_to_netlist(nl) == []
    assert nl.by_ref("U1").type == "as7341"


def test_a_declared_component_can_never_be_undrawable():
    # Le formulaire contraint le nombre de broches ; on verrouille ici que la
    # passe de re-application ne peut pas fabriquer le trou undrawable_component
    # qu'on a bouche le 2026-07-29.
    dc.set_registry([_as7341()])
    nl = _netlist_with_placeholder()
    apply_library_to_netlist(nl)
    before = len(nl.warnings)
    _warn_unrenderable_components(nl)
    assert len(nl.warnings) == before


def test_declared_unconnected_pins_label_exists_in_all_languages():
    from ui.wiring.instructions import _WARNING_TEMPLATES
    tpl = _WARNING_TEMPLATES["declared_unconnected_pins"]
    for lg in ("fr", "en", "es", "it"):
        assert lg in tpl and "{pins}" in tpl[lg], lg


def test_prefill_uses_the_presumed_i2c_pins():
    c = Component(ref="U1", type="as7341", fn_id="fn-1",
                  pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                        Pin("SDA", "A4"), Pin("SCL", "A5")],
                  attributes={"presumed_wiring": True, "header": "AS7341.h"})
    assert prefill_pins(c, _NETS) == [
        ("VCC", "5V"), ("GND", "GND"), ("SDA", "A4"), ("SCL", "A5")]


def test_prefill_uses_the_constructor_pins_seen_in_the_code():
    c = _placeholder()          # constructor_pins = ["D5", "D6"]
    rows = prefill_pins(c, _NETS)
    assert len(rows) == 4                       # placeholder = 4 broches
    assert [n for _, n in rows][:2] == ["D5", "D6"]
    assert [n for _, n in rows][2:] == ["", ""]


def test_prefill_ignores_constructor_pins_absent_from_the_board():
    c = _placeholder()
    c.attributes["constructor_pins"] = ["D5", "D99"]
    rows = prefill_pins(c, _NETS)
    assert [n for _, n in rows][:2] == ["D5", ""]


def test_a_declared_component_is_offered_on_any_ambiguous_pin():
    """Re-pointe le 2026-08-13 : ces deux affirmations portaient sur les
    tuiles (`build_options_for_type`), qui n'existent plus. Elles portent
    maintenant sur la source vivante. `DECLARE_OPTION_ID` n'y figure plus :
    dans la modale unifiee « Creer un composant » est un BOUTON, pas un
    candidat — il n'a plus a etre le dernier d'une liste."""
    dc.set_registry([_as7341()])
    led = Component(ref="D1", type="led", fn_id="fn-1",
                    pins=[Pin("A", "D5"), Pin("K", "GND")],
                    attributes={"category": "single_output"})
    ids = [t for t, _ in full_candidate_choices(led, "fr")]
    assert "custom:as7341" in ids, ids


def test_a_placeholder_is_never_left_without_candidates():
    """Un type NON RECONNU (placeholder d'include inconnu) garde son propre
    type en tete et recoit les echappatoires : un picker vide sur le seul
    composant que l'app n'a pas su lire serait exactement le mauvais moment
    pour ne rien proposer.

    Re-pointe le 2026-08-13 depuis `build_options_for_type`, dont la
    distinction « avec / sans composant » n'a plus d'equivalent :
    `full_candidate_choices` recoit toujours le composant."""
    dc.set_registry([])
    c = _placeholder()
    ids = [t for t, _ in full_candidate_choices(c, "fr")]
    assert ids[0] == c.type, ids
    for hatch in ("servo", "dc_motor", "module_generic"):
        assert hatch in ids, (hatch, ids)
    assert not any(t.startswith("custom:") for t in ids), ids

    dc.set_registry([_as7341()])
    ids = [t for t, _ in full_candidate_choices(c, "fr")]
    assert "custom:as7341" in ids, ids


# -- Review finding 2026-07-30 #1: cancelling "Decrire mon composant..." must
# never leave the sentinel where it can be persisted. The real decision lives
# inside StudioView._resolve_wiring_netlist (not callable headless: it needs
# a live modal exec()), so it was extracted into a tiny pure helper and is
# tested here instead. --------------------------------------------------

def test_filter_persistable_choices_drops_cancelled_declarations():
    chosen = {"D1": "led", "D2": DECLARE_OPTION_ID, "D3": "custom:as7341"}
    out = filter_persistable_choices(chosen, cancelled_refs={"D2"})
    assert out == {"D1": "led", "D3": "custom:as7341"}


def test_filter_persistable_choices_never_lets_the_sentinel_through():
    # Defensive branch: even a ref NOT listed as cancelled must be dropped if
    # its type_id is still the sentinel (belt-and-suspenders for a future
    # caller that forgets to track cancellations).
    chosen = {"D1": DECLARE_OPTION_ID}
    assert filter_persistable_choices(chosen, cancelled_refs=set()) == {}


def test_filter_persistable_choices_is_a_pure_passthrough_otherwise():
    chosen = {"D1": "led", "D2": "buzzer"}
    assert filter_persistable_choices(chosen) == chosen


def test_resolve_board_nets_uses_the_connected_board():
    from ui.board_manager import board_manager
    orig_env, orig_model = board_manager.env, board_manager.model
    try:
        board_manager.set_board_manual("arduino", "Uno")
        nets = resolve_board_nets()
        assert {"5V", "GND", "D13", "A0"} <= set(nets)
    finally:
        board_manager.set_board_manual(orig_env, orig_model)


def test_resolve_board_nets_falls_back_for_an_uncatalogued_board():
    from ui.board_manager import board_manager
    orig_env, orig_model = board_manager.env, board_manager.model
    try:
        # esp32 has no entry in _ENV_MODEL_TO_BOARD_ID and env != "arduino"
        # -> board_id_for_env_model returns None -> literal fallback.
        board_manager.set_board_manual("esp32", "ESP32 DevKit v1")
        nets = resolve_board_nets()
        assert nets == (["5V", "3V3", "GND"] + [f"D{i}" for i in range(14)]
                        + [f"A{i}" for i in range(6)])
    finally:
        board_manager.set_board_manual(orig_env, orig_model)


def test_resolve_board_nets_never_raises_when_the_lookup_fails():
    import ui.wiring.boards as boards_mod

    def _boom(board_id):
        raise RuntimeError("simulated lookup failure")

    orig = boards_mod.load_board
    boards_mod.load_board = _boom
    try:
        nets = resolve_board_nets()      # must not raise
        assert nets == (["5V", "3V3", "GND"] + [f"D{i}" for i in range(14)]
                        + [f"A{i}" for i in range(6)])
    finally:
        boards_mod.load_board = orig


def _fake_studio_view():
    """Bind the pure(-ish) StudioView methods used below onto a bare object,
    same pattern as test_skip_refs_lets_the_project_resolution_win: no Qt
    widget construction needed, they only touch `self._wiring_resolutions`
    and their arguments."""
    from ui.studio_view import StudioView
    class _FakeSV:
        _declared_optouts = StudioView._declared_optouts
        _persist_declared_optout = StudioView._persist_declared_optout
        _declared_opt_candidate = StudioView._declared_opt_candidate
    return _FakeSV()


# -- Review finding 2026-07-30 #1 (gear menu dead end): a declared component
# belongs to no electrical category (category_of -> None, is_replaceable ->
# False) and the safety-net attributes were deliberately dropped by
# _apply_declared (is_uncertain_component -> False). Without is_user_declared
# in the gear's `editable` predicate, the gear menu offered no "Modifier..."
# entry -- a dead end. `_on_gear_clicked` needs a live QMenu / gear click and
# isn't reachable headless, so the predicate was extracted into a pure
# module-level helper, `wiring_diagram_dialog.gear_menu_editable(target,
# base_editable)`, called from `_on_gear_clicked` -- this tests THAT helper
# directly, so it is a real guard on the shipped call site, not a mirror of
# it (2026-07-30 re-review: the first version of this test mirrored the
# predicate expression instead of exercising the call site, and passed even
# at db9b8aa where is_user_declared was entirely absent from the path). ----

def test_declared_component_editability_predicate():
    from ui.wiring.wiring_diagram_dialog import gear_menu_editable
    dc.set_registry([_as7341()])
    c = _placeholder()
    apply_saved_resolution(c, "custom:as7341", Netlist(board_id="uno", components=[c]))
    assert is_user_declared(c) is True
    # base_editable=False: nothing else (is_replaceable, is_uncertain_component)
    # sees a declared component -- only is_user_declared can save it.
    assert gear_menu_editable(c, False) is True


def test_gear_menu_editable_is_inert_for_a_non_replaceable_component():
    # A component that is NEITHER user-declared NOR uncertain NOR replaceable
    # (e.g. a resistor) must stay non-editable via this predicate.
    from ui.wiring.wiring_diagram_dialog import gear_menu_editable
    r = Component(ref="R1", type="resistor", fn_id="fn-1", pins=[Pin("A", "D3")])
    assert gear_menu_editable(r, False) is False


def test_gear_menu_editable_respects_base_editable():
    from ui.wiring.wiring_diagram_dialog import gear_menu_editable
    r = Component(ref="R1", type="resistor", fn_id="fn-1", pins=[Pin("A", "D3")])
    assert gear_menu_editable(r, True) is True


# -- Review finding 2026-07-30 #2 (opt-out survives reopening): a saved
# resolution to a NON-custom type could never override the library on
# reload, because a placeholder's `_resolution_key_for` is degenerate
# ((fn_id, "")) and `_already_resolved_refs` deliberately never trusts it
# (see its docstring). Fixed with a header-keyed opt-out persisted in
# `_wiring_resolutions` under a namespaced key, symmetric with the
# declaration path. --------------------------------------------------------

def test_optout_wins_over_the_declaration_on_reapplication():
    dc.set_registry([_as7341()])
    nl = _netlist_with_placeholder()
    changed = apply_library_to_netlist(nl, opt_outs={"as7341.h": "led"})
    assert changed == ["U1"]
    assert nl.by_ref("U1").type == "led"   # opt-out wins, not custom:as7341


def test_optout_pointing_to_a_custom_type_behaves_like_a_declaration():
    other = dc.DeclaredComponent(id="other", name="Other",
                                 headers=("other.h",), pins=())
    dc.set_registry([_as7341(), other])
    nl = _netlist_with_placeholder()
    changed = apply_library_to_netlist(nl, opt_outs={"as7341.h": "custom:other"})
    assert changed == ["U1"]
    assert nl.by_ref("U1").type == "custom:other"


def test_optout_open_pins_warning_only_for_declared_targets():
    # Opting out to "led" leaves the declared-component family entirely:
    # "declared_unconnected_pins" is not this module's business anymore.
    dc.set_registry([_as7341()])
    nl = _netlist_with_placeholder()
    apply_library_to_netlist(nl, opt_outs={"as7341.h": "led"})
    assert nl.warnings == []


def test_declared_optouts_extraction_from_wiring_resolutions():
    from ui.studio_view import _DECLARED_OPTOUT_PREFIX
    fake = _fake_studio_view()
    fake._wiring_resolutions = {
        ("", _DECLARED_OPTOUT_PREFIX + "as7341.h"): "led",
        ("fn-1", "D5"): "buzzer",          # unrelated entry: must be ignored
    }
    assert fake._declared_optouts() == {"as7341.h": "led"}


def test_persist_declared_optout_records_a_non_custom_choice():
    from ui.studio_view import _DECLARED_OPTOUT_PREFIX
    from ui.wiring.declared_apply import OPTOUT_HEADER_ECHO_ATTR
    fake = _fake_studio_view()
    fake._wiring_resolutions = {}
    comp = _placeholder()
    fake._persist_declared_optout(comp, "as7341.h", "led")
    assert fake._wiring_resolutions == {
        ("", _DECLARED_OPTOUT_PREFIX + "as7341.h"): "led"
    }
    # Echoed onto the component so a LATER edit in the same reopening can
    # still find the header even after a transform wipes `attributes`.
    assert comp.attributes[OPTOUT_HEADER_ECHO_ATTR] == "as7341.h"


def test_persist_declared_optout_removes_it_on_redeclaration():
    """Explicit review requirement: re-choosing the declared type must
    remove any earlier opt-out for that header -- otherwise the opt-out
    would keep silently overriding the fresh declaration on next reopen."""
    from ui.studio_view import _DECLARED_OPTOUT_PREFIX
    from ui.wiring.declared_apply import OPTOUT_HEADER_ECHO_ATTR
    fake = _fake_studio_view()
    key = ("", _DECLARED_OPTOUT_PREFIX + "as7341.h")
    fake._wiring_resolutions = {key: "led"}
    comp = _placeholder()
    comp.attributes[OPTOUT_HEADER_ECHO_ATTR] = "as7341.h"
    fake._persist_declared_optout(comp, "as7341.h", "custom:as7341")
    assert key not in fake._wiring_resolutions
    # The echo attribute is deliberately LEFT IN PLACE (review 2026-07-30
    # re-review #1): _apply_declared never restores "header" once a
    # wholesale-replacing transform has wiped it, so popping the echo here
    # would strand the NEXT opt-out with no handle at all. Only the
    # PERSISTED opt-out entry (_wiring_resolutions) needs clearing.
    assert comp.attributes[OPTOUT_HEADER_ECHO_ATTR] == "as7341.h"


def test_persist_declared_optout_handles_the_triple_toggle():
    """Reproduced by review (2026-07-30 re-review #1): custom:as7341 -> led
    -> custom:as7341 -> buzzer in ONE session. Popping
    OPTOUT_HEADER_ECHO_ATTR on re-declare used to strand the 2nd opt-out
    (to buzzer): _declared_opt_candidate found no "header" (wiped by
    _to_led_red) and no echo (just popped) -> the caller's guard
    (`declared_candidate_before and header_before`) silently skipped
    persistence, and reopening reverted the component to custom:as7341."""
    from ui.studio_view import _DECLARED_OPTOUT_PREFIX
    dc.set_registry([_as7341()])
    fake = _fake_studio_view()
    fake._wiring_resolutions = {}
    optout_key = ("", _DECLARED_OPTOUT_PREFIX + "as7341.h")
    c = _placeholder()
    nl = Netlist(board_id="uno", components=[c])

    # 1) declare
    apply_saved_resolution(c, "custom:as7341", nl)

    # 2) opt out to led
    is_cand, header = fake._declared_opt_candidate(c)
    assert (is_cand, header) == (True, "as7341.h")
    apply_saved_resolution(c, "led", nl)
    fake._persist_declared_optout(c, header, "led")
    assert fake._wiring_resolutions.get(optout_key) == "led"

    # 3) re-declare: the persisted opt-out is cleared...
    is_cand, header = fake._declared_opt_candidate(c)
    assert (is_cand, header) == (True, "as7341.h"), "echo must still resolve"
    apply_saved_resolution(c, "custom:as7341", nl)
    fake._persist_declared_optout(c, header, "custom:as7341")
    assert optout_key not in fake._wiring_resolutions

    # 4) ...but a SECOND opt-out, to a DIFFERENT type, must still be
    # persisted -- this is the exact step the bug broke.
    is_cand, header = fake._declared_opt_candidate(c)
    assert (is_cand, header) == (True, "as7341.h"), \
        "the 2nd opt-out must still find its header"
    apply_saved_resolution(c, "buzzer", nl)
    fake._persist_declared_optout(c, header, "buzzer")
    assert fake._wiring_resolutions.get(optout_key) == "buzzer"


def test_declared_opt_candidate_survives_an_attribute_wiping_transform():
    """Literal repro from the review: declare, THEN switch to "led" via the
    gear. The header must be captured BEFORE apply_saved_resolution runs,
    because _to_led_red replaces `attributes` wholesale
    (c.attributes = {"color": "red"}), taking "header" down with it."""
    dc.set_registry([_as7341()])
    fake = _fake_studio_view()
    c = _placeholder()
    nl = Netlist(board_id="uno", components=[c])
    apply_saved_resolution(c, "custom:as7341", nl)        # declare
    assert c.attributes.get("user_declared") is True
    is_candidate, header = fake._declared_opt_candidate(c)  # snapshot BEFORE
    assert is_candidate is True
    assert header == "as7341.h"
    apply_saved_resolution(c, "led", nl)                  # gear -> "led"
    assert "header" not in c.attributes                   # confirms the wipe
    assert header == "as7341.h"                           # snapshot untouched


def test_declared_opt_candidate_uses_the_echo_after_an_earlier_optout():
    """A component already opted out earlier in the SAME reopening (silent
    replay by apply_library_to_netlist) has no "header" attribute left, but
    still carries the echo -- re-choosing custom:as7341 for it must still be
    able to find and clear the opt-out."""
    from ui.wiring.declared_apply import OPTOUT_HEADER_ECHO_ATTR
    fake = _fake_studio_view()
    led = Component(ref="U1", type="led", fn_id="fn-1",
                    pins=[Pin("A", "D3"), Pin("K", "GND")],
                    attributes={"color": "red",
                                OPTOUT_HEADER_ECHO_ATTR: "as7341.h"})
    assert fake._declared_opt_candidate(led) == (True, "as7341.h")


def test_declared_opt_candidate_is_inert_for_ordinary_components():
    fake = _fake_studio_view()
    led = Component(ref="D1", type="led", fn_id="fn-1", pins=[Pin("A", "D5")])
    assert fake._declared_opt_candidate(led) == (False, "")


def test_optout_key_round_trips_through_the_project_serialization():
    """Mirrors StudioView.save_project's `f"{k[0]}|{k[1]}"` serialization and
    the loader's `k_str.split("|", 1)` deserialization (ui/studio_view.py):
    fn_id="" with a pin_net containing "::" and "." must survive intact --
    split() with maxsplit=1 only ever splits on the FIRST "|", and a
    normalized header never contains one."""
    from ui.studio_view import _DECLARED_OPTOUT_PREFIX
    key = ("", _DECLARED_OPTOUT_PREFIX + "adafruit_as7341.h")
    value = "led"
    serialized = {f"{key[0]}|{key[1]}": value}
    restored = {}
    for k_str, v in serialized.items():
        if "|" in k_str:
            fn_id, pin_net = k_str.split("|", 1)
            restored[(fn_id, pin_net)] = v
    assert restored == {key: value}


# -- Review finding 2026-07-30 #3 (latent crash): AmbiguityDialog.apply_choices
# did `dlg.result_component.type_id` unguarded right after `dlg.exec() ==
# Accepted`. result_component is None whenever Accepted is reached without
# going through _on_save (the "Remove" path via existing=..., not wired into
# any caller on this branch -- or any future Accepted path that forgets to
# set it). studio_view._open_declare_dialog already guards against None;
# this exercises the mirrored guard inside AmbiguityDialog itself. ---------

def test_the_form_shows_sda_scl_without_changing_the_stored_net():
    """QA 2026-08-08 : le formulaire n'offrait ni SDA ni SCL, alors qu'un
    débutant cherche la broche imprimée sur sa carte -- même si c'est le même
    trou que A4/A5.

    L'alias est PUREMENT visuel : le combo sépare déjà affichage et valeur
    (`addItem(texte, userData)`), donc le net enregistré ne bouge pas et le
    routage n'est pas touché. `findData` doit continuer de résoudre le net,
    sinon rouvrir une déclaration existante ne présélectionnerait plus rien.
    """
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    dlg = DeclareComponentDialog()
    cb = dlg._rows[0][1]
    shown = {cb.itemData(i): cb.itemText(i) for i in range(cb.count())}
    assert shown.get("A4") == "A4 (SDA)", shown.get("A4")
    assert shown.get("A5") == "A5 (SCL)", shown.get("A5")
    # Les autres broches ne gagnent PAS de parenthèse.
    assert shown.get("A3") == "A3", shown.get("A3")
    assert shown.get("5V") == "5V", shown.get("5V")
    # La valeur reste le net, et reste retrouvable.
    assert cb.findData("A4") >= 0
    assert cb.findData("A5") >= 0


def test_the_advanced_modal_can_edit_a_declared_component():
    """QA G4 (2026-08-08) : le crayon n existait que sur les tuiles du mode
    Debutant. En Intermediaire/Avance, le schema n offrait AUCUN moyen de
    corriger une declaration -- alors que la procedure annonce les deux
    chemins comme equivalents. Corriger un composant ne doit pas dependre du
    mode dans lequel on se trouve : « le mode n est qu un affichage ».

    Depuis le passage aux cards (2026-08-13), le crayon n est plus UN bouton de
    section grise selon le choix courant : chaque card porte le sien et il agit
    sur ELLE. Le comportement verifie reste le meme -- le crayon d une entree
    declaree rouvre le formulaire sur CETTE entree -- mais il est atteint par
    le signal de la card, pas par un bouton unique."""
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    entry = _as7341()
    dc.set_registry([entry])
    c = _placeholder()
    nl = Netlist(board_id="uno", components=[c])
    modal = AmbiguityDialog([c], netlist=nl)
    picker = modal._pickers.get(c.ref)
    assert picker is not None, "aucun picker dans la modale avancee"

    card = picker.card_for(entry.type_id)
    assert card is not None, (
        f"l entree declaree n est pas proposee : {picker.visible_type_ids()}")
    assert card._btn_edit is not None, "la card n a pas de crayon"
    assert card._btn_edit.isEnabled(), "le crayon d une entree declaree est grise"

    # Le crayon repart avec le TYPE de cablage (`custom:<id>`), pas la cle nue
    # de la fiche : c est ce que la modale sait router vers « mon entree ».
    # On intercepte le routeur SUR L INSTANCE (le branchement appelle
    # `self._edit_component`, donc l attribut d instance gagne) : sans ca le
    # clic ouvrirait vraiment le formulaire, dont l `exec()` bloque le test.
    vus: list = []
    modal._edit_component = lambda ref, tid: vus.append((ref, tid))
    card._btn_edit.click()
    assert vus == [(c.ref, entry.type_id)], vus

    # Et un composant CURE a lui aussi son crayon : le modifier, c est le
    # reprendre a son compte (QA I4) -- jamais un bouton mort.
    autre = next(t for t in picker.visible_type_ids() if t != entry.type_id)
    assert picker.card_for(autre)._btn_edit.isEnabled(), autre


def test_the_name_is_always_a_keyword():
    """QA G4bis (2026-08-08) : renommer une entree la rendait introuvable sous
    son NOUVEAU nom -- celui que l onglet affiche et que l utilisateur
    reecrira.

    Deux comportements deliberes se neutralisaient : la synchronisation
    nom -> mots-cles s arrete des que les mots-cles different du defaut (ne pas
    ecraser une saisie), et l enregistrement les UNIONNE (ne pas oublier ce
    que la bibliotheque savait). Donc le PREMIER renommage laisse deux
    mots-cles, l entree parait des lors personnalisee, et tous les suivants
    laissaient le nom en arriere."""
    _use_temp_library()
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    entry = dc.DeclaredComponent(
        id="x", name="AS7341V2", headers=("x.h",),
        pins=(dc.DeclaredPin("1", "signal", ""),),
        lib="", keywords=("AS7341", "AS7341V2"))    # <- deja « personnalise »
    dc.set_registry([entry])
    dc.save([entry])
    dlg = DeclareComponentDialog(existing=entry)
    dlg._name.setText("AS7341V3")
    dlg._on_save()
    saved = next(c for c in dc.load() if c.id == "x")
    kws = {k.casefold() for k in saved.keywords}
    assert "as7341v3" in kws, saved.keywords      # le nouveau nom declenche
    assert "as7341" in kws, saved.keywords        # ... sans perdre les anciens
    assert "as7341v2" in kws, saved.keywords


def test_the_name_is_not_duplicated_in_the_keywords():
    _use_temp_library()
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    dlg = DeclareComponentDialog()
    dlg._name.setText("Mon Capteur")
    dlg._on_save()
    saved = dc.load()[0]
    assert [k.casefold() for k in saved.keywords].count("mon capteur") == 1, \
        saved.keywords


def test_the_library_name_cannot_be_typed_by_hand():
    """QA I4 (2026-08-08) : saisi a la main, un nom de librairie est faux a une
    lettre pres, et l erreur ne se voit qu a la generation suivante -- vu en
    QA I5, ou « Grove Ultrasonic » (au lieu de « Grove Ultrasonic Ranger »)
    etait introuvable au registre. Il passe donc par la recherche."""
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    dlg = DeclareComponentDialog()
    assert dlg._lib.isReadOnly(), "le champ librairie reste editable"
    assert dlg._btn_pick_lib is not None       # ... mais choisissable
    assert dlg._lib.placeholderText()          # « a determiner » quand vide


def test_a_declared_library_can_be_cleared():
    """Un composant peut legitimement ne demander AUCUNE librairie. Le champ
    etant en lecture seule, l effacer a la main n est plus possible : sans ce
    bouton, un choix serait definitif."""
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    entry = dc.DeclaredComponent(id="x", name="X", headers=(), pins=(),
                                 lib="Grove Ultrasonic Ranger",
                                 keywords=("X",))
    dlg = DeclareComponentDialog(existing=entry)
    assert dlg._lib.text() == "Grove Ultrasonic Ranger"
    dlg._btn_clear_lib.click()
    assert dlg._lib.text() == ""


def test_the_form_opens_with_savable_pin_names():
    """QA G3 (2026-08-08) : le formulaire REFUSE d'enregistrer tant qu'une
    broche n'a pas de nom. Ca bloquait le cas ou on declare un composant pour
    lui apprendre sa BIBLIOTHEQUE, pas pour le dessiner -- il fallait inventer
    des noms de broches pour pouvoir enregistrer une lib.

    Un numero n'invente rien (c'est ce que le dessin generique affiche de
    toute facon) et reste modifiable ; la regle « tous distincts » tient."""
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    dlg = DeclareComponentDialog()
    labels = [le.text().strip() for le, _ in dlg._rows]
    assert all(labels), labels                       # aucun vide
    assert len(set(labels)) == len(labels), labels   # tous distincts


def test_added_pins_are_named_too():
    """Changer le nombre de broches ne doit pas re-creer des lignes vides :
    sinon le blocage revient des qu'on passe de 2 a 6."""
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    dlg = DeclareComponentDialog()
    idx = dlg._count.findData(6)
    assert idx >= 0, "6 broches devrait etre proposable"
    dlg._count.setCurrentIndex(idx)
    labels = [le.text().strip() for le, _ in dlg._rows]
    assert len(labels) == 6, labels
    assert all(labels) and len(set(labels)) == 6, labels


def test_a_reopened_declaration_keeps_its_own_pin_names():
    """Le defaut ne doit s'appliquer qu'aux lignes VIDES : rouvrir une
    declaration existante doit montrer SES noms, pas « 1 », « 2 »…"""
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    entry = dc.DeclaredComponent(
        id="x", name="X", headers=("x.h",),
        pins=(dc.DeclaredPin("VCC", "vcc", "5V"),
              dc.DeclaredPin("GND", "gnd", "GND")),
        lib="", keywords=("X",))
    dlg = DeclareComponentDialog(existing=entry)
    assert [le.text() for le, _ in dlg._rows] == ["VCC", "GND"]


def test_apply_choices_survives_a_none_result_component():
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    from ui.wiring.declare_component_dialog import (
        DECLARE_OPTION_ID, DeclareComponentDialog,
    )

    c = _placeholder()
    nl = Netlist(board_id="uno", components=[c])
    modal = AmbiguityDialog([c], netlist=nl)
    modal._chosen_type[c.ref] = DECLARE_OPTION_ID

    # Simulates the "Remove" path (Accepted, result_component left at its
    # None default) without needing existing= wiring: monkeypatch exec().
    orig_exec = DeclareComponentDialog.exec
    DeclareComponentDialog.exec = lambda self: QDialog.DialogCode.Accepted
    try:
        modal.apply_choices(nl)     # must NOT raise AttributeError
    finally:
        DeclareComponentDialog.exec = orig_exec
    assert c.type == "as7341"       # untouched: nothing to apply


# -- Review finding 2026-07-30 #6 (untranslated badge): the advanced
# dropdown hardcoded the French "(perso)" for declared entries instead of
# reusing the localized badge like the beginner tiles. Depuis les cards
# (2026-08-13) la pastille est celle de l onglet « Composants »
# (`components_filter_declared`) : meme pastille, meme mot, quel que soit
# l ecran. Le defaut vise reste le meme -- un badge en dur en francais. ------

def test_advanced_declared_badge_is_translated():
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    from ui.i18n import lang_manager

    entry = _as7341()
    dc.set_registry([entry])
    led = Component(ref="D1", type="led", fn_id="fn-1",
                    pins=[Pin("A", "D5"), Pin("K", "GND")],
                    attributes={"_confidence": "low"})
    nl = Netlist(board_id="uno", components=[led])
    orig_lang = lang_manager.lang
    vus = set()
    try:
        for lg in ("fr", "en", "es", "it"):
            lang_manager.set_language(lg)
            dlg = AmbiguityDialog([led], netlist=nl)
            card = dlg._pickers["D1"].card_for(entry.type_id)
            assert card is not None, (lg, dlg._pickers["D1"].visible_type_ids())
            assert card._lbl_badge is not None, (
                lg, "aucune pastille « perso » sur une entree declaree")
            texte = card._lbl_badge.text()
            assert texte == lang_manager.current.components_filter_declared, \
                (lg, texte)
            vus.add(texte)
    finally:
        lang_manager.set_language(orig_lang)
    assert len(vus) > 1, f"la pastille est la meme dans les 4 langues : {vus}"


# -- Review finding 2026-07-30 #4 (forward-compat data loss): load() returns
# [] for an unknown schema version OR a corrupt file, indistinguishable from
# "no library yet" -- _on_save then wrote a fresh version-1 file containing
# only the new entry, silently destroying whatever a future build had
# written. library_file_unusable() lets the form refuse to save instead. ---

def test_library_file_unusable_false_when_absent():
    d = Path(tempfile.mkdtemp(prefix="promptuino-lib-"))
    dc._LIBRARY_PATH = d / "nope.json"
    assert dc.library_file_unusable() is False


def test_library_file_unusable_true_for_unknown_version():
    _use_temp_library(json.dumps({"version": 99, "components": []}))
    assert dc.library_file_unusable() is True


def test_library_file_unusable_true_for_corrupt_json():
    _use_temp_library("{ not json at all")
    assert dc.library_file_unusable() is True


def test_library_file_unusable_false_for_a_valid_library():
    _use_temp_library()
    dc.save([_as7341()])
    assert dc.library_file_unusable() is False


def _grove() -> "dc.DeclaredComponent":
    """A component whose name has NO digits -- the Seeed case that killed the
    'looks like a part number' rule."""
    return dc.DeclaredComponent(
        id="grove-moisture-sensor", name="Grove Moisture Sensor",
        lib="Grove Moisture Sensor",
        keywords=("Grove Moisture Sensor", "moisture", "humidite du sol"),
        headers=("grove_moisture_sensor.h",),
        pins=(dc.DeclaredPin("VCC", "vcc", "5V"),
              dc.DeclaredPin("GND", "gnd", "GND"),
              dc.DeclaredPin("SIG", "signal", "A0")))


def test_new_fields_roundtrip():
    _use_temp_library()
    dc.save([_grove()])
    back = dc.load()
    assert len(back) == 1
    assert back[0] == _grove()


def test_library_written_before_this_feature_still_loads():
    """No migration: an entry with no `lib` nor `keywords` still loads, with
    lib="" and keywords derived from the name."""
    _use_temp_library(json.dumps({
        "version": dc._SCHEMA_VERSION,
        "components": [{"id": "as7341", "name": "AS7341",
                        "headers": ["as7341.h"],
                        "pins": [{"label": "VCC", "role": "vcc", "net": "5V"}]}],
    }))
    back = dc.load()
    assert len(back) == 1
    assert back[0].lib == ""
    assert back[0].keywords == ("AS7341",)


def test_default_keywords_is_just_the_name():
    assert dc.default_keywords("Grove Moisture Sensor") == ("Grove Moisture Sensor",)
    assert dc.default_keywords("  ") == ()


def test_upsert_merges_instead_of_suffixing():
    """The rule CHANGED (2026-07-30): a slug already in use UPDATES the
    entry, it no longer creates `as7341-2`. That suffix is what made a
    correction get lost -- `find_by_header` returns the FIRST match."""
    first = dc.DeclaredComponent(
        id="as7341", name="AS7341", lib="", keywords=("AS7341",),
        headers=("as7341.h",),
        pins=(dc.DeclaredPin("VCC", "vcc", "5V"),))
    second = dc.DeclaredComponent(
        id="as7341", name="AS7341", lib="Adafruit AS7341",
        keywords=("AS7341", "spectre"),
        headers=("adafruit_as7341.h",),
        pins=(dc.DeclaredPin("VCC", "vcc", "5V"),
              dc.DeclaredPin("GND", "gnd", "GND")))
    out = dc.upsert([first], second)
    assert len(out) == 1, [c.id for c in out]
    merged = out[0]
    assert merged.id == "as7341"
    assert merged.lib == "Adafruit AS7341"
    assert len(merged.pins) == 2                       # the new pinout wins
    assert set(merged.headers) == {"as7341.h", "adafruit_as7341.h"}
    assert set(merged.keywords) == {"AS7341", "spectre"}


def test_upsert_appends_a_genuinely_new_entry():
    out = dc.upsert([_grove()], _as7341())
    assert {c.id for c in out} == {"grove-moisture-sensor", "as7341"}


def test_match_prompt_on_a_multiword_name_without_digits():
    dc.set_registry([_grove()])
    hit = dc.match_prompt("lis l'humidite avec mon Grove Moisture Sensor")
    assert hit is not None and hit.id == "grove-moisture-sensor"


def test_match_prompt_on_a_single_keyword():
    dc.set_registry([_grove()])
    assert dc.match_prompt("mesure la moisture du pot") is not None


def test_match_prompt_respects_word_boundaries():
    dc.set_registry([_grove()])
    # "moisture" must not match inside a longer word.
    assert dc.match_prompt("le mot moistureproof ne compte pas") is None


def test_match_prompt_is_accent_and_case_insensitive():
    dc.set_registry([_grove()])
    assert dc.match_prompt("HUMIDITE DU SOL") is not None
    assert dc.match_prompt("humidité du sol") is not None


def test_match_prompt_returns_none_on_collision():
    """Two entries triggered => we inject nothing and write nothing: we
    would not know which entry the result belongs to."""
    other = dc.DeclaredComponent(
        id="autre", name="Autre", lib="", keywords=("moisture",),
        headers=(), pins=(dc.DeclaredPin("S", "signal", ""),))
    dc.set_registry([_grove(), other])
    assert dc.match_prompt("mesure la moisture") is None
    assert len(dc.matches_in_prompt("mesure la moisture")) == 2


def test_match_prompt_on_a_name_ending_with_a_non_word_character():
    """`\\b` only marks a boundary after a non-word character if the NEXT
    character is a word character, so a component named "TinyGPS++" was never
    recognised -- not even by its own name written verbatim in the prompt. No
    trigger, no write-back, the card stayed on "library to determine" for ever,
    and nothing said so (the keywords field displayed the right text)."""
    e = dc.DeclaredComponent(
        id="tinygps", name="TinyGPS++", lib="", keywords=("TinyGPS++",),
        headers=(), pins=(dc.DeclaredPin("TX", "signal", "D3"),))
    dc.set_registry([e])
    assert dc.match_prompt("utilise mon TinyGPS++ pour la position") is not None, \
        "a component is not recognised by its own verbatim name"
    assert dc.match_prompt("mon TinyGPS++, puis une LED") is not None
    assert dc.match_prompt("mon TinyGPS++") is not None          # end of string


def test_match_prompt_on_a_name_with_non_word_characters_inside():
    """Same defect, with the non-word characters INSIDE the name as well as at
    its edge -- and the existing protection must keep holding: "moisture" must
    still not match inside "moistureproof"."""
    e = dc.DeclaredComponent(
        id="grove-x", name="Capteur (Grove)", lib="",
        keywords=("Capteur (Grove)", "moisture"), headers=(),
        pins=(dc.DeclaredPin("S", "signal", "A0"),))
    dc.set_registry([e])
    assert dc.match_prompt("lis le Capteur (Grove) svp") is not None, \
        "a name ending on a non-word character never matches"
    assert dc.match_prompt("un Capteur (Grove) v2") is not None
    assert dc.match_prompt("le mot moistureproof ne compte pas") is None


def test_match_prompt_empty_registry_or_prompt():
    dc.set_registry([])
    assert dc.match_prompt("n'importe quoi") is None
    dc.set_registry([_grove()])
    assert dc.match_prompt("") is None


def test_entry_for_header_finds_the_existing_entry():
    """Opening the form from a box whose header already matches an entry
    must edit THAT entry, not create a blank sheet (otherwise we would
    recreate the duplicate `upsert` was introduced to remove)."""
    from ui.wiring.declare_component_dialog import entry_for_header
    dc.set_registry([_as7341()])
    assert entry_for_header("Adafruit/AS7341.H") is not None
    assert entry_for_header("Autre.h") is None
    assert entry_for_header("") is None


def test_prefill_without_a_component_yields_unconnected_pins():
    """Creating from the tab: no schema, so "VCC -> 5V" has no meaning. All
    pins start unconnected."""
    from ui.wiring.declare_component_dialog import prefill_pins
    assert prefill_pins(None, _NETS) == []


def test_saving_a_second_time_updates_instead_of_duplicating():
    """End to end for the changed rule: saving the same name twice leaves
    ONE entry."""
    _use_temp_library()
    first = dc.DeclaredComponent(
        id="as7341", name="AS7341", lib="", keywords=("AS7341",),
        headers=("as7341.h",), pins=(dc.DeclaredPin("VCC", "vcc", "5V"),))
    dc.save(dc.upsert(dc.load(), first))
    second = dc.DeclaredComponent(
        id="as7341", name="AS7341", lib="Adafruit AS7341",
        keywords=("AS7341",), headers=("adafruit_as7341.h",),
        pins=(dc.DeclaredPin("VCC", "vcc", "5V"),
              dc.DeclaredPin("GND", "gnd", "GND")))
    dc.save(dc.upsert(dc.load(), second))
    back = dc.load()
    assert len(back) == 1, [c.id for c in back]
    assert back[0].lib == "Adafruit AS7341"
    assert set(back[0].headers) == {"as7341.h", "adafruit_as7341.h"}


def test_creating_under_a_renamed_entrys_old_name_does_not_destroy_it():
    """Renaming in edit mode keeps the id (no orphan) -- but it leaves the OLD
    name's slug held by an entry that no longer bears that name, and the next
    creation under that old name MERGED into it: name and pinout replaced while
    the learned #include and library stayed attached. Silent data loss AND a
    wrong wiring attachment (every schema including capteur_a.h then displayed
    "Capteur A" with A's pinout), i.e. exactly what the merge rule was meant to
    cure. The premise "two components with the same name are the same
    component" only holds while the id follows the name."""
    from ui.wiring.declare_component_dialog import DeclareComponentDialog

    def _fill(dlg, name, labels, lib=None):
        dlg._name.setText(name)
        if lib is not None:
            dlg._lib.setText(lib)
        dlg._count.setCurrentIndex(dlg._count.findData(len(labels)))
        for (le, _cb), label in zip(dlg._rows, labels):
            le.setText(label)
        dlg._on_save()

    _use_temp_library()
    a = dc.DeclaredComponent(
        id="capteur-a", name="Capteur A", lib="", keywords=("Capteur A",),
        headers=("capteur_a.h",),
        pins=(dc.DeclaredPin("5V", "vcc", "5V"),
              dc.DeclaredPin("A1", "signal", "A1")))
    dc.save([a]); dc.set_registry([a])
    # 2) pencil -> rename to "Capteur B": the id is preserved on purpose.
    _fill(DeclareComponentDialog(None, existing=a, board_nets=_NETS),
          "Capteur B", ["5V", "A1"], lib="LibB")
    # 3) tab -> "Describe a component" named like the OLD name.
    _fill(DeclareComponentDialog(None, board_nets=_NETS),
          "Capteur A", ["D2", "D3"])

    back = {c.id: c for c in dc.load()}
    assert len(back) == 2, sorted(back)
    assert back["capteur-a"].name == "Capteur B", back["capteur-a"].name
    assert back["capteur-a"].lib == "LibB"
    assert dc.find_by_header("capteur_a.h").name == "Capteur B", \
        dc.find_by_header("capteur_a.h").name


def test_redeclaring_the_same_name_still_merges():
    """The suffix must come back ONLY when the two components are genuinely
    distinct: re-declaring the same name is still an update, which is the whole
    point of the 2026-07-30 merge rule."""
    items = [dc.DeclaredComponent(
        id="capteur-a", name="Capteur A", lib="", keywords=("Capteur A",),
        headers=("capteur_a.h",), pins=(dc.DeclaredPin("S", "signal", "D2"),))]
    assert dc.new_entry_id("Capteur A", items) == "capteur-a"
    assert dc.new_entry_id("  capteur a  ", items) == "capteur-a"   # same slug
    assert dc.new_entry_id("Capteur B", items) == "capteur-b"
    assert dc.new_entry_id("Capteur A", []) == "capteur-a"


def test_renaming_in_edit_mode_keeps_the_keywords_in_sync():
    """`_keywords_dirty` must mean "the user typed in this field", not "we are
    editing": seeded to True in edit mode, the name->keywords sync was dead
    even when the field had never been touched, so renaming "Foo" to "Bar" left
    keywords=("Foo",) -- the component stayed recognised under its old name and
    not under the new one. A field the user DID customise must still be left
    alone by a rename."""
    from ui.wiring.declare_component_dialog import DeclareComponentDialog
    pristine = dc.DeclaredComponent(
        id="foo", name="Foo", lib="", keywords=("Foo",), headers=("foo.h",),
        pins=(dc.DeclaredPin("S", "signal", "D2"),))
    dlg = DeclareComponentDialog(None, existing=pristine, board_nets=_NETS)
    assert dlg._keywords.text() == "Foo"
    dlg._name.setText("Bar")
    assert dlg._keywords.text() == "Bar", dlg._keywords.text()

    customised = replace(pristine, keywords=("Foo", "mon capteur maison"))
    dlg2 = DeclareComponentDialog(None, existing=customised, board_nets=_NETS)
    dlg2._name.setText("Bar")
    assert dlg2._keywords.text() == "Foo, mon capteur maison", \
        dlg2._keywords.text()


TESTS = [
    test_declared_component_editability_predicate,
    test_gear_menu_editable_is_inert_for_a_non_replaceable_component,
    test_gear_menu_editable_respects_base_editable,
    test_optout_wins_over_the_declaration_on_reapplication,
    test_optout_pointing_to_a_custom_type_behaves_like_a_declaration,
    test_optout_open_pins_warning_only_for_declared_targets,
    test_declared_optouts_extraction_from_wiring_resolutions,
    test_persist_declared_optout_records_a_non_custom_choice,
    test_persist_declared_optout_removes_it_on_redeclaration,
    test_persist_declared_optout_handles_the_triple_toggle,
    test_declared_opt_candidate_survives_an_attribute_wiping_transform,
    test_declared_opt_candidate_uses_the_echo_after_an_earlier_optout,
    test_declared_opt_candidate_is_inert_for_ordinary_components,
    test_optout_key_round_trips_through_the_project_serialization,
    test_the_form_shows_sda_scl_without_changing_the_stored_net,
    test_the_name_is_always_a_keyword,
    test_the_name_is_not_duplicated_in_the_keywords,
    test_the_advanced_modal_can_edit_a_declared_component,
    test_the_library_name_cannot_be_typed_by_hand,
    test_a_declared_library_can_be_cleared,
    test_the_form_opens_with_savable_pin_names,
    test_added_pins_are_named_too,
    test_a_reopened_declaration_keeps_its_own_pin_names,
    test_apply_choices_survives_a_none_result_component,
    test_advanced_declared_badge_is_translated,
    test_library_file_unusable_false_when_absent,
    test_library_file_unusable_true_for_unknown_version,
    test_library_file_unusable_true_for_corrupt_json,
    test_library_file_unusable_false_for_a_valid_library,
    test_type_id_uses_the_prefix,
    test_slugify_normalizes_and_dedups,
    test_drawable_pin_counts_match_the_layout,
    test_role_is_derived_from_net_then_label,
    test_normalize_header_drops_path_and_case,
    test_roundtrip_save_load,
    test_corrupt_file_is_ignored,
    test_invalid_utf8_bytes_are_ignored,
    test_unknown_version_is_ignored,
    test_missing_file_is_empty_not_an_error,
    test_malformed_records_are_skipped,
    test_find_by_type_and_header,
    test_lookup_resolves_a_declared_component,
    test_lookup_resolves_a_declared_dip,
    test_lookup_unknown_declared_type_is_none,
    test_lookup_still_resolves_builtin_types,
    test_role_of_works_for_declared_types,
    test_applying_a_declaration_rewires_and_cleans_up,
    test_applying_an_unknown_declaration_leaves_the_component_alone,
    test_a_declared_component_stays_editable,
    test_the_library_is_offered_on_an_ordinary_component,
    test_a_non_replaceable_component_stays_empty,
    test_going_back_from_declared_to_a_builtin_type,
    test_instructions_use_the_declared_name,
    test_reapplication_by_header,
    test_reapplication_on_a_presumed_i2c_box,
    test_obsolete_warnings_are_dropped_and_open_pins_reported,
    test_a_fully_wired_declaration_reports_nothing,
    test_skip_refs_lets_the_project_resolution_win,
    test_unknown_header_changes_nothing,
    test_a_declared_component_can_never_be_undrawable,
    test_declared_unconnected_pins_label_exists_in_all_languages,
    test_prefill_uses_the_presumed_i2c_pins,
    test_prefill_uses_the_constructor_pins_seen_in_the_code,
    test_prefill_ignores_constructor_pins_absent_from_the_board,
    test_a_declared_component_is_offered_on_any_ambiguous_pin,
    test_a_placeholder_is_never_left_without_candidates,
    test_filter_persistable_choices_drops_cancelled_declarations,
    test_filter_persistable_choices_never_lets_the_sentinel_through,
    test_filter_persistable_choices_is_a_pure_passthrough_otherwise,
    test_resolve_board_nets_uses_the_connected_board,
    test_resolve_board_nets_falls_back_for_an_uncatalogued_board,
    test_resolve_board_nets_never_raises_when_the_lookup_fails,
    test_new_fields_roundtrip,
    test_library_written_before_this_feature_still_loads,
    test_default_keywords_is_just_the_name,
    test_upsert_merges_instead_of_suffixing,
    test_upsert_appends_a_genuinely_new_entry,
    test_match_prompt_on_a_multiword_name_without_digits,
    test_match_prompt_on_a_single_keyword,
    test_match_prompt_respects_word_boundaries,
    test_match_prompt_is_accent_and_case_insensitive,
    test_match_prompt_returns_none_on_collision,
    test_match_prompt_on_a_name_ending_with_a_non_word_character,
    test_match_prompt_on_a_name_with_non_word_characters_inside,
    test_match_prompt_empty_registry_or_prompt,
    test_entry_for_header_finds_the_existing_entry,
    test_prefill_without_a_component_yields_unconnected_pins,
    test_saving_a_second_time_updates_instead_of_duplicating,
    test_creating_under_a_renamed_entrys_old_name_does_not_destroy_it,
    test_redeclaring_the_same_name_still_merges,
    test_renaming_in_edit_mode_keeps_the_keywords_in_sync,
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
