"""
Library view — manage Arduino libraries installed via arduino-cli.

Layout:
    ┌──────────────────────────────────────────────────────────────┐
    │  Library                                                     │
    │  Platform: [Arduino] [ESP32 (grayed out, coming soon)]       │
    │  ┌ 🔍 Search a library to install… ──────────────────────┐  │
    │  └───────────────────────────────────────────────────────┘  │
    │  ──────────────────────────────────────────────────────────  │
    │  Installed libraries (5)                                     │
    │  ┌ card ──────────────────────────────────────────────────┐  │
    │  │ Adafruit GFX Library          v1.11.9   [Uninstall]    │  │
    │  │ by Adafruit                                            │  │
    │  │ Common library for graphics primitives.                │  │
    │  └────────────────────────────────────────────────────────┘  │
    └──────────────────────────────────────────────────────────────┘

When the user types in the search bar, the list of installed libraries
is replaced by the results of `arduino-cli lib search`. The search is
triggered automatically 350 ms after the last keystroke (debounce).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from PyQt6.QtCore import Qt, QSize, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QSizePolicy, QMessageBox, QMenu,
)

from .theme import (
    ColorScheme, theme_manager, install_icon_hover, selection_bg, input_qss,
    filter_pill_qss, icon_button_qss, primary_button_qss,
)
from .board_manager import COMING_SOON_ENVS
from .i18n import lang_manager, Strings
from .message_box import ask_yes_no
from . import icons as IC
from .workspace import workspace_manager
from .board_manager import board_manager
from .arduino_cli import is_available as cli_is_available, arduino_cli_path
from .subprocess_flags import NO_CONSOLE


SEARCH_DEBOUNCE_MS = 350
SEARCH_MIN_CHARS   = 2

# Color of the "stack of books" icon before the name — deep indigo
# used as an accent in the rest of the UI.
LIBRARY_ICON_COLOR = "#4338ca"


def _reveal_folder(path: str) -> None:
    """Open the folder in the native file explorer."""
    if not path:
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


# One FQBN per env_id — used only to obtain the right arduino-cli.yaml
# (workspace_manager.cli_config derives the env from the prefix).
_ENV_FQBN: dict[str, str] = {
    "arduino": "arduino:avr:uno",
    "esp32":   "esp32:esp32:esp32",
}

# ESP32 = grayed out "coming soon" ; STM32 / Raspberry Pi removed.
_PLATFORM_ORDER: list[str] = ["arduino", "esp32"]


def _platform_label(env: str) -> str:
    s = lang_manager.current
    return {
        "arduino": s.library_platform_arduino,
        "esp32":   s.library_platform_esp32,
    }.get(env, env)


def _resolve(cmd: list[str]) -> list[str]:
    """Replace 'arduino-cli' with its absolute path if found outside PATH."""
    if cmd and cmd[0] == "arduino-cli":
        path = arduino_cli_path()
        if path:
            return [path, *cmd[1:]]
    return cmd


def _run_json(cmd: list[str], timeout: int = 60) -> tuple[int, dict | list, str]:
    """Run arduino-cli and parse JSON. Returns (rc, data, stderr)."""
    try:
        result = subprocess.run(
            _resolve(cmd),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            creationflags=NO_CONSOLE,
        )
    except subprocess.TimeoutExpired:
        return -1, {}, "timeout"
    except FileNotFoundError:
        return -1, {}, "arduino-cli not found"
    out = result.stdout.strip()
    err = result.stderr.strip()
    if not out:
        return result.returncode, {}, err
    try:
        return result.returncode, json.loads(out), err
    except json.JSONDecodeError:
        return result.returncode, {}, err or out


# ─────────────────────────────────────────────────────────────────────────────
#  Workers (threads)
# ─────────────────────────────────────────────────────────────────────────────
class _ListLibsWorker(QThread):
    """List the libraries installed in the workspace of the given env."""

    done = pyqtSignal(list)   # list[dict] with name, version, author, sentence

    def __init__(self, env: str, parent=None):
        super().__init__(parent)
        self._env = env

    def run(self):
        fqbn = _ENV_FQBN.get(self._env, _ENV_FQBN["arduino"])
        cfg = workspace_manager.cli_config(fqbn)
        rc, data, _ = _run_json([
            "arduino-cli", "lib", "list",
            "--config-file", cfg,
            "--format", "json",
        ])
        items: list[dict] = []
        if rc == 0 and isinstance(data, dict):
            for it in data.get("installed_libraries", []) or []:
                lib = it.get("library", {}) or {}
                items.append({
                    "name":     lib.get("real_name") or lib.get("name") or "",
                    "version":  lib.get("version") or "",
                    "author":   lib.get("author") or "",
                    "sentence": lib.get("sentence") or "",
                    "install_dir": lib.get("install_dir") or "",
                })
        items.sort(key=lambda d: d["name"].lower())
        self.done.emit(items)


class _SearchLibsWorker(QThread):
    """Search for libraries in the registry via arduino-cli."""

    done = pyqtSignal(int, list)   # (request_id, list[dict])

    def __init__(self, env: str, query: str, request_id: int, parent=None):
        super().__init__(parent)
        self._env   = env
        self._query = query
        self._req   = request_id

    def run(self):
        fqbn = _ENV_FQBN.get(self._env, _ENV_FQBN["arduino"])
        cfg = workspace_manager.cli_config(fqbn)
        rc, data, _ = _run_json([
            "arduino-cli", "lib", "search",
            "--config-file", cfg,
            "--format", "json",
            self._query,
        ])
        items: list[dict] = []
        if rc == 0 and isinstance(data, dict):
            for lib in data.get("libraries", []) or []:
                latest = lib.get("latest", {}) or {}
                items.append({
                    "name":     lib.get("name") or "",
                    "version":  latest.get("version") or "",
                    "author":   latest.get("author") or "",
                    "sentence": latest.get("sentence") or "",
                })
        # Sort: approximate relevance — exact match first, then prefix,
        # then alphabetical order. arduino-cli does not provide a score.
        q = self._query.lower()
        def _key(d: dict) -> tuple[int, str]:
            n = d["name"].lower()
            if n == q:
                return (0, n)
            if n.startswith(q):
                return (1, n)
            return (2, n)
        items.sort(key=_key)
        self.done.emit(self._req, items)


class _InstallLibWorker(QThread):
    """Install a library. Returns (ok, message)."""

    done = pyqtSignal(str, bool, str)   # (name, ok, error_message)

    def __init__(self, env: str, name: str, parent=None):
        super().__init__(parent)
        self._env  = env
        self._name = name

    def run(self):
        fqbn = _ENV_FQBN.get(self._env, _ENV_FQBN["arduino"])
        cfg = workspace_manager.cli_config(fqbn)
        try:
            r = subprocess.run(
                _resolve([
                    "arduino-cli", "lib", "install",
                    "--config-file", cfg,
                    self._name,
                ]),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=180,
                creationflags=NO_CONSOLE,
            )
        except subprocess.TimeoutExpired:
            self.done.emit(self._name, False, "timeout")
            return
        except FileNotFoundError:
            self.done.emit(self._name, False, "arduino-cli not found")
            return
        if r.returncode == 0:
            self.done.emit(self._name, True, "")
        else:
            err = (r.stderr or r.stdout or "").strip()
            self.done.emit(self._name, False, err)


class _UninstallLibWorker(QThread):
    """Uninstall a library. arduino-cli deletes the folder on disk."""

    done = pyqtSignal(str, bool, str)   # (name, ok, error_message)

    def __init__(self, env: str, name: str, parent=None):
        super().__init__(parent)
        self._env  = env
        self._name = name

    def run(self):
        fqbn = _ENV_FQBN.get(self._env, _ENV_FQBN["arduino"])
        cfg = workspace_manager.cli_config(fqbn)
        try:
            r = subprocess.run(
                _resolve([
                    "arduino-cli", "lib", "uninstall",
                    "--config-file", cfg,
                    self._name,
                ]),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=60,
                creationflags=NO_CONSOLE,
            )
        except subprocess.TimeoutExpired:
            self.done.emit(self._name, False, "timeout")
            return
        except FileNotFoundError:
            self.done.emit(self._name, False, "arduino-cli not found")
            return
        if r.returncode == 0:
            self.done.emit(self._name, True, "")
        else:
            err = (r.stderr or r.stdout or "").strip()
            self.done.emit(self._name, False, err)


# ─────────────────────────────────────────────────────────────────────────────
#  Platform filter button (segmented control)
# ─────────────────────────────────────────────────────────────────────────────
class _PlatformButton(QPushButton):
    def __init__(self, text: str, parent=None, coming_soon: bool = False):
        super().__init__(text, parent)
        self._coming_soon = coming_soon
        # Coming soon (ESP32): not selectable but stays ENABLED so that
        # the "Coming soon" tooltip shows on hover.
        self.setCheckable(not coming_soon)
        self.setCursor(Qt.CursorShape.PointingHandCursor if not coming_soon
                       else Qt.CursorShape.ArrowCursor)
        self.setFixedHeight(28)
        self.apply_theme(theme_manager.current)

    def apply_theme(self, c: ColorScheme):
        # Filter pill (spec §3): checked nav_active + signal_ok border ;
        # unchecked transparent + text_primary + border ; radius 4.
        if self._coming_soon:
            # Grayed out "coming soon": no green hover, not clickable.
            #
            # ⚠️ The ONLY pill still written by hand, deliberately (TODO #50):
            # `filter_pill_qss` covers checked/unchecked and stops there. This
            # state needs disabled_text ON a `border` border and NO hover rule
            # at all -- two different colors, which the helper's hover (one
            # `signal_ok` for both border and text) cannot express. And it
            # cannot be obtained by disabling the button either: the widget
            # must stay ENABLED for its "Coming soon" tooltip to show.
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {c.disabled_text};
                    border: 1px solid {c.border};
                    border-radius: 4px;
                    font-size: 9pt; font-weight: 500;
                    padding: 3px 12px;
                }}
            """)
            return
        # Checked: GREEN text too (user request) + green border.
        # Unchecked: on hover, GREEN border AND text (user request).
        self.setStyleSheet(filter_pill_qss(c, checked=self.isChecked()))


# ─────────────────────────────────────────────────────────────────────────────
#  Library card (shared by installed / search results)
# ─────────────────────────────────────────────────────────────────────────────
class _LibraryCard(QFrame):
    """Display card for a library. mode = 'installed' or 'search'."""

    install_requested   = pyqtSignal(str)   # name
    uninstall_requested = pyqtSignal(str)   # name

    def __init__(self, lib: dict, mode: str, already_installed: bool = False, parent=None):
        super().__init__(parent)
        self._lib = lib
        self._mode = mode
        self._already_installed = already_installed
        self._busy = False
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAutoFillBackground(True)
        self._build()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)

    @property
    def name(self) -> str:
        return self._lib.get("name", "")

    def set_busy(self, busy: bool):
        self._busy = busy
        s = lang_manager.current
        if self._mode == "installed":
            # ⋯ replaced by a "Suppression…" label during the operation.
            if busy:
                self._busy_label.setText(s.library_uninstalling)
                self._busy_label.setVisible(True)
                self._action_btn.setVisible(False)
            else:
                self._busy_label.setVisible(False)
                self._action_btn.setVisible(True)
            return
        # "search" mode: the button changes text and becomes disabled.
        if busy:
            self._action_btn.setText(s.library_installing)
            self._action_btn.setEnabled(False)
        else:
            self._refresh_action_label()
            self._action_btn.setEnabled(True)

    def _refresh_action_label(self):
        s = lang_manager.current
        if self._mode == "installed":
            # ⋯ button: no text, just the icon (handled in apply_theme).
            self._action_btn.setText("")
            self._action_btn.setToolTip(s.library_more_actions)
        else:
            if self._already_installed:
                self._action_btn.setText(s.library_installed_badge)
                self._action_btn.setEnabled(False)
            else:
                self._action_btn.setText(s.library_install)

    def _build(self):
        s = lang_manager.current
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        # Left column: name + meta + description
        left = QVBoxLayout()
        left.setSpacing(4)

        # Row 1: blue icon + name + version
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self._lbl_icon = QLabel()
        self._lbl_icon.setFixedSize(QSize(18, 18))
        title_row.addWidget(self._lbl_icon, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._lbl_name = QLabel(self._lib.get("name", ""))
        self._lbl_name.setStyleSheet("font-size: 11pt; font-weight: 700;")
        title_row.addWidget(self._lbl_name)

        version = self._lib.get("version", "")
        if version:
            self._lbl_version = QLabel(f"{s.library_version_prefix}{version}")
            self._lbl_version.setStyleSheet("font-size: 9pt;")
            title_row.addWidget(self._lbl_version)
        else:
            self._lbl_version = None

        title_row.addStretch()
        left.addLayout(title_row)

        # Row 2: author
        author = self._lib.get("author", "")
        if author:
            self._lbl_author = QLabel(s.library_by.format(author=author))
            self._lbl_author.setStyleSheet("font-size: 9pt;")
            left.addWidget(self._lbl_author)
        else:
            self._lbl_author = None

        # Row 3: description
        sentence = (self._lib.get("sentence") or "").strip()
        if sentence:
            self._lbl_desc = QLabel(sentence)
            self._lbl_desc.setWordWrap(True)
            self._lbl_desc.setStyleSheet("font-size: 9pt;")
            left.addWidget(self._lbl_desc)
        else:
            self._lbl_desc = None

        root.addLayout(left, stretch=1)

        # Right column: "Removing…" label (mode installed, busy)
        # + action button (⋯ for installed, Install/Installed for search)
        self._busy_label = QLabel("")
        self._busy_label.setStyleSheet("font-size: 9pt; font-style: italic;")
        self._busy_label.setVisible(False)
        root.addWidget(self._busy_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._action_btn = QPushButton()
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._mode == "installed":
            self._action_btn.setFixedSize(32, 30)
            self._action_btn.setIconSize(QSize(16, 16))
            self._action_btn.clicked.connect(self._show_menu)
            # "…" icon: gray at rest, GREEN on hover (follows the theme).
            install_icon_hover(self._action_btn, IC.MORE_HORIZONTAL, 16,
                               normal_role="text_secondary")
        else:
            self._action_btn.setFixedHeight(30)
            self._action_btn.setMinimumWidth(110)
            self._action_btn.clicked.connect(
                lambda: self.install_requested.emit(self.name)
            )
        self._refresh_action_label()
        root.addWidget(self._action_btn, alignment=Qt.AlignmentFlag.AlignTop)

    def _show_menu(self):
        s = lang_manager.current
        menu = QMenu(self)
        act_open = menu.addAction(s.library_open_folder)
        menu.addSeparator()
        act_del = menu.addAction(s.library_uninstall)
        chosen = menu.exec(
            self._action_btn.mapToGlobal(self._action_btn.rect().bottomLeft())
        )
        if chosen == act_open:
            _reveal_folder(self._lib.get("install_dir", ""))
        elif chosen == act_del:
            self.uninstall_requested.emit(self.name)

    def apply_theme(self, c: ColorScheme):
        # Card = surface (spec §3), radius 6, hover text_secondary border.
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.surface))
        self.setPalette(p)
        self.setStyleSheet(f"""
            _LibraryCard {{
                background-color: {c.surface};
                border: 1px solid {c.border};
                border-radius: 6px;
            }}
            _LibraryCard:hover {{
                border: 1px solid {c.signal_ok};
            }}
        """)
        self._lbl_icon.setPixmap(
            IC.make_icon(IC.LIBRARY, c.accent, 18).pixmap(18, 18)
        )
        self._lbl_icon.setStyleSheet("background-color: transparent;")
        self._lbl_name.setStyleSheet(
            f"color: {c.text_primary}; font-size: 11pt; font-weight: 700;"
            "background-color: transparent;"
        )
        if self._lbl_version is not None:
            self._lbl_version.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 9pt;"
                "background-color: transparent;"
            )
        if self._lbl_author is not None:
            self._lbl_author.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 9pt;"
                "background-color: transparent;"
            )
        if self._lbl_desc is not None:
            self._lbl_desc.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 9pt;"
                "background-color: transparent;"
            )
        self._busy_label.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 9pt; font-style: italic;"
            "background-color: transparent;"
        )

        if self._mode == "installed":
            # ⋯ button: background on hover ; the icon turns GREEN (handled by
            # install_icon_hover set in _build — QSS does not recolor a QIcon).
            self._action_btn.setStyleSheet(icon_button_qss(c))
        else:
            # "Installer": on hover, the background turns GREEN (user request).
            self._action_btn.setStyleSheet(
                primary_button_qss(c, font_pt=9, padding="4px 14px"))


# ─────────────────────────────────────────────────────────────────────────────
#  Main view
# ─────────────────────────────────────────────────────────────────────────────
class LibraryView(QWidget):
    """Library view — list / search / install / uninstall.

    `compact=True` adapts the layout to live inside the Settings dialog
    (smaller title, tighter margins) instead of a full-height tab.
    """

    def __init__(self, parent=None, *, compact: bool = False):
        super().__init__(parent)
        self._compact = compact
        self._title_pt = 13 if compact else 16
        # Current platform: env_id of the connected board (otherwise arduino).
        self._env: str = board_manager.env if board_manager.env in _ENV_FQBN else "arduino"
        self._installed: list[dict] = []           # cache of installed libraries
        self._installed_names: set[str] = set()
        self._search_results: list[dict] = []
        self._current_query: str = ""
        self._search_request_id: int = 0
        self._busy_names: set[str] = set()         # libs being installed/uninstalled

        # Workers (one per type at a time ; new ones replace the active one)
        self._list_worker:    _ListLibsWorker | None    = None
        self._search_worker:  _SearchLibsWorker | None  = None
        self._install_worker:   _InstallLibWorker | None    = None
        self._uninstall_worker: _UninstallLibWorker | None  = None

        self._build()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

        # Search debounce
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._fire_search)

        # The view lives in a QStackedWidget: its closeEvent never fires.
        # We wait for the workers to finish via aboutToQuit to avoid a segfault
        # when Qt destroys the view while a QThread is still running.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_workers)

        self._refresh_installed()

    def _stop_workers(self):
        for w in (self._list_worker, self._search_worker,
                  self._install_worker, self._uninstall_worker):
            if w is not None and w.isRunning():
                w.requestInterruption()
                w.wait(2000)

    # ── Construction ─────────────────────────────────────────────
    def _build(self):
        s = lang_manager.current
        root = QVBoxLayout(self)
        if self._compact:
            root.setContentsMargins(24, 16, 24, 16)
            root.setSpacing(10)
        else:
            root.setContentsMargins(24, 20, 24, 20)
            root.setSpacing(12)

        # ── Title ────────────────────────────────────────────────
        self._lbl_title = QLabel(s.library_title)
        self._lbl_title.setStyleSheet(f"font-size: {self._title_pt}pt; font-weight: 700;")
        root.addWidget(self._lbl_title)

        # ── "arduino-cli introuvable" banner (visible if absent) ─
        self._cli_banner = QLabel(s.library_no_cli)
        self._cli_banner.setWordWrap(True)
        self._cli_banner.setVisible(not cli_is_available())
        root.addWidget(self._cli_banner)

        # ── Platform selector ────────────────────────────────────
        plat_row = QHBoxLayout()
        plat_row.setSpacing(6)
        self._lbl_platform = QLabel(s.library_platform_label)
        self._lbl_platform.setStyleSheet("font-size: 10pt; font-weight: 600;")
        plat_row.addWidget(self._lbl_platform)
        plat_row.addSpacing(4)

        self._platform_btns: dict[str, _PlatformButton] = {}
        for env in _PLATFORM_ORDER:
            soon = env in COMING_SOON_ENVS
            btn = _PlatformButton(_platform_label(env), coming_soon=soon)
            if soon:
                btn.setToolTip(lang_manager.current.board_coming_soon)
            else:
                btn.setChecked(env == self._env)
                btn.clicked.connect(lambda _, e=env: self._on_platform_changed(e))
            plat_row.addWidget(btn)
            self._platform_btns[env] = btn
        plat_row.addStretch()
        root.addLayout(plat_row)

        # ── Search bar ───────────────────────────────────────────
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(s.library_search_placeholder)
        self._search_edit.setFixedHeight(34)
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        root.addWidget(self._search_edit)

        # ── Status / Section header ──────────────────────────────
        self._lbl_section = QLabel("")
        self._lbl_section.setStyleSheet("font-size: 11pt; font-weight: 600;")
        root.addWidget(self._lbl_section)

        # ── Scroll area + cards container ────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._list_host = QWidget()
        self._list_host.setObjectName("libraryListHost")
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_host)
        root.addWidget(self._scroll, stretch=1)

        # ── Empty / status state (within the list) ───────────────
        self._lbl_empty = QLabel("")
        self._lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_empty.setWordWrap(True)
        self._lbl_empty.setVisible(False)
        self._list_layout.insertWidget(0, self._lbl_empty)

    # ── Public API ───────────────────────────────────────────────
    def refresh(self):
        """Refresh the list of installed libraries (useful from outside)."""
        self._refresh_installed()

    def _suppress_parent_autoclose(self, on: bool):
        """When embedded in the Settings dialog (which auto-closes when it loses
        activation), a modal QMessageBox would steal activation and close the
        dialog underneath it. Toggle the host's `_suppress_close` guard around
        such message boxes (no-op when used as a full tab). Mirrors the
        QFileDialog guard in settings_dialog._StoragePage."""
        w = self.window()
        if hasattr(w, "_suppress_close"):
            w._suppress_close = on

    # ── Slots / interaction ──────────────────────────────────────
    def _on_platform_changed(self, env: str):
        if env == self._env:
            # Re-click on the active pill: keep it checked
            btn = self._platform_btns.get(env)
            if btn:
                btn.setChecked(True)
                btn.apply_theme(theme_manager.current)
            return
        self._env = env
        for k, b in self._platform_btns.items():
            b.setChecked(k == env)
            b.apply_theme(theme_manager.current)
        self._busy_names.clear()
        self._refresh_installed()
        # If a search is in progress, relaunch it for the new platform.
        if self._current_query:
            self._fire_search()

    def _on_search_text_changed(self, text: str):
        q = text.strip()
        self._current_query = q
        if not q:
            # Re-display the installed libraries without waiting
            self._search_timer.stop()
            self._render_installed()
            return
        if len(q) < SEARCH_MIN_CHARS:
            self._search_timer.stop()
            return
        # Debounce: restart the timer on each keystroke.
        self._search_timer.start()

    def _fire_search(self):
        q = self._current_query
        if not q or len(q) < SEARCH_MIN_CHARS:
            return
        if not cli_is_available():
            return
        self._search_request_id += 1
        s = lang_manager.current
        self._render_status(s.library_searching)
        # Stop the current worker if still active (the event loop will finish it).
        if self._search_worker is not None and self._search_worker.isRunning():
            self._search_worker.requestInterruption()
        self._search_worker = _SearchLibsWorker(self._env, q, self._search_request_id, self)
        self._search_worker.done.connect(self._on_search_done)
        self._search_worker.start()

    def _on_search_done(self, request_id: int, items: list):
        # Stale result: the user has already typed something else.
        if request_id != self._search_request_id:
            return
        self._search_results = items
        self._render_search()

    def _refresh_installed(self):
        if not cli_is_available():
            self._installed = []
            self._installed_names = set()
            self._render_installed()
            return
        s = lang_manager.current
        self._render_status(s.library_loading)
        if self._list_worker is not None and self._list_worker.isRunning():
            self._list_worker.requestInterruption()
        self._list_worker = _ListLibsWorker(self._env, self)
        self._list_worker.done.connect(self._on_list_done)
        self._list_worker.start()

    def _on_list_done(self, items: list):
        self._installed = items
        self._installed_names = {it["name"] for it in items}
        # If the search is active, refresh the results display
        # (to update the "Installed" badges). Otherwise, list installed libraries.
        if self._current_query:
            self._render_search()
        else:
            self._render_installed()

    # ── Rendering ────────────────────────────────────────────────
    def _clear_cards(self):
        # Remove everything except the final stretch and the "empty" label
        for i in reversed(range(self._list_layout.count())):
            item = self._list_layout.itemAt(i)
            w = item.widget()
            if w is None:
                continue
            if w is self._lbl_empty:
                continue
            self._list_layout.takeAt(i)
            w.deleteLater()

    def _render_status(self, message: str):
        """Clear the list and show a centered message (loading / search)."""
        self._clear_cards()
        self._lbl_section.setVisible(False)
        self._lbl_empty.setText(message)
        self._lbl_empty.setVisible(True)

    def _render_installed(self):
        s = lang_manager.current
        self._clear_cards()
        self._lbl_section.setVisible(True)
        self._lbl_section.setText(
            f"{s.library_installed_section}  ·  "
            f"{s.library_installed_count.format(n=len(self._installed))}"
        )
        if not self._installed:
            self._lbl_empty.setText(
                s.library_installed_empty.format(platform=_platform_label(self._env))
                + "\n"
                + s.library_installed_empty_hint
            )
            self._lbl_empty.setVisible(True)
            return
        self._lbl_empty.setVisible(False)
        # Insert the cards before the stretch (which is in the last position).
        for lib in self._installed:
            card = _LibraryCard(lib, mode="installed")
            card.uninstall_requested.connect(self._on_uninstall_requested)
            if lib["name"] in self._busy_names:
                card.set_busy(True)
            insert_at = self._list_layout.count() - 1
            self._list_layout.insertWidget(insert_at, card)

    def _render_search(self):
        s = lang_manager.current
        self._clear_cards()
        self._lbl_section.setVisible(True)
        self._lbl_section.setText(s.library_search_section)
        if not self._search_results:
            self._lbl_empty.setText(
                s.library_search_no_results.format(query=self._current_query)
            )
            self._lbl_empty.setVisible(True)
            return
        self._lbl_empty.setVisible(False)
        for lib in self._search_results:
            already = lib["name"] in self._installed_names
            card = _LibraryCard(lib, mode="search", already_installed=already)
            card.install_requested.connect(self._on_install_requested)
            if lib["name"] in self._busy_names:
                card.set_busy(True)
            insert_at = self._list_layout.count() - 1
            self._list_layout.insertWidget(insert_at, card)

    # ── Install / Uninstall ──────────────────────────────────────
    def _find_card(self, name: str) -> _LibraryCard | None:
        for i in range(self._list_layout.count()):
            w = self._list_layout.itemAt(i).widget()
            if isinstance(w, _LibraryCard) and w.name == name:
                return w
        return None

    def _on_install_requested(self, name: str):
        if not name or name in self._busy_names:
            return
        self._busy_names.add(name)
        card = self._find_card(name)
        if card is not None:
            card.set_busy(True)
        self._install_worker = _InstallLibWorker(self._env, name, self)
        self._install_worker.done.connect(self._on_install_done)
        self._install_worker.start()

    def _on_install_done(self, name: str, ok: bool, error: str):
        self._busy_names.discard(name)
        if not ok:
            s = lang_manager.current
            self._suppress_parent_autoclose(True)
            try:
                QMessageBox.warning(
                    self, s.library_install_error_title,
                    s.library_install_error_msg.format(name=name, error=error or "?"),
                )
            finally:
                self._suppress_parent_autoclose(False)
            card = self._find_card(name)
            if card is not None:
                card.set_busy(False)
            return
        # Success: reload the installed list (will update the badges).
        self._refresh_installed()

    def _on_uninstall_requested(self, name: str):
        if not name or name in self._busy_names:
            return
        s = lang_manager.current
        self._suppress_parent_autoclose(True)
        try:
            ans = ask_yes_no(self, s.library_delete_confirm_title,
                             s.library_delete_confirm_msg.format(name=name))
        finally:
            self._suppress_parent_autoclose(False)
        if not ans:
            return
        self._busy_names.add(name)
        card = self._find_card(name)
        if card is not None:
            card.set_busy(True)
        self._uninstall_worker = _UninstallLibWorker(self._env, name, self)
        self._uninstall_worker.done.connect(self._on_uninstall_done)
        self._uninstall_worker.start()

    def _on_uninstall_done(self, name: str, ok: bool, error: str):
        self._busy_names.discard(name)
        if not ok:
            s = lang_manager.current
            self._suppress_parent_autoclose(True)
            try:
                QMessageBox.warning(
                    self, s.library_uninstall_error_title,
                    s.library_uninstall_error_msg.format(name=name, error=error or "?"),
                )
            finally:
                self._suppress_parent_autoclose(False)
            card = self._find_card(name)
            if card is not None:
                card.set_busy(False)
            return
        self._refresh_installed()

    # ── i18n / theme ─────────────────────────────────────────────
    def apply_lang(self, s: Strings):
        self._lbl_title.setText(s.library_title)
        self._cli_banner.setText(s.library_no_cli)
        self._lbl_platform.setText(s.library_platform_label)
        self._search_edit.setPlaceholderText(s.library_search_placeholder)
        for env, btn in self._platform_btns.items():
            btn.setText(_platform_label(env))
            btn.apply_theme(theme_manager.current)
            # Same oversight as in board_view / projects_view (3rd occurrence):
            # the "Coming soon" (ESP32) tooltip was set AT CONSTRUCTION only,
            # so it stayed frozen in the language of the first paint.
            if getattr(btn, "_coming_soon", False):
                btn.setToolTip(s.board_coming_soon)
        # Re-render to reflect the section / button labels.
        if self._current_query:
            self._render_search()
        else:
            self._render_installed()

    def apply_theme(self, c: ColorScheme):
        self.setObjectName("libraryView")
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        self.setPalette(p)
        self.setAutoFillBackground(True)
        self.setStyleSheet(f"QWidget#libraryView {{ background-color: {c.main_bg}; }}")

        self._lbl_title.setStyleSheet(
            f"color: {c.text_primary}; font-size: {self._title_pt}pt; font-weight: 700;"
        )
        self._cli_banner.setStyleSheet(f"""
            QLabel {{
                background-color: {c.nav_hover_bg};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 10pt;
            }}
        """)
        self._lbl_platform.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt; font-weight: 600;"
        )
        for btn in self._platform_btns.values():
            btn.apply_theme(c)

        self._search_edit.setStyleSheet(input_qss(c, padding="4px 10px"))

        self._lbl_section.setStyleSheet(
            f"color: {c.text_primary}; font-size: 11pt; font-weight: 600;"
        )
        self._lbl_empty.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt; padding: 24px;"
        )

        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self._list_host.setStyleSheet(
            f"QWidget#libraryListHost {{ background: {c.main_bg}; }}"
        )
        vp = self._scroll.viewport()
        vp_p = vp.palette()
        vp_p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        vp_p.setColor(QPalette.ColorRole.Base,   QColor(c.main_bg))
        vp.setPalette(vp_p)
        vp.setBackgroundRole(QPalette.ColorRole.Window)
        vp.setAutoFillBackground(True)
