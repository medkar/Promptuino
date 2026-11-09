"""Le moteur LM Studio : l'adaptateur compatible OpenAI, plus la reflexion.

Sous-classe d'`OpenAICompatBackend` : toute la construction des prompts est
heritee ; seuls changent les champs ajoutes a chaque requete.

- **Aucun plafond de reponse** (decision de l'auteur, 2026-11-06) : la
  reflexion le mangeait -- mesure, 505 tokens de reflexion sur 600, reponse
  COUPEE.
- **La reflexion** (TODO #123) : desactivee par defaut. Par l'API compatible
  OpenAI, SEULE `reasoning_effort: "none"` la coupe (mesure sur 0.4 : 0 token,
  0,3 s au lieu de 5,3 s) ; l'activer, c'est ne rien envoyer -- le modele
  reflechit par defaut. Le champ n'est envoye qu'a un modele dont LM Studio
  dit qu'il accepte « off » (`capabilities.reasoning.allowed_options`) : il
  n'a ete essaye sur rien d'autre.

La capacite du modele se lit a la PREMIERE requete -- toujours dans un fil
(generation, chat, sonde) -- jamais a la construction, que la vue fait sur le
fil de l'interface. Lue une fois ; tant que le serveur se tait, on relit.
"""
from __future__ import annotations

from .openai_compat import OpenAICompatBackend
from .. import reflexion

_A_LIRE = object()


class LMStudioBackend(OpenAICompatBackend):
    def __init__(self, base_url: str, model: str, *, reflexion: "bool | None",
                 context_window_hint: int, fiche=None, transport=None):
        super().__init__(base_url=base_url, api_key="", model=model,
                         backend_id="lmstudio", label="LM Studio",
                         context_window_hint=context_window_hint,
                         requires_key=False, max_output_tokens=None,
                         transport=transport)
        # None : relu dans `ai_config` a chaque requete -- la pastille du chat
        # le change sans recreer le moteur (2026-11-07).
        self._reflexion = None if reflexion is None else bool(reflexion)
        if fiche is None:
            from .. import lmstudio_models

            def fiche():
                return lmstudio_models.fiche(base_url, model)
        self._lire_fiche = fiche
        self._capacite = _A_LIRE
        self._fiche = None              # la fiche, des qu'elle est lue
        self._ctx_tente = False         # le maximum n'est tente qu'une fois

    def _fiche_modele(self) -> "dict | None":
        if self._fiche is None:
            self._fiche = self._lire_fiche()
        return self._fiche

    @property
    def context_window_hint(self) -> int:
        """Le reglage de l'onglet IA BORNE au maximum du modele, comme la page
        qui le charge (`contexte.ramener`) : un reglage de 131 072 avec un
        modele limite a 32 768 est charge a 32 768, et la garde « prompt trop
        long » comme le budget du chat doivent voir CE chiffre. Le maximum se
        lit une fois (jamais a la construction, qui se fait sur le fil de
        l'interface) ; serveur muet ou maximum inconnu : le reglage tel quel."""
        from .. import contexte
        hint = self._ctx_hint
        if self._fiche is None and not self._ctx_tente:
            self._ctx_tente = True
            try:
                self._fiche_modele()
            except Exception:
                pass
        ctx_max = (self._fiche or {}).get("ctx_max")
        if ctx_max:
            return contexte.ramener(hint, ctx_max)
        return hint

    def _capacite_modele(self) -> "reflexion.Capacite | None":
        if self._capacite is _A_LIRE:
            f = self._fiche_modele()
            if f is None:
                return None                 # serveur muet : on relira
            self._capacite = reflexion.depuis_lmstudio(f.get("reflexion"))
        return self._capacite

    def _champs_en_plus(self) -> dict:
        from ..ai_config import ai_config   # lazy: evite un cycle
        voulu = self._reflexion
        if voulu is None:
            voulu = ai_config.lmstudio_think
        return reflexion.lmstudio_champs(self._capacite_modele(), voulu,
                                         ai_config.lmstudio_think_level)
