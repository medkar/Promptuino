"""QA I6 (2026-08-10) : choisir une librairie DANS le formulaire ne prevenait
personne.

Mesure d'origine. La campagne QA a remplace le bouton « Changer de
bibliotheque » de l'onglet Composants par le crayon. Le signal qui le portait
(`ComponentsView.change_lib_requested`) est reste DECLARE et BRANCHE jusqu'a
`StudioView.on_change_lib_for_component`... mais plus jamais emis. Toute la
suite est donc devenue injoignable depuis l'onglet :

  - `_after_lib_preference_changed`  -> l'offre de regeneration ;
  - `_warn_lib_swap_unchecked`       -> « impossible de verifier si le code
                                        utilise encore l'ancienne librairie ».

La banniere, elle, avait garde les deux. Une porte deplacee sans rebrancher ce
qu'il y avait derriere.

Ces tests exercent la troisieme porte (formulaire) et ses deux garde-fous de
bruit. Rejoues sur le code d'avant, les 6 echouent -- mais par AttributeError
(les methodes n'existaient pas), pas sur un comportement faux : le defaut etait
une ABSENCE. Ce qu'ils verrouillent vraiment, c'est que la porte du formulaire
partage la meme queue que la banniere, que le jeton envoye est le NOM et non
l'id de la fiche, et que les deux cas « rien n'a ete remplace » restent muets.

Run : python scripts/test_lib_choice_from_form.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level

from ui.main_window import MainWindow
from ui.studio_view import StudioView


class _FakeSaved:
    """Ce que `DeclareComponentDialog.result_component` rend d'utile ici."""
    def __init__(self, name: str, lib: str) -> None:
        self.name, self.lib = name, lib


class _SpyStudio:
    """Studio minimal : on veut savoir CE QUI est appele, pas construire une
    vue (couteuse, et sans rapport avec la decision testee)."""
    def __init__(self) -> None:
        self.calls: list = []

    def on_lib_chosen_in_form(self, token, old_lib, new_lib):
        self.calls.append((token, old_lib, new_lib))


def _notify(key: str, old_lib: str, saved) -> _SpyStudio:
    """Appelle la methode reelle de MainWindow sans construire la fenetre.

    `__new__` sans `__init__` : la methode ne lit que `self._views`, et monter
    une MainWindow complete pour eprouver un aiguillage de trois lignes
    couterait une fenetre entiere par test.
    """
    win = MainWindow.__new__(MainWindow)
    spy = _SpyStudio()
    win._views = {"console": spy}
    MainWindow._notify_lib_chosen_in_form(win, key, old_lib, saved)
    return spy


def _studio_spy():
    """StudioView reel, mais dont on remplace la queue par des mouchards :
    c'est bien le code des GARDES de `on_lib_chosen_in_form` qui tourne."""
    sv = StudioView.__new__(StudioView)
    calls: list = []
    sv._after_lib_preference_changed = lambda *a: calls.append(("hook",) + a)
    sv._offer_lib_swap_regeneration = lambda: calls.append(("offer",))
    return sv, calls


def test_replacing_a_library_from_the_form_notifies_the_studio():
    spy = _notify("veml7700", "DevLab_VEML7700",
                  _FakeSaved("VEML7700", "Adafruit VEML7700 Library"))
    assert spy.calls == [("veml7700", "DevLab_VEML7700",
                          "Adafruit VEML7700 Library")], spy.calls


def test_the_form_door_runs_the_same_tail_as_the_banner():
    """Le fond du correctif : une seule chaine derriere les trois portes."""
    sv, calls = _studio_spy()
    StudioView.on_lib_chosen_in_form(sv, "veml7700", "DevLab_VEML7700",
                                     "Adafruit VEML7700 Library")
    assert calls == [("hook", "veml7700", "DevLab_VEML7700",
                      "Adafruit VEML7700 Library"), ("offer",)], calls


def test_creating_a_component_with_a_library_says_nothing():
    """Garde-fou de bruit : sans librairie PRECEDENTE, rien n'a ete remplace,
    donc aucun code ne peut utiliser l'ancienne. Avertir ici ferait parler
    l'app a chaque creation."""
    sv, calls = _studio_spy()
    StudioView.on_lib_chosen_in_form(sv, "sht31", "", "Adafruit SHT31 Library")
    assert calls == [], calls


def test_choosing_the_same_library_says_nothing():
    """Meme librairie a la casse et aux espaces pres = pas un changement."""
    sv, calls = _studio_spy()
    StudioView.on_lib_chosen_in_form(sv, "veml7700", "Adafruit VEML7700 Library",
                                     "adafruit  veml7700   library")
    assert calls == [], calls


def test_the_token_is_the_entry_name_not_the_card_key():
    """Le jeton doit etre celui sous lequel le cache a ete rempli, sinon
    `_after_lib_preference_changed` ne retrouve pas les en-tetes concernes.
    Une entree renommee a un id qui ne coincide plus avec son nom."""
    spy = _notify("grove-ultrasonic-ranger", "Grove Ultrasonic",
                  _FakeSaved("Grove Ultrasonic Ranger", "Ultrasonic"))
    assert spy.calls == [("grove ultrasonic ranger", "Grove Ultrasonic",
                          "Ultrasonic")], spy.calls


def test_cancelling_the_form_notifies_nothing():
    assert _notify("veml7700", "DevLab_VEML7700", None).calls == []


TESTS = [
    test_replacing_a_library_from_the_form_notifies_the_studio,
    test_the_form_door_runs_the_same_tail_as_the_banner,
    test_creating_a_component_with_a_library_says_nothing,
    test_choosing_the_same_library_says_nothing,
    test_the_token_is_the_entry_name_not_the_card_key,
    test_cancelling_the_form_notifies_nothing,
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
