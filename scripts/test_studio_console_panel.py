"""ConsolePanel (ui/studio) : câblage interne journal<->série + API."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(sys.argv)   # ref module-level

from ui.i18n import lang_manager
from ui.studio import ConsolePanel


def test_serial_data_routed_to_log():
    p = ConsolePanel()
    p.serial.data_received.emit("hello serial\n")
    assert "hello serial" in p.log._text.toPlainText()


def test_autoscroll_follows_checkbox_signal():
    p = ConsolePanel()
    p.serial.autoscroll_changed.emit(False)
    assert p.log._auto_scroll is False
    p.serial.autoscroll_changed.emit(True)
    assert p.log._auto_scroll is True


def test_connection_header_and_relay():
    p = ConsolePanel()
    got = []
    p.connection_changed.connect(got.append)
    p.serial.connection_changed.emit(True)
    header = lang_manager.current.serial_console_header
    assert header in p.log._text.toPlainText()
    assert got == [True]
    # Fermeture : relais sans nouvel en-tête.
    before = p.log._text.toPlainText()
    p.serial.connection_changed.emit(False)
    assert p.log._text.toPlainText() == before
    assert got == [True, False]


def test_log_signal_relays():
    p = ConsolePanel()
    helps, actions = [], []
    p.help_with_error_requested.connect(helps.append)
    p.action_clicked.connect(actions.append)
    p.log.help_with_error_requested.emit("err")
    p.log.action_clicked.emit("repairs")
    assert helps == ["err"] and actions == ["repairs"]


def test_clear_for_operation():
    p = ConsolePanel()
    p.log.begin_phase("Test", "#3b82f6")
    assert p.log._text.toPlainText()
    p.clear_for_operation()          # port fermé (no-op ici) + clear
    assert not p.log._text.toPlainText()


def test_serial_bar_in_log():
    p = ConsolePanel(serial_bar_in_log=True)
    assert p.log._bottom_overlay is not None
    p2 = ConsolePanel()
    assert p2.log._bottom_overlay is None


TESTS = [test_serial_data_routed_to_log, test_autoscroll_follows_checkbox_signal,
         test_connection_header_and_relay, test_log_signal_relays,
         test_clear_for_operation, test_serial_bar_in_log]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        t()
        passed += 1
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0)
