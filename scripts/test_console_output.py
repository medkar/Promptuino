"""Un `print` de diagnostic ne doit jamais tuer l'app (2026-08-10).

Le bug, trouve en relancant l'app apres #42 : sortie 139, segfault. La chaine
etait courte et faite de choses qui semblaient chacune inoffensives :

  1. `registry_lookup` ecrit ses lignes avec une fleche —
     « [REGISTRY] « as7341 » → lib « Adafruit AS7341 » » ;
  2. `studio_view._apply_registry_results` recopie chaque ligne sur stdout par
     un `print` nu ;
  3. sur Windows, stdout prend la page de code ANSI (cp1252 sur une install
     occidentale), ou U+2192 n'existe pas -> UnicodeEncodeError ;
  4. l'exception est levee DANS un slot Qt (le callback `done` du
     `RegistryLookupWorker`). PyQt6 ne les avale pas : il abandonne le
     processus.

Une LIGNE DE DIAGNOSTIC tuait donc l'application, en pleine generation, sur le
chemin qui marche. Invisible depuis un terminal UTF-8 (PowerShell 7) ; fatal
depuis cmd.exe.

Le correctif ne force PAS l'UTF-8 — ca transformerait les accents en mojibake
sur une console cp1252. Il relache seulement le GESTIONNAIRE D'ERREURS.

Run : python scripts/test_console_output.py
"""
import io
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.console_output import make_console_lenient, make_stream_lenient

# La vraie ligne, telle que `registry_lookup` la fabrique.
LIGNE = "[REGISTRY] « as7341 » → lib « Adafruit AS7341 » du registre Arduino"


def _cp1252_stream():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")


def test_the_bug_reproduces_without_the_fix():
    """Sans le correctif, imprimer cette ligne LEVE. Si ce test cesse
    d'echouer, c'est que la reproduction ne vaut plus rien et que les autres
    ne prouvent plus grand-chose."""
    flux = _cp1252_stream()
    try:
        print(LIGNE, file=flux)
    except UnicodeEncodeError:
        return
    raise AssertionError("la ligne s'encode : la reproduction est perimee")


def test_after_the_fix_the_line_no_longer_raises():
    flux = _cp1252_stream()
    assert make_stream_lenient(flux) is True
    print(LIGNE, file=flux)               # ne doit plus lever


def test_the_unencodable_character_degrades_it_does_not_disappear():
    """`errors="replace"` : la fleche devient « ? ». Le reste de la ligne —
    accents et guillemets compris, qui EXISTENT en cp1252 — est intact."""
    flux = _cp1252_stream()
    make_stream_lenient(flux)
    print(LIGNE, file=flux)
    flux.flush()
    sortie = flux.buffer.getvalue().decode("cp1252")
    assert "?" in sortie
    assert "« as7341 »" in sortie
    assert "Adafruit AS7341" in sortie


def test_a_utf8_stream_is_left_readable():
    """On ne force pas l'encodage : sur une console UTF-8 la fleche reste une
    fleche. Forcer utf-8 aurait produit du mojibake ailleurs."""
    flux = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="")
    make_stream_lenient(flux)
    print(LIGNE, file=flux)
    flux.flush()
    assert "→" in flux.buffer.getvalue().decode("utf-8")


# ── Le durcisseur ne doit pas devenir lui-meme une source de panne ───────────

def test_it_tolerates_a_none_stream():
    """PyInstaller en mode fenetre met stdout a None."""
    assert make_stream_lenient(None) is False


def test_it_tolerates_a_stream_without_reconfigure():
    class _Faux:
        def write(self, _s): pass
    assert make_stream_lenient(_Faux()) is False


def test_it_tolerates_a_reconfigure_that_raises():
    class _Rale:
        def reconfigure(self, **_kw):
            raise OSError("flux detache")
    assert make_stream_lenient(_Rale()) is False


def test_make_console_lenient_never_raises():
    vrai_out, vrai_err = sys.stdout, sys.stderr
    try:
        sys.stdout = None
        sys.stderr = object()
        make_console_lenient()
    finally:
        sys.stdout, sys.stderr = vrai_out, vrai_err


# ── Le verrou : c'est appele AVANT que quoi que ce soit puisse ecrire ────────

def test_main_applies_it_before_importing_anything_that_prints():
    """Verrou par la source. Le durcissement n'a de valeur que s'il precede
    les imports : une ligne imprimee pendant le chargement d'un module
    passerait avant lui."""
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    idx_appel = src.index("make_console_lenient()")
    idx_qt = src.index("from PyQt6")
    idx_ui = src.index("from ui import MainWindow")
    assert idx_appel < idx_qt, "appele apres l'import de PyQt6"
    assert idx_appel < idx_ui, "appele apres l'import de l'app"


# ── Le VRAI stdout, pas un BytesIO (2026-08-12) ──────────────────────────────
#
# Les tests ci-dessus prouvent le mecanisme sur un `TextIOWrapper` fabrique a la
# main. Ils ne prouvent PAS que le durcissement atteint le `sys.stdout` d'un
# vrai processus — c'est pourtant la seule chose qui tuait l'app.
#
# La procedure manuelle O1 etait censee couvrir ce trou. Elle ne le pouvait pas :
# mesure le 2026-08-12, une VRAIE console Windows n'utilise pas la page de code
# (`_WindowsConsoleIO`, encoding=utf-8 quel que soit `chcp`) — la fleche y passe
# toujours. Ce qui declenche le defaut, c'est la REDIRECTION de stdout (fichier
# ou tuyau), ou Python retombe sur l'encodage de la locale.
#
# On force donc `PYTHONIOENCODING=cp1252` dans l'enfant : le flux hostile est
# reproduit a l'identique sur toute machine, quelle que soit sa locale.

_ENFANT = (
    "import sys\n"
    "{durcissement}"
    "print('[REGISTRY] \\u00ab as7341 \\u00bb \\u2192 lib \\u00ab Adafruit AS7341 \\u00bb')\n"
    "print('[SONDE] la generation continue')\n"
)


def _lance(durci: bool):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    code = _ENFANT.format(
        durcissement=(
            "from ui.console_output import make_console_lenient\n"
            "make_console_lenient()\n"
            if durci
            else ""
        )
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,      # capture = stdout redirige : la condition du bug
        env=env,
    )


def test_a_real_redirected_stdout_dies_without_the_hardening():
    """Le contre-exemple. Sans lui, le test suivant passerait meme si le
    durcissement etait devenu un no-op."""
    r = _lance(durci=False)
    assert r.returncode != 0, "l'enfant survit : la reproduction est perimee"
    assert b"UnicodeEncodeError" in r.stderr
    assert b"la generation continue" not in r.stdout, "la suite s'est executee"


def test_a_real_redirected_stdout_survives_with_the_hardening():
    r = _lance(durci=True)
    assert r.returncode == 0, r.stderr.decode("cp1252", "replace")
    sortie = r.stdout.decode("cp1252")
    assert "?" in sortie, "la fleche n'a pas ete remplacee"
    assert "« as7341 »" in sortie, "le reste de la ligne a ete perdu"
    assert "la generation continue" in sortie, "la suite ne s'est pas executee"


TESTS = [
    test_the_bug_reproduces_without_the_fix,
    test_after_the_fix_the_line_no_longer_raises,
    test_the_unencodable_character_degrades_it_does_not_disappear,
    test_a_utf8_stream_is_left_readable,
    test_it_tolerates_a_none_stream,
    test_it_tolerates_a_stream_without_reconfigure,
    test_it_tolerates_a_reconfigure_that_raises,
    test_make_console_lenient_never_raises,
    test_main_applies_it_before_importing_anything_that_prints,
    test_a_real_redirected_stdout_dies_without_the_hardening,
    test_a_real_redirected_stdout_survives_with_the_hardening,
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
