"""Cote STUDIO du fichier de contexte PARTAGE (prompt + chat).

Verifie que deposer/joindre un fichier cote chat (route via
StudioView.attach_context_file) :
  - copie le fichier dans le dossier projet + set project.context_file_path,
  - re-pousse le contexte au chat (chat_context_changed) avec le NOM + le
    CONTENU du fichier (nourrit le chip + le system prompt),
et que le retrait (_on_context_removed) vide le push (chip + badge ensemble).

NB : un seul test (un vrai StudioView par process — cf gotchas Qt offscreen).

Qt requis (offscreen) ; skip propre si absent.
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
    # Reference module-level OBLIGATOIRE (sinon GC -> crash 0xC0000409).
    _APP = QApplication.instance() or QApplication([])
except Exception:
    _HAS_QT = False


def test_chat_attach_routes_to_shared_context_and_pushes():
    from ui.studio_view import StudioView
    from ui.project_manager import Project, ProjectType

    sv = StudioView()

    payloads: list[dict] = []
    sv.chat_context_changed.connect(payloads.append)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        proj_dir = tmp / "proj"
        proj_dir.mkdir()
        sv._current_project = Project(
            path=proj_dir, name="t", type=ProjectType.ARDUINO,
        )

        src = tmp / "notes.md"
        src.write_text("DATASHEET PARTAGEE", encoding="utf-8")

        # Simule un drop / + Attach cote CHAT (passe par le point d'entree
        # public route depuis MainWindow).
        sv.attach_context_file(str(src))

        # Le fichier a ete copie dans le projet + reference.
        assert sv._current_project.context_file_path == "notes.md"
        assert (proj_dir / "notes.md").read_text(encoding="utf-8") == "DATASHEET PARTAGEE"

        # Un push chat a eu lieu avec nom + contenu (alimente chip + prompt).
        assert payloads, "aucun push chat apres attach"
        last = payloads[-1]
        assert last["context_name"] == "notes.md", last
        assert "DATASHEET PARTAGEE" in last["user_material"], last

        # Retrait : le push suivant vide nom ET contenu (chip + badge tombent).
        sv._on_context_removed()
        assert sv._current_project.context_file_path == ""
        assert not (proj_dir / "notes.md").exists()
        last = payloads[-1]
        assert last["context_name"] == "", last
        assert last["user_material"] == "", last


TESTS = [test_chat_attach_routes_to_shared_context_and_pushes]


def main() -> None:
    if not _HAS_QT:
        print("SKIP (PyQt6 absent)")
        os._exit(0)
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:
            print(f"FAIL {t.__name__}: {exc}")
            failed += 1
    print(f"OK : {len(TESTS)} test" if not failed else f"{failed} failed")
    # Teardown statique Qt apres un vrai StudioView crashe sous Windows
    # offscreen APRES les assertions -> os._exit reflete le resultat reel.
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
