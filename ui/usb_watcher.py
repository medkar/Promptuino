"""
Background USB monitoring.
Polls serial ports every second to detect connection
or disconnection of a known board.
"""
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .board_manager import _KNOWN_DEVICES


def _current_pids() -> set[tuple[int, int]]:
    try:
        from serial.tools import list_ports
        return {
            (p.vid, p.pid)
            for p in list_ports.comports()
            if p.vid is not None and p.pid is not None
        }
    except Exception:
        return set()


class USBWatcher(QObject):
    """
    Emits board_connected(env_id, model) when a known board is plugged in,
    board_disconnected() when it is removed.
    """
    board_connected    = pyqtSignal(str, str)
    board_disconnected = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_pids:  set[tuple[int, int]]       = set()
        self._active_pid: tuple[int, int] | None      = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)

    def start(self, active_pid: tuple[int, int] | None = None):
        """Starts monitoring. active_pid: VID:PID already detected at startup."""
        self._last_pids  = _current_pids()
        self._active_pid = active_pid
        self._timer.start()

    def _poll(self):
        current = _current_pids()
        added   = current - self._last_pids
        removed = self._last_pids - current
        self._last_pids = current

        # Active board disconnected
        if self._active_pid and self._active_pid in removed:
            self._active_pid = None
            self.board_disconnected.emit()

        # New known board detected
        if not self._active_pid:
            for pid in added:
                if pid in _KNOWN_DEVICES:
                    self._active_pid = pid
                    env_id, model = _KNOWN_DEVICES[pid]
                    self.board_connected.emit(env_id, model)
                    break
