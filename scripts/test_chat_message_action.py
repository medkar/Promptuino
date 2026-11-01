"""Test de ChatMessage.set_action (ajout d'un bouton apres construction)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PyQt6.QtWidgets import QApplication, QPushButton
    _HAS_QT = True
except Exception:
    _HAS_QT = False


def test_set_action_adds_button():
    from ui.chat.chat_message import ChatMessage
    app = QApplication.instance() or QApplication([])
    msg = ChatMessage(role="assistant", text="Coucou")
    clicked = {"n": 0}
    msg.set_action("Appliquer", lambda: clicked.__setitem__("n", 1))
    buttons = msg.findChildren(QPushButton)
    assert any(b.text() == "Appliquer" for b in buttons), "bouton absent"
    next(b for b in buttons if b.text() == "Appliquer").click()
    assert clicked["n"] == 1


TESTS = [test_set_action_adds_button]


def main():
    if not _HAS_QT:
        print("SKIP — PyQt6 indisponible")
        sys.exit(0)
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
