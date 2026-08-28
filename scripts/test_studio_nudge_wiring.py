"""Le helper de nudge de StudioView : affiche UNE fois dans le journal quand
le compteur atteint le seuil ET qu'on est dans le bon mode, puis ne se répète
plus (drapeau app-wide).

Offscreen. Patche session vers un chemin temporaire pour ne pas polluer le vrai
session.json. Garde une ref module-level à QApplication (sinon GC -> crash).
Run : python scripts/test_studio_nudge_wiring.py
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)

from ui.fonts import setup_fonts
setup_fonts(_APP)

import ui.session as session_mod
from ui.progress_nudge import (
    COUNTER_BEGINNER, NUDGE_BEGINNER, BEGINNER_GEN_THRESHOLD,
)


def _isolate_session():
    d = tempfile.mkdtemp()
    session_mod._SESSION_PATH = Path(d) / "session.json"
    new = session_mod.Session()
    session_mod.session = new
    return new


def test_nudge_fires_once_at_threshold():
    sess = _isolate_session()
    from ui.studio_view import StudioView
    import ui.studio_view as sv
    sv.session = sess                         # studio_view a `from .session import session`
    view = StudioView()
    view._on_mode_changed("beginner")
    _APP.processEvents()

    def _call():
        view._maybe_progress_nudge(
            mode="beginner", counter_key=COUNTER_BEGINNER,
            threshold=BEGINNER_GEN_THRESHOLD, nudge_key=NUDGE_BEGINNER,
            message="MSG", action_label="GO", target_mode="intermediate",
        )

    # Sous le seuil : pas de nudge, bandeau caché.
    for _ in range(BEGINNER_GEN_THRESHOLD - 1):
        sess.bump_progress_count(COUNTER_BEGINNER)
    _call()
    assert sess.nudge_seen(NUDGE_BEGINNER) is False
    # isHidden() reflète l'état explicite (indépendant de l'affichage des ancêtres,
    # la vue n'étant pas show()n en offscreen).
    assert view._nudge_banner.isHidden() is True

    # Au seuil : bandeau montré + marqué vu + cible mémorisée.
    sess.bump_progress_count(COUNTER_BEGINNER)
    _call()
    assert sess.nudge_seen(NUDGE_BEGINNER) is True
    assert view._nudge_banner.isHidden() is False
    assert view._nudge_target_mode == "intermediate"

    # Idempotent : on cache le bandeau ; un nouvel appel ne le ré-affiche pas.
    view._nudge_banner.hide()
    _call()
    assert view._nudge_banner.isHidden() is True
    assert sess.nudge_seen(NUDGE_BEGINNER) is True
    print("  OK — bandeau de nudge une fois au seuil + idempotent")


TESTS = [test_nudge_fires_once_at_threshold]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}", flush=True)
            os._exit(1)
    print(f"OK : {len(TESTS)} tests", flush=True)
    os._exit(0)


if __name__ == "__main__":
    main()
