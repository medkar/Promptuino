"""Tests de la réparation ANCRÉE sur les lignes d'erreur du compilateur.

Idée : arduino-cli donne `sketch.ino:LINE:COL: error: …`. On n'a donc PAS besoin
que le modèle localise l'édit — NOUS extrayons une petite fenêtre autour de la
ligne, le modèle ne corrige QUE ces lignes, et NOUS la réinjectons. Le reste du
fichier est intouché par construction (plus de troncature ni de gutting), et la
charge du modèle est minuscule.

Convention repo : runner standalone, pas de pytest.
  QT_QPA_PLATFORM=offscreen python scripts/test_line_anchored_repair.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.arduino_cli import (
    _parse_error_lines, _merge_windows, line_anchored_repair,
    _is_structurally_balanced,
)


class _StubRegionBackend:
    """backend.repair_region(region, …) → version corrigée d'après `mapping`
    (région inchangée par défaut). Mémorise les régions ET les erreurs reçues."""
    def __init__(self, mapping=None):
        self.mapping = mapping or {}
        self.calls = []
        self.errors_seen = []

    def repair_region(self, region, errors, language, board_name):
        self.calls.append(region)
        self.errors_seen.append(errors)
        return self.mapping.get(region, region)


# ── Parsing des lignes d'erreur ──────────────────────────────────

def test_parse_error_lines():
    err = (
        "Using library Wire\n"
        "C:\\tmp\\sketch\\sketch.ino:12:3: error: expected ';' before '}'\n"
        "   12 |   foo()\n"
        "sketch.ino:5:1: error: 'x' was not declared\n"
    )
    assert _parse_error_lines(err) == [5, 12]


def test_parse_error_lines_dedup_sorted():
    err = "f.ino:9:2: error: a\nf.ino:3:1: error: b\nf.ino:9:7: error: c"
    assert _parse_error_lines(err) == [3, 9]


def test_parse_no_error_lines():
    assert _parse_error_lines("collect2: error: ld returned 1 exit status") == []
    assert _parse_error_lines("") == []


# ── Windows ──────────────────────────────────────────────────────

def test_merge_windows_adjacent_merge():
    # 3±2=1-5, 4±2=2-6 → merge 1-6; 20±2=18-22 separate.
    assert _merge_windows([3, 4, 20], total=30, radius=2) == [(1, 6), (18, 22)]


def test_merge_windows_clamped():
    assert _merge_windows([1], total=3, radius=2) == [(1, 3)]


# ── Line-anchored repair ─────────────────────────────────────────

_CODE = "a;\nb\nc;\nd;\ne;\nf;\ng;\nh;\n"   # ligne 2 « b » : ; manquant


def test_line_anchored_splices_only_target_keeps_tail():
    win = "a;\nb\nc;\nd;"           # window lines 1-4 (line 2 ±2)
    fixed = "a;\nb;\nc;\nd;"
    be = _StubRegionBackend({win: fixed})
    out = line_anchored_repair(_CODE, "sketch.ino:2:1: error: expected ';'",
                               be, "French", "Arduino Uno")
    assert out == "a;\nb;\nc;\nd;\ne;\nf;\ng;\nh;\n"   # seule la ligne 2 change
    assert be.calls == [win]                            # single window call


def test_line_anchored_none_without_line_numbers():
    # No usable line number (linker error) → None → caller will fall back.
    out = line_anchored_repair(_CODE, "collect2: error: ld failed",
                               _StubRegionBackend(), "fr", "Uno")
    assert out is None


def test_line_anchored_none_when_model_returns_unchanged():
    be = _StubRegionBackend()   # returns the region unchanged
    out = line_anchored_repair(_CODE, "sketch.ino:2:1: error: x",
                               be, "fr", "Uno")
    assert out is None          # nothing changed → fall back


def test_line_anchored_rejects_gutting_region():
    # Model "fixes" by emptying the window → guard → None (fall back).
    win = "a;\nb\nc;\nd;"
    be = _StubRegionBackend({win: ""})   # emptied region
    out = line_anchored_repair(_CODE, "sketch.ino:2:1: error: x",
                               be, "fr", "Uno")
    assert out is None


# ── Rustine : chaque fenêtre ne reçoit QUE ses erreurs ───────────

def test_line_anchored_filters_errors_per_window():
    # 15 lignes, 2 erreurs BIEN écartées (l.2 et l.12) -> 2 fenêtres distinctes.
    # Chaque fenêtre ne doit recevoir QUE l'erreur qui tombe dedans (sinon le
    # SLM tente de réparer une erreur absente de sa fenêtre).
    code = "\n".join(f"line{i};" for i in range(1, 16)) + "\n"
    err = ("sketch.ino:2:1: error: expected ';' before 'x'\n"
           "sketch.ino:12:1: error: 'zz' was not declared in this scope\n")
    be = _StubRegionBackend()
    line_anchored_repair(code, err, be, "fr", "Uno")
    assert len(be.calls) == 2, be.calls
    win2 = next(e for r, e in zip(be.calls, be.errors_seen) if "line2;" in r)
    assert "expected ';'" in win2 and "was not declared" not in win2, win2
    win12 = next(e for r, e in zip(be.calls, be.errors_seen) if "line12;" in r)
    assert "was not declared" in win12 and "expected ';'" not in win12, win12


# ── Structural detection (missing brace/parenthesis) ─────────────

def test_balanced_true():
    assert _is_structurally_balanced("void loop() {\n  f();\n}\n") is True


def test_missing_brace_false():
    # Closing brace removed → imbalance → structural error.
    assert _is_structurally_balanced("void loop() {\n  f();\n") is False


def test_missing_paren_false():
    assert _is_structurally_balanced("if (x {\n  y();\n}\n") is False


def test_brace_in_string_ignored():
    # A "}" inside a string or comment must not be counted.
    assert _is_structurally_balanced('void s(){ Serial.println("}"); } // }\n') is True


TESTS = [
    test_parse_error_lines,
    test_parse_error_lines_dedup_sorted,
    test_parse_no_error_lines,
    test_merge_windows_adjacent_merge,
    test_merge_windows_clamped,
    test_line_anchored_splices_only_target_keeps_tail,
    test_line_anchored_none_without_line_numbers,
    test_line_anchored_none_when_model_returns_unchanged,
    test_line_anchored_rejects_gutting_region,
    test_line_anchored_filters_errors_per_window,
    test_balanced_true,
    test_missing_brace_false,
    test_missing_paren_false,
    test_brace_in_string_ignored,
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
