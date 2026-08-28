"""Tests pour le pre-chargement contextuel du chat (F2 etape 4)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.chat.chat_controller import ChatController, ChatTurnKind


class _StubBackend:
    """Backend qui capture le system_prompt recu pour assertion."""
    def __init__(self):
        self.last_system_prompt = None
    def chat(self, system_prompt, messages):
        self.last_system_prompt = system_prompt
        return "ok"
    def chat_stream(self, system_prompt, messages):
        self.last_system_prompt = system_prompt
        yield "ok"


def test_controller_has_system_extras_once_field():
    """Apres init, system_extras_once est vide."""
    ctrl = ChatController(backend=_StubBackend(), user_mode="beginner")
    assert ctrl.system_extras_once == "", (
        f"Expected empty default, got {ctrl.system_extras_once!r}"
    )


def test_system_extras_once_injected_in_next_turn():
    """Quand system_extras_once est set, le prochain tour LLM le recoit
    dans le system prompt, puis le champ est vide."""
    backend = _StubBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner")
    ctrl.system_extras_once = "EXTRA_CONTEXT_MARKER_42"

    result = ctrl.run_turn("Une question normale")
    assert result.kind == ChatTurnKind.LLM_REPLY
    assert backend.last_system_prompt is not None
    assert "EXTRA_CONTEXT_MARKER_42" in backend.last_system_prompt, (
        "Le system_extras_once n'a pas ete injecte dans le system prompt"
    )
    assert ctrl.system_extras_once == "", (
        "system_extras_once doit etre consume (vide) apres injection"
    )


def test_system_extras_once_not_persisted_to_second_turn():
    """Le 2e tour apres injection ne recoit PLUS les extras."""
    backend = _StubBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner")
    ctrl.system_extras_once = "EXTRA_ONLY_FIRST_TURN"

    ctrl.run_turn("Premier message")
    first_prompt = backend.last_system_prompt
    assert "EXTRA_ONLY_FIRST_TURN" in first_prompt

    ctrl.run_turn("Deuxieme message")
    second_prompt = backend.last_system_prompt
    assert "EXTRA_ONLY_FIRST_TURN" not in second_prompt, (
        "Le 2e tour ne doit pas recevoir les extras du 1er"
    )


def test_system_extras_once_skipped_on_heuristic_path():
    """Si l'eleve clique '?' puis tape un prompt qui est intercepte
    par les heuristiques (intent generation / off-scope), system_extras_once
    reste intact (pas de tour LLM consume) pour pouvoir etre utilise au
    prochain vrai tour LLM."""
    backend = _StubBackend()
    ctrl = ChatController(backend=backend, user_mode="beginner")
    ctrl.system_extras_once = "EXTRA_SHOULD_SURVIVE"

    result = ctrl.run_turn("Genere-moi un programme")  # GENERATION_REDIRECT
    assert result.kind == ChatTurnKind.GENERATION_REDIRECT
    assert ctrl.system_extras_once == "EXTRA_SHOULD_SURVIVE", (
        "Heuristique a consume system_extras_once a tort"
    )


TESTS = [
    test_controller_has_system_extras_once_field,
    test_system_extras_once_injected_in_next_turn,
    test_system_extras_once_not_persisted_to_second_turn,
    test_system_extras_once_skipped_on_heuristic_path,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
