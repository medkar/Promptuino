"""
Interface with arduino-cli for compilation and upload.

Workflow:
  0. Detect the #include <...> from the code → attempt arduino-cli lib install
  1. Create a temporary sketch  (<tmpdir>/sketch/sketch.ino)
  2. Compile  : arduino-cli compile --fqbn <fqbn> <sketch_dir>
     → if library error : natural message, no AI loop
     → if code error    : AI loop (max MAX_FIX_ATTEMPTS)
  3. Upload   : arduino-cli upload  --fqbn <fqbn> --port <port> <sketch_dir>
  4. Clean up the temporary directory
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

from PyQt6.QtCore import QThread, pyqtSignal

from .board_manager import board_manager, get_fqbn, _KNOWN_DEVICES
from .i18n import lang_manager
from .workspace import workspace_manager, fqbn_to_env

# Mapping language code → English name for the AI prompts
_LANG_NAMES: dict[str, str] = {
    "fr": "French",
    "en": "English",
    "es": "Spanish",
    "it": "Italian",
}

# ── ANSI cleanup ──────────────────────────────────────────────────────────────

# Standard ESC sequences (\x1b[...X) AND bare sequences ([digits;m) that arduino-cli
# can produce on some Windows terminals.
_ANSI_RE = re.compile(r'(?:\x1b\[[0-9;]*[A-Za-z]|\[[0-9;]+[mGKHF])')


def _strip_ansi(text: str) -> str:
    """Strip ANSI/VT100 color codes from a string."""
    return _ANSI_RE.sub('', text)


# ── Cores (platforms) ─────────────────────────────────────────────────────────

def _core_id_from_fqbn(fqbn: str) -> str:
    """`arduino:avr:uno` → `arduino:avr`. Empty if FQBN is malformed."""
    parts = fqbn.split(":")
    return ":".join(parts[:2]) if len(parts) >= 2 else ""


def _core_installed(core_id: str, config_file: str) -> bool:
    """True if the `vendor:arch` platform is already installed."""
    import json as _json
    ret, out = _run([
        'arduino-cli', 'core', 'list',
        '--config-file', config_file,
        '--format', 'json',
    ])
    if ret != 0 or not out:
        return False
    try:
        data = _json.loads(out)
        platforms = data.get('platforms', data) if isinstance(data, dict) else data
        for p in platforms or []:
            if p.get('id') == core_id:
                return True
    except Exception:
        pass
    return False


def _install_core(core_id: str, config_file: str) -> tuple[bool, str]:
    """Install the platform. Update the index first (in case it is
    empty on a fresh install). Returns (ok, output)."""
    _run(['arduino-cli', 'core', 'update-index', '--config-file', config_file])
    ret, out = _run([
        'arduino-cli', 'core', 'install',
        '--config-file', config_file,
        core_id,
    ])
    return ret == 0, out


# ── Library detection ─────────────────────────────────────────────────────────

_INCLUDE_RE = re.compile(r'^\s*#include\s*<([^>]+)>', re.MULTILINE)

# Built-in headers — no need to install them
_BUILTIN_HEADERS = {
    'Arduino.h', 'HardwareSerial.h', 'SoftwareSerial.h',
    'Stream.h', 'Print.h', 'WString.h', 'Printable.h',
    'Wire.h', 'SPI.h', 'I2S.h', 'EEPROM.h',
    'Ethernet.h', 'WiFi.h', 'WiFiClient.h', 'WiFiServer.h',
    'SD.h', 'FS.h', 'SPIFFS.h', 'LittleFS.h',
    'Stepper.h', 'LiquidCrystal.h',
    'stdlib.h', 'string.h', 'math.h', 'stdint.h', 'stdbool.h',
    'stdio.h', 'ctype.h', 'limits.h', 'stddef.h',
    'avr/io.h', 'avr/interrupt.h', 'avr/pgmspace.h',
    'util/delay.h', 'util/twi.h',
}

# Namespace prefixes that are always built-in
_BUILTIN_PREFIXES = ('avr/', 'util/', 'sys/', 'linux/', 'windows/')


# Extensions d'en-tete C/C++ rencontrees dans les libs Arduino. `.hpp` n'est pas
# exotique : c'est celle d'IRremote v4, et le corpus la fournit au modele a
# raison. Elle n'etait traitee NULLE PART (QA K1, 2026-08-10) -- l'en-tete
# partait tel quel comme nom de lib (« IRremote.hpp »), la recherche au registre
# ne trouvait rien, la lib n'etait jamais installee, et l'echec de compilation
# n'etait meme pas reconnu comme « librairie manquante ».
_HEADER_SUFFIXES = (".hpp", ".hh", ".h")


def _header_stem(header: str) -> str:
    """« IRremote.hpp » -> « IRremote ». Rendu tel quel s'il n'a pas d'extension
    connue -- mieux vaut chercher un nom bizarre que rien du tout."""
    for suffix in _HEADER_SUFFIXES:
        if header.endswith(suffix):
            return header[:-len(suffix)]
    return header


def _extract_unknown_libs(code: str) -> list[str]:
    """
    Returns the HEADER FILE names of the third-party libraries to install
    (deduplicated, ordered). Excludes the headers built into the platform.

    Le header, PAS un nom de librairie : les deux different (« Adafruit
    MCP23017 Arduino Library » fournit « Adafruit_MCP23X17.h ») et seul le
    header identifie le fournisseur dans `provides_includes`. L'appelant en
    derive ce dont il a besoin (`_header_stem` pour chercher,
    `lib_by_header.lib_name_for_header` pour le vrai nom).
    """
    seen: set[str] = set()
    result: list[str] = []
    for header in _INCLUDE_RE.findall(code):
        if header in _BUILTIN_HEADERS:
            continue
        if any(header.startswith(p) for p in _BUILTIN_PREFIXES):
            continue
        if header not in seen:
            seen.add(header)
            result.append(header)
    return result


def _installed_libs(config_file: str) -> dict[str, dict]:
    """
    Returns {registry_name: {'headers': [...], 'install_dir': '...'}}
    for all libraries installed in the workspace.
    """
    import json as _json
    ret, out = _run([
        'arduino-cli', 'lib', 'list',
        '--config-file', config_file,
        '--format', 'json',
    ])
    if ret != 0 or not out:
        return {}
    try:
        data = _json.loads(out)
        return {
            item['library']['name']: {
                'headers':     item['library'].get('provides_includes') or [],
                'install_dir': item['library'].get('install_dir', ''),
            }
            for item in data.get('installed_libraries', [])
        }
    except Exception:
        return {}


def _read_depends(install_dir: str) -> list[str]:
    """
    Reads library.properties and returns the list of direct dependencies.
    Handles version constraints: "Adafruit BusIO (>=1.0)" → "Adafruit BusIO".
    """
    from pathlib import Path
    props = Path(install_dir) / 'library.properties'
    if not props.exists():
        return []
    try:
        for line in props.read_text(encoding='utf-8', errors='replace').splitlines():
            if line.startswith('depends='):
                raw = line[len('depends='):].strip()
                if not raw:
                    return []
                return [d.split('(')[0].strip() for d in raw.split(',') if d.strip()]
    except Exception:
        pass
    return []


def _transitive_keep(provider: str, libs: dict[str, dict]) -> set[str]:
    """
    Returns the provider + all its transitive dependencies
    (BFS over library.properties/depends).
    """
    keep: set[str] = set()
    queue = [provider]
    while queue:
        lib = queue.pop()
        if lib in keep:
            continue
        keep.add(lib)
        if lib in libs:
            for dep in _read_depends(libs[lib]['install_dir']):
                if dep not in keep:
                    queue.append(dep)
    return keep


def _search_queries(name: str, known_lib: str | None) -> list[str]:
    """Search terms to try, in order, for the library providing `<name>.h`.

    The REAL registry name first when a store knows it (`lib_by_header`), the
    header stem second. Keeping the stem is not belt-and-braces: it covers the
    majority of libraries (`Servo.h` -> "Servo") AND rescues the case where a
    stored name has gone stale (a renamed library would otherwise now fail
    where it used to work).

    Pure, so the ordering can be tested without arduino-cli.
    """
    out: list[str] = []
    for q in (known_lib, name.replace('_', ' ')):
        q = (q or '').strip()
        if q and q not in out:
            out.append(q)
    return out


def _search_candidates(query: str, config_file: str) -> list[str]:
    """Library names returned by 'lib search --names <query>' ([] on failure)."""
    ret, out = _run([
        'arduino-cli', 'lib', 'search',
        '--config-file', config_file,
        '--names', query,
    ])
    candidates: list[str] = []
    if ret == 0 and out:
        for line in out.splitlines():
            candidate = line.strip().removeprefix('Name:').strip().strip('"')
            if candidate:
                candidates.append(candidate)
    return candidates


def _try_install_lib(name: str, config_file: str,
                     known_lib: str | None = None,
                     header_file: str | None = None) -> bool:
    """
    For each candidate returned by 'lib search <query>':
      1. Snapshot of installed libs
      2. Install the candidate (+ automatic dependencies)
      3. Diff → new libs
      4. Identify the provider via 'provides_includes'
      5. Compute provider + transitive dependencies (library.properties/depends)
         → to keep
      6. Uninstall everything else (e.g. DotStarMatrix, DotStar)
      7. If no new lib provides the header → uninstall everything,
         try the next candidate

    `name` stays the HEADER STEM: it is what identifies the provider at step 4,
    and it must not be replaced by the library name. `known_lib` only widens the
    SEARCH (see `_search_queries`) -- the verification stays "does this library
    provide <name>.h", so a wrong stored name can never install the wrong lib.

    `header_file` est l'en-tete REEL vu dans le `#include` : c'est lui que
    `provides_includes` liste, et il ne se devine pas depuis `name` (IRremote
    fournit `IRremote.hpp`, pas `IRremote.h`). Repli sur `<name>.h` pour les
    appelants qui ne l'ont pas.

    Returns True if a lib providing that header was installed.
    """
    header_file = header_file or f"{name}.h"

    # If an already-installed lib provides this header, nothing to do
    current = _installed_libs(config_file)
    if any(header_file in info['headers'] for info in current.values()):
        return True

    tried: set[str] = set()
    for query in _search_queries(name, known_lib):
        for candidate in _search_candidates(query, config_file):
            if candidate in tried:
                continue
            tried.add(candidate)
            before = _installed_libs(config_file)

            ret, _ = _run([
                'arduino-cli', 'lib', 'install',
                '--config-file', config_file,
                candidate,
            ])
            if ret != 0:
                continue

            after = _installed_libs(config_file)
            new_libs = {n: info for n, info in after.items() if n not in before}

            # Find the lib that provides the header
            provider = next(
                (n for n, info in new_libs.items()
                 if header_file in info['headers']),
                None,
            )

            if provider:
                # Keep provider + its transitive dependencies, uninstall the rest
                keep = _transitive_keep(provider, after)
                for lib_name in new_libs:
                    if lib_name not in keep:
                        _run(['arduino-cli', 'lib', 'uninstall',
                              '--config-file', config_file, lib_name])
                return True

            # No new lib provides the header → uninstall everything
            for lib_name in new_libs:
                _run(['arduino-cli', 'lib', 'uninstall',
                      '--config-file', config_file, lib_name])

    return False


# ── Error classification ──────────────────────────────────────────────────────

# `.hpp` / `.hh` acceptees en plus de `.h` : sans elles, un `#include
# <IRremote.hpp>` manquant n'etait meme pas RECONNU comme une librairie
# absente, et l'utilisateur recevait une erreur de compilation brute au lieu du
# message qui nomme la lib a installer (QA K1, 2026-08-10).
_MISSING_LIB_RE = re.compile(
    r'fatal error:\s*([^\s:]+\.h(?:pp|h)?)\s*:\s*[Nn]o such file or directory'
)


def _detect_missing_lib(error: str) -> str | None:
    """
    Returns the name of the missing .h file if the error is a missing library,
    otherwise None.
    """
    m = _MISSING_LIB_RE.search(error)
    return m.group(1) if m else None


def _classify_upload_error(error: str) -> str:
    """
    Returns a key describing the cause of the upload failure:
      'port_busy'   — port held by another app (IDE Serial Monitor, etc.)
      'port'        — port not found (board unplugged, wrong port number)
      'no_response' — board not responding (bootloader, Reset needed)
      'timeout'     — timed out
      ''            — unknown error
    """
    low = error.lower()
    # Priority: access denied → port held by another application
    if any(p in low for p in (
        'access is denied', 'permission denied',
        'device or resource busy', 'resource busy',
    )):
        return 'port_busy'
    if any(p in low for p in (
        'ser_open', "can't open", 'cannot open', 'no such file', 'port not found',
    )):
        return 'port'
    if any(p in low for p in (
        'not in sync', 'programmer is not responding',
        'stk500', 'invalid device signature', 'device signature',
        'no device found', 'could not find',
    )):
        return 'no_response'
    if 'timeout' in low:
        return 'timeout'
    return ''


# ── Repair anchored on the error lines ────────────────────────────────────────
# The compiler reports the line of the problem (`sketch.ino:12:3: error: …`). So
# we do NOT need the model to locate the edit (which it does poorly): we
# extract a small window around the line, the model corrects ONLY those
# lines, and we splice them back in. The rest of the file is untouched by construction.

from .ai_backends.base import _repair_acceptable   # anti-gutting guard
from .code_format import insert_missing_brace      # deterministic brace insertion

_ERROR_LINE_RE = re.compile(r':(\d+)(?::\d+)?:\s*error', re.IGNORECASE)
_REPAIR_WINDOW_RADIUS = 2     # context lines on either side of the error
_MAX_REPAIR_WINDOWS = 4       # bounds the number of model calls per attempt


def _repair_debug(start: int, end: int, errors: str,
                  region: str, corrected: str) -> None:
    """OPTIONAL trace (env variable `PROMPTUINO_REPAIR_DEBUG`) of each
    targeted repair: error + window sent + raw model response.
    Lets you SEE what the repairer receives/returns without polluting the UI.
    Writes to `%TEMP%/promptuino_repair_debug.log` (or the provided path)."""
    path = os.environ.get("PROMPTUINO_REPAIR_DEBUG")
    if not path:
        return
    if path == "1":
        path = os.path.join(tempfile.gettempdir(), "promptuino_repair_debug.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n===== région lignes {start}-{end} =====\n")
            f.write(f"--- erreur ---\n{errors}\n")
            f.write(f"--- envoyé ---\n{region}\n")
            f.write(f"--- reçu ---\n{corrected}\n")
    except Exception:
        pass


def _repair_debug_note(msg: str) -> None:
    """Free-form trace line in the same log as `_repair_debug` (opt-in)."""
    path = os.environ.get("PROMPTUINO_REPAIR_DEBUG")
    if not path:
        return
    if path == "1":
        path = os.path.join(tempfile.gettempdir(), "promptuino_repair_debug.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n>>> {msg}\n")
    except Exception:
        pass


def _parse_error_lines(error_text: str) -> list[int]:
    """Line numbers (1-based) reported by the compiler, sorted/deduplicated."""
    nums = {int(m.group(1)) for m in _ERROR_LINE_RE.finditer(error_text or "")
            if int(m.group(1)) >= 1}
    return sorted(nums)


def _merge_windows(line_nos: list[int], total: int,
                   radius: int = _REPAIR_WINDOW_RADIUS) -> list[tuple[int, int]]:
    """Windows (start, end) 1-based inclusive around the error lines,
    merged if they overlap/touch, clamped to [1, total]."""
    windows: list[tuple[int, int]] = []
    for L in sorted(set(line_nos)):
        s, e = max(1, L - radius), min(total, L + radius)
        if e < s:
            continue
        if windows and s <= windows[-1][1] + 1:
            windows[-1] = (windows[-1][0], max(windows[-1][1], e))
        else:
            windows.append((s, e))
    return windows


def _strip_strings_comments(code: str) -> str:
    """Strips comments and string/char literals so as NOT to count the
    braces/parentheses they contain (e.g. `Serial.println("}")`)."""
    code = re.sub(r'//[^\n]*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r'"(?:\\.|[^"\\])*"', '', code)
    code = re.sub(r"'(?:\\.|[^'\\])*'", '', code)
    return code


def _is_structurally_balanced(code: str) -> bool:
    """True if braces and parentheses are balanced (excluding strings/comments).
    An imbalance = missing brace/parenthesis → STRUCTURAL error, often
    reported by the compiler FAR from the real cause → the targeted edit (window
    around the error line) cannot fix it; in that case we prefer the
    whole-file repair (which sees the entire structure)."""
    c = _strip_strings_comments(code)
    return c.count("{") == c.count("}") and c.count("(") == c.count(")")


_SCOPE_ERROR_RE = re.compile(r"was not declared in this scope", re.IGNORECASE)


def _is_scope_error(error_text: str) -> bool:
    """True si l'erreur est un « X was not declared in this scope ».

    C'est la signature d'un COUPLAGE entre sections (ex. deux fonctionnalités où
    la 2ᵉ référence une variable locale de la 1ʳᵉ). Le bon fix — hisser la
    déclaration au scope GLOBAL — se situe LOIN des lignes signalées (au site de
    déclaration, pas d'usage) → la réparation ciblée (fenêtre autour de la ligne
    fautive) ne peut PAS le faire et risque un re-déclaration locale (shadowing).
    On route donc droit vers la réparation fichier-entier (qui voit toute la
    structure et est guidée pour remonter la variable en global)."""
    return bool(_SCOPE_ERROR_RE.search(error_text or ""))


_SCOPE_NAME_RE = re.compile(r"'([^']+)' was not declared in this scope",
                            re.IGNORECASE)


def _scope_repair_hint(error_text: str) -> str:
    """Diagnostic DÉTERMINISTE pour une erreur de scope, injecté à la place du
    diagnostic flou du SLM. On extrait le(s) identifiant(s) fautif(s) et on donne
    la consigne exacte : déclarer en GLOBAL, supprimer la déclaration locale, ne
    PAS re-déclarer localement (le piège qui « compile mais affiche faux »). Le
    prompt de réparation est conçu pour suivre ce diagnostic ciblé."""
    names = []
    for m in _SCOPE_NAME_RE.finditer(error_text or ""):
        n = m.group(1)
        if n not in names:
            names.append(n)
    if names:
        ident = ", ".join(f"`{n}`" for n in names)
        subject = "these identifiers are" if len(names) > 1 else "this identifier is"
        them = "them" if len(names) > 1 else "it"
        they = "they are" if len(names) > 1 else "it is"
    else:
        ident = "the shared variable"
        subject = "this identifier is"
        them = "it"
        they = "it is"
    return (
        f"Scope coupling: {ident} — {subject} used in one place but only declared "
        f"LOCALLY elsewhere (inside an `if`/block or another function), so the "
        f"rest of the code cannot see {them}.\n"
        f"FIX: declare {ident} ONCE at GLOBAL scope (above setup(), with the "
        f"correct type and a sensible initial value) and REMOVE the local "
        f"declaration; just ASSIGN to {them} where {they} computed. "
        f"Do NOT re-declare {ident} locally (a second local declaration shadows "
        f"the global and keeps the value out of scope — it compiles but shows "
        f"wrong values). Change nothing else."
    )


def line_anchored_repair(code: str, error_text: str, backend,
                         language: str, board_name: str) -> str | None:
    """Repairs by giving the model only the lines reported by the
    compiler (+ context). Returns the corrected code, or None if no line
    is usable / nothing changed / the result breaks the guard — in
    those cases the caller falls back on the whole-file repair."""
    error_lines = _parse_error_lines(error_text)
    if not error_lines:
        return None
    # ⚠️ Le bloc d'API se calcule ICI, sur le code COMPLET : la fenetre
    # envoyee au modele ne contient jamais les `#include`, donc le reparateur
    # cible — le PREMIER de la chaine, celui qui traite les erreurs a ligne
    # connue comme une mauvaise arite (`motor2.forward(2000)`) — reparait a
    # l'aveugle (QA AB2 bis du #82, 2026-08-31 : « restored » pendant que
    # l'injection du fallback fichier-entier attendait un tour qui ne venait
    # pas). Calcule UNE fois, servi a chaque fenetre. Garde : une erreur du
    # RAG degrade vers l'ancien prompt, jamais vers un crash du filet.
    try:
        from .rag import api_context_for_code
        api_ctx = api_context_for_code(code)
    except Exception:
        api_ctx = ""
    code_lines = code.split("\n")
    windows = _merge_windows(error_lines, len(code_lines))[:_MAX_REPAIR_WINDOWS]
    if not windows:
        return None
    # Useful error lines only (drop the « Using library… » noise).
    err_lines = [l for l in error_text.splitlines() if "error:" in l.lower()]
    all_errs = "\n".join(err_lines) or error_text
    changed = False
    # Bottom to top: the indices of the higher windows stay valid after
    # replacing the lower windows.
    for s, e in sorted(windows, reverse=True):
        region = "\n".join(code_lines[s - 1:e])
        # Give each window ONLY the errors whose reported line falls inside it
        # (else the SLM tries to fix an error absent from its window). Fall
        # back to all errors if none maps into this window (e.g. line-less).
        win_errs = "\n".join(
            l for l in err_lines
            if any(s <= n <= e for n in _parse_error_lines(l))) or all_errs
        try:
            corrected = backend.repair_region(region, win_errs, language,
                                              board_name, api_context=api_ctx)
        except Exception:
            continue
        corrected = (corrected or "").rstrip("\n")
        _repair_debug(s, e, win_errs, region, corrected)
        if corrected and corrected != region:
            code_lines[s - 1:e] = corrected.split("\n")
            changed = True
    if not changed:
        return None
    new_code = "\n".join(code_lines)
    return new_code if _repair_acceptable(code, new_code) else None


# ── arduino-cli subcommands ───────────────────────────────────────────────────

# Known locations of arduino-cli when it is not in the PATH.
# On Windows, the official installer places the binary under "Program Files".
# In PyInstaller bundle mode, the binary is embedded next to the exe.
def _candidate_paths() -> list[str]:
    paths: list[str] = []
    exe_name = "arduino-cli.exe" if sys.platform == "win32" else "arduino-cli"
    # PyInstaller bundle mode: binary placed next to the executable
    # or in the _internal/ subfolder (PyInstaller 6.x one-folder
    # convention) or in _MEIPASS (one-file).
    # sys.frozen is True when PyInstaller has packaged the app.
    if getattr(sys, "frozen", False):
        bundle_dir = os.path.dirname(os.path.abspath(sys.executable))
        paths.append(os.path.join(bundle_dir, exe_name))
        paths.append(os.path.join(bundle_dir, "_internal", exe_name))
        paths.append(os.path.join(bundle_dir, "third_party", exe_name))
        # PyInstaller onefile: extracted into _MEIPASS
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(os.path.join(meipass, exe_name))
    if sys.platform == "win32":
        for env_var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            base = os.environ.get(env_var)
            if base:
                paths.append(os.path.join(base, "Arduino CLI", "arduino-cli.exe"))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            paths.append(os.path.join(local, "Programs", "Arduino CLI", "arduino-cli.exe"))
    else:
        paths.extend([
            "/usr/local/bin/arduino-cli",
            "/usr/bin/arduino-cli",
            "/opt/homebrew/bin/arduino-cli",
            os.path.expanduser("~/bin/arduino-cli"),
            os.path.expanduser("~/.local/bin/arduino-cli"),
        ])
    return paths


_arduino_cli_path_cache: str | None = None


def arduino_cli_path() -> str | None:
    """Returns the absolute path of arduino-cli, or None if not found.

    Checks the PATH first (shutil.which), then a few known locations
    (on Windows: "C:/Program Files/Arduino CLI/arduino-cli.exe" even if the
    folder was not added to the PATH by the installer).
    """
    global _arduino_cli_path_cache
    if _arduino_cli_path_cache and os.path.isfile(_arduino_cli_path_cache):
        return _arduino_cli_path_cache
    found = shutil.which("arduino-cli")
    if not found:
        for p in _candidate_paths():
            if os.path.isfile(p):
                found = p
                break
    _arduino_cli_path_cache = found
    return found


def is_available() -> bool:
    """Returns True if arduino-cli is found (PATH or known location)."""
    return arduino_cli_path() is not None


def _find_port_auto() -> str:
    """
    Scans the USB ports to find the one of the currently known board.
    Used when the board was detected automatically (port not stored).
    """
    try:
        from serial.tools import list_ports
        env = board_manager.env
        for p in list_ports.comports():
            if p.vid is None or p.pid is None:
                continue
            result = _KNOWN_DEVICES.get((p.vid, p.pid))
            if result and result[0] == env:
                return p.device
    except Exception:
        pass
    return ""


def _resolve_cmd(cmd: list[str]) -> list[str]:
    """Replaces 'arduino-cli' with its absolute path if found outside the PATH."""
    if cmd and cmd[0] == "arduino-cli":
        path = arduino_cli_path()
        if path:
            return [path, *cmd[1:]]
    return cmd


def _run(cmd: list[str], cwd: str | None = None, register=None) -> tuple[int, str]:
    """Runs a command, returns (return_code, cleaned stdout+stderr output).

    `register` (optional callback) receives the live `Popen` so the caller can
    kill it to cancel the operation — used by `CompileUploadWorker.cancel()` to
    abort WITHOUT `QThread.terminate()` (which crashes the app when the thread is
    mid-subprocess). `register(None)` is called once the process is done."""
    proc = subprocess.Popen(
        _resolve_cmd(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
    )
    if register is not None:
        register(proc)
    try:
        out, err = proc.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise
    finally:
        if register is not None:
            register(None)
    output = _strip_ansi((out + err).strip())
    return proc.returncode, output


# ── Worker ────────────────────────────────────────────────────────────────────

MAX_FIX_ATTEMPTS = 3   # cosmetic placeholder (core/libs/upload status)

# Number of ANALYZE→REPAIR passes before giving up and UNDOING the
# changes (revert to the original code). 2 passes: beyond that, on a local
# model, persisting rarely succeeds.
MAX_REPAIR_ATTEMPTS = 2


class CompileUploadWorker(QThread):
    """
    Compilation + upload thread.

    Steps:
      0. Automatic installation of detected third-party libraries
      1. Compilation loop (max MAX_FIX_ATTEMPTS):
           - Missing library error → translated message, immediate stop (no AI)
           - Code error            → AI fix then retry
      2. Upload

    Signals:
      status(str, int, int)  — (step, attempt, max) — steps: "libs","compile","fix","upload"
      output(str)            — arduino-cli output line
      code_updated(str)      — code corrected by the AI
      done(bool, str)        — (success, translated final message)
    """

    status       = pyqtSignal(str, int, int)
    output       = pyqtSignal(str)
    code_updated = pyqtSignal(str)
    repair_steps = pyqtSignal(list)   # list of auto-repair steps (educational)
    done         = pyqtSignal(bool, str)

    def __init__(self, code: str, fqbn: str, port: str = "",
                 backend=None, board_name: str = "Arduino",
                 verify_only: bool = False):
        super().__init__()
        self._code        = code
        self._fqbn        = fqbn
        self._port        = port
        self._backend     = backend
        self._board_name  = board_name
        self._verify_only = verify_only   # compile + réparation, SANS upload ni revert interne
        self._proc        = None     # live subprocess (compile/upload), for cancel
        self._cancelled   = False

    def _set_proc(self, proc) -> None:
        """Track the running subprocess so `cancel()` can kill it."""
        self._proc = proc

    def cancel(self) -> None:
        """Cancel by killing the current subprocess (compile/upload). Avoids
        `QThread.terminate()`, which crashes the app when the thread is blocked
        in a subprocess. `run()` sees `_cancelled` and returns without emitting
        `done` (the UI already shows « Annulé »)."""
        self._cancelled = True
        p = self._proc
        if p is not None and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    def _ensure_libs(self, code: str, cli_cfg: str, attempted: set) -> None:
        """Installs the libraries from the #include of `code` not yet attempted.
        Called at startup AND after each repair (a fix can ADD
        an #include — e.g. `Servo.h` — which must then be installed before
        recompiling, otherwise `No such file`)."""
        from .lib_by_header import lib_name_for_header
        new = [h for h in _extract_unknown_libs(code) if h not in attempted]
        if new:
            self.status.emit("libs", 0, MAX_FIX_ATTEMPTS)
        for header in new:
            attempted.add(header)
            # Le nom REEL de la librairie quand une des trois sources le
            # connait : le radical de l'en-tete ne le donne pas toujours
            # (`Adafruit_MCP23X17.h` <- « Adafruit MCP23017 Arduino Library »,
            # QA J1). Le journal montre ce qui est REELLEMENT cherche, sinon la
            # ligne « lib install » decrit une requete qui n'a pas eu lieu.
            known = lib_name_for_header(header)
            stem = _header_stem(header)
            self.output.emit(f"→ lib install {(known or stem)!r}")
            if not _try_install_lib(stem, cli_cfg, known_lib=known,
                                    header_file=header):
                self.output.emit(
                    f"ℹ '{known or stem}' introuvable dans le registre — la compilation vérifiera."
                )

    def run(self):
        tmp_dir    = None
        sketch_dir = None
        try:
            tmp_dir    = tempfile.mkdtemp(prefix="promptuino_")
            sketch_dir = os.path.join(tmp_dir, "sketch")
            os.makedirs(sketch_dir)
            ino_path   = os.path.join(sketch_dir, "sketch.ino")

            current_code = self._code
            s = lang_manager.current   # language snapshot at worker startup

            # workspace arduino-cli config (directories.data + directories.user)
            cli_cfg = workspace_manager.cli_config(self._fqbn)

            # ── Step 0a: install the core (platform) ─
            core_id = _core_id_from_fqbn(self._fqbn)
            if core_id and not _core_installed(core_id, cli_cfg):
                self.status.emit("core", 0, MAX_FIX_ATTEMPTS)
                self.output.emit(f"→ core install {core_id!r}")
                ok, install_out = _install_core(core_id, cli_cfg)
                if install_out:
                    self.output.emit(install_out)
                if not ok:
                    self.done.emit(
                        False, f"{s.studio_err_core_install} '{core_id}'"
                    )
                    return

            # ── Step 0b: install the libraries ──────────
            # `attempted_libs`: libs already attempted, reused after each
            # repair (a fix can add an #include).
            attempted_libs: set[str] = set()
            self._ensure_libs(current_code, cli_cfg, attempted_libs)

            # ── ANALYZE → REPAIR loop (revert on failure) ──
            # On a local model, ANALYZING an error is far more reliable than
            # fixing it outright. On each failure: (1) we analyze the error
            # (explain_error), (2) we repair by GIVING that analysis to the
            # repairer (targeted SEARCH/REPLACE edits). If after
            # MAX_REPAIR_ATTEMPTS passes it still does not compile, we UNDO
            # all the changes (back to the original code): better an
            # original broken code + a good diagnosis than a half-
            # butchered code that is still broken.
            original_code = current_code
            last_error = ""
            errors_history: list[str] = []
            repair_log: list[dict] = []   # fixes ACTUALLY kept
            lang_name = _LANG_NAMES.get(lang_manager.lang, "English")
            analysis = ""
            compile_ok = False

            for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
                with open(ino_path, "w", encoding="utf-8") as f:
                    f.write(current_code)

                self.status.emit("compile", attempt + 1, MAX_REPAIR_ATTEMPTS + 1)
                ret, out = _run([
                    "arduino-cli", "compile",
                    "--config-file", cli_cfg,
                    "--fqbn", self._fqbn,
                    sketch_dir,
                ], register=self._set_proc)
                if self._cancelled:
                    return
                if ret == 0:
                    if out:
                        self.output.emit(out)   # sketch size, etc.
                    compile_ok = True
                    break

                last_error = out or "Erreur de compilation."
                errors_history.append(f"Attempt {attempt + 1}:\n{last_error}")

                # Missing library → natural message, no AI loop.
                missing = _detect_missing_lib(last_error)
                if missing:
                    # Nommer la VRAIE librairie quand une source la connait :
                    # c'est cette chaine-la qu'il faut taper pour l'installer a
                    # la main. Le radical de l'en-tete, lui, peut n'exister
                    # NULLE PART au registre -- « Adafruit_MCP23X17 » y renvoie
                    # zero resultat alors que la librairie s'appelle « Adafruit
                    # MCP23017 Arduino Library » (QA J1, 2026-08-10). Le message
                    # envoyait donc l'utilisateur chercher un nom qui n'existe
                    # pas. Repli sur le radical quand rien ne la connait.
                    from .lib_by_header import lib_name_for_header
                    lib_name = (lib_name_for_header(missing)
                                or _header_stem(missing))
                    # If a fix has already been applied (e.g. an #include
                    # added), we still publish the history → the
                    # « voir les corrections » button stays accessible despite the
                    # missing lib.
                    if repair_log:
                        repair_log[-1]["final_ok"] = compile_ok   # False here
                        self.repair_steps.emit(repair_log)
                    self.done.emit(False, f"{s.studio_err_missing_lib} '{lib_name}'")
                    return

                # No backend: direct failure (neither analysis nor repair).
                if self._backend is None:
                    self.done.emit(False, last_error)
                    return

                # No more repair budget: we exit for the revert + analysis.
                if attempt == MAX_REPAIR_ATTEMPTS:
                    break

                self.status.emit("fix", attempt + 1, MAX_REPAIR_ATTEMPTS)
                code_before = current_code
                fix_summary = ""
                fixed = None

                # (A) TARGETED REPAIR: we give the model only the lines
                #     pointed to by the compiler (+ context), we splice them our-
                #     selves → the rest of the file is untouched by construction.
                #     EXCEPT a STRUCTURAL error (missing brace/parenthesis):
                #     it is reported far from its cause → the targeted window does
                #     not contain it. We then route straight to the whole
                #     file (fallback below), which sees the entire structure.
                if _is_scope_error(last_error):
                    # « X was not declared in this scope » = couplage entre
                    # sections : le fix (hisser la déclaration en global) est
                    # DISTANT des lignes signalées → la réparation ciblée ne peut
                    # pas le faire. On va droit au fichier entier (fallback B),
                    # qui est guidé pour remonter la variable en global.
                    fixed = None
                    _repair_debug_note("scope error -> whole-file (global hoist)")
                elif _is_structurally_balanced(current_code):
                    try:
                        fixed = line_anchored_repair(
                            current_code, last_error, self._backend,
                            lang_name, self._board_name,
                        )
                    except Exception as e:
                        self.done.emit(False, f"Erreur IA : {e}")
                        return
                else:
                    # Brace imbalance: if ONE `}` is missing and we can
                    # locate it via indentation, we insert it
                    # DETERMINISTICALLY (without AI). Otherwise whole-file fallback.
                    fixed = insert_missing_brace(current_code)
                    _repair_debug_note(
                        "deterministic brace insertion" if fixed is not None
                        else "structural imbalance, not locatable -> whole-file"
                    )

                # (B) FALLBACK: no usable line (linker error…) or targeted
                #     edit with no effect → WHOLE-FILE repair guided by
                #     the analysis (the local model is good at analyzing).
                if fixed is None:
                    if _is_scope_error(last_error):
                        # Diagnostic DÉTERMINISTE (pas le SLM) : précis et stable,
                        # il cible le hoist global et interdit la re-déclaration
                        # locale (cause du « compile mais affiche faux »).
                        analysis = _scope_repair_hint(last_error)
                    else:
                        self.status.emit("explain", 0, 0)
                        try:
                            analysis = self._backend.explain_error(last_error, lang_name)
                        except Exception:
                            analysis = ""
                    errors_for_repair = last_error
                    if analysis:
                        errors_for_repair = (
                            f"{last_error}\n\n"
                            f"Diagnosis (what is wrong and how to fix it):\n{analysis}"
                        )
                    try:
                        fixed, fix_summary = self._backend.repair_code(
                            current_code, errors_for_repair, lang_name,
                            self._board_name,
                        )
                    except Exception as e:
                        self.done.emit(False, f"Erreur IA : {e}")
                        return

                # Nothing changed (fallback with no effect): no point logging it.
                if not fixed or fixed == code_before:
                    continue

                current_code = fixed
                repair_log.append({
                    "index": len(repair_log) + 1,
                    "kind": "fix",
                    "error": last_error,        # raw error of THIS attempt
                    "code_before": code_before,
                    "code_after": fixed,
                    "summary": fix_summary or "",
                })
                self.code_updated.emit(current_code)
                # The fix may have ADDED an #include (e.g. Servo.h) → install
                # the corresponding lib before recompiling (otherwise « No such
                # file » and abort).
                self._ensure_libs(current_code, cli_cfg, attempted_libs)

            # Educational history: emitted as soon as at least ONE fix was
            # attempted — viewable even after revert/upload (this is what makes
            # the « voir les corrections » button reappear). final_ok = did we
            # end up compiling (so: fixes kept) or not (revert).
            _repair_debug_note(
                f"OUTCOME compile_ok={compile_ok} repair_log={len(repair_log)} "
                f"-> {'emit repair_steps' if repair_log else 'NO repair_steps'}"
            )
            if repair_log:
                repair_log[-1]["final_ok"] = compile_ok
                self.repair_steps.emit(repair_log)

            # ── Final failure: UNDO the changes + analyze ──
            if not compile_ok:
                # verify_only : c'est studio_view qui gère le revert (vers le
                # baseline PRE-génération, PAS original_code = le code qu'on vient
                # de générer). On ne revert donc PAS en interne ici.
                if not self._verify_only and current_code != original_code:
                    # Revert: do not leave a half-repaired and still
                    # broken code. We restore the editor to the code from before the loop.
                    current_code = original_code
                    self.code_updated.emit(original_code)
                # Make sure there is an analysis to show (the whole error history).
                if not analysis:
                    self.status.emit("explain", 0, 0)
                    try:
                        analysis = self._backend.explain_error(
                            "\n\n".join(errors_history), lang_name,
                        )
                    except Exception:
                        analysis = ""
                self.done.emit(False, analysis or last_error)
                return

            # verify_only : la compilation a réussi -> on livre SANS uploader.
            if self._verify_only:
                self.done.emit(True, "")
                return

            # ── Upload ─────────────────────────────────────────
            self.status.emit("upload", 0, 0)
            ret, out = _run([
                "arduino-cli", "upload",
                "--config-file", cli_cfg,
                "--fqbn", self._fqbn,
                "--port", self._port,
                sketch_dir,
            ], register=self._set_proc)
            if self._cancelled:
                return
            if out:
                self.output.emit(out)
            if ret != 0:
                err_key = _classify_upload_error(out)
                if err_key == 'port_busy':
                    msg = s.studio_err_upload_port_busy
                elif err_key == 'port':
                    msg = s.studio_err_upload_port
                elif err_key == 'no_response':
                    msg = s.studio_err_upload_no_response
                elif err_key == 'timeout':
                    msg = s.studio_err_upload_timeout
                else:
                    # Unknown error → AI explanation
                    if self._backend and self._backend.is_available():
                        self.status.emit("explain", 0, 0)
                        lang_name = _LANG_NAMES.get(lang_manager.lang, "English")
                        try:
                            msg = self._backend.explain_error(out, lang_name)
                        except Exception:
                            msg = out or "Erreur d'upload."
                    else:
                        msg = out or "Erreur d'upload."
                self.done.emit(False, msg)
                return

            self.done.emit(True, "")

        except subprocess.TimeoutExpired:
            if not self._cancelled:
                self.done.emit(False, "Délai dépassé (arduino-cli timeout).")
        except Exception as e:
            if not self._cancelled:
                self.done.emit(False, str(e))
        finally:
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)


