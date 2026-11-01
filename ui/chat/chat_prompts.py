"""Templates de system prompt pour le chat MVP.

Redige en ANGLAIS pour :
- economie tokens (~30-50% vs francais ; accents = +1 token chacun)
- meilleur suivi d'instructions par les SLM 7B (langue d'entrainement
  dominante)
- coherence avec build_wiring_addendum (ui/ai_backends/codegen_rules.py)

La reponse de l'assistant est en FRANCAIS par defaut, via instruction
explicite dans le prompt. Modeles >=7B gerent ca nativement.
"""
from __future__ import annotations

from .chat_rag import CorpusHit


_MAX_CODE_LINES = 120


# UI label keys cited by the app-knowledge section. They are resolved against
# the CURRENT language (by the caller, from lang_manager.current) so the
# assistant quotes the labels the user actually sees on screen.
APP_KNOWLEDGE_LABEL_KEYS = (
    "studio_prompt_label", "studio_generate", "gen_modal_title",
    "gen_modal_regenerate", "gen_modal_add", "gen_modal_correct",
    "studio_functions_title", "nav_bibliotheque", "menu_card", "mn_goto_board",
    "studio_compile_upload", "studio_upload_only", "studio_serial_monitor_chk",
    "studio_bottom_collapsed_title", "studio_action_schema", "clarify_title",
    "studio_tools_panel_title", "studio_tool_repair", "mode_beginner",
    "mode_intermediate", "mode_advanced", "board_coming_soon", "menu_view",
    "settings_title",
    # Vue avancée 2 fenêtres + gestion des fonctionnalités (#34) :
    "studio_window_ai", "studio_window_stable", "studio_transfer_to_stable",
    "studio_manual_feature_label", "ctx_menu_assign_feature",
    "feature_action_regen", "feature_action_delete",
)

# English fallbacks, used when a label is absent (e.g. unit tests that pass no
# labels). Keeps the section present and the prose grammatical.
_APP_LABEL_FALLBACK = {
    "studio_prompt_label": "Generate a feature",
    "studio_generate": "Generate",
    "gen_modal_title": "What do you want to do?",
    "gen_modal_regenerate": "Regenerate",
    "gen_modal_add": "Add a feature",
    "gen_modal_correct": "Modify",
    "studio_functions_title": "Features",
    "nav_bibliotheque": "Libraries",
    "menu_card": "Board",
    "mn_goto_board": "Select board/port…",
    "studio_compile_upload": "Compile & Upload",
    "studio_upload_only": "Upload",
    "studio_serial_monitor_chk": "Serial monitor",
    "studio_bottom_collapsed_title": "Log and serial monitor",
    "studio_action_schema": "View diagram",
    "clarify_title": "Specify the component",
    "studio_tools_panel_title": "Tools",
    "studio_tool_repair": "Analyse / Repair the code",
    "mode_beginner": "Beginner",
    "mode_intermediate": "Intermediate",
    "mode_advanced": "Advanced",
    "board_coming_soon": "Coming soon",
    "menu_view": "View",
    "settings_title": "Settings",
    "studio_window_ai": "Generated code (AI)",
    "studio_window_stable": "Stable code",
    "studio_transfer_to_stable": "Transfer to stable",
    "studio_manual_feature_label": "Manual edits",
    "ctx_menu_assign_feature": "Assign to a feature",
    "feature_action_regen": "Regenerate",
    "feature_action_delete": "Delete",
}


def _app_label(labels: dict[str, str] | None, key: str) -> str:
    """Label for `key` in the caller-provided language, else English fallback."""
    if labels:
        val = labels.get(key)
        if val:
            return val
    return _APP_LABEL_FALLBACK.get(key, key)


def _estimate_tokens(text: str) -> int:
    """Estimation grossiere du nombre de tokens (~4 chars/token). Pour le
    budgeting defensif, pas pour la facturation. Minimum 1."""
    return max(1, len(text) // 4)


def _truncate_code(code: str, max_lines: int = _MAX_CODE_LINES) -> str:
    """Tronque le code Arduino a max_lines, ajoute '... (truncated)' sinon."""
    if not code:
        return ""
    lines = code.splitlines()
    if len(lines) <= max_lines:
        return code
    return "\n".join(lines[:max_lines]) + "\n// ... (rest truncated)"


def _format_wiring(wiring_summary: list[str] | None) -> str:
    """Formate la liste de composants detectes en bullet list."""
    if not wiring_summary:
        return ""
    return "\n".join(f"- {line}" for line in wiring_summary)


def _format_rag(hits: list[CorpusHit]) -> str:
    """Formate les top-k hits RAG en bullet list pour le system prompt."""
    if not hits:
        return ""
    out: list[str] = []
    for h in hits:
        entry = h.entry
        name = entry.get("name", "?")
        author = entry.get("author", "")
        headers = entry.get("headers") or []
        desc = entry.get("description", "")
        # Trim description pour ne pas exploser les tokens.
        if len(desc) > 200:
            desc = desc[:200] + "..."
        headers_str = ", ".join(headers) if headers else "(no headers)"
        author_str = f" ({author})" if author else ""
        out.append(f"- {name}{author_str}. Headers: {headers_str}.\n  {desc}")
    return "\n".join(out)


def _is_concept_entry(entry: dict) -> bool:
    """True for a reference-fact entry (concept, board, hardware trap...).

    Structural on purpose: an entry qualifies because it CARRIES `summary` or
    `facts`, not because its category appears in a hand-kept list. The
    previous whitelist form -- `category in ("concept", "board")` -- silently
    misrouted any NEW category into the library block, where `_format_rag`
    prints "Headers: (no headers)" and DROPS `facts`, which is the actionable
    part. Measured 2026-08-20: 0 of the 91 corpus libraries carry
    `summary`/`facts`, and 0 of the 79 concepts (of the time) lack both, so
    the split was exact then; `test_chat_hardware_traps.py` keeps it exact
    as entries are added or removed.
    """
    return bool(entry.get("summary") or entry.get("facts"))


def _format_concepts(hits: list[CorpusHit]) -> str:
    """Formate les hits concept/carte : nom + summary + facts en puces."""
    if not hits:
        return ""
    out: list[str] = []
    for h in hits:
        e = h.entry
        name = e.get("name", "?")
        summary = e.get("summary", "")
        lines = [f"- {name}: {summary}".rstrip(": ").rstrip()]
        for fact in (e.get("facts") or []):
            lines.append(f"  - {fact}")
        out.append("\n".join(lines))
    return "\n".join(out)


def build_system_prompt(
    *,
    user_mode: str,
    board_facts: list[str] | None = None,
    original_prompt: str = "",
    user_material: str = "",
    app_labels: dict[str, str] | None = None,
) -> str:
    """Build the STABLE part of the chat system prompt.

    Holds only what does NOT change from one turn to the next within a
    conversation: the assistant role, the rules, the app knowledge, the user
    mode, and the project's stable facts (selected board, original atelier
    prompt, reference material). The per-turn VOLATILE content (current code,
    wiring, compile error, query-dependent RAG hits) lives in
    build_turn_context() and is appended to the current user message instead.

    Keeping this prefix byte-identical across turns lets the backend reuse its
    prompt cache (Anthropic cache_control, OpenAI/Gemini implicit prefix cache,
    Ollama KV-cache), so old turns are re-billed at a fraction of the cost.

    `board_facts`: specs of the selected board, always injected (stable).
    """
    sections: list[str] = []

    # UI labels (L) are resolved in the user's current language so the
    # assistant quotes exactly what is shown on screen.
    def L(key: str) -> str:
        return _app_label(app_labels, key)

    sections.append(
        "You are the Arduino assistant inside Promptuino, an educational tool "
        "that AUTO-GENERATES Arduino code from the student's natural-language "
        "requests and AUTO-INSTALLS any required libraries. Generating from a "
        "description is the primary workflow and libraries are never installed "
        "by hand, though the student MAY also edit the code directly. The user "
        "works on an Arduino project."
    )
    sections.append(
        "# Rules\n"
        "- Stay within Arduino / embedded / current project. "
        "Refuse off-topic politely.\n"
        "- Be honest if you don't know. Don't invent.\n"
        "- Short code snippets in explanations are FINE (a few lines in "
        "```cpp blocks``` to illustrate a concept). But for FULL programs "
        "or complete .ino sketches with setup()+loop(), redirect to the "
        f"\"{L('studio_prompt_label')}\" field.\n"
        "- The user works in Promptuino (this app), NOT Arduino IDE. "
        "Libraries auto-install when the code references them. "
        "Never suggest manual installation steps via Library Manager.\n"
        "- Do NOT use LaTeX or MathJax syntax ($$, \\(, etc.). "
        "Use plain text or markdown code blocks for formulas.\n"
        "- Answer in the user's language (default: French).\n"
        "- Response detail is driven by the user's message, not a fixed "
        "setting. DEFAULT: a balanced answer (a few sentences, one example "
        "if useful). If the user explicitly asks to be brief/short "
        "(e.g. \"en bref\", \"juste le code\", \"keep it short\", \"breve\", "
        "\"in breve\"), reply in 1-2 sentences with no preamble. If they ask "
        "for depth (e.g. \"détaille\", \"explique en détail\", \"in depth\", "
        "\"en detalle\", \"in dettaglio\"), give a full explanation "
        "(examples, edge cases, why + how). Detect this intent in FR/EN/ES/IT."
    )

    # App knowledge: lets the chat answer "how do I use the app" questions.
    sections.append(
        "# About Promptuino (this app)\n"
        "Promptuino is the desktop app the user is running. Use these facts "
        "to answer questions about how to use it. Quoted UI labels are in the "
        "user's language, exactly as shown on screen:\n"
        f"- Code is created from natural language: the user types a description "
        f"in the \"{L('studio_prompt_label')}\" field and clicks "
        f"\"{L('studio_generate')}\". A dialog \"{L('gen_modal_title')}\" then "
        f"offers \"{L('gen_modal_regenerate')}\" (start over), "
        f"\"{L('gen_modal_add')}\" (keep current code, add a behavior), or "
        f"\"{L('gen_modal_correct')}\" (change an existing feature). The student "
        f"can ALSO edit the code directly in the editor: it is hidden in "
        f"\"{L('mode_beginner')}\" mode but shown and editable in "
        f"\"{L('mode_intermediate')}\" and \"{L('mode_advanced')}\".\n"
        f"- The generated behaviors are listed in the "
        f"\"{L('studio_functions_title')}\" dropdown: tick a feature to "
        f"highlight its lines, or use its per-feature "
        f"\"{L('feature_action_regen')}\" / \"{L('feature_action_delete')}\" "
        f"buttons. Hand edits that belong to no generated feature are grouped "
        f"under a \"{L('studio_manual_feature_label')}\" entry; right-clicking "
        f"the code offers \"{L('ctx_menu_assign_feature')}\" to reassign lines "
        "to a feature.\n"
        f"- In \"{L('mode_advanced')}\" mode the code area splits into two "
        f"windows: \"{L('studio_window_ai')}\" (what the AI writes) and "
        f"\"{L('studio_window_stable')}\" (edited by hand, never overwritten by "
        f"the AI). \"{L('studio_transfer_to_stable')}\" copies features from the "
        f"AI window to the stable one (a drag-and-drop transfer popup lets the "
        f"user choose which); each window has its own compile & upload.\n"
        "- Libraries install AUTOMATICALLY when the generated code needs them. "
        f"The \"{L('settings_title')}\" dialog also has a "
        f"\"{L('nav_bibliotheque')}\" section to search/install/remove them "
        "manually.\n"
        f"- To run code on the board: choose board + port via the "
        f"\"{L('menu_card')}\" menu (\"{L('mn_goto_board')}\"), then "
        f"\"{L('studio_compile_upload')}\"; \"{L('studio_upload_only')}\" "
        "sends the current code.\n"
        f"- The \"{L('studio_serial_monitor_chk')}\" shows what the board "
        f"prints over Serial, in the bottom "
        f"\"{L('studio_bottom_collapsed_title')}\" panel.\n"
        f"- Wiring: \"{L('studio_action_schema')}\" opens an interactive "
        "diagram of how to wire the components. If the app picked the wrong "
        "component, the user fixes it FROM the diagram (gear icon on that "
        "component) and the app then offers to regenerate the code — there "
        "is no pre-generation clarification dialog anymore.\n"
        f"- AI tools on the code (\"{L('studio_tools_panel_title')}\"): explain "
        "selected lines, detect antipatterns, add teaching comments, "
        f"analyse/repair compile errors (\"{L('studio_tool_repair')}\" compiles "
        "first, then repairs until the code builds), and format the code.\n"
        f"- Three display modes (\"{L('mode_beginner')}\" / "
        f"\"{L('mode_intermediate')}\" / \"{L('mode_advanced')}\") reveal "
        "controls progressively; they change ONLY what is shown, never the "
        "generated code.\n"
        f"- Boards: only Arduino is active. ESP32 shows as "
        f"\"{L('board_coming_soon')}\" and cannot be selected yet.\n"
        f"- Settings (language, light/dark theme) live in the "
        f"\"{L('settings_title')}\" panel; the theme is also in the "
        f"\"{L('menu_view')}\" menu.\n"
        "- This chat is for questions, explanations and advice (Arduino, the "
        "current project, or how to use this app). It does NOT generate full "
        f"programs — that is the \"{L('studio_prompt_label')}\" field."
    )

    mode_section = f"# User mode: {user_mode}"
    if user_mode == "beginner":
        mode_section += (
            "\nUser is a beginner. Avoid jargon. Say \"broche 5\" not \"D5\". "
            "Use \"tu\". Reference the diagram visually when possible."
        )
    else:
        mode_section += "\nTechnical wording OK. Pins as D5/A0/etc. fine."
    sections.append(mode_section)

    project_parts: list[str] = []
    if board_facts:
        project_parts.append(
            "## Selected board\n"
            + "\n".join(f"- {f}" for f in board_facts)
        )
    if original_prompt:
        project_parts.append(
            "## Original atelier prompt\n\"" + original_prompt + "\""
        )
    if user_material:
        project_parts.append("## User material\n" + user_material)
    if project_parts:
        sections.append("# Project context\n" + "\n\n".join(project_parts))

    return "\n\n".join(sections)


def build_turn_context(
    *,
    code: str = "",
    wiring_summary: list[str] | None = None,
    last_compile_error: str = "",
    rag_hits: list[CorpusHit] | None = None,
    include_code: bool = True,
    include_wiring: bool = True,
) -> str:
    """Build the VOLATILE per-turn context block.

    Everything here can change from one turn to the next: the current code, the
    detected wiring, the last compile error, and the query-dependent RAG hits.
    It is appended to the CURRENT user message (never to the cached system
    prefix), so a code change busts only this block, not the cached prefix.

    `include_code` / `include_wiring`: let the budget sacrifice these sections
    (see assemble_within_budget). Returns "" when there is nothing to add.
    """
    sections: list[str] = []

    project_parts: list[str] = []
    if include_code and code:
        project_parts.append(
            "## Code Arduino\n```cpp\n" + _truncate_code(code) + "\n```"
        )
    wiring_str = _format_wiring(wiring_summary) if include_wiring else ""
    if wiring_str:
        project_parts.append("## Detected wiring\n" + wiring_str)
    if last_compile_error:
        project_parts.append("## Last compile error\n" + last_compile_error)
    if project_parts:
        sections.append(
            "# Current project state\n" + "\n\n".join(project_parts)
        )

    hits = rag_hits or []
    lib_hits = [h for h in hits if not _is_concept_entry(h.entry)]
    concept_hits = [h for h in hits if _is_concept_entry(h.entry)]
    lib_str = _format_rag(lib_hits)
    if lib_str:
        sections.append("# Relevant Arduino libraries\n" + lib_str)
    concept_str = _format_concepts(concept_hits)
    if concept_str:
        sections.append(
            "# Reference facts (concepts & boards)\n" + concept_str
        )

    return "\n\n".join(sections)


def assemble_within_budget(
    *,
    user_mode: str,
    code: str = "",
    wiring_summary: list[str] | None = None,
    original_prompt: str = "",
    user_material: str = "",
    last_compile_error: str = "",
    rag_hits: list[CorpusHit] | None = None,
    board_facts: list[str] | None = None,
    history: list[dict] | None = None,
    current_user_text: str = "",
    token_budget: int = 8192,
    history_window_turns: int = 5,
    app_labels: dict[str, str] | None = None,
) -> tuple[str, list[dict]]:
    """Assemble (system_prompt, messages) within a token budget.

    Layout (most stable first, so the prefix is prompt-cacheable):
      system   = stable: rules + app knowledge + mode + board/original/material
      messages = [history window] + [current user message]
      current user message = volatile turn context (code, wiring, compile
                             error, RAG hits) + the user's question

    Sacrifice order on overflow (least precious first):
    1. code section, 2. wiring section, 3. history turns (oldest first).
    Never sacrificed: rules + mode + app knowledge + RAG + board facts
    + stable project facts + current question.
    """
    history = history or []
    reserve = min(2048, token_budget // 4)
    available = token_budget - reserve

    # The system prompt holds only stable content (cacheable prefix); it does
    # not depend on the sacrifice flags, so build it once.
    system = build_system_prompt(
        user_mode=user_mode, board_facts=board_facts,
        original_prompt=original_prompt, user_material=user_material,
        app_labels=app_labels,
    )
    recent = list(history[-(2 * history_window_turns):])

    def build(inc_code: bool, inc_wiring: bool,
              recent_msgs: list[dict]) -> list[dict]:
        # Volatile context rides on the CURRENT user message, after history,
        # so it stays out of the cached prefix.
        turn_ctx = build_turn_context(
            code=code, wiring_summary=wiring_summary,
            last_compile_error=last_compile_error, rag_hits=rag_hits,
            include_code=inc_code, include_wiring=inc_wiring,
        )
        content = (turn_ctx + "\n\n" + current_user_text
                   if turn_ctx else current_user_text)
        msgs = [{"role": m["role"], "content": m["content"]}
                for m in recent_msgs]
        msgs.append({"role": "user", "content": content})
        return msgs

    def total(msgs: list[dict]) -> int:
        return _estimate_tokens(system) + sum(
            _estimate_tokens(m["content"]) for m in msgs
        )

    msgs = build(True, True, recent)
    if total(msgs) <= available:
        return system, msgs
    msgs = build(False, True, recent)
    if total(msgs) <= available:
        return system, msgs
    msgs = build(False, False, recent)
    if total(msgs) <= available:
        return system, msgs
    while recent:
        recent = recent[2:]
        msgs = build(False, False, recent)
        if total(msgs) <= available:
            return system, msgs
    return system, msgs


# Reponses standardisees pour les filtres heuristiques

GENERATION_REDIRECT_FR = (
    "Cette demande ressemble à une génération de code. "
    "Utilise le champ **Générer une fonctionnalité** (en haut à droite de la fenêtre Studio) "
    "pour la décrire et lancer la génération."
)

OFFSCOPE_REFUSAL_FR = (
    "Cette question sort du périmètre Arduino. "
    "Je peux t'aider sur le projet en cours : code, branchements, "
    "erreurs de compilation, librairies."
)

NO_BACKEND_FR = (
    "Aucun modèle IA n'est activé. Va dans l'onglet **Modèle IA** "
    "(barre latérale) pour en activer un."
)
