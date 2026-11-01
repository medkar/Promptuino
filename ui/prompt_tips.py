"""Rotating tips in a text field placeholder (#24).

`PromptTipRotator` cycles through `lang_manager.current.prompt_tips` in the
placeholder of a widget ("Generate a feature" prompt field + chat input) every
10 s. The placeholder is only visible when the field is empty, so the rotation
naturally disappears as soon as the user types.

Shared between Studio and chat. `start()`/`stop()` for fields whose placeholder
sometimes has another role (e.g. chat with no backend -> dedicated message).
"""
from __future__ import annotations

import random

from PyQt6.QtCore import QObject, QTimer

from .i18n import lang_manager

_INTERVAL_MS = 10_000


class PromptTipRotator(QObject):
    """Rotates tips in the placeholder of `target` (which must expose
    `setPlaceholderText`)."""

    def __init__(self, target, parent=None, interval_ms: int = _INTERVAL_MS):
        super().__init__(parent or target)
        self._target = target
        self._i = 0
        self._active = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)
        lang_manager.changed.connect(self._on_lang)

    def start(self) -> None:
        self._active = True
        # Random start (not always the same first tip).
        tips = getattr(lang_manager.current, "prompt_tips", ())
        if tips:
            self._i = random.randrange(len(tips))
        self._apply()
        self._timer.start()

    def stop(self) -> None:
        self._active = False
        self._timer.stop()

    def _on_lang(self, _s) -> None:
        if self._active:
            self._apply()

    def _pick(self, n: int) -> int:
        """Random index DIFFERENT from the current one (no immediate repetition)."""
        if n <= 1:
            return 0
        j = random.randrange(n - 1)
        return j if j < self._i else j + 1

    def _tick(self) -> None:
        tips = getattr(lang_manager.current, "prompt_tips", ())
        if tips:
            self._i = self._pick(len(tips))
            self._apply()

    def _apply(self) -> None:
        tips = getattr(lang_manager.current, "prompt_tips", ())
        if not tips:
            return
        self._i %= len(tips)
        self._target.setPlaceholderText(tips[self._i])
