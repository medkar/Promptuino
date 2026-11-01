"""Test offscreen : l'aperçu dev (_build_codegen_preview) gate le bloc moteur
sur le prompt BRUT, pas sur le blob augmenté par le RAG.

Régression : un exemple de lib moteur (L293D) injecté par le RAG dans le
message utilisateur ne doit PAS faire apparaître MOTOR RULES dans le SYSTEM
PROMPT quand la requête réelle est un capteur."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.studio_view import _build_codegen_preview
from ui.ai_backends.base import AIBackend


def _stub():
    class _Stub(AIBackend):
        pass
    _Stub.__abstractmethods__ = frozenset()
    return _Stub()


_AUG_SENSOR = (
    "Task: lis un capteur INA3221\n\n"
    "Relevant Arduino libraries\n### L293D\n"
    "// L293D drive motor A — setMotor(...) analogWrite\n\n"
    "---\nlis un capteur INA3221"
)


def test_preview_system_has_no_motor_when_bare_is_sensor():
    txt = _build_codegen_preview(_stub(), _AUG_SENSOR, "Arduino Nano",
                                 "advanced", 2, rules_prompt="lis un capteur INA3221")
    system_part = txt.split("MESSAGE UTILISATEUR")[0]
    assert "MOTOR RULES START" not in system_part   # gated on the raw prompt
    assert "L293D" in txt                            # the augmented message is still displayed


def test_preview_system_has_motor_when_bare_is_motor():
    txt = _build_codegen_preview(_stub(), "Task: pilote\n---\npilote", "Arduino Nano",
                                 "advanced", 2, rules_prompt="pilote un moteur DC")
    system_part = txt.split("MESSAGE UTILISATEUR")[0]
    assert "MOTOR RULES START" in system_part


def test_preview_defaults_to_user_prompt_without_rules():
    # back-compat: without rules_prompt, gate on user_prompt.
    txt = _build_codegen_preview(_stub(), "pilote un moteur DC", "Arduino Nano",
                                 "advanced", 2)
    system_part = txt.split("MESSAGE UTILISATEUR")[0]
    assert "MOTOR RULES START" in system_part


TESTS = [
    test_preview_system_has_no_motor_when_bare_is_sensor,
    test_preview_system_has_motor_when_bare_is_motor,
    test_preview_defaults_to_user_prompt_without_rules,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
