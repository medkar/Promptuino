"""Le corpus promet-il des bibliothèques que le registre Arduino ne connaît pas ?

⚠️ **Pourquoi cet outil existe** (2026-08-29). Un utilisateur a demandé « deux
moteurs DC » ; le RAG a retenu `SparkFun TB6612FNG Motor Driver Library`, la
génération a écrit du code contre elle, et la compilation a échoué sur
`Missing library`. Cette bibliothèque existe sur GitHub mais **n'est pas
publiée au Library Manager** : elle était donc inutilisable depuis toujours,
et rien ne le disait. L'audit a trouvé **quatre** entrées dans ce cas sur 132,
dont trois n'étaient qu'un suffixe manquant (« Library », « v1.3 »).

Aucun test unitaire ne peut couvrir ça : il faut `arduino-cli` et son index.
D'où un outil à lancer **à la main, avant chaque lot d'ajouts au corpus** —
même discipline que `scripts/bench_rag.py`.

⚠️ **Ce que cet outil NE dit pas.** Qu'une bibliothèque soit installable ne la
rend pas PERTINENTE. Le même incident l'a montré : sur un prompt sans puce
nommée, le corpus a proposé une bibliothèque liée à une puce précise plutôt
que l'entrée générique `dc_motor` (qui, elle, n'a aucune bibliothèque). C'est
un problème de CLASSEMENT, pas de nommage, et il se mesure avec
`scripts/bench_rag.py`.

Usage :
    python scripts/audit_corpus_libs.py

Sortie : la liste des entrées fautives, et un code de retour non nul s'il y en
a — pour qu'un enchaînement de commandes s'arrête dessus.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "assets" / "rag" / "corpus.json"


def index_arduino() -> set[str]:
    """Noms de l'index Arduino, en minuscules. Ensemble VIDE si la CLI est
    absente — l'appelant refuse alors de conclure : un audit qui ne peut pas
    interroger le registre ne doit pas déclarer le corpus sain."""
    try:
        sortie = subprocess.run(
            ["arduino-cli", "lib", "search", "--format", "json",
             "--omit-releases-details"],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        ).stdout
    except Exception:
        return set()
    if not sortie.strip():
        return set()
    try:
        donnees = json.loads(sortie)
    except json.JSONDecodeError:
        return set()
    libs = donnees.get("libraries", donnees) if isinstance(donnees, dict) \
        else donnees
    noms = set()
    for lib in libs:
        nom = (lib.get("name") or "").strip()
        if nom:
            noms.add(nom.lower())
    return noms


def entrees_fautives(corpus: list, noms: set[str]) -> list[tuple[str, str]]:
    """(id, nom de bibliothèque) des entrées dont la bibliothèque est absente
    du registre. Les entrées SANS bibliothèque sont légitimes et ignorées :
    13 composants du corpus n'en ont aucune (`pir-motion-sensor`, `mq135`,
    `eeprom`, `dc_motor`…) — un document décrit un composant, pas forcément
    une bibliothèque."""
    fautives = []
    for entree in corpus:
        lib = (entree.get("arduino_lib_name") or "").strip()
        if not lib:
            continue
        if lib.lower() not in noms:
            fautives.append((entree.get("id", "?"), lib))
    return fautives


def main() -> int:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    avec_lib = [e for e in corpus
                if (e.get("arduino_lib_name") or "").strip()]

    print("chargement de l'index Arduino (local, peut prendre ~10 s)…")
    noms = index_arduino()
    if not noms:
        print("REFUS DE CONCLURE : index indisponible (arduino-cli absent, "
              "index non initialisé, ou appel en échec).")
        print("  -> `arduino-cli core update-index` puis relancer.")
        return 2

    print(f"index Arduino            : {len(noms)} bibliothèques")
    print(f"entrées du corpus        : {len(corpus)}")
    print(f"  dont une bibliothèque  : {len(avec_lib)}")

    fautives = entrees_fautives(corpus, noms)
    print(f"  INTROUVABLE au registre: {len(fautives)}")
    if not fautives:
        print("\nOK — chaque bibliothèque annoncée existe au registre.")
        return 0

    print("\nCes entrées promettent une bibliothèque que `arduino-cli lib "
          "install` ne trouvera pas.\nToute génération qui les retient "
          "échouera à la compilation :\n")
    for cid, lib in fautives:
        print(f"  [X] {cid}  ->  {lib!r}")
        proches = [n for n in sorted(noms)
                   if lib.lower() in n or n in lib.lower()][:5]
        print(f"      au registre, de nom proche : "
              f"{proches if proches else 'AUCUN'}")
    print("\nDeux issues, selon le cas :")
    print("  - un suffixe manque (« Library », « v1.3 ») -> corriger le nom ;")
    print("  - la bibliothèque n'est pas publiée au Library Manager -> retirer")
    print("    `arduino_lib_name`, `headers` et `api_signatures`, et réécrire")
    print("    les exemples SANS elle. Sinon le modèle continuera de l'écrire.")
    print("\n⚠️ Ne PAS toucher `description` ni `keywords` : ce sont les seuls")
    print("   champs de l'empreinte RAG, alignée PAR POSITION sur ce fichier.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
