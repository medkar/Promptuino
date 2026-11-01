"""Retrieval RAG sur le corpus pedagogique librairies Arduino.

Index BM25 implemente en pur Python (zero dependance ML). Indexation
unique au demarrage sur `assets/rag/corpus.json` (41 entrees) ainsi que
sur `concepts.json` (concepts + cartes) via `load_concepts()`, puis
queries en O(N*k) -- negligeable sur ce volume.

Tokenisation : NFKD (suppression diacritiques) + lowercase + split sur
[^a-z0-9_]. Suffisant pour matcher du texte de description librairie +
headers Arduino, y compris les termes accentues FR/ES/IT.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CORPUS_PATH = _PROJECT_ROOT / "assets" / "rag" / "corpus.json"

# Minimum BM25 score threshold below which we return []. Calibrated empirically:
# une query totalement orthogonale (ex. "zebra giraffe penguin") donne un score
# proche de 0 ; une query qui matche un peu donne au moins 0.5.
_SCORE_THRESHOLD = 0.5

# BM25 standard params.
_BM25_K1 = 1.5
_BM25_B = 0.75


_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


def _strip_accents(text: str) -> str:
    """Supprime les diacritiques : 'résistance' -> 'resistance'. Permet le
    matching FR/ES/IT contre des aliases ecrits avec ou sans accent."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _tokenize(text: str) -> list[str]:
    """Strip accents + lowercase + split sur non-alphanum. Garde les _."""
    return _TOKEN_PATTERN.findall(_strip_accents(text).lower())


def _entry_text(entry: dict) -> str:
    """Concatene les champs textuels indexables d'une entree pour BM25.

    Couvre les entrees librairie (name/description/headers/category) ET les
    entrees concept/carte (aliases/summary/facts)."""
    parts: list[str] = [
        str(entry.get("name") or ""),
        str(entry.get("description") or ""),
        " ".join(entry.get("headers") or []),
        str(entry.get("category") or ""),
        " ".join(entry.get("aliases") or []),
        str(entry.get("summary") or ""),
        " ".join(entry.get("facts") or []),
    ]
    return " ".join(parts)


@dataclass
class CorpusHit:
    """Resultat d'une query : entree + score."""
    entry: dict
    score: float


class CorpusIndex:
    """Index BM25 in-memory sur une liste d'entrees corpus.json."""

    def __init__(self, entries: list[dict], doc_tokens: list[list[str]],
                  doc_freq: dict[str, int], avg_doc_len: float):
        self.entries = entries
        self._doc_tokens = doc_tokens
        self._doc_freq = doc_freq
        self._avg_doc_len = avg_doc_len
        self._n_docs = len(entries)

    @classmethod
    def from_entries(cls, entries: list[dict]) -> "CorpusIndex":
        """Construit l'index depuis une liste d'entrees corpus.json."""
        doc_tokens: list[list[str]] = []
        doc_freq: dict[str, int] = {}
        for entry in entries:
            tokens = _tokenize(_entry_text(entry))
            doc_tokens.append(tokens)
            for tok in set(tokens):
                doc_freq[tok] = doc_freq.get(tok, 0) + 1
        avg_doc_len = (
            sum(len(t) for t in doc_tokens) / len(doc_tokens)
            if doc_tokens else 0.0
        )
        return cls(entries, doc_tokens, doc_freq, avg_doc_len)

    def _idf(self, term: str) -> float:
        """Inverse document frequency BM25."""
        df = self._doc_freq.get(term, 0)
        # BM25 IDF avec +0.5 smoothing.
        return math.log((self._n_docs - df + 0.5) / (df + 0.5) + 1.0)

    def _score_doc(self, query_tokens: list[str], doc_idx: int) -> float:
        """Score BM25 d'un document pour la query."""
        doc = self._doc_tokens[doc_idx]
        if not doc or not self._avg_doc_len:
            return 0.0
        doc_len = len(doc)
        # Term frequencies dans le doc.
        tf: dict[str, int] = {}
        for tok in doc:
            tf[tok] = tf.get(tok, 0) + 1
        score = 0.0
        for term in query_tokens:
            if term not in tf:
                continue
            idf = self._idf(term)
            f = tf[term]
            num = f * (_BM25_K1 + 1)
            denom = f + _BM25_K1 * (
                1 - _BM25_B + _BM25_B * doc_len / self._avg_doc_len
            )
            score += idf * num / denom
        return score

    def query(self, text: str, top_k: int = 3,
              min_score: float | None = None) -> list[CorpusHit]:
        """Retourne les top-k entrees rankees par BM25, filtrees par seuil.

        `min_score` override le seuil par defaut (_SCORE_THRESHOLD). Sert au
        tuning SLM (seuil releve = moins de bruit). Returns [] si query vide
        ou si aucun doc n'atteint le seuil.
        """
        threshold = _SCORE_THRESHOLD if min_score is None else min_score
        query_tokens = _tokenize(text)
        if not query_tokens:
            return []
        scored: list[CorpusHit] = []
        for i, entry in enumerate(self.entries):
            s = self._score_doc(query_tokens, i)
            if s >= threshold:
                scored.append(CorpusHit(entry=entry, score=s))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]


def load_default_corpus() -> list[dict]:
    """Charge `assets/rag/corpus.json` (path projet)."""
    with _DEFAULT_CORPUS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


_DEFAULT_CONCEPTS_PATH = _PROJECT_ROOT / "assets" / "rag" / "concepts.json"


def load_concepts() -> list[dict]:
    """Charge `assets/rag/concepts.json` (concepts, cartes, pieges materiels).
    [] si absent.

    REGLE POUR AJOUTER UNE ENTREE (le fichier est un tableau JSON, il ne peut
    pas porter d'en-tete : c'est ici qu'elle vit).

    Toute entree DOIT porter `summary` ou `facts` -- c'est ce qui la route
    vers le bloc « faits de reference » du prompt plutot que vers le bloc
    « bibliotheques », ou ses faits seraient jetes
    (`chat_prompts._is_concept_entry`).

    Pour la categorie `hardware_trap` en particulier : n'y mettre que du FAIT
    VERIFIABLE -- un registre a lire, une valeur attendue, une consequence
    electrique. Jamais une opinion sur un vendeur ou une place de marche.
    « Mefie-toi de tel site » est du bruit ; « lis le registre 0xD0 :
    0x58 = BMP280, 0x60 = BME280 » est actionnable.
    """
    if not _DEFAULT_CONCEPTS_PATH.exists():
        return []
    with _DEFAULT_CONCEPTS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def find_board_entry(model_name: str,
                     entries: list[dict] | None = None) -> dict | None:
    """Mappe un nom de modele (board_manager.model) vers son entree carte.

    1) Match exact (name/alias, accents et casse ignores).
    2) Sinon match souple par inclusion : on retient le candidat dont la
       longueur est la PLUS PROCHE de la cible (le plus specifique). Cela
       evite qu'un alias court ('uno') ou un nom long ('arduino uno r4 minima')
       l'emporte a tort dans un sens comme dans l'autre. None si aucune carte
       ne correspond."""
    if not model_name or not model_name.strip():
        return None
    entries = entries if entries is not None else load_concepts()
    boards = [e for e in entries if e.get("category") == "board"]
    target = _strip_accents(model_name).lower().strip()

    def candidates(e: dict) -> list[str]:
        return [_strip_accents(n).lower().strip()
                for n in ([e.get("name", "")] + list(e.get("aliases") or []))
                if n]

    for e in boards:                       # 1. match exact
        if target in candidates(e):
            return e

    best = None                            # 2. match souple (inclusion)
    best_dist: int | None = None
    for e in boards:
        for n in candidates(e):
            if n and (n in target or target in n):
                dist = abs(len(n) - len(target))
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best = e
    return best
