"""End-to-end : Ctrl+Z après « Supprimer » (overlay fonctionnalité) restaure les
fonctionnalités, leurs métadonnées câblage ET le sélecteur de fonctionnalités.

Avant le fix, `_resync_features_from_editor` restaurait `self._features` mais
ni `_wiring_resolutions`/`_implicit_actions` (perdus au strip de la
suppression), ni le sélecteur (qui restait sur l'état supprimé).

NB : un seul test — il construit un vrai StudioView (un par process, cf.
test_scoped_edit_persistence.py). Qt requis (offscreen) ; skip propre si absent.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
    # Reference module-level obligatoire (sinon l'app temporaire est GC-ee
    # et la construction de widgets crashe le process).
    _APP = QApplication.instance() or QApplication([])
except Exception:
    _HAS_QT = False


def test_undo_after_delete_restores_features_metadata_and_chips():
    from ui.studio_view import StudioView
    from ui.generation import Feature, assemble

    f1 = Feature(id="f1", prompt="allume une LED", summary="LED",
                 global_lines=["const int PIN_LED = 5;"],
                 setup_lines=["pinMode(PIN_LED, OUTPUT);"],
                 loop_lines=["digitalWrite(PIN_LED, HIGH);"])
    f2 = Feature(id="f2", prompt="fais sonner un buzzer", summary="Buzzer",
                 global_lines=["const int PIN_BUZZER = 9;"],
                 setup_lines=["pinMode(PIN_BUZZER, OUTPUT);"],
                 loop_lines=["tone(PIN_BUZZER, 440);"])

    sv = StudioView()
    sv._current_mode = "intermediate"      # sélecteur peuplé hors Débutant
    sv._features = [f1, f2]
    _dd = sv._code_panel.feature_dropdown   # rows = 1 par fonctionnalité
    # État A (remplacement undoable) — via le helper d'attribution (#29) pour
    # que la carte lignes->fonctionnalité de CET état soit correcte : c'est
    # elle que Ctrl+Z doit restaurer plus bas (sinon _delete_features indexe
    # un état "avant" sans carte, et l'undo restaurerait des None partout).
    sv._set_code_with_attribution(assemble([f1, f2]), sv._features)
    sv._code_baseline = sv.get_code()
    sv._wiring_resolutions = {("f2", "D9"): "buzzer"}
    sv._implicit_actions = {("f2", "D9", "res"): "220"}
    sv._refresh_feature_chips()
    assert len(_dd._rows) == 2

    # Suppression de f2 (le chemin des puces appelle _delete_features).
    sv._delete_features({"f2"})
    assert [f.id for f in sv._features] == ["f1"]
    assert sv._wiring_resolutions == {} and sv._implicit_actions == {}
    assert len(_dd._rows) == 1
    assert "PIN_BUZZER" not in sv.get_code()

    # Ctrl+Z -> tout revient : features, métadonnées câblage, bandeau.
    sv._editor.undo()
    assert [f.id for f in sv._features] == ["f1", "f2"], sv._features
    assert sv._wiring_resolutions == {("f2", "D9"): "buzzer"}, sv._wiring_resolutions
    assert sv._implicit_actions == {("f2", "D9", "res"): "220"}
    assert len(_dd._rows) == 2
    assert "PIN_BUZZER" in sv.get_code()

    # La carte lignes->fonctionnalité revient aussi avec l'undo (#29).
    owners = sv._editor.line_owners()
    assert "f2" in owners, owners
    idx_buzzer = next(i for i, ln in enumerate(sv.get_code().split("\n"))
                      if "PIN_BUZZER = 9" in ln)
    assert owners[idx_buzzer] == "f2", owners[idx_buzzer]

    # Ctrl+Y -> l'état supprimé revient, métadonnées re-nettoyées.
    sv._editor.redo()
    assert [f.id for f in sv._features] == ["f1"]
    assert sv._wiring_resolutions == {} and sv._implicit_actions == {}
    assert len(_dd._rows) == 1
    assert "f2" not in sv._editor.line_owners()


def main() -> int:
    if not _HAS_QT:
        print("SKIP (PyQt6 indisponible)")
        return 0
    try:
        test_undo_after_delete_restores_features_metadata_and_chips()
        print("OK   test_undo_after_delete_restores_features_metadata_and_chips")
        print("\n1/1 tests passed")
        return 0
    except AssertionError as e:
        print(f"FAIL test_undo_after_delete_restores_features_metadata_and_chips: {e}")
        return 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
