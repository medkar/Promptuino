"""Le choix du modele s'enregistre a la selection, sans bouton (Task 3, spec
2026-09-03, decision D).

Avant ce correctif, le modele n'etait persiste qu'au clic sur << Enregistrer >>
-- un bouton place dans la ligne de la CLE D'API. Changer de modele et fermer
l'ecran laissait la config sur l'ANCIEN modele : c'est le defaut le plus
couteux du chantier (l'utilisateur a change de modele, la generation a
continue d'utiliser le precedent, avec un message d'erreur dont la cause etait
fausse).

Run: python scripts/test_model_choice_is_saved.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Importer ui.ia_view charge PyQt6 : il faut une QApplication vivante avant
# tout, meme si les widgets construits ici ne sont jamais affiches (motif de
# scripts/test_resemblance_notice.py).
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)

import ui.ia_view as ia_view
from ui.ia_view import _CloudSection as CloudSection

_SRC = (ROOT / "ui" / "ia_view.py").read_text(encoding="utf-8")

# ── Ne JAMAIS toucher la vraie config utilisateur ──────────────────────────
# `~/Documents/Promptuino/data/config.json` porte le reglage REEL de
# l'utilisateur (il vient justement de le reparer a la main). On bouchonne
# ai_config.set_model / set_api_key pour toute la duree du fichier, et on
# verifie le fichier sur disque avant/apres par securite supplementaire.
from ui.ai_config import CONFIG_PATH, ai_config as _ai_config


def _config_snapshot() -> str | None:
    return CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else None


class _Recorder:
    """Bouchon d'ecriture : enregistre les appels au lieu de persister quoi
    que ce soit sur disque ou dans le trousseau Windows."""

    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)


def _stubbed_section():
    """Construit une VRAIE CloudSection (widgets reels, comportement reel),
    mais avec ai_config entierement bouchonne : aucune lecture ne depend de
    la machine (donc pas de fetch reseau au demarrage si une cle existe deja
    dans le trousseau), et aucune ecriture n'atteint le disque/trousseau.

    Rend (section, set_model_recorder, set_api_key_recorder, restore).
    `restore()` remet ai_config dans l'etat trouve, a appeler dans un
    `finally`.
    """
    orig_api_key = _ai_config.api_key
    orig_model_for = _ai_config.model_for
    orig_set_model = _ai_config.set_model
    orig_set_api_key = _ai_config.set_api_key

    set_model_calls = _Recorder()
    set_api_key_calls = _Recorder()

    # Aucune cle "vue" -> _maybe_fetch_models() ne demarre aucun worker
    # reseau, quel que soit le trousseau de la machine qui execute le test.
    _ai_config.api_key = lambda pid: ""
    _ai_config.model_for = lambda pid: ""
    _ai_config.set_model = set_model_calls
    _ai_config.set_api_key = set_api_key_calls

    def restore():
        _ai_config.api_key = orig_api_key
        _ai_config.model_for = orig_model_for
        _ai_config.set_model = orig_set_model
        _ai_config.set_api_key = orig_set_api_key

    try:
        section = CloudSection()
    except Exception:
        restore()
        raise
    # Task 4 (spec 2026-09-03, B) a branche une VERIFICATION reseau sur
    # _on_model_chosen, apres la persistance sous test ici. Ce fichier ne
    # teste que la persistance : la sonde est coupee pour qu'aucun de ses
    # tests ne parte faire un appel reseau reel en arriere-plan (voir
    # scripts/test_model_probe.py pour la sonde elle-meme).
    section._start_model_probe = lambda *_a, **_kw: None
    return section, set_model_calls, set_api_key_calls, restore


# ── 1. Sur le code source : les DEUX signaux sont branches ────────────────

def test_activated_is_wired_to_the_save_hook():
    """Un choix dans la liste (clic) doit appeler _on_model_chosen."""
    assert "_model_combo.activated.connect(self._on_model_chosen)" in _SRC, \
        "le signal `activated` du combo modele n'est plus branche"


def test_editing_finished_is_wired_to_the_save_hook():
    """Une saisie au clavier ne doit s'enregistrer qu'A LA VALIDATION."""
    assert "editingFinished.connect(self._on_model_chosen)" in _SRC, \
        "editingFinished du lineEdit du combo modele n'est plus branche"


def test_text_edited_is_never_wired():
    """`textEdited` ecrirait un id incomplet a CHAQUE caractere : il ne doit
    jamais etre connecte a la persistance."""
    assert "textEdited.connect(self._on_model_chosen)" not in _SRC


def test_on_save_is_no_longer_the_only_writer():
    """`ai_config.set_model(` doit apparaitre a au moins DEUX endroits :
    `_on_save` (bouton, inchange) et `_on_model_chosen` (nouveau)."""
    assert _SRC.count("ai_config.set_model(") >= 2, \
        "set_model() n'a qu'un seul appelant -- la persistance a la " \
        "selection n'a pas ete branchee"


# ── 2. Comportement : un choix dans la liste ecrit ─────────────────────────

def test_picking_from_the_list_writes_the_expected_pair():
    section, set_model_calls, _, restore = _stubbed_section()
    try:
        assert section.selected_provider_id() == "gemini", \
            "le fournisseur par defaut a change -- adapter le test"
        combo = section._model_combo
        # setCurrentText() seul n'emet PAS `activated` (Qt ne l'emet que sur
        # un geste utilisateur reel) : on pose le texte puis on simule le
        # choix, exactement comme scripts/test_studio_console_panel.py le
        # fait pour les signaux internes des panels.
        combo.setCurrentText("gemini-3.5-flash")
        combo.activated.emit(0)
        assert set_model_calls.calls == [("gemini", "gemini-3.5-flash")], \
            set_model_calls.calls
    finally:
        restore()


def test_validating_a_typed_model_writes_it():
    """Entree / perte de focus (editingFinished) = validation -> ecrit."""
    section, set_model_calls, _, restore = _stubbed_section()
    try:
        edit = section._model_combo.lineEdit()
        assert edit is not None
        edit.setText("mon-modele-tape")
        edit.editingFinished.emit()
        assert set_model_calls.calls == [("gemini", "mon-modele-tape")], \
            set_model_calls.calls
    finally:
        restore()


# ── 3. Comportement : une frappe caractere par caractere n'ecrit PAS ───────

def test_typing_character_by_character_writes_nothing():
    """`textEdited` (frappe) ne doit JAMAIS declencher set_model -- seule la
    validation (editingFinished) le fait."""
    section, set_model_calls, _, restore = _stubbed_section()
    try:
        edit = section._model_combo.lineEdit()
        assert edit is not None
        texte = ""
        for ch in "gemini-3.5-flash":
            texte += ch
            edit.setText(texte)
            edit.textEdited.emit(texte)
        assert set_model_calls.calls == [], \
            f"la frappe a ecrit {len(set_model_calls.calls)} fois: " \
            f"{set_model_calls.calls}"
        # La validation qui suit, elle, doit ecrire une seule fois -- preuve
        # que le combo etait bien fonctionnel pendant la frappe.
        edit.editingFinished.emit()
        assert set_model_calls.calls == [("gemini", "gemini-3.5-flash")]
    finally:
        restore()


# ── 4. Un remplissage PROGRAMMATIQUE n'ecrit jamais ────────────────────────

def test_set_model_text_does_not_write():
    """`_set_model_text` bloque les signaux : un remplissage programmatique
    (ex. changement de fournisseur) ne doit jamais persister."""
    section, set_model_calls, _, restore = _stubbed_section()
    try:
        section._set_model_text("gemini-2.5-flash-programmatique")
        assert set_model_calls.calls == []
    finally:
        restore()


def test_reload_fields_does_not_write():
    """Un rechargement de champs (changement de fournisseur) ne doit pas
    reecrire le modele qu'il vient de recharger."""
    section, set_model_calls, _, restore = _stubbed_section()
    try:
        section._reload_fields()
        assert set_model_calls.calls == []
    finally:
        restore()


def test_async_model_list_arrival_does_not_write():
    """L'arrivee asynchrone de la liste des modeles (_on_models_fetched) ne
    doit jamais ecraser le choix de l'utilisateur en silence."""
    section, set_model_calls, _, restore = _stubbed_section()
    try:
        section._on_models_fetched(
            "gemini", ["gemini-3.5-flash", "gemini-2.5-flash"], "")
        assert set_model_calls.calls == []
    finally:
        restore()


# ── 5. Le bouton << Enregistrer >> continue de fonctionner pour la cle ────

def test_the_save_button_still_persists_key_and_model():
    """La cle d'API GARDE son bouton (champ mot de passe : jamais a la
    volee). _on_save doit continuer d'ecrire la cle ET le modele."""
    section, set_model_calls, set_api_key_calls, restore = _stubbed_section()
    try:
        section._key_input.setText("")  # vide -> pas de fetch reseau declenche
        section._model_combo.setCurrentText("gemini-3.5-flash")
        section._on_save()
        assert set_api_key_calls.calls == [("gemini", "")], \
            set_api_key_calls.calls
        assert set_model_calls.calls == [("gemini", "gemini-3.5-flash")], \
            set_model_calls.calls
    finally:
        restore()


TESTS = [
    test_activated_is_wired_to_the_save_hook,
    test_editing_finished_is_wired_to_the_save_hook,
    test_text_edited_is_never_wired,
    test_on_save_is_no_longer_the_only_writer,
    test_picking_from_the_list_writes_the_expected_pair,
    test_validating_a_typed_model_writes_it,
    test_typing_character_by_character_writes_nothing,
    test_set_model_text_does_not_write,
    test_reload_fields_does_not_write,
    test_async_model_list_arrival_does_not_write,
    test_the_save_button_still_persists_key_and_model,
]


def main() -> int:
    before = _config_snapshot()
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    after = _config_snapshot()
    if before != after:
        failed += 1
        print("  FAIL config utilisateur MODIFIEE par les tests -- "
              f"{CONFIG_PATH} a change")
    else:
        print(f"  (config utilisateur inchangee : {CONFIG_PATH})")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
