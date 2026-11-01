"""Reconnaissance du gabarit de l'editeur — et pourquoi les anciens comptent.

`is_known_template` compare des chaines EXACTES. C'est elle qui repond « cet
editeur est vide » : `_code_is_drawable` s'en sert pour activer ou non les
boutons « Voir le schema » et « Uploader » (QA E1). Reformuler un gabarit sans
conserver l'ancien rend donc meconnaissables les projets deja enregistres --
leur editeur vide passe pour du vrai code.

Arrive le 2026-08-08 en renommant « bibliotheque » en « librairie » : le
remplacement avait touche le gabarit COURANT *et* la table des anciens, qui
n'est pas de la prose a entretenir mais la trace de ce que les versions
passees ont reellement ecrit.

Run : python scripts/test_editor_templates.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.i18n import (EDITOR_TEMPLATES, _LEGACY_EDITOR_TEMPLATES,
                     _PRE_2026_08_08_FR_TEMPLATE, lang_manager)


def test_every_current_template_is_recognized():
    for lang, tpl in EDITOR_TEMPLATES.items():
        assert lang_manager.is_known_template(tpl), lang


def test_every_legacy_template_is_recognized():
    for lang, tpl in _LEGACY_EDITOR_TEMPLATES.items():
        assert lang_manager.is_known_template(tpl), lang


def test_the_pre_rename_template_is_still_recognized():
    assert lang_manager.is_known_template(_PRE_2026_08_08_FR_TEMPLATE)


def test_the_legacy_table_keeps_the_word_it_shipped_with():
    """La table des anciens gabarits est un ENREGISTREMENT, pas un texte a
    corriger : elle doit dire ce que l'app disait a l'epoque."""
    assert "bibliothèques externes" in _LEGACY_EDITOR_TEMPLATES["fr"], \
        "le gabarit historique a ete reformule -- il ne reconnait plus rien"


def test_a_real_sketch_is_not_a_template():
    sketch = ("void setup() {\n  pinMode(13, OUTPUT);\n}\n"
              "void loop() {\n  digitalWrite(13, HIGH);\n}\n")
    assert not lang_manager.is_known_template(sketch)
    # ... et un gabarit MODIFIE non plus : une seule ligne ajoutee suffit.
    assert not lang_manager.is_known_template(
        EDITOR_TEMPLATES["fr"] + "int x = 0;\n")


TESTS = [
    test_every_current_template_is_recognized,
    test_every_legacy_template_is_recognized,
    test_the_pre_rename_template_is_still_recognized,
    test_the_legacy_table_keeps_the_word_it_shipped_with,
    test_a_real_sketch_is_not_a_template,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
