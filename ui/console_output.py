"""Make the diagnostic streams unable to kill the application.

Found the hard way on 2026-08-10: the app died with a segfault (exit 139) the
moment a registry lookup SUCCEEDED. The chain was short and entirely made of
things that each looked harmless:

  1. `registry_lookup` writes its log lines with an arrow —
     ``[REGISTRY] « as7341 » → lib « Adafruit AS7341 »`` ;
  2. `studio_view._apply_registry_results` mirrors every line to stdout with a
     plain `print` ;
  3. on Windows, stdout defaults to the ANSI code page (cp1252 on a Western
     install), where U+2192 has no encoding → `UnicodeEncodeError` ;
  4. that exception is raised inside a **Qt slot** (the `RegistryLookupWorker`
     done callback). PyQt6 does not swallow those: it aborts the process.

So a DIAGNOSTIC LINE killed the app, in the middle of a generation, on the
happy path. It went unnoticed because the developer's own terminal
(PowerShell 7) is UTF-8; a user launching from `cmd.exe` would lose everything.

The fix belongs here rather than at each `print`: there are dozens of them
(`[RAG] …`, `[REGISTRY] …`, worker traces) and any future one would reopen the
hole. We do NOT force UTF-8 — that would turn accented text into mojibake on a
cp1252 console. We only relax the ERROR HANDLER: an unencodable character
becomes `?`, and the app lives.
"""
import sys


def make_stream_lenient(stream) -> bool:
    """Switch one text stream to ``errors="replace"``. Returns True if it
    took effect.

    Silent no-op when the stream is None (PyInstaller windowed builds set
    stdout to None) or has no `reconfigure` (already-wrapped streams). A
    hardening helper that raises would be its own kind of joke."""
    if stream is None:
        return False
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return False
    try:
        reconfigure(errors="replace")
    except Exception:
        return False
    return True


def make_console_lenient() -> None:
    """Apply to stdout and stderr. Call ONCE, as early as possible — before
    anything can print."""
    make_stream_lenient(sys.stdout)
    make_stream_lenient(sys.stderr)
