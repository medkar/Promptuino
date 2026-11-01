"""QA J3 (2026-08-10) : un nom declare trop long est coupe dans la boite, sans
aucun moyen de lire le nom entier.

`component_names.fit` ramene le nom a 13 caracteres (« Mon capteur d'humidite
Grove » -> « Mon capteur… »). C'est voulu -- un nom qui deborde ne serait plus
un nom -- mais rien ne donnait acces au texte complet. Le survol le donne
desormais.

Ce que ces tests verrouillent :
  - `full_name` rend EXACTEMENT ce que `short_name` rend, sauf sur le chemin du
    repli (nom declare), ou il ne tronque pas ;
  - donc l'infobulle ne se pose que la ou elle apporte quelque chose : sur un
    composant du catalogue, la boite montre deja son nom entier et repeter le
    texte visible serait du bruit.

Sans Qt : la decision testee est celle des noms, pas celle du widget.

Run : python scripts/test_component_name_tooltip.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.component_names import (
    MAX_CHARS, fit, full_name, known_types, short_name,
)

LONG = "Mon capteur d'humidite Grove"


def _tooltip_for(component_type: str, lang: str, fallback: str) -> str:
    """La regle appliquee par `wiring_diagram_dialog._name_tooltip`, isolee :
    infobulle SEULEMENT quand le nom complet differe du nom dessine."""
    full = full_name(component_type, lang, fallback)
    if full and full != short_name(component_type, lang, fallback):
        return full
    return ""


def test_a_long_declared_name_gets_its_full_text_on_hover():
    assert short_name("custom:le-mien", "fr", LONG) == "Mon capteur…"
    assert _tooltip_for("custom:le-mien", "fr", LONG) == LONG


def test_a_catalog_component_gets_no_tooltip():
    """La boite d'un MCP23017 montre deja « MCP23017 » en entier : une
    infobulle qui repete le texte visible serait du bruit."""
    for type_id in ("mcp23017", "relay", "ds18b20", "pir"):
        assert _tooltip_for(type_id, "fr", "") == "", type_id


def test_a_short_declared_name_gets_no_tooltip_either():
    """Le critere est « la boite a-t-elle coupe », pas « est-ce declare »."""
    assert _tooltip_for("custom:led-a-moi", "fr", "LED a moi") == ""


def test_full_name_never_truncates_where_short_name_does():
    assert len(short_name("custom:x", "fr", LONG)) <= MAX_CHARS
    assert full_name("custom:x", "fr", LONG) == LONG
    assert len(full_name("custom:x", "fr", LONG)) > MAX_CHARS


def test_the_two_agree_on_every_curated_type_and_language():
    """L'invariant qui empeche l'infobulle d'apparaitre partout : sur les types
    cures, les deux fonctions doivent rendre la MEME chaine, dans les 4
    langues. Un nom cure qui depasserait le budget les ferait diverger et
    poserait une infobulle sur tout le catalogue."""
    for type_id in sorted(known_types()):
        for lang in ("fr", "en", "es", "it"):
            assert full_name(type_id, lang) == short_name(type_id, lang), \
                f"{type_id} [{lang}]"


def test_an_empty_name_produces_no_tooltip():
    assert _tooltip_for("custom:vide", "fr", "") == ""
    assert _tooltip_for("", "fr", "") == ""


def test_fit_still_cuts_without_a_space_before_the_ellipsis():
    """Garde-fou repris de la procedure elle-meme (J3)."""
    assert not fit("Mon capteur d'humidite Grove").endswith(" …")


TESTS = [
    test_a_long_declared_name_gets_its_full_text_on_hover,
    test_a_catalog_component_gets_no_tooltip,
    test_a_short_declared_name_gets_no_tooltip_either,
    test_full_name_never_truncates_where_short_name_does,
    test_the_two_agree_on_every_curated_type_and_language,
    test_an_empty_name_produces_no_tooltip,
    test_fit_still_cuts_without_a_space_before_the_ellipsis,
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
