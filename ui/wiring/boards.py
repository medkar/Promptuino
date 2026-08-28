"""Catalog of supported boards for the wiring schematic.

Loads `assets/wiring/boards/boards.json` and exposes an ergonomic Board
class (capabilities, pin positions, voltage rails).

For MVP1: only `arduino_uno_r3` ships — the architecture is ready
to host Nano, Mega, ESP32 etc. (add an entry in the JSON).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Mapping FQBN arduino-cli -> catalog board_id. Lets us start
# from the board_manager state (which knows FQBN/env/model) to select
# the right board from the wiring catalog.
_FQBN_TO_BOARD_ID: dict[str, str] = {
    "arduino:avr:uno":                   "arduino_uno_r3",
    "arduino:renesas_uno:minima":        "arduino_uno_r4",
    "arduino:renesas_uno:unor4wifi":     "arduino_uno_r4",
    "arduino:avr:nano":                  "arduino_nano",
    "arduino:avr:mega":                  "arduino_mega_2560",
    "arduino:avr:leonardo":              "arduino_leonardo",
}

# Ergonomic mapping (env, model) -> board_id, for board_manager which
# exposes env="arduino"/etc. + model="Uno"/"Nano"/etc.
_ENV_MODEL_TO_BOARD_ID: dict[tuple[str, str], str] = {
    ("arduino", "Uno"):              "arduino_uno_r3",
    ("arduino", "Uno R4 Minima"):    "arduino_uno_r4",
    ("arduino", "Uno R4 WiFi"):      "arduino_uno_r4",
    ("arduino", "Nano"):             "arduino_nano",
    ("arduino", "Mega 2560"):        "arduino_mega_2560",
    ("arduino", "Leonardo"):         "arduino_leonardo",
    # Pro Mini / Micro share the ATmega328/32u4 — we map them onto Uno R3
    # by default (compatible footprint for educational wiring).
    ("arduino", "Pro Mini"):         "arduino_uno_r3",
    ("arduino", "Micro"):            "arduino_leonardo",
}


def _assets_root() -> Path:
    # ui/wiring/boards.py -> go up two levels to reach the repo root,
    # then assets/wiring/boards.
    return Path(__file__).resolve().parents[2] / "assets" / "wiring"


_BOARDS_FILE = _assets_root() / "boards" / "boards.json"

_cache: dict[str, dict[str, Any]] | None = None


def _load() -> dict[str, dict[str, Any]]:
    global _cache
    if _cache is not None:
        return _cache
    try:
        data = json.loads(_BOARDS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _cache = {}
        return _cache
    _cache = dict(data.get("boards", {}) or {})
    return _cache


class Board:
    """Ergonomic view of a board loaded from boards.json."""

    def __init__(self, board_id: str, raw: dict[str, Any]):
        self.id          = board_id
        self.display_name= raw.get("display_name", board_id)
        self.fqbn        = raw.get("fqbn", "")
        self.form_factor = raw.get("form_factor", "")
        self.voltage_logic = float(raw.get("voltage_logic", 5.0))
        self.voltage_rails = list(raw.get("voltage_rails", []) or [])
        self._pinout: dict[str, dict[str, Any]] = dict(raw.get("pinout", {}) or {})
        self._render: dict[str, Any] = dict(raw.get("render", {}) or {})

    # ── Pinout ───────────────────────────────────────────────
    def pins(self) -> list[str]:
        return list(self._pinout.keys())

    def has_pin(self, pin: str) -> bool:
        return pin in self._pinout

    def has_capability(self, pin: str, cap: str) -> bool:
        info = self._pinout.get(pin)
        if not info:
            return False
        return cap in (info.get("capabilities", []) or [])

    def pwm_capable_pins(self) -> set[str]:
        """Returns the set of pins having the 'pwm' capability according to
        boards.json. Hardware source of truth used by Strategy
        4 of the DC motor detector (markers._resolve_pwm_capable_fallback)
        when analyzing the code alone isn't enough to distinguish PWM vs
        digital. Hardware-agnostic: works for any
        board present in the catalog (Uno/Nano/Mega/Uno R4/...)."""
        return {pin for pin in self._pinout
                 if self.has_capability(pin, "pwm")}

    def pin_position(self, pin: str) -> tuple[int, int] | None:
        info = self._pinout.get(pin)
        if not info:
            return None
        pos = info.get("pos")
        if not pos or len(pos) < 2:
            return None
        return (int(pos[0]), int(pos[1]))

    def alias_count(self, pin: str) -> int:
        info = self._pinout.get(pin)
        if not info:
            return 0
        return int(info.get("alias_count", 1))

    def is_power_rail(self, net: str) -> bool:
        return net in self.voltage_rails

    # ── Rendering ────────────────────────────────────────────────
    @property
    def render(self) -> dict[str, Any]:
        return self._render


def load_board(board_id: str) -> Board | None:
    raw = _load().get(board_id)
    if raw is None:
        return None
    return Board(board_id, raw)


def list_boards() -> list[str]:
    return list(_load().keys())


def board_id_for_fqbn(fqbn: str) -> str | None:
    """Returns the wiring catalog board_id for a given FQBN.

    None if the FQBN has no (yet) matching board in the
    catalog. The caller must gracefully degrade (e.g. display a
    message « cette carte n'est pas encore supportee »).
    """
    return _FQBN_TO_BOARD_ID.get(fqbn)


def board_id_for_env_model(env: str, model: str) -> str | None:
    """Ergonomic env/model mapping (board_manager) -> board_id.

    Strict lookup in the MVP4 catalog (Uno R3 / Uno R4 / Nano /
    Mega 2560 / Leonardo + aliases Pro Mini & Micro). For Arduino
    models not listed (Due, Nano Every) we fall back to Uno R3 rather
    than returning None — the D0-D13/A0-A5 pinout stays 90 %
    compatible and avoids a « non supporte » banner. The other environments
    (esp32, « bientot disponible ») return None as long as they don't have
    their own board in the catalog.
    """
    bid = _ENV_MODEL_TO_BOARD_ID.get((env, model))
    if bid is not None:
        return bid
    if env == "arduino":
        return "arduino_uno_r3"
    return None
