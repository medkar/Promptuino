"""Les TROIS portes qui rouvrent le formulaire de declaration previennent-elles
le Studio quand la librairie change ? (TODO #52)

Le defaut, signale a l'ecran le 2026-08-12 : changer la librairie d'un composant
depuis le SCHEMA modifiait bien `components.json`, mais ne proposait ni
regeneration ni avertissement `lib_swap_unchecked`. Le code genere continuait de
referencer l'ancienne librairie EN SILENCE.

Une seule des trois portes rebranchait l'apres-coup (la fiche de l'onglet
« Composants », via `main_window._notify_lib_chosen_in_form`). Les deux crayons
du schema — celui de la tuile Debutant et celui de la liste du mode Avance —
etaient restes muets. C'est le meme motif qu'en QA I6 du 2026-08-10 : une porte
deplacee sans rebrancher ce qu'il y avait derriere.

Ces tests visent le POINT DE PASSAGE (`StudioView.notify_lib_chosen_in_form`) et
le signal qui y mene, pas la mise en page : ce sont eux qui portent la garantie
« une seule facon de changer de librairie, quelle que soit la porte ».

Run : python scripts/test_lib_change_from_schema.py
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# QApplication gardee au niveau module : sans reference, une app temporaire
# GC-ee puis la construction d'un QWidget plante le process (0xC0000409).
from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

from ui.declared_components import DeclaredComponent  # noqa: E402
import ui.studio_view as sv  # noqa: E402
import ui.wiring.ambiguity_dialog as amb  # noqa: E402


def _entry(name: str, lib: str) -> DeclaredComponent:
    return DeclaredComponent(
        id=name.lower().replace(" ", "-"), name=name, headers=(), pins=(),
        lib=lib, keywords=(name,))


class _Spy:
    """Un StudioView reduit a ce que `notify_lib_chosen_in_form` touche.

    On emprunte la VRAIE methode plutot que de la reecrire : un test qui
    reimplemente ce qu'il verifie ne verifie plus rien.

    L'emprunt se fait A L'APPEL et non a l'import. Sur un code depourvu du
    correctif, une liaison a l'import ferait planter le MODULE entier par
    `AttributeError` — le fichier ne serait plus importable, aucun test ne
    tournerait, et on ne saurait pas lesquels rougissent ni pourquoi. Verifie :
    par cette forme, les tests echouent un par un en nommant ce qui manque.
    """

    def __init__(self):
        self.calls = []

    def on_lib_chosen_in_form(self, token, old_lib, new_lib):
        self.calls.append((token, old_lib, new_lib))

    def notify_lib_chosen_in_form(self, old_lib, saved):
        fn = getattr(sv.StudioView, "notify_lib_chosen_in_form", None)
        assert fn is not None, (
            "StudioView n'expose pas notify_lib_chosen_in_form : les portes du "
            "schema n'ont aucun point de passage vers l'offre de regeneration")
        return fn(self, old_lib, saved)


# ---------------------------------------------------------------------------
# Le point de passage commun
# ---------------------------------------------------------------------------

def test_a_replaced_library_reaches_the_regeneration_hook():
    spy = _Spy()
    spy.notify_lib_chosen_in_form("Ancienne Lib",
                                  _entry("Grove Ultrasonic Ranger", "Nouvelle Lib"))
    assert spy.calls == [("grove ultrasonic ranger", "Ancienne Lib",
                          "Nouvelle Lib")]


def test_the_token_is_the_name_lowercased_never_the_id():
    """`_declared_lookup_token` est la source de verite de cette derivation.
    L'id (« grove-ultrasonic-ranger ») et le jeton (« grove ultrasonic ranger »)
    different des que le nom porte un espace — viser l'id ferait manquer le
    cache."""
    spy = _Spy()
    entry = _entry("Grove Ultrasonic Ranger", "Nouvelle")
    spy.notify_lib_chosen_in_form("Ancienne", entry)
    token = spy.calls[0][0]
    assert token == "grove ultrasonic ranger"
    assert token != entry.id


def test_an_unchanged_library_says_nothing():
    """Proposer de regenerer un code qui reference deja la bonne librairie
    serait du bruit."""
    spy = _Spy()
    spy.notify_lib_chosen_in_form("MemeLib", _entry("X", "MemeLib"))
    assert spy.calls == []


def test_whitespace_alone_is_not_a_change():
    spy = _Spy()
    spy.notify_lib_chosen_in_form("  MemeLib  ", _entry("X", "MemeLib"))
    assert spy.calls == []


def test_a_cancelled_or_removed_form_says_nothing():
    """`result_component` vaut None quand le formulaire a ete annule ou quand
    l'entree a ete supprimee : il n'y a alors aucune librairie a annoncer."""
    spy = _Spy()
    spy.notify_lib_chosen_in_form("Ancienne", None)
    assert spy.calls == []


def test_clearing_the_library_is_a_change_too():
    """« Laisser l'app decider » vide le champ : le code reference encore
    l'ancienne librairie, donc l'offre de regeneration doit partir."""
    spy = _Spy()
    spy.notify_lib_chosen_in_form("Ancienne", _entry("X", ""))
    assert spy.calls == [("x", "Ancienne", "")]


# ---------------------------------------------------------------------------
# Les portes elles-memes
# ---------------------------------------------------------------------------

def test_the_advanced_modal_exposes_the_signal_that_reaches_the_studio():
    """`AmbiguityDialog` n'a AUCUN acces au Studio : sans ce signal, son crayon
    ne peut pas prevenir, et c'est exactement ce qui manquait."""
    from PyQt6.QtCore import pyqtBoundSignal
    sig = getattr(amb.AmbiguityDialog, "lib_changed_in_form", None)
    assert sig is not None, "AmbiguityDialog n'expose pas lib_changed_in_form"
    led = amb.Component(ref="D1", type="led",
                        pins=[amb.Pin("A", "D5"), amb.Pin("K", "GND")],
                        attributes={"category": "single_output",
                                    "_confidence": "low"})
    dlg = amb.AmbiguityDialog([led], netlist=amb.Netlist(board_id="uno_r3",
                                                        components=[led]))
    assert isinstance(dlg.lib_changed_in_form, pyqtBoundSignal)
    got = []
    dlg.lib_changed_in_form.connect(lambda old, saved: got.append((old, saved)))
    entry = _entry("X", "Nouvelle")
    dlg.lib_changed_in_form.emit("Ancienne", entry)
    assert got == [("Ancienne", entry)]
    dlg.deleteLater()


def test_both_schema_doors_capture_the_old_library_before_opening():
    """La garde qui compte : l'ancienne librairie doit etre lue AVANT
    d'ouvrir le formulaire. Apres acceptation, l'entree porte deja la nouvelle
    et l'ancienne est perdue a jamais — c'est precisement l'erreur que ce
    correctif repare, et elle ne laisse aucune trace a l'execution.

    Verifie sur la SOURCE, parce qu'aucune assertion d'execution ne peut
    distinguer « lu avant » de « lu apres » une fois le formulaire ferme.

    ⚠️ TROIS portes depuis le 2026-08-13, plus deux : la modale d'ambiguite
    est passee aux cards, et le crayon d'une card NON declaree la « reprend a
    ton compte » (`_adopt_component`) exactement comme la fiche de l'onglet.
    C'est une porte de plus vers le meme formulaire, donc une occasion de plus
    de perdre l'ancienne librairie. Le defaut d'origine (#52) a ete trouve en
    production sur une porte oubliee : ajouter une porte sans l'ajouter ici,
    c'est le faire revenir. Toute nouvelle porte s'ajoute a cette liste.
    """
    import inspect
    failures = []
    for label, fn in (
            ("studio_view._open_declare_dialog_for_entry",
             sv.StudioView._open_declare_dialog_for_entry),
            ("ambiguity_dialog._edit_declared",
             amb.AmbiguityDialog._edit_declared),
            ("ambiguity_dialog._adopt_component",
             amb.AmbiguityDialog._adopt_component)):
        src = inspect.getsource(fn)
        before, sep, after = src.partition("DeclareComponentDialog(")
        if not sep:
            failures.append(f"{label} : n'ouvre plus le formulaire ?")
            continue
        if "old_lib" not in before:
            failures.append(f"{label} : old_lib n'est pas capture AVANT "
                            f"l'ouverture du formulaire")
        if "old_lib" not in after:
            failures.append(f"{label} : old_lib capture mais jamais utilise "
                            f"apres")
    assert not failures, failures


def test_the_beginner_door_notifies_through_the_common_hook():
    """`_open_declare_dialog_for_entry` doit passer par le point de passage
    commun, pas reimplementer sa regle dans son coin."""
    import inspect
    src = inspect.getsource(sv.StudioView._open_declare_dialog_for_entry)
    assert "notify_lib_chosen_in_form" in src


TESTS = [
    test_a_replaced_library_reaches_the_regeneration_hook,
    test_the_token_is_the_name_lowercased_never_the_id,
    test_an_unchanged_library_says_nothing,
    test_whitespace_alone_is_not_a_change,
    test_a_cancelled_or_removed_form_says_nothing,
    test_clearing_the_library_is_a_change_too,
    test_the_advanced_modal_exposes_the_signal_that_reaches_the_studio,
    test_both_schema_doors_capture_the_old_library_before_opening,
    test_the_beginner_door_notifies_through_the_common_hook,
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
    # Detruire des QDialog pendant le teardown Qt statique plante le process
    # sous Windows APRES que les assertions ont deja tranche.
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
