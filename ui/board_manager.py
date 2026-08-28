"""
Target board manager.
Stores the selected environment (arduino/esp32) and model.
Provides automatic detection via pyserial (optional).
"""
from PyQt6.QtCore import QObject, pyqtSignal

# "Coming soon" environments: present in the UI but greyed out
# (non-selectable) with a tooltip. ESP32 is kept visible but disabled
# until its support is ready. (STM32 / Raspberry Pi have been removed.)
COMING_SOON_ENVS: frozenset[str] = frozenset({"esp32"})

# Catalog: env_id → {label, models}
BOARDS: dict[str, dict] = {
    "arduino": {
        "label": "Arduino",
        "models": [
            "Uno", "Uno R4 Minima", "Uno R4 WiFi",
            "Mega 2560", "Nano", "Nano Every",
            "Leonardo", "Due", "Micro", "Pro Mini",
        ],
    },
    "esp32": {
        "label": "ESP32",
        "models": [
            "ESP32 DevKit v1", "ESP32-S2", "ESP32-S3",
            "ESP32-C3", "Wemos D1 Mini ESP32",
        ],
    },
}

# FQBN (Fully Qualified Board Name) for arduino-cli
FQBN: dict[tuple[str, str], str] = {
    ("arduino", "Uno"):               "arduino:avr:uno",
    ("arduino", "Uno R4 Minima"):     "arduino:renesas_uno:minima",
    ("arduino", "Uno R4 WiFi"):       "arduino:renesas_uno:unor4wifi",
    ("arduino", "Mega 2560"):         "arduino:avr:mega",
    ("arduino", "Nano"):              "arduino:avr:nano",
    ("arduino", "Nano Every"):        "arduino:megaavr:nona4809",
    ("arduino", "Leonardo"):          "arduino:avr:leonardo",
    ("arduino", "Due"):               "arduino:sam:arduino_due_x_dbg",
    ("arduino", "Micro"):             "arduino:avr:micro",
    ("arduino", "Pro Mini"):          "arduino:avr:pro",
    ("esp32",   "ESP32 DevKit v1"):   "esp32:esp32:esp32",
    ("esp32",   "ESP32-S2"):          "esp32:esp32:esp32s2",
    ("esp32",   "ESP32-S3"):          "esp32:esp32:esp32s3",
    ("esp32",   "ESP32-C3"):          "esp32:esp32:esp32c3",
    ("esp32",   "Wemos D1 Mini ESP32"):"esp32:esp32:wemos_d1_mini32",
}


def get_fqbn(env_id: str, model: str) -> str | None:
    """Returns the FQBN for arduino-cli, or None if not supported."""
    return FQBN.get((env_id, model))


# VID:PID → (env_id, model_name)
# Only verified or confirmed values are listed here.
_KNOWN_DEVICES: dict[tuple[int, int], tuple[str, str]] = {
    # Arduino Uno R3 (ATmega16U2) — old/new bootloader
    (0x2341, 0x0001): ("arduino", "Uno"),
    (0x2341, 0x0043): ("arduino", "Uno"),
    # Arduino Uno R4
    (0x2341, 0x1002): ("arduino", "Uno R4 WiFi"),
    # Arduino Mega 2560 (ATmega16U2) — old/new bootloader
    (0x2341, 0x0010): ("arduino", "Mega 2560"),
    (0x2341, 0x0042): ("arduino", "Mega 2560"),
    # Arduino Leonardo — bootloader / runtime
    (0x2341, 0x0036): ("arduino", "Leonardo"),
    (0x2341, 0x8036): ("arduino", "Leonardo"),
    # Arduino Due — programming port / native port
    (0x2341, 0x003D): ("arduino", "Due"),
    (0x2341, 0x003E): ("arduino", "Due"),
    # Arduino Micro — bootloader / runtime
    (0x2341, 0x0037): ("arduino", "Micro"),
    (0x2341, 0x8037): ("arduino", "Micro"),
    # Arduino Nano clone (CH340G)
    (0x1A86, 0x7523): ("arduino", "Nano"),
    # ESP32 / STM32 / Raspberry Pi: auto-detection removed (ESP32 = "coming
    # soon", non-selectable; STM32 / RPi not supported).
}


def detect_board() -> tuple[str, str] | None:
    """
    Scans USB serial ports and returns (env_id, model_name) if a known board
    is found, otherwise None.
    Raises ImportError if pyserial is not installed.
    """
    from serial.tools import list_ports  # late import — pyserial optional
    for port in list_ports.comports():
        if port.vid is None or port.pid is None:
            continue
        result = _KNOWN_DEVICES.get((port.vid, port.pid))
        if result is not None:
            return result
    return None


class BoardState:
    NONE      = "none"       # no board
    MANUAL    = "manual"     # configured manually (not verified)
    CONNECTED = "connected"  # detected/verified via USB


class BoardManager(QObject):
    """Emits a signal when the board or its state changes."""

    changed       = pyqtSignal(str, str)  # (env_id, model_name)
    state_changed = pyqtSignal(str)       # BoardState value

    def __init__(self):
        super().__init__(None)
        self._env:   str = ""
        self._model: str = ""
        self._port:  str = ""
        self._state: str = BoardState.NONE

    @property
    def env(self) -> str:
        return self._env

    @property
    def model(self) -> str:
        return self._model

    @property
    def state(self) -> str:
        return self._state

    @property
    def port(self) -> str:
        return self._port

    def set_port(self, port: str):
        self._port = port

    @property
    def connected(self) -> bool:
        return self._state == BoardState.CONNECTED

    def set_board_manual(self, env_id: str, model: str):
        """Manual selection confirmed by the user."""
        board_changed = env_id != self._env or model != self._model
        self._env   = env_id
        self._model = model
        if board_changed:
            self.changed.emit(env_id, model)
        if self._state != BoardState.MANUAL:
            self._state = BoardState.MANUAL
            self.state_changed.emit(BoardState.MANUAL)

    def set_board_connected(self, env_id: str, model: str):
        """Board detected via USB — physically verified."""
        board_changed = env_id != self._env or model != self._model
        self._env   = env_id
        self._model = model
        if board_changed:
            self.changed.emit(env_id, model)
        if self._state != BoardState.CONNECTED:
            self._state = BoardState.CONNECTED
            self.state_changed.emit(BoardState.CONNECTED)

    def set_connected(self, connected: bool):
        """Called by the USB watcher on disconnection."""
        new_state = BoardState.CONNECTED if connected else BoardState.NONE
        if new_state == self._state:
            return
        self._state = new_state
        self.state_changed.emit(new_state)


# Global instance — import from other modules
board_manager = BoardManager()
