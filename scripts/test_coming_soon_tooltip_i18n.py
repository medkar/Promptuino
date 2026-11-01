"""L'infobulle ESP32 « Bientot disponible » suit-elle la langue, sur les TROIS
sites qui la posent ?

Contexte : cette infobulle est posee A LA CONSTRUCTION du bouton
(`btn.setToolTip(lang_manager.current.board_coming_soon)`). Si `apply_lang` ne
la repose pas, elle reste figee dans la langue du premier affichage — un
utilisateur en anglais lit « Bientot disponible ». L'oubli a ete commis TROIS
fois : `board_view.py` et `projects_view.py` (corriges le 2026-08-11), puis
`library_view.py` (Parametres > Bibliotheques), corrige ici.

Le test construit les VRAIS widgets, lit le tooltip, change la langue, relit :
c'est ce que les gardes statiques de i18n ne voient pas (elles verifient que la
CLE existe dans les 4 langues, jamais que le widget va la relire).

Un 4e site est couvert par `test_no_module_sets_the_tooltip_without_refreshing_it`,
un balayage AST de `ui/` : tout module qui POSE l'infobulle doit la reposer dans
un `apply_lang`. Limite assumee : la granularite est le FICHIER, pas la classe.
`projects_view._NewProjectDialog` pose l'infobulle sur un item de combo sans la
reposer et n'est pas signale — sans consequence ici (modale courte, reconstruite
a chaque ouverture, la langue ne peut pas changer pendant qu'elle est modale),
mais un 4e site ajoute dans un fichier qui corrige DEJA le sien passerait entre
les mailles.
"""
from __future__ import annotations
import ast
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from ui.i18n import lang_manager, TRANSLATIONS
from ui.board_manager import COMING_SOON_ENVS

FR = TRANSLATIONS["fr"].board_coming_soon      # « Bientot disponible »
EN = TRANSLATIONS["en"].board_coming_soon      # « Coming soon »


def _reset_lang():
    lang_manager.set_language("fr")


class _StubProjectManager:
    """ProjectsView only calls `list_projects` while it is being built. A stub
    keeps the test off the user's real project folder (no mkdir, no I/O)."""

    def list_projects(self, type_filter=None):
        return []


def _coming_soon_widgets(root) -> list:
    """Every child widget flagged `_coming_soon` (the marker the three sites
    already share), plus the root itself if it carries the flag."""
    from PyQt6.QtWidgets import QWidget
    found = [w for w in root.findChildren(QWidget)
             if getattr(w, "_coming_soon", False)]
    if getattr(root, "_coming_soon", False):
        found.append(root)
    return found


def _check_follows_language(build) -> None:
    """Build the view in French, assert the tooltip is French, switch to
    English, assert it followed. Shared body of the three site tests."""
    _reset_lang()
    view = build()
    widgets = _coming_soon_widgets(view)
    assert widgets, "aucun widget marque _coming_soon : le site a change de forme"

    for w in widgets:
        assert w.toolTip() == FR, (
            f"tooltip a la construction = {w.toolTip()!r}, attendu {FR!r}")

    lang_manager.set_language("en")
    try:
        for w in widgets:
            assert w.toolTip() == EN, (
                f"tooltip fige apres passage en anglais : {w.toolTip()!r}, "
                f"attendu {EN!r} (apply_lang ne repose pas board_coming_soon)")
    finally:
        _reset_lang()

    # Back to French: the refresh must work in both directions.
    for w in widgets:
        assert w.toolTip() == FR, (
            f"tooltip bloque en anglais apres retour au francais : {w.toolTip()!r}")


def test_the_two_reference_strings_actually_differ():
    """Garde anti-test-vide : si FR et EN etaient identiques, les trois tests
    ci-dessous passeraient sans rien verifier."""
    assert FR != EN, "les chaines fr/en sont identiques : le test ne prouve rien"
    assert "esp32" in COMING_SOON_ENVS, "plus aucun env « bientot disponible »"


def test_board_view_tooltip_follows_language():
    from ui.board_view import BoardView
    _check_follows_language(BoardView)


def test_projects_view_tooltip_follows_language():
    from ui.projects_view import ProjectsView
    _check_follows_language(lambda: ProjectsView(pm=_StubProjectManager()))


def test_library_view_tooltip_follows_language():
    from ui import library_view
    # No arduino-cli call: `_refresh_installed` returns early when the CLI is
    # absent, so no QThread and no subprocess are started by the constructor.
    original = library_view.cli_is_available
    library_view.cli_is_available = lambda: False
    try:
        _check_follows_language(library_view.LibraryView)
    finally:
        library_view.cli_is_available = original


def _sets_coming_soon_tooltip(node) -> bool:
    """True if the subtree contains a `…setToolTip(….board_coming_soon)` call.
    Narrower than « the file mentions the key »: `ui/chat/chat_prompts.py` cites
    the same label in an LLM prompt (resolved at call time, no widget), and must
    not be flagged."""
    for n in ast.walk(node):
        if not (isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "setToolTip"):
            continue
        if any(isinstance(a, ast.Attribute) and a.attr == "board_coming_soon"
               for arg in n.args for a in ast.walk(arg)):
            return True
    return False


def test_no_module_sets_the_tooltip_without_refreshing_it():
    """Balayage AST : tout module de `ui/` qui POSE l'infobulle doit aussi la
    reposer dans un `apply_lang`. C'est ce qui rougira pour un 4e site."""
    offenders: list[str] = []
    for path in sorted((ROOT / "ui").rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "board_coming_soon" not in src:
            continue
        tree = ast.parse(src)
        if not _sets_coming_soon_tooltip(tree):
            continue
        refreshed = any(
            isinstance(node, ast.FunctionDef) and node.name == "apply_lang"
            and _sets_coming_soon_tooltip(node)
            for node in ast.walk(tree)
        )
        if not refreshed:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "ces modules posent l'infobulle « bientot disponible » sans la reposer "
        f"dans apply_lang (elle restera figee) : {offenders}")


TESTS = [
    test_the_two_reference_strings_actually_differ,
    test_board_view_tooltip_follows_language,
    test_projects_view_tooltip_follows_language,
    test_library_view_tooltip_follows_language,
    test_no_module_sets_the_tooltip_without_refreshing_it,
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
    _reset_lang()
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    # Meme motif que test_ambiguity_i18n.py : detruire plusieurs vues Qt
    # pendant le teardown statique crashe le process (0xC0000409) sous Windows
    # APRES que les assertions ont deja tranche.
    os._exit(0 if passed == len(TESTS) else 1)
