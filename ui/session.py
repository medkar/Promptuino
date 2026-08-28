"""Persistent session state (excluding AI config).

Stores:
 - the path of the last opened project to restore it on restart,
 - the workspace root (folder for projects and libraries).

File: ~/Documents/Promptuino/data/session.json
"""
import json
import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal


# Les deux emplacements sont decides dans `ui/paths.py` (qui migre aussi
# les donnees de l'ancienne arborescence a plat). Les constantes restent
# ICI : les tests les detournent une par une.
from .paths import DATA_DIR, DEFAULT_WORKSPACE
_SESSION_PATH = DATA_DIR / "session.json"
_DEFAULT_WORKSPACE_ROOT = DEFAULT_WORKSPACE


class Session(QObject):
    """Lightweight persistence (atomic JSON read/write on each setter)."""

    workspace_root_changed = pyqtSignal(str)  # new absolute path

    def __init__(self):
        super().__init__()
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            if _SESSION_PATH.exists():
                self._data = json.loads(_SESSION_PATH.read_text(encoding="utf-8"))
        except Exception:
            # Corrupt/truncated file (e.g. an unclean shutdown predating the
            # atomic write below). Set it aside for forensics instead of
            # silently discarding, then start fresh.
            self._data = {}
            try:
                _SESSION_PATH.replace(_SESSION_PATH.with_suffix(".json.corrupt"))
            except Exception:
                pass

    def _save(self) -> None:
        """Persist atomically: write a temp file in the same folder, flush it
        to disk, then os.replace() it over the target. A crash or power loss
        therefore leaves either the complete previous file or the complete new
        one — never a truncated file that would read back empty on the next
        launch (which would replay the first-launch wizard + tutorial)."""
        try:
            _SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(self._data, indent=2, ensure_ascii=False)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(_SESSION_PATH.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(text)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_name, _SESSION_PATH)
            finally:
                if os.path.exists(tmp_name):
                    try:
                        os.remove(tmp_name)
                    except OSError:
                        pass
        except Exception:
            pass

    # ── Last opened project ────────────────────────────────────

    @property
    def last_project_path(self) -> str:
        return self._data.get("last_project_path", "") or ""

    @last_project_path.setter
    def last_project_path(self, value: str) -> None:
        self._data["last_project_path"] = value or ""
        self._save()

    # ── Workspace root ─────────────────────────────────────────

    @staticmethod
    def default_workspace_root() -> Path:
        return _DEFAULT_WORKSPACE_ROOT

    @property
    def workspace_root(self) -> Path:
        """Root folder used for projects and libraries.

        Default: ~/Documents/Promptuino/projets. The user can
        change it via the Settings window."""
        stored = self._data.get("workspace_root", "") or ""
        return Path(stored) if stored else _DEFAULT_WORKSPACE_ROOT

    @workspace_root.setter
    def workspace_root(self, value) -> None:
        if not value:
            new = ""  # empty string = reset to the default value
        else:
            new = str(Path(value).expanduser().resolve())
        key_present = "workspace_root" in self._data
        current = self._data.get("workspace_root", "") or ""
        # If the key already exists with the same value: no-op.
        # Otherwise we write (this notably happens on first startup when
        # the default path is "confirmed" to mark it as configured).
        if key_present and new == current:
            return
        self._data["workspace_root"] = new
        self._save()
        self.workspace_root_changed.emit(str(self.workspace_root))

    def is_workspace_root_default(self) -> bool:
        return not (self._data.get("workspace_root", "") or "")

    def is_workspace_root_configured(self) -> bool:
        """True if the user has already chosen (or confirmed) a folder.

        Allows triggering the first-launch wizard only
        while the key is not present in session.json."""
        return "workspace_root" in self._data

    # ── "Don't ask me again" preferences ───────────────────────

    @property
    def skip_wrong_component_confirm(self) -> bool:
        """True if the user checked "don't ask me again" on the confirmation
        popup of the "this isn't the right component" safety net (the click
        then opens the chat directly, without confirmation)."""
        return bool(self._data.get("skip_wrong_component_confirm", False))

    @skip_wrong_component_confirm.setter
    def skip_wrong_component_confirm(self, value: bool) -> None:
        self._data["skip_wrong_component_confirm"] = bool(value)
        self._save()

    # ── « Coulisses du prompt » (#42) ──────────────────────────

    @property
    def prompt_backstage(self) -> bool:
        """True when every generation first shows the prompt for validation.

        Persisted, unlike the developer toggle it replaces. That toggle lived
        in the Help menu and deliberately reset on every launch because it was
        a dev feature; the justification went away with the name."""
        return bool(self._data.get("prompt_backstage", False))

    @prompt_backstage.setter
    def prompt_backstage(self, value: bool) -> None:
        self._data["prompt_backstage"] = bool(value)
        self._save()

    # Les trois proprietes `telemetry_*` ont ete RETIREES le 2026-08-28
    # (TODO #72). Aucune migration n'est necessaire : ce magasin garde un
    # dict brut, lit en `.get(cle, defaut)` et reecrit le dict ENTIER --
    # les cles inconnues d'une session existante sont ignorees a la
    # lecture et preservees a l'ecriture.

    # ── Layout state: collapsed chat (Phase 3) ─────────────────

    @property
    def chat_collapsed(self) -> bool:
        """True if the chat panel is collapsed (48px strip). Restored on
        startup. We store this UI state in the same session.json as the
        rest (the app only has one prefs mechanism)."""
        return bool(self._data.get("chat_collapsed", False))

    @chat_collapsed.setter
    def chat_collapsed(self, value: bool) -> None:
        if bool(value) == self._data.get("chat_collapsed", False):
            return
        self._data["chat_collapsed"] = bool(value)
        self._save()

    # ── Layout state: collapsed sidebar (Phase 3) ──────────────

    @property
    def sidebar_collapsed(self) -> bool:
        """True if the sidebar is collapsed (52px). Restored on startup."""
        return bool(self._data.get("sidebar_collapsed", False))

    @sidebar_collapsed.setter
    def sidebar_collapsed(self, value: bool) -> None:
        if bool(value) == self._data.get("sidebar_collapsed", False):
            return
        self._data["sidebar_collapsed"] = bool(value)
        self._save()

    # ── Theme preference (light / dark) ────────────────────────

    @property
    def theme_is_dark(self) -> bool:
        """App theme: True = dark (default), False = light. Restored on
        startup (cf. main.py) and saved on every toggle."""
        return bool(self._data.get("theme_is_dark", True))

    @theme_is_dark.setter
    def theme_is_dark(self, value: bool) -> None:
        if bool(value) == self._data.get("theme_is_dark", True):
            return
        self._data["theme_is_dark"] = bool(value)
        self._save()

    # ── Language preference (fr / en / es / it) ────────────────

    @property
    def language(self) -> str:
        """App language, restored on startup and saved on every change (same
        mechanism as `theme_is_dark`, and for the same reason: both are
        APP-wide preferences, not project state).

        It was the only one of the two that survived nothing: the theme has
        been persisted since 2026-06-24, the language never was, so a user
        reading Spanish had to pick it again at every launch. Default "fr"
        matches LanguageManager's own default.
        """
        value = self._data.get("language", "fr")
        return value if isinstance(value, str) and value else "fr"

    @language.setter
    def language(self, value: str) -> None:
        code = (value or "").strip()
        # Written straight through without validating the code against the
        # translation table: session.py knows nothing of i18n and must keep it
        # that way. The reader (main.py) hands it to `set_language`, which
        # already ignores anything it does not know -- so a hand-edited or
        # stale file degrades to the default instead of raising.
        if not code or code == self._data.get("language", "fr"):
            return
        self._data["language"] = code
        self._save()

    # ── Welcome tutorial (seen once per mode) ──────────────────
    # The coachmark tutorial triggers on the 1st launch (beginner mode) and on
    # the 1st visit to each mode (new elements). These flags remember that it
    # has already been shown so it isn't replayed every time (manually
    # re-triggerable via Help » Replay the tutorial).

    def tutorial_seen(self, mode: str) -> bool:
        """True if the tutorial for the given mode has already been shown."""
        return bool(self._data.get(f"tutorial_seen_{mode}", False))

    def set_tutorial_seen(self, mode: str, value: bool = True) -> None:
        key = f"tutorial_seen_{mode}"
        if bool(value) == self._data.get(key, False):
            return
        self._data[key] = bool(value)
        self._save()

    # ── Progression nudges (compteurs + drapeaux APP-WIDE) ─────
    # Persistés dans session.json (état global de l'app), JAMAIS par projet :
    # un compteur cumule à travers tous les projets, et un nudge montré une
    # fois ne se rejoue plus, y compris sur un nouveau projet.

    def progress_count(self, key: str) -> int:
        """Compteur cumulatif app-wide pour `key` (0 si absent)."""
        return int(self._data.get(f"progress_count_{key}", 0))

    def bump_progress_count(self, key: str) -> int:
        """Incrémente le compteur `key`, persiste, et retourne la nouvelle valeur."""
        n = self.progress_count(key) + 1
        self._data[f"progress_count_{key}"] = n
        self._save()
        return n

    def nudge_seen(self, key: str) -> bool:
        """True si le nudge `key` a déjà été montré (app-wide)."""
        return bool(self._data.get(f"nudge_seen_{key}", False))

    def mark_nudge_seen(self, key: str) -> None:
        """Marque le nudge `key` comme montré (idempotent)."""
        if self._data.get(f"nudge_seen_{key}", False):
            return
        self._data[f"nudge_seen_{key}"] = True
        self._save()

    def nudge_shown(self, key: str) -> int | None:
        """Nombre d'affichages du nudge RÉPÉTÉ `key`, ou None si la session est
        antérieure à ce compteur (cf. `progress_nudge.showings_so_far`, qui
        sait le reconstruire — ici on se contente de dire qu'on ne sait pas)."""
        v = self._data.get(f"nudge_shown_{key}")
        return int(v) if isinstance(v, int) else None

    def set_nudge_shown(self, key: str, n: int) -> None:
        """Fixe le nombre d'affichages du nudge `key`.

        Un setter plutôt qu'un incrément : l'appelant vient de RECONSTRUIRE ce
        compte pour les sessions antérieures (`showings_so_far`), et
        incrémenter depuis un compteur absent le ramènerait à 1 en effaçant
        cette reconstruction."""
        self._data[f"nudge_shown_{key}"] = int(n)
        self._save()


session = Session()
