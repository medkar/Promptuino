"""#111 : l'explication des bornes en serie se comprend, et se copie.

Deux defauts distincts dans la meme phrase, signales en QA (AP6 et AP7,
2026-09-10).

**(1) La formulation.** « Les bornes IP+ / IP- se coupent **en serie** dans
le fil du circuit dont tu mesures le courant » suppose qu'on sache ce que
<< couper en serie >> veut dire. Un debutant, non -- et c'est le public de
cette application. Le message decrit desormais le GESTE (couper le fil,
brancher un bout sur chaque borne), et le mot << serie >> arrive APRES, comme
une definition de ce qu'on vient de faire, plus comme une condition pour
comprendre la phrase.

**(2) La copie.** Le texte vit aussi dans une modale ouverte au clic sur la
pastille d'attention -- laquelle passait par `QMessageBox.information(...)`.
⛔ Cette commodite est STATIQUE : elle construit la boite ET l'execute d'un
bloc, sans jamais rendre la main. `make_selectable` (TODO #95) ne pouvait donc
PAS s'y appliquer, et c'est exactement pourquoi ce chantier-la n'avait pas
couvert ces modales. On construit la boite a la main.

⚠️ L'INFOBULLE, elle, reste non selectionnable et le restera : une infobulle
Qt ne l'est jamais. C'est la raison pour laquelle le correctif n'est pas
<< rendre l'infobulle copiable >> mais << ne pas compter sur une infobulle
pour porter un texte qu'on veut pouvoir coller >>.

Run: python scripts/test_series_terminals_explained.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtWidgets import QApplication, QMessageBox, QLabel  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

from ui.wiring.instructions import (  # noqa: E402
    _WARNING_TEMPLATES, _render_warning_message)
from ui.selectable_text import make_selectable, is_selectable  # noqa: E402

_LANGUES = ("fr", "en", "es", "it")
_CODE = "current_sensor_series_terminals"


def _plat(s: str) -> str:
    """Minuscules SANS accents -- « série » ne contient pas « serie »."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn")


class _Faux:
    """Le warning tel que `markers` l'emet pour un ACS712."""
    code = _CODE
    message = ""
    params = {"name": "ACS712", "pins": "IP+ / IP-",
              "pin1": "IP+", "pin2": "IP-"}


# ── (1) la formulation ────────────────────────────────────────────────────

def test_the_two_terminals_are_named_one_by_one():
    """LE changement de fond : le geste demande de designer chaque borne.
    Un `{pins}` joint (« IP+ / IP- ») ne permet pas de dire « un bout sur
    l'une, l'autre bout sur l'autre »."""
    for lg in _LANGUES:
        tpl = _WARNING_TEMPLATES[_CODE][lg]
        assert "{pin1}" in tpl and "{pin2}" in tpl, lg


def test_the_message_describes_a_gesture():
    """Chaque langue doit porter le VERBE du geste. Sans lui on retombe sur
    la phrase d'origine, qui nommait l'operation sans jamais la decrire."""
    verbes = {"fr": "coupe", "en": "cut", "es": "corta", "it": "taglia"}
    for lg, verbe in verbes.items():
        texte = _render_warning_message(_Faux, lg).lower()
        assert verbe in texte, (lg, texte)


def test_the_terminals_really_appear_in_the_rendered_text():
    """Test de rendu, pas de gabarit : un `{pin1}` non substitue passerait le
    test precedent et s'afficherait tel quel a l'utilisateur."""
    for lg in _LANGUES:
        texte = _render_warning_message(_Faux, lg)
        assert "IP+" in texte and "IP-" in texte, (lg, texte)
        assert "{" not in texte, (lg, texte)


def test_series_is_no_longer_a_prerequisite():
    """Le mot reste -- il a une valeur pedagogique -- mais il doit venir
    APRES le geste. S'il ouvrait encore l'explication, on aurait renomme le
    probleme sans le corriger."""
    for lg, verbe in {"fr": "coupe", "en": "cut",
                      "es": "corta", "it": "taglia"}.items():
        # ⚠️ Accents REPLIES avant de chercher : « série » ne contient pas
        # « serie », et l'ignorer rend un faux rouge (paye a l'ecriture de ce
        # fichier).
        texte = _plat(_render_warning_message(_Faux, lg))
        mot = "series" if lg == "en" else "serie"
        i_geste, i_mot = texte.index(verbe), texte.find(mot)
        assert i_mot > i_geste, (lg, i_geste, i_mot)


def test_every_language_was_really_rewritten():
    """Quatre langues, quatre reecritures : la phrase d'origine ne doit
    survivre nulle part."""
    for lg in _LANGUES:
        tpl = _WARNING_TEMPLATES[_CODE][lg]
        assert "in the wire of the" not in tpl, lg
        assert "dans le fil du circuit" not in tpl, lg


# ── (2) la copie ──────────────────────────────────────────────────────────

def test_a_message_box_label_is_reachable_by_make_selectable():
    """La brique du correctif, verifiee plutot que supposee : le texte d'une
    QMessageBox vit bien dans un QLabel enfant, donc `make_selectable` mord."""
    box = QMessageBox()
    box.setText(_render_warning_message(_Faux, "fr"))
    make_selectable(box)
    porteurs = [l for l in box.findChildren(QLabel) if l.text()]
    assert porteurs, "aucun label porteur de texte dans la QMessageBox"
    assert all(is_selectable(l) for l in porteurs)


def test_the_dialog_no_longer_uses_the_static_convenience():
    """⛔ La regression a ne pas refaire. `QMessageBox.information(...)`
    construit ET execute d'un bloc : aucun endroit ou rendre le texte
    selectionnable. Verifie sur la SOURCE parce que ces modales demandent un
    clic humain pour s'ouvrir.

    ⚠️ Lu a l'AST, pas par recherche de texte : la docstring du helper CITE
    cette commodite pour expliquer pourquoi elle est bannie, et un simple
    `in src` s'y accrochait (paye a l'ecriture de ce fichier). L'assertion ne
    porte que des NUMEROS DE LIGNE -- un extrait de source dans un message
    d'echec peut contenir un caractere que la console Windows ne sait pas
    encoder, et le lanceur meurt alors sur le message au lieu du defaut.
    """
    import ast
    src = (ROOT / "ui" / "wiring" / "wiring_diagram_dialog.py").read_text(
        encoding="utf-8")
    fautifs = [
        n.lineno for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "information"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "QMessageBox"
    ]
    assert not fautifs, fautifs


def test_the_helper_makes_its_box_selectable():
    """Le point de passage unique porte bien l'appel -- sans lui, le helper
    n'aurait deplace le probleme que d'un cran."""
    src = (ROOT / "ui" / "wiring" / "wiring_diagram_dialog.py").read_text(
        encoding="utf-8")
    debut = src.index("def _info_box(")
    corps = src[debut:src.index("def _on_info_clicked(", debut)]
    assert "make_selectable(box)" in corps, corps[-400:]
    assert "box.exec()" in corps


TESTS = [
    test_the_two_terminals_are_named_one_by_one,
    test_the_message_describes_a_gesture,
    test_the_terminals_really_appear_in_the_rendered_text,
    test_series_is_no_longer_a_prerequisite,
    test_every_language_was_really_rewritten,
    test_a_message_box_label_is_reachable_by_make_selectable,
    test_the_dialog_no_longer_uses_the_static_convenience,
    test_the_helper_makes_its_box_selectable,
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
