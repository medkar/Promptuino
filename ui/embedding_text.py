"""Le texte qu'on donne a l'encodeur pour une entree du corpus — source UNIQUE.

⛔ **Pourquoi ce module existe.** Cette regle etait ecrite dans
`scripts/build_rag_embeddings.py` seul, donc seul le PRODUCTEUR de la matrice
la connaissait. Le controle d'accord modele/matrice (TODO #120) a besoin de la
MEME regle pour encoder un texte temoin et le comparer a sa ligne : la
recopier serait garantir une derive silencieuse — un texte qui differe d'un
mot rend un vecteur different, donc un « desaccord » sur un modele sain.

⚠️ J'ai failli la recopier de memoire le 2026-11-05, et ma version etait fausse
sur TROIS points : elle prefixait le `name` (le builder ne le fait pas), elle
utilisait le tokenizer du runtime (configure a 128 jetons AVEC troncature) au
lieu d'un tokenizer dedie sans troncature, et elle oubliait la duplication des
mots-cles en minuscules. Trois ecarts invisibles a la relecture, fatals a la
comparaison.

Module **pur** : aucun Qt, aucun numpy, aucune lecture de corpus. Il ne sait
transformer qu'une entree en texte.
"""
from __future__ import annotations

# TODO #65 (mesure du 2026-08-26) — la description est PLAFONNEE pour
# l'encodeur, et seulement pour lui : `corpus.json` garde son texte entier,
# qui sert a l'affichage, au boost lexical et au contexte injecte.
#
# Pourquoi 64 : l'encodeur tronque a 128 jetons et la description passait
# AVANT les mots-cles. 91 des 137 entrees depassaient le budget (mediane 214
# jetons, max 629), si bien que 5 a 9 mots-cles sur 25 seulement entraient --
# et comme ils sont ranges anglais d'abord, les traductions fr/es/it
# n'entraient JAMAIS.
DESCRIPTION_TOKEN_BUDGET = 64

_truncation_tokenizer = None


def truncate_to_tokens(text: str, budget: int) -> str:
    """Coupe `text` a `budget` jetons, sur une frontiere de jeton.

    Compte en JETONS et non en caracteres : c'est le budget en jetons qui est
    la ressource rare, et un plafond en caracteres se decale d'une langue a
    l'autre -- le corpus est multilingue.

    Utilise un tokenizer DEDIE, sans troncature, plutot que celui de `ui.rag` :
    celui-ci est un singleton de module configure a 128 jetons, et le
    deconfigurer le temps d'un calcul laisserait le runtime sans troncature si
    l'appelant echouait en cours de route.

    ⚠️ `no_truncation()` est indispensable, pas decoratif : `tokenizer.json`
    embarque `truncation: max_length 128`, donc un tokenizer fraichement charge
    tronque DEJA. Inoffensif tant que le budget est inferieur a 128 -- le point
    de coupe reste dans la fenetre -- mais un budget plus grand serait
    silencieusement ramene a 128, et le plafond mentirait sur sa propre valeur.
    """
    global _truncation_tokenizer
    if _truncation_tokenizer is None:
        from tokenizers import Tokenizer

        from .rag import _TOKENIZER_PATH
        _truncation_tokenizer = Tokenizer.from_file(str(_TOKENIZER_PATH))
        _truncation_tokenizer.no_truncation()
    enc = _truncation_tokenizer.encode(text)
    if len(enc.ids) <= budget:
        return text
    return text[:enc.offsets[budget - 1][1]]


def embedding_text(entry: dict) -> str:
    """Le texte d'embedding : description (plafonnee) + mots-cles, chaque
    mot-cle non minuscule etant DOUBLE en minuscules.

    Pourquoi doubler : `paraphrase-multilingual-MiniLM` tokenise en
    respectant la casse. Avec seulement « OLED » dans les mots-cles,
    « ecran oled » (ce que tape un utilisateur) tombe de 0,43 a 0,20. Tout
    passer en minuscules repare ce cas mais degrade les numeros de modele
    comme « DHT22 », que l'encodeur traite en entites nommees. Garder les
    DEUX formes prend le meilleur des deux.
    """
    description = truncate_to_tokens(entry.get("description", "") or "",
                                     DESCRIPTION_TOKEN_BUDGET)
    keywords = entry.get("keywords", []) or []
    expanded: list[str] = []
    for k in keywords:
        expanded.append(k)
        kl = k.lower()
        if kl != k:
            expanded.append(kl)
    return f"{description} {' '.join(expanded)}".strip()
