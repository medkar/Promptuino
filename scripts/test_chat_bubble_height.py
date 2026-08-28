"""Regression : les bulles assistant grandissent pour afficher TOUTE la
reponse (pas de crop + scroll interne).

Bug d'origine : QTextDocument met en page les tables de maniere PARESSEUSE
(nos blocs de code fences sont wrappes en <table>, cf chat_message._md_to_html).
La hauteur du document ne se stabilise qu'APRES setHtml, souvent sans
changement de largeur pour re-declencher resizeEvent -> la hauteur figee a la
creation restait trop petite -> la bulle croppait la reponse et scrollait en
interne. Fix : recalcul sur documentSizeChanged.

Run : python scripts/test_chat_bubble_height.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402

# Ref module-level (sinon GC -> crash sans sortie, cf memory offscreen tests).
_APP = QApplication.instance() or QApplication(sys.argv)

from ui.fonts import setup_fonts  # noqa: E402

setup_fonts(_APP)

from ui.chat.chat_controller import ChatController  # noqa: E402
from ui.chat.chat_message import ChatMessage  # noqa: E402
from ui.chat.chat_view import ChatView  # noqa: E402


_LONG_WITH_CODE = (
    "Voici une explication detaillee du montage.\n\n"
    + ("Cette phrase explique le cablage et le code en detail pour "
       "rallonger la reponse du modele. " * 12)
    + "\n\n```cpp\nvoid setup() {\n  pinMode(13, OUTPUT);\n}\n"
      "void loop() {\n  digitalWrite(13, HIGH);\n  delay(500);\n}\n```\n\n"
    + ("Du texte de conclusion qui rallonge encore la reponse. " * 8)
)

_LONG_PLAIN = "Reponse longue sans aucun bloc de code. " * 120

_WITH_TABLE = (
    "Voici le brochage :\n\n| Broche | Role |\n|---|---|\n"
    + "\n".join(f"| D{i} | pilote la LED numero {i} |" for i in range(12))
    + "\n\nApres le tableau, encore du texte. " * 4
)


def _bubble_for(text: str) -> ChatMessage:
    """Construit un ChatView reel (largeur 340) avec une reponse assistant
    et retourne la bulle assistant rendue, apres stabilisation du layout."""
    ctrl = ChatController(backend=None, user_mode="debutant")
    ctrl.history = [
        {"role": "user", "content": "explique"},
        {"role": "assistant", "content": text},
    ]
    view = ChatView(ctrl)
    view.resize(340, 700)
    view.show()
    for _ in range(8):
        _APP.processEvents()
    for bm in view._conv_container.findChildren(ChatMessage):
        if bm._browser is not None:
            return bm
    raise AssertionError("aucune bulle assistant trouvee")


def _assert_not_cropped(text: str, label: str) -> None:
    bm = _bubble_for(text)
    b = bm._browser
    b.document().setTextWidth(b.width() - 4)
    true_h = b.document().size().height()
    fixed_h = b.height()
    # La hauteur figee doit couvrir toute la hauteur reelle du document
    # (marge de 2px tolereee). Si fixed < true -> crop + scroll interne.
    assert fixed_h + 2 >= true_h, (
        f"{label}: bulle croppee (fixed={fixed_h} < true={true_h:.0f}, "
        f"largeur={b.width()})"
    )


def test_long_response_with_code_block_not_cropped():
    _assert_not_cropped(_LONG_WITH_CODE, "code_block")


def test_long_plain_response_not_cropped():
    _assert_not_cropped(_LONG_PLAIN, "long_plain")


def test_response_with_table_not_cropped():
    _assert_not_cropped(_WITH_TABLE, "table")


TESTS = [
    test_long_response_with_code_block_not_cropped,
    test_long_plain_response_not_cropped,
    test_response_with_table_not_cropped,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}", flush=True)
            os._exit(1)
    print(f"OK : {len(TESTS)} tests", flush=True)
    # os._exit pour contourner le teardown Qt (cf memory offscreen tests).
    os._exit(0)


if __name__ == "__main__":
    main()
