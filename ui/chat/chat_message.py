"""Message bubble widget (user or assistant) for the chat panel.

Layout:
- User: bubble aligned to the right, accent color background, plain text (no
  markdown -- the user does not write in markdown).
- Assistant: NO bubble, text across the full width of the panel, rendered
  as markdown via QTextBrowser (with code blocks colored in inline CSS).
  More readable for long responses than a narrow, cropped bubble.
- Assistant errors: red bubble kept (important visual signal).

Markdown rendering uses the `markdown` package (PyPI). If not available,
plain text fallback.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextOption
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
    QWidget, QSizePolicy, QTextEdit,
)

from ..theme import DARK, LIGHT
from ..fonts import MONO_CSS

try:
    import markdown as _markdown
    _HAS_MARKDOWN = True
except ImportError:
    _HAS_MARKDOWN = False


_USER_BG = "#3b82f6"
_USER_FG = "#ffffff"
_ASSISTANT_BG_LIGHT = "#f3f4f6"
_ASSISTANT_BG_DARK = "#1f2937"
_ASSISTANT_FG_LIGHT = "#1f2937"
_ASSISTANT_FG_DARK = "#f3f4f6"
_ERROR_BG = "#fee2e2"
_ERROR_FG = "#7f1d1d"


def _highlight_arduino_code(code: str) -> str:
    """Arduino/C++ syntax highlighting -> HTML with inline styles.

    Reuses the regexes + the `_DARK` palette from `ui/code_editor.py` for
    visual consistency with the int/advanced mode editor (same colors
    on the same tokens). We always use _DARK here because the chat code
    block has a fixed dark background (`#0d1117`), independent of the app theme.

    Algorithm: for each character, its color is computed via successive
    passes (comments first, then preprocessor / types / keywords
    / builtins / numbers / function calls, finally strings / line comments
    -- same order as ArduinoHighlighter._build_rules). The last pass
    that writes wins, EXCEPT for block comments which are marked first
    in `comment_mask` and stay untouchable.

    Returns: HTML with `<span style="color:...">` per token. If
    `code_editor` cannot be imported, simple escape fallback.
    """
    try:
        from ..code_editor import (
            _DARK, _KW, _TYPES, _BUILTINS, _PREPROC, _NUMBER, _FUNC,
            _STRING, _CHAR, _CMT_LINE, _CMT_START, _CMT_END,
        )
    except Exception:
        return (code.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))

    import re as _re
    n = len(code)
    color_map: list[str | None] = [None] * n
    comment_color = _DARK["comment"]
    comment_mask: list[bool] = [False] * n

    # 1. Block comments (multi-line, max priority).
    block_re = _re.compile(_CMT_START + r'.*?' + _CMT_END, _re.DOTALL)
    for m in block_re.finditer(code):
        for i in range(m.start(), m.end()):
            comment_mask[i] = True
            color_map[i] = comment_color
    # Block comment opened but not closed (code being edited).
    for m in _re.finditer(_CMT_START, code):
        if comment_mask[m.start()]:
            continue
        end_m = _re.search(_CMT_END, code[m.end():])
        end_pos = m.end() + end_m.end() if end_m else n
        for i in range(m.start(), end_pos):
            comment_mask[i] = True
            color_map[i] = comment_color

    def _apply(pattern: str, color: str, group: int = 0) -> None:
        for m in _re.finditer(pattern, code, _re.MULTILINE):
            start = m.start(group)
            end = m.end(group)
            for i in range(start, end):
                if comment_mask[i]:
                    continue
                color_map[i] = color

    # 2. Order identical to ArduinoHighlighter._build_rules: rules
    # applied later overwrite the previous ones (strings overwrite
    # keywords contained inside strings, etc.).
    _apply(_PREPROC, _DARK["preprocessor"])
    _apply(_TYPES, _DARK["type"])
    _apply(_KW, _DARK["keyword"])
    _apply(_BUILTINS, _DARK["builtin"])
    _apply(_NUMBER, _DARK["number"])
    _apply(_FUNC, _DARK["function"], group=1)
    _apply(_STRING, _DARK["string"])
    _apply(_CHAR, _DARK["string"])
    _apply(_CMT_LINE, _DARK["comment"])

    # 3. Emit HTML by merging runs of the same color.
    out: list[str] = []
    i = 0
    while i < n:
        color = color_map[i]
        j = i + 1
        while j < n and color_map[j] == color:
            j += 1
        run = code[i:j]
        esc = (run.replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;"))
        if color is None:
            out.append(esc)
        else:
            out.append(f'<span style="color:{color}">{esc}</span>')
        i = j
    return "".join(out)


# Common LaTeX symbols -> Unicode. Long tokens before their prefixes
# (\leq before \le) to avoid a partial replacement.
_LATEX_SYMBOLS = {
    r"\times": "×", r"\cdot": "·", r"\div": "÷",
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥",
    r"\neq": "≠", r"\approx": "≈", r"\pm": "±",
    r"\Omega": "Ω", r"\omega": "ω", r"\mu": "µ",
    r"\alpha": "α", r"\beta": "β", r"\Delta": "Δ", r"\pi": "π",
    r"\rightarrow": "→", r"\Rightarrow": "⇒", r"\to": "→",
    r"\ldots": "…", r"\dots": "…", r"\infty": "∞",
}


def _delatex(text: str) -> str:
    r"""Convert leftover LaTeX/MathJax into readable text.

    Small models sometimes ignore the "no LaTeX" instruction and emit
    formulas like ``$$R = \frac{V}{I}$$`` that QTextBrowser displays
    raw. We strip the delimiters, expand \frac / \text / subscripts and
    the common symbols. Targets only LaTeX macros (\frac, \text,
    delimiters, _{}/^{}) that do not appear in Arduino code: bare
    `_`/`^` and C escapes (\n, \t) are left intact."""
    if "\\" not in text and "$" not in text:
        return text  # nothing LaTeX-ish -> short-circuit
    # 1. Math delimiters
    text = re.sub(r"\$\$(.+?)\$\$", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"\\\[(.+?)\\\]", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"\\\((.+?)\\\)", r"\1", text, flags=re.DOTALL)
    # $...$ inline only if the content is math-ish (\ { } _ ^)
    text = re.sub(r"\$([^$\n]*?[\\{}_^][^$\n]*?)\$", r"\1", text)
    # 2. \text{x}, \mathrm{x}... -> x  (remove the braces first)
    text = re.sub(
        r"\\(?:text|mathrm|mathit|mathbf|operatorname)\s*\{([^{}]*)\}",
        r"\1", text)
    # 3. Subscripts/superscripts: _{x} -> _x, ^{x} -> ^x (before \frac to
    #    free the nested braces of the numerator/denominator)
    text = re.sub(r"_\{([^{}]*)\}", r"_\1", text)
    text = re.sub(r"\^\{([^{}]*)\}", r"^\1", text)
    # 4. \frac{a}{b} -> (a) / (b) (several passes for 1 nesting level)
    for _ in range(3):
        new = re.sub(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
                     r"(\1) / (\2)", text)
        if new == text:
            break
        text = new
    # 5. Symbols
    for tok, sym in _LATEX_SYMBOLS.items():
        text = text.replace(tok, sym)
    # 6. Leftover LaTeX spacing
    text = re.sub(r"\\(?:quad|qquad)", "  ", text)
    text = re.sub(r"\\[,;:!> ]", " ", text)
    return text


def _md_to_html(text: str) -> str:
    """Convert markdown to HTML for QTextBrowser. Plain text fallback
    if the `markdown` package is not installed OR if markdown
    raises an exception while rendering (defensive: we prefer raw text
    rather than a crash of the bubble)."""
    text = _delatex(text)
    plain_fallback = (
        f"<p>"
        + text.replace("&", "&amp;")
              .replace("<", "&lt;")
              .replace(">", "&gt;")
              .replace("\n", "<br>")
        + f"</p>"
    )
    if not _HAS_MARKDOWN:
        return plain_fallback
    try:
        html = _markdown.markdown(
            text, extensions=["fenced_code", "tables"],
        )
    except Exception as e:
        print(f"[chat] markdown render failed, fallback to plain: {e}",
              flush=True)
        return plain_fallback
    # QTextBrowser (Qt 6) does NOT render `background-color` on the
    # `<pre>` or `<code>` tags (inline OR via setDefaultStyleSheet:
    # the widget setStyleSheet overrides the color, and the bg of <pre> is
    # simply not drawn by the richtext engine).
    # Proven workaround: wrap each fenced code block in a
    # `<table>` -- table cells (`<td>`) fully support
    # `background-color` in Qt richtext, this is the
    # classic "colored box" method via QTextBrowser.
    import re as _re
    def _wrap_code_block(match: "_re.Match") -> str:
        # The content may be <pre><code class="language-cpp">...
        # or simply <pre>... depending on what markdown generates.
        inner = match.group(1)
        # Remove a possible <code...>...</code> that already wraps the
        # text (markdown.fenced_code generates <pre><code>...</code></pre>).
        inner = _re.sub(r'^\s*<code[^>]*>', '', inner)
        inner = _re.sub(r'</code>\s*$', '', inner)
        # markdown.fenced_code has already escaped the code (&lt; &amp; etc).
        # We reverse the escape to recover the raw code, apply
        # syntax highlighting (which re-escapes cleanly per token),
        # and inject the colored HTML into the table-wrap.
        raw_code = (inner.replace('&lt;', '<')
                          .replace('&gt;', '>')
                          .replace('&amp;', '&'))
        highlighted = _highlight_arduino_code(raw_code)
        # Bg `#0d1117` (even darker than the dark bubble `#1f2937`)
        # so the block stays visually distinct in the dark theme.
        # In the light theme (bubble `#f3f4f6`), it is obviously a strong
        # contrast. GitHub-style IDE convention.
        return (
            '<table cellpadding="8" cellspacing="0" width="100%" '
            'style="background-color:#0d1117;">'
            '<tr><td>'
            '<span style="color:#e5e7eb; '
            f'font-family:{MONO_CSS}; '
            'white-space:pre-wrap;">'
            + highlighted +
            '</span>'
            '</td></tr></table>'
        )
    html = _re.sub(
        r'<pre>(.*?)</pre>',
        _wrap_code_block,
        html,
        flags=_re.DOTALL,
    )
    # Inline code (`var`): a span with monospace style + dark bg. The bg
    # works on span (though it looks block-level, an acceptable fix
    # for MVP).
    html = html.replace(
        "<code>",
        '<code style="background-color:#0d1117; color:#e5e7eb; '
        f"font-family:{MONO_CSS};\">",
    )
    return html


class ChatMessage(QFrame):
    """A message bubble in the chat conversation."""

    def __init__(self, role: str, text: str,
                 *, is_error: bool = False,
                 dark_theme: bool = False,
                 action: "tuple[str, Callable[[], None]] | "
                         "list[tuple[str, Callable[[], None]]] | None" = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.role = role
        self.text = text
        self.is_error = is_error
        self._dark = dark_theme
        self._browser: QTextBrowser | None = None
        # Re-entrancy guard: _adjust_browser_height sets the text width,
        # which can re-emit documentSizeChanged (-> recursion).
        self._adjusting = False
        # Optional (label, on_click) -> renders a button under the text of
        # the bubble. Used for "Ouvrir dans Studio" on the
        # GENERATION_REDIRECT bubbles. None = no button.
        #
        # A LIST of such pairs is also accepted: the redirect bubble carries a
        # second, « répondre quand même » button, so a misread intent stays
        # repairable in one click (QA D2, 2026-08-08).
        self._actions: list = (
            [] if action is None
            else [action] if isinstance(action, tuple)
            else list(action)
        )
        self._build()

    def _build(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(0)

        # Direction B colors (spec §3) — theme-aware via the _dark flag.
        c = DARK if self._dark else LIGHT
        if self.is_error:
            bg = "#4a1010" if self._dark else "#fde8e8"   # KO background (spec §3 badges)
            fg = c.signal_error
            border_col = c.signal_error
        elif self.role == "user":
            bg, fg, border_col = c.surface, c.text_primary, c.border
        else:
            bg, fg, border_col = c.surface, c.text_primary, c.border

        # "No bubble" mode for normal assistant responses: the
        # text flows across the full width of the panel, more readable and avoids
        # the right crop. The bubble stays for user (right-aligned accent)
        # and for errors (red background = important signal).
        no_bubble = (self.role == "assistant" and not self.is_error)

        # Internal container (receives text + optional action button).
        if no_bubble:
            # Assistant response (spec §3): no background, phosphor left bar.
            bubble = QFrame()
            bubble.setObjectName("ChatAssistant")
            bubble.setStyleSheet(
                f"#ChatAssistant {{ background: transparent; "
                f"border-left: 2px solid {c.signal_ok}; "
                f"padding: 2px 0 2px 12px; }}"
            )
            bubble.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred,
            )
            container_lay = QVBoxLayout(bubble)
            container_lay.setContentsMargins(0, 0, 0, 0)
            container_lay.setSpacing(2)
        else:
            # User / error bubble (spec §3): background + border, radius 6.
            bubble = QFrame()
            bubble.setObjectName("ChatBubble")
            bubble.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred,
            )
            bubble.setStyleSheet(
                f"#ChatBubble {{ background:{bg}; "
                f"border:1px solid {border_col}; border-radius:6px; "
                f"padding:4px 8px; }}"
            )
            container_lay = QVBoxLayout(bubble)
            container_lay.setContentsMargins(8, 4, 8, 4)

        self._container_lay = container_lay

        # Content: plain QLabel for user, QTextBrowser markdown otherwise.
        if self.role == "user":
            lbl = QLabel(self.text)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            lbl.setStyleSheet(f"color: {fg};")
            container_lay.addWidget(lbl)
        else:
            # Markdown rendered via QTextBrowser. In no-bubble: transparent
            # background + Expanding sizePolicy to use the full
            # available width. In bubble mode (error): colored background.
            browser_bg = "transparent" if no_bubble else bg
            self._browser = QTextBrowser()
            # Do not capture file drops: let the event bubble up
            # to the ChatView (dropping a document anywhere in the chat).
            self._browser.setAcceptDrops(False)
            self._browser.setLineWrapMode(
                QTextEdit.LineWrapMode.WidgetWidth,
            )
            self._browser.setWordWrapMode(
                QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere,
            )
            # Code blocks always in dark theme (IDE convention):
            # guaranteed contrast in light + dark themes.
            self._browser.document().setDefaultStyleSheet(
                f"pre {{ background-color: {DARK.code_bg}; "
                f"      color: #e5e7eb; "
                f"      padding: 8px; "
                f"      border-radius: 4px; "
                f"      font-family: {MONO_CSS}; }} "
                f"code {{ background-color: {DARK.code_bg}; "
                f"       color: #e5e7eb; "
                f"       font-family: {MONO_CSS}; "
                f"       padding: 1px 4px; "
                f"       border-radius: 2px; }}"
            )
            self._browser.setOpenExternalLinks(True)
            self._browser.setHtml(_md_to_html(self.text))
            self._browser.setStyleSheet(
                f"QTextBrowser {{ background:{browser_bg}; "
                f"color:{fg}; border:none; }}"
            )
            self._browser.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self._browser.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            # Grow-to-fit: QTextDocument lays out tables (our fenced code
            # blocks are <table>-wrapped, cf _md_to_html) LAZILY -- the
            # document's true height only settles AFTER setHtml, often with
            # no width change to re-trigger resizeEvent. Without this, the
            # height computed at creation stays stale and too small -> the
            # bubble crops the response and scrolls internally. Recomputing
            # on documentSizeChanged makes the bubble always expand to its
            # full content (the outer conversation scroll handles overflow).
            self._browser.document().documentLayout().documentSizeChanged.connect(
                self._on_doc_size_changed
            )
            if no_bubble:
                self._browser.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
            # Initial height (recomputed in resizeEvent when the
            # real layout width is known).
            self._adjust_browser_height()
            container_lay.addWidget(self._browser)

        # Optional action button (e.g. "Ouvrir dans Studio").
        for label, on_click in self._actions:
            self._add_action_button(label, on_click)

        # Final assembly.
        if no_bubble:
            outer.addWidget(bubble, stretch=1)
        else:
            if self.role == "user":
                outer.addStretch(1)
            outer.addWidget(bubble, alignment=(
                Qt.AlignmentFlag.AlignRight if self.role == "user"
                else Qt.AlignmentFlag.AlignLeft
            ))
            if self.role != "user":
                outer.addStretch(1)

    def _add_action_button(self, label: str, on_click) -> None:
        """Add an action button under the bubble text."""
        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        c = DARK if self._dark else LIGHT
        btn.setStyleSheet(
            f"QPushButton {{ background:{c.btn_primary_bg}; color:{c.btn_primary_text}; "
            f"border:none; border-radius:4px; padding:4px 10px; "
            f"font-size:11px; }} "
            f"QPushButton:hover {{ background:{c.btn_primary_hover}; }}"
        )
        btn.clicked.connect(on_click)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.addWidget(btn)
        btn_row.addStretch(1)
        self._container_lay.addLayout(btn_row)

    def set_action(self, label: str, on_click) -> None:
        """Add an action button AFTER the bubble has been built.
        (Utility: the repair redirection now goes through a
        dedicated bubble via _append_temp_bubble, like the generation redirection.)"""
        self._add_action_button(label, on_click)

    def _on_doc_size_changed(self, _size) -> None:
        """The QTextDocument finished (re)laying out its content -- notably
        the lazy table layout of code blocks. Recompute the bubble height so
        it grows to the full content instead of cropping it. Guarded against
        re-entrancy (setTextWidth inside _adjust_browser_height can itself
        emit documentSizeChanged; it converges in one extra pass)."""
        self._adjust_browser_height()

    def _adjust_browser_height(self) -> None:
        """Adjust the QTextBrowser height to the content, based on the
        current width. Idempotent — called at creation, on each
        resize, after each update_text() during streaming, and whenever the
        document layout settles (documentSizeChanged)."""
        if self._browser is None:
            return
        if self._adjusting:
            return
        self._adjusting = True
        try:
            self._do_adjust_browser_height()
        finally:
            self._adjusting = False

    def _do_adjust_browser_height(self) -> None:
        # Target width = real browser width at the time of the call,
        # with a 280px fallback as long as the layout has not been computed
        # (first creation). The resizeEvent will catch up.
        w = self._browser.width() - 4
        if w < 40:
            w = 280
        self._browser.document().setTextWidth(w)
        h = int(self._browser.document().size().height()) + 8
        self._browser.setFixedHeight(max(40, h))

    def resizeEvent(self, event):
        """Recompute the height when the width changes (the content may
        reflow and require more or fewer lines)."""
        super().resizeEvent(event)
        self._adjust_browser_height()

    def update_text(self, new_text: str) -> None:
        """Re-render the bubble with new text (streaming case).
        For role=user, no-op (user bubbles are static QLabels
        and their content is never updated dynamically)."""
        self.text = new_text
        if self._browser is None:
            return
        self._browser.setHtml(_md_to_html(new_text))
        self._adjust_browser_height()
