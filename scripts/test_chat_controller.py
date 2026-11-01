"""Smoke test pipeline chat complet avec backend mock.

Run : python scripts/test_chat_controller.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.chat.chat_controller import (
    ChatController, ChatTurnResult, ChatTurnKind, StreamingRequired,
)


class MockBackend:
    """Backend factice qui enregistre les appels et retourne du texte fixe."""

    def __init__(self, response: str = "Mock LLM reply."):
        self.response = response
        self.calls: list[dict] = []

    def chat(self, system_prompt: str, messages: list[dict]) -> str:
        self.calls.append({
            "system": system_prompt,
            "messages": list(messages),
        })
        return self.response


# Intent generation -> redirection sans appel LLM
def test_generation_intent_redirects_no_llm():
    backend = MockBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner")
    result = ctrl.run_turn("fais clignoter une LED sur D5")
    assert result.kind == ChatTurnKind.GENERATION_REDIRECT
    assert backend.calls == [], "LLM should NOT be called for generation intent"
    assert "Studio" in result.text


# Off-scope -> refus sans appel LLM
def test_offscope_refuses_no_llm():
    backend = MockBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner")
    result = ctrl.run_turn("quelle est la capitale de l'Italie ?")
    assert result.kind == ChatTurnKind.OFFSCOPE_REFUSAL
    assert backend.calls == [], "LLM should NOT be called for off-scope"
    assert "périmètre" in result.text or "perimetre" in result.text.lower()


# Question valide -> appel LLM avec system prompt + history
def test_valid_question_calls_llm():
    backend = MockBackend(response="DHT11 envoie la temperature et l'humidite.")
    ctrl = ChatController(backend=backend, user_mode="beginner")
    result = ctrl.run_turn("comment marche le DHT11 ?")
    assert result.kind == ChatTurnKind.LLM_REPLY
    assert result.text == "DHT11 envoie la temperature et l'humidite."
    assert len(backend.calls) == 1
    call = backend.calls[0]
    assert "Arduino assistant" in call["system"]
    # Le contexte de tour (RAG / code / wiring) chevauche le DERNIER message
    # user (cf. assemble_within_budget) : la question doit y FIGURER, pas y etre
    # seule. Assertion par sous-chaine -> robuste que le RAG injecte ou non
    # (selon la presence de l'encodeur ONNX).
    last = call["messages"][-1]
    assert last["role"] == "user"
    assert "comment marche le DHT11 ?" in last["content"]


# RAG injection dans le DERNIER message user (contenu volatile, hors du prefixe
# cacheable) -- cf. assemble_within_budget.
def test_rag_injection_for_relevant_query():
    backend = MockBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner")
    ctrl.run_turn("comment utiliser le DHT11 pour la temperature ?")
    assert len(backend.calls) == 1
    last_content = backend.calls[0]["messages"][-1]["content"]
    assert "Relevant Arduino libraries" in last_content
    assert "DHT" in last_content


# Historique multi-tour : la fenetre (jusqu'a _MAX_HISTORY_TURNS=50, trimee par
# le budget tokens) est passee au LLM, le message user courant EN QUEUE. Avec un
# budget large (mock) et 7 tours seulement, tout l'historique tient. (Le cap a 50
# est couvert par test_budget_caps_history_at_50_turns.)
def test_history_window_keeps_turns_and_current_last():
    backend = MockBackend(response="reply")
    ctrl = ChatController(backend=backend, user_mode="advanced")
    for i in range(7):
        ctrl.run_turn(f"question {i}")
    msgs = backend.calls[-1]["messages"]
    # 6 tours precedents (user+assistant) + le message courant = 13.
    assert len(msgs) == 13, f"history messages: {len(msgs)}"
    assert msgs[-1]["role"] == "user"
    # Le contexte de tour peut preceder le texte -> comparaison par suffixe.
    assert msgs[-1]["content"].endswith("question 6")


# No backend -> message d'erreur sans crash
def test_no_backend_returns_error_message():
    ctrl = ChatController(backend=None, user_mode="beginner")
    result = ctrl.run_turn("comment marche le DHT11 ?")
    assert result.kind == ChatTurnKind.NO_BACKEND
    assert "Modèle IA" in result.text or "Modele IA" in result.text


# Mode passe au system prompt
def test_user_mode_in_system_prompt():
    backend = MockBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner")
    ctrl.run_turn("c'est quoi PWM ?")
    system = backend.calls[0]["system"]
    assert "User mode: beginner" in system
    assert "broche 5" in system or "User is a beginner" in system


# Drapeau correction_intent (sous-projet 2)
_SOME_CODE = "const int LED = 13;\nvoid setup(){}\nvoid loop(){}"

def test_correction_intent_flag_true_with_code():
    backend = MockBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner", code=_SOME_CODE)
    decision = ctrl.evaluate_turn("corrige le delai du blink")
    assert isinstance(decision, StreamingRequired)
    assert decision.correction_intent is True

def test_correction_intent_flag_false_without_code():
    # Gate « il y a du code » : pas de code -> pas de proposition.
    backend = MockBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner", code="")
    decision = ctrl.evaluate_turn("corrige le delai du blink")
    assert isinstance(decision, StreamingRequired)
    assert decision.correction_intent is False

def test_correction_intent_flag_false_neutral():
    backend = MockBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner", code=_SOME_CODE)
    decision = ctrl.evaluate_turn("comment marche un pull-up ?")
    assert isinstance(decision, StreamingRequired)
    assert decision.correction_intent is False

def test_force_answer_bypasses_the_generation_redirect():
    # QA D2 (2026-08-08), 2e volet : aucune heuristique d'intention ne sera
    # jamais exacte sur une phrase courte -- ce projet a deja ecarte les
    # embeddings (filet auto d'ambiguite) et le SLM pour ce genre de tache.
    # Plutot que de courir apres la precision, on rend l'ERREUR REPARABLE :
    # l'utilisateur peut demander au chat de repondre quand meme.
    backend = MockBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner", code="")
    text = "fais clignoter une LED"
    normal = ctrl.evaluate_turn(text)
    assert isinstance(normal, ChatTurnResult)
    assert normal.kind == ChatTurnKind.GENERATION_REDIRECT
    forced = ctrl.evaluate_turn(text, force_answer=True)
    assert isinstance(forced, StreamingRequired), forced


def test_force_answer_does_not_disable_the_other_guards():
    # Le contournement ne concerne QUE la redirection de generation : il ne
    # doit pas ouvrir la porte aux questions hors sujet.
    backend = MockBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner", code="")
    forced = ctrl.evaluate_turn("donne-moi une recette de gateau",
                                force_answer=True)
    assert isinstance(forced, ChatTurnResult)
    assert forced.kind == ChatTurnKind.OFFSCOPE_REFUSAL


def test_correction_intent_generation_priority_preserved():
    # Un message de generation court-circuite AVANT -> pas de StreamingRequired.
    backend = MockBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner", code=_SOME_CODE)
    decision = ctrl.evaluate_turn("ecris-moi un code de blink")
    assert isinstance(decision, ChatTurnResult)
    assert decision.kind == ChatTurnKind.GENERATION_REDIRECT


TESTS = [
    test_generation_intent_redirects_no_llm,
    test_offscope_refuses_no_llm,
    test_valid_question_calls_llm,
    test_rag_injection_for_relevant_query,
    test_history_window_keeps_turns_and_current_last,
    test_no_backend_returns_error_message,
    test_user_mode_in_system_prompt,
    test_correction_intent_flag_true_with_code,
    test_correction_intent_flag_false_without_code,
    test_correction_intent_flag_false_neutral,
    test_force_answer_bypasses_the_generation_redirect,
    test_force_answer_does_not_disable_the_other_guards,
    test_correction_intent_generation_priority_preserved,
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
