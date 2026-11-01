"""Tests estimateur + assemblage sous budget tokens.
Run : python scripts/test_chat_token_budget.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.chat.chat_prompts import _estimate_tokens
from ui.chat.chat_prompts import build_system_prompt
from ui.chat.chat_prompts import build_turn_context
from ui.chat.chat_prompts import assemble_within_budget
from ui.chat.chat_rag import CorpusHit
from ui.chat.chat_controller import ChatController, StreamingRequired


class _FakeBackend:
    def __init__(self, is_slm=False, ctx=200_000):
        self._is_slm = is_slm
        self._ctx = ctx
    name = "fake"
    @property
    def is_slm(self):
        return self._is_slm
    @property
    def context_window_hint(self):
        return self._ctx
    def chat(self, system_prompt, messages):
        return "ok"


class _FakeEffBackend(_FakeBackend):
    """Declares a huge nominal window but a small EFFECTIVE chat context."""
    def effective_chat_context(self):
        return 12345


def test_estimate_tokens_monotonic():
    assert _estimate_tokens("") == 1
    assert _estimate_tokens("abcd") == 1
    assert _estimate_tokens("a" * 400) == 100
    assert _estimate_tokens("a" * 4000) > _estimate_tokens("a" * 400)


def test_turn_context_concept_section():
    # RAG hits are query-dependent (volatile) -> live in the turn context,
    # not the cached system prefix.
    hit = CorpusHit(entry={
        "id": "pwm", "name": "PWM", "category": "concept",
        "summary": "pulse width modulation", "facts": ["analogWrite 0..255"],
    }, score=2.0)
    ctx = build_turn_context(rag_hits=[hit])
    assert "PWM" in ctx and "pulse width modulation" in ctx
    assert "analogWrite 0..255" in ctx


def test_turn_context_include_flags():
    ctx_full = build_turn_context(
        code="void loop(){}", wiring_summary=["LED on D9"])
    assert "void loop(){}" in ctx_full and "LED on D9" in ctx_full
    ctx_nocode = build_turn_context(
        code="void loop(){}", wiring_summary=["LED on D9"],
        include_code=False)
    assert "void loop(){}" not in ctx_nocode and "LED on D9" in ctx_nocode
    ctx_nowiring = build_turn_context(
        code="void loop(){}", wiring_summary=["LED on D9"],
        include_wiring=False)
    assert "LED on D9" not in ctx_nowiring


def test_system_prompt_has_no_volatile_content():
    # The cacheable prefix must not carry code/wiring/RAG -> they would bust
    # the cache whenever the code changes.
    sysp = build_system_prompt(user_mode="beginner")
    assert "## Code Arduino" not in sysp
    assert "## Detected wiring" not in sysp
    assert "# Relevant Arduino libraries" not in sysp


def test_system_prompt_has_app_knowledge():
    # No labels -> English fallback labels, section still present.
    sysp = build_system_prompt(user_mode="beginner")
    assert "About Promptuino" in sysp
    assert "Generate a feature" in sysp


def test_app_knowledge_uses_provided_labels():
    # Labels passed in the app language are quoted verbatim.
    sysp = build_system_prompt(
        user_mode="beginner",
        app_labels={"studio_prompt_label": "Générer une fonctionnalité",
                    "studio_generate": "Générer"})
    assert "Générer une fonctionnalité" in sysp
    assert "Generate a feature" not in sysp  # fallback overridden


def test_build_system_prompt_board_facts():
    sysp = build_system_prompt(
        user_mode="beginner",
        board_facts=["MCU: ATmega328P", "Logic level: 5V"])
    assert "ATmega328P" in sysp and "5V" in sysp


def test_app_knowledge_manual_editing_is_allowed():
    # #34 : l'ancienne affirmation « the student does NOT write code by hand »
    # est fausse depuis #33 (edition libre en Intermediaire + Avance).
    sysp = build_system_prompt(user_mode="advanced").lower()
    assert "not write code by hand" not in sysp
    assert "edit the code" in sysp            # l'edition manuelle est mentionnee


def test_app_knowledge_two_windows_and_transfer():
    # #34 : la vue Avancee 2 fenetres (IA / stable) + le transfert doivent etre
    # decrits (fallbacks anglais, aucun label fourni).
    sysp = build_system_prompt(user_mode="advanced")
    assert "Generated code (AI)" in sysp      # studio_window_ai
    assert "Stable code" in sysp              # studio_window_stable
    assert "Transfer to stable" in sysp       # studio_transfer_to_stable


def test_app_knowledge_dropdown_and_manual_feature():
    # #34 : dropdown (pas « chip … rename double-click ») + « Editions manuelles »
    # + clic droit « Attribuer a ».
    sysp = build_system_prompt(user_mode="advanced")
    assert "Manual edits" in sysp             # studio_manual_feature_label
    assert "Assign to a feature" in sysp      # ctx_menu_assign_feature
    low = sysp.lower()
    assert "double-click" not in low
    assert "chip" not in low


def test_app_knowledge_new_labels_are_localized():
    # #34 : les nouveaux libelles sont cites dans la langue fournie (pas le
    # fallback anglais).
    sysp = build_system_prompt(
        user_mode="advanced",
        app_labels={"studio_transfer_to_stable": "Transferer vers stable",
                    "studio_manual_feature_label": "Editions manuelles"})
    assert "Transferer vers stable" in sysp
    assert "Editions manuelles" in sysp
    assert "Transfer to stable" not in sysp   # fallback ecrase


def _big(n):
    return "x" * n


def test_budget_keeps_everything_when_large():
    # Volatile context (code + wiring) now rides on the current user message,
    # not the system prompt.
    sysp, msgs = assemble_within_budget(
        user_mode="beginner", code="void loop(){}",
        wiring_summary=["LED on D9"], current_user_text="hello",
        token_budget=200_000)
    last = msgs[-1]["content"]
    assert "void loop(){}" in last and "LED on D9" in last
    assert msgs[-1]["role"] == "user" and last.endswith("hello")
    assert "void loop(){}" not in sysp, "code must stay out of cached prefix"


def test_budget_drops_code_first():
    sysp, msgs = assemble_within_budget(
        user_mode="beginner",
        code="// " + _big(40_000),
        wiring_summary=["LED on D9"],
        current_user_text="question",
        token_budget=8192)
    last = msgs[-1]["content"]
    assert "LED on D9" in last, "wiring should survive the code"
    assert _big(40_000) not in last, "the big code should have been dropped"


def test_budget_drops_wiring_after_code():
    sysp, msgs = assemble_within_budget(
        user_mode="beginner",
        code="// " + _big(40_000),
        wiring_summary=[_big(40_000)],
        current_user_text="ma question importante",
        token_budget=8192)
    last = msgs[-1]["content"]
    assert _big(40_000) not in last
    assert last.endswith("ma question importante")


def test_system_prompt_stable_across_code_changes():
    # Same stable inputs, different volatile code -> identical system prefix.
    # This byte-equality is exactly what lets the backend prompt cache hit.
    common = dict(user_mode="beginner", board_facts=["MCU: ATmega328P"],
                  original_prompt="blink an LED", current_user_text="why?",
                  token_budget=200_000)
    sys1, _ = assemble_within_budget(code="int a;", **common)
    sys2, _ = assemble_within_budget(
        code="float b; void loop(){ digitalWrite(13, HIGH); }", **common)
    assert sys1 == sys2


def test_budget_trims_oldest_history():
    history = [
        {"role": "user", "content": _big(20_000)},
        {"role": "assistant", "content": _big(20_000)},
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]
    sysp, msgs = assemble_within_budget(
        user_mode="beginner", history=history,
        current_user_text="now", token_budget=8192)
    contents = [m["content"] for m in msgs]
    assert "now" in contents
    assert _big(20_000) not in contents, "le vieux tour aurait du etre coupe"


def test_controller_injects_selected_board():
    c = ChatController(backend=_FakeBackend(), user_mode="beginner")
    c.board_model = "Arduino Uno R3"
    decision = c.evaluate_turn("combien de memoire ?")
    assert isinstance(decision, StreamingRequired)
    assert "SRAM" in decision.system_prompt or "Flash" in decision.system_prompt


def test_controller_slm_uses_top1():
    c = ChatController(backend=_FakeBackend(is_slm=True), user_mode="beginner")
    decision = c.evaluate_turn("c'est quoi le pwm et l'i2c et le spi")
    assert isinstance(decision, StreamingRequired)
    # RAG concepts now live in the current user message, not the system prompt.
    blob = decision.messages[-1]["content"]
    n_concepts = sum(blob.count(f"- {n}") for n in ("PWM", "I2C", "SPI"))
    assert n_concepts <= 1, f"SLM should cap at top-1, got {n_concepts}"


def test_controller_uses_effective_context():
    import ui.chat.chat_controller as cc
    captured = {}
    real = cc.assemble_within_budget

    def spy(**kw):
        captured.update(kw)
        return real(**kw)

    cc.assemble_within_budget = spy
    try:
        c = ChatController(backend=_FakeEffBackend(), user_mode="beginner")
        c.evaluate_turn("combien de memoire ?")
    finally:
        cc.assemble_within_budget = real
    assert captured.get("token_budget") == 12345


def test_controller_falls_back_to_hint():
    import ui.chat.chat_controller as cc
    captured = {}
    real = cc.assemble_within_budget

    def spy(**kw):
        captured.update(kw)
        return real(**kw)

    cc.assemble_within_budget = spy
    try:
        # _FakeBackend has no effective_chat_context() -> falls back to ctx hint.
        c = ChatController(backend=_FakeBackend(ctx=200_000), user_mode="beginner")
        c.evaluate_turn("combien de memoire ?")
    finally:
        cc.assemble_within_budget = real
    assert captured.get("token_budget") == 200_000


def test_budget_caps_history_at_50_turns():
    # 60 turns of tiny content + a huge budget: the 50-turn guard keeps the
    # last 50 turns (100 messages) + the current message = 101.
    history = []
    for i in range(60):
        history.append({"role": "user", "content": f"q{i}"})
        history.append({"role": "assistant", "content": f"a{i}"})
    sysp, msgs = assemble_within_budget(
        user_mode="beginner", history=history,
        current_user_text="now", token_budget=1_000_000,
        history_window_turns=50)
    assert len(msgs) == 101                       # 50 turns + current
    contents = [m["content"] for m in msgs]
    assert "q9" not in contents                   # turn 9 (oldest 10) dropped
    assert "q10" in contents and "a59" in contents


TESTS = [
    test_estimate_tokens_monotonic,
    test_turn_context_concept_section,
    test_turn_context_include_flags,
    test_system_prompt_has_no_volatile_content,
    test_system_prompt_has_app_knowledge,
    test_app_knowledge_uses_provided_labels,
    test_build_system_prompt_board_facts,
    test_app_knowledge_manual_editing_is_allowed,
    test_app_knowledge_two_windows_and_transfer,
    test_app_knowledge_dropdown_and_manual_feature,
    test_app_knowledge_new_labels_are_localized,
    test_budget_keeps_everything_when_large,
    test_budget_drops_code_first,
    test_budget_drops_wiring_after_code,
    test_system_prompt_stable_across_code_changes,
    test_budget_trims_oldest_history,
    test_controller_injects_selected_board,
    test_controller_slm_uses_top1,
    test_controller_uses_effective_context,
    test_controller_falls_back_to_hint,
    test_budget_caps_history_at_50_turns,
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
