"""Calcul des consommateurs transitifs d'une fonctionnalite dans un graphe
de dependances {consumer_id -> {producer_id, ...}}.

Le graphe lui-meme est produit par `code_analyzer.analyze_code(...).graph`.
"""
from __future__ import annotations


def transitive_consumers(
    producer_id: str, graph: dict[str, set[str]]
) -> set[str]:
    """Ensemble des fonctions qui dependent transitivement de producer_id.

    `graph` est de la forme {consumer: {producer, ...}}. Le resultat ne
    contient PAS producer_id lui-meme.
    """
    inv: dict[str, set[str]] = {}
    for consumer, producers in graph.items():
        for p in producers:
            inv.setdefault(p, set()).add(consumer)

    visited: set[str] = set()
    stack = [producer_id]
    while stack:
        cur = stack.pop()
        for c in inv.get(cur, ()):
            if c not in visited:
                visited.add(c)
                stack.append(c)
    return visited
