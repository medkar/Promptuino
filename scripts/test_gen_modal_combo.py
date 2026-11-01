"""Test offscreen du sélecteur « Modifier » de la modale : cases à cocher
multi-sélection (label avec broches + tooltip complet), présélection
casse-insensible, « Tout sélectionner » et résultat multi-cible.

Run : QT_QPA_PLATFORM=offscreen python scripts/test_gen_modal_combo.py
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from PyQt6.QtWidgets import QApplication, QDialog
from ui.generation.feature_model import Feature, guess_correction_target
from ui.generation.gen_modal import GenerationModal, CORRECT

_qapp = QApplication.instance() or QApplication([])
_keep: list = []


def _feats():
    led = Feature(id="f1", prompt="led", summary="Clignote la LED",
                  global_lines=["const int LED = 5;"],
                  setup_lines=["pinMode(LED, OUTPUT);"])
    servo = Feature(id="f2", prompt="servo", summary="Servo balayage",
                    global_lines=["const int SERVO_PIN = 9;", "Servo s;"],
                    setup_lines=["s.attach(SERVO_PIN);"])
    return [led, servo]


def _modal(prompt, preselect=None):
    m = GenerationModal(_feats(), prompt, preselect_target_id=preselect)
    _keep.append(m)
    return m


def _labels(m):
    return [cb.text() for cb, _ in m._feat_cbs]


def test_checkbox_labels_show_pins():
    labels = _labels(_modal("CORRECTION modifie la led en d5"))
    assert any("D5" in l for l in labels), labels
    assert any("D9" in l for l in labels), labels
    print("  [OK] les cases à cocher montrent les broches (D5, D9)")


def test_checkbox_tooltip_has_pins():
    m = _modal("CORRECTION x")
    tip0 = m._feat_cbs[0][0].toolTip()
    assert tip0 and "D5" in tip0, tip0
    print("  [OK] le tooltip d'une case contient la broche")


def test_preselects_led_on_lowercase_d5():
    # lowercase 'd5' -> LED (f1) preselected (checked, alone).
    feats = _feats()
    target = guess_correction_target(feats, "CORRECTION modifie la led en d5")
    assert target == "f1"
    m = GenerationModal(feats, "CORRECTION modifie la led en d5",
                        preselect_target_id=target)
    _keep.append(m)
    assert m._selected_ids() == ["f1"], m._selected_ids()
    print("  [OK] présélection de la LED en d5 (une seule cochée)")


def test_default_checks_first_feature():
    # No preselection: first feature is checked (always ≥1 target).
    m = _modal("CORRECTION x")
    assert m._selected_ids() == ["f1"], m._selected_ids()
    print("  [OK] 1re feature cochée par défaut")


def test_select_all_checks_every_feature():
    m = _modal("CORRECTION x")
    m._all_cb.setChecked(True)
    m._on_all_clicked(True)           # simulate click on "Select all"
    assert m._selected_ids() == ["f1", "f2"], m._selected_ids()
    print("  [OK] « Tout sélectionner » coche toutes les features")


def test_all_cb_syncs_when_every_box_checked():
    m = _modal("CORRECTION x")
    for cb, _ in m._feat_cbs:
        cb.setChecked(True)
    assert m._all_cb.isChecked(), "« Tout sélectionner » devrait être coché"
    m._feat_cbs[0][0].setChecked(False)
    assert not m._all_cb.isChecked(), "décocher une case décoche « Tout »"
    print("  [OK] « Tout sélectionner » suit l'état des cases")


def test_validate_returns_list_of_ids():
    m = _modal("CORRECTION x")
    m._rb[CORRECT].setChecked(True)
    for cb, _ in m._feat_cbs:
        cb.setChecked(True)
    m._on_validate()
    action, target = m.result_choice
    assert action == CORRECT, action
    assert target == ["f1", "f2"], target
    print("  [OK] result_choice renvoie la LISTE des ids cochés")


def test_ok_disabled_when_no_feature_checked():
    m = _modal("CORRECTION x")
    m._rb[CORRECT].setChecked(True)
    for cb, _ in m._feat_cbs:
        cb.setChecked(False)
    assert not m._ok.isEnabled(), "« Valider » doit être grisé sans cible"
    m._feat_cbs[0][0].setChecked(True)
    assert m._ok.isEnabled(), "« Valider » réactivé dès qu'une case est cochée"
    print("  [OK] « Valider » grisé tant qu'aucune feature n'est cochée")


TESTS = [
    test_checkbox_labels_show_pins,
    test_checkbox_tooltip_has_pins,
    test_preselects_led_on_lowercase_d5,
    test_default_checks_first_feature,
    test_select_all_checks_every_feature,
    test_all_cb_syncs_when_every_box_checked,
    test_validate_returns_list_of_ids,
    test_ok_disabled_when_no_feature_checked,
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
