"""Orchestrator for a chat turn: heuristics -> RAG -> LLM.

Pipeline:
1. is_generation_intent(text) -> True: ChatTurnResult.GENERATION_REDIRECT
2. is_off_scope(text)         -> True: ChatTurnResult.OFFSCOPE_REFUSAL
3. backend is None            -> True: ChatTurnResult.NO_BACKEND
4. Otherwise: RAG (top-k governed by is_slm) + assemble_within_budget
   (system prompt + messages sized to the backend's token budget, board
   specs auto-injected) + backend.chat() -> LLM_REPLY

History is kept in-memory (list of role/content dicts). A sliding
window of up to _MAX_HISTORY_TURNS (50) turns is sent to the LLM,
then trimmed further to fit the backend's token budget
(assemble_within_budget). Older turns stay in self.history (for
persistence) but are excluded from the LLM context.

No project persistence handling here: it is the caller's responsibility
(ChatView) to push/load self.history into Project.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol

from .chat_heuristics import (
    is_generation_intent, is_off_scope, is_correction_intent,
)
from .chat_prompts import (
    GENERATION_REDIRECT_FR, OFFSCOPE_REFUSAL_FR, NO_BACKEND_FR,
    build_system_prompt, assemble_within_budget, APP_KNOWLEDGE_LABEL_KEYS,
)
from ..i18n import lang_manager
from .chat_rag import (
    CorpusIndex, load_default_corpus, load_concepts, find_board_entry,
)


_MAX_HISTORY_TURNS = 50   # upper guard (cloud); the token budget trims below

_SLM_TOP_K = 1
_LLM_TOP_K = 3
_SLM_MIN_SCORE = 0.7
_LLM_MIN_SCORE = 0.5


class ChatTurnKind(str, Enum):
    """Type of result returned by ChatController.run_turn()."""
    GENERATION_REDIRECT = "generation_redirect"
    OFFSCOPE_REFUSAL = "offscope_refusal"
    NO_BACKEND = "no_backend"
    LLM_REPLY = "llm_reply"
    ERROR = "error"


@dataclass
class ChatTurnResult:
    """Result of a chat turn.

    `kind` indicates the nature of the response (redirect, refusal, LLM
    reply, error). `text` is the content to display in the assistant bubble.
    `error_detail` is non-None only if kind == ERROR (for logging).
    """
    kind: ChatTurnKind
    text: str
    error_detail: str | None = None


@dataclass
class StreamingRequired:
    """Indicates that ChatView must launch a streaming worker to
    obtain the LLM response. evaluate_turn() returns this when the
    user request is not filtered out by the heuristics and a
    backend is available.

    system_prompt: system prompt already built (RAG + context).
    messages: {role, content} list ready for backend.chat_stream()
        (budget-trimmed history window + current user message at the tail).
    user_text: the user's original text, to pass to
        commit_streamed_turn() after the stream ends.
    correction_intent: True if the message expresses a correction
        intent AND there is code to correct -> ChatView will offer
        an additional « Corriger dans Studio » button after the response.
    """
    system_prompt: str
    messages: list[dict]
    user_text: str
    correction_intent: bool = False


class _ChatBackendProtocol(Protocol):
    """Minimal protocol for the backend (AIBackend or MockBackend)."""

    def chat(self, system_prompt: str,
              messages: list[dict]) -> str:
        ...


class ChatController:
    """Orchestrator for a chat turn. Holds the in-memory history."""

    def __init__(self,
                 *,
                 backend: _ChatBackendProtocol | None,
                 user_mode: str,
                 corpus_index: CorpusIndex | None = None,
                 # Project context -- updated by the caller between turns.
                 code: str = "",
                 wiring_summary: list[str] | None = None,
                 original_prompt: str = "",
                 user_material: str = "",
                 last_compile_error: str = ""):
        self.backend = backend
        self.user_mode = user_mode
        self.code = code
        self.wiring_summary = wiring_summary or []
        self.original_prompt = original_prompt
        self.user_material = user_material
        self.last_compile_error = last_compile_error
        # Selected board model (board_manager.model), pushed by the
        # caller. Used to auto-inject the board specs into the context.
        self.board_model: str = ""
        # Text document attached from the chat (persistent attachment,
        # distinct from the project's user_material). Combined into the system prompt.
        self.attachment_name: str = ""
        self.attachment_text: str = ""
        # Lazy RAG index (expensive to build? no, but let's avoid the IO if
        # the user never uses the chat).
        self._corpus_index = corpus_index
        # History format: [{"role", "content", "ts"}].
        self.history: list[dict] = []
        # Additional block injected into the system prompt of the NEXT
        # LLM turn only. Consumed + reset after use. Used by
        # ChatView.preload() for the contextual bridges (F2 step 4).
        self.system_extras_once: str = ""
        # Additional STICKY block injected into the system prompt of EVERY
        # LLM turn as long as it is non-empty (vs system_extras_once consumed
        # after 1 turn). Used by the correction safety net (F2 step 5):
        # the "CORRECTION: <id>" contract must stay active across the whole
        # multi-turn conversation until resolution/reset.
        self.system_extras_sticky: str = ""

    def _get_corpus_index(self) -> CorpusIndex:
        if self._corpus_index is None:
            self._corpus_index = CorpusIndex.from_entries(
                load_default_corpus() + load_concepts()
            )
        return self._corpus_index

    def _combined_material(self) -> str:
        """Reference material for the system prompt = project user_material
        + optional document attached from the chat (does not replace the project)."""
        if not self.attachment_text:
            return self.user_material
        block = (f"--- Document joint : {self.attachment_name} ---\n"
                 f"{self.attachment_text}")
        return (self.user_material + "\n\n" + block) if self.user_material else block

    def reset(self) -> None:
        """Clears the history (= 'Nouvelle conversation' click)."""
        self.history.clear()
        self.attachment_name = ""
        self.attachment_text = ""
        self.system_extras_sticky = ""

    def load_history(self, history: list[dict]) -> None:
        """Replaces the current history (on project switch)."""
        self.history = list(history)
        self.system_extras_sticky = ""

    def evaluate_turn(self, user_text: str, *, force_answer: bool = False):
        """Heuristic filter + build system prompt. Does NOT make the
        LLM call. Returns either an immediate ChatTurnResult (heuristic /
        no_backend / empty message), or a StreamingRequired that contains
        everything needed to launch the streaming worker.

        `force_answer` skips the generation redirect -- and ONLY that one.
        No intent heuristic on a short sentence will ever be exact (this
        project already dropped embeddings and an SLM for comparable tasks),
        so rather than chasing precision the mistake is made REPAIRABLE: the
        redirect bubble carries a « répondre quand même » button that replays
        the turn with this flag (QA D2, 2026-08-08). The off-scope refusal is
        deliberately NOT bypassed -- it answers a different question.

        Returns: ChatTurnResult | StreamingRequired
        """
        if not user_text or not user_text.strip():
            return ChatTurnResult(
                kind=ChatTurnKind.ERROR,
                text="Message vide.",
                error_detail="empty user message",
            )

        # 1. Generation intent.
        if not force_answer and is_generation_intent(user_text):
            return ChatTurnResult(
                kind=ChatTurnKind.GENERATION_REDIRECT,
                text=GENERATION_REDIRECT_FR,
            )

        # 2. Off-scope.
        if is_off_scope(user_text):
            return ChatTurnResult(
                kind=ChatTurnKind.OFFSCOPE_REFUSAL,
                text=OFFSCOPE_REFUSAL_FR,
            )

        # 3. Missing backend.
        if self.backend is None:
            return ChatTurnResult(
                kind=ChatTurnKind.NO_BACKEND,
                text=NO_BACKEND_FR,
            )

        # 4. RAG (top_k + threshold governed by is_slm).
        is_slm = bool(getattr(self.backend, "is_slm", False))
        top_k = _SLM_TOP_K if is_slm else _LLM_TOP_K
        min_score = _SLM_MIN_SCORE if is_slm else _LLM_MIN_SCORE
        rag_hits = self._get_corpus_index().query(
            user_text, top_k=top_k, min_score=min_score
        )

        # 5. Specs of the selected board (auto-injection).
        board_facts = None
        if self.board_model:
            entry = find_board_entry(self.board_model)
            if entry:
                board_facts = entry.get("facts") or None

        # 6. Assembly within the token budget.
        get_eff = getattr(self.backend, "effective_chat_context", None)
        if callable(get_eff):
            budget = int(get_eff() or 8192)
        else:
            budget = int(getattr(self.backend, "context_window_hint", 8192)
                         or 8192)
        # App-knowledge UI labels in the user's current language, so the
        # assistant quotes what is actually shown on screen.
        strings = lang_manager.current
        app_labels = {k: getattr(strings, k, "")
                      for k in APP_KNOWLEDGE_LABEL_KEYS}
        system, messages = assemble_within_budget(
            user_mode=self.user_mode,
            code=self.code,
            wiring_summary=self.wiring_summary,
            original_prompt=self.original_prompt,
            user_material=self._combined_material(),
            last_compile_error=self.last_compile_error,
            rag_hits=rag_hits,
            board_facts=board_facts,
            history=self.history,
            current_user_text=user_text,
            token_budget=budget,
            history_window_turns=_MAX_HISTORY_TURNS,
            app_labels=app_labels,
        )
        # STICKY injection (persists as long as non-empty) then one-shot.
        if self.system_extras_sticky:
            system = system + "\n\n" + self.system_extras_sticky
        if self.system_extras_once:
            system = system + "\n\n" + self.system_extras_once
            self.system_extras_once = ""
        correction_intent = (
            is_correction_intent(user_text) and bool(self.code.strip())
        )
        return StreamingRequired(
            system_prompt=system,
            messages=messages,
            user_text=user_text,
            correction_intent=correction_intent,
        )

    def commit_streamed_turn(self, user_text: str,
                              full_text: str) -> None:
        """Persists the 2 user + assistant messages into history after
        the stream ends (or after a stop with a partial). To be called
        only when the assistant response is consolidated."""
        ts = datetime.now().isoformat()
        self.history.append(
            {"role": "user", "content": user_text, "ts": ts}
        )
        self.history.append(
            {"role": "assistant", "content": full_text, "ts": ts}
        )

    def run_turn(self, user_text: str) -> ChatTurnResult:
        """Synchronous wrapper: calls evaluate_turn, then if streaming
        is required makes the blocking chat() call and commits. Kept for
        compat with the existing tests."""
        decision = self.evaluate_turn(user_text)
        if isinstance(decision, ChatTurnResult):
            return decision
        # StreamingRequired -> blocking synchronous call.
        try:
            reply_text = self.backend.chat(
                system_prompt=decision.system_prompt,
                messages=decision.messages,
            )
        except Exception as e:
            return ChatTurnResult(
                kind=ChatTurnKind.ERROR,
                text=f"Erreur lors de l'appel au modèle : {e}",
                error_detail=str(e),
            )
        self.commit_streamed_turn(decision.user_text, reply_text)
        return ChatTurnResult(
            kind=ChatTurnKind.LLM_REPLY,
            text=reply_text,
        )
