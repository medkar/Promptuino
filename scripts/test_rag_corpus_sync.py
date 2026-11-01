"""Garde-fou : embeddings.npy DOIT avoir autant de lignes que corpus.json
a d'entrées. Sinon ui.rag._load() refuse de charger (RAG éteint). Pur, sans
modèle — destiné à tourner avec la suite de tests à chaque modif du corpus.
Forcing function couche 2 (cf. test_disambiguation_candidates_have_keywords)."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_CORPUS = ROOT / "assets" / "rag" / "corpus.json"
_EMB = ROOT / "assets" / "rag" / "embeddings.npy"
_FINGERPRINT = ROOT / "assets" / "rag" / "embeddings.fingerprint.json"


def test_embeddings_row_count_matches_corpus():
    corpus = json.load(_CORPUS.open(encoding="utf-8"))
    emb = np.load(_EMB)
    assert emb.shape[0] == len(corpus), (
        f"embeddings.npy={emb.shape[0]} lignes != corpus.json={len(corpus)} "
        f"entrées — lance : python scripts/build_rag_embeddings.py"
    )


def test_corpus_ids_unique():
    import collections

    corpus = json.load(_CORPUS.open(encoding="utf-8"))
    ids = [e["id"] for e in corpus]
    dups = [k for k, v in collections.Counter(ids).items() if v > 1]
    assert not dups, f"ids dupliqués dans corpus.json : {dups}"
    print("  OK — ids corpus uniques")


def test_embeddings_were_built_from_THIS_corpus():
    """Le compte de lignes ne voit PAS une entree modifiee.

    Defaut mesure le 2026-08-27 : deux alias serigraphies ajoutes la veille
    -- KY-040 sur `encoder`, GY-909 sur `mlx90614` -- vivaient dans
    corpus.json sans que la matrice ait ete reconstruite. Le nombre
    d'entrees n'ayant pas bouge, la garde ci-dessus restait verte, et les
    deux alias etaient INERTES pour le RAG : ecrits, committes, sans le
    moindre effet.

    On compare donc l'empreinte des TEXTES REELLEMENT ENCODES, que le
    script de build ecrit a cote de la matrice.
    """
    import hashlib
    import importlib.util

    if not _FINGERPRINT.exists():
        raise AssertionError(
            "assets/rag/embeddings.fingerprint.json manquant -- lance : "
            "python scripts/build_rag_embeddings.py")
    spec = importlib.util.spec_from_file_location(
        "_build_rag", ROOT / "scripts" / "build_rag_embeddings.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)

    corpus = json.load(_CORPUS.open(encoding="utf-8"))
    textes = [build._embedding_text(e) for e in corpus]
    attendu = json.load(_FINGERPRINT.open(encoding="utf-8"))
    assert attendu.get("count") == len(corpus), (
        f"empreinte pour {attendu.get(chr(34)+chr(99)+chr(111)+chr(117)+chr(110)+chr(116)+chr(34))} "
        f"entrees != corpus {len(corpus)}")
    h = hashlib.sha256()
    for t in textes:
        h.update(t.encode("utf-8"))
        h.update(bytes(1))
    assert h.hexdigest() == attendu.get("sha256"), (
        "corpus.json a change depuis le dernier build des embeddings -- "
        "lance : python scripts/build_rag_embeddings.py")

TESTS = [test_embeddings_row_count_matches_corpus, test_corpus_ids_unique,
         test_embeddings_were_built_from_THIS_corpus]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
