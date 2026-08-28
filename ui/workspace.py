"""
PromptuinoUI workspace manager.

Structure created in ~/Documents/PromptuinoUI_projects/ :
  Arduino/
    libraries/   ← arduino-cli installs the libraries here
    projects/    ← saved .ino files
  ESP32/   (coming soon)
    libraries/
    projects/

Each platform has an arduino-cli.yaml file that redirects
directories.user to its subfolder, thereby isolating the libraries.
"""
import subprocess
from pathlib import Path

from .session import session

# env_id → displayed folder name
_ENV_DIRS: dict[str, str] = {
    "arduino": "Arduino",
    "esp32":   "ESP32",
}


def fqbn_to_env(fqbn: str) -> str:
    """Infers the env_id from the FQBN prefix."""
    f = fqbn.lower()
    if f.startswith("esp32:"):
        return "esp32"
    return "arduino"   # fallback (only Arduino is supported; ESP32 coming soon)


class WorkspaceManager:
    """
    Creates and manages the workspace folder structure.

    Usage:
        from .workspace import workspace_manager
        path = workspace_manager.libraries_path("arduino")
        cfg  = workspace_manager.cli_config(fqbn)
    """

    def __init__(self):
        # On the very first launch, the user has not yet chosen
        # a folder: we create nothing until the welcome dialog has
        # confirmed. The workspace_root_changed signal (emitted by the
        # welcome dialog or the Settings page) will trigger creation.
        if session.is_workspace_root_configured():
            self._ensure_structure()
        session.workspace_root_changed.connect(self._on_root_changed)

    def _on_root_changed(self, _new_path: str):
        self._ensure_structure()

    # ── Folder creation ──────────────────────────────────

    def _ensure_structure(self):
        root = session.workspace_root
        for platform_dir in _ENV_DIRS.values():
            for subdir in ("libraries", "projects"):
                (root / platform_dir / subdir).mkdir(
                    parents=True, exist_ok=True
                )

    # ── Paths ───────────────────────────────────────────────

    @property
    def root(self) -> Path:
        return session.workspace_root

    def platform_dir(self, env: str) -> Path:
        return session.workspace_root / _ENV_DIRS.get(env, "Arduino")

    def libraries_path(self, env: str) -> Path:
        return self.platform_dir(env) / "libraries"

    def projects_path(self, env: str) -> Path:
        return self.platform_dir(env) / "projects"

    # ── Config arduino-cli ────────────────────────────────────

    def _config_path(self, env: str) -> Path:
        return self.platform_dir(env) / "arduino-cli.yaml"

    @staticmethod
    def _get_data_dir() -> str:
        """Reads directories.data from the current arduino-cli config."""
        try:
            from .arduino_cli import arduino_cli_path
            cli = arduino_cli_path() or "arduino-cli"
            r = subprocess.run(
                [cli, "config", "get", "directories.data"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
        return ""

    def _ensure_cli_config(self, env: str) -> Path:
        """
        Generates the arduino-cli config file for the given environment.
        Copies directories.data from the system config (preserves the
        library index and the cores) and redirects directories.user to
        our workspace to isolate the libraries per platform.
        """
        cfg_path = self._config_path(env)
        user_dir = self.platform_dir(env)
        data_dir = self._get_data_dir()

        lines = ["directories:"]
        if data_dir:
            lines.append(f'  data: "{Path(data_dir).as_posix()}"')
        lines.append(f'  user: "{user_dir.as_posix()}"')

        cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return cfg_path

    def cli_config(self, fqbn: str) -> str:
        """
        Returns the path (str) of the arduino-cli config file
        corresponding to the given FQBN.  Creates the file if needed.
        """
        env = fqbn_to_env(fqbn)
        return str(self._ensure_cli_config(env))


# Global instance
workspace_manager = WorkspaceManager()
