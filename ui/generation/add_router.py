"""Une demande de MODIFICATION déguisée en ajout (TODO #88, 2026-08-31).

Mesuré : sur « le clignotement ne doit avoir lieu **que si** l'interrupteur
est fermé », le modèle ne peut pas toucher au code de la fonctionnalité
existante (le contrat d'Ajout est append-only), donc il fabrique un SECOND
clignotement gardé, pendant que le premier reste inconditionnel. 2/2. Ça
compile, et la demande n'est pas satisfaite — échec silencieux.

Aucune règle de fusion ne peut rattraper ça en aval : la demande n'est pas
un ajout, c'est une modification. Ce module la reconnaît AVANT la
génération, pour que la modale {Régénérer / Ajouter / Modifier} s'ouvre sur
« Modifier <la bonne fonctionnalité> » au lieu de « Ajouter ».

⛔ **CATÉGORIEL, jamais un score.** Le projet a déjà débranché un détecteur
qui devinait par proximité sémantique (`rag._AUTO_AMBIGUITY_NET_ENABLED =
False`, faux positifs impossibles à calibrer). Ici, deux conditions
lexicales fermées, toutes deux nécessaires :

  1. le prompt porte un **marqueur de modification** (lexique clos, ×4
     langues) — c'est la PORTE, et elle seule décide qu'on propose ;
  2. il partage un mot de contenu avec une fonctionnalité existante — ça ne
     décide rien, ça choisit seulement LAQUELLE.

Sans (1), aucune proposition, même si tout le vocabulaire se recoupe : un
ajout normal réutilise forcément les mots du projet (« ajoute une LED
verte » sur un projet à LED). Sans (2), aucune proposition non plus : on
saurait qu'il s'agit d'une modification sans savoir de QUOI.

⚠️ **Ça ne décide rien à la place de l'utilisateur** : la modale s'ouvre
sur ce défaut, il voit les trois choix et peut basculer sur « Ajouter » en
un clic. Même principe que le retrait du préfixe magique `CORRECTION …` :
on propose, on ne clique pas Générer à sa place.

Module PUR — aucun Qt, aucune lecture disque.
"""
from __future__ import annotations

import re
import unicodedata

from .feature_model import Feature


def _fold(text: str) -> str:
    """minuscules + accents repliés (même esprit que `declared_components`)."""
    nfd = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in nfd if not unicodedata.combining(ch))


# ── (1) la PORTE : marqueurs de modification, lexique CLOS ────────────────
# Expressions MULTI-MOTS de préférence (règle de CLAUDE.md : un mot générique
# fait des faux positifs). Chaque entrée dit « cette phrase agit sur un
# comportement qui EXISTE DÉJÀ », jamais « voici un nouveau comportement ».
#
# ⛔ Pièges écartés volontairement, vérifiés sur la batterie :
#   - « tant que » (« joue une note tant que le bouton est appuyé ») est un
#     AJOUT parfaitement normal : réagir à un état n'est pas modifier ;
#   - « quand » / « si » seuls : la moitié des ajouts conditionnels les
#     contiennent ;
#   - « plus vite » / « moins fort » seuls : un nouveau composant peut être
#     décrit ainsi.
_MODIFICATION_MARKERS: tuple[str, ...] = (
    # — restrictifs : on RESTREINT un comportement existant
    "que si", "que quand", "que lorsque",
    "seulement si", "seulement quand", "seulement lorsque",
    "uniquement si", "uniquement quand", "uniquement lorsque",
    "sauf si", "sauf quand",
    "only if", "only when", "unless",
    "solo si", "solo cuando", "salvo si", "a menos que",
    "solo se", "solo quando", "a meno che",
    # L'adverbe restrictif SEUL. Ajouté après mesure : l'ordre des mots
    # « adverbe + verbe + condition » (« only blink the LED when… »,
    # « solo muestra la temperatura si… ») ne présente aucun de mes
    # bigrammes, et ces deux cas passaient à travers. Coût vérifié sur la
    # batterie : toujours 0 faux positif — restreindre est justement ce
    # que ces adverbes DISENT, quel que soit ce qui les suit.
    "seulement", "uniquement", "only ", "solo ", "solamente",
    "soltanto", "unicamente",
    # — substitutifs : on REMPLACE un comportement existant
    "au lieu de", "a la place de", "plutot que", "plutot qu",
    "instead of", "rather than",
    "en vez de", "en lugar de",
    "invece di", "al posto di",
    # — impératifs de modification
    "ne doit plus", "ne doit pas", "ne dois plus", "ne plus",
    "arrete de", "arreter de", "supprime le", "supprime la",
    "enleve le", "enleve la", "retire le", "retire la",
    "modifie", "change le", "change la", "change les",
    "remplace le", "remplace la", "remplace les",
    "no longer", "stop the", "remove the", "replace the", "change the",
    "deja de", "quita el", "quita la", "reemplaza",
    "smetti di", "togli il", "togli la", "sostituisci",
)

# ── (2) le CIBLAGE : mots de contenu partagés ────────────────────────────
# Mots vides des 4 langues + vocabulaire de plomberie Arduino qui traverse
# tous les prompts (« broche », « code »…) : les garder ferait matcher
# n'importe quelle fonctionnalité avec n'importe quel prompt.
_STOPWORDS = frozenset(_fold(w) for w in (
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "a", "au",
    "aux", "en", "sur", "dans", "pour", "avec", "sans", "par", "que", "qui",
    "quand", "si", "ne", "pas", "plus", "moins", "est", "sont", "doit",
    "doivent", "avoir", "etre", "faire", "fait", "fais", "lieu", "son", "sa",
    "ses", "ce", "cet", "cette", "mon", "ma", "mes", "il", "elle", "on",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "when", "if", "not", "must", "should", "be", "is", "are", "do", "does",
    "el", "los", "las", "y", "o", "del", "por", "para", "con", "sin",
    "cuando", "si", "no", "debe", "ser", "hacer",
    "il", "lo", "gli", "e", "di", "da", "per", "con", "senza", "quando",
    "se", "non", "deve", "essere", "fare",
    # plomberie Arduino, présente partout
    "broche", "broches", "pin", "pins", "arduino", "code", "sketch",
    "carte", "board", "projet", "project", "valeur", "value",
))
# Un mot de contenu doit faire au moins 4 caractères (les plus courts sont
# soit des mots vides, soit trop génériques pour désigner quoi que ce soit).
_MIN_WORD = 4
# Radical = les 6 premiers caractères repliés. C'est ce qui fait tenir
# « clignotement » (le mot du prompt) et « clignoter » (le mot de la
# fonctionnalité) — mesuré : sans radical, le cas qui a motivé ce module
# n'était pas rattaché à sa fonctionnalité.
_STEM_LEN = 6

_WORD_RE = re.compile(r"[a-z0-9_]+")


def _stems(text: str) -> set[str]:
    out: set[str] = set()
    for w in _WORD_RE.findall(_fold(text)):
        if len(w) < _MIN_WORD or w in _STOPWORDS:
            continue
        out.add(w[:_STEM_LEN])
    return out


def prompt_asks_a_modification(prompt: str) -> bool:
    """(1) seule : le prompt agit-il sur un comportement EXISTANT ?"""
    low = _fold(prompt)
    return any(m in low for m in _MODIFICATION_MARKERS)


def modification_target(prompt: str, features: list[Feature]) -> str | None:
    """Id de la fonctionnalité que ce prompt MODIFIE, ou None.

    None dès qu'une des deux conditions manque — et None aussi en cas
    d'ÉGALITÉ entre deux fonctionnalités : proposer la première d'une liste
    serait un tirage au sort présenté comme une déduction. L'utilisateur
    garde la modale telle qu'elle s'ouvrait avant.
    """
    if not features or not prompt_asks_a_modification(prompt):
        return None
    voulus = _stems(prompt)
    if not voulus:
        return None
    scores: list[tuple[int, str]] = []
    for f in features:
        # Le PROMPT de la fonctionnalité (ce que l'utilisateur a demandé) et
        # son résumé : c'est le vocabulaire humain. Les identifiants du code
        # ne suffisent pas — mesuré sur le cas d'origine, la demande dit
        # « le clignotement » et ne cite aucun identifiant.
        texte = " ".join([f.first_prompt or "", f.prompt or "", f.summary or ""])
        n = len(voulus & _stems(texte))
        if n:
            scores.append((n, f.id))
    if not scores:
        return None
    scores.sort(key=lambda t: -t[0])
    if len(scores) > 1 and scores[0][0] == scores[1][0]:
        return None                      # égalité : on ne tire pas au sort
    return scores[0][1]
