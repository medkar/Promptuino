"""Aucun sous-processus ne doit pouvoir ouvrir une fenetre de console.

⛔ **Le defaut que ce test verrouille a survecu a toute la vie du projet**, et
il a fallu la PREMIERE INSTALLATION du `.exe` (2026-08-31) pour le voir : sur
Windows, une application graphique qui lance un programme console se voit
allouer une console neuve par le systeme -- une fenetre noire apparait le temps
de l'appel. Rediriger `stdout`/`stderr` n'y change rien : l'allocation depend du
sous-systeme de l'executable ENFANT, pas des descripteurs.

Depuis les sources, l'application herite de la console du terminal qui l'a
lancee, l'enfant la reutilise, aucune fenetre n'apparait. **Le defaut n'existe
donc que dans le paquet** -- invisible en developpement, invisible aux tests
d'interface, invisible a la relecture, visible au premier double-clic.

Deux symptomes signales par l'utilisateur, une seule cause :

1. des fenetres de terminal qui clignotent pendant la generation
   (`arduino_cli._run`, appele a chaque compilation) ;
2. **la fenetre de parametres qui se refermait toute seule** :
   `SettingsDialog.changeEvent` ferme la fenetre des qu'elle perd le focus
   (« close on outside click »), et `LibraryView` lance `arduino-cli lib list`
   a sa construction. La console volait l'activation, les parametres se
   fermaient. C'est le meme bug, vu par l'autre bout.

Sur les SEPT invocations que portait `ui/`, une seule passait le drapeau.

⚠️ Ce test lit le code (AST), il ne lance rien : la seule facon de VOIR le
defaut est d'installer le paquet, ce qu'aucune CI ne fait ici. Il ne prouve donc
pas l'absence de fenetre -- il prouve que le drapeau est passe partout, ce qui
est la condition qu'on sait verifier mecaniquement.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

# Fonctions de `subprocess` qui LANCENT un processus.
_LANCEURS = {"run", "Popen", "call", "check_call", "check_output"}

# Exemptions, avec leur raison -- jamais une liste muette. Chaque entree est
# (fichier, nom du programme lance).
#
# `open` et `xdg-open` ne tournent QUE sur macOS et Linux : ils vivent dans les
# branches `elif sys.platform == "darwin"` / `else` d'un `_reveal_folder` dont
# la branche Windows utilise `os.startfile`, qui ne lance aucune console.
# `CREATE_NO_WINDOW` n'existe pas sur ces plateformes (la constante y vaut 0),
# donc le passer serait du bruit qui laisserait croire a une precaution utile.
_EXEMPTES = {
    ("ui/library_view.py", "open"),
    ("ui/library_view.py", "xdg-open"),
    ("ui/projects_view.py", "open"),
    ("ui/projects_view.py", "xdg-open"),
}


def _programme_lance(appel: ast.Call) -> str:
    """Premier element de la commande, quand il est litteral. Sert UNIQUEMENT
    a reconnaitre les exemptions ; un appel dont la commande est calculee n'est
    jamais exempte."""
    if not appel.args:
        return ""
    premier = appel.args[0]
    if isinstance(premier, ast.List) and premier.elts:
        tete = premier.elts[0]
        if isinstance(tete, ast.Constant) and isinstance(tete.value, str):
            return tete.value
    if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
        return premier.value
    return ""


def _spawns(chemin: Path) -> list[tuple[int, str, bool]]:
    """(ligne, programme, passe_le_drapeau) pour chaque lancement du fichier."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        f = noeud.func
        est_lanceur = (
            isinstance(f, ast.Attribute) and f.attr in _LANCEURS
            and isinstance(f.value, ast.Name) and f.value.id == "subprocess"
        )
        if not est_lanceur:
            continue
        drapeau = any(kw.arg == "creationflags" for kw in noeud.keywords)
        trouves.append((noeud.lineno, _programme_lance(noeud), drapeau))
    return trouves


def _fichiers_ui() -> list[Path]:
    return sorted((RACINE / "ui").rglob("*.py"))


def test_every_spawn_hides_its_console():
    """LE test. Un lancement sans `creationflags` fait clignoter une fenetre
    noire dans l'application installee -- et peut, par ricochet, fermer une
    fenetre qui se ferme quand elle perd le focus."""
    fautifs = []
    for f in _fichiers_ui():
        rel = f.relative_to(RACINE).as_posix()
        for ligne, prog, drapeau in _spawns(f):
            if drapeau or (rel, prog) in _EXEMPTES:
                continue
            fautifs.append(f"{rel}:{ligne} lance {prog or '<calcule>'}")
    assert not fautifs, (
        "sous-processus sans creationflags (fenetre de console dans le "
        "paquet) :\n  " + "\n  ".join(fautifs))


def test_the_flag_is_the_shared_constant():
    """Pas de `getattr(subprocess, "CREATE_NO_WINDOW", 0)` recopie sur place :
    une constante partagee est ce qui rend la regle citable dans une revue, et
    c'est la seule version documentee."""
    recopies = [
        f.relative_to(RACINE).as_posix() for f in _fichiers_ui()
        if f.name != "subprocess_flags.py"
        and "CREATE_NO_WINDOW" in f.read_text(encoding="utf-8")
    ]
    assert not recopies, recopies


def test_the_constant_is_neutral_off_windows():
    """`CREATE_NO_WINDOW` n'existe que sur Windows. Ailleurs la constante DOIT
    valoir 0, sans quoi la passer inconditionnellement casserait Linux et macOS
    -- et c'est ce caractere inconditionnel qui fait qu'on ne peut pas l'oublier
    dans une branche de plateforme."""
    import subprocess
    from ui.subprocess_flags import NO_CONSOLE
    attendu = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert NO_CONSOLE == attendu
    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert NO_CONSOLE == 0


def test_the_settings_window_still_closes_when_it_loses_focus():
    """Le second symptome n'a PAS ete corrige en retirant la fermeture au
    changement de focus : c'est un comportement voulu (« close on outside
    click »). On a corrige la CAUSE -- la console qui volait l'activation.

    Ce test constate le comportement conserve : s'il disparaissait un jour, ce
    serait une decision a prendre, pas un effet de bord de ce ticket.
    """
    src = (RACINE / "ui" / "settings_dialog.py").read_text(encoding="utf-8")
    assert "ActivationChange" in src
    assert "self.close()" in src


def test_the_generation_path_is_covered():
    """Le symptome le plus visible pour l'utilisateur (« pendant la generation
    j'ai des fenetres de terminal ») passe par UN helper central. Verrouille
    nommement : c'est celui qu'on ne peut pas se permettre de rater."""
    spawns = _spawns(RACINE / "ui" / "arduino_cli.py")
    assert spawns, "arduino_cli ne lance plus rien ? verifier ce test"
    assert all(drapeau for _, _, drapeau in spawns), spawns


TESTS = [
    test_every_spawn_hides_its_console,
    test_the_flag_is_the_shared_constant,
    test_the_constant_is_neutral_off_windows,
    test_the_settings_window_still_closes_when_it_loses_focus,
    test_the_generation_path_is_covered,
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
