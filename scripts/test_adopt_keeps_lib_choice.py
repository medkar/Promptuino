"""QA I5 (2026-08-10) : reprendre un composant a son compte effacait le choix
de librairie de l'utilisateur.

Mesure d'origine. L'utilisateur avait choisi « Adafruit VEML7700 Library » via
« Changer de librairie » (ecrit dans component-libs.json) ; le cache du
registre, lui, portait encore la DEVINETTE « DevLab_VEML7700 ». Le crayon de la
fiche (`_adoptable_entry`) pre-remplissait le formulaire depuis le CACHE, donc
l'entrée perso naissait avec la devinette. Et comme une entree declaree gagne
ensuite sur component-libs.json (`component_libs.preferred_lib_for` : une seule
source par composant), le choix d'origine devenait inatteignable autrement
qu'en le refaisant a la main.

Ces tests montent la SITUATION (cache et preference en desaccord), pas la
configuration : sur le code d'avant le correctif, le premier echoue en
retournant 'DevLab_VEML7700'.

Run : python scripts/test_adopt_keeps_lib_choice.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level

from ui import component_libs, declared_components, registry_lookup
from ui.main_window import _adoptable_entry

TOKEN = "veml7700"
GUESS = "DevLab_VEML7700"
CHOICE = "Adafruit VEML7700 Library"

_CACHE = {TOKEN: {"lib_name": GUESS,
                  "entry": {"id": TOKEN, "name": GUESS,
                            "headers": ["DevLab_VEML7700.h"]},
                  "alternatives": [CHOICE]}}


def _setup(preference: str | None) -> None:
    """Cache = la devinette ; preferences = ce que le test veut eprouver.

    Le registre des composants declares est vide : `_adoptable_entry` n'est
    appele QUE pour un composant qui n'en est pas un (main_window
    `_on_declare_requested` essaie `find_by_type` d'abord).
    """
    registry_lookup.set_cache_for_tests(_CACHE)
    declared_components.set_registry([])
    component_libs.set_registry({TOKEN: preference} if preference else {})


def _teardown() -> None:
    registry_lookup.set_cache_for_tests(None)
    component_libs.set_registry({})
    declared_components.set_registry([])


def test_adoption_keeps_the_library_the_user_chose():
    """Le coeur du defaut : la DECISION bat la DEVINETTE."""
    _setup(CHOICE)
    try:
        entry = _adoptable_entry(TOKEN)
        assert entry is not None, "aucun brouillon produit pour un jeton en cache"
        assert entry.lib == CHOICE, (
            f"le formulaire s'ouvrirait sur {entry.lib!r} (la devinette du "
            f"cache) au lieu de {CHOICE!r} (le choix de l'utilisateur)")
    finally:
        _teardown()


def test_without_a_choice_the_guess_is_still_used():
    """Le correctif ne doit pas vider le champ quand rien n'a ete choisi :
    sans preference, la devinette reste le meilleur pre-remplissage."""
    _setup(None)
    try:
        entry = _adoptable_entry(TOKEN)
        assert entry is not None
        assert entry.lib == GUESS, (
            f"sans preference, le champ devrait porter la devinette {GUESS!r}, "
            f"pas {entry.lib!r}")
    finally:
        _teardown()


def test_the_name_still_comes_from_the_token():
    """Garde-fou : le correctif ne touche QUE la librairie. Le nom d'une fiche
    devinee vient du jeton, jamais du nom de la librairie -- sinon la fiche
    s'appellerait « DevLab_VEML7700 »."""
    _setup(CHOICE)
    try:
        entry = _adoptable_entry(TOKEN)
        assert entry.name == "VEML7700", (
            f"nom attendu depuis le jeton, obtenu {entry.name!r}")
        assert entry.id, "un brouillon sans id ne peut pas etre enregistre"
    finally:
        _teardown()


def test_an_unknown_token_yields_nothing():
    """Ni cache ni registre cure -> pas de brouillon (et pas d'exception)."""
    _setup(CHOICE)
    try:
        assert _adoptable_entry("jetonquinexistepas9999") is None
    finally:
        _teardown()


TESTS = [
    test_adoption_keeps_the_library_the_user_chose,
    test_without_a_choice_the_guess_is_still_used,
    test_the_name_still_comes_from_the_token,
    test_an_unknown_token_yields_nothing,
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
