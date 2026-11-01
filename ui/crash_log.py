"""Journal de plantage LOCAL — aucun reseau, aucune collecte, aucun consentement.

Remplace le volet << crash >> du paquet `ui/telemetry/`, supprime le
2026-08-28 (TODO #72). Ce qui a disparu avec lui : les evenements d'usage,
l'envoi reseau, la case des parametres et la note de transparence. Ce qui
RESTE ici, et pourquoi :

- **Les excepthooks.** Sans eux, une exception non rattrapee ne laisse
  strictement RIEN : ni trace a l'ecran, ni fichier. Un utilisateur qui dit
  << ca s'est bloque >> serait sans recours. Le rapport est ecrit A COTE de
  `session.json`, sur SA machine, et n'est jamais envoye nulle part.

- **`on_unhandled()` (TODO #49).** PyQt6 n'abandonne le processus que si le
  hook est celui PAR DEFAUT ; celui pose ici retourne normalement, donc l'app
  SURVIT — mais DANS L'ETAT OU ELLE ETAIT. Une exception partie d'un callback
  de worker laissait `_gen_busy` arme, le bouton bloque sur << Annuler >> et le
  journal en train de tourner : une app figee alors qu'elle tournait.
  **Survivre en silence dans un etat casse est sa propre forme de mensonge.**
  Le Studio s'abonne ici pour se remettre d'aplomb.

- **Le masquage du nom d'utilisateur.** Un traceback contient typiquement
  `C:\\Users\\prenom.nom\\...`. Le rapport reste local, mais il est fait pour
  etre envoye A LA MAIN par l'utilisateur s'il demande de l'aide : autant
  qu'il ne trahisse pas son identite au passage.
"""
from __future__ import annotations

import re
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .paths import DATA_DIR
CRASH_DIR = DATA_DIR / "crash-reports"

_installed = False

# Liste de callables NUS : ce module ne connait ni Qt, ni le Studio, ni
# `_gen_busy`. C'est a l'abonne de repasser sur le thread graphique s'il en a
# besoin (le Studio le fait via un signal).
_recovery_hooks: list = []

# C:\Users\<nom>\...  ou  C:/Users/<nom>/...
_WIN_USER = re.compile(r"([A-Za-z]:[\\/]+Users[\\/]+)[^\\/\r\n]+", re.IGNORECASE)
# /home/<nom>/...  et  /Users/<nom>/...  (macOS)
_NIX_HOME = re.compile(r"(/(?:home|Users)/)[^/\r\n]+")


def on_unhandled(fn) -> None:
    """Enregistre un rappel invoque apres chaque exception non rattrapee.

    ⚠️ Peut etre appele depuis N'IMPORTE QUEL thread : `threading.excepthook`
    s'execute dans le thread fautif. Un abonne qui touche a des widgets DOIT
    repasser par un signal Qt."""
    if fn not in _recovery_hooks:
        _recovery_hooks.append(fn)


def scrub_text(text: str) -> str:
    """Retourne `text` avec le nom d'utilisateur masque (`<USER>`). Idempotent ;
    ne leve jamais (retourne `text` tel quel en cas d'erreur)."""
    try:
        if not text:
            return text
        out = _WIN_USER.sub(r"\1<USER>", text)
        return _NIX_HOME.sub(r"\1<USER>", out)
    except Exception:
        return text


def build_report(exc_type: str, tb_text: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return "\n".join([
        "Promptuino crash report",
        f"ts: {stamp}   exc: {exc_type}",
        f"python: {sys.version.split()[0]}   platform: {sys.platform}",
        "", "--- traceback ---", scrub_text(tb_text or ""),
    ])


def write_report(text: str, base_dir: Path) -> Path:
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = base_dir / f"crash-{stamp}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def install(report_dir: "Path | None" = None) -> None:
    """Pose les excepthooks. Ne re-eleve jamais. Idempotent."""
    global _installed
    if _installed:
        return
    base = Path(report_dir) if report_dir else CRASH_DIR

    def _handle(exc_type, exc, tb) -> None:
        try:
            tb_text = "".join(traceback.format_exception(exc_type, exc, tb))
            name = getattr(exc_type, "__name__", "?")
            write_report(build_report(name, tb_text), base)
        except Exception:
            pass
        # Remise d'aplomb de l'interface, APRES le rapport et hors du try
        # ci-dessus : un rappel qui echouerait ne doit pas empecher le rapport
        # d'exister, et le rapport qui echoue ne doit pas empecher l'interface
        # de se debloquer. Chacun est isole -- une panne DANS le filet vaut
        # moins que pas de filet.
        for hook in list(_recovery_hooks):
            try:
                hook()
            except Exception:
                pass

    def _excepthook(exc_type, exc, tb):
        _handle(exc_type, exc, tb)
        sys.__excepthook__(exc_type, exc, tb)

    def _thread_hook(args):
        _handle(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
    _installed = True
