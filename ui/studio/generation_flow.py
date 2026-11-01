"""Génération IA : worker + aperçu de prompt (Prompt 4 du plan
PATHFINDER-2026-07-05, 1re tranche).

`GenerateWorker` (QThread) lance `backend.generate_code` en tâche de fond.
`build_codegen_preview` / `PromptPreviewDialog` servent le mode dév « aperçu
du prompt » (menu Aide) — fidèles au message réellement envoyé car ils
réutilisent `GenerateWorker.compose_user_prompt`.

⚠️ La relocalisation de l'ORCHESTRATION de génération (start/done/vérif v2/
recombine/finalize + convergence du mode débutant) reste dans studio_view
pour l'instant : c'est le sous-système le plus couplé et son chemin n'est
couvert ni par le smoke ni par les tests unitaires — à déplacer avec une
vérification UI. Cette 1re tranche extrait la partie autonome et testable."""
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ..i18n import lang_manager
from ..theme import primary_button_qss, secondary_button_qss, theme_manager


class PromptPreviewDialog(QDialog):
    """« Coulisses du prompt » (#42): shows what the app really sends, then
    lets the generation proceed.

    It used to be a dead end — a read-only view with a single "Fermer", and
    the two generation paths `return`ed before calling the backend. Seeing the
    prompt and generating were mutually exclusive: to do both you had to
    reopen the Help menu, untick, and start over.

    TWO PANES, and only one of them is editable. The system prompt is the
    app's own engineering (hardware rules, motor gating, comment directives);
    showing it is the pedagogical point, but editing it would mean rewriting
    the app's behaviour for one generation — and it would have to be threaded
    through every backend's `generate_code`. The user message is the user's
    own text, so it is editable.

    ⚠️ An edited message is used for THIS generation only. The Feature keeps
    the request the user typed, so a later ↻ regenerates from the project and
    will NOT reproduce the edit. That is stated in the journal rather than
    hidden — see `edited` and `Strings.backstage_edited`."""

    def __init__(self, title: str, system_prompt: str, user_message: str,
                 parent=None):
        super().__init__(parent)
        s = lang_manager.current
        self.setWindowTitle(title or s.backstage_title)
        self.resize(820, 640)
        self._original_user = user_message

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._lbl_system = QLabel(s.backstage_system)
        layout.addWidget(self._lbl_system)
        self._system_edit = self._make_editor(system_prompt, read_only=True)
        layout.addWidget(self._system_edit, 2)

        self._lbl_user = QLabel(s.backstage_user)
        layout.addWidget(self._lbl_user)
        self._user_edit = self._make_editor(user_message, read_only=False)
        layout.addWidget(self._user_edit, 3)

        self._lbl_count = QLabel()
        layout.addWidget(self._lbl_count)
        self._user_edit.textChanged.connect(self._refresh_count)
        self._refresh_count()

        row = QHBoxLayout()
        row.addStretch()
        self._btn_cancel = QPushButton(s.studio_cancel)
        self._btn_send = QPushButton(s.backstage_send)
        for b, qss in ((self._btn_cancel, secondary_button_qss),
                       (self._btn_send, primary_button_qss)):
            b.setFixedWidth(140)
            b.setFixedHeight(34)
            # Enter in the editable pane must not fire a button (same class of
            # bug as the zoom field of the wiring dialog, and as the search
            # combo of the swap modal).
            b.setAutoDefault(False)
            b.setDefault(False)
            b.setStyleSheet(qss(theme_manager.current))
            row.addWidget(b)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_send.clicked.connect(self.accept)
        layout.addLayout(row)

    @staticmethod
    def _make_editor(text: str, *, read_only: bool) -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setReadOnly(read_only)
        edit.setPlainText(text)
        font = edit.font()
        font.setFamily("Consolas")
        edit.setFont(font)
        edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        return edit

    def _refresh_count(self):
        self._lbl_count.setText(
            lang_manager.current.backstage_chars.format(
                n=len(self.user_message())))

    def user_message(self) -> str:
        """The message as it stands — edited or not."""
        return self._user_edit.toPlainText()

    def edited(self) -> bool:
        """True when the user changed the message. Drives the journal notice:
        an edit that nothing mentions would look like a bug the day ↻ produces
        something else."""
        return self.user_message() != self._original_user


class GenerateWorker(QThread):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    # Verbosity directives for Advanced mode. Index = slider value.
    # None: strictly forbids any comment ("bare" code).
    # Minimal: strict useful minimum (pins, magic constants).
    # Standard: equivalent to the historical behavior of Advanced mode.
    # Detailed: pedagogical explanations (what + why), same audience
    # as in beginner/intermediate — useful in a course context.
    _ADV_DIRECTIVES = {
        0: (
            "Target audience: experienced embedded developer. "
            "Do NOT add ANY comments in the code. No // comments, no /* */ "
            "blocks, no docstrings, no file headers. Produce bare executable "
            "code only. This is an explicit requirement."
        ),
        1: (
            "Target audience: experienced embedded developer. "
            "Keep comments to the bare minimum: annotate ONLY pin assignments, "
            "magic constants, and non-obvious timings or hardware choices. "
            "At most one very short inline note per such case. Do NOT add "
            "block headers, do NOT narrate what setup() or loop() do, do NOT "
            "explain language constructs."
        ),
        2: (
            "Target audience: experienced embedded developer. "
            "Keep comments informative and concise — one short header "
            "comment per logical block (setup, loop, helper function) "
            "stating its purpose, plus brief inline notes for magic "
            "constants, pin assignments, timings, or non-obvious choices. "
            "Prefer a single line over a paragraph. Do NOT narrate line "
            "by line, do NOT restate what the code does in plain English, "
            "do NOT add pedagogical explanations about what setup() or "
            "loop() are."
        ),
        3: (
            "Target audience: a learner discovering embedded programming. "
            "Use clear explanatory comments so the student understands "
            "what each block does and why. Cover the intent of setup() "
            "and loop(), explain non-trivial language constructs, and "
            "note potential gotchas (debouncing, timing, pull-ups, etc.). "
            "Prefer clarity over brevity."
        ),
    }

    def __init__(self, backend, prompt: str, board_name: str,
                 mode: str = "intermediate", comment_verbosity: int = 2,
                 rules_prompt: str | None = None,
                 user_message: str | None = None):
        super().__init__()
        self._backend    = backend
        self._prompt     = prompt
        self._board_name = board_name
        self._mode       = mode
        # 0..3 — ignored in non-advanced mode (pedagogical directive enforced).
        self._verbosity  = max(0, min(3, int(comment_verbosity)))
        # RAW prompt (without RAG augmentation) for the motor gating: otherwise a
        # motor lib example retrieved by the RAG triggers the motor block
        # wrongly. Default None -> generate_code falls back to the augmented prompt.
        self._rules_prompt = rules_prompt
        # ALREADY-COMPOSED message (#42, « Coulisses du prompt »): what the
        # user validated — possibly edited — in the dialog. Composing it again
        # would append the comment directives a second time, since they are
        # already in the text the user was shown. None -> normal path.
        self._user_message = user_message

    @property
    def backend(self):
        """Le backend que ce worker fait travailler.

        Expose pour l'ANNULATION (TODO #24) : `run()` est bloque dans
        `generate_code`, donc le seul moyen d'en sortir est de demander au
        backend de couper son E/S — `backend.cancel()`, le mecanisme que
        `AIBackend` documente et que le chat utilise deja."""
        return self._backend

    @staticmethod
    def compose_user_prompt(prompt: str, mode: str, verbosity: int) -> str:
        """Assemble the final user message = prompt + comment
        directives. Shared between `run()` (real send) and the Studio
        debug preview, so the preview stays faithful to what is sent.
        """
        verbosity = max(0, min(3, int(verbosity)))
        directives = [
            f"IMPORTANT: Write all code comments in {lang_manager.ai_lang_name()}."
        ]
        if mode == "advanced":
            directives.append(GenerateWorker._ADV_DIRECTIVES[verbosity])
        else:
            directives.append(
                "Target audience: a learner discovering embedded programming. "
                "Use clear explanatory comments so the student understands "
                "what each block does and why."
            )
        return f"{prompt}\n\n" + "\n".join(directives)

    def run(self):
        try:
            prompt = self._user_message
            if prompt is None:
                prompt = self.compose_user_prompt(
                    self._prompt, self._mode, self._verbosity
                )
            self.finished.emit(self._backend.generate_code(
                prompt, self._board_name, rules_prompt=self._rules_prompt))
        except Exception as e:
            self.error.emit(str(e))


def build_codegen_parts(backend, user_prompt: str, board_name: str,
                        mode: str, verbosity: int,
                        rules_prompt: str | None = None) -> tuple[str, str]:
    """(system prompt, composed user message) — the two halves of what is
    really sent, kept apart.

    `build_codegen_preview` glues them into one display string; the
    « Coulisses du prompt » dialog (#42) needs them separate, because only the
    second is editable. Both go through the SAME calls, so the dialog cannot
    drift from what the worker sends."""
    rules = rules_prompt if rules_prompt is not None else user_prompt
    return (backend.codegen_system_prompt(board_name, rules),
            GenerateWorker.compose_user_prompt(user_prompt, mode, verbosity))


def build_codegen_preview(backend, user_prompt: str, board_name: str,
                          mode: str, verbosity: int,
                          rules_prompt: str | None = None) -> str:
    """Debug preview text = full prompt actually sent to the
    model = system prompt + user message (with directives).

    Without this, the preview showed only the user message and hid
    the entire system prompt (hardware / MOTOR / DISAMBIGUATION rules =
    the SLM optimization), which gave the misleading impression of an
    almost empty prompt in beginner mode.

    `rules_prompt` (default = user_prompt) = RAW prompt for the motor gating,
    so the preview stays faithful to the real generation (which also gates on
    the raw prompt, not on the RAG-augmented blob).
    """
    system, user_msg = build_codegen_parts(
        backend, user_prompt, board_name, mode, verbosity, rules_prompt)
    return (
        "════════════════ SYSTEM PROMPT ════════════════\n"
        f"{system}\n\n"
        "════════════════ MESSAGE UTILISATEUR ════════════════\n"
        f"{user_msg}"
    )
