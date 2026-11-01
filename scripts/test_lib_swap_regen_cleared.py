"""« Laisser l'app decider » ne doit jamais affirmer qu'une bibliotheque a ete
CHOISIE quand elle a ete EFFACEE.

Contexte du bug (revue 2026-08-12) : les portes 1 et 2 de `studio_view.py`
mettaient en file `(old, "")` pour un effacement, exactement comme `(old,
new)` pour un vrai changement. `_offer_lib_swap_regeneration` filtre les
chaines vides avant de joindre `new` pour la popup -- donc un effacement SEUL
rendait `new = ""`, et la popup (`lib_swap_regen_body`, qui affirme "tu as
choisi la librairie {new}") affichait litteralement « tu as choisi la
librairie —, mais le code utilise encore {old} ». Un mensonge : l'utilisateur
n'a rien choisi, il a efface son choix. Pire dans un lot MIXTE (un changement
+ un effacement dans la meme offre groupee) : l'effacement disparaissait de
`new` mais restait dans `old`, imputant a un vrai changement un effacement
qui n'a rien a voir.

Le correctif routes CHAQUE lot contenant au moins un effacement vers un
message dedie (`lib_swap_regen_body_cleared`) qui ne nomme jamais de nouvelle
bibliotheque -- seul `{old}` (ce que le code utilise encore) y figure, vrai
pour TOUT le lot. Un lot de changements purs garde le message d'avant, mot
pour mot (garde anti-regression).

Ce fichier teste :
  1. le ROUTAGE de `_offer_lib_swap_regeneration` (cleared-only / mixte /
     changements purs) directement sur des paires injectees ;
  2. les DEUX portes (`_on_change_lib_requested`, `on_change_lib_for_component`)
     de bout en bout avec `clear_requested=True`, y compris le cas "rien a
     effacer" (`current == ""`) qui ne doit RIEN proposer du tout.

Run : python scripts/test_lib_swap_regen_cleared.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level

import ui.component_libs as cl_mod
import ui.lib_choice_dialog as lcd_mod
import ui.registry_lookup as rl_mod
from ui.studio_view import StudioView


# ─── 1. Routage de _offer_lib_swap_regeneration ──────────────────────────
def _sv_with_pending(pairs, ids):
    """StudioView minimal, dote uniquement de ce que la methode lit/appelle :
    la file en attente, et les 3 methodes qu'elle route entre."""
    sv = StudioView.__new__(StudioView)
    sv._pending_lib_swap_ids = set(ids)
    sv._pending_lib_swap_pairs = list(pairs)
    calls = []

    def _changed(old, new):
        calls.append(("changed", old, new))
        return False  # jamais de vraie regeneration ici : on teste le ROUTAGE

    def _cleared(old):
        calls.append(("cleared", old))
        return False

    def _regen(ids):
        calls.append(("regen", ids))

    sv._confirm_lib_swap_regen = _changed
    sv._confirm_lib_swap_regen_cleared = _cleared
    sv._regenerate_features = _regen
    return sv, calls


def test_a_pure_changes_lot_uses_the_original_message_unchanged():
    """Garde anti-regression : SANS effacement dans le lot, le chemin est
    identique a avant -- `_confirm_lib_swap_regen(old, new)`, jamais le
    sibling « cleared »."""
    sv, calls = _sv_with_pending([("Old1", "New1")], {1})
    StudioView._offer_lib_swap_regeneration(sv)
    assert calls == [("changed", "Old1", "New1")], calls


def test_a_cleared_only_lot_uses_the_cleared_message():
    sv, calls = _sv_with_pending([("OldX", "")], {2})
    StudioView._offer_lib_swap_regeneration(sv)
    assert calls == [("cleared", "OldX")], calls


def test_a_mixed_lot_uses_the_cleared_message_with_both_olds():
    """LE cas que la revue a repere : un changement ET un effacement dans le
    meme lot. Aucune phrase nommant une "nouvelle" bibliotheque n'est vraie
    pour TOUT le lot -- le message cleared l'emporte, et cite les DEUX
    anciennes bibliotheques (celle du changement ET celle de l'effacement),
    jamais seulement l'une des deux."""
    sv, calls = _sv_with_pending(
        [("OldChanged", "NewLib"), ("OldCleared", "")], {3, 4})
    StudioView._offer_lib_swap_regeneration(sv)
    assert calls == [("cleared", "OldChanged, OldCleared")], calls


def test_confirming_the_cleared_popup_still_regenerates():
    """L'offre de regenerer garde tout son sens apres un effacement -- ce
    n'est PAS un no-op deguise."""
    sv, calls = _sv_with_pending([("OldX", "")], {5})
    sv._confirm_lib_swap_regen_cleared = lambda old: True
    StudioView._offer_lib_swap_regeneration(sv)
    assert calls == [("regen", {5})], calls


def test_declining_the_cleared_popup_does_not_regenerate():
    sv, calls = _sv_with_pending([("OldX", "")], {6})
    StudioView._offer_lib_swap_regeneration(sv)
    assert ("regen", {6}) not in calls, calls


# ─── 2. Les portes, de bout en bout ───────────────────────────────────────
class _FakeDlg:
    """Remplace `LibChoiceDialog` : `.exec()` "accepte" toujours, et porte
    les TROIS champs que les portes lisent apres coup.

    ⚠️ La signature suit celle de la vraie modale, `current_no_lib` compris
    (TODO #51). Un `**kwargs` fourre-tout aurait fait passer ce test au vert
    sans qu'aucune porte ne transmette le nouvel etat -- c'est justement ce
    qu'on veut voir rougir."""

    def __init__(self, parent, *, token, current_lib, alternatives,
                config_file, arch, current_no_lib=False):
        self.token, self.current_lib = token, current_lib
        self.alternatives, self.config_file, self.arch = (
            alternatives, config_file, arch)
        self.current_no_lib = current_no_lib
        self.chosen_lib = ""
        self.clear_requested = False
        self.no_library_requested = False

    def exec(self):
        return 1  # QDialog.DialogCode.Accepted


def _clearing_dialog_factory():
    def _make(parent, **kw):
        dlg = _FakeDlg(parent, **kw)
        dlg.clear_requested = True
        return dlg
    return _make


def _patched(attrs: dict):
    """Contexte : remplace des attributs de MODULE (les portes font des
    `from .x import y` LOCAUX a chaque appel -- patcher le module avant
    d'appeler suffit, pas besoin de mock plus invasif), les restaure a la
    sortie meme si le test echoue. `attrs` : {(module, "name"): valeur}."""
    class _Ctx:
        def __enter__(self):
            self._saved = []
            for (mod, name), value in attrs.items():
                self._saved.append((mod, name, getattr(mod, name)))
                setattr(mod, name, value)
            return self

        def __exit__(self, *exc):
            for mod, name, old in self._saved:
                setattr(mod, name, old)
            return False
    return _Ctx()


def test_door1_clear_with_a_known_current_clears_and_queues():
    """Porte 1 (banniere), boucle : `clear_requested=True` avec une
    bibliotheque actuellement connue doit effacer la preference ET mettre en
    file le hook de regeneration -- de bout en bout, pas juste au niveau du
    routage."""
    calls = []
    with _patched({
        (lcd_mod, "LibChoiceDialog"): _clearing_dialog_factory(),
        (cl_mod, "clear_preference"):
            lambda token: calls.append(("clear_pref", token)) or True,
    }):
        sv = StudioView.__new__(StudioView)
        sv._registry_choices = [("veml7700", "Old Lib", ["Alt"])]
        sv._registry_config_file = lambda: None
        sv._board_architecture = lambda: ""
        sv._after_lib_preference_changed = (
            lambda *a: calls.append(("hook",) + a))
        sv._offer_lib_swap_regeneration = lambda: calls.append(("offer",))
        StudioView._on_change_lib_requested(sv)
    assert calls == [
        ("clear_pref", "veml7700"),
        ("hook", "veml7700", "Old Lib", ""),
        ("offer",),
    ], calls


def test_door2_clear_with_a_known_current_clears_and_queues():
    """Meme scenario que ci-dessus, porte 2 (fiche Composants) : pas de
    boucle, l'offre suit immediatement le changement."""
    calls = []
    with _patched({
        (lcd_mod, "LibChoiceDialog"): _clearing_dialog_factory(),
        (cl_mod, "clear_preference"):
            lambda token: calls.append(("clear_pref", token)) or True,
        (cl_mod, "preferred_lib_for"): lambda token: "Old Lib",
        (rl_mod, "cached_lookups"): lambda: {},
    }):
        sv = StudioView.__new__(StudioView)
        sv._registry_config_file = lambda: None
        sv._board_architecture = lambda: ""
        sv._after_lib_preference_changed = (
            lambda *a: calls.append(("hook",) + a))
        sv._offer_lib_swap_regeneration = lambda: calls.append(("offer",))
        StudioView.on_change_lib_for_component(sv, "veml7700")
    assert calls == [
        ("clear_pref", "veml7700"),
        ("hook", "veml7700", "Old Lib", ""),
        ("offer",),
    ], calls


def test_door1_clear_with_nothing_to_clear_offers_nothing():
    """Le trou signale par la revue : `current == ""` (cette entree n'avait
    deja AUCUNE preference connue). Effacer un choix qui n'existe pas ne doit
    RIEN faire -- ni ecriture, ni hook, ni popup (« — / — » vide de sens).
    Utilise le VRAI `_offer_lib_swap_regeneration` (pas un mock) pour prouver
    que la chaine complete ne produit aucune popup, pas seulement que le hook
    n'est pas appele."""
    calls = []
    with _patched({
        (lcd_mod, "LibChoiceDialog"): _clearing_dialog_factory(),
        (cl_mod, "clear_preference"):
            lambda token: calls.append(("clear_pref", token)) or True,
    }):
        sv = StudioView.__new__(StudioView)
        sv._registry_choices = [("veml7700", "", ["Alt"])]  # current == ""
        sv._registry_config_file = lambda: None
        sv._board_architecture = lambda: ""
        sv._after_lib_preference_changed = (
            lambda *a: calls.append(("hook",) + a))
        sv._pending_lib_swap_ids = set()
        sv._pending_lib_swap_pairs = []
        sv._confirm_lib_swap_regen = (
            lambda old, new: calls.append(("changed", old, new)) or False)
        sv._confirm_lib_swap_regen_cleared = (
            lambda old: calls.append(("cleared", old)) or False)
        sv._regenerate_features = lambda ids: calls.append(("regen", ids))
        StudioView._on_change_lib_requested(sv)
    # Ni ecriture ni hook -- et surtout, la vraie `_offer_lib_swap_regeneration`
    # (appelee en fin de boucle, sans rien en file) ne produit AUCUNE popup.
    assert calls == [], calls


def test_door2_clear_with_nothing_to_clear_offers_nothing():
    """Meme garde, porte 2 -- cas REEL ici (contrairement a la porte 1) :
    `preferred_lib_for` et le cache registre peuvent tous deux etre vides
    pour une fiche jamais resolue."""
    calls = []
    with _patched({
        (lcd_mod, "LibChoiceDialog"): _clearing_dialog_factory(),
        (cl_mod, "clear_preference"):
            lambda token: calls.append(("clear_pref", token)) or True,
        (cl_mod, "preferred_lib_for"): lambda token: "",
        (rl_mod, "cached_lookups"): lambda: {},
    }):
        sv = StudioView.__new__(StudioView)
        sv._registry_config_file = lambda: None
        sv._board_architecture = lambda: ""
        sv._after_lib_preference_changed = (
            lambda *a: calls.append(("hook",) + a))
        sv._offer_lib_swap_regeneration = lambda: calls.append(("offer",))
        StudioView.on_change_lib_for_component(sv, "unknownpart")
    assert calls == [], calls


TESTS = [
    test_a_pure_changes_lot_uses_the_original_message_unchanged,
    test_a_cleared_only_lot_uses_the_cleared_message,
    test_a_mixed_lot_uses_the_cleared_message_with_both_olds,
    test_confirming_the_cleared_popup_still_regenerates,
    test_declining_the_cleared_popup_does_not_regenerate,
    test_door1_clear_with_a_known_current_clears_and_queues,
    test_door2_clear_with_a_known_current_clears_and_queues,
    test_door1_clear_with_nothing_to_clear_offers_nothing,
    test_door2_clear_with_nothing_to_clear_offers_nothing,
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
