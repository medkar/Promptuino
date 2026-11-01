"""Le chat émet request_modify_in_studio(seed) AVEC un texte propre (sans
préfixe CORRECTION) quand on clique « Modifier dans le Studio » (chat libre).
Run : python scripts/test_chat_modify_signal.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QPushButton
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.chat.chat_controller import ChatController
from ui.chat.chat_view import ChatView
from ui.chat.chat_message import ChatMessage


def test_free_chat_offer_emits_clean_seed():
    ctrl = ChatController(backend=None, user_mode="beginner")
    v = ChatView(ctrl)
    seen = []
    v.request_modify_in_studio.connect(lambda s: seen.append(s))

    v._append_correction_studio_offer("change la vitesse de la LED")
    _APP.processEvents()

    bubbles = v._conv_container.findChildren(ChatMessage)
    btn = None
    for bm in reversed(bubbles):
        b = bm.findChild(QPushButton)
        if b is not None:
            btn = b
            break
    assert btn is not None, "bouton d'action introuvable"
    btn.click()
    _APP.processEvents()

    assert seen == ["change la vitesse de la LED"], seen
    assert not seen[0].upper().startswith("CORRECTION"), seen
    print("  OK — chat libre émet un seed propre")


TESTS = [test_free_chat_offer_emits_clean_seed]


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
