"""Filet de sécurité du pipeline de génération (StudioView).

Pilote directement _on_generation_done (le worker de génération n'est qu'un
thread qui appelle le backend ; on court-circuite le thread en fournissant
le code « généré »). Sans arduino-cli/carte, la vérif v2 se saute et le
commit est synchrone -> assertions déterministes sur features/code/baseline.

But : verrouiller le comportement AVANT la convergence du mode débutant
(Prompt 4 tranche 2), pour détecter toute régression du cœur de génération
(non couvert par le smoke de lancement).

Run : python scripts/test_studio_generation_pipeline.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.studio_view import StudioView
from ui.generation import REGENERATE, ADD

_SKETCH = ("void setup() {\n  pinMode(13, OUTPUT);\n}\n"
           "void loop() {\n  digitalWrite(13, HIGH);\n}\n")
_SKETCH2 = ("void setup() {\n  pinMode(9, OUTPUT);\n}\n"
            "void loop() {\n  digitalWrite(9, LOW);\n}\n")


def _prime_regenerate(v, prompt):
    """Reproduit l'état posé par _start_generation avant l'appel au worker."""
    v.set_prompt(prompt)
    v._gen_revert_code = v.get_code()
    v._gen_revert_features = list(v._features)
    v._pending_from_scratch = False
    v._pending_action = (REGENERATE, None)
    v._set_generating(True)


def test_regenerate_first_gen_commits_single_feature():
    v = StudioView()
    v._on_mode_changed("advanced")
    _prime_regenerate(v, "clignote la LED sur D13")
    v._on_generation_done(_SKETCH)
    _APP.processEvents()
    assert len(v._features) == 1, v._features
    assert v._features[0].id == "f1"
    assert v._features[0].prompt == "clignote la LED sur D13"
    assert "pinMode(13" in v.get_code()
    assert v._has_generated is True
    assert v._code_baseline == v.get_code()
    assert v._pending_action is None          # libéré
    print("  OK — REGENERATE 1re génération : f1, code, baseline, libéré")


def test_regenerate_replaces_in_place():
    v = StudioView()
    v._on_mode_changed("advanced")
    _prime_regenerate(v, "LED D13")
    v._on_generation_done(_SKETCH)
    _APP.processEvents()
    # 2e régénération : remplace, toujours une seule f1.
    _prime_regenerate(v, "LED D9")
    v._on_generation_done(_SKETCH2)
    _APP.processEvents()
    assert len(v._features) == 1, v._features
    assert v._features[0].id == "f1"
    assert "pinMode(9" in v.get_code()
    assert "pinMode(13" not in v.get_code()
    print("  OK — REGENERATE remplace en place (1 seule f1)")


def test_add_appends_second_feature():
    v = StudioView()
    v._on_mode_changed("advanced")
    _prime_regenerate(v, "LED D13")
    v._on_generation_done(_SKETCH)
    _APP.processEvents()
    # Ajout d'une 2e fonctionnalité (pas de modale d'avertissement en 1->2
    # sans conflit ; _apply_feature_change assemble ou splice).
    v._gen_revert_code = v.get_code()
    v._gen_revert_features = list(v._features)
    v._pending_from_scratch = False
    v._pending_action = (ADD, None)
    v._set_generating(True)
    v._on_generation_done(
        "void setup() {\n  pinMode(7, INPUT);\n}\n"
        "void loop() {\n  digitalRead(7);\n}\n")
    _APP.processEvents()
    assert len(v._features) == 2, v._features
    ids = {f.id for f in v._features}
    assert ids == {"f1", "f2"}, ids
    assert v._has_generated is True
    print("  OK — ADD ajoute une 2e fonctionnalité (f1 + f2)")


TESTS = [
    test_regenerate_first_gen_commits_single_feature,
    test_regenerate_replaces_in_place,
    test_add_appends_second_feature,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {e}", flush=True)
            os._exit(1)
    print(f"OK : {len(TESTS)} tests", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
