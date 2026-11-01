"""Reusable diff tools (red/green highlighted code view).

Shared between the « Analyser / Réparer » modal (side-by-side diff) and the
« Corrections automatiques » modal (unified diff). No Qt dependency beyond
the themed code editor.
"""
from __future__ import annotations

import difflib

from PyQt6.QtGui import QColor, QTextCursor, QTextFormat
from PyQt6.QtWidgets import QTextEdit

from .code_editor import CodeEditor
from .theme import theme_manager


def build_side_by_side_diff(old_code: str, new_code: str):
    """Side-by-side diff. Returns (old_removed, new_added): 0-based indices of
    the ORIGINAL lines removed/modified (RED on the left) and the CORRECTED
    lines added/modified (GREEN on the right). Each panel keeps its text
    verbatim."""
    old_lines = old_code.splitlines()
    new_lines = new_code.splitlines()
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    old_removed: set[int] = set()
    new_added: set[int] = set()
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ('delete', 'replace'):
            old_removed.update(range(i1, i2))
        if op in ('insert', 'replace'):
            new_added.update(range(j1, j2))
    return old_removed, new_added


def build_unified_diff(old_code: str, new_code: str):
    """Line-by-line unified diff. Returns (lines, removed, added): `lines` =
    lines to display (context + removed + added interleaved), `removed`/
    `added` = 0-based indices in `lines` of the removed lines (RED) and added/
    modified ones (GREEN). Compact: a single panel shows both versions."""
    old_lines = old_code.splitlines()
    new_lines = new_code.splitlines()
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    lines: list[str] = []
    removed: set[int] = set()
    added: set[int] = set()
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            lines.extend(new_lines[j1:j2])
        else:  # delete / insert / replace: removed first, added next
            for ln in old_lines[i1:i2]:
                removed.add(len(lines))
                lines.append(ln)
            for ln in new_lines[j1:j2]:
                added.add(len(lines))
                lines.append(ln)
    return lines, removed, added


def link_scrollbars(view_a, view_b):
    """Synchronizes two editors vertically by VALUE (not by ratio).

    Setting one sets the other to the same value; `QScrollBar.setValue`
    automatically clamps to [min, max]. Intended consequence when the two codes don't
    have the same number of lines: the longer panel can scroll lower
    than the shorter one (which stays pinned to its max); scrolling back up, only the
    longer one moves as long as its value exceeds the shorter one's max, then — once
    back in the common range — the two scroll together again.

    Re-entrance guard (`state["sync"]`) to break the feedback loop
    (setting B emits B's `valueChanged`, which would want to re-set A…)."""
    bar_a = view_a.verticalScrollBar()
    bar_b = view_b.verticalScrollBar()
    state = {"sync": False}

    def _mirror(dst):
        def handler(value):
            if state["sync"]:
                return
            state["sync"] = True
            dst.setValue(value)        # clamped to dst's [min, max] by Qt
            state["sync"] = False
        return handler

    bar_a.valueChanged.connect(_mirror(bar_b))
    bar_b.valueChanged.connect(_mirror(bar_a))


class _DiffCodeView(CodeEditor):
    """Read-only CodeEditor that highlights a diff: red background on the removed
    lines, green on the added/modified ones. The selections survive
    cursor moves (re-injected in `_rebuild_extra_selections`, which
    CodeEditor calls back on every move / theme change)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    def set_diff(self, removed: set[int], added: set[int]):
        self._removed = set(removed)
        self._added = set(added)
        self._rebuild_extra_selections()

    @staticmethod
    def _rgba(hex_color: str, alpha: int) -> QColor:
        h = hex_color.lstrip("#")
        return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)

    def _line_selection(self, line_idx: int, color: QColor):
        block = self.document().findBlockByNumber(line_idx)
        if not block.isValid():
            return None
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(color)
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        # Select the WHOLE block (start -> end), not a collapsed cursor: otherwise,
        # when the line overflows and wraps (word-wrap), only the 1st
        # display line is colored. With the entire block selected, the
        # highlight covers all the visual lines of the wrap.
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor)
        sel.cursor = cursor
        return sel

    def _rebuild_extra_selections(self):
        c = theme_manager.current
        red = self._rgba(c.signal_error, 60)
        green = self._rgba(c.signal_ok, 50)
        sels: list = []
        for i in getattr(self, '_removed', ()):  # getattr: super().__init__ may
            s = self._line_selection(i, red)      # call back before set_diff
            if s is not None:
                sels.append(s)
        for i in getattr(self, '_added', ()):
            s = self._line_selection(i, green)
            if s is not None:
                sels.append(s)
        cur = self._build_current_line_selection()   # None when read-only
        if cur is not None:
            sels.append(cur)
        self.setExtraSelections(sels)
