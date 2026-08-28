"""
Integrated Serial Monitor — displays and sends serial data in real time.

Auto-scroll controlled by a checkbox in the title bar.
  - Checked (default): each new message scrolls to the bottom.
  - Unchecked: messages keep arriving but the view stays put,
    allowing the history to be re-read.

Automatic connection managed by the parent (StudioView).
Changing the baud rate during an active connection closes and reopens it.
"""

import re
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QLabel, QPushButton, QPlainTextEdit, QLineEdit, QComboBox, QCheckBox,
)

from pathlib import Path

_BAUD_RE = re.compile(r'Serial\.begin\s*\(\s*(\d+)\s*\)')

from .theme import (
    ColorScheme, theme_manager, radio_checkbox_qss, neutral_button_qss,
    combo_qss, input_qss
)
from .fonts import MONO_CSS
from .i18n import lang_manager, Strings
from .board_manager import board_manager
from . import arduino_cli

_BAUD_RATES   = ["300", "1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"]
_DEFAULT_BAUD = "9600"
_WORKER_WAIT_MS = 1000


# ── Serial reader worker ───────────────────────────────────────────────────

class _SerialReaderWorker(QThread):
    """
    Thread dedicated to reading the serial port.
    Loops while _running is True, reads available bytes
    every 20 ms and emits data_received.
    """

    data_received = pyqtSignal(str)
    error         = pyqtSignal(str)
    disconnected  = pyqtSignal()

    def __init__(self, port: str, baud: int):
        super().__init__()
        self._port    = port
        self._baud    = baud
        self._running = True
        self._ser     = None

    def send(self, text: str):
        """Sends a line of text over the serial port."""
        if self._ser and self._ser.is_open:
            try:
                self._ser.write((text + '\n').encode('utf-8', errors='replace'))
            except Exception:
                pass

    def stop(self):
        """Requests the read loop to stop."""
        self._running = False

    def run(self):
        try:
            import serial
        except ImportError:
            self.error.emit("Package pyserial non installé.\nLancez : pip install pyserial")
            return
        try:
            self._ser = serial.Serial(self._port, self._baud, timeout=0.1)
            while self._running:
                try:
                    waiting = self._ser.in_waiting
                    if waiting:
                        raw = self._ser.read(waiting)
                        self.data_received.emit(raw.decode('utf-8', errors='replace'))
                except Exception:
                    break
                self.msleep(20)
        except serial.SerialException as e:
            self.error.emit(str(e))
        finally:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = None
            self.disconnected.emit()


# ── Serial Monitor widget ─────────────────────────────────────────────────────

class SerialMonitorWidget(QWidget):
    """
    Serial Monitor without a Connect/Disconnect button.
    The connection is managed externally via open_port() / close_port().

    Public API:
      is_open() -> bool
      open_port()              — opens via board_manager or auto-detection
      close_port()             — closes cleanly
      connection_changed(bool) — signal emitted on each state change
    """

    connection_changed = pyqtSignal(bool)
    # Broadcasts each received serial chunk to the outside — lets the advanced
    # Studio route the serial stream into the merged STDOUT console (Phase 3 §5)
    # rather than into the internal display (hidden in that case).
    data_received = pyqtSignal(str)
    # State of the « auto-scroll » checkbox — relayed to drive the scroll of
    # the external console when the internal display is hidden (Phase 3 §5).
    autoscroll_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _SerialReaderWorker | None = None
        # Callback that provides the current code. Called on each open_port
        # to detect the baud via Serial.begin(...) and apply it before
        # opening the port. Set by the parent (studio_view).
        self._code_source: Optional[Callable[[], str]] = None
        # Compact mode: narrow control strip (advanced Studio right column,
        # 380 px) -> everything on ONE line with a reduced font, baud label
        # hidden (combo + tooltip). The "Auto-scroll" label stays whole.
        self._compact = False
        self._build()
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── Control row: title | auto-scroll checkbox | baud ──
        self._ctrl_w = QWidget()
        ctrl = QHBoxLayout(self._ctrl_w)
        ctrl.setSpacing(8)
        ctrl.setContentsMargins(0, 0, 0, 0)

        self._lbl_title = QLabel()
        ctrl.addWidget(self._lbl_title)
        ctrl.addStretch()

        # Connect/Disconnect button — reserved for Advanced mode (hidden by
        # default). In Beginner/Intermediate the connection is automatic.
        self._btn_connect = QPushButton()
        self._btn_connect.setFixedHeight(28)
        self._btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_connect.clicked.connect(self._on_connect_clicked)
        self._btn_connect.setVisible(False)
        # Minimum policy: the button never shrinks below the width of
        # its text -> "Connect"/"Disconnect" is no longer clipped.
        self._btn_connect.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        ctrl.addWidget(self._btn_connect)
        ctrl.addSpacing(6)

        # Auto-scroll label + checkbox — label on the left, checked by default
        self._lbl_autoscroll = QLabel()
        ctrl.addWidget(self._lbl_autoscroll)

        self._chk_autoscroll = QCheckBox()
        self._chk_autoscroll.setChecked(True)
        self._chk_autoscroll.toggled.connect(self.autoscroll_changed.emit)
        ctrl.addWidget(self._chk_autoscroll)

        self._lbl_baud = QLabel()
        ctrl.addSpacing(6)
        ctrl.addWidget(self._lbl_baud)

        self._baud_combo = QComboBox()
        self._baud_combo.addItems(_BAUD_RATES)
        self._baud_combo.setCurrentText(_DEFAULT_BAUD)
        self._baud_combo.setFixedWidth(100)
        self._baud_combo.currentTextChanged.connect(self._on_baud_changed)
        ctrl.addWidget(self._baud_combo)

        layout.addWidget(self._ctrl_w)

        # ── Display area ──
        self._display = QPlainTextEdit()
        self._display.setReadOnly(True)
        self._display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._display, stretch=1)

        # ── Send row ──
        self._send_row_w = QWidget()
        send_row = QHBoxLayout(self._send_row_w)
        send_row.setSpacing(8)
        send_row.setContentsMargins(0, 0, 0, 0)

        self._send_input = QLineEdit()
        self._send_input.setFixedHeight(32)
        self._send_input.returnPressed.connect(self._on_send)
        send_row.addWidget(self._send_input, stretch=1)

        self._btn_send = QPushButton()
        self._btn_send.setFixedHeight(32)
        self._btn_send.setEnabled(False)
        self._btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_send.clicked.connect(self._on_send)
        send_row.addWidget(self._btn_send)

        layout.addWidget(self._send_row_w)

    # ── Public API ──────────────────────────────────────────────────────────

    def is_open(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def recent_output(self, max_lines: int = 40) -> str:
        """Last `max_lines` NON-EMPTY lines currently shown in the monitor —
        runtime evidence for the behavioral review (layer A). "" if empty."""
        lines = [l for l in self._display.toPlainText().split("\n") if l.strip()]
        return "\n".join(lines[-max_lines:])

    def suggest_baud(self, baud: str):
        """
        Applies the baud rate detected in the code (Serial.begin).

        If the port is open and the detected baud differs, we change it
        anyway: `_on_baud_changed` will close and reopen the connection with the
        new value. The user can always override manually via
        the combo (which stays editable even during a connection).
        """
        values = [self._baud_combo.itemText(i) for i in range(self._baud_combo.count())]
        if baud in values:
            self._baud_combo.setCurrentText(baud)

    def set_title_visible(self, visible: bool):
        self._lbl_title.setVisible(visible)

    def get_ctrl_widget(self) -> QWidget:
        """Returns the control row (autoscroll + baud) for external placement."""
        return self._ctrl_w

    def get_send_widget(self) -> QWidget:
        """Returns the send row (message field + Send button) for
        external placement (e.g. bottom strip of the advanced Studio log)."""
        return self._send_row_w

    def set_send_visible(self, visible: bool):
        self._send_row_w.setVisible(visible)

    def set_display_visible(self, visible: bool):
        """Hides the internal display when the serial stream is routed to an
        external console (merged STDOUT of the advanced Studio, Phase 3 §5)."""
        self._display.setVisible(visible)

    def set_baud_visible(self, visible: bool):
        """Hides the baud selector (+ its label). Used in beginner mode
        where Connect is kept but not the baud choice."""
        self._lbl_baud.setVisible(visible)
        self._baud_combo.setVisible(visible)

    def set_compact(self, compact: bool):
        """Narrow control strip (advanced Studio right column): baud label
        hidden (combo + tooltip) and controls DISTRIBUTED evenly across the
        width — Connect on the left, « Défilement auto » in the center, baud on
        the right (two equal stretches)."""
        self._compact = compact
        self._baud_combo.setFixedWidth(78 if compact else 100)
        self._lbl_baud.setVisible(True)              # « Baud » label kept
        ctrl = self.get_ctrl_widget().layout()
        if compact:
            # Empty the layout (the widgets remain, referenced by self._*) then
            # reorder with stretches for an even distribution. Margins
            # and spacing reduced to fit everything on one line.
            while ctrl.count():
                ctrl.takeAt(0)
            ctrl.setContentsMargins(0, 0, 0, 0)
            ctrl.setSpacing(4)
            ctrl.addWidget(self._btn_connect)        # left
            ctrl.addStretch(1)
            ctrl.addWidget(self._lbl_autoscroll)     # center
            ctrl.addWidget(self._chk_autoscroll)
            ctrl.addStretch(1)
            ctrl.addWidget(self._lbl_baud)           # right: Baud + combo
            ctrl.addWidget(self._baud_combo)
        self.apply_theme(theme_manager.current)
        self.apply_lang(lang_manager.current)

    def is_autoscroll(self) -> bool:
        """Current state of the « auto-scroll » checkbox."""
        return self._chk_autoscroll.isChecked()

    def set_connect_visible(self, visible: bool):
        """Shows or hides the Connect/Disconnect button.

        In Beginner/Intermediate mode the connection is automatic and this
        button is not relevant; in Advanced the user may want to
        free the port for another tool, hence its exposure.
        """
        self._btn_connect.setVisible(visible)

    def set_code_source(self, source: Optional[Callable[[], str]]):
        """Registers a function that returns the current code.

        Used on each open_port to detect Serial.begin(...) and
        sync the baud combo. The user can then override
        manually via the combo (their choice is kept until the next
        open).
        """
        self._code_source = source

    def open_port(self, refresh_baud: bool = True):
        """Opens the serial port.

        refresh_baud=True (default): scans the current code via
        `set_code_source` and adjusts the combo. Set to False to reopen
        after a manual baud change (see _on_baud_changed) so as
        not to overwrite the user's explicit choice.
        """
        if self.is_open():
            return
        if refresh_baud and self._code_source is not None:
            try:
                code = self._code_source() or ""
            except Exception:
                code = ""
            m = _BAUD_RE.search(code)
            if m:
                self.suggest_baud(m.group(1))
        port = board_manager.port or arduino_cli._find_port_auto()
        if not port:
            return
        baud = int(self._baud_combo.currentText())
        self._worker = _SerialReaderWorker(port, baud)
        self._worker.data_received.connect(self._on_data)
        self._worker.error.connect(self._on_error)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.start()
        self._set_ui_connected(True)

    def close_port(self):
        if self._worker:
            w = self._worker
            # Detach the reference IMMEDIATELY: if `_on_baud_changed`
            # chains a close_port + open_port, the new worker must
            # not be overwritten by a late `disconnected` signal from the
            # previous worker. We also disconnect all slots so that
            # no late delivery (cross-thread queue) reaches
            # self._on_disconnected / _on_data / _on_error once the
            # new worker is in place.
            self._worker = None
            for sig, slot in (
                (w.data_received, self._on_data),
                (w.error, self._on_error),
                (w.disconnected, self._on_disconnected),
            ):
                try:
                    sig.disconnect(slot)
                except TypeError:
                    pass
            w.stop()
            w.wait(_WORKER_WAIT_MS)
            w.deleteLater()
        self._set_ui_connected(False)

    # ── Internal slots ────────────────────────────────────────────────────────

    def _on_baud_changed(self):
        """Automatic reconnection if the baud changes during an active session.

        refresh_baud=False: the user has just explicitly imposed this
        value via the combo, we don't want open_port to overwrite it by
        re-reading the code.
        """
        if self.is_open():
            self.close_port()
            self.open_port(refresh_baud=False)

    def _on_data(self, text: str):
        """
        Inserts the received data at the end of the document.
        If the auto-scroll checkbox is checked, scrolls to the bottom.
        Otherwise, saves and restores the position so the view doesn't move.
        """
        # Merged STDOUT (advanced studio): we also broadcast to an external
        # console mixing compile log + serial (spec Phase 3 §5).
        self.data_received.emit(text)
        sb = self._display.verticalScrollBar()

        if self._chk_autoscroll.isChecked():
            # Automatic scrolling: insert + scroll to the bottom
            cursor = self._display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text)
            self._display.setTextCursor(cursor)
        else:
            # No scrolling: insert without moving the view
            saved = sb.value()
            cursor = self._display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text)
            self._display.setTextCursor(cursor)
            sb.setValue(saved)

    def _on_error(self, msg: str):
        self._display.appendPlainText(f"⚠ {msg}")
        self._worker = None
        self._set_ui_connected(False)

    def _on_disconnected(self):
        self._worker = None
        self._set_ui_connected(False)

    def _on_send(self):
        text = self._send_input.text().strip()
        if text and self._worker:
            self._worker.send(text)
            self._send_input.clear()

    def _on_connect_clicked(self):
        if self.is_open():
            self.close_port()
        else:
            self.open_port()

    def _set_ui_connected(self, connected: bool):
        self._btn_send.setEnabled(connected)
        # The baud combo stays editable even during a connection: a
        # change triggers close_port + open_port in _on_baud_changed.
        s = lang_manager.current
        self._btn_connect.setText(
            s.serial_disconnect if connected else s.serial_connect
        )
        self.connection_changed.emit(connected)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def apply_theme(self, c: ColorScheme):
        # In compact mode (narrow strip): reduced font to keep everything on
        # one line.
        # The compact strip keeps a normal font (9-10 pt): the room is enough
        # with the real font (Geist) once the « Baud » label is hidden and the
        # combo tightened. Only the combo/spacings are reduced.
        lp   = 9                            # labels
        bp   = 9                            # Connect button
        bpad = 9 if self._compact else 10   # Connect horizontal padding
        cp   = 9 if self._compact else 10   # baud combo
        ch   = 28 if self._compact else 32  # combo height
        self._lbl_title.setStyleSheet(
            f"font-size: 10pt; font-weight: 600; color: {c.text_primary};"
        )
        self._lbl_baud.setStyleSheet(f"font-size: {lp}pt; color: {c.text_secondary};")
        self._lbl_autoscroll.setStyleSheet(f"font-size: {lp}pt; color: {c.text_secondary};")
        # "auto-scroll" checkbox: centralized agreed style (wireframe
        # white/gray indicator -> GREEN on hover AND checked, with a white check).
        self._chk_autoscroll.setStyleSheet(radio_checkbox_qss(c))

        # Serial display = output area -> code_bg background (spec §3); send field
        # = input -> input_bg. border border, radius 6.
        self._display.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {c.code_bg};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: 6px;
                padding: 6px 8px;
                font-family: {MONO_CSS};
                font-size: 9pt;
            }}
        """)
        self._send_input.setStyleSheet(
            input_qss(c, font_pt=9, padding="6px 8px", font_family=MONO_CSS))

        # « Envoyer » button: same NEUTRAL wireframe style as « Connecter »
        # (solid code_bg, opaque, border, green on hover). cf neutral_button_qss.
        self._btn_send.setStyleSheet(
            neutral_button_qss(c, bg=c.code_bg, font_pt=bp, padding=f"0 {bpad}px")
        )
        # « Connecter » button: opaque NEUTRAL style, but with the SAME background as
        # the console/log (code_bg) -> it blends in. Green on hover.
        self._btn_connect.setStyleSheet(
            neutral_button_qss(c, bg=c.code_bg, font_pt=bp, padding=f"0 {bpad}px")
        )
        # Baud combo: the app's combo, like its two neighbours in this same
        # strip (« Envoyer », « Connecter ») which already turn GREEN on hover.
        # Its hand-written copy was a PARTIAL one -- no :hover, no :focus, no
        # :disabled, native arrow instead of the app chevron -- so this one
        # control stayed inert while everything around it lit up.
        #
        # The height goes through setFixedHeight instead of a `height:` rule
        # concatenated to the helper: a QComboBox rule written here would keep
        # this file in the theme-coherence exemption list, which is what the
        # conversion exists to leave. `+ 2` because the QSS `height` it replaces
        # sized the CONTENT box -- the 1 px border on each side came on top
        # (measured: `height: 32px` rendered a 34 px widget). Same rendered
        # height as before, in both compact and normal mode.
        self._baud_combo.setFixedHeight(ch + 2)
        self._baud_combo.setStyleSheet(combo_qss(c, font_pt=cp, padding="0 8px"))

    # ── Language ────────────────────────────────────────────────────────────────

    def apply_lang(self, s: Strings):
        self._lbl_title.setText(s.serial_title)
        self._lbl_baud.setText(s.serial_baud)
        self._lbl_autoscroll.setText(s.serial_autoscroll)
        self._chk_autoscroll.setText("")
        self._btn_send.setText(s.serial_send)
        self._send_input.setPlaceholderText(s.serial_send_placeholder)
        self._btn_connect.setText(
            s.serial_disconnect if self.is_open() else s.serial_connect
        )
