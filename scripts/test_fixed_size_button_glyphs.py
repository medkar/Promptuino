"""Un bouton a taille FIXE portant un glyphe TEXTE doit declarer padding:0.

Regression introduite le 2026-08-11 par l'allumage du style global
(`theme.app_qss`, commit 82848f5) : le defaut impose `padding: 7px 18px` a tout
bouton dont le QSS local ne declare pas le sien. Sur un bouton a taille fixe,
le contenu est pousse hors du cadre.

Le piege etait DOCUMENTE (procedure QA section P, memoire du chantier) et deux
helpers le respectaient deja (`help_button_qss`, `bare_button_qss`) -- mais
trois boutons ecrits a la main y sont passes au travers, et personne ne l'a vu
parce que l'inspection visuelle ne montre rien : un bouton vide ressemble a un
bouton. Mesure du 2026-08-11 :

    chat_view  ✕ (puce piece jointe)  18x18 ->   0 px d'encre  (INVISIBLE)
    nudge_banner ✕ (fermeture)        22x22 ->   0 px d'encre  (INVISIBLE)
    chat_view  ■ (bouton Stop)        28x28 -> 272 au lieu de 304 (tronque)

⚠️ La ligne de partage n'est PAS « taille fixe » mais « taille fixe ET glyphe
TEXTE » : un bouton-icone (QIcon) n'est pas ecarte par le padding -- mesure
faite sur 22/26/28/32 px, position identique au pixel. Poser `padding: 0`
partout « par securite » serait donc du bruit.

Run : python scripts/test_fixed_size_button_glyphs.py
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Les messages d'echec citent les glyphes eux-memes (✕, ■) : sans ceci, la
# console cp1252 de Windows fait echouer le print AVANT d'afficher la cause.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QPushButton, QWidget
from ui.theme import app_qss, theme_manager

_VIVANTS: list = []


def _encre(w: QWidget) -> int:
    """Pixels differents du pixel du coin haut-gauche (= le fond)."""
    px = QPixmap(w.size())
    px.fill()
    w.render(px)
    img = px.toImage()
    fond = img.pixel(0, 0)
    return sum(1 for y in range(img.height()) for x in range(img.width())
               if img.pixel(x, y) != fond)


def _sous_app_qss(fabrique, mesure):
    """Construit un widget ET LE MESURE avec la feuille d'application REELLE
    posee -- la seule condition dans laquelle le defaut de padding s'applique.

    ⚠️ La mesure doit avoir lieu DANS le contexte. Une premiere version rendait
    le widget apres avoir restaure l'ancienne feuille : les trois tests
    passaient alors meme correctif retire, c'est-a-dire qu'ils ne gardaient
    rien. Verifie depuis en neutralisant le correctif (ils rougissent)."""
    ancien = _APP.styleSheet()
    _APP.setStyleSheet(app_qss(theme_manager.current))
    try:
        w = fabrique()
        w.show()
        _APP.processEvents()
        _VIVANTS.append(w)
        return mesure(w)
    finally:
        _APP.setStyleSheet(ancien)


def _chat_view():
    from ui.chat.chat_view import ChatView
    from ui.chat.chat_controller import ChatController
    return ChatView(ChatController(backend=None, user_mode="beginner"))


def test_the_chat_attachment_remove_button_draws_its_glyph():
    """Le ✕ qui retire une piece jointe : sans padding:0 il ne dessinait RIEN,
    donc le seul moyen de retirer un fichier etait invisible."""
    encre = _sous_app_qss(_chat_view, lambda v: _encre(v._chip_remove_btn))
    assert encre > 0, "le ✕ de la puce de piece jointe ne dessine aucun pixel"


def test_the_chat_stop_button_draws_its_whole_glyph():
    """Le ■ du bouton Stop : sans padding:0, seul le CERCLE se dessinait --
    mesure sur le vrai widget, 160 px d'encre au lieu de 192, les 32 px
    manquants etant le carre lui-meme.

    Auto-calibre plutot qu'ancre sur 192 : on compare le bouton tel qu'il est
    au MEME bouton prive de son `padding`. Un seuil en dur casserait a la
    premiere retouche de bordure ou de police, et le nombre magique ne dirait
    plus ce qu'il verifie."""
    def mesure(vue):
        btn = vue._stop_btn
        avec = _encre(btn)
        qss = btn.styleSheet()
        btn.setStyleSheet(qss.replace("padding:0;", "").replace("padding: 0;", ""))
        _APP.processEvents()
        sans = _encre(btn)
        btn.setStyleSheet(qss)          # remise en etat
        return avec, sans

    avec, sans = _sous_app_qss(_chat_view, mesure)
    assert avec > sans, (
        f"`padding: 0` ne change rien sur le bouton Stop ({avec} = {sans} px) : "
        "soit le glyphe n'est plus rogne, soit la mesure ne mesure plus rien")


def test_the_nudge_banner_close_button_draws_its_glyph():
    from ui.nudge_banner import NudgeBanner
    encre = _sous_app_qss(lambda: NudgeBanner(), lambda b: _encre(b._close))
    assert encre > 0, "le ✕ de fermeture du bandeau ne dessine aucun pixel"


def test_every_fixed_size_text_button_declares_its_padding():
    """LA garde. Balayage de SOURCE : tout QSS local pose sur un bouton a
    taille fixe portant un glyphe texte doit declarer `padding`.

    Source et non runtime, parce que le runtime ne voit que les boutons qu'on
    a su instancier -- et le defaut de ce matin s'est justement cache dans
    ceux que personne n'affichait en test."""
    import ast
    fautifs = []

    def _cible(node) -> str | None:
        """`self._x.setFixedSize(...)` -> "_x" ; `btn.setFixedSize(...)` -> "btn"."""
        v = getattr(node.func, "value", None)
        return getattr(v, "attr", None) or getattr(v, "id", None)

    for p in sorted((ROOT / "ui").rglob("*.py")):
        src = p.read_text(encoding="utf-8", errors="replace")
        arbre = ast.parse(src)
        avec_texte: set[str] = set()   # porte un GLYPHE TEXTE litteral
        taille_fixe: set[str] = set()
        feuilles: list[tuple[str, int, str]] = []   # (cible, ligne, bloc)

        for n in ast.walk(arbre):
            # self._x = QPushButton("✕")  /  x = QPushButton("■")
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
                fn = getattr(n.value.func, "id", None) \
                    or getattr(n.value.func, "attr", None)
                if fn == "QPushButton" and n.value.args:
                    a0 = n.value.args[0]
                    if isinstance(a0, ast.Constant) \
                            and isinstance(a0.value, str) and a0.value.strip():
                        for t in n.targets:
                            nom = getattr(t, "attr", None) or getattr(t, "id", None)
                            if nom:
                                avec_texte.add(nom)
            if not isinstance(n, ast.Call):
                continue
            attr = getattr(n.func, "attr", None)
            cible = _cible(n)
            if not cible:
                continue
            if attr == "setFixedSize":
                taille_fixe.add(cible)
            elif attr == "setText" and n.args:
                a0 = n.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str) \
                        and a0.value.strip():
                    avec_texte.add(cible)
            elif attr == "setStyleSheet" and n.args:
                # On ne juge que les feuilles dont le texte est reconstituable
                # (litteral ou f-string) : une feuille calculee ailleurs n'est
                # pas analysable ici, et l'inventer serait pire que l'ignorer.
                bloc = ast.unparse(n.args[0])
                feuilles.append((cible, n.lineno, bloc))

        for cible, ligne, bloc in feuilles:
            if cible not in taille_fixe or cible not in avec_texte:
                continue                    # icone, ou taille libre : le
                                            # padding global ne rogne rien
            if "QPushButton" not in bloc or "padding" in bloc:
                continue
            fautifs.append(f"{p.relative_to(ROOT).as_posix()}:{ligne} ({cible})")

    assert not fautifs, (
        "bouton a taille fixe + glyphe TEXTE dont le QSS local ne declare pas "
        f"`padding` (le defaut global le poussera hors du cadre) : {fautifs}")


TESTS = [
    test_the_chat_attachment_remove_button_draws_its_glyph,
    test_the_chat_stop_button_draws_its_whole_glyph,
    test_the_nudge_banner_close_button_draws_its_glyph,
    test_every_fixed_size_text_button_declares_its_padding,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
