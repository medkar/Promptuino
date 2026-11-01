"""behavior_review: capability gate + intent builder + review_conformance."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui.generation.behavior_review as br
from ui.generation.behavior_review import conformance_available, build_intent
from ui.generation.feature_model import Feature
from ui.ai_backends.base import AIBackend


class _Backend:
    def __init__(self, slm, chat_reply=""):
        self._slm = slm
        self._reply = chat_reply
        self.last_system = None
        self.last_user = None

    def is_slm(self):
        return self._slm

    # Minimal transport used by AIBackend.review_conformance.
    def chat(self, system_prompt, messages):
        self.last_system = system_prompt
        self.last_user = messages[0]["content"]
        return self._reply

    # Borrow the real prompt builders + apply pipeline from the ABC.
    _build_conformance_system = AIBackend._build_conformance_system
    _build_conformance_user = AIBackend._build_conformance_user
    _repair_from_response = AIBackend._repair_from_response
    review_conformance = AIBackend.review_conformance


# ── Gate ─────────────────────────────────────────────────────────

def test_gate_on_slm_flag_true_offers_everywhere():
    br.CONFORMANCE_ON_SLM = True
    assert conformance_available(_Backend(slm=True)) is True
    assert conformance_available(_Backend(slm=False)) is True
    assert conformance_available(None) is False


def test_gate_flag_false_restricts_to_capable():
    br.CONFORMANCE_ON_SLM = False
    try:
        assert conformance_available(_Backend(slm=True)) is False
        assert conformance_available(_Backend(slm=False)) is True
    finally:
        br.CONFORMANCE_ON_SLM = True     # restore default for other tests


# ── Intent ───────────────────────────────────────────────────────

def test_build_intent_combines_full_prompts():
    f1 = Feature(id="f1", prompt="allume la LED", prompts=["allume la LED"])
    f2 = Feature(id="f2", prompt="fais clignoter",
                 prompts=["fais clignoter", "plus vite"])
    intent = build_intent([f1, f2])
    assert "allume la LED" in intent and "fais clignoter" in intent


def test_build_intent_empty_without_features():
    assert build_intent([]) == ""


# ── review_conformance (transport = chat, apply = SEARCH/REPLACE) ──

_CODE = ("void setup(){ pinMode(13, OUTPUT); }\n"
         "void loop(){ digitalWrite(13, LOW); }\n")   # intent: LED ON


def _sr(search, replace):
    return (f"[SUMMARY]\n- **Line 2:** LED was driven LOW\n[/SUMMARY]\n"
            f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE\n")


def test_review_applies_targeted_fix():
    be = _Backend(slm=False, chat_reply=_sr(
        "void loop(){ digitalWrite(13, LOW); }",
        "void loop(){ digitalWrite(13, HIGH); }"))
    code, summary = be.review_conformance(_CODE, "allumer la LED", "Uno")
    assert "digitalWrite(13, HIGH)" in code
    assert "LED was driven LOW" in summary


def test_review_passes_intent_and_evidence_to_prompt():
    be = _Backend(slm=False, chat_reply="[SUMMARY]\n[/SUMMARY]\n")
    be.review_conformance(_CODE, "faire suivre la ligne", "Uno",
                          evidence="distance: 0\ndistance: 0")
    assert "faire suivre la ligne" in be.last_user
    assert "distance: 0" in be.last_user
    assert "OBSERVED SERIAL OUTPUT" in be.last_user


def test_review_no_change_returns_original():
    be = _Backend(slm=False, chat_reply="[SUMMARY]\n[/SUMMARY]\n")  # no blocks
    code, summary = be.review_conformance(_CODE, "intent", "Uno")
    assert code == _CODE and summary == ""


TESTS = [
    test_gate_on_slm_flag_true_offers_everywhere,
    test_gate_flag_false_restricts_to_capable,
    test_build_intent_combines_full_prompts,
    test_build_intent_empty_without_features,
    test_review_applies_targeted_fix,
    test_review_passes_intent_and_evidence_to_prompt,
    test_review_no_change_returns_original,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1
        except Exception as e:
            import traceback
            print(f"FAIL {t.__name__}: {e}")
            traceback.print_exc()
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
