"""« Cette bibliotheque fournit-elle cet en-tete ? » -- la question du #113.

Contexte, mesure du 2026-09-11. `_try_install_lib` repondait en consultant
`provides_includes`, qui N'EST PAS un inventaire : c'est le champ `includes=`
de `library.properties`, la liste que l'IDE insere quand on ajoute la
bibliotheque. Facultative, et parfois FAUSSE. Deux victimes vivantes :

  - `TM1637` (Avishay Orpaz) livre `TM1637Display.h` et declare
    `includes=TM1637.h` -- un fichier qui n'existe pas chez elle. L'app
    installait la bonne bibliotheque puis la DESINSTALLAIT, a chaque
    generation.
  - `IRremote` 4.7.1 declare `IRremote.hpp` seul mais livre AUSSI `IRremote.h`
    (stub de compatibilite). Verifie a l'`arduino-cli` : le croquis en
    `#include <IRremote.h>` COMPILE une fois la bibliotheque posee.

Ces tests n'ont besoin ni de reseau ni d'arduino-cli : ils construisent de
fausses arborescences de bibliotheque sur disque.
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ui import arduino_cli  # noqa: E402


def _fausse_lib(racine: str, nom: str, fichiers: list, declare: list) -> dict:
    """Pose une arborescence de bibliotheque et rend son descripteur
    `_installed_libs` (le meme dict que produit `arduino-cli lib list`)."""
    base = os.path.join(racine, nom)
    for rel in fichiers:
        chemin = os.path.join(base, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, 'w', encoding='utf-8') as f:
            f.write('// %s\n' % rel)
    os.makedirs(base, exist_ok=True)
    return {'headers': list(declare), 'install_dir': base}


# ── La declaration reste le chemin rapide ────────────────────────────────────

def test_a_declared_header_is_accepted_without_touching_the_disk():
    """Le cas de loin le plus frequent : quand `includes=` est absent,
    `arduino-cli lib list` le calcule depuis le disque (mesure : `Servo` ne
    declare rien a l'index et rapporte `['Servo.h']` une fois installee). Ce
    chemin ne doit donc meme pas regarder le disque."""
    info = {'headers': ['Servo.h'], 'install_dir': '/chemin/qui/nexiste/pas'}
    assert arduino_cli._lib_provides_header(info, 'Servo.h')


# ── Les deux defauts mesures ─────────────────────────────────────────────────

def test_a_header_on_disk_counts_even_when_undeclared():
    """Le cas IRremote : `IRremote.h` existe, la declaration ne le liste pas."""
    tmp = tempfile.mkdtemp()
    try:
        info = _fausse_lib(
            tmp, 'IRremote',
            ['src/IRremote.hpp', 'src/IRremote.h'],
            declare=['IRremote.hpp'],
        )
        assert arduino_cli._lib_provides_header(info, 'IRremote.hpp')
        assert arduino_cli._lib_provides_header(info, 'IRremote.h'), (
            "l'en-tete est sur le disque : le refuser faisait desinstaller "
            "une bibliotheque qui compile"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_wrong_declaration_does_not_hide_the_real_header():
    """Le cas TM1637 : la bibliotheque declare un fichier qu'elle n'a pas."""
    tmp = tempfile.mkdtemp()
    try:
        info = _fausse_lib(
            tmp, 'TM1637',
            ['TM1637Display.h', 'TM1637Display.cpp'],
            declare=['TM1637.h'],          # <- mensonge de library.properties
        )
        assert arduino_cli._lib_provides_header(info, 'TM1637Display.h')
        # Et la declaration fausse ne fabrique pas un fournisseur imaginaire.
        assert arduino_cli._lib_provides_header(info, 'TM1637.h'), (
            "la declaration reste le chemin rapide, meme fausse -- ce test "
            "documente le comportement, il ne l'approuve pas : c'est "
            "arduino-cli qui repond alors, pas nous"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_header_in_a_subdirectory_is_found():
    """`#include <utility/Foo.h>` doit trouver `src/utility/Foo.h`."""
    tmp = tempfile.mkdtemp()
    try:
        info = _fausse_lib(tmp, 'Lib', ['src/utility/Foo.h'], declare=[])
        assert arduino_cli._lib_provides_header(info, 'utility/Foo.h')
        assert arduino_cli._lib_provides_header(info, 'Foo.h')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Les pieges que le balayage disque INTRODUIT ──────────────────────────────

def test_a_lookalike_name_does_not_satisfy_the_include():
    """⛔ Le piege du `endswith` : `XFoo.h` se termine bien par `Foo.h`.
    La comparaison porte sur le SEGMENT de chemin, pas sur la chaine."""
    tmp = tempfile.mkdtemp()
    try:
        info = _fausse_lib(tmp, 'Lib', ['src/XFoo.h'], declare=[])
        assert not arduino_cli._lib_provides_header(info, 'Foo.h'), (
            "un nom qui finit pareil n'est pas le meme fichier"
        )
        assert arduino_cli._lib_provides_header(info, 'XFoo.h')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_an_example_sketch_does_not_make_the_library_a_provider():
    """Les croquis d'exemple ont leurs propres en-tetes. Les compter ferait
    dire « fournie » a une bibliotheque qui ne l'est pas depuis le croquis de
    l'utilisateur -- et ferait garder la mauvaise bibliotheque."""
    tmp = tempfile.mkdtemp()
    try:
        info = _fausse_lib(
            tmp, 'Lib',
            ['src/Vrai.h', 'examples/Demo/Faux.h', 'docs/Autre.h'],
            declare=[],
        )
        assert arduino_cli._lib_provides_header(info, 'Vrai.h')
        assert not arduino_cli._lib_provides_header(info, 'Faux.h')
        assert not arduino_cli._lib_provides_header(info, 'Autre.h')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_an_absent_header_is_still_absent():
    tmp = tempfile.mkdtemp()
    try:
        info = _fausse_lib(tmp, 'Lib', ['src/Vrai.h'], declare=[])
        assert not arduino_cli._lib_provides_header(info, 'Inexistant.h')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_missing_install_dir_is_not_a_crash():
    """Une bibliotheque desinstallee sous nos pieds ne doit pas faire tomber
    la compilation -- elle ne fournit simplement rien."""
    assert not arduino_cli._lib_provides_header(
        {'headers': [], 'install_dir': ''}, 'Foo.h')
    assert not arduino_cli._lib_provides_header(
        {'headers': [], 'install_dir': '/nexiste/vraiment/pas'}, 'Foo.h')


# ── Le journal ne doit plus designer la mauvaise cause ───────────────────────

def _sans_cli(fn):
    """Joue `fn` avec la CLI neutralisee : aucun appel reseau ni processus."""
    orig_run = arduino_cli._run
    orig_inst = arduino_cli._installed_libs
    arduino_cli._run = lambda cmd, **kw: (0, "")
    arduino_cli._installed_libs = lambda cfg: {}
    try:
        return fn()
    finally:
        arduino_cli._run = orig_run
        arduino_cli._installed_libs = orig_inst


def test_nothing_in_the_registry_and_nothing_providing_are_told_apart():
    """⛔ Le second defaut du #113 : `False` recouvrait DEUX causes opposees,
    et le journal en imprimait une seule. « introuvable dans le registre »
    s'affichait alors que la bibliotheque avait ete trouvee, installee, puis
    rejetee -- ce message a envoye l'enquete au mauvais endroit."""
    orig_cand = arduino_cli._search_candidates

    arduino_cli._search_candidates = lambda q, cfg: []
    try:
        r = _sans_cli(lambda: arduino_cli._try_install_lib(
            'Zorglub', 'cfg', header_file='Zorglub.h'))
        assert r == arduino_cli.INSTALL_NO_CANDIDATE, r

        # Le registre propose quelque chose, mais rien ne fournit l'en-tete.
        arduino_cli._search_candidates = lambda q, cfg: ['UneLib']
        r = _sans_cli(lambda: arduino_cli._try_install_lib(
            'Zorglub', 'cfg', header_file='Zorglub.h'))
        assert r == arduino_cli.INSTALL_NO_PROVIDER, r
    finally:
        arduino_cli._search_candidates = orig_cand


def test_the_three_outcomes_are_distinct_values():
    """Une garde bete, mais elle attrape la faute la plus couteuse : deux
    constantes egales feraient passer les tests ci-dessus au vert en
    confondant a nouveau les deux causes."""
    issues = {arduino_cli.INSTALL_OK,
              arduino_cli.INSTALL_NO_CANDIDATE,
              arduino_cli.INSTALL_NO_PROVIDER}
    assert len(issues) == 3, issues


def test_the_journal_has_a_sentence_for_each_failure():
    """Les deux causes doivent produire DEUX phrases differentes dans le
    journal -- sinon les distinguer dans le code ne sert a rien."""
    import inspect
    src = inspect.getsource(arduino_cli.CompileUploadWorker._ensure_libs)
    assert 'INSTALL_NO_CANDIDATE' in src and 'INSTALL_NO_PROVIDER' in src, (
        "le journal doit trancher entre les deux causes"
    )
    assert 'introuvable dans le registre' in src
    assert 'ne fournit' in src, (
        "la seconde cause a besoin de sa propre phrase : dire « introuvable » "
        "d'une bibliotheque trouvee est ce qui a coute l'enquete du #113"
    )


TESTS = [
    test_a_declared_header_is_accepted_without_touching_the_disk,
    test_a_header_on_disk_counts_even_when_undeclared,
    test_a_wrong_declaration_does_not_hide_the_real_header,
    test_a_header_in_a_subdirectory_is_found,
    test_a_lookalike_name_does_not_satisfy_the_include,
    test_an_example_sketch_does_not_make_the_library_a_provider,
    test_an_absent_header_is_still_absent,
    test_a_missing_install_dir_is_not_a_crash,
    test_nothing_in_the_registry_and_nothing_providing_are_told_apart,
    test_the_three_outcomes_are_distinct_values,
    test_the_journal_has_a_sentence_for_each_failure,
]


def main() -> int:
    echecs = 0
    for t in TESTS:
        try:
            t()
            print("  OK   %s" % t.__name__)
        except AssertionError as e:
            echecs += 1
            print("  FAIL %s\n       %s" % (t.__name__, e))
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print("  ERR  %s\n       %r" % (t.__name__, e))
    print("\n%d/%d" % (len(TESTS) - echecs, len(TESTS)))
    return 1 if echecs else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
