"""Abstract base class for all AI backends."""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ui.ai_backends.codegen_rules import build_wiring_addendum

# The hardware rules injected into the system prompt (universal rule +
# disambiguation + conditional motor block) live in codegen_rules.py.
# The motor block is only added if the prompt (generation) or the code
# (repair) mentions a motor — see build_wiring_addendum / mentions_motor.


# ── Repair via localized edits (SEARCH/REPLACE) ───────────────────────────
# The model NO LONGER rewrites the whole file (which, on a local SLM, truncates the
# end of the code as soon as prompt+output exceed num_ctx). It emits
# SEARCH/REPLACE blocks that we apply by EXACT search: anything not inside
# a block is copied verbatim → the end of the file can no longer be cut off. A
# SEARCH that is not found or is ambiguous is REJECTED (never applied at random). See
# docs/superpowers/specs/2026-06-22-repair-search-replace-design.md


@dataclass
class Edit:
    """A localized edit: replace the EXACT text `search` with `replace`."""
    search: str
    replace: str


def _parse_search_replace_blocks(text: str) -> list[Edit]:
    """Extract the `<<<<<<< SEARCH … ======= … >>>>>>> REPLACE` blocks.

    Tolerant of whitespace around the markers. Malformed blocks (missing
    separator or closing marker) are ignored silently rather than crashing."""
    lines = text.split("\n")

    def is_search_start(l: str) -> bool:
        s = l.lstrip()
        return s.startswith("<<<<<<<") and "SEARCH" in s.upper()

    def is_divider(l: str) -> bool:
        s = l.strip()
        return len(s) >= 3 and set(s) == {"="}

    def is_replace_end(l: str) -> bool:
        s = l.lstrip()
        return s.startswith(">>>>>>>") and "REPLACE" in s.upper()

    edits: list[Edit] = []
    i, n = 0, len(lines)
    while i < n:
        if not is_search_start(lines[i]):
            i += 1
            continue
        i += 1
        search_lines: list[str] = []
        while i < n and not (is_divider(lines[i]) or is_search_start(lines[i])
                             or is_replace_end(lines[i])):
            search_lines.append(lines[i])
            i += 1
        if i >= n or not is_divider(lines[i]):
            continue   # malformed: no separator
        i += 1
        replace_lines: list[str] = []
        while i < n and not (is_replace_end(lines[i]) or is_divider(lines[i])
                             or is_search_start(lines[i])):
            replace_lines.append(lines[i])
            i += 1
        if i >= n or not is_replace_end(lines[i]):
            continue   # malformed: no closing marker
        i += 1
        edits.append(Edit("\n".join(search_lines), "\n".join(replace_lines)))
    return edits


def _reindent(lines: list[str], delta: int) -> list[str]:
    """Shift each line's indentation by `delta` spaces (clamped to 0)."""
    out = []
    for ln in lines:
        if not ln.strip():
            out.append(ln)            # empty line: no spurious indentation
        elif delta > 0:
            out.append(" " * delta + ln)
        elif delta < 0:
            existing = len(ln) - len(ln.lstrip(" "))
            out.append(ln[min(existing, -delta):])
        else:
            out.append(ln)
    return out


def _apply_normalized(code: str, search: str, replace: str) -> str | None:
    """Line-by-line match ignoring indentation (each line `strip()`).
    Replaces ONLY if the match is UNIQUE, preserving the original
    indentation of the matched region. None if not found/ambiguous."""
    code_lines = code.split("\n")
    search_lines = search.split("\n")
    k = len(search_lines)
    if k == 0 or not search.strip():
        return None
    norm = [l.strip() for l in search_lines]
    starts = [s for s in range(len(code_lines) - k + 1)
              if [l.strip() for l in code_lines[s:s + k]] == norm]
    if len(starts) != 1:
        return None
    s = starts[0]
    indent_code = code_lines[s][:len(code_lines[s]) - len(code_lines[s].lstrip(" "))]
    indent_search = search_lines[0][:len(search_lines[0]) - len(search_lines[0].lstrip(" "))]
    delta = len(indent_code) - len(indent_search)
    repl = _reindent(replace.split("\n"), delta)
    new_lines = code_lines[:s] + repl + code_lines[s + k:]
    return "\n".join(new_lines)


def _apply_edits(code: str, edits: list[Edit]) -> tuple[str, int, list[str]]:
    """Apply the edits sequentially. Returns (code, nb_applied,
    rejects). Per-block strategy: unique EXACT match → else unique
    whitespace-normalized match → else REJECT (not found or ambiguous)."""
    applied = 0
    rejected: list[str] = []
    for e in edits:
        if not e.search.strip():
            rejected.append(e.search)
            continue
        cnt = code.count(e.search)
        if cnt == 1:
            code = code.replace(e.search, e.replace, 1)
            applied += 1
            continue
        if cnt > 1:
            rejected.append(e.search)     # ambiguous: we don't guess
            continue
        new_code = _apply_normalized(code, e.search, e.replace)
        if new_code is None:
            rejected.append(e.search)
        else:
            code = new_code
            applied += 1
    return code, applied, rejected


def _strip_strings_comments(code: str) -> str:
    """Remove comments and string/char literals so their braces/parens are
    NOT counted (e.g. `Serial.println("}")`). Mirror of the arduino_cli
    helper (kept local to avoid an ai_backends -> arduino_cli import cycle)."""
    code = re.sub(r'//[^\n]*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r'"(?:\\.|[^"\\])*"', '', code)
    code = re.sub(r"'(?:\\.|[^'\\])*'", '', code)
    return code


def _repair_acceptable(before: str, after: str) -> bool:
    """Structural safeguard: rejects a repair that breaks/butchers the
    file (the real bulwark remains SEARCH/REPLACE; this is just a net).

    Brace/paren balance is checked on a string/comment-STRIPPED copy: a
    legitimate fix that adds `Serial.println("}")` or a comment with a brace
    must not be counted as an imbalance (bug 2026-07-06 — the raw count made
    the guard reject valid fixes)."""
    if not after.strip():
        return False
    if len(after) < 0.85 * len(before):       # massive collapse
        return False
    sb, sa = _strip_strings_comments(before), _strip_strings_comments(after)
    for op, cl in (("{", "}"), ("(", ")")):   # no more unbalanced than before
        bal_before = sb.count(op) - sb.count(cl)
        bal_after = sa.count(op) - sa.count(cl)
        if bal_after != 0 and abs(bal_after) > abs(bal_before):
            return False
    for kw in ("setup(", "loop("):            # key structures preserved
        if kw in before and kw not in after:
            return False
    return True


def _split_summary(text: str) -> tuple[str, str]:
    """Separate the `[SUMMARY]…[/SUMMARY]` block from the rest. Returns (summary, rest)."""
    m = re.search(r'\[SUMMARY\](.*?)\[/SUMMARY\]', text, re.DOTALL)
    if m:
        return m.group(1).strip(), text[m.end():]
    return "", text


def _strip_md_fences(text: str) -> str:
    """Strip any markdown ```…``` fences around a code block."""
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


def _apply_repair_response(code: str, raw: str) -> tuple[str, str]:
    """Full pipeline for a repair response. Returns (final_code,
    summary); (original code unchanged, "") if nothing usable.

    Two paths, in order:
      1. **Localized edits** SEARCH/REPLACE if the model produced any (ideal:
         preserves everything by construction). If blocks exist but none
         applies cleanly → we stop there (we do NOT mistake the text of the
         blocks for complete code).
      2. **Whole file**: if NO block, the model most likely
         returned the full corrected program (the case for local SLMs, incapable
         of the SEARCH/REPLACE format). We accept it ONLY if it passes the
         structural safeguard — anti-gutting and anti-truncation (num_ctx already
         prevents truncation upstream).
    In all cases, a result that would break/butcher the file is
    rejected → original code kept (the calling loop will do the revert)."""
    summary, body = _split_summary(raw)
    edits = _parse_search_replace_blocks(body)
    if edits:
        new_code, applied, _rejected = _apply_edits(code, edits)
        if applied and _repair_acceptable(code, new_code):
            return new_code, summary
        return code, ""
    candidate = _strip_md_fences(body)
    if candidate and candidate.strip() != code.strip() \
            and _repair_acceptable(code, candidate):
        return candidate, summary
    return code, ""


class AIBackend(ABC):

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Internal identifier (e.g.: 'claude_code')."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name displayed in the UI."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description displayed under the title."""

    @property
    def requires_api_key(self) -> bool:
        return False

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the backend can be used in the current state."""

    # ── Model capabilities (for the chat's context budget) ──

    @property
    def context_window_hint(self) -> int:
        """Approximate size of the model's context window, in
        tokens. Cautious local SLM default (~8k). Override per backend."""
        return 8192

    def effective_chat_context(self) -> int:
        """Tokens the backend actually attends to for ONE chat turn.

        Default: the declared window (cloud / CLI APIs attend the whole
        window). Override where the runtime budget differs from the model's
        nominal context (e.g. Ollama, which only allocates `num_ctx`)."""
        return self.context_window_hint

    def generation_context(self) -> int:
        """Tokens available for ONE code generation — prompt AND output.

        Distinct from `effective_chat_context`: the generation path has its
        own budget (Ollama allocates a different `num_ctx` there, and the chat
        slider must not move it). Same default, overridden where the runtime
        budget differs.

        Exists for TODO #48: nothing checked that the prompt fit, and beyond a
        certain project size the model silently loses the beginning of the
        context — it then writes code that ignores part of the sketch, without
        a word."""
        return self.context_window_hint

    @property
    def is_slm(self) -> bool:
        """True if a small local model for which we reduce RAG noise
        (top-1, raised threshold). Default False (cloud / unknown size)."""
        return False

    # ── Generation ────────────────────────────────────────────

    @abstractmethod
    def generate_code(self, user_prompt: str, board_name: str,
                      rules_prompt: str | None = None) -> str:
        """
        Generate embedded code from a natural-language prompt.
        Returns the raw source code (without markdown fences).

        `rules_prompt` (default = user_prompt) is the text on which the
        conditional injection of the motor rules is decided (cf. build_wiring_addendum).
        Pass the RAW USER prompt here, NOT the RAG-augmented
        version: otherwise a motor lib example retrieved by the RAG triggers the
        motor block by mistake.
        """

    @abstractmethod
    def fix_code(self, code: str, error: str, board_name: str) -> str:
        """
        Fix the code based on a compilation error message.
        Returns the corrected code (without markdown fences).

        LEGACY: NOT used by the repair pipeline anymore (which goes through
        `repair_region` line-anchored + `repair_code` whole-file). Kept for
        the ABC contract / a possible external caller; only exercised by
        `scripts/test_openai_compat_backend.py`. Do not build new paths on it.
        """

    @abstractmethod
    def explain_error(self, error: str, language: str) -> str:
        """
        Explain a technical error message in natural language.
        language : language name in English (e.g. "French", "English"…)
        Returns a short explanation (1-2 sentences), without markdown.
        """

    @abstractmethod
    def explain_code(self, code: str, selection: str, language: str,
                     board_name: str) -> str:
        """
        Explain in natural language what the lines of `selection` do
        in the context of the complete `code`.
        `language` : language name in English (e.g. "French").
        Returns a prose explanation (not code). Can be multi-paragraph.
        If `selection` is empty, explain the whole code.
        """

    @abstractmethod
    def lint_code(self, code: str, language: str, board_name: str) -> str:
        """
        Detect embedded antipatterns in `code` (blocking delay(),
        dynamic String on Uno, missing pinMode, built-in LED pin conflict,
        int instead of long for millis(), etc.) and return a
        structured list in natural language (markdown).
        """

    @abstractmethod
    def add_comments(self, code: str, language: str, board_name: str) -> str:
        """
        Return the `code` enriched with pedagogical comments (in
        `language`) without changing the logic. Output = pure source code,
        without markdown fences.
        """

    @abstractmethod
    def repair_code(self, code: str, errors: str, language: str,
                    board_name: str) -> tuple[str, str]:
        """
        Aggressive repair of code that could not be repaired by
        `fix_code` in 3 attempts. Allowed to restructure more
        broadly. `errors` may be empty (manual call).
        `language` : language of the explanatory summary (e.g. "French").
        Returns `(repaired_code, summary)`. The summary is markdown
        listing the fixes (one bullet per fix). If the AI does not provide
        one, the summary is an empty string.
        """

    @abstractmethod
    def chat(self, system_prompt: str,
              messages: list[dict]) -> str:
        """Conversational multi-turn. Used by the Chat MVP panel.

        `system_prompt` : pre-built system prompt (see chat_prompts.py).
        `messages` : user/assistant alternation in chronological order,
            ending with the current user message.
            Format : [{"role": "user"|"assistant", "content": str}, ...]
        Returns : assistant response (raw text or markdown). Without fences.
        """

    def chat_stream(self, system_prompt: str,
                     messages: list[dict]):
        """Stream the iteration of the response. Default impl: yield the
        result of chat() in a single chunk (backends without native
        streaming, e.g. ClaudeCodeBackend). The native overrides
        (Anthropic/Gemini/Ollama in the subclasses) yield
        incremental fragments as they come.

        Returns : Iterator[str] -- chunks of the response, to concatenate
        caller-side to obtain the final text.
        """
        yield self.chat(system_prompt, messages)

    def cancel(self) -> None:
        """Interrupt an operation in progress. Default no-op.

        Called by the chat's watchdog when the backend does not respond.
        Backends that hold long-running blocking I/O (subprocess,
        socket without yield) MUST override to terminate their process
        explicitly -- otherwise the cooperative `_stop_requested` flag of the
        worker thread stays unread and the wait lasts until the native
        timeout (~2 min for subprocess.run by default).

        Backends that yield often (Anthropic, Gemini, Ollama
        streaming) do not need an override: the cooperative flag will be
        read at the next chunk (<1s in practice).
        """
        pass

    def repair_region(self, region: str, errors: str, language: str,
                      board_name: str) -> str:
        """Fix a SMALL region (a few lines around a compiler
        error) and return ONLY those corrected lines.

        Generic default: delegates to `repair_code`, treating the region as
        a mini-file. The local backends (Ollama) override with a
        lightweight prompt — on an SLM, fixing 5 flagged lines is trivial where
        rewriting the whole file fails."""
        code, _ = self.repair_code(region, errors, language, board_name)
        return code

    def _build_repair_region_system(self, board_name: str) -> str:
        return (
            f"You are fixing a SMALL region of {board_name} code that fails to "
            f"compile. You are given a few consecutive lines and the compiler "
            f"error.\n"
            f"Return ONLY those lines, corrected: fix exactly what the compiler "
            f"flags and nothing else. Keep the same code, the same identifiers, "
            f"the same indentation; usually the same number of lines.\n"
            f"Output RAW code only — no line numbers, no markdown fences, no "
            f"explanation, no extra line before or after."
        )

    def _build_repair_region_user(self, region: str, errors: str) -> str:
        return (
            f"Compiler error(s):\n{errors}\n\n"
            f"Code lines to fix:\n{region}\n\n"
            f"Return ONLY these lines, corrected."
        )

    def _build_explain_prompt(self, error: str, language: str) -> str:
        return (
            f"You are helping a student with embedded programming (Arduino).\n"
            f"The following is a technical error message from arduino-cli or avrdude.\n"
            f"Explain in {language} what the problem is and what the student should do, "
            f"in 1-2 sentences, in plain language for a beginner.\n"
            f"Reply ONLY with the explanation — no markdown, no code.\n\n"
            f"Error:\n{error}"
        )

    def _build_fix_system_prompt(self, board_name: str) -> str:
        return (
            f"You are an expert embedded systems programmer.\n"
            f"The following {board_name} code has a compilation error. Fix ONLY the error.\n"
            f"Return the COMPLETE corrected source file — every single line, "
            f"unchanged except for the minimal fix required.\n"
            f"Do NOT omit, summarize, truncate, or skip any part of the code.\n"
            f"Do NOT delete functions, loops, variables or comments; do NOT "
            f"rewrite or restructure working code; do NOT invent new functions, "
            f"variables, libraries or APIs that are not already present in the "
            f"code. Keep the program identical except for the failing part.\n"
            f"Reply with the full source code ONLY — no markdown fences, no explanations."
        )

    def _build_fix_user_message(self, code: str, error: str) -> str:
        return (
            f"Compilation error:\n{error}\n\n"
            f"Complete code to fix (return it entirely, with only the error corrected):\n{code}"
        )

    def _build_system_prompt(self, board_name: str, user_prompt: str = "") -> str:
        base = (
            f"You are an expert embedded systems programmer.\n"
            f"Generate clean, well-commented code for the {board_name}.\n"
            f"Reply with the source code ONLY — no markdown fences, no explanations.\n"
            f"The code must be complete and compile as-is."
        )
        return f"{base}\n\n{build_wiring_addendum(user_prompt)}"

    def _build_full_prompt(self, user_prompt: str, board_name: str,
                           rules_prompt: str | None = None) -> str:
        """Concatenate the system prompt and the user prompt (for the CLIs).

        `rules_prompt` (default = user_prompt) serves the motor gating: pass the
        RAW prompt so the RAG context (which may contain a
        motor lib example) does not trigger the motor block by mistake."""
        rules = rules_prompt if rules_prompt is not None else user_prompt
        return f"{self._build_system_prompt(board_name, rules)}\n\n{user_prompt}"

    def codegen_system_prompt(self, board_name: str, user_prompt: str = "") -> str:
        """Expose the code-generation system prompt (read-only).

        Used by the Studio's debug preview (`_PromptPreviewDialog`) to
        display the complete prompt actually sent to the model — otherwise
        the preview only shows the user message and hides the whole
        SLM optimization block (hardware rules / MOTOR / DISAMBIGUATION).
        """
        return self._build_system_prompt(board_name, user_prompt)

    def _build_explain_code_system(self, board_name: str, language: str) -> str:
        return (
            f"You are helping a student learn embedded programming on {board_name}.\n"
            f"Explain the given lines of code in {language}, suitable for a "
            f"beginner-to-intermediate learner. Focus on WHAT the lines do and WHY "
            f"(intent, hardware implications, pins, timings, pitfalls).\n"
            f"Format your answer in Markdown for readability:\n"
            f"- short intro sentence,\n"
            f"- then a bulleted list explaining each notable line or concept,\n"
            f"- use **bold** for key terms and `backticks` for identifiers, "
            f"functions, numeric values and pin names,\n"
            f"- optionally one short fenced code block if it clarifies.\n"
            f"Be concise. Reply in {language}."
        )

    def _build_explain_code_user(self, code: str, selection: str) -> str:
        if selection.strip():
            return (
                f"Full source for context:\n{code}\n\n"
                f"Lines to explain:\n{selection}"
            )
        return f"Code to explain:\n{code}"

    def _build_lint_code_system(self, board_name: str, language: str) -> str:
        return (
            f"You are an embedded programming reviewer for {board_name}.\n"
            f"Audit the student's code for common pitfalls and antipatterns "
            f"specific to embedded development, for example:\n"
            f"- blocking calls like `delay()` that prevent concurrent tasks,\n"
            f"- dynamic `String` usage on memory-constrained boards,\n"
            f"- missing `pinMode()` before `digitalWrite`/`digitalRead`,\n"
            f"- conflicts with built-in LED pin (13 on Uno, etc.),\n"
            f"- `int` used where `unsigned long` is required (e.g. `millis()`),\n"
            f"- busy loops, ISR-unsafe code, volatile missing on shared vars,\n"
            f"- serial.print in a tight loop flooding the UART,\n"
            f"- floating-point inefficiencies on AVR,\n"
            f"- any other embedded-specific smell.\n"
            f"Do NOT flag cosmetic style issues (spacing, naming) or generic "
            f"C++ advice unrelated to embedded.\n"
            f"Reply in {language}, formatted as Markdown:\n"
            f"- one bullet per issue,\n"
            f"- start each bullet with the affected **line numbers** in "
            f"bold,\n"
            f"- follow with a short description, then a `suggestion:` "
            f"with the fix,\n"
            f"- use `backticks` for identifiers, functions, pin names, "
            f"numeric values.\n"
            f"If the code is clean, reply with a single short sentence "
            f"stating that no antipattern was detected."
        )

    def _build_lint_code_user(self, code: str) -> str:
        # Number the lines to help the AI point precisely to the
        # relevant area in its bullets.
        numbered = "\n".join(
            f"{i+1:>4}: {line}" for i, line in enumerate(code.splitlines())
        )
        return f"Code to audit (line numbers prefixed):\n{numbered}"

    def _build_add_comments_system(self, board_name: str, language: str) -> str:
        return (
            f"You are enriching {board_name} code for a student learning "
            f"embedded programming.\n"
            f"Add pedagogical comments to the given code, written in {language}:\n"
            f"- a short header for each logical block (setup, loop, helper "
            f"functions) stating its purpose,\n"
            f"- inline notes for non-obvious lines: pin assignments, magic "
            f"constants, timings, hardware quirks, language constructs the "
            f"learner may not know,\n"
            f"- explain WHY (intent, gotchas), not just WHAT,\n"
            f"- prefer one short comment over a paragraph.\n"
            f"CRITICAL constraints:\n"
            f"- do NOT change the logic,\n"
            f"- do NOT rename or add or remove identifiers, variables, "
            f"functions or non-comment lines,\n"
            f"- only insert/replace comments,\n"
            f"- preserve indentation, blank lines and the order of code.\n"
            f"Reply with the COMPLETE source code only — no markdown fences, "
            f"no preamble, no postamble, no explanation."
        )

    def _build_add_comments_user(self, code: str) -> str:
        return f"Code to comment:\n{code}"

    def _build_repair_code_system(self, board_name: str, language: str,
                                  code: str = "", errors: str = "") -> str:
        # Two modes depending on `errors`:
        #  - non-empty -> AUTO compile repair (after fix_code failure):
        #    we fix what prevents building. (arduino_cli)
        #  - empty     -> manual "Analyse / Repair" tool: we AUDIT the
        #    embedded antipatterns AND apply the fixes, while
        #    PRESERVING the header that summarizes the program.
        if errors.strip():
            intro = (
                f"You are repairing {board_name} code that fails to compile. Apply "
                f"the SMALLEST changes that make it build:\n"
                f"- add missing includes, declarations, semicolons, braces,\n"
                f"- fix type mismatches and obvious typos in identifiers,\n"
                f"- correct the malformed statements the compiler flags.\n"
                f"- if an identifier is \"not declared in this scope\" because it is "
                f"SHARED between sections (e.g. computed in one place and used in "
                f"another), HOIST its declaration to GLOBAL scope (above setup()) "
                f"instead of re-declaring it locally — re-declaring would shadow it "
                f"and break the logic.\n"
                f"A diagnosis of the error may be appended to the errors — use it "
                f"to target the fix.\n"
            )
        else:
            intro = (
                f"You are REVIEWING {board_name} code for a student learning "
                f"embedded programming. The code already compiles. Identify "
                f"genuine embedded pitfalls/antipatterns and fix ONLY those, "
                f"each with the SMALLEST possible change:\n"
                f"- blocking `delay()` where it harms responsiveness,\n"
                f"- dynamic `String` on memory-constrained boards,\n"
                f"- missing `pinMode()` before `digitalWrite`/`digitalRead`,\n"
                f"- built-in LED pin conflicts (13 on Uno, etc.),\n"
                f"- `int` where `unsigned long` is required (`millis()`),\n"
                f"- ISR-unsafe code, `volatile` missing on shared vars,\n"
                f"- `Serial.print` flooding a tight loop.\n"
                f"If nothing genuinely needs fixing, return the code unchanged "
                f"with an empty [SUMMARY].\n"
            )
        # Rewrite the COMPLETE file (the format that every model, including the
        # local SLMs, can produce — the SEARCH/REPLACE format failed on them,
        # zero edits applied). The net is elsewhere: num_ctx (anti-truncation),
        # structural safeguard and revert (anti-gutting) on the _apply_repair_response
        # / arduino_cli side. A capable model can still emit
        # SEARCH/REPLACE blocks: they are applied with priority (cf _apply_repair_response).
        return (
            intro
            + f"STRICT rules — repair, do NOT rewrite (this is a student's "
            f"program, not a draft to regenerate):\n"
            f"- KEEP every working line and EVERY comment; do NOT delete, "
            f"summarise or rewrite code the compiler did not flag;\n"
            f"- do NOT remove functions, loops, variables or features;\n"
            f"- do NOT invent functions, variables, libraries or APIs not already "
            f"present; preserve existing NAMES (other code references them) — add "
            f"a new variable rather than rename an existing one;\n"
            f"- preserve structure, order, indentation and the header comment "
            f"block.\n\n"
            f"Reply EXACTLY in this format:\n"
            f"[SUMMARY]\n"
            f"- **Line <n>:** <short description of the fix, in {language}>\n"
            f"- **Line <n>:** <another fix, in {language}>\n"
            f"[/SUMMARY]\n"
            f"<the COMPLETE corrected source file>\n\n"
            f"The code after [/SUMMARY] MUST be the FULL file: every original line "
            f"present, only the failing parts changed, no markdown fences, no "
            f"preamble, no truncation. If nothing meaningful changed, still emit "
            f"an empty [SUMMARY] then the full code.\n"
            f"Summary bullets: start with `- `, BOLD the line label "
            f"(`**Ligne 3 :**` French, `**Line 3:**` English, `**Línea 3:**` "
            f"Spanish, `**Riga 3:**` Italian) referring to the CORRECTED code; "
            f"use `backticks` around identifiers, pins and literal values."
            # Hardware rules + DC motor pattern: same constraints as the
            # initial generation. Without this, the repair can break the
            # factorization `setMotor(pwmPin, in1Pin, in2Pin, speed)`
            # required by the detector (TODO 6).
            + f"\n\n{build_wiring_addendum(code)}"
        )

    def _build_repair_code_user(self, code: str, errors: str) -> str:
        if errors.strip():
            return (
                f"Compilation errors (a natural-language diagnosis may be "
                f"appended):\n{errors}\n\n"
                f"Complete code to fix (return it ENTIRELY, only the errors "
                f"corrected):\n{code}"
            )
        return (
            f"Code to review. Identify and fix genuine problems, returning the "
            f"COMPLETE code:\n{code}"
        )

    def _repair_from_response(self, code: str, raw: str) -> tuple[str, str]:
        """Apply a SEARCH/REPLACE repair response to the original `code`.
        Returns `(final_code, summary)` — code unchanged if nothing applies
        cleanly (cf. _apply_repair_response + safeguard)."""
        return _apply_repair_response(code, raw)

    # ── Conformance review (layer C — intent vs code) ──────────
    def _build_conformance_system(self, board_name: str, language: str) -> str:
        return (
            f"You are reviewing {board_name} code written for a student. The "
            f"code COMPILES. You are given the student's INTENT (what they "
            f"asked the program to do) and the code. Your job: check whether "
            f"the code actually DOES what the intent asks.\n"
            f"Report ONLY genuine BEHAVIORAL mismatches — logic that does not "
            f"achieve the intent (wrong condition, inverted logic, missing "
            f"step, wrong pin role, threshold/units off). IGNORE style, "
            f"comments and micro-optimizations. If OBSERVED SERIAL OUTPUT is "
            f"provided, use it as ground truth about what actually happens.\n"
            f"Fix each mismatch with the SMALLEST possible change, preferring "
            f"targeted SEARCH/REPLACE edits (do NOT rewrite the whole file, do "
            f"NOT rename existing identifiers, do NOT invent APIs). If the code "
            f"already fulfills the intent, return an EMPTY [SUMMARY] and no "
            f"edits.\n\n"
            f"Reply EXACTLY in this format:\n"
            f"[SUMMARY]\n"
            f"- **Line <n>:** <what behaviour was wrong and the fix, in "
            f"{language}>\n"
            f"[/SUMMARY]\n"
            f"then, for each fix, a block:\n"
            f"<<<<<<< SEARCH\n<exact original lines>\n=======\n"
            f"<corrected lines>\n>>>>>>> REPLACE\n"
            f"Emit ONLY the [SUMMARY] and the SEARCH/REPLACE blocks — no prose, "
            f"no markdown fences, no full file."
        )

    def _build_conformance_user(self, code: str, intent: str,
                                evidence: str = "") -> str:
        parts = [f"INTENT (what the program should do):\n{intent}\n"]
        if evidence and evidence.strip():
            parts.append(
                f"OBSERVED SERIAL OUTPUT (what actually happened at runtime):\n"
                f"{evidence}\n")
        parts.append(
            f"CODE (compiles; check it against the intent):\n{code}\n\n"
            f"List the behavioural mismatches and fix them with SEARCH/REPLACE "
            f"blocks. If it already matches, empty [SUMMARY] and no blocks.")
        return "\n".join(parts)

    def review_conformance(self, code: str, intent: str, board_name: str,
                           evidence: str = "",
                           language: str = "English") -> tuple[str, str]:
        """Layer C: does `code` fulfil `intent`? Returns (corrected_code,
        summary) — code unchanged if it already matches or nothing applies
        cleanly. Concrete for ALL backends: it routes through the unified
        `chat()` transport and reuses the SEARCH/REPLACE apply + guard, so no
        per-backend override is needed. Targeted edits keep the output small
        (safe with chat token limits)."""
        system = self._build_conformance_system(board_name, language)
        user = self._build_conformance_user(code, intent, evidence)
        raw = self.chat(system, [{"role": "user", "content": user}])
        return self._repair_from_response(code, raw)

    @staticmethod
    def _clean(text: str) -> str:
        """Strip any markdown fences the model may have added."""
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip(), flags=re.MULTILINE)
        text = re.sub(r"\n?```$", "", text.strip(), flags=re.MULTILINE)
        return text.strip()
