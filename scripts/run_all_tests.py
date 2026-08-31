"""Lance TOUS les tests automatises du depot d'un coup.

Chaque `scripts/test_*.py` est un script autonome (pas de pytest) qui sort avec
le code 0 si tout passe. Ce lanceur les execute chacun dans un sous-processus
(isolation : plusieurs manipulent des singletons Qt / la session / le RAG),
collecte les resultats et affiche un recapitulatif.

    python scripts/run_all_tests.py                # tout, en serie
    python scripts/run_all_tests.py -j 8           # en parallele (plus rapide)
    python scripts/run_all_tests.py -k wiring      # seulement ceux qui matchent
    python scripts/run_all_tests.py --list         # lister sans executer
    python scripts/run_all_tests.py --failed-only  # n'afficher que les echecs

Code de sortie : 0 si tout passe, 1 sinon (utilisable en pre-push / CI).

⚠️  Le parallele (-j) est OPT-IN : quelques tests ecrivent des fichiers
partages (session, projets temporaires). En cas d'echec bizarre avec -j,
rejouer en serie avant de conclure a une regression.

Complement MANUEL (UI, modele local, carte branchee) : docs/qa/PROCEDURES.md.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

# Delai max par test. Les plus lents chargent le modele ONNX du RAG (~qq s) ;
# 300 s laisse une marge confortable meme sur une machine chargee.
TIMEOUT_S = 300

# Scripts exclus du lancement automatique, avec la RAISON. N'y ranger QUE des
# outils interactifs (pas de test rouge : un test rouge se repare ou se
# supprime, il ne se cache pas ici).
EXCLUDED: dict[str, str] = {
    "test_svg_component.py":
        "visualiseur interactif (ouvre une fenetre, app.exec() bloquant) — "
        "pas un test automatisable ; se lance a la main pour valider "
        "visuellement la convention SVG",
}


def discover(pattern: str | None) -> list[Path]:
    files = sorted(SCRIPTS.glob("test_*.py"))
    files = [f for f in files if f.name not in EXCLUDED]
    if pattern:
        files = [f for f in files if pattern.lower() in f.name.lower()]
    return files


def run_one(path: Path) -> tuple[Path, int, float, str]:
    """(chemin, code de sortie, duree, sortie). code 124 = timeout."""
    env = dict(os.environ)
    # Qt sans affichage : indispensable pour les tests qui instancient des
    # widgets sur une machine sans session graphique (CI, SSH).
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # `ui/paths.py` migre les donnees de l'ancienne arborescence a
    # l'import. C'est bon dans l'app, jamais dans un test : ce sont les
    # VRAIS fichiers de l'utilisateur.
    env["PROMPTUINO_NO_MIGRATION"] = "1"
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT), env=env, timeout=TIMEOUT_S,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return path, proc.returncode, time.monotonic() - started, out
    except subprocess.TimeoutExpired:
        return path, 124, time.monotonic() - started, f"TIMEOUT > {TIMEOUT_S}s"
    except OSError as e:
        return path, 125, time.monotonic() - started, f"LANCEMENT IMPOSSIBLE : {e}"


def main() -> int:
    # Meme parade que bench_rag (et pour la meme raison, payee le
    # 2026-08-31) : sous Git Bash stdout est cp1252, et IMPRIMER la sortie
    # d'un test qui echoue crashe le lanceur des qu'elle porte un caractere
    # hors table (un � de sortie de sous-processus suffit). Le crash
    # remplacait alors le VRAI diagnostic -- deux tests rouges se lisaient
    # comme un bug d'encodage du lanceur.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-k", "--filter", metavar="MOTIF",
                    help="ne lancer que les tests dont le nom contient MOTIF")
    ap.add_argument("-j", "--jobs", type=int, default=1, metavar="N",
                    help="lancer N tests en parallele (defaut 1 = serie)")
    ap.add_argument("--list", action="store_true",
                    help="lister les tests selectionnes sans les executer")
    ap.add_argument("--failed-only", action="store_true",
                    help="n'afficher que les echecs pendant l'execution")
    args = ap.parse_args()

    tests = discover(args.filter)
    if not tests:
        print("Aucun test ne correspond.", file=sys.stderr)
        return 1
    if args.list:
        for t in tests:
            print(t.name)
        print(f"\n{len(tests)} test(s).")
        return 0

    print(f"Lancement de {len(tests)} test(s)"
          f"{f' (filtre : {args.filter})' if args.filter else ''}"
          f"{f', {args.jobs} en parallele' if args.jobs > 1 else ''}…\n",
          flush=True)
    started = time.monotonic()
    results: list[tuple[Path, int, float, str]] = []

    def report(res):
        path, code, dur, _out = res
        # flush=True : sans ca, une sortie REDIRIGEE (log, CI, tee) est
        # bufferisee par blocs et n'affiche rien avant la toute fin du run —
        # impossible de suivre l'avancement d'une passe de plusieurs minutes.
        if code == 0:
            if not args.failed_only:
                print(f"  OK    {path.name}  ({dur:.1f}s)", flush=True)
        else:
            label = "TIMEOUT" if code == 124 else f"ECHEC({code})"
            print(f"  {label:8} {path.name}  ({dur:.1f}s)", flush=True)

    if args.jobs > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for res in pool.map(run_one, tests):
                results.append(res)
                report(res)
    else:
        for t in tests:
            res = run_one(t)
            results.append(res)
            report(res)

    failed = [r for r in results if r[1] != 0]
    total_s = time.monotonic() - started
    print(f"\n{'=' * 62}")
    print(f"{len(results) - len(failed)}/{len(results)} test(s) au vert "
          f"en {total_s:.0f}s")
    if EXCLUDED:
        print(f"({len(EXCLUDED)} exclu(s) : "
              f"{', '.join(f'{k} — {v}' for k, v in EXCLUDED.items())})")
    if failed:
        print(f"\n{len(failed)} ECHEC(S) — sortie de chacun :")
        for path, code, _dur, out in failed:
            print(f"\n{'-' * 62}\n### {path.name}  (code {code})\n{'-' * 62}")
            tail = out.strip().splitlines()[-25:]
            print("\n".join(tail) if tail else "(aucune sortie)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
