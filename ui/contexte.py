"""La taille de contexte d'un modele local : UNE regle pour Ollama et LM Studio.

Decisions de l'auteur du 2026-11-06 :
- un curseur qui va du plancher au maximum du modele, pas seulement des
  puissances de 2 ;
- aucune valeur sous ce que Promptuino demande (`CTX_PROMPTUINO`) ;
- un modele dont le maximum est plus petit est INUTILISABLE, et le message
  dit que c'est son contexte qui est trop petit ;
- la meme mecanique sur les deux moteurs.

⚠️ `CTX_PROMPTUINO` n'est PAS calibre sur un echantillon : 16 384 a ete
choisi le 2026-11-04 pour LM Studio, puis retenu par l'auteur pour les deux
moteurs. Ce qu'on sait : Ollama generait a 8 192 depuis juin sans troncature
signalee ; un « Modifier » sur un gros projet n'a jamais ete mesure.

Mesures du 2026-11-06 : Ollama applique la valeur EXACTE (20 000 -> 20 000) ;
LM Studio l'arrondit au multiple de 256 superieur (20 000 -> 20 224).

Module pur : ni Qt, ni reseau.
"""
from __future__ import annotations

CTX_PROMPTUINO = 16384
PAS = 1024
ARRONDI_LMSTUDIO = 256
# Quand le moteur ne dit pas le maximum du modele. Aucun cas reel mesure : les
# neuf modeles installes le 2026-11-06 le donnaient tous. 32 768 etait le haut
# de l'ancien curseur d'Ollama -- une valeur deja proposee, pas une invention.
MAX_INCONNU = 32768


def utilisable(ctx_max: "int | None") -> bool:
    """Un maximum INCONNU n'est pas un maximum trop petit."""
    return ctx_max is None or ctx_max >= CTX_PROMPTUINO


def plage(ctx_max: "int | None") -> "tuple[int, int]":
    """(bas, haut) du curseur ; le haut tombe sur un pas entier."""
    haut = (ctx_max if ctx_max else MAX_INCONNU) // PAS * PAS
    return CTX_PROMPTUINO, max(CTX_PROMPTUINO, haut)


def ramener(valeur, ctx_max: "int | None") -> int:
    """`valeur` ramenee dans la plage, sur un pas."""
    bas, haut = plage(ctx_max)
    try:
        v = int(valeur) // PAS * PAS
    except (TypeError, ValueError):
        v = bas
    return min(max(v, bas), haut)


def accorde(charge: "int | None", voulu: int) -> bool:
    """Le contexte charge correspond-il au reglage ? L'arrondi de LM Studio
    (jusqu'a 255 tokens de plus) n'est pas une difference."""
    return charge is not None and voulu <= charge < voulu + ARRONDI_LMSTUDIO
