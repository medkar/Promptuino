"""Mesure la batterie C : que recoit le modele sur un prompt de SUITE ? (#64)

⚠️ Banc SEPARE de `bench_rag.py`, et pour une raison de fond : son
classificateur ne peut pas juger un prompt de suite. Pour lui, `silent` n'est
ni bon ni mauvais. Ici, sur les bandes `unit_change` et `behaviour`, le silence
est **exactement ce qu'on veut** -- le materiel ne change pas, le code fait
autorite -- et toute injection est une faute. La meme sortie a donc deux sens
opposes selon la bande, ce qu'un classificateur unique ne sait pas exprimer.

QUATRE ISSUES, et `wrong` n'y designe pas la meme chose que dans A et B :

  correct   la bande attend une lib et l'une des `expect` est injectee ;
            ou la bande n'attend rien et rien n'est injecte.
  silent    la bande attend une lib et rien n'est injecte -- l'utilisateur
            n'est pas aide, mais rien de faux ne lui est servi.
  wrong     une lib HORS `expect` est injectee.
  redundant une lib deja presente dans le PROJET est injectee alors que la
            bande n'attend rien. Pas une faute : le code la contient deja, le
            modele n'apprend rien de neuf et rien de faux. Comptee a part
            plutot que noyee dans `wrong`, sans quoi on corrigerait un defaut
            qui n'existe pas.

⚠️ CE BANC MESURE LE CHEMIN DE PRODUCTION. Depuis le correctif de #64 il
appelle `project_chips.chip_tokens_for_headers`, la fonction que l'app utilise,
et non une replique ecrite pour la mesure : une replique noterait un code que
personne n'execute. `--nu` rejoue le signal d'AVANT (prompt seul) pour que le
defaut d'origine reste reproductible et comparable.

Run : python scripts/bench_rag_followup.py [--freeze] [--nu]
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

BATTERY = ROOT / "scripts" / "bench_rag_prompts_c.json"
BASELINE = ROOT / "scripts" / "bench_rag_baseline_c.json"
ATTEND_RIEN = {"unit_change", "behaviour"}


def _libs_du_projet(headers: list[str]) -> set[str]:
    """Les entrees corpus que le code du projet declare deja, via ses #include.

    Passe par `markers._header_slug` + la table d'alias derivee du registre
    (TODO #60) : la correspondance en-tete -> composant existe deja, elle n'est
    pas a reecrire ici."""
    from ui.wiring.markers import _clean_lib_name
    from ui.rag import all_corpus_entries
    par_slug: dict[str, str] = {}
    for e in all_corpus_entries():
        for h in (e.get("headers") or []):
            par_slug.setdefault(_clean_lib_name(h, default=""), e["id"])
    return {par_slug[s] for h in headers
            if (s := _clean_lib_name(h, default="")) in par_slug}


def signal_de_recherche(cas: dict, nu: bool = False) -> str:
    """Le texte reellement classe : le prompt, plus les puces du projet.

    La forme de l'indice a ete MESUREE, pas choisie -- quatre variantes, dont
    deux aggravent. Le detail est dans la docstring de `ui/project_chips.py` ;
    ne pas la retoucher sans rejouer ce banc.
    """
    if nu:
        return cas["prompt"]
    from ui.project_chips import chip_tokens_for_headers
    indice = " ".join(chip_tokens_for_headers(cas["project_headers"]))
    if not indice:
        return cas["prompt"]
    return cas["prompt"] + "\n" + indice


def classer(injecte: list[str], cas: dict, du_projet: set[str]) -> str:
    """⚠️ Sur les bandes qui ATTENDENT une lib, un voisin injecte a cote de la
    bonne n'est PAS une faute.

    Premiere version de ce juge : « une lib hors `expect` => wrong ». Elle
    comptait 6 fautes qui n'en etaient pas — « ajoute un ecran OLED » remonte
    `adafruit-ssd1306` ET `ssd1351`, soit la bonne reponse accompagnee d'un
    voisin plausible. C'est du BRUIT, et `bench_rag_core.classify` le traite
    deja ainsi depuis toujours ; s'en ecarter ici aurait fait rapporter comme
    defaut de l'app un defaut de la mesure.

    Sur les bandes qui n'attendent RIEN, en revanche, toute injection compte —
    c'est la le sujet de #64.
    """
    if cas["band"] in ATTEND_RIEN:
        if not injecte:
            return "correct"
        return "redundant" if all(i in du_projet for i in injecte) else "wrong"
    if not injecte:
        return "silent"
    return "correct" if any(i in cas["expect"] for i in injecte) else "wrong"


def main() -> int:
    import ui.rag as rag
    import bench_rag
    if not rag._load():
        print("ERREUR : " + bench_rag.diagnose_missing_model(), file=sys.stderr)
        return 2

    cases = json.loads(BATTERY.read_text(encoding="utf-8"))
    n2i = bench_rag._name_to_id()
    import bench_rag_core as core
    import contextlib
    import io

    nu = "--nu" in sys.argv[1:]
    resultats = []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for cas in cases:
            contexte = rag.build_lib_context(
                signal_de_recherche(cas, nu=nu))
            injecte = core.resolve_to_ids(core.injected_names(contexte), n2i)
            du_projet = _libs_du_projet(cas["project_headers"])
            resultats.append({
                "prompt": cas["prompt"], "lang": cas["lang"],
                "band": cas["band"], "project": cas["project"],
                "injecte": injecte,
                "outcome": classer(injecte, cas, du_projet),
            })

    variante = "signal NU (avant #64)" if nu else (
        "signal enrichi des puces du projet (production)")
    print(f"Batterie C : {len(resultats)} cas de SUITE -- {variante}\n")
    for bande in ("unit_change", "behaviour", "add_unnamed", "add_named",
                  "replace_named"):
        lot = [r for r in resultats if r["band"] == bande]
        c = Counter(r["outcome"] for r in lot)
        attendu = "rien" if bande in ATTEND_RIEN else "une lib"
        print(f"  {bande:15s} (attend {attendu:8s}) "
              f"correct {c['correct']:2d}  silent {c['silent']:2d}  "
              f"wrong {c['wrong']:2d}  redundant {c['redundant']:2d}")

    fautes = [r for r in resultats if r["outcome"] == "wrong"]
    if fautes:
        print(f"\n  Les {len(fautes)} fautes, nommees :")
        for r in fautes:
            print(f"    [{r['lang']}] {r['band']:14s} projet {r['project']:8s} "
                  f"-> {r['injecte']}")
            print(f"        {r['prompt'][:82]}")

    if "--freeze" in sys.argv[1:]:
        BASELINE.write_text(json.dumps(resultats, ensure_ascii=False, indent=1)
                            + "\n", encoding="utf-8")
        print(f"\nReference gelee dans {BASELINE.name}.")
    elif BASELINE.exists():
        ref = {(r["prompt"], r["lang"]): r["outcome"]
               for r in json.loads(BASELINE.read_text(encoding="utf-8"))}
        bouges = [r for r in resultats
                  if ref.get((r["prompt"], r["lang"])) != r["outcome"]]
        print(f"\nECARTS avec la reference : {len(bouges)}")
        for r in bouges:
            print(f"    [{r['lang']}] {r['band']:14s} "
                  f"{ref.get((r['prompt'], r['lang']))} -> {r['outcome']}  "
                  f"{r['prompt'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
