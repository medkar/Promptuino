"""
User project management.

Disk tree:
    ~/Documents/Promptuino/projets/
        Arduino/projects/<nom>/<nom>.ino
        Arduino/projects/<nom>/<nom>.promptuino.json
        Esp32/projects/...   (coming soon)

A project = a folder containing a .ino (Arduino IDE convention) and
a .promptuino.json for the metadata (name, mode, board, prompt, etc.).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from ui.generation.feature_model import Feature, serialize_features, deserialize_features


class ProjectType(str, Enum):
    ARDUINO = "arduino"
    ESP32   = "esp32"   # "coming soon" (greyed out in the UI)


TYPE_DIR_NAMES: dict[ProjectType, str] = {
    ProjectType.ARDUINO: "Arduino",
    ProjectType.ESP32:   "Esp32",
}

TYPE_LABELS: dict[ProjectType, str] = {
    ProjectType.ARDUINO: "Arduino",
    ProjectType.ESP32:   "ESP32",
}


def projects_root() -> Path:
    # The root is driven by the session (Parametres -> Stockage).
    # By default: ~/Documents/Promptuino/projets.
    from .session import session
    return session.workspace_root


def type_dir(t: ProjectType) -> Path:
    return projects_root() / TYPE_DIR_NAMES[t] / "projects"


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


# Characters allowed in a project name: letters/digits/_/-/space.
# Compatible with the Arduino IDE convention (folder name == .ino name).
_NAME_RE = re.compile(r"^[A-Za-z0-9_\-() ]+$")


def is_name_valid(name: str) -> bool:
    n = (name or "").strip()
    return bool(n) and bool(_NAME_RE.match(n)) and len(n) <= 80


def code_hash(code: str) -> str:
    """SHA-256 of the code. Used to detect an edit of the .ino outside Promptuino."""
    return hashlib.sha256((code or "").encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
#  Function (= logical block added by the AI, tracked in the side panel)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Export:
    """Public variable exposed by a Function to the other functions.

    Declared by the AI at generation time via a dedicated marker block.
    `name` must be a valid C identifier; `type` follows the Arduino
    convention (bool, int, float, long, byte, String, etc.); `doc` is a
    short natural-language description injected into the consumers'
    prompts so that the AI understands the meaning of the variable.
    """
    name: str
    type: str = ""
    doc:  str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type, "doc": self.doc}

    @classmethod
    def from_dict(cls, d: dict) -> "Export":
        return cls(
            name=str(d.get("name", "")),
            type=str(d.get("type", "")),
            doc=str(d.get("doc", "")),
        )


@dataclass
class Function:
    """A block of code attributed to an AI prompt and displayed in the Studio side panel.

    The lines are 0-indexed (aligned on the QTextDocument blocks).
    `prompts` keeps the history: [prompt_initial, prompt_regen_1, …] —
    the last element is the active prompt.
    `exports` declares the public variables exposed to the other functions
    (filled by the AI via the marker protocol).
    `name` is an optional label chosen by the user; empty =
    "Fonctionnalité N" display derived from the id.
    """
    id:         str
    prompts:    list[str] = field(default_factory=list)
    model_used: str       = ""
    lines:      list[int] = field(default_factory=list)
    color:      str       = ""
    created_at: str       = ""
    exports:    list[Export] = field(default_factory=list)
    name:       str       = ""

    @property
    def current_prompt(self) -> str:
        return self.prompts[-1] if self.prompts else ""

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "prompts":    list(self.prompts),
            "model_used": self.model_used,
            "lines":      list(self.lines),
            "color":      self.color,
            "created_at": self.created_at,
            "exports":    [e.to_dict() for e in self.exports],
            "name":       self.name,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Function":
        return cls(
            id         = str(d.get("id", "")),
            prompts    = [str(p) for p in d.get("prompts", [])],
            model_used = str(d.get("model_used", "")),
            lines      = [int(x) for x in d.get("lines", [])],
            color      = str(d.get("color", "")),
            created_at = str(d.get("created_at", "")),
            exports    = [Export.from_dict(e) for e in d.get("exports", [])],
            name       = str(d.get("name", "")),
        )


def next_function_id(functions: list[Function]) -> str:
    """Returns the next 'fN' id based on the existing ids."""
    max_n = 0
    for f in functions:
        if f.id.startswith("f"):
            try:
                n = int(f.id[1:])
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return f"f{max_n + 1}"


def merge_functions(functions: list[Function], ids_to_merge: list[str]
                    ) -> list[Function]:
    """Merges several `Function` into one (new list returned).

    The resulting function:
      - keeps the fid, the color and created_at of the FIRST function
        of `ids_to_merge` that appears in `functions` (« primary »),
      - concatenates the `prompts` histories and adds a new element
        « merged: <p1> + <p2> + ... » bringing together the active prompts,
      - merges the `exports`, deduplicating by `name`,
      - merges the `lines` (sorted union),
      - resets the custom `name` (falls back to the auto display),
      - takes the `model_used` of the last merged one.

    The other functions are removed. The order of the returned list
    respects the order of the original `functions`: the merged function
    takes the place of « primary ».

    Raises ValueError if fewer than 2 valid ids are provided.
    """
    by_id = {f.id: f for f in functions}
    to_merge = [by_id[fid] for fid in ids_to_merge if fid in by_id]
    if len(to_merge) < 2:
        raise ValueError("merge_functions requires at least 2 valid ids")

    # Primary = the one that appears earliest in `functions` among
    # the requested ids. Guarantees a stable identity even if the order of
    # `ids_to_merge` does not follow the project order.
    merge_ids = {f.id for f in to_merge}
    primary = next(f for f in functions if f.id in merge_ids)

    # Reorder to_merge so that `primary` is at the head (the rest follows
    # in the project order).
    ordered = [primary] + [f for f in functions if f.id in merge_ids and f.id != primary.id]

    concat_prompts: list[str] = []
    for fn in ordered:
        concat_prompts.extend(fn.prompts)
    current_prompts = [fn.current_prompt for fn in ordered if fn.current_prompt]
    if current_prompts:
        concat_prompts.append("merged: " + " + ".join(current_prompts))

    seen_names: set[str] = set()
    merged_exports: list[Export] = []
    for fn in ordered:
        for e in fn.exports:
            if e.name not in seen_names:
                seen_names.add(e.name)
                merged_exports.append(e)

    merged_lines = sorted({ln for fn in ordered for ln in fn.lines})

    merged = Function(
        id         = primary.id,
        prompts    = concat_prompts,
        model_used = ordered[-1].model_used,
        lines      = merged_lines,
        color      = primary.color,
        created_at = primary.created_at,
        exports    = merged_exports,
        name       = "",
    )

    # Rebuild the list: replace primary with merged, remove
    # the other merged ids.
    out: list[Function] = []
    for fn in functions:
        if fn.id == primary.id:
            out.append(merged)
        elif fn.id in merge_ids:
            continue
        else:
            out.append(fn)
    return out


@dataclass
class Project:
    path: Path
    name: str
    type: ProjectType
    mode: str = "beginner"
    board_env: str = ""
    board_model: str = ""
    last_prompt: str = ""
    ai_backend: str = ""
    created_at: str = ""
    updated_at: str = ""
    functions: list[Function] = field(default_factory=list)
    code_hash: str = ""  # hash of the .ino at the time of the last save
    comment_verbosity: int = 2  # 0 None / 1 Minimal / 2 Standard / 3 Detailed
    serial_monitor: bool = True  # include Serial.begin + Serial.println (advanced mode)
    # .md/.txt file injected as context into the AI prompts. Stores the path
    # relative to the project folder (just the filename) to stay portable;
    # empty if no context. The file itself lives in the project folder.
    context_file_path: str = ""
    # Resolutions of the ambiguous wiring components (cf StudioView). Key
    # stored as a string "fn_id|pin_net" (JSON-compatible). Value: the chosen
    # type_id (led/buzzer/dc_motor/module_generic). For dc_motor, a 2nd
    # entry with the suffix "::_driver" stores the driver type (l298n, etc.).
    wiring_resolutions: dict[str, str] = field(default_factory=dict)
    # State of the implicit actions of the Level 3 interactive schematic (cf
    # ui/wiring/implicit_actions.py). String key "fn_id|pin_net|action_id".
    # Value: bool for the toggles (servo external_power, BTN/DHT pullup),
    # str for the selectors (LED series R in ohms "220"/"330"/..., buzzer
    # series R "none"/"100"/"220"). JSON-native for persistence.
    wiring_implicit_actions: dict[str, object] = field(default_factory=dict)
    # MVP chat history (Feature 1). Each entry:
    # {"role": "user"|"assistant", "content": str, "ts": ISO8601 str}.
    # Persisted as-is in .promptuino.json. On load, the caller pushes
    # this list into ChatController.load_history().
    chat_history: list[dict] = field(default_factory=list)
    # Features generated by the feature->code engine (generation overhaul).
    # Empty for projects created before the overhaul (transparent migration).
    features: list[Feature] = field(default_factory=list)
    # Features livrees dans la fenetre "stable" (mode avance 2 fenetres).
    # Miroir de `features` pour le code stable ; vide pour les projets anterieurs.
    stable_features: list[Feature] = field(default_factory=list)
    # Code de la fenetre "stable" (mode avance 2 fenetres) : edite a la
    # main, jamais touche par l'IA. Vide pour les projets anterieurs.
    stable_code: str = ""

    @property
    def ino_path(self) -> Path:
        return self.path / f"{self.name}.ino"

    @property
    def meta_path(self) -> Path:
        return self.path / f"{self.name}.promptuino.json"

    def to_dict(self) -> dict:
        return {
            "path":        str(self.path),
            "name":        self.name,
            "type":        self.type.value,
            "mode":        self.mode,
            "board_env":   self.board_env,
            "board_model": self.board_model,
            "last_prompt": self.last_prompt,
            "ai_backend":  self.ai_backend,
            "created_at":  self.created_at,
            "updated_at":  self.updated_at,
            "functions":   [f.to_dict() for f in self.functions],
            "code_hash":   self.code_hash,
            "comment_verbosity": self.comment_verbosity,
            "serial_monitor": self.serial_monitor,
            "context_file_path": self.context_file_path,
            "wiring_resolutions": dict(self.wiring_resolutions),
            "wiring_implicit_actions": dict(self.wiring_implicit_actions),
            "chat_history": list(self.chat_history),
            "features":        serialize_features(self.features),
            "stable_features": serialize_features(self.stable_features),
            "stable_code":     self.stable_code,
        }

    @classmethod
    def from_dict(cls, d: dict, path: Path, fallback_type: ProjectType) -> "Project":
        raw_type = d.get("type") or fallback_type.value
        try:
            t = ProjectType(raw_type)
        except ValueError:
            t = fallback_type
        functions = [Function.from_dict(f) for f in d.get("functions", [])]
        features = deserialize_features(d.get("features", []))
        stable_features = deserialize_features(d.get("stable_features", []))
        return cls(
            path        = path,
            name        = d.get("name", path.name),
            type        = t,
            mode        = d.get("mode", "beginner"),
            board_env   = d.get("board_env", ""),
            board_model = d.get("board_model", ""),
            last_prompt = d.get("last_prompt", ""),
            ai_backend  = d.get("ai_backend", ""),
            created_at  = d.get("created_at", ""),
            updated_at  = d.get("updated_at", ""),
            functions       = functions,
            features        = features,
            stable_features = stable_features,
            code_hash       = d.get("code_hash", ""),
            comment_verbosity = int(d.get("comment_verbosity", 2)),
            serial_monitor = bool(d.get("serial_monitor", True)),
            context_file_path = str(d.get("context_file_path", "")),
            wiring_resolutions = {
                str(k): str(v)
                for k, v in (d.get("wiring_resolutions") or {}).items()
            },
            wiring_implicit_actions = {
                str(k): v
                for k, v in (d.get("wiring_implicit_actions") or {}).items()
                if isinstance(v, (bool, str, int, float))
            },
            chat_history = [
                e for e in (d.get("chat_history") or [])
                if isinstance(e, dict)
            ],
            stable_code = str(d.get("stable_code", "")),
        )


class ProjectManager:
    """Disk I/O layer for projects. Stateless — instantiated once."""

    # ── Init / setup ──────────────────────────────────────────────

    def ensure_dirs(self) -> None:
        for t in ProjectType:
            type_dir(t).mkdir(parents=True, exist_ok=True)

    # ── Listing / loading ─────────────────────────────────────────

    def list_projects(self, type_filter: ProjectType | None = None) -> list[Project]:
        self.ensure_dirs()
        types = [type_filter] if type_filter else list(ProjectType)
        result: list[Project] = []
        for t in types:
            base = type_dir(t)
            if not base.exists():
                continue
            for folder in sorted(base.iterdir(), key=lambda p: p.name.lower()):
                if not folder.is_dir():
                    continue
                proj = self._load_folder(folder, t)
                if proj is not None:
                    result.append(proj)
        # Global sort by descending modification date, then by name
        result.sort(key=lambda p: (p.updated_at or "", p.name.lower()), reverse=True)
        return result

    def _load_folder(self, folder: Path, expected_type: ProjectType) -> Project | None:
        """Loads a project folder. Returns None if it does not contain a .ino."""
        ino_files = list(folder.glob("*.ino"))
        if not ino_files:
            return None
        # We first look for a .promptuino.json (any one)
        meta_files = list(folder.glob("*.promptuino.json"))
        if meta_files:
            try:
                data = json.loads(meta_files[0].read_text(encoding="utf-8"))
                proj = Project.from_dict(data, folder, expected_type)
                # If the folder name was renamed by hand outside the app,
                # we resynchronize the "name" field on the folder name.
                if proj.name != folder.name:
                    proj.name = folder.name
                return proj
            except Exception:
                pass
        # No metadata: project created manually or corrupted meta.
        return Project(
            path       = folder,
            name       = folder.name,
            type       = expected_type,
            mode       = "beginner",
            created_at = _now_iso(),
            updated_at = _now_iso(),
        )

    def load_code(self, project: Project) -> str:
        try:
            return project.ino_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # Fallback: first .ino found in the folder
            for f in project.path.glob("*.ino"):
                try:
                    return f.read_text(encoding="utf-8")
                except Exception:
                    continue
            return ""

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def unique_name(base: str, parent_dir: Path,
                    exclude: Path | None = None) -> str:
        """Returns an available project name in parent_dir.

        If `base` is free (or matches the `exclude` folder), returns
        `base` as-is. Otherwise appends a suffix `(1)`, `(2)`, … until
        finding an available name. `exclude` allows ignoring the folder
        of the project being renamed (so as not to find itself in
        collision with itself).
        """
        base = (base or "").strip()
        excl_resolved = exclude.resolve() if exclude is not None else None

        def _taken(path: Path) -> bool:
            if not path.exists():
                return False
            if excl_resolved is not None and path.resolve() == excl_resolved:
                return False
            return True

        if not _taken(parent_dir / base):
            return base
        i = 1
        while True:
            candidate = f"{base}({i})"
            if not _taken(parent_dir / candidate):
                return candidate
            i += 1

    # ── Mutations ─────────────────────────────────────────────────

    def create(self, name: str, ptype: ProjectType, *,
               initial_code: str = "") -> Project:
        name = (name or "").strip()
        if not is_name_valid(name):
            raise ValueError(f"Nom de projet invalide : '{name}'")
        base = type_dir(ptype)
        base.mkdir(parents=True, exist_ok=True)
        folder = base / name
        if folder.exists():
            raise FileExistsError(f"Un projet nommé « {name} » existe déjà.")
        folder.mkdir()
        now = _now_iso()
        proj = Project(
            path       = folder,
            name       = name,
            type       = ptype,
            created_at = now,
            updated_at = now,
        )
        proj.ino_path.write_text(initial_code, encoding="utf-8")
        self._write_meta(proj)
        return proj

    def save(self, project: Project, *, code: str,
             mode: str | None = None,
             board_env: str | None = None,
             board_model: str | None = None,
             last_prompt: str | None = None,
             ai_backend: str | None = None,
             functions: list[Function] | None = None,
             features: list[Feature] | None = None,
             stable_features: list[Feature] | None = None,
             context_file_path: str | None = None,
             wiring_resolutions: dict[str, str] | None = None,
             wiring_implicit_actions: dict[str, object] | None = None,
             stable_code: str | None = None) -> Project:
        """Writes the .ino and updates the provided metadata.

        The code hash is recomputed on every save to allow the next load
        to detect an edit outside Promptuino.
        """
        if mode is not None:        project.mode        = mode
        if board_env is not None:   project.board_env   = board_env
        if board_model is not None: project.board_model = board_model
        if last_prompt is not None: project.last_prompt = last_prompt
        if ai_backend is not None:  project.ai_backend  = ai_backend
        if functions is not None:   project.functions   = functions
        if features is not None:         project.features         = list(features)
        if stable_features is not None:  project.stable_features  = list(stable_features)
        if context_file_path is not None: project.context_file_path = context_file_path
        if wiring_resolutions is not None: project.wiring_resolutions = dict(wiring_resolutions)
        if wiring_implicit_actions is not None: project.wiring_implicit_actions = dict(wiring_implicit_actions)
        if stable_code is not None: project.stable_code = stable_code
        project.code_hash  = code_hash(code)
        project.updated_at = _now_iso()
        project.path.mkdir(parents=True, exist_ok=True)
        project.ino_path.write_text(code, encoding="utf-8")
        self._write_meta(project)
        return project

    # ── Code / function integrity ────────────────────────────────

    def code_matches_hash(self, project: Project, code: str) -> bool:
        """True if the provided code matches the hash recorded in the JSON.

        For a project without a hash (old format), we return True — no
        retroactive degradation.
        """
        if not project.code_hash:
            return True
        return code_hash(code) == project.code_hash

    @staticmethod
    def strip_function_lines(project: Project) -> None:
        """Degraded mode: clears the line ranges of each function.

        To be called when the .ino has been modified outside Promptuino. The cards
        remain displayable (id, prompts, model), only the highlighting and the
        targeted deletion are lost — regeneration remains possible.
        """
        for f in project.functions:
            f.lines = []

    def rename(self, project: Project, new_name: str) -> Project:
        new_name = (new_name or "").strip()
        if not is_name_valid(new_name):
            raise ValueError(f"Nom invalide : '{new_name}'")
        if new_name == project.name:
            return project
        new_folder = project.path.parent / new_name
        if new_folder.exists():
            raise FileExistsError(f"Un projet nommé « {new_name} » existe déjà.")
        old_name = project.name
        # 1) Rename the folder
        project.path.rename(new_folder)
        project.path = new_folder
        # 2) Rename the main .ino if its stem matches the old name
        old_ino = new_folder / f"{old_name}.ino"
        new_ino = new_folder / f"{new_name}.ino"
        if old_ino.exists() and old_ino != new_ino:
            old_ino.rename(new_ino)
        # 3) Delete all the old metadata, we write a fresh one
        for f in new_folder.glob("*.promptuino.json"):
            try: f.unlink()
            except Exception: pass
        project.name = new_name
        project.updated_at = _now_iso()
        self._write_meta(project)
        return project

    def duplicate(self, project: Project) -> Project:
        base = f"{project.name} (copie)"
        name = base
        i = 2
        parent = project.path.parent
        while (parent / name).exists():
            name = f"{base} {i}"
            i += 1
        new_folder = parent / name
        shutil.copytree(project.path, new_folder)
        # Clean up the files with the old name in the new folder
        for f in new_folder.glob("*.ino"):
            target = new_folder / f"{name}.ino"
            if f != target:
                if target.exists():
                    try: f.unlink()
                    except Exception: pass
                else:
                    f.rename(target)
        for f in new_folder.glob("*.promptuino.json"):
            try: f.unlink()
            except Exception: pass
        now = _now_iso()
        # EXACT copy: round-trip the WHOLE metadata (functions, features, chat
        # history, wiring resolutions + implicit actions, context file, board,
        # etc.) and override only the identity/timestamps. Rebuilding from a
        # hand-picked subset of fields silently dropped features/chat/wiring on
        # every duplicate — this stays correct for any future Project field too.
        # The .ino and the context file are already copied by copytree above.
        data = project.to_dict()
        data["name"]       = name
        data["created_at"] = now
        data["updated_at"] = now
        new_proj = Project.from_dict(data, new_folder, project.type)
        self._write_meta(new_proj)
        return new_proj

    def delete(self, project: Project) -> None:
        if project.path.exists():
            shutil.rmtree(project.path)

    # ── Internals ──────────────────────────────────────────────────

    def _write_meta(self, project: Project) -> None:
        project.path.mkdir(parents=True, exist_ok=True)
        project.meta_path.write_text(
            json.dumps(project.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# Shared instance — to import from the other modules
project_manager = ProjectManager()
