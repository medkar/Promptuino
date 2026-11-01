"""Deterministic heuristics to filter chat messages BEFORE the LLM.

Two roles:
1. `is_generation_intent`: detects code generation requests
   ("fais clignoter", "ecris-moi", "make blink", etc.) to redirect them
   to the workshop instead of calling the LLM.
2. `is_off_scope`: detects blatantly out-of-scope questions (weather,
   capital, recipe, etc.) to reply with a standardized refusal without
   calling the LLM.

Philosophy: 7B SLMs are unreliable at following multi-clause
rules in a system prompt. We filter upstream with deterministic
regexes -- what we can do in Python, we don't delegate to the
LLM (cf wiring/markers.py same philosophy).

Multilingual: FR/EN/ES/IT to match the project's i18n spec.
"""
from __future__ import annotations

import re


# Generation intent: imperative verbs + "Arduino code" indicator

# Imperative verbs that indicate a code production request.
# Word-boundary regex case-insensitive. Covers FR/EN/ES/IT.
# NOTE: broad EN verbs (make/write) restricted to the presence of an article
# to avoid false positives ("make sure", "write to Serial", "Wire.write").
_GENERATION_VERBS = (
    # FR
    r"fais",        # "fais clignoter"
    r"fais-moi",
    r"ecris(?:-moi)?",
    r"ecrire",
    r"code-moi",
    r"coder",
    r"genere",      # "genere" -> accent-less normalized to match school keyboards
    r"generer",
    r"cree(?:-moi)?",
    r"creer",
    r"programme(?:-moi)?",
    r"ajoute(?:-moi)?",   # "Ajouter" est une action de l'atelier (QA D2.3)
    r"ajouter",
    # EN
    r"make\s+(?:an?|the|some|me)",   # "make an LED blink" but not "make sure"
    r"write\s+(?:me\s+)?(?:an?|the|some|code)",  # "write me a func" but not "write to Serial"
    r"generate",
    r"create",
    r"program",
    # Article required, same caution as make/write above: a bare "add" catches
    # "add 5 to the counter" / "add overflow warnings", which ask for nothing.
    r"add\s+(?:an?|the|some)",
    # "build" removed: false positive on "build error" / "failed to build"
    # ES
    r"escribe",     # "escribeme"
    r"escribir",
    r"haz(?:me)?",
    r"crea",        # ES + IT
    r"genera",      # ES + IT
    r"programa",
    r"a[nñ]ade",    # accent optional: school keyboards often lack the tilde
    r"a[nñ]adir",
    r"agrega",
    # IT
    r"scrivi(?:mi)?",
    r"fai",         # "fai lampeggiare"
    r"programma",
    r"aggiungi",
)

_GENERATION_PATTERN = re.compile(
    r"\b(?:" + "|".join(_GENERATION_VERBS) + r")\b",
    re.IGNORECASE,
)


# A sentence OPENING with an interrogative adverb is a how-to QUESTION, not a
# request -- whatever verb it happens to contain further on.
#
# The opening is the discriminator, NOT the question mark: "peux-tu écrire un
# programme… ?" ends with one and remains a request, so keying on punctuation
# would stop redirecting real requests. Measured against the QA cases
# (2026-08-08): "comment je fais si l'app se trompe de composant ?" and
# "comment modifier un composant faux" both open this way, while every
# generation phrasing in this file's tests does not.
_QUESTION_OPENERS = (
    r"comment", r"pourquoi", r"quand", r"ou est",       # FR
    r"how", r"why", r"when", r"where",                  # EN
    r"como", r"cómo", r"por que", r"por qué", r"cuando",  # ES
    r"come", r"perche", r"perché", r"quando", r"dove",  # IT
)

_QUESTION_OPENER_PATTERN = re.compile(
    r"^\W*(?:" + "|".join(_QUESTION_OPENERS) + r")\b",
    re.IGNORECASE,
)


def is_how_to_question(text: str) -> bool:
    """True when `text` opens with an interrogative adverb ("comment…",
    "how…"). Such a message asks the assistant to EXPLAIN, so it must be
    answered -- never swapped for a redirect nor decorated with an action
    button."""
    return bool(_QUESTION_OPENER_PATTERN.match((text or "").strip()))


def is_generation_intent(text: str) -> bool:
    """Returns True if `text` looks like an embedded code generation
    request (= to redirect to the workshop instead of calling the LLM).

    Heuristic: presence of an imperative code production verb
    (FR/EN/ES/IT), EXCEPT in a how-to question.

    That exception is not cosmetic: this intent SHORT-CIRCUITS the LLM
    (`ChatTurnKind.GENERATION_REDIRECT` returns before any call), so a false
    positive means the question is never answered at all. "comment je fais si
    l'app se trompe de composant ?" contains "fais" and was therefore
    redirected -- while being the most natural French phrasing for asking for
    help. This docstring used to call such false positives benign; QA D2
    (2026-08-08) showed they are frequent, and costly.
    """
    if not text or not text.strip():
        return False
    if is_how_to_question(text):
        return False
    return bool(_GENERATION_PATTERN.search(text))


# Off-scope: explicit keywords outside Arduino / embedded

# Words/phrases that NEVER have any relation to an Arduino project.
# Word-boundary regex case-insensitive. Conservative: we only list
# the blatant off-scope ones. Ambiguous questions go to the LLM (which has
# its short refusal system prompt).
_OFFSCOPE_KEYWORDS = (
    # Geography / general knowledge
    r"capitale",
    r"capital(?:\s+of)?",
    # Cooking
    r"recette",
    r"recipe",
    r"receta",
    r"ricetta",
    # Weather
    r"meteo",
    r"weather",
    r"quel temps",
    r"what'?s the weather",
    # External search
    r"wikipedia",
    r"google",
    r"bing",
    # Entertainment
    r"netflix",   # "film" removed: collision with "thin film resistor" / "film capacitor"
    r"tiktok",
    r"youtube",
    r"movie",
    r"pelicula",
    # Sport / general news
    r"foot",
    r"football",
    r"soccer",
    r"basketball",
)

_OFFSCOPE_PATTERN = re.compile(
    r"\b(?:" + "|".join(_OFFSCOPE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def is_off_scope(text: str) -> bool:
    """Returns True if `text` contains a blatant off-scope keyword
    (= to politely refuse without calling the LLM).

    Conservative: we only flag the OBVIOUS off-scope ones. Fuzzy
    questions go to the LLM which handles them via its scope system prompt.
    """
    if not text or not text.strip():
        return False
    return bool(_OFFSCOPE_PATTERN.search(text))


# Correction intent: imperative verbs for MODIFICATION of the existing.

# Sister of _GENERATION_VERBS. Word-boundary regex case-insensitive, FR/EN/ES/IT.
# Accent-less forms (corrige/repare), like _GENERATION_VERBS (genere/cree):
# the text is not de-accented upstream and school keyboards often type
# without accents. `update` (EN) deliberately EXCLUDED (too noisy:
# "update available"). Benign false positives: the « Corriger dans
# Studio » button is additive, it never short-circuits the chat's reply.
_CORRECTION_VERBS = (
    # FR
    r"corrige(?:-moi)?",
    r"corriger",
    r"modifie(?:-moi)?",
    r"modifier",
    r"change",
    r"changer",
    r"remplace",
    r"remplacer",
    r"ajuste",
    r"ajuster",
    r"repare",
    r"reparer",
    # EN ("change" shared with FR; "update" deliberately excluded)
    r"fix",
    r"correct",
    r"modify",
    r"replace",
    r"adjust",
    # ES ("corrige"/"modifica"/"cambia" shared with FR/IT)
    r"corregir",
    r"modifica",
    r"cambia",
    r"cambiar",
    r"reemplaza",
    r"ajusta",
    r"repara",
    # IT
    r"correggi",
    r"correggere",
    r"cambiare",
    r"sostituisci",
    r"aggiusta",
    r"ripara",
)

_CORRECTION_PATTERN = re.compile(
    r"\b(?:" + "|".join(_CORRECTION_VERBS) + r")\b",
    re.IGNORECASE,
)


def is_correction_intent(text: str) -> bool:
    """Returns True if `text` expresses an intention to CORRECT / MODIFY
    the existing code (FR/EN/ES/IT). Deterministic heuristic, sister of
    is_generation_intent.

    Additive: does NOT short-circuit the LLM (unlike generation).
    Serves only to offer a « Corriger dans Studio » button under the
    chat's normal reply. False positives are benign (non-intrusive
    button, reply never blocked) -- but a how-to question is excluded all the
    same: "comment modifier un composant faux" is asking how the app works,
    and offering to change the code under a purely informative answer is
    incongruous (QA D2, 2026-08-08).
    """
    if not text or not text.strip():
        return False
    if is_how_to_question(text):
        return False
    return bool(_CORRECTION_PATTERN.search(text))
