"""Build embeddings.npy from assets/rag/corpus.json.

Run from the repo root:
    python scripts/build_rag_embeddings.py

Output:
    assets/rag/embeddings.npy   shape (N, D), float32, L2-normalized.
    Row order matches corpus.json order (entry i in JSON ↔ row i in matrix).

Embedding text per entry: description + " " + " ".join(keywords).
That mirrors the runtime path so search uses the same surface form.

Uses the same ONNX encoder as ui/rag.py (no sentence-transformers / torch
dependency). Requires the model files under assets/rag/model/ — see
scripts/export_onnx_model.py.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = REPO_ROOT / "assets" / "rag" / "corpus.json"
EMBEDDINGS_PATH = REPO_ROOT / "assets" / "rag" / "embeddings.npy"
FINGERPRINT_PATH = REPO_ROOT / "assets" / "rag" / "embeddings.fingerprint.json"

sys.path.insert(0, str(REPO_ROOT))


# TODO #65 (mesuré le 2026-08-26) — la description est PLAFONNÉE ici, et
# seulement ici : `corpus.json` garde son texte entier, qui sert à l'affichage,
# au boost lexical et au contexte injecté. Ce plafond ne concerne QUE le texte
# donné à l'encodeur.
#
# Pourquoi 64 : l'encodeur tronque à `_MAX_SEQ_LEN` (128 tokens) et la
# description passait AVANT les mots-clés. 91 des 137 entrées dépassaient le
# budget (médiane 214 tokens, max 629), si bien que 5 à 9 mots-clés sur 25
# seulement entraient — et comme ils sont rangés anglais d'abord, les
# traductions fr/es/it n'entraient JAMAIS.
#
# ⛔ Le réflexe « il suffit de lever la limite à 256 » a été mesuré et c'est la
# PIRE option : l'empreinte est la MOYENNE des tokens, donc plus on laisse
# entrer de prose, plus elle dérive vers le centre. Mesuré, « afficher du texte
# sur un LCD 16x2 » contre son entrée : 0,609 à 128 tokens, 0,495 à 256, 0,389
# à 384 — sous le plancher d'injection, donc plus rien. Allonger dilue, donc
# raccourcir concentre : le gain de ce plafond vient autant de la netteté de
# l'empreinte que de l'entrée des mots-clés.
#
# Chiffres du choix (548 cas, deux batteries) : 14 gains / 5 régressions, AUCUNE
# régression sur la batterie A, la bande « nommé » gagne +4, et le plafond de
# bruit passe de 0,543 à 0,495 — sous le plancher de 0,50.
# Mesure : docs/superpowers/measures/2026-08-26-65-budget-de-tokens.md
# ⛔ LA REGLE DU TEXTE D'EMBEDDING VIT DANS `ui/embedding_text.py`, PAS ICI.
# Elle y a demenage le 2026-11-05 (TODO #120) parce que le controle d'accord
# modele/matrice a besoin de la MEME regle pour encoder un texte temoin : deux
# copies auraient derive, et un texte qui differe d'un mot rend un vecteur
# different -- donc un « desaccord » sur un modele sain.
#
# ⚠️ Les alias ci-dessous gardent les noms que ce script utilisait, pour que le
# deplacement ne change RIEN a ce qu'il produit. Verifie bit a bit : l'empreinte
# des textes de `embeddings.fingerprint.json` est inchangee apres le
# deplacement (`test_the_moved_rule_produces_the_same_texts`).
from ui.embedding_text import (DESCRIPTION_TOKEN_BUDGET as _DESCRIPTION_TOKEN_BUDGET,
                               embedding_text as _embedding_text,
                               truncate_to_tokens as _truncate_to_tokens)


def _encode_batched(texts: list[str], batch_size: int = 16) -> np.ndarray:
    """Encode in chunks to keep memory bounded on small machines."""
    from ui.rag import _load_encoder, encode

    if not _load_encoder():
        raise RuntimeError(
            "RAG encoder not loaded — check assets/rag/model/"
        )
    out_chunks: list[np.ndarray] = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i + batch_size]
        out_chunks.append(encode(chunk))
        print(f"  encoded {min(i + batch_size, len(texts))}/{len(texts)}")
    return np.concatenate(out_chunks, axis=0)


def _texts_fingerprint(texts) -> str:
    """Empreinte stable des textes encodes, pour que la garde de
    synchronisation voie un CONTENU modifie, pas seulement un compte."""
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(bytes(1))
    return h.hexdigest()


def main() -> int:
    if not CORPUS_PATH.exists():
        print(f"Corpus not found: {CORPUS_PATH}", file=sys.stderr)
        return 1

    with CORPUS_PATH.open(encoding="utf-8") as f:
        corpus = json.load(f)
    if not corpus:
        print("Corpus is empty.", file=sys.stderr)
        return 1

    texts = [_embedding_text(e) for e in corpus]
    print(f"Embedding {len(texts)} libraries via ONNX encoder…")

    matrix = _encode_batched(texts).astype(np.float32)

    EMBEDDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS_PATH, matrix)
    # Empreinte des TEXTES reellement encodes. Le compte de lignes ne
    # suffit pas : modifier une entree existante sans reconstruire laisse
    # la matrice perimee POUR CETTE LIGNE, et le nombre ne bouge pas.
    # Mesure du 2026-08-27 : deux alias serigraphies (KY-040 sur
    # `encoder`, GY-909 sur `mlx90614`) etaient au corpus depuis la veille
    # et INERTES pour le RAG, sans qu aucun test ne rougisse.
    FINGERPRINT_PATH.write_text(
        json.dumps({"count": len(texts),
                    "sha256": _texts_fingerprint(texts)}, indent=2) + chr(10),
        encoding="utf-8")
    print(f"Saved {matrix.shape} -> {EMBEDDINGS_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
