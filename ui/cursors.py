"""Every enabled button shows the hand cursor -- by default, not by discipline.

The convention was already there and almost universal: measured on 2026-08-11,
575 buttons carried `PointingHandCursor` and 28 did not. That ratio is exactly
what made the gap feel like a bug rather than a style: a user hovering the app
learns "a button gives me the hand", then meets one that does not.

The 28 were not a family. They were whatever nobody remembered to write
`setCursor(...)` on -- including every button of the component modals, which is
where the report came from.

So the cursor stops being a line to remember at each `QPushButton(...)` and
becomes an application-level default, installed once from `main.py` next to
`install_global_auto_hide`. Two properties matter:

1. **A deliberate cursor is never overridden.** Some buttons set
   `ArrowCursor` on purpose to say "not for you" -- the ESP32 « bientôt
   disponible » entries in the board, filter and settings views. The filter
   only ever touches a button that had NO explicit cursor when it first saw
   it, and remembers its verdict, so a later `unsetCursor` cannot turn an
   opt-out into a hand.

2. **A disabled button does NOT get the hand.** Qt keeps painting a widget's
   cursor while it is disabled, so a greyed-out button would otherwise still
   invite the click it refuses. The cursor follows the enabled state both
   ways (`EnabledChange`).
"""
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QAbstractButton

# Marks a button the filter is allowed to manage. Absent = never examined;
# False = it had its own cursor from the start, hands off for good.
_MANAGED = "_promptuino_cursor_managed"


def _adopt(btn: QAbstractButton) -> bool:
    """Decide once whether this button is ours to manage, and remember it.

    An opt-out is an explicit cursor that is NOT the hand. Setting the hand by
    hand is not a refusal, it is the same intent written the old way -- and
    treating those 575 buttons as opt-outs would have left them holding the
    hand while greyed out, i.e. a new inconsistency in place of the old one.
    """
    managed = btn.property(_MANAGED)
    if managed is None:
        explicit = btn.testAttribute(Qt.WidgetAttribute.WA_SetCursor)
        managed = (not explicit
                   or btn.cursor().shape() == Qt.CursorShape.PointingHandCursor)
        btn.setProperty(_MANAGED, managed)
    return bool(managed)


def _refresh(btn: QAbstractButton) -> None:
    if not _adopt(btn):
        return
    if btn.isEnabled():
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
    else:
        btn.unsetCursor()


class _ButtonCursorFilter(QObject):
    """Application-wide filter: gives every enabled button the hand cursor.

    Listens to Polish (fired once, when the widget is first styled -- early
    enough that the cursor is right before the button is ever shown) and to
    EnabledChange (so the hand appears and disappears with the button).
    """

    _EVENTS = (QEvent.Type.Polish, QEvent.Type.EnabledChange)

    def eventFilter(self, obj, ev):
        if ev.type() in self._EVENTS and isinstance(obj, QAbstractButton):
            _refresh(obj)
        return False


def install_button_cursors(app) -> _ButtonCursorFilter:
    """Install the filter on the application. Returns it -- keep the reference
    alive, an event filter that gets garbage-collected stops filtering."""
    f = _ButtonCursorFilter(app)
    app.installEventFilter(f)
    return f
