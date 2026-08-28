"""QA A4b + E1 (2026-08-08) : ce qui est livre SANS avoir compile doit le DIRE,
et le bouton « Uploader » doit suivre le CODE present.

Contexte : `_start_assembly_verify` se contente d'un `return False` quand la
verification est impossible, et l'appelant ecrivait alors « Code pret » -- le
meme libelle, de la meme couleur, qu'un code reellement compile ET repare. Ce
n'est pas un cas limite : `fqbn` est nul des qu'AUCUNE CARTE n'est
selectionnee, l'etat normal d'un debutant qui n'a pas encore branche la sienne.

Run : python scripts/test_unverified_delivery.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui import studio_view as SV
from ui.i18n import lang_manager
from ui.session import session

session._save = lambda: None            # ne jamais ecrire le vrai session.json

_SKETCH = ("void setup() {\n  pinMode(13, OUTPUT);\n}\n"
           "void loop() {\n  digitalWrite(13, HIGH);\n}\n")


def _view():
    v = SV.StudioView()
    v._on_mode_changed("intermediate")
    return v


class _Board:
    """Etat carte simule : `env`/`model` sont ce que lit `_verify_skip_reason`."""
    def __init__(self, env=None, model=None):
        self.env, self.model = env, model


def _with_env(cli_available: bool, board: _Board, fn):
    """Execute `fn` avec arduino-cli et la carte forces, puis restaure."""
    old_avail = SV.arduino_cli.is_available
    old_board = SV.board_manager
    SV.arduino_cli.is_available = lambda: cli_available
    SV.board_manager = board
    try:
        return fn()
    finally:
        SV.arduino_cli.is_available = old_avail
        SV.board_manager = old_board


# ── A4b : dire que le code n'a pas ete compile ───────────────────────────────

def test_no_board_is_named_as_the_reason():
    v = _view()
    reason = _with_env(True, _Board(), v._verify_skip_reason)
    assert reason == lang_manager.current.studio_unverified_no_board, reason


def test_missing_cli_wins_over_the_board():
    """Sans arduino-cli, choisir une carte n'y changerait rien : c'est LUI
    qu'il faut dire, sinon on envoie l'utilisateur brancher du materiel."""
    v = _view()
    reason = _with_env(False, _Board("arduino", "Uno"),
                       v._verify_skip_reason)
    assert reason == lang_manager.current.studio_unverified_no_cli, reason


def test_nothing_is_said_when_verification_can_run():
    # « Uno », pas « uno » : get_fqbn ne resout que le modele tel qu'il est
    # declare dans BOARDS -- un couple invalide passerait pour une absence de
    # carte et le test se croirait vert pour la mauvaise raison.
    from ui.board_manager import get_fqbn
    assert get_fqbn("arduino", "Uno"), "couple carte/modele invalide"
    v = _view()
    reason = _with_env(True, _Board("arduino", "Uno"), v._verify_skip_reason)
    assert reason == "", reason


def test_the_reason_is_translated_everywhere():
    for lang in ("fr", "en", "es", "it"):
        lang_manager.set_language(lang)
        s = lang_manager.current
        assert s.studio_unverified_no_board, lang
        assert s.studio_unverified_no_cli, lang
        # Le conseil doit renvoyer vers l'app, pas vers un telechargement
        # manuel : arduino-cli.exe est BUNDLE dans l'installeur (BUILD.md).
        assert "arduino.cc" not in s.studio_err_no_cli, lang
    lang_manager.set_language("fr")


def test_the_ready_line_carries_the_reason():
    """Le libelle lui-meme doit porter la reserve. Un « Code pret » vert
    suivi d'une note ailleurs se lit comme un succes."""
    lang_manager.set_language("fr")
    v = _view()
    captured = {}

    class _Journal:
        def set_live_line(self, html): captured["html"] = html
        def commit_live_line(self): pass

    v._gen_loader_journal = _Journal()
    v._stop_gen_loader_ready(unverified="non vérifié : aucune carte sélectionnée")
    html = captured["html"]
    assert "aucune carte" in html, html
    from ui.theme import theme_manager
    assert theme_manager.current.signal_warn in html, html   # ambre, pas vert


def test_a_verified_delivery_stays_plain_green():
    lang_manager.set_language("fr")
    v = _view()
    captured = {}

    class _Journal:
        def set_live_line(self, html): captured["html"] = html
        def commit_live_line(self): pass

    v._gen_loader_journal = _Journal()
    v._stop_gen_loader_ready()                       # rien a signaler
    html = captured["html"]
    assert "vérifié" not in html, html
    from ui.theme import theme_manager
    assert theme_manager.current.signal_warn not in html, html


# ── E1 : le bouton « Uploader » suit le code ────────────────────────────────

def test_upload_button_follows_pasted_code():
    """`_has_generated` repond « une generation a-t-elle eu lieu ? » et reste
    faux pour du code colle -- le bouton Schema a ete corrige, celui-ci etait
    reste en arriere."""
    v = _view()
    assert v._has_generated is False
    v._editor.setPlainText(_SKETCH)
    assert v._uploadable() is True
    assert v._btn_upload_only.isEnabled() is True


def test_upload_button_stays_off_on_the_bare_template():
    # LE gabarit de l'editeur, pas un setup/loop ecrit a la main :
    # `is_known_template` compare a des chaines exactes, donc un squelette
    # equivalent mais different EST du vrai code -- et doit rester
    # televersable.
    v = _view()
    v._editor.setPlainText(lang_manager.editor_template())
    assert v._uploadable() is False
    assert v._btn_upload_only.isEnabled() is False


def test_upload_button_ignores_hardware_readiness():
    """Les pre-requis materiels ne grisent PAS le bouton : le preflight les
    verifie au clic et sait dire lequel manque, ce qu'un bouton gris ne peut
    pas faire."""
    v = _view()
    v._editor.setPlainText(_SKETCH)
    assert _with_env(False, _Board(), v._uploadable) is True


TESTS = [
    test_no_board_is_named_as_the_reason,
    test_missing_cli_wins_over_the_board,
    test_nothing_is_said_when_verification_can_run,
    test_the_reason_is_translated_everywhere,
    test_the_ready_line_carries_the_reason,
    test_a_verified_delivery_stays_plain_green,
    test_upload_button_follows_pasted_code,
    test_upload_button_stays_off_on_the_bare_template,
    test_upload_button_ignores_hardware_readiness,
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
