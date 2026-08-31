"""Claude Code backend — uses the `claude` CLI installed locally."""
import shutil
import subprocess
import sys
import threading
from .base import AIBackend
from ..subprocess_flags import NO_CONSOLE

# Generation can be long for complex requests; align with the other backends
# (Ollama / openai_compat use 300 s). The chat watchdog can cancel() earlier.
_CLI_TIMEOUT = 300  # seconds — `claude -p` generation timeout


class ClaudeCodeBackend(AIBackend):

    def __init__(self):
        # Reference to the running subprocess (to allow cancel()).
        # Protected by a lock because cancel() can be called from the
        # UI thread while _call_cli is running in the worker thread.
        self._process: subprocess.Popen | None = None
        self._process_lock = threading.Lock()

    @property
    def backend_id(self) -> str:
        return "claude_code"

    @property
    def name(self) -> str:
        return "Claude Code (CLI)"

    @property
    def description(self) -> str:
        return "Utilise le CLI claude installé sur votre machine. Aucune clé API requise."

    @property
    def requires_api_key(self) -> bool:
        return False

    def is_available(self) -> bool:
        return shutil.which("claude") is not None

    @property
    def context_window_hint(self) -> int:
        return 200_000

    def generate_code(self, user_prompt: str, board_name: str,
                      rules_prompt: str | None = None) -> str:
        """⚠️ SANS DELAI (TODO #24). Une generation simplement lente etait
        TUEE a 300 s et l'utilisateur perdait tout. La sortie n'est plus un
        couperet mais le bouton « Annuler », qui appelle `cancel()` — lequel
        existait deja ici, pour le chat."""
        full_prompt = self._build_full_prompt(user_prompt, board_name, rules_prompt)
        return self._clean(self._call_cli(full_prompt, timeout=None))

    def fix_code(self, code: str, error: str, board_name: str) -> str:
        prompt = (
            f"{self._build_fix_system_prompt(board_name)}\n\n"
            f"{self._build_fix_user_message(code, error)}"
        )
        return self._clean(self._call_cli(prompt))

    def explain_error(self, error: str, language: str) -> str:
        return self._clean(self._call_cli(self._build_explain_prompt(error, language)))

    def explain_code(self, code: str, selection: str, language: str,
                     board_name: str) -> str:
        prompt = (
            f"{self._build_explain_code_system(board_name, language)}\n\n"
            f"{self._build_explain_code_user(code, selection)}"
        )
        return self._call_cli(prompt).strip()

    def lint_code(self, code: str, language: str, board_name: str) -> str:
        prompt = (
            f"{self._build_lint_code_system(board_name, language)}\n\n"
            f"{self._build_lint_code_user(code)}"
        )
        return self._call_cli(prompt).strip()

    def add_comments(self, code: str, language: str, board_name: str) -> str:
        prompt = (
            f"{self._build_add_comments_system(board_name, language)}\n\n"
            f"{self._build_add_comments_user(code)}"
        )
        return self._clean(self._call_cli(prompt))

    def repair_code(self, code: str, errors: str, language: str,
                    board_name: str) -> tuple[str, str]:
        prompt = (
            f"{self._build_repair_code_system(board_name, language, code, errors)}\n\n"
            f"{self._build_repair_code_user(code, errors)}"
        )
        return self._repair_from_response(code, self._call_cli(prompt))

    def chat(self, system_prompt: str,
              messages: list[dict]) -> str:
        # claude --print is not conversational: we serialize
        # the history into a single prompt. Acceptable for short
        # multi-turn; for very long conversations, switch backend.
        parts: list[str] = []
        for m in messages:
            tag = "USER" if m["role"] == "user" else "ASSISTANT"
            parts.append(f"{tag}: {m['content']}")
        user_text = "\n\n".join(parts)
        full_prompt = f"{system_prompt}\n\n{user_text}"
        return self._call_cli(full_prompt).strip()

    def cancel(self) -> None:
        """Terminates the running claude CLI subprocess if one exists.

        Called by the chat watchdog (cf. chat_view.py) when the
        backend does not respond within the deadline. Without this kill, the caller
        waits for subprocess.run to reach its timeout (_CLI_TIMEOUT) -- minutes
        of freeze for nothing when the wifi is cut.
        """
        with self._process_lock:
            p = self._process
        if p is None:
            return
        try:
            p.terminate()
        except (ProcessLookupError, OSError):
            pass   # already terminated

    def _call_cli(self, prompt: str, timeout: int | None = _CLI_TIMEOUT) -> str:
        claude = shutil.which("claude")
        if claude is None:
            raise RuntimeError("CLI `claude` introuvable dans le PATH.")

        # On Windows, `claude` is often a .cmd/.bat — not executable
        # directly by CreateProcess, it must go through cmd.exe.
        # The prompt is passed via stdin to avoid any
        # shell escaping issue (newlines, quotes, special characters).
        if sys.platform == "win32" and claude.lower().endswith((".cmd", ".bat")):
            cmd = ["cmd", "/c", claude, "-p"]
        else:
            cmd = [claude, "-p"]

        # Popen + communicate instead of subprocess.run: we keep
        # a handle on the Popen to allow cancel() to stop it
        # from another thread (the UI worker when the user clicks stop
        # or the watchdog fires).
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=NO_CONSOLE,
        )
        with self._process_lock:
            self._process = proc
        try:
            try:
                # `timeout=None` : aucun delai (TODO #24). Reserve aux appels
                # que l'utilisateur peut ANNULER — aujourd'hui la seule
                # generation. La reparation, l'explication et le lint gardent
                # les 300 s : sans bouton d'annulation, retirer leur delai ne
                # ferait qu'ajouter un sous-processus que rien n'arreterait.
                stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                raise RuntimeError(
                    f"Claude Code n'a pas repondu dans le delai imparti "
                    f"({timeout}s)."
                )
        finally:
            with self._process_lock:
                self._process = None

        if proc.returncode != 0:
            # May be due to cancel() (explicit terminate) or a real
            # CLI error. In both cases, we surface a short message;
            # chat_view.py will translate it into a user-readable message.
            err = (stderr or "").strip()
            if not err:
                err = "Claude Code s'est arrete sans message d'erreur."
            raise RuntimeError(err)
        return stdout
