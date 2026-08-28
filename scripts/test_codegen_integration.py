"""Tests d'intégration du threading prompt → system prompt (gating moteur).

On instancie une sous-classe minimale d'AIBackend en neutralisant les
méthodes abstraites (on ne teste que les builders de prompt, qui n'utilisent
aucun état d'instance)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.ai_backends.base import AIBackend


def _stub():
    class _Stub(AIBackend):
        pass
    _Stub.__abstractmethods__ = frozenset()
    return _Stub()


# ── generation: codegen_system_prompt(board, user_prompt) ──────────────
def test_system_prompt_excludes_motor_for_sensor():
    sp = _stub().codegen_system_prompt("Arduino Uno", "lis le capteur INA3221")
    assert "MOTOR RULES START" not in sp
    assert "HARDWARE RULE" in sp            # P1 toujours
    assert "DISAMBIGUATION RULE" in sp      # P2 toujours

def test_system_prompt_includes_motor_for_motor():
    sp = _stub().codegen_system_prompt("Arduino Uno",
                                       "fais tourner un moteur DC avec un L298N")
    assert "MOTOR RULES START" in sp

def test_system_prompt_default_no_prompt_has_p1_p2_no_p3():
    # Call without user_prompt (backward compat): P1+P2, not P3.
    sp = _stub()._build_system_prompt("Arduino Uno")
    assert "HARDWARE RULE" in sp
    assert "DISAMBIGUATION RULE" in sp
    assert "MOTOR RULES START" not in sp

def test_full_prompt_threads_user_prompt():
    fp = _stub()._build_full_prompt("contrôle un ventilateur", "Arduino Uno")
    assert "MOTOR RULES START" in fp        # ventilateur → moteur
    assert "contrôle un ventilateur" in fp  # user prompt is present


# ── gating on the RAW prompt, not the RAG-augmented blob ────────────────
# A motor lib example (L293D) retrieved by the RAG must NOT trigger
# the motor block when the actual request is a sensor.
_AUG_SENSOR = (
    "Task: lis un capteur INA3221\n\n"
    "### L293D\nExample:\n// L293D drive motor A — setMotor(...) analogWrite\n\n"
    "---\nlis un capteur INA3221"
)

def test_codegen_system_prompt_gates_on_its_arg():
    # codegen_system_prompt gates on the text passed to it: the dev preview
    # sends the RAW prompt (cf. _build_codegen_preview), not the RAG blob.
    sp = _stub().codegen_system_prompt("Arduino Uno", "lis un capteur INA3221")
    assert "MOTOR RULES START" not in sp

def test_full_prompt_gates_on_rules_prompt_not_blob():
    fp = _stub()._build_full_prompt(_AUG_SENSOR, "Arduino Uno",
                                    rules_prompt="lis un capteur INA3221")
    assert "MOTOR RULES START" not in fp   # gated on raw → no motor block
    assert "L293D" in fp                    # augmented user message still present

def test_full_prompt_rules_prompt_motor():
    fp = _stub()._build_full_prompt("Task: pilote", "Arduino Uno",
                                    rules_prompt="pilote un moteur DC")
    assert "MOTOR RULES START" in fp

def test_full_prompt_rules_prompt_defaults_to_user_prompt():
    # backward compat: without rules_prompt, gates on user_prompt.
    fp = _stub()._build_full_prompt("pilote un moteur", "Arduino Uno")
    assert "MOTOR RULES START" in fp


# ── repair: _build_repair_code_system(board, language, code) ───────────
def test_repair_gates_on_code_motor():
    rp = _stub()._build_repair_code_system(
        "Arduino Uno", "Français",
        "void setMotor(uint8_t p, uint8_t a, uint8_t b, int s){}")
    assert "MOTOR RULES START" in rp

def test_repair_gates_on_code_plain():
    rp = _stub()._build_repair_code_system(
        "Arduino Uno", "Français", "digitalWrite(13, HIGH);")
    assert "MOTOR RULES START" not in rp
    assert "HARDWARE RULE" in rp            # P1 always present even in repair


# ── repair: full file + [SUMMARY] (local model unable to produce ─────────
#    SEARCH/REPLACE format → request full file, guarded by structural
#    check + num_ctx + revert) ────────────────────────────────────────────
def test_repair_prompt_requests_full_file():
    rp = _stub()._build_repair_code_system(
        "Arduino Uno", "Français", "void loop(){}", errors="error: x")
    assert "[SUMMARY]" in rp
    assert "COMPLETE corrected source file" in rp
    assert "uses it" in rp or "use it" in rp   # mentions injected diagnostic

def test_repair_user_includes_full_code():
    user = _stub()._build_repair_code_user("a;\nb;\nc;", "error: x")
    assert "a;\nb;\nc;" in user               # full code, NOT line-numbered
    assert "   1: a;" not in user


TESTS = [
    test_system_prompt_excludes_motor_for_sensor,
    test_system_prompt_includes_motor_for_motor,
    test_system_prompt_default_no_prompt_has_p1_p2_no_p3,
    test_full_prompt_threads_user_prompt,
    test_codegen_system_prompt_gates_on_its_arg,
    test_full_prompt_gates_on_rules_prompt_not_blob,
    test_full_prompt_rules_prompt_motor,
    test_full_prompt_rules_prompt_defaults_to_user_prompt,
    test_repair_gates_on_code_motor,
    test_repair_gates_on_code_plain,
    test_repair_prompt_requests_full_file,
    test_repair_user_includes_full_code,
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
