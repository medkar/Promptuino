"""Intent↔code conformance review — gate + intent builder (layer C).

Layer C of the behavioral-review pipeline (spec 2026-07-06): the app knows the
INTENT (each feature's prompt history) so it can ask the model "does the code
do what was asked?". This module holds the pure, Qt-free glue: the capability
gate and the intent string builder. The actual review call is
`AIBackend.review_conformance` (ai_backends/base.py); applying its fix reuses
the SEARCH/REPLACE pipeline + guard.

────────────────────────────────────────────────────────────────────────────
BACKEND GATE — how to restrict layer C, and WHY
────────────────────────────────────────────────────────────────────────────
`CONFORMANCE_ON_SLM` decides whether the conformance review is offered on a
SMALL LOCAL MODEL (`backend.is_slm()` — e.g. Ollama).

  - True  (current default): offered on EVERY backend, including the local
           SLM. Chosen to let us TEST the feature everywhere.
  - False: offered ONLY on capable backends (Claude CLI / cloud APIs). On the
           local SLM the review is HIDDEN/disabled with an explanatory tooltip.

WHY you may want False: layer C is a SEMANTIC judgment ("does the logic match
the intent?"). A weak local SLM does this poorly — false positives and
hazardous "fixes" — so on Ollama the review disappoints. Layer B
(behavior_lint) stays reliable everywhere and is unaffected by this flag.

TO RESTRICT: flip the single flag below to `False`. That is the ONLY change
needed; every call site goes through `conformance_available(backend)`.
"""
from __future__ import annotations

from .gen_prompts import combine_feature_prompts

# Single switch (see module docstring). True = offer layer C on every backend
# (incl. local SLM) so we can test it; set False to restrict to capable
# backends (non-SLM) once the SLM quality proves too unreliable.
CONFORMANCE_ON_SLM = True


def conformance_available(backend) -> bool:
    """Whether layer C (intent↔code review) should be offered for `backend`.
    Always True when CONFORMANCE_ON_SLM ; otherwise True only for a capable
    (non-SLM) backend. A None backend is never eligible."""
    if backend is None:
        return False
    if CONFORMANCE_ON_SLM:
        return True
    return not backend.is_slm()


def build_intent(features) -> str:
    """The reference INTENT of a sketch = every feature's full prompt history
    (original + modifications), combined. Empty string if no feature (raw
    code) — the caller then hides layer C (no reliable intent to check
    against). The synthetic `manual` feature is excluded (hand-typed code has
    no rewritten intent)."""
    from .feature_model import ai_features
    prompts = [f.full_prompt() for f in ai_features([f for f in features if f is not None])]
    prompts = [p for p in prompts if p and p.strip()]
    if not prompts:
        return ""
    return combine_feature_prompts(prompts)
