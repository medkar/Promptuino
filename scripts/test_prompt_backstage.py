"""TODO #42 — « Coulisses du prompt » : voir le prompt ET pouvoir l'envoyer.

Avant, c'etait un OU-BIEN. `_DEBUG_SHOW_PROMPT`, une case du menu Aide,
faisait sortir les deux chemins de generation par un `return` sec avant
d'appeler le backend : on voyait le prompt, ou on generait, jamais les deux.
Pour regarder puis lancer vraiment, il fallait rouvrir le menu, decocher, et
recommencer.

Trois changements, verrouilles ici :

  1. la modale est une ETAPE — deux boutons, Annuler garde le comportement
     d'avant, Envoyer poursuit avec EXACTEMENT le message affiche ;
  2. le message utilisateur est MODIFIABLE, le prompt systeme ne l'est pas
     (c'est l'ingenierie de l'app, et le rendre modifiable demanderait de
     faire passer un prompt systeme personnalise dans tous les backends) ;
  3. l'option a quitte le menu Aide pour Parametres, et elle est PERSISTEE —
     la non-persistance etait justifiee par le statut « fonction de
     developpeur », qui tombe avec le renommage.

⚠️ Consequence assumee d'un message modifie : le prompt cesse d'etre
reproductible depuis l'etat du projet. La Feature garde la demande ecrite par
l'utilisateur, donc un ↻ ulterieur ne le reproduira pas. Ca doit se DIRE
(`backstage_edited`), pas se decouvrir.

Run : python scripts/test_prompt_backstage.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QPushButton
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui.i18n import TRANSLATIONS, lang_manager
from ui.session import session
from ui.studio.generation_flow import (GenerateWorker, PromptPreviewDialog,
                                       build_codegen_parts,
                                       build_codegen_preview)

session._save = lambda: None            # ne JAMAIS ecrire le vrai session.json

LANGS = ("fr", "en", "es", "it")


class _StubBackend:
    def codegen_system_prompt(self, board_name, rules_prompt=None):
        return f"SYSTEM for {board_name} :: {rules_prompt}"

    def generate_code(self, prompt, board_name, rules_prompt=None):
        self.sent = prompt
        return "void setup(){}"


def _dialog(system="SYS", user="USER"):
    return PromptPreviewDialog("titre", system, user)


# ── La modale est une etape, pas un cul-de-sac ────────────────────────────────

def test_it_offers_cancel_and_send_not_a_single_close():
    dlg = _dialog()
    libelles = {b.text() for b in dlg.findChildren(QPushButton)}
    s = lang_manager.current
    assert s.backstage_send in libelles, libelles
    assert s.studio_cancel in libelles, libelles
    assert "Fermer" not in libelles, "l'ancien cul-de-sac est de retour"


def test_cancel_rejects_and_send_accepts():
    dlg = _dialog()
    s = lang_manager.current
    boutons = {b.text(): b for b in dlg.findChildren(QPushButton)}
    boutons[s.studio_cancel].click()
    assert dlg.result() == QDialog.DialogCode.Rejected

    dlg2 = _dialog()
    {b.text(): b for b in dlg2.findChildren(QPushButton)}[s.backstage_send].click()
    assert dlg2.result() == QDialog.DialogCode.Accepted


def test_no_button_steals_the_enter_key():
    """Meme classe de bug que le champ de zoom du schema et que la recherche
    de la modale de swap : Entree dans la zone editable ne doit pas valider."""
    dlg = _dialog()          # garder la ref : sinon Qt detruit le parent et
    for b in dlg.findChildren(QPushButton):   # les enfants sous nos pieds
        assert not b.autoDefault(), b.text()
        assert not b.isDefault(), b.text()


# ── Ce qui est modifiable, et ce qui ne l'est pas ─────────────────────────────

def test_the_user_message_is_editable_and_the_system_prompt_is_not():
    dlg = _dialog("SYS", "USER")
    editors = dlg.findChildren(QPlainTextEdit)
    assert len(editors) == 2, len(editors)
    par_texte = {e.toPlainText(): e for e in editors}
    assert par_texte["SYS"].isReadOnly(), "le prompt systeme doit rester fige"
    assert not par_texte["USER"].isReadOnly(), "le message doit etre modifiable"


def test_it_returns_the_edited_message():
    dlg = _dialog("SYS", "USER")
    assert dlg.user_message() == "USER"
    assert not dlg.edited()
    next(e for e in dlg.findChildren(QPlainTextEdit)
         if not e.isReadOnly()).setPlainText("AUTRE")
    assert dlg.user_message() == "AUTRE"
    assert dlg.edited(), "une modification doit se signaler"


def test_an_emptied_message_still_counts_as_a_message():
    """Le sentinel d'annulation existe pour ca : vider la zone est une
    modification, pas une annulation, et une chaine vide ne doit pas se lire
    comme « annule »."""
    dlg = _dialog("SYS", "USER")
    next(e for e in dlg.findChildren(QPlainTextEdit)
         if not e.isReadOnly()).setPlainText("")
    assert dlg.user_message() == ""
    assert dlg.edited()


# ── Fidelite : la modale montre ce que le worker enverra ──────────────────────

def test_the_two_panes_are_exactly_what_the_worker_composes():
    be = _StubBackend()
    system, user_msg = build_codegen_parts(
        be, "fais clignoter une led", "Arduino Uno", "advanced", 2,
        rules_prompt="brut")
    assert system == be.codegen_system_prompt("Arduino Uno", "brut")
    assert user_msg == GenerateWorker.compose_user_prompt(
        "fais clignoter une led", "advanced", 2)


def test_the_glued_preview_still_matches_the_parts():
    """`build_codegen_preview` garde trois tests a lui
    (test_codegen_preview_gating). Il doit rester colle sur les memes morceaux,
    sinon l'aperçu et la modale divergeraient en silence."""
    be = _StubBackend()
    system, user_msg = build_codegen_parts(be, "p", "Uno", "beginner", 2)
    colle = build_codegen_preview(be, "p", "Uno", "beginner", 2)
    assert system in colle and user_msg in colle


def test_a_validated_message_is_sent_verbatim_not_recomposed():
    """Le piege : le message affiche contient DEJA les directives de
    commentaires. Le recomposer les ajouterait une seconde fois."""
    be = _StubBackend()
    valide = GenerateWorker.compose_user_prompt("p", "advanced", 2)
    w = GenerateWorker(be, "p", "Uno", "advanced", 2, user_message=valide)
    w.run()                               # synchrone, pas de thread ici
    assert be.sent == valide
    assert be.sent.count("Target audience") == 1, be.sent


def test_without_the_feature_the_worker_composes_as_before():
    be = _StubBackend()
    GenerateWorker(be, "p", "Uno", "advanced", 2).run()
    assert be.sent == GenerateWorker.compose_user_prompt("p", "advanced", 2)


# ── L'option : emplacement et persistance ────────────────────────────────────

def test_the_preference_is_persisted():
    import ui.studio_view as SV
    avant = session.prompt_backstage
    try:
        SV.set_debug_show_prompt(True)
        assert session.prompt_backstage is True
        assert SV.debug_show_prompt_enabled() is True
        SV.set_debug_show_prompt(False)
        assert session.prompt_backstage is False
    finally:
        session.prompt_backstage = avant


def test_it_defaults_to_off():
    session._data.pop("prompt_backstage", None)
    assert session.prompt_backstage is False


def test_the_help_menu_no_longer_carries_it():
    """Verrou par la source : l'action du menu Aide doit avoir disparu, sinon
    deux endroits piloteraient la meme preference."""
    src = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "_act_debug_prompt" not in src
    assert "mn_debug_prompt" not in src


def test_the_shared_helper_never_clears_the_generation_state():
    """Verrou par la source. `_gen_busy` vaut « beginner » ou « advanced »
    selon le chemin ; un `_set_generating(False)` DANS le helper partage le
    remettrait a zero meme quand l'utilisateur ENVOIE — bouton debutant
    restaure pendant qu'une generation tourne. La restauration appartient a
    chaque appelant, sur la branche d'annulation seulement."""
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    debut = src.index("def _prompt_backstage")
    fin = src.index("def _resolve_lib_ambiguity")
    corps = src[debut:fin]
    assert "_set_generating" not in corps, corps
    # Et il rend la main au journal quand — et seulement quand — ca part.
    assert "_stop_gen_loader" in corps and "_start_gen_loader" in corps


def test_the_settings_page_exists_and_drives_the_session():
    from ui.settings_dialog import _BackstagePage
    avant = session.prompt_backstage
    try:
        session.prompt_backstage = False
        page = _BackstagePage()
        page._chk.setChecked(True)
        assert session.prompt_backstage is True
        page._chk.setChecked(False)
        assert session.prompt_backstage is False
    finally:
        session.prompt_backstage = avant


# ── i18n : c'est une fonction utilisateur, plus un outil de dev ───────────────

def test_every_label_is_translated_in_the_four_languages():
    cles = ("settings_backstage", "backstage_enable", "backstage_desc",
            "backstage_title", "backstage_system", "backstage_user",
            "backstage_chars", "backstage_send", "backstage_edited")
    for code in LANGS:
        s = TRANSLATIONS[code]
        for cle in cles:
            assert getattr(s, cle, "").strip(), f"{code}/{cle}"


def test_the_dialog_takes_its_labels_from_the_current_language():
    """Le libelle « Prompt final (N caracteres) » et les quatre titres etaient
    codes en dur en francais — invisible tant que c'etait un outil de dev."""
    for code in ("en", "es", "it"):
        lang_manager.set_language(code)
        try:
            dlg = _dialog()
            textes = {b.text() for b in dlg.findChildren(QPushButton)}
            assert TRANSLATIONS[code].backstage_send in textes, (code, textes)
        finally:
            lang_manager.set_language("fr")


def test_the_word_debug_is_gone_from_the_user_facing_labels():
    for code in LANGS:
        s = TRANSLATIONS[code]
        for cle in ("settings_backstage", "backstage_enable", "backstage_title"):
            assert "debug" not in getattr(s, cle).lower(), f"{code}/{cle}"
            assert "débug" not in getattr(s, cle).lower(), f"{code}/{cle}"


TESTS = [
    test_it_offers_cancel_and_send_not_a_single_close,
    test_cancel_rejects_and_send_accepts,
    test_no_button_steals_the_enter_key,
    test_the_user_message_is_editable_and_the_system_prompt_is_not,
    test_it_returns_the_edited_message,
    test_an_emptied_message_still_counts_as_a_message,
    test_the_two_panes_are_exactly_what_the_worker_composes,
    test_the_glued_preview_still_matches_the_parts,
    test_a_validated_message_is_sent_verbatim_not_recomposed,
    test_without_the_feature_the_worker_composes_as_before,
    test_the_preference_is_persisted,
    test_it_defaults_to_off,
    test_the_help_menu_no_longer_carries_it,
    test_the_shared_helper_never_clears_the_generation_state,
    test_the_settings_page_exists_and_drives_the_session,
    test_every_label_is_translated_in_the_four_languages,
    test_the_dialog_takes_its_labels_from_the_current_language,
    test_the_word_debug_is_gone_from_the_user_facing_labels,
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
