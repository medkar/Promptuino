"""Règles PURES et texte de la bannière d'info (ambre) du Studio.

Ce n'est PAS un widget -- le widget est `ui/nudge_banner.py`. Ce module porte
ce que cette bannière DIT (`numbered`) et QUAND le message « choisie par
ressemblance » en fait partie (`should_disclose_resemblance`), pour que les
deux soient testables sans Qt, sans l'encodeur ONNX et sans construire une
`StudioView`.
"""
from __future__ import annotations

from collections.abc import Sequence

# `ui.generation.gen_modal.CORRECT`, RECOPIÉ plutôt qu'importé : le paquet
# `ui/generation/` ré-exporte `gen_modal`, qui importe PyQt6 (il porte aussi le
# QDialog), et ce module doit rester chargeable sans Qt. La copie est
# surveillée par `test_correct_constant_has_not_drifted`.
_CORRECT = "correct"


def numbered(messages: Sequence[str]) -> str:
    """Rend plusieurs messages de bannière en UN seul corps en texte riche.

    Un message seul ne porte AUCUN numéro -- numéroter un élément unique est du
    bruit, et c'est le cas courant. À partir de deux, ils sont numérotés et
    séparés par une ligne vide : avant, un simple `"<br>".join(...)` les
    collait. Le cas qui rend ça réel est un prompt nommant DEUX part-numbers
    inconnus, qui produit deux messages du registre (TODO #61).
    """
    msgs = [m for m in messages if m]
    if not msgs:
        return ""
    if len(msgs) == 1:
        return msgs[0]
    return "<br><br>".join(f"{i}. {m}" for i, m in enumerate(msgs, 1))


def should_disclose_resemblance(*, by_resemblance: bool, action: str,
                                from_scratch: bool, has_targets: bool) -> bool:
    """Faut-il dire à l'UTILISATEUR que cette génération repose sur une
    devinette de bibliothèque ?

    `by_resemblance` vient de `rag.build_lib_context` : les libs injectées ont
    été proposées par la recherche de similarité pour un prompt qui ne nommait
    rien que l'app reconnaisse. Le modèle, lui, est déjà prévenu (en-tête
    hedgé) ; sans ce message l'humain ne l'était jamais.

    Le reste est l'objection de l'utilisateur (2026-08-21) : un prompt qui ne
    nomme rien peut être parfaitement légitime. « Finalement affiche la
    température en °C au lieu de °F », après un premier prompt qui nommait bien
    la puce, ne fait que s'appuyer sur le code déjà écrit -- et sur un
    « Modifier » le modèle REÇOIT ce code. La référence y est écrite, pas
    devinée : annoncer « aucune référence reconnue » y serait faux.

    Tranché par l'ACTION choisie par l'utilisateur, jamais par le mode : le
    chemin débutant parle parce que son action régénère tout depuis le prompt
    (son 2ᵉ prompt écrase, l'app le fait confirmer), pas parce qu'il est le
    mode débutant.
    """
    if not by_resemblance:
        return False
    model_gets_existing_code = (action == _CORRECT and has_targets
                                and not from_scratch)
    return not model_gets_existing_code
