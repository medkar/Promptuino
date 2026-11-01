"""Tests standalone pour le retrieval RAG sur assets/rag/corpus.json.

Run : python scripts/test_chat_rag.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.chat.chat_rag import CorpusIndex, load_default_corpus


_INDEX: CorpusIndex | None = None


def get_index() -> CorpusIndex:
    """Index lazy-loaded une seule fois (corpus.json ne change pas)."""
    global _INDEX
    if _INDEX is None:
        _INDEX = CorpusIndex.from_entries(load_default_corpus())
    return _INDEX


# Index construction
def test_index_loads_all_entries():
    # Pas de nombre EN DUR : le corpus grossit (41 -> 91 depuis l'ecriture de ce
    # test), ce qui faisait echouer la suite a chaque ajout de lib alors que
    # l'invariant reel est « l'index charge TOUT le corpus ».
    idx = get_index()
    expected = len(load_default_corpus())
    assert expected > 0, "corpus vide"
    assert len(idx.entries) == expected, \
        f"index {len(idx.entries)} entrees vs corpus {expected}"

def test_index_has_dht():
    idx = get_index()
    dht_ids = [e.get("id") for e in idx.entries if "DHT" in e.get("name", "")]
    assert "dht-sensor-library" in dht_ids

# Retrieval top-k
def test_query_dht_returns_dht_top1():
    idx = get_index()
    hits = idx.query("DHT temperature humidity", top_k=3)
    assert len(hits) > 0
    assert "DHT" in hits[0].entry["name"], f"Top-1 not DHT-related: {hits[0].entry['name']}"

def test_query_onewire():
    idx = get_index()
    hits = idx.query("OneWire DS18B20", top_k=3)
    assert len(hits) > 0
    names = [h.entry["name"] for h in hits]
    assert any("OneWire" in n or "Dallas" in n for n in names), \
        f"OneWire/Dallas not in top-3: {names}"

def test_query_returns_at_most_k():
    idx = get_index()
    hits = idx.query("servo motor angle", top_k=3)
    assert 0 < len(hits) <= 3

def test_query_empty_returns_empty():
    idx = get_index()
    assert idx.query("", top_k=3) == []
    assert idx.query("   ", top_k=3) == []

# Threshold
def test_query_irrelevant_below_threshold():
    idx = get_index()
    hits = idx.query("zebra giraffe penguin", top_k=3)
    assert hits == [], f"Irrelevant query should return [], got {hits}"

# Score ordering
def test_query_scores_descending():
    idx = get_index()
    hits = idx.query("DHT humidity sensor", top_k=3)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True), f"Scores not descending: {scores}"


TESTS = [
    test_index_loads_all_entries,
    test_index_has_dht,
    test_query_dht_returns_dht_top1,
    test_query_onewire,
    test_query_returns_at_most_k,
    test_query_empty_returns_empty,
    test_query_irrelevant_below_threshold,
    test_query_scores_descending,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
