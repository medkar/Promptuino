"""Guards for the short name drawn inside a component box.

Standalone script, like the rest of the suite: `python scripts/test_component_names.py`.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring import component_names as cn
from ui.wiring.layout.component_catalog import CATALOG
from ui.component_registry import registry

LANGS = ("fr", "en", "es", "it")


def _drawable_types() -> set[str]:
    """Every type that can end up drawn in a box: the wiring catalogue plus
    every registry component that has something to wire."""
    return set(CATALOG) | {c.id for c in registry() if c.wiring != "none"}


# ─── Comportement ────────────────────────────────────────────────────────

def test_a_universal_name_is_the_same_in_every_language():
    for lang in LANGS:
        assert cn.short_name("ds18b20", lang) == "DS18B20"


def test_a_localized_name_follows_the_language():
    assert cn.short_name("relay", "fr") == "Relais"
    assert cn.short_name("relay", "en") == "Relay"
    assert cn.short_name("relay", "es") == "Relé"
    assert cn.short_name("relay", "it") == "Relè"


def test_an_unknown_language_falls_back_to_french():
    assert cn.short_name("relay", "de") == "Relais"


def test_an_unknown_type_with_no_fallback_yields_nothing():
    assert cn.short_name("pas_un_type", "fr") == ""


def test_the_fallback_is_truncated_so_a_declared_name_never_overflows():
    # A user-declared component carries a name typed by the user. We cannot
    # curate it, so it must be cut.
    got = cn.short_name("custom:x", "fr",
                        fallback="Mon capteur Grove tres long")
    assert got == "Mon capteur…", got
    assert len(got) <= cn.MAX_CHARS


def test_the_ellipsis_counts_inside_the_budget():
    got = cn.short_name("custom:x", "fr", fallback="x" * 40)
    assert len(got) == cn.MAX_CHARS, f"{got!r} = {len(got)}"


def test_truncation_leaves_no_space_before_the_ellipsis():
    assert cn.fit("Mon capteur Grove") == "Mon capteur…"


def test_a_name_that_exactly_fits_is_not_touched():
    exact = "a" * cn.MAX_CHARS
    assert cn.fit(exact) == exact


# ─── Gardes ──────────────────────────────────────────────────────────────

def test_guard_1_every_drawable_type_has_a_short_name():
    missing = _drawable_types() - cn.known_types()
    assert not missing, f"types dessinables sans nom court : {sorted(missing)}"


def test_guard_1b_no_short_name_for_a_type_that_cannot_be_drawn():
    # Keeps the tables from accumulating dead entries as the catalogue moves.
    extra = cn.known_types() - _drawable_types()
    assert not extra, f"noms courts orphelins : {sorted(extra)}"


def test_guard_2_every_short_name_fits_the_budget_in_all_four_languages():
    too_long = []
    for t in sorted(cn.known_types()):
        for lang in LANGS:
            name = cn.short_name(t, lang)
            assert name, f"nom vide pour {t}/{lang}"
            if len(name) > cn.MAX_CHARS:
                too_long.append(f"{t}/{lang} = {len(name)} ({name!r})")
    assert not too_long, "noms trop longs : " + ", ".join(too_long)


def test_guard_3_the_fallback_is_safe_too():
    # short_name falls back on CatalogEntry.name. A net that overflowed the
    # day it is used would be no net at all.
    too_long = []
    for key, entry in sorted(CATALOG.items()):
        name = getattr(entry, "name", "") or ""
        if len(name) > cn.MAX_CHARS:
            too_long.append(f"{key} = {len(name)} ({name!r})")
    assert not too_long, "noms de catalogue trop longs : " + ", ".join(too_long)


def test_guard_4_a_type_belongs_to_exactly_one_table():
    both = set(cn._UNIVERSAL_NAME) & set(cn._LOCALIZED_NAME)
    assert not both, f"types dans les deux tables : {sorted(both)}"


def test_the_renderer_draws_the_short_name_in_the_requested_language():
    """End-to-end: a real scene, rendered, must carry the short localized
    name -- not the raw catalogue name."""
    from pathlib import Path
    from ui.wiring.layout.layout import place_scene
    from ui.wiring.layout.renderer import SceneRenderer

    root = Path(__file__).resolve().parents[1]
    board = root / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
    netlist = [
        {"ref": "K1", "type": "relay", "pins": [
            {"name": "IN", "net": "D2"},
            {"name": "VCC", "net": "5V"},
            {"name": "GND", "net": "GND"},
        ]},
    ]
    scene = place_scene(netlist, board)

    svg_fr = SceneRenderer(scene, [], lang="fr").render()
    assert ">Relais<" in svg_fr, "le nom francais n'est pas dans le SVG"

    svg_it = SceneRenderer(scene, [], lang="it").render()
    assert ">Relè<" in svg_it, "le nom italien n'est pas dans le SVG"

    # The raw identifier must be gone for good.
    assert "RELAY" not in svg_fr


def test_an_unrecognized_type_gets_a_readable_fallback_name():
    """A placeholder built from an unknown #include must not be cut
    mid-word, nor keep its underscores."""
    from ui.wiring.layout.component_catalog import resolve_generic
    pins = [{"name": "OUT", "net": "D2"}, {"name": "GND", "net": "GND"},
            {"name": "VCC", "net": "5V"}]
    entry = resolve_generic("my_weird_sensor", pins)
    assert entry is not None
    assert "_" not in entry.name, entry.name
    # No blind cut at 10: fit() applies the real budget, ellipsis included.
    assert entry.name == "my weird sensor", entry.name
    assert cn.fit(entry.name) == "my weird sen…", cn.fit(entry.name)


TESTS = [
    test_a_universal_name_is_the_same_in_every_language,
    test_a_localized_name_follows_the_language,
    test_an_unknown_language_falls_back_to_french,
    test_an_unknown_type_with_no_fallback_yields_nothing,
    test_the_fallback_is_truncated_so_a_declared_name_never_overflows,
    test_the_ellipsis_counts_inside_the_budget,
    test_truncation_leaves_no_space_before_the_ellipsis,
    test_a_name_that_exactly_fits_is_not_touched,
    test_guard_1_every_drawable_type_has_a_short_name,
    test_guard_1b_no_short_name_for_a_type_that_cannot_be_drawn,
    test_guard_2_every_short_name_fits_the_budget_in_all_four_languages,
    test_guard_3_the_fallback_is_safe_too,
    test_guard_4_a_type_belongs_to_exactly_one_table,
    test_the_renderer_draws_the_short_name_in_the_requested_language,
    test_an_unrecognized_type_gets_a_readable_fallback_name,
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
