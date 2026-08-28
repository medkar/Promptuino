"""Régression : la persistance de session est ATOMIQUE et tolère un fichier
corrompu (cause du bug « relance = comme un premier lancement » : un
session.json tronqué par un arrêt brutal / coupure de courant était relu
vide -> assistant de 1er lancement + tutoriel rejoués).

IMPORTANT : ce test patche `_SESSION_PATH` vers un dossier TEMPORAIRE — il ne
touche JAMAIS le vrai ~/Documents/Promptuino/session.json.

Run : python scripts/test_session_atomic.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.session as session_mod  # noqa: E402


def _fresh_session(tmpdir: Path):
    """Nouvelle instance Session pointant sur un session.json isolé."""
    session_mod._SESSION_PATH = tmpdir / "session.json"
    return session_mod.Session()


def test_save_then_reload_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _fresh_session(tmp)
        s.workspace_root = ""          # « configuré » (clé présente, défaut)
        s.set_tutorial_seen("beginner", True)
        s.last_project_path = r"C:\proj\Foo"
        # Recharger depuis le disque (nouvelle instance) doit tout retrouver.
        s2 = _fresh_session(tmp)
        assert s2.is_workspace_root_configured() is True
        assert s2.tutorial_seen("beginner") is True
        assert s2.last_project_path == r"C:\proj\Foo"


def test_save_is_atomic_no_leftover_tmp():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        s = _fresh_session(tmp)
        s.set_tutorial_seen("advanced", True)
        # Aucun fichier .tmp résiduel ; le fichier final est un JSON complet.
        leftovers = list(tmp.glob("*.tmp"))
        assert not leftovers, f"temp file leak: {leftovers}"
        data = json.loads((tmp / "session.json").read_text(encoding="utf-8"))
        assert data.get("tutorial_seen_advanced") is True


def test_corrupt_file_is_set_aside_not_crash():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # Simule un fichier tronqué par une coupure (JSON invalide).
        (tmp / "session.json").write_text('{"workspace_root": "", "tuto',
                                          encoding="utf-8")
        s = _fresh_session(tmp)          # ne doit PAS crasher
        # Repart sur des défauts (clé absente -> assistant 1er lancement),
        # MAIS le fichier corrompu est mis de côté pour diagnostic.
        assert s.is_workspace_root_configured() is False
        assert (tmp / "session.json.corrupt").exists()
        # Et une sauvegarde ultérieure réécrit un fichier valide.
        s.workspace_root = ""
        data = json.loads((tmp / "session.json").read_text(encoding="utf-8"))
        assert "workspace_root" in data


TESTS = [
    test_save_then_reload_roundtrip,
    test_save_is_atomic_no_leftover_tmp,
    test_corrupt_file_is_set_aside_not_crash,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}", flush=True)
            return 1
    print(f"OK : {len(TESTS)} tests", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
