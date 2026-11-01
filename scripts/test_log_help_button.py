"""#112 : « demander de l'aide » vient APRES l'erreur, et se voit.

Deux defauts signales en QA (AP9, 2026-09-10), capture a l'appui :

1. **Placement** : le bouton s'affichait AU-DESSUS du journal, donc avant
   l'erreur qu'il propose d'expliquer. L'ordre de lecture est « je lis
   l'erreur, puis je demande de l'aide ».
2. **Style** : il portait la variante `logAction` (bloc blanc discret) et se
   fondait dans le fond du journal -- il existait sans se voir. Demande de
   l'utilisateur : le style de bouton PRINCIPAL, comme « Generer » ou
   « Uploader ».

⚠️ Ce test verrouille l'ORDRE DANS LA DISPOSITION, pas une capture d'ecran :
c'est la seule forme verifiable sans oeil humain, et c'est exactement ce qui
avait derive. La verification visuelle reste la procedure de QA.

⚠️ Il verrouille aussi la place de la BARRE DE CONTROLE (moniteur serie), qui
reste en dernier : elle est du mobilier permanent, pas une suite de la
transcription. Sans ce test, la deplacer un jour remettrait le bouton d'aide
au mauvais endroit sans que rien ne le dise.

Run: python scripts/test_log_help_button.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtWidgets import (QApplication, QWidget, QHBoxLayout,  # noqa: E402
                             QLabel)

_APP = QApplication.instance() or QApplication(sys.argv)

from ui.studio.log_widget import LogWidget  # noqa: E402


def _ordre(w: LogWidget) -> list[str]:
    """Nom de role de chaque element de la disposition, de haut en bas."""
    lay = w.layout()
    noms = []
    for i in range(lay.count()):
        it = lay.itemAt(i).widget()
        noms.append("aide" if it is w._help_btn
                    else "corrections" if it is w._repairs_btn
                    else "journal" if it is w._text
                    else "barre")
    return noms


def test_the_help_button_comes_after_the_log():
    """LE test du ticket : on lit l'erreur, PUIS on demande de l'aide."""
    w = LogWidget()
    o = _ordre(w)
    assert o.index("aide") > o.index("journal"), o


def test_the_control_strip_stays_last():
    """La barre du moniteur serie est du mobilier permanent : elle reste en
    bas, sous le bouton d'aide."""
    w = LogWidget()
    barre = QWidget()
    QHBoxLayout(barre).addWidget(QLabel("serie"))
    w.set_bottom_bar(barre)
    o = _ordre(w)
    assert o == ["corrections", "journal", "aide", "barre"], o


def test_the_help_button_wears_the_primary_style():
    """La variante decide du style via la feuille de l'application
    (`QPushButton[variant="primary"]`, cf. theme.app_qss)."""
    w = LogWidget()
    assert w._help_btn.property("variant") == "primary"


def test_the_repairs_button_keeps_its_own_style():
    """« voir les corrections » n'a PAS change : deux boutons principaux dans
    la meme console se disputeraient l'oeil, et le ticket ne parlait que de
    celui d'aide."""
    w = LogWidget()
    assert w._repairs_btn.property("variant") == "logAction"


def test_the_primary_variant_is_served_by_the_app_sheet():
    """Test de FIL : poser la propriete ne sert a rien si la feuille de
    l'application ne porte pas le selecteur. Verifie sur la feuille reelle,
    pas sur une reconstitution."""
    from ui.theme import theme_manager, app_qss
    assert 'QPushButton[variant="primary"]' in app_qss(
        theme_manager.current)


def test_the_button_is_not_zero_pixels():
    """Un bouton stylise peut se retrouver a ZERO pixel (deja paye deux fois
    sur ce projet, TODO #50). On mesure ce qui est AFFICHE."""
    w = LogWidget()
    w.resize(760, 300)
    w.set_done(False, "erreur: 'foo' was not declared in this scope")
    w.show()
    _APP.processEvents()
    t = w._help_btn.size()
    assert w._help_btn.isVisible(), "bouton masque apres un echec"
    assert t.width() > 100 and t.height() > 15, (t.width(), t.height())


TESTS = [
    test_the_help_button_comes_after_the_log,
    test_the_control_strip_stays_last,
    test_the_help_button_wears_the_primary_style,
    test_the_repairs_button_keeps_its_own_style,
    test_the_primary_variant_is_served_by_the_app_sheet,
    test_the_button_is_not_zero_pixels,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
