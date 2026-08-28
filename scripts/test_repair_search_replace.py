"""Tests du mécanisme de réparation par édits localisés SEARCH/REPLACE.

Cœur de la régression « la réparation coupe la fin du code » : on n'autorise
plus la ré-écriture du fichier entier. Le modèle émet des blocs SEARCH/REPLACE
qu'on applique par recherche EXACTE (le reste du fichier est recopié verbatim →
la fin ne peut plus disparaître), avec rejet fail-safe des matchs
introuvables/ambigus et un garde-fou structurel.

Convention repo : runner standalone, pas de pytest.
  QT_QPA_PLATFORM=offscreen python scripts/test_repair_search_replace.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.ai_backends.base import (
    Edit,
    _parse_search_replace_blocks,
    _apply_edits,
    _repair_acceptable,
    _apply_repair_response,
)


def _block(search, replace):
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


# ── Parsing ──────────────────────────────────────────────────────

def test_parse_single_block():
    edits = _parse_search_replace_blocks(_block("a = 1", "a = 1;"))
    assert len(edits) == 1
    assert edits[0].search == "a = 1"
    assert edits[0].replace == "a = 1;"


def test_parse_multiple_blocks():
    text = _block("foo()", "foo();") + "\n" + _block("bar", "baz")
    edits = _parse_search_replace_blocks(text)
    assert [(e.search, e.replace) for e in edits] == [
        ("foo()", "foo();"), ("bar", "baz"),
    ]


def test_parse_with_summary_prefix():
    text = "[SUMMARY]\n- **Ligne 1 :** fix\n[/SUMMARY]\n" + _block("x", "y")
    edits = _parse_search_replace_blocks(text)
    assert len(edits) == 1 and edits[0].search == "x"


def test_parse_zero_blocks():
    assert _parse_search_replace_blocks("[SUMMARY]\n\n[/SUMMARY]\n") == []


def test_parse_tolerates_marker_whitespace():
    text = "<<<<<<<   SEARCH  \nk\n=======  \nm\n>>>>>>>  REPLACE  "
    edits = _parse_search_replace_blocks(text)
    assert len(edits) == 1 and edits[0].search == "k" and edits[0].replace == "m"


def test_parse_skips_malformed_block():
    # No ======= separator -> block ignored, no crash.
    text = "<<<<<<< SEARCH\norphan\n>>>>>>> REPLACE"
    assert _parse_search_replace_blocks(text) == []


# ── Application : match exact ────────────────────────────────────

_CODE = (
    "// header pédagogique\n"
    "void setup() {\n"
    "  pinMode(13, OUTPUT)\n"
    "}\n"
    "void loop() {\n"
    "  digitalWrite(13, HIGH);\n"
    "  delay(500);\n"
    "}\n"
)


def test_apply_exact_match_keeps_tail_intact():
    edits = [Edit("  pinMode(13, OUTPUT)", "  pinMode(13, OUTPUT);")]
    out, applied, rejected = _apply_edits(_CODE, edits)
    assert applied == 1 and rejected == []
    assert "pinMode(13, OUTPUT);" in out
    # THE regression point: everything else, including the END, intact.
    assert out.endswith("  delay(500);\n}\n")
    assert "void loop() {" in out
    assert out.count("\n") == _CODE.count("\n")  # aucune ligne perdue


def test_apply_normalized_whitespace_match():
    # SEARCH re-indented differently (2 spaces -> 4) still matches.
    edits = [Edit("    pinMode(13, OUTPUT)", "    pinMode(13, OUTPUT);")]
    out, applied, rejected = _apply_edits(_CODE, edits)
    assert applied == 1 and rejected == []
    # The ORIGINAL indentation (2 spaces) is preserved.
    assert "\n  pinMode(13, OUTPUT);\n" in out


def test_apply_rejects_missing_search():
    edits = [Edit("analogWrite(9, 200)", "analogWrite(9, 255)")]
    out, applied, rejected = _apply_edits(_CODE, edits)
    assert applied == 0 and len(rejected) == 1
    assert out == _CODE   # code unchanged


def test_apply_rejects_ambiguous_search():
    code = "x = 1;\ny = 2;\nx = 1;\n"   # "x = 1;" appears 2 times
    edits = [Edit("x = 1;", "x = 10;")]
    out, applied, rejected = _apply_edits(code, edits)
    assert applied == 0 and len(rejected) == 1
    assert out == code


def test_apply_sequential_edits():
    edits = [
        Edit("  pinMode(13, OUTPUT)", "  pinMode(13, OUTPUT);"),
        Edit("  delay(500);", "  delay(1000);"),
    ]
    out, applied, rejected = _apply_edits(_CODE, edits)
    assert applied == 2 and rejected == []
    assert "pinMode(13, OUTPUT);" in out and "delay(1000);" in out


# ── Garde-fou structurel ─────────────────────────────────────────

def test_guard_rejects_unbalanced_braces():
    before = "void setup(){}\nvoid loop(){}\n"
    after = "void setup(){}\nvoid loop(){\n"   # accolade fermante perdue
    assert _repair_acceptable(before, after) is False


def test_guard_rejects_dropped_loop():
    before = "void setup(){}\nvoid loop(){ /* ... */ }\n"
    after = "void setup(){}\n"                 # loop() disparu
    assert _repair_acceptable(before, after) is False


def test_guard_rejects_massive_shrink():
    before = "x\n" * 100
    after = "x\n" * 50                         # ~50 % -> effondrement
    assert _repair_acceptable(before, after) is False


def test_guard_accepts_minimal_fix():
    before = "void setup(){\n  a = 1\n}\nvoid loop(){}\n"
    after = "void setup(){\n  a = 1;\n}\nvoid loop(){}\n"
    assert _repair_acceptable(before, after) is True


def test_guard_ignores_braces_in_strings_and_comments():
    # Rustine : le garde-fou compte les accolades BRUTES -> un fix légitime
    # qui ajoute Serial.println("}") ou un commentaire avec } était rejeté à
    # tort. On doit stripper chaînes/commentaires avant de compter.
    before = "void setup(){}\nvoid loop(){}\n"
    after = ('void setup(){\n  Serial.println("}");  // closes }\n}\n'
             'void loop(){}\n')
    assert _repair_acceptable(before, after) is True
    # And a REAL missing brace is still rejected (the fix must not blind us).
    broken = 'void setup(){\n  Serial.println("}");\nvoid loop(){}\n'
    assert _repair_acceptable(before, broken) is False


# ── Bout-en-bout ─────────────────────────────────────────────────

def test_end_to_end_applies_minimal_fix():
    raw = (
        "[SUMMARY]\n- **Ligne 3 :** point-virgule manquant\n[/SUMMARY]\n"
        + _block("  pinMode(13, OUTPUT)", "  pinMode(13, OUTPUT);")
    )
    out, summary = _apply_repair_response(_CODE, raw)
    assert "pinMode(13, OUTPUT);" in out
    assert out.endswith("  delay(500);\n}\n")     # fin intacte
    assert "point-virgule" in summary


def test_end_to_end_rejects_gutting():
    # The model "repairs" by deleting the entire body -> SEARCH not found,
    # or result breaks the safety guard: return the original unchanged.
    raw = "[SUMMARY]\n[/SUMMARY]\n" + _block("void loop() {", "")
    out, summary = _apply_repair_response(_CODE, raw)
    assert out == _CODE and summary == ""


def test_end_to_end_no_blocks_returns_original():
    out, summary = _apply_repair_response(_CODE, "[SUMMARY]\n\n[/SUMMARY]\n")
    assert out == _CODE and summary == ""


# ── End-to-end: FULL FILE fallback (local model without SEARCH/REPLACE) ──

def test_end_to_end_accepts_wholefile_rewrite():
    # No block -> treat the body as the full corrected file, accepted
    # because it passes the safety guard (length, braces, setup/loop).
    fixed = _CODE.replace("OUTPUT)\n", "OUTPUT);\n")
    raw = "[SUMMARY]\n- **Line 3:** semicolon\n[/SUMMARY]\n" + fixed
    out, summary = _apply_repair_response(_CODE, raw)
    assert out.strip() == fixed.strip()
    assert "semicolon" in summary


def test_end_to_end_rejects_wholefile_gutting():
    # Full file but gutted (loop() lost, collapse) -> safety guard
    # rejects -> original code preserved.
    raw = "[SUMMARY]\n[/SUMMARY]\nvoid setup() {}\n"
    out, summary = _apply_repair_response(_CODE, raw)
    assert out == _CODE and summary == ""


def test_end_to_end_strips_markdown_fences_wholefile():
    fixed = _CODE.replace("OUTPUT)\n", "OUTPUT);\n")
    raw = "[SUMMARY]\n- fix\n[/SUMMARY]\n```cpp\n" + fixed + "```"
    out, _ = _apply_repair_response(_CODE, raw)
    assert out.strip() == fixed.strip()       # ```cpp fences stripped


TESTS = [
    test_parse_single_block,
    test_parse_multiple_blocks,
    test_parse_with_summary_prefix,
    test_parse_zero_blocks,
    test_parse_tolerates_marker_whitespace,
    test_parse_skips_malformed_block,
    test_apply_exact_match_keeps_tail_intact,
    test_apply_normalized_whitespace_match,
    test_apply_rejects_missing_search,
    test_apply_rejects_ambiguous_search,
    test_apply_sequential_edits,
    test_guard_rejects_unbalanced_braces,
    test_guard_rejects_dropped_loop,
    test_guard_rejects_massive_shrink,
    test_guard_accepts_minimal_fix,
    test_guard_ignores_braces_in_strings_and_comments,
    test_end_to_end_applies_minimal_fix,
    test_end_to_end_rejects_gutting,
    test_end_to_end_no_blocks_returns_original,
    test_end_to_end_accepts_wholefile_rewrite,
    test_end_to_end_rejects_wholefile_gutting,
    test_end_to_end_strips_markdown_fences_wholefile,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
