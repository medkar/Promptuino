"""Le prompt tient-il dans la fenêtre du modèle ? (TODO #48)

Rien ne le vérifiait. `ollama_backend._call` alloue une fenêtre qui doit
contenir **le prompt ET la sortie**, et au-delà d'une certaine taille de projet
le modèle perd le début du contexte : la génération produit alors du code qui
ignore une partie du sketch — redéclare une variable, réutilise une broche déjà
prise — **sans qu'aucun message ne le dise**. Le symptôme n'est pas une erreur,
c'est un résultat plausible et faux. Même famille que la netlist vide muette et
que l'interface restée verrouillée.

Mesures du 2026-08-10, texture prise sur les 1409 lignes de code des 91
exemples du corpus (24,3 caractères par ligne), fenêtre locale de 8192 :

    Ajouter   dépasse vers ~1070 lignes de sketch (il injecte le sketch entier)
    Modifier  dépasse vers  ~560 lignes pour UNE fonctionnalité
    Régénérer ne dépasse jamais (1141 tokens, plat)

Un projet débutant fait 30 à 120 lignes — 21 à 28 % de la fenêtre. Le trou ne
s'ouvre que sur un gros projet, et c'est précisément là que l'utilisateur a le
plus à perdre.

Module PUR : ni Qt, ni backend concret. Il reçoit des textes et un nombre.
"""
from __future__ import annotations

# 4 caractères ≈ 1 token. Règle de trois utilisée dans toutes les mesures du
# chantier RAG ; réclamer un vrai tokenizer ici serait le meilleur moyen de ne
# rien faire, pour une précision dont l'avertissement n'a pas besoin.
_CHARS_PER_TOKEN = 4

# Part de la fenêtre qu'on refuse de laisser au prompt seul. La sortie d'une
# génération EST du code : sur le chemin Régénérer elle pèse le sketch entier.
# 0.75 laisse un quart de fenêtre à la réponse — au-delà, le modèle n'a plus la
# place de répondre même si le prompt, lui, est entré.
_PROMPT_SHARE = 0.75


def estimate_tokens(text: str) -> int:
    """Estimation basse et volontairement grossière (cf. `_CHARS_PER_TOKEN`)."""
    return len(text or "") // _CHARS_PER_TOKEN


def generation_window(backend) -> int:
    """Fenêtre réellement allouée par ce backend pour une génération.

    Passe par `backend.generation_context()` — la MÊME méthode que le backend
    utilise pour s'allouer la fenêtre, donc les deux ne peuvent pas diverger.
    Repli prudent sur 8192 si le backend est absent ou muet : mieux vaut un
    avertissement de trop qu'un garde-fou qui ne garde rien."""
    for nom in ("generation_context", "context_window_hint"):
        valeur = getattr(backend, nom, None)
        try:
            valeur = valeur() if callable(valeur) else valeur
            if isinstance(valeur, int) and valeur > 0:
                return valeur
        except Exception:
            continue
    return 8192


def prompt_overflows(system_prompt: str, user_message: str, backend) -> dict | None:
    """`None` si ça tient. Sinon un dict prêt à remplir le message.

    Ne dit RIEN quand tout va bien : c'est un avertissement, pas un compteur.
    Un message qui apparaît à chaque génération apprend à être ignoré."""
    window = generation_window(backend)
    tokens = estimate_tokens(system_prompt) + estimate_tokens(user_message)
    budget = int(window * _PROMPT_SHARE)
    if tokens <= budget:
        return None
    return {
        "tokens": str(tokens),
        "window": str(window),
        "percent": str(min(999, round(100 * tokens / max(1, window)))),
    }
