"""#60 -- le banc doit accepter une SECONDE batterie, et tolérer des `expect`
qui n'existent pas encore. Run: python scripts/test_bench_rag_options.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

BENCH = ROOT / "scripts" / "bench_rag.py"


def _run(args, timeout=900):
    return subprocess.run([sys.executable, str(BENCH), *args], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def test_an_unknown_option_is_still_refused():
    """La garde existante ne doit pas être affaiblie par les nouvelles."""
    r = _run(["--nawak"])
    assert r.returncode == 2, r.returncode
    assert "inconnue" in (r.stdout + r.stderr).lower()


def test_the_new_options_are_accepted():
    """Elles doivent au moins passer le contrôle des options (le banc peut
    ensuite échouer faute de modèle ONNX : c'est un AUTRE code de sortie)."""
    r = _run(["--battery", "x.json", "--baseline", "y.json",
              "--expect-may-be-missing"])
    combined = (r.stdout + r.stderr).lower()
    assert "option" not in combined or "inconnue" not in combined, combined


def test_a_missing_expect_stops_the_bench_by_default():
    """La validation reste un GARDE-FOU : sans le drapeau, un `expect` qui ne
    résout vers rien doit arrêter le banc -- c'est ce qui attrape les fautes
    de frappe.

    Test UNITAIRE et PUR (n'appelle que `core.validate_expect_ids`, pas
    `main()`) : utile pour isoler le comportement de la fonction, mais
    n'exerce pas le cablage `expect_problems and expect_may_be_missing`
    ecrit dans `bench_rag.main`. Voir le jumeau bout-en-bout ci-dessous,
    qui, lui, mord sur ce cablage (revue 2026-08-21, preuve par mutation)."""
    import bench_rag_core as core
    cases = [{"prompt": "p", "lang": "fr", "band": "described",
              "expect": ["nexiste-pas-du-tout"]}]
    problems = core.validate_expect_ids(cases, {"dht-sensor-library"})
    assert problems, "un expect inconnu doit etre signale"


def test_a_missing_expect_stops_the_bench_by_default_end_to_end():
    """Jumeau BOUT EN BOUT (subprocess) du test ci-dessus, SANS le drapeau.

    Revue 2026-08-21 : le test unitaire pur ci-dessus n'exerce que
    `core.validate_expect_ids`, jamais le `if expect_problems and
    expect_may_be_missing:` cable dans `main()`. Preuve par mutation du
    reviewer -- remplacer cette condition par `if expect_problems:` (le
    drapeau devient sans effet, le garde-fou par defaut disparait) laissait
    la suite annoncer `4/4 tests OK` quand meme. Ce test-ci appelle le VRAI
    `main()` par subprocess, sans `--expect-may-be-missing`, et doit donc
    voir le banc s'arreter (sortie 2)."""
    battery = [{"prompt": "fais clignoter une led", "lang": "fr",
                "band": "generic", "expect": [],
                "added": "2026-08-21", "source": "test_bench_rag_options"},
               {"prompt": "lis la temperature avec un dht22", "lang": "fr",
                "band": "named", "expect": ["pas-encore-au-corpus"],
                "added": "2026-08-21", "source": "test_bench_rag_options"}]
    with tempfile.TemporaryDirectory() as d:
        bpath = Path(d) / "b.json"
        bpath.write_text(json.dumps(battery), encoding="utf-8")
        base = Path(d) / "base.json"
        r = _run(["--battery", str(bpath), "--baseline", str(base)])
    out = r.stdout + r.stderr
    if "modele ONNX" in out or "model.onnx" in out:
        raise AssertionError(
            "modele ONNX indisponible : la mesure ne peut pas conclure")
    assert r.returncode == 2, out[-1500:]
    assert "pas-encore-au-corpus" in out, \
        "l'id absent doit apparaitre dans le message d'erreur, meme arrete"


def test_battery_flag_without_a_value_is_refused():
    """`--battery` en fin de ligne coupe le contrôle AVANT le chargement du
    modele ONNX (470 Mo) : timeout court pour le prouver -- si une
    regression fait retomber ce cas en silence sur la batterie par defaut,
    le banc partirait dans une mesure complete et ce test depasserait
    largement 60 s au lieu d'echouer proprement en sortie 2."""
    r = _run(["--battery"], timeout=60)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "erreur" in (r.stdout + r.stderr).lower()


def test_battery_flag_followed_by_another_flag_is_refused():
    """`--battery --freeze` : `--freeze` ne doit pas etre avale comme valeur
    (ce qui ferait planter `core.load_battery` sur un fichier `--freeze`
    introuvable, traceback brut, sortie 1) -- refus propre, sortie 2."""
    r = _run(["--battery", "--freeze"], timeout=60)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "traceback" not in (r.stdout + r.stderr).lower()


def test_battery_flag_followed_by_an_unknown_option_is_refused():
    """`--battery --nawak` : meme chose, ET `--nawak` doit etre signale
    (avant : avale comme "valeur" de `--battery`, jamais mentionne)."""
    r = _run(["--battery", "--nawak"], timeout=60)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    combined = r.stdout + r.stderr
    assert "traceback" not in combined.lower()
    assert "--nawak" in combined


def test_a_missing_expect_is_only_a_warning_with_the_flag():
    """Avec le drapeau, le banc IMPRIME les ids absents et continue : une
    faute de frappe reste visible, elle n'arrête plus la mesure."""
    # `added`/`source` sont exiges par `bench_rag_core.validate_case` (champs
    # obligatoires ajoutes apres la redaction du brief) -- absents, le banc
    # s'arrete pour batterie invalide avant meme d'atteindre le comportement
    # teste ici.
    battery = [{"prompt": "fais clignoter une led", "lang": "fr",
                "band": "generic", "expect": [],
                "added": "2026-08-21", "source": "test_bench_rag_options"},
               {"prompt": "lis la temperature avec un dht22", "lang": "fr",
                "band": "named", "expect": ["pas-encore-au-corpus"],
                "added": "2026-08-21", "source": "test_bench_rag_options"}]
    with tempfile.TemporaryDirectory() as d:
        bpath = Path(d) / "b.json"
        bpath.write_text(json.dumps(battery), encoding="utf-8")
        base = Path(d) / "base.json"
        r = _run(["--battery", str(bpath), "--baseline", str(base),
                  "--expect-may-be-missing", "--freeze"])
    out = r.stdout + r.stderr
    if "modele ONNX" in out or "model.onnx" in out:
        raise AssertionError(
            "modele ONNX indisponible : la mesure ne peut pas conclure")
    assert r.returncode == 0, out[-1500:]
    assert "pas-encore-au-corpus" in out, \
        "les ids absents doivent etre IMPRIMES, pas avales"


TESTS = [
    test_an_unknown_option_is_still_refused,
    test_the_new_options_are_accepted,
    test_a_missing_expect_stops_the_bench_by_default,
    test_a_missing_expect_stops_the_bench_by_default_end_to_end,
    test_battery_flag_without_a_value_is_refused,
    test_battery_flag_followed_by_another_flag_is_refused,
    test_battery_flag_followed_by_an_unknown_option_is_refused,
    test_a_missing_expect_is_only_a_warning_with_the_flag,
]


def main() -> int:
    # Meme garde que `bench_rag.main` (voir son commentaire) : un message de
    # FAIL peut reproduire tel quel la sortie d'un subprocess, et donc les
    # caracteres non-ASCII (`�`, `→`...) qu'elle contient -- sur un
    # terminal cp1252, les imprimer sans filet fait planter le RAPPORTEUR de
    # l'echec lui-meme, en perdant le compte final. Observe en pratique le
    # 2026-08-21 en rejouant la mutation de revue.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
