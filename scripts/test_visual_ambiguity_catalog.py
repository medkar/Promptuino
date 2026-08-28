"""Tests du catalogue de la modale d'ambiguite elargie (Priorite 1)."""
from __future__ import annotations
import ast
import re
import sys, types
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ui_pkg = types.ModuleType("ui"); ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.visual_ambiguity_catalog import (
    GENERIC_OUTPUT_OPTIONS, label_for, examples_for, dialog_label,
    DIALOG_LABELS,
)

_LANGS = ("fr", "en", "es", "it")


def test_four_options_present():
    ids = [o.option_id for o in GENERIC_OUTPUT_OPTIONS]
    assert ids == ["led", "buzzer", "servo", "dc_motor"], ids


def test_every_icon_resolves():
    for o in GENERIC_OUTPUT_OPTIONS:
        has_file = o.svg_path is not None and o.svg_path.exists()
        has_inline = bool(o.svg_inline)
        assert has_file or has_inline, f"{o.option_id}: aucune icone"
        # SVG inline -> doit etre du XML bien forme (M2 : attrape un SVG
        # casse par une edition future, ce que bool() ne verrait pas).
        if has_inline:
            ET.fromstring(o.svg_inline)


def test_pin_placeholder_in_templates():
    # M3 : les libelles parametres doivent garder leur {pin} dans les 4
    # langues, sinon .format(pin=...) leverait/produirait un texte casse.
    for key in ("output_on_pin", "motor_question"):
        for lang in _LANGS:
            tmpl = dialog_label(key, lang)
            assert "{pin}" in tmpl, f"{key}/{lang} : placeholder {{pin}} manquant"
            assert "D3" in tmpl.format(pin="D3")


def test_labels_all_langs():
    for o in GENERIC_OUTPUT_OPTIONS:
        for lang in _LANGS:
            assert label_for(o, lang), f"{o.option_id}/{lang} label vide"
            assert examples_for(o, lang), f"{o.option_id}/{lang} exemples vides"


def test_dialog_labels_present():
    for key in ("title", "subtitle", "cancel", "validate",
                "output_on_pin", "motor_question", "motor_yes", "motor_no",
                "regroup_banner", "regroup_button"):
        for lang in _LANGS:
            assert dialog_label(key, lang), f"{key}/{lang} manquant"


def _dialog_label_calls(py_file: Path) -> set[str]:
    """Toutes les cles `dialog_label("...", lang)` litterales appelees dans
    un fichier, par AST (pas de regex : une cle construite dynamiquement ne
    doit pas etre confondue avec une chaine litterale)."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name != "dialog_label" or not node.args:
            continue
        arg0 = node.args[0]
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            keys.add(arg0.value)
    return keys


def test_every_dialog_label_call_has_an_entry():
    """LA garde (2026-08-11, meme motif que test_warning_templates.py) : un
    appel `dialog_label("cle", lang)` dont la cle est absente de
    DIALOG_LABELS retombe sur son repli francais dans les 4 langues, en
    silence -- c'est exactement le trou qui a laisse 18 chaines de la
    modale d'ambiguite AVANCEE en dur pendant tout le chantier."""
    called = set()
    for rel in ("ambiguity_dialog.py", "visual_ambiguity_catalog.py"):
        called |= _dialog_label_calls(ROOT / "ui" / "wiring" / rel)
    missing = sorted(called - set(DIALOG_LABELS))
    assert not missing, f"cles appelees sans entree DIALOG_LABELS : {missing}"


def test_every_dialog_label_entry_has_the_four_languages():
    incomplete = {key: sorted(set(_LANGS) - set(entry))
                  for key, entry in DIALOG_LABELS.items()
                  if set(_LANGS) - set(entry) or not all(entry.values())}
    assert not incomplete, incomplete


def test_no_dialog_label_lost_a_placeholder_along_the_way():
    """Les 4 langues d'une meme cle doivent porter LES MEMES trous : un
    `{limit}` oublie dans une langue leve un KeyError au .format() -- dans
    cette langue seulement, donc invisible depuis une machine francaise."""
    faulty = []
    for key, entry in DIALOG_LABELS.items():
        sets = {lang: set(re.findall(r"\{(\w+)\}", entry[lang]))
                for lang in _LANGS if lang in entry}
        if len({frozenset(v) for v in sets.values()}) > 1:
            faulty.append((key, sets))
    assert not faulty, faulty


def test_advanced_modal_keys_really_differ_between_languages():
    """Les cles ajoutees le 2026-08-11 pour la modale d'ambiguite AVANCEE :
    quatre copies du francais passeraient le test precedent sans rien
    traduire -- c'est le defaut qu'on corrige, pas sa mise en forme.

    Pas d'exigence de distinction 2 a 2 : "Pin {net}" est legitimement
    identique en en/es/it (le mot est le meme dans les 3 langues) -- seul
    le cas « les 4 langues sont IDENTIQUES » (= rien traduit) est fautif."""
    added = (
        "adv_window_title", "adv_intro", "motors_limit_warning",
        "pin_digital", "pin_analog", "pin_generic", "prompt_excerpt",
        "prompt_excerpt_missing", "motor_yes_dc", "components_separate",
        "motors_detected_title", "motors_groups_desc", "assumed_motor_label",
        "motor_confirm_checkbox", "motor_confirm_tooltip",
        "wire_motor_checkbox", "motors_limit_toast",
        "driver_label_l293d_module", "driver_label_l293d_dip",
        "grouped_outputs_title", "grouped_excerpt_found",
        "grouped_excerpt_missing",
    )
    for key in added:
        entry = DIALOG_LABELS[key]
        assert len({entry[l] for l in _LANGS}) > 1, (key, entry)
        # fr doit rester distinct de CHAQUE traduction (le cas qui compte :
        # le francais recopie tel quel dans une langue qui a une vraie
        # traduction naturelle disponible).
        for lang in ("en", "es", "it"):
            assert entry[lang] != entry["fr"], (key, lang, entry)


TESTS = [
    test_four_options_present,
    test_every_icon_resolves,
    test_pin_placeholder_in_templates,
    test_labels_all_langs,
    test_dialog_labels_present,
    test_every_dialog_label_call_has_an_entry,
    test_every_dialog_label_entry_has_the_four_languages,
    test_no_dialog_label_lost_a_placeholder_along_the_way,
    test_advanced_modal_keys_really_differ_between_languages,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
