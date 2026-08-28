"""
Arduino code editor with:
  - Line numbers (gutter)
  - Arduino/C++ syntax highlighting (ArduinoHighlighter)
  - Reactive light/dark theme
"""
import re
from PyQt6.QtCore import Qt, QRect, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPalette, QTextCursor, QTextFormat, QTextCharFormat,
    QSyntaxHighlighter, QTextBlockUserData, QPixmap, QIcon,
)
from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit

from .theme import theme_manager, ColorScheme, context_menu_qss, selection_bg
from .fonts import mono_font


# ── Syntax color palettes ──────────────────────────────────────────

# GitHub Dark Dimmed / GitHub Light palette (spec §4).
_DARK = {
    "keyword":     "#ff7b72",   # red    (void, if, for…)
    "type":        "#ffa657",   # orange (int, classes: OneWire, DHT…)
    "builtin":     "#ffa657",   # orange (Serial, HIGH, LOW…: same as types)
    "preprocessor":"#ff7b72",   # red    (#include, #define… = keywords, §4)
    "string":      "#a5d6ff",   # light blue (literals + <includes>)
    "comment":     "#6e7681",   # gray   (// and /* */)
    "number":      "#79c0ff",   # blue
    "function":    "#d2a8ff",   # purple (function calls)
}

_LIGHT = {
    "keyword":     "#cf222e",
    "type":        "#953800",
    "builtin":     "#953800",
    "preprocessor":"#cf222e",
    "string":      "#0a3069",
    "comment":     "#6e7781",
    "number":      "#0550ae",
    "function":    "#8250df",
}

# C/C++ keywords
_KW = r"\b(if|else|for|while|do|switch|case|break|continue|return|new|delete|"  \
      r"class|struct|public|private|protected|virtual|override|"                 \
      r"void|true|false|NULL|nullptr|sizeof|typedef|enum|namespace|using|"       \
      r"static|const|volatile|extern|inline|template|typename)\b"

# Arduino/C++ base types
_TYPES = r"\b(int|long|short|char|byte|float|double|bool|boolean|"  \
         r"uint8_t|uint16_t|uint32_t|int8_t|int16_t|int32_t|"       \
         r"String|Array|word|unsigned|signed)\b"

# Arduino functions and constants
_BUILTINS = r"\b(setup|loop|"                                                     \
            r"pinMode|digitalWrite|digitalRead|analogWrite|analogRead|"           \
            r"delay|millis|micros|delayMicroseconds|"                             \
            r"Serial|Serial1|Wire|SPI|"                                           \
            r"begin|end|print|println|write|read|available|flush|"                \
            r"attachInterrupt|detachInterrupt|"                                   \
            r"HIGH|LOW|INPUT|OUTPUT|INPUT_PULLUP|"                                \
            r"LED_BUILTIN|A0|A1|A2|A3|A4|A5|"                                    \
            r"map|constrain|min|max|abs|pow|sqrt|random|randomSeed|"              \
            r"tone|noTone|pulseIn|shiftIn|shiftOut)\b"

# Preprocessor directives
_PREPROC = r"^\s*#\s*(include|define|undef|ifdef|ifndef|if|elif|else|endif|pragma|error)"

# Number (integer, hex, float)
_NUMBER  = r"\b(0x[0-9a-fA-F]+|\d+\.?\d*([eE][+-]?\d+)?[uUlLfF]?)\b"

# Function call: identifier followed by (
_FUNC    = r"\b([A-Za-z_]\w*)\s*(?=\()"

# String literal (double or single quote), with basic escape handling
_STRING  = r'"([^"\\]|\\.)*"'
_CHAR    = r"'([^'\\]|\\.)*'"

# Comments
_CMT_LINE  = r"//[^\n]*"
_CMT_START = r"/\*"
_CMT_END   = r"\*/"


# Detect the function under the cursor (right-click) for the contextual
# chat bridge. Hand-rolled pattern (no AST): C++ signature +
# brace counting.
_FUNC_SIGNATURE_RE = re.compile(
    r'^[ \t]*(?:(?:static|inline|virtual|extern|const|volatile)\s+)*'
    r'[\w:<>\*&\s]+?\s+(\w+)\s*\([^)]*\)\s*\{',
    re.MULTILINE,
)

# C++ keywords that the signature regex may match as a "name" if
# they are used at top-level (typical case: code being edited,
# `if (...)`{` instead of being inside setup()). We skip them so we don't
# offer "Ask the assistant about the function if".
_CPP_CONTROL_KEYWORDS = {
    "if", "while", "for", "switch", "do", "else", "return",
    "case", "default", "try", "catch", "break", "continue",
    "sizeof", "typedef", "using", "namespace",
}


def _find_function_at_cursor(text: str, char_pos: int) -> "tuple[str, str] | None":
    """Find the function whose body contains `char_pos` in `text`.
    Returns (function_name, full_function_text) or None if no
    function contains this position (file comment, includes,
    space between functions, global variables, etc.).

    Hand-rolled pattern (no AST): find C++ signatures via
    regex then match braces to delimit the body. Used by the
    contextual chat bridge (F2 step 4) to preload the chat with
    a function's explanation when the student right-clicks on it."""
    for m in _FUNC_SIGNATURE_RE.finditer(text):
        name = m.group(1)
        if name in _CPP_CONTROL_KEYWORDS:
            continue   # `if (...) {` etc. are not functions
        start_brace = m.end() - 1   # position of the '{'
        depth = 1
        i = start_brace + 1
        while i < len(text) and depth > 0:
            ch = text[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
            i += 1
        if depth != 0:
            continue   # signature without closed body: skip
        end_pos = i   # after the final '}'
        if m.start() <= char_pos <= end_pos:
            return (name, text[m.start():end_pos])
    return None


def _fmt(hex_color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(hex_color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


# ── Highlighter ───────────────────────────────────────────────────────────────

class ArduinoHighlighter(QSyntaxHighlighter):
    """Arduino/C++ syntax highlighting — theme-aware."""

    _IN_BLOCK_COMMENT = 1

    def __init__(self, document):
        super().__init__(document)
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []
        self._fmt_comment = QTextCharFormat()
        self._build_rules(theme_manager.is_dark)
        theme_manager.changed.connect(self._on_theme)

    def _on_theme(self, _c: ColorScheme):
        self._build_rules(theme_manager.is_dark)
        self.rehighlight()

    def _build_rules(self, dark: bool):
        p = _DARK if dark else _LIGHT
        self._rules = []

        # Order matters: more specific rules first
        for pattern, key, bold in [
            (_PREPROC,  "preprocessor", False),
            (_TYPES,    "type",         True),
            (_KW,       "keyword",      True),
            (_BUILTINS, "builtin",      False),
            (_NUMBER,   "number",       False),
            (_FUNC,     "function",     False),
            (_STRING,   "string",       False),
            (_CHAR,     "string",       False),
            (_CMT_LINE, "comment",      False),
        ]:
            self._rules.append((
                re.compile(pattern, re.MULTILINE),
                _fmt(p[key], bold=bold, italic=(key == "comment")),
            ))

        self._fmt_comment = _fmt(p["comment"], italic=True)

    def highlightBlock(self, text: str):
        # ── Multi-line comments (block state) ───────────
        start_expr = re.compile(_CMT_START)
        end_expr   = re.compile(_CMT_END)

        if self.previousBlockState() == self._IN_BLOCK_COMMENT:
            # We are already inside a comment block
            m = end_expr.search(text)
            if m:
                self.setFormat(0, m.end(), self._fmt_comment)
                self.setCurrentBlockState(0)
                offset = m.end()
            else:
                self.setFormat(0, len(text), self._fmt_comment)
                self.setCurrentBlockState(self._IN_BLOCK_COMMENT)
                return
        else:
            self.setCurrentBlockState(0)
            offset = 0

        # Search for comment block starts in the rest of the line
        while True:
            m_start = start_expr.search(text, offset)
            if not m_start:
                break
            m_end = end_expr.search(text, m_start.end())
            if m_end:
                length = m_end.end() - m_start.start()
                self.setFormat(m_start.start(), length, self._fmt_comment)
                offset = m_end.end()
            else:
                self.setFormat(m_start.start(), len(text) - m_start.start(), self._fmt_comment)
                self.setCurrentBlockState(self._IN_BLOCK_COMMENT)
                return

        # ── Single-line rules ──────────────────────────────────
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                # For function calls, only color group 1
                g = 1 if pattern.groups else 0
                start = m.start(g)
                length = m.end(g) - start
                # Do not overwrite an already-colored comment
                existing = self.format(start)
                if existing.foreground().color() == self._fmt_comment.foreground().color():
                    continue
                self.setFormat(start, length, fmt)


# ── Gutter (line numbers) ─────────────────────────────────────────────────

class _LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_line_numbers(event)


# ── Main editor ─────────────────────────────────────────────────────────

class _OwnerBlockData(QTextBlockUserData):
    """Propriétaire d'une ligne (feature_id ou None) — ancre de bloc pour le
    surlignage par fonctionnalité (#29). Qt déplace le userData AVEC le bloc
    (édition en place, insertions/suppressions ailleurs) ; seuls les blocs
    NOUVELLEMENT créés naissent sans data -> héritage via contentsChange."""
    def __init__(self, owner: "str | None"):
        super().__init__()
        self.owner = owner


class CodeEditor(QPlainTextEdit):
    # Signal emitted when the student right-clicks on a function and
    # chooses "Ask the assistant" in the context menu
    # (chat bridge F2 step 4). Payload: (function_name, function_body).
    help_with_function_requested = pyqtSignal(str, str)

    # Fix 3 variant: the student has an active selection and chooses
    # "Ask the assistant". The scope is limited to the selected
    # lines (useful to explain a 3-line block inside a
    # 50-line loop()). Payload: (selected_text, function_name_or_empty).
    # `function_name` (may be empty) provides the context of the enclosing
    # function to help the LLM, but the focus is on the selection.
    help_with_selection_requested = pyqtSignal(str, str)

    # Emitted when the user ACTUALLY tries to modify the text while
    # the editor is read-only (intermediate mode): typing a
    # character, Enter, Backspace/Delete, paste/cut. Navigation,
    # selection and copy do NOT emit this signal (we must be able to copy
    # lines without triggering the popup).
    edit_attempted = pyqtSignal()

    # Right-click « Assign to a feature » (#31 failsafe): the user picked a
    # target for the selected/clicked line(s). Payload: (start_line, end_line,
    # feature_id). The editor is feature-agnostic — the panel/studio provides
    # the choices via `set_feature_provider` and applies the result.
    assign_lines_to_feature = pyqtSignal(int, int, str)

    _AUTO_PAIRS = {"(": ")", "{": "}", "[": "]"}
    _AUTO_CLOSERS = frozenset(")}]")
    # Un niveau d'indentation = 1 tabulation, aligné sur code_format.INDENT
    # (décision D4 : le code généré est réindenté en tabs). L'auto-indent de
    # l'éditeur produit donc le même caractère que la réindentation.
    _INDENT = "\t"

    def __init__(self, parent=None):
        super().__init__(parent)
        # Provider for the « Assign to a feature » submenu: a zero-arg callable
        # returning [(feature_id, label, color_hex), …] or [] (no submenu).
        self._feature_provider = None
        # "Locked" mode (intermediate): the editor stays editable IN APPEARANCE
        # (cursor visible, selection/copy possible) but any modification
        # attempt is blocked and opens the popup -> edit_attempted. We avoid
        # setReadOnly() which would hide the cursor.
        self._edit_locked = False
        self._line_area = _LineNumberArea(self)
        self._highlighter = ArduinoHighlighter(self.document())

        # Monospace font — 10 pt (spec §6): JetBrains Mono → Cascadia → Consolas.
        self.setFont(mono_font(10))
        self.setTabStopDistance(
            self.fontMetrics().horizontalAdvance(" ") * 2
        )

        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._rebuild_extra_selections)
        # Also rebuild when the selection changes (to hide the current-line
        # highlight as soon as a green selection is active).
        self.selectionChanged.connect(self._rebuild_extra_selections)

        # Surlignage par fonctionnalité (#29) : couleurs actives (feature_id
        # -> QColor) + héritage du propriétaire pour les blocs créés à la main.
        self._feature_highlight_colors: dict[str, "QColor"] = {}
        self.document().contentsChange.connect(self._inherit_new_block_owners)

        self._update_line_area_width(0)
        self._rebuild_extra_selections()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)

    # ── Line numbers ──────────────────────────────────────

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 6 + self.fontMetrics().horizontalAdvance("9") * (digits + 1)

    def _update_line_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_area(self, rect: QRect, dy: int):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(QRect(cr.left(), cr.top(),
                                          self.line_number_area_width(), cr.height()))

    def showEvent(self, event):
        super().showEvent(event)
        # When the content is set while the editor is HIDDEN (e.g. the stable
        # editor, only shown on entering advanced mode), the viewport margins
        # computed then don't get applied to the viewport geometry until a real
        # relayout -> on first show the gutter overlaps the first characters
        # ("cropped/shifted left"). Deferred so it runs once the editor has real
        # geometry (user 2026-07-08).
        QTimer.singleShot(0, self._sync_gutter_geometry)

    def _sync_gutter_geometry(self):
        """Force the viewport margins + gutter to match the current gutter
        width. setViewportMargins is a no-op when Qt thinks the value is
        unchanged (so a stale viewport never recomputes) -> toggle through 0 to
        guarantee the viewport is re-laid out."""
        w = self.line_number_area_width()
        self.setViewportMargins(0, 0, 0, 0)
        self.setViewportMargins(w, 0, 0, 0)
        cr = self.contentsRect()
        self._line_area.setGeometry(QRect(cr.left(), cr.top(), w, cr.height()))

    def paint_line_numbers(self, event):
        c = theme_manager.current
        p = QPainter(self._line_area)
        p.fillRect(event.rect(), QColor(c.code_bg))   # gutter = editor background (spec §3)

        block  = self.firstVisibleBlock()
        num    = block.blockNumber()
        top    = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        h      = self.fontMetrics().height()

        p.setFont(self.font())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                p.setPen(QColor(c.disabled_text))
                p.drawText(0, top, self._line_area.width() - 4, h,
                           Qt.AlignmentFlag.AlignRight, str(num + 1))
            block  = block.next()
            top    = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            num   += 1

    # ── Current line ────────────────────────────────────────

    def _build_current_line_selection(self) -> "QTextEdit.ExtraSelection | None":
        """Current line selection (None if read-only OR if a text
        selection is active — otherwise the current-line highlight would
        fight with the green selection highlight)."""
        if self.isReadOnly() or self.textCursor().hasSelection():
            return None
        c = theme_manager.current
        sel = QTextEdit.ExtraSelection()
        # Current line = SUBTLE phosphor tint (same green family as the
        # selection, but lighter) instead of the nav_hover_bg blue.
        _sk = c.signal_ok.lstrip("#")
        _r, _g, _b = int(_sk[0:2], 16), int(_sk[2:4], 16), int(_sk[4:6], 16)
        sel.format.setBackground(QColor(_r, _g, _b, 28))
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        return sel

    def _rebuild_extra_selections(self):
        """Rebuild the complete list of extra selections."""
        selections: list = []
        cur_sel = self._build_current_line_selection()
        if cur_sel is not None:
            selections.append(cur_sel)
        selections.extend(self._build_feature_selections())
        self.setExtraSelections(selections)

    # ── Attribution lignes -> fonctionnalité (#29) ─────────────

    def set_line_owners(self, owners: list) -> None:
        """Pose la carte (index de bloc -> feature_id | None). Les index
        au-delà de la carte -> None."""
        blk = self.document().firstBlock()
        i = 0
        while blk.isValid():
            owner = owners[i] if i < len(owners) else None
            blk.setUserData(_OwnerBlockData(owner))
            blk = blk.next()
            i += 1
        self._rebuild_extra_selections()

    def line_owners(self) -> list:
        out = []
        blk = self.document().firstBlock()
        while blk.isValid():
            data = blk.userData()
            out.append(data.owner if isinstance(data, _OwnerBlockData) else None)
            blk = blk.next()
        return out

    def _inherit_new_block_owners(self, position: int, removed: int, added: int):
        """Un bloc créé par l'édition (Enter, collage) hérite du propriétaire
        du bloc au-dessus (décision utilisateur 2026-07-03). setPlainText /
        remplacements complets recréent TOUS les blocs sans data : le premier
        bloc n'ayant pas de « dessus » taggé, tout reste None jusqu'à ce que
        le Studio repose la carte (set_line_owners)."""
        doc = self.document()
        first = doc.findBlock(position)
        last = doc.findBlock(position + added)
        # Insertion PILE au début d'une ligne existante (Enter, collage) :
        # Qt garde l'identité (et la userData) sur le PREMIER fragment alors
        # que le contenu d'origine est poussé dans le DERNIER bloc de la
        # plage (nouveau, sans data). On répare : la data suit le CONTENU,
        # puis la boucle d'héritage remplit le premier fragment depuis le
        # bloc au-dessus. Ce transfert n'est valable QUE pour une insertion
        # PURE (removed == 0) : avec removed > 0 (remplacement select-all +
        # insertText, ou ligne sélectionnée remplacée par un collage), le
        # bloc réutilisé par Qt en position `first` peut porter l'owner d'un
        # bloc d'origine tout à fait différent (ex. le DERNIER bloc supprimé)
        # -> le faire suivre poserait un owner périmé sur du contenu NEUF.
        # Revue finale #29 : doute -> orpheline (first.setUserData(None),
        # rien posé sur `last`).
        if position == first.position() and first != last:
            fdata = first.userData()
            if removed == 0:
                if isinstance(fdata, _OwnerBlockData) and last.userData() is None:
                    last.setUserData(_OwnerBlockData(fdata.owner))
                    first.setUserData(None)
            else:
                first.setUserData(None)
        prev = first.previous()
        prev_data = prev.userData() if prev.isValid() else None
        prev_owner = prev_data.owner if isinstance(prev_data, _OwnerBlockData) else None
        blk = first
        while blk.isValid():
            data = blk.userData()
            if isinstance(data, _OwnerBlockData):
                prev_owner = data.owner
            else:
                blk.setUserData(_OwnerBlockData(prev_owner))
            if blk == last:
                break
            blk = blk.next()
        if self._feature_highlight_colors:
            self._rebuild_extra_selections()

    def set_feature_highlights(self, colors: dict) -> None:
        """Active le fond pleine ligne (~25 %) pour chaque bloc dont le
        propriétaire est dans `colors` (feature_id -> QColor opaque, l'alpha
        est posé ici). Dict vide = tout retirer."""
        self._feature_highlight_colors = dict(colors)
        self._rebuild_extra_selections()

    def _build_feature_selections(self) -> list:
        if not self._feature_highlight_colors:
            return []
        sels = []
        blk = self.document().firstBlock()
        while blk.isValid():
            data = blk.userData()
            owner = data.owner if isinstance(data, _OwnerBlockData) else None
            color = self._feature_highlight_colors.get(owner)
            if color is not None:
                sel = QTextEdit.ExtraSelection()
                bg = QColor(color)
                bg.setAlpha(64)                      # ~25 %
                sel.format.setBackground(bg)
                sel.format.setProperty(
                    QTextFormat.Property.FullWidthSelection, True)
                cur = QTextCursor(blk)
                sel.cursor = cur
                sels.append(sel)
            blk = blk.next()
        return sels

    def scroll_to_first_owned(self, feature_id: str) -> None:
        blk = self.document().firstBlock()
        while blk.isValid():
            data = blk.userData()
            if isinstance(data, _OwnerBlockData) and data.owner == feature_id:
                cur = QTextCursor(blk)
                self.setTextCursor(cur)
                self.centerCursor()
                return
            blk = blk.next()

    # ── Autocomplete ()[]{} ───────────────────────────────────

    @staticmethod
    def _is_edit_key(event) -> bool:
        """True if the key would try to MODIFY the text (insertion, Enter,
        deletion, paste/cut). False for navigation / copy / selection."""
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if ctrl:
            # Paste / cut = edit; copy / select-all / etc. = no.
            return key in (Qt.Key.Key_V, Qt.Key.Key_X)
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete,
                   Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            return True
        # Printable character typed (letters, digits, space, punctuation).
        t = event.text()
        return bool(t) and t.isprintable()

    def set_edit_locked(self, locked: bool):
        """Lock/unlock editing without touching setReadOnly (which
        would hide the cursor). Intermediate mode = locked."""
        self._edit_locked = locked

    def _insert_newline_with_indent(self, cursor) -> None:
        """Entrée « intelligente » : reproduit l'indentation de la ligne
        courante, ajoute UN niveau (_INDENT) après un « { » de fin de ligne, et
        développe une paire « {|} » (accolade auto-fermée) en bloc indenté — la
        « } » descend sur sa propre ligne, le curseur reste sur la ligne du
        milieu, indentée. Un seul beginEditBlock -> un seul Ctrl+Z."""
        doc = cursor.document()
        block = cursor.block()
        line = block.text()
        indent = line[:len(line) - len(line.lstrip(" \t"))]
        before = line[:cursor.position() - block.position()]
        opens_block = before.rstrip().endswith("{")
        next_char = doc.characterAt(cursor.position())
        cursor.beginEditBlock()
        if opens_block and next_char == "}":
            # « {|} » -> « {\n<indent><tab>|\n<indent>} »
            cursor.insertText("\n" + indent + self._INDENT + "\n" + indent)
            mid = self.textCursor()
            mid.movePosition(QTextCursor.MoveOperation.Up)
            mid.movePosition(QTextCursor.MoveOperation.EndOfLine)
            self.setTextCursor(mid)
        elif opens_block:
            cursor.insertText("\n" + indent + self._INDENT)
            self.setTextCursor(cursor)
        else:
            cursor.insertText("\n" + indent)
            self.setTextCursor(cursor)
        cursor.endEditBlock()

    def keyPressEvent(self, event):
        if self.isReadOnly() or self._edit_locked:
            # Locked (intermediate mode): a real edit attempt
            # opens the popup (signal); navigation/copy stays allowed.
            if self._is_edit_key(event):
                self.edit_attempted.emit()
                return
            super().keyPressEvent(event)
            return

        cursor = self.textCursor()
        doc = self.document()
        key = event.key()
        text = event.text()
        mods = event.modifiers()

        # Ctrl+Shift+Z → redo (in addition to the native Ctrl+Y)
        if (
            key == Qt.Key.Key_Z
            and mods & Qt.KeyboardModifier.ControlModifier
            and mods & Qt.KeyboardModifier.ShiftModifier
        ):
            self.redo()
            return

        # Enter → auto-indent : conserve l'indentation courante, +1 niveau après
        # un « { », développe « {|} » en bloc. Curseur simple uniquement (une
        # sélection ou Maj+Entrée retombent sur le comportement natif).
        if (
            key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not (mods & Qt.KeyboardModifier.ShiftModifier)
            and not cursor.hasSelection()
        ):
            self._insert_newline_with_indent(cursor)
            return

        # Backspace on empty pair → delete both characters
        if key == Qt.Key.Key_Backspace and not cursor.hasSelection():
            pos = cursor.position()
            if 0 < pos < doc.characterCount() - 1:
                prev_c = doc.characterAt(pos - 1)
                next_c = doc.characterAt(pos)
                if prev_c in self._AUTO_PAIRS and self._AUTO_PAIRS[prev_c] == next_c:
                    cursor.beginEditBlock()
                    cursor.deletePreviousChar()
                    cursor.deleteChar()
                    cursor.endEditBlock()
                    return

        # Opening → insert the pair (or wrap the selection)
        if text in self._AUTO_PAIRS:
            opener = text
            closer = self._AUTO_PAIRS[opener]
            if cursor.hasSelection():
                start = cursor.selectionStart()
                end = cursor.selectionEnd()
                cursor.beginEditBlock()
                c_end = self.textCursor()
                c_end.setPosition(end)
                c_end.insertText(closer)
                c_start = self.textCursor()
                c_start.setPosition(start)
                c_start.insertText(opener)
                new_cur = self.textCursor()
                new_cur.setPosition(start + 1)
                new_cur.setPosition(end + 1, QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(new_cur)
                cursor.endEditBlock()
            else:
                cursor.beginEditBlock()
                cursor.insertText(opener + closer)
                new_cur = self.textCursor()
                new_cur.setPosition(new_cur.position() - 1)
                self.setTextCursor(new_cur)
                cursor.endEditBlock()
            return

        # Closing → skip if the next character is already the same
        if text in self._AUTO_CLOSERS and not cursor.hasSelection():
            pos = cursor.position()
            if pos < doc.characterCount() - 1 and doc.characterAt(pos) == text:
                new_cur = self.textCursor()
                new_cur.setPosition(pos + 1)
                self.setTextCursor(new_cur)
                return

        super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        """Paste / drag-drop / middle-click: blocked when locked (opens the
        popup) -> covers all paste paths, not just Ctrl+V."""
        if self.isReadOnly() or self._edit_locked:
            self.edit_attempted.emit()
            return
        super().insertFromMimeData(source)

    def inputMethodEvent(self, event):
        """Input via input method (IME / dead keys): blocked if
        locked."""
        if (self.isReadOnly() or self._edit_locked) and event.commitString():
            self.edit_attempted.emit()
            event.accept()
            return
        super().inputMethodEvent(event)

    # ── Theme ─────────────────────────────────────────────────

    def apply_theme(self, c: ColorScheme):
        # Editor background via QPalette (Base=code_bg, the darkest background);
        # border/rounding in QSS (spec §3). bg redundant but reliable under QSS.
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(c.code_bg))
        pal.setColor(QPalette.ColorRole.Text, QColor(c.text_primary))
        self.setPalette(pal)
        # Selection highlight = UNIFORM phosphor tint (signal_ok), and the
        # selected text becomes text_primary -> no more "fight" between the
        # syntax highlighting and the selection: the whole highlighted block is green.
        sel_bg = selection_bg(c)
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {c.code_bg};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: 6px;
                selection-background-color: {sel_bg};
                selection-color: {c.text_primary};
            }}
        """)
        self._rebuild_extra_selections()

    # ── Context menu (right-click) ──────────────────────────

    def set_feature_provider(self, provider) -> None:
        """Set the callable feeding the « Assign to a feature » submenu (#31):
        it returns [(feature_id, label, color_hex), …] (empty -> no submenu)."""
        self._feature_provider = provider

    @staticmethod
    def _feature_dot(color_hex: str) -> QIcon:
        """A small filled dot icon for a feature entry (same idea as the
        dropdown pastille)."""
        pm = QPixmap(12, 12)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(color_hex))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 10, 10)
        p.end()
        return QIcon(pm)

    def _selected_line_range(self, event) -> "tuple[int, int]":
        """(start_line, end_line) 0-based of the current selection, or the
        single clicked line when there is no selection. A selection ending at
        column 0 does NOT include that trailing line."""
        cur = self.textCursor()
        if not cur.hasSelection():
            n = self.cursorForPosition(event.pos()).blockNumber()
            return n, n
        doc = self.document()
        a = doc.findBlock(cur.selectionStart()).blockNumber()
        end_block = doc.findBlock(cur.selectionEnd())
        b = end_block.blockNumber()
        if b > a and cur.selectionEnd() == end_block.position():
            b -= 1                       # selection stops at the line start
        return min(a, b), max(a, b)

    def contextMenuEvent(self, event) -> None:
        """Extend the standard context menu (Undo/Cut/Copy/Paste/...) with
        an 'Ask the assistant' entry (F2 step 4).

        Selection > function: if the student has an active selection, the
        scope is limited to the selected lines (useful to target
        a block inside a 50-line loop()). We still keep the
        enclosing function as metadata to give context to the LLM,
        but the prefix and focus are on the selection.

        Otherwise, fall back to the initial behavior: if the right-click
        cursor is in a function body, we emit the complete
        function (cf. Fix 4 for the no-selection-outside-function case).
        """
        menu = self.createStandardContextMenu()
        # Opaque themed background: the editor has its own stylesheet (QPlainTextEdit),
        # so its context menu does not always inherit the global QMenu rule
        # on Windows -> without this the popup shows up transparent. So we style it
        # directly (cf. theme.context_menu_qss).
        menu.setStyleSheet(context_menu_qss(theme_manager.current))
        from .i18n import lang_manager
        strings = lang_manager.current

        # Translation of standard labels: Qt does not translate them without
        # a loaded translator. We remap them by objectName (stable and
        # independent of the Qt language), preserving the shortcut hint
        # (« \tCtrl+C ») present in the original text.
        _labels = {
            "edit-undo":   strings.ctx_menu_undo,
            "edit-redo":   strings.ctx_menu_redo,
            "edit-cut":    strings.ctx_menu_cut,
            "edit-copy":   strings.ctx_menu_copy,
            "edit-paste":  strings.ctx_menu_paste,
            "edit-delete": strings.ctx_menu_delete,
            "select-all":  strings.ctx_menu_select_all,
        }
        for act in menu.actions():
            label = _labels.get(act.objectName())
            if label is None:
                continue
            orig = act.text()
            hint = orig.split("\t", 1)[1] if "\t" in orig else ""
            act.setText(f"{label}\t{hint}" if hint else label)

        # Locked (intermediate): we disable the editing actions
        # (Undo/Redo/Cut/Paste/Delete); we keep Copy and Select
        # All (which keep their natural Qt state), plus the
        # "Ask the assistant" entry (added afterwards, so never grayed out here).
        if self._edit_locked or self.isReadOnly():
            _keep = {"edit-copy", "select-all"}
            for act in menu.actions():
                if act.isSeparator() or act.objectName() in _keep:
                    continue
                act.setEnabled(False)
        text = self.toPlainText()
        sel_cursor = self.textCursor()

        if sel_cursor.hasSelection():
            # Fix 3: scope = selection. We determine the enclosing
            # function (if it exists) via the selection start
            # position -- useful for the LLM but not for the prefix.
            selected_text = sel_cursor.selectedText()
            # Qt uses U+2029 (PARAGRAPH SEPARATOR) for line
            # breaks in selectedText(). We normalize to \n so the
            # LLM sees readable code.
            selected_text = selected_text.replace(" ", "\n")
            sel_start = min(sel_cursor.anchor(), sel_cursor.position())
            fn = _find_function_at_cursor(text, sel_start)
            fn_name = fn[0] if fn is not None else ""
            menu.addSeparator()
            act = menu.addAction(lang_manager.current.chat_help_menu_code)
            act.triggered.connect(
                lambda _checked=False, s=selected_text, n=fn_name:
                    self.help_with_selection_requested.emit(s, n)
            )
        else:
            # No selection: if we are inside a function, initial
            # behavior (emit the whole function). Outside a function without
            # a selection: no entry (covered by Fix 4 later).
            cursor = self.cursorForPosition(event.pos())
            result = _find_function_at_cursor(text, cursor.position())
            if result is not None:
                name, body = result
                menu.addSeparator()
                act = menu.addAction(lang_manager.current.chat_help_menu_code)
                act.triggered.connect(
                    lambda _checked=False, n=name, b=body:
                        self.help_with_function_requested.emit(n, b)
                )

        # « Assign to a feature » submenu (#31 failsafe): re-attribute the
        # selected/clicked line(s) to a chosen feature (or « Manual edits »).
        # Never disabled by the lock loop (added after it) — it changes only the
        # attribution metadata, not the text.
        items = self._feature_provider() if self._feature_provider else []
        if items:
            start_line, end_line = self._selected_line_range(event)
            menu.addSeparator()
            sub = menu.addMenu(strings.ctx_menu_assign_feature)
            sub.setStyleSheet(context_menu_qss(theme_manager.current))
            for fid, flabel, fcolor in items:
                a = sub.addAction(self._feature_dot(fcolor), flabel)
                a.triggered.connect(
                    lambda _checked=False, s=start_line, e=end_line, i=fid:
                        self.assign_lines_to_feature.emit(s, e, i))
        menu.exec(event.globalPos())
