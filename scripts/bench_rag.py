"""RAG bench: what actually reaches the model, per band and per language.

Run:
    python scripts/bench_rag.py            # measure, and compare to the baseline
    python scripts/bench_rag.py --freeze   # measure, and WRITE the baseline

Measures `build_lib_context` END TO END rather than `retrieve_libs`, because
the guards sit between the two: "fais clignoter une LED" retrieves three wrong
libraries above the floor and still injects nothing. Measuring the intermediate
is what kept the existing battery from ever seeing that.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import bench_rag_core as core

BATTERY = ROOT / "scripts" / "bench_rag_prompts.json"
BASELINE = ROOT / "scripts" / "bench_rag_baseline.json"

_KNOWN_OPTIONS = {"--freeze", "--expect-may-be-missing"}
# Options à VALEUR (`--battery chemin`), traitées à part du jeu ci-dessus.
_KNOWN_VALUE_OPTIONS = {"--battery", "--baseline"}


def diagnose_missing_model() -> str:
    """Actionable message for why `ui.rag._load()` returned False.

    Two different root causes both make `retrieve_libs` swallow the failure
    and return `[]`, so from a caller's point of view they look identical --
    but they need two different fixes. Told apart (I6, final review
    2026-08-18) by loading each artifact independently and comparing
    `embeddings.npy`'s row count to the corpus length, exactly what
    `rag._load()` itself checks before refusing:
      - the ONNX encoder itself is missing (470 MB, git-ignored) -> rebuild
        the export;
      - the encoder is fine but `embeddings.npy` is stale relative to
        `corpus.json` (a corpus batch landed without a rebuild -- the
        NOMINAL failure mode of TODO #54 step 3) -> rebuild the embeddings.
    Shared by `_require_model` below and by the two characterization guards
    in `test_rag_injection_invariants.py`, so both callers explain the same
    failure the same way instead of drifting apart.
    """
    import ui.rag as rag
    if not rag._load_encoder():
        return (
            "le modele ONNX n'a pas pu etre charge.\n"
            "  Attendu : assets/rag/model/model.onnx (470 Mo, git-ignore)\n"
            "  Le regenerer : python scripts/export_onnx_model.py")
    if not rag._load_corpus():
        return "assets/rag/corpus.json est introuvable ou illisible."
    if not rag._EMBEDDINGS_PATH.exists():
        return (
            "assets/rag/embeddings.npy est absent.\n"
            "  Le regenerer : python scripts/build_rag_embeddings.py")
    try:
        import numpy as np
        embeddings = np.load(rag._EMBEDDINGS_PATH)
    except Exception as e:
        return f"assets/rag/embeddings.npy est illisible ({e})."
    n_corpus = len(rag._corpus or [])
    if embeddings.shape[0] != n_corpus:
        return (
            f"assets/rag/embeddings.npy est DESYNCHRONISE du corpus "
            f"({embeddings.shape[0]} lignes vs {n_corpus} entrees) -- un lot "
            f"a ete ajoute au corpus sans reconstruire les embeddings.\n"
            f"  Le regenerer : python scripts/build_rag_embeddings.py")
    return "le modele ONNX n'a pas pu etre charge (cause non identifiee)."


def _require_model() -> None:
    """Stop with an actionable message when the ONNX path is unusable.

    `retrieve_libs` SWALLOWS a load failure and returns [], so without this
    check the bench would print zeros everywhere -- a catastrophic regression
    where there is only a missing 470 MB file or a stale embeddings rebuild.
    """
    import ui.rag as rag
    if not rag._load():
        print("ERREUR : " + diagnose_missing_model(), file=sys.stderr)
        raise SystemExit(2)


def _name_to_id() -> dict[str, str]:
    """The name -> id map every classification in this bench relies on.

    Guarded by `core.name_collisions` (I5, final review 2026-08-18): two
    corpus entries sharing a `name` would silently make this map wrong for
    one of them, misreading either as a phantom regression or a phantom fix.
    """
    from ui.rag import all_corpus_entries
    entries = all_corpus_entries()
    collisions = core.name_collisions(entries)
    if collisions:
        raise SystemExit(
            "ERREUR : le corpus a des noms de bibliotheque en collision, le "
            "banc ne peut pas classer de facon fiable :\n  "
            + "\n  ".join(f"{n!r} -> {ids}" for n, ids in collisions.items()))
    return core.name_to_id_map(entries)


def measure(cases: list[dict], name_to_id: dict[str, str]) -> list[dict]:
    """Run every case through `build_lib_context` and classify the outcome."""
    from ui.rag import build_lib_context
    results = []
    for case in cases:
        context = build_lib_context(case["prompt"])
        results.append({
            "prompt": case["prompt"],
            "lang": case["lang"],
            "band_label": core.band_label(case),
            "outcome": core.classify(context, case["expect"], name_to_id),
            "stray": core.stray_libs(context, case["expect"], name_to_id),
        })
    return results


def noise_ceiling_by_case(cases: list[dict]) -> dict[tuple[str, str], float]:
    """Highest RAW similarity any corpus entry reaches, PER generic prompt.

    Excludes the I2C-scanner prompts (I1, final review 2026-08-18): they
    short-circuit `build_lib_context` unconditionally (`_prompt_is_i2c_
    scan`), so their raw similarity to random corpus entries can never affect
    what gets injected -- including them would measure noise the code path
    never consults. The basic-component prompts stay in: their guard
    (`_prompt_is_basic_component`) is bypassed the moment `prompt_names_a_
    chip` turns true, so a rising score there IS an early warning.

    Reported PER CASE, not as a single scalar: a new entry that pushes one
    specific prompt's score past the floor would leave an unrelated prompt's
    already-higher score as the reported max, unchanged.
    """
    import numpy as np
    import ui.rag as rag
    by_case: dict[tuple[str, str], float] = {}
    for case in cases:
        if case["band"] != "generic" or case["expect"]:
            continue
        sims = rag._embeddings @ rag.encode([case["prompt"]])[0]
        by_case[(case["prompt"], case["lang"])] = float(np.max(sims))
    return by_case


def main(argv: list[str]) -> int:
    # Defensive, at the entry point only: `format_deltas` stays pure and keeps
    # printing the `→`/`⚠` the brief mandates, but this bench is meant to be
    # run BY HAND on two machines whose shell is unknown ahead of time.
    # Measured: under Git Bash on this same machine, `sys.stdout.encoding` is
    # `cp1252` (vs. `utf-8` under the project's main shell, PowerShell), and
    # printing `→` raises `UnicodeEncodeError` -- a hard crash that loses the
    # rest of the output mid-print. Reconfiguring with `errors="replace"`
    # turns that crash into a degraded-but-complete printout instead.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    def _value_of(flag: str) -> str | None:
        """Valeur d'une option `--flag valeur`.

        None si le flag est absent, si c'est le dernier token (valeur
        manquante), OU si le token suivant commence lui-meme par `--`
        (le flag a avale un AUTRE drapeau plutot que sa valeur). Dans ces
        deux derniers cas le flag n'est PAS marque "consomme" plus bas : il
        retombe dans la liste des options inconnues, et recoit exactement le
        meme traitement (ERREUR sur stderr, sortie 2) plutot que de laisser
        `core.load_battery` planter en essayant d'ouvrir un fichier nomme
        `--freeze` ou `--nawak`.
        """
        args = argv[1:]
        if flag not in args:
            return None
        i = args.index(flag)
        if i + 1 >= len(args):
            return None
        value = args[i + 1]
        return None if value.startswith("--") else value

    battery_path = _value_of("--battery")
    baseline_path = _value_of("--baseline")
    consumed = set()
    for flag, value in (("--battery", battery_path), ("--baseline", baseline_path)):
        if flag in argv[1:] and value is not None:
            consumed.update({flag, value})
    unknown = [a for a in argv[1:]
               if a not in _KNOWN_OPTIONS and a not in consumed]
    if unknown:
        print(f"ERREUR : option(s) inconnue(s) : {', '.join(unknown)}\n"
              f"  Options valides : "
              f"{', '.join(sorted(_KNOWN_OPTIONS | _KNOWN_VALUE_OPTIONS))}",
              file=sys.stderr)
        return 2
    freeze = "--freeze" in argv[1:]
    expect_may_be_missing = "--expect-may-be-missing" in argv[1:]
    battery = Path(battery_path) if battery_path else BATTERY
    baseline = Path(baseline_path) if baseline_path else BASELINE

    _require_model()
    from ui.rag import _CODEGEN_MIN_SCORE
    cases = core.load_battery(battery)
    name_to_id = _name_to_id()

    expect_problems = core.validate_expect_ids(cases, set(name_to_id.values()))
    if expect_problems and expect_may_be_missing:
        # #60 : à la mesure « avant » de la batterie B, les 48 ids n'existent
        # pas encore et la validation refuserait de démarrer. On IMPRIME les
        # ids absents plutôt que de les avaler : une faute de frappe reste
        # visible, elle n'arrête simplement plus la mesure.
        print("ATTENTION : expect absent(s) du corpus, mesure poursuivie "
              "(--expect-may-be-missing) :")
        for p in expect_problems:
            print(f"  {p}")
        expect_problems = []
    if expect_problems:
        print("ERREUR : batterie invalide (expect qui ne resout vers aucun "
              "id) :\n  " + "\n  ".join(expect_problems), file=sys.stderr)
        return 2

    results = measure(cases, name_to_id)
    summary = core.summarize(results)
    stray = core.stray_summary(results)
    ceiling_by_case = noise_ceiling_by_case(cases)
    ceiling = max(ceiling_by_case.values(), default=0.0)

    print(f"Batterie : {len(cases)} cas — {battery.name}")
    print(f"Plafond de bruit (bande generique, hors scanner I2C qui "
          f"court-circuite le retrieval) : {ceiling:.3f}   "
          f"plancher = {_CODEGEN_MIN_SCORE:.2f}")
    print()
    for band in sorted(summary):
        counts = summary[band]["_all"]
        print(f"{band:20} correct {counts['correct']:3d}   "
              f"silent {counts['silent']:3d}   wrong {counts['wrong']:3d}")
        for lang in core.LANGS:
            if lang in summary[band]:
                c = summary[band][lang]
                print(f"    {lang}               correct {c['correct']:3d}   "
                      f"silent {c['silent']:3d}   wrong {c['wrong']:3d}")
    print()
    print(f"Libs hors expect (bruit embarque dans un contexte correct/wrong) "
          f": {stray['cases']} cas, {stray['ids']} id(s) — ne bouge PAS un "
          f"verdict correct/silent/wrong (I2 : la fuite que classify() ne "
          f"voit pas).")
    print()
    print("Les taux ABSOLUS ci-dessus dependent de l'echantillon de prompts et")
    print("ne sont pas un score de l'application. Seuls les ECARTS font autorite.")
    print("Hors perimetre : le pipeline hors-corpus (part-number inconnu), qui")
    print("demande reseau et arduino-cli.")

    if freeze:
        payload = {
            "schema_version": core.SCHEMA_VERSION,
            "results": results,
            "ceiling": {
                "by_case": [{"prompt": p, "lang": lg, "score": s}
                            for (p, lg), s in sorted(ceiling_by_case.items())],
            },
        }
        baseline.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(f"\nReference gelee ecrite dans {baseline.name}.")
        return 0

    if not baseline.exists():
        print(f"\nAucune reference ({baseline.name}) : rien a comparer.")
        print("La creer avec : python scripts/bench_rag.py --freeze")
        return 0

    ref = json.loads(baseline.read_text(encoding="utf-8"))
    try:
        core.check_baseline_schema(ref)
    except ValueError as e:
        print(f"\nERREUR : {e}", file=sys.stderr)
        return 2

    baseline_identities = [(r["prompt"], r["lang"]) for r in ref["results"]]
    current_identities = [core.case_identity(c) for c in cases]
    ajouts, retraits = core.battery_drift(baseline_identities, current_identities)
    common = core.common_identities(baseline_identities, current_identities)

    if ajouts or retraits:
        print("\nDECALAGE DE BATTERIE — les ecarts ne portent que sur les cas communs.")
        for p, lg in ajouts:
            print(f"  + [{lg}] {p!r}")
        for p, lg in retraits:
            print(f"  - [{lg}] {p!r}")

    cur_common = core.summarize(core.restrict_to_common(results, common))
    base_common = core.summarize(core.restrict_to_common(ref["results"], common))

    print(f"\nECARTS (la seule sortie qui fasse autorite) — {len(common)} cas "
          f"communs sur {len(current_identities)} :")
    for line in core.format_deltas(cur_common, base_common):
        print("  " + line)

    baseline_ceiling_by_case = {
        (c["prompt"], c["lang"]): c["score"]
        for c in ref.get("ceiling", {}).get("by_case", [])}
    cur_ceiling_common = {k: v for k, v in ceiling_by_case.items() if k in common}
    base_ceiling_common = {
        k: v for k, v in baseline_ceiling_by_case.items() if k in common}
    old_ceiling_common = core.max_ceiling(base_ceiling_common, common)
    new_ceiling_common = core.max_ceiling(cur_ceiling_common, common)
    print(f"  {'plafond de bruit':20} {old_ceiling_common:.3f} → "
          f"{new_ceiling_common:.3f} "
          f"({new_ceiling_common - old_ceiling_common:+.3f})")
    for line in core.format_ceiling_deltas(cur_ceiling_common, base_ceiling_common):
        print(line)

    cur_stray_common = core.stray_summary(core.restrict_to_common(results, common))
    base_stray_common = core.stray_summary(
        core.restrict_to_common(ref["results"], common))
    print(f"  {'libs hors expect':20} "
          f"{base_stray_common['ids']:3d} → {cur_stray_common['ids']:3d} id(s)"
          f"   ({base_stray_common['cases']:3d} → "
          f"{cur_stray_common['cases']:3d} cas)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
