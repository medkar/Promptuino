"""Backend << forfait ChatGPT >> : la Responses API avec le jeton de l'utilisateur
(TODO #122).

Sous-classe d'`OpenAICompatBackend` : TOUTE la construction des prompts
(generation, reparation, explication, chat) est heritee ; seule la couche
d'envoi change. Contrat documente
(developers.openai.com/siwc/token-sharing-open-source/models-and-inference) :

- `POST https://api.openai.com/v1/responses`, `stream: true` et
  `store: false` OBLIGATOIRES. Corps : `model`, `instructions`, `input`.
  ⚠️ Ni `temperature` ni `max_output_tokens` : la doc ne les montre pas, et un
  parametre refuse ferait echouer toutes les generations.
- Texte dans `response.output_text.delta` ; succes SEULEMENT a
  `response.completed` -- un flux qui s'arrete avant est un ECHEC, meme avec
  du texte (« Treat inference as successful only after response.completed »).
- Forfait epuise : 429 `subscription_sharing_usage_limit_exceeded`, aussi en
  plein flux dans `response.failed`. Le message renvoie vers « Gerer
  l'usage », comme le demande le guide d'interface.
- Un 401 : UN renouvellement force, UN nouvel essai. Au-dela, reconnexion.

Le transport est celui de l'adaptateur (`iter_sse`, `get_json`,
`close_inflight`) : le bouton Annuler d'une generation marche donc tel quel.
"""
from __future__ import annotations

import json
from typing import Iterator

from .openai_compat import (
    OpenAICompatBackend, HttpError, _DEFAULT_TIMEOUT, _LIST_TIMEOUT,
    _PROBE_TIMEOUT, _TIMEOUT, _error_message, _provider_detail, _status_kind,
)
from ..chatgpt_auth import PAGE_USAGE, RESOURCE, session as _session_partagee

CODE_QUOTA = "subscription_sharing_usage_limit_exceeded"
CODE_NON_PRIS_EN_CHARGE = "subscription_sharing_unsupported_capability"

# Le niveau de reflexion (TODO #123) : `reasoning.effort`, que la doc de la
# connexion ChatGPT NE MONTRE PAS. Sa page d'erreurs dit en revanche qu'un 400
# `subscription_sharing_unsupported_capability` nomme le champ fautif dans
# `error.param`, et qu'il faut alors « retirer l'entree non prise en charge »
# -- jamais renvoyer le meme corps. Un refus vaut pour le MODELE et pour la
# session : on ne redemande pas a chaque requete. Inverifiable sans compte
# payant (QA AW2).
_REFLEXION_REFUSEE: set = set()


def reflexion_refusee(modele: str) -> bool:
    """OpenAI a-t-il refuse le niveau de reflexion pour ce modele, cette
    session ? La section l'affiche sous le curseur."""
    return modele in _REFLEXION_REFUSEE


def _refus_de_la_reflexion(e: HttpError) -> bool:
    """Ce 400 vise-t-il le champ `reasoning` ? Un refus « non pris en
    charge » sans `param` est attribue a la reflexion -- c'est le seul champ
    facultatif que l'app envoie."""
    if e.status != 400:
        return False
    try:
        corps = json.loads(e.body or "{}")
    except Exception:
        return False
    err = corps.get("error") if isinstance(corps, dict) else None
    if not isinstance(err, dict):
        return False
    param = str(err.get("param") or "")
    if param:
        return param.split(".")[0] == "reasoning"
    return err.get("code") == CODE_NON_PRIS_EN_CHARGE

# Repli anglais si l'i18n n'est pas chargeable (meme discipline que
# `openai_compat._ERR_FALLBACK`).
_REPLI = {
    "chatgpt_err_signed_out": "Not signed in to ChatGPT — sign in under “AI Model”.",
    "chatgpt_err_quota": "Your ChatGPT plan's usage limit is reached — Manage usage: {url}",
    "chatgpt_err_forbidden": "This ChatGPT account can't use its plan in Promptuino.",
    "chatgpt_err_interrupted": "The ChatGPT response stopped before it was complete.",
    "chatgpt_err_network": "Couldn't reach OpenAI (network down or service unavailable) — your ChatGPT sign-in is kept, try again in a moment.",
}


def _texte(cle: str, **champs) -> str:
    base = ""
    try:
        from ..i18n import lang_manager
        base = getattr(lang_manager.current, cle, "")
    except Exception:
        base = ""
    return (base or _REPLI[cle]).format(**champs)


def _code_et_message(erreur) -> "tuple[str, str]":
    if isinstance(erreur, dict):
        return str(erreur.get("code") or ""), str(erreur.get("message") or "")
    if isinstance(erreur, str):
        return "", erreur
    return "", ""


def _message_http(e: HttpError) -> str:
    try:
        corps = json.loads(e.body or "{}")
    except Exception:
        corps = {}
    code, _msg = _code_et_message(corps.get("error") if isinstance(corps, dict) else None)
    if code == CODE_QUOTA or e.status == 429:
        return _texte("chatgpt_err_quota", url=PAGE_USAGE)
    if e.status == 401:
        return _texte("chatgpt_err_signed_out")
    if e.status == 403:
        detail = _provider_detail(e.body)
        base = _texte("chatgpt_err_forbidden")
        return f"{base} — {detail}" if detail else base
    return _error_message(_status_kind(e.status), _provider_detail(e.body))


def _message_evenement(erreur) -> str:
    code, msg = _code_et_message(erreur)
    if code == CODE_QUOTA:
        return _texte("chatgpt_err_quota", url=PAGE_USAGE)
    return _error_message("provider", msg)


# `effort=EN_DIRECT` : le niveau est relu dans `ai_config` a chaque requete.
# La pastille du chat le change sans recreer le moteur (2026-11-07).
EN_DIRECT = object()


class ChatGPTPlanBackend(OpenAICompatBackend):
    def __init__(self, model: str, *, effort: "str | None" = None,
                 session=None, transport=None):
        super().__init__(base_url=RESOURCE, api_key="", model=model,
                         backend_id="chatgpt", label="ChatGPT",
                         context_window_hint=128_000, transport=transport)
        self._session = session or _session_partagee
        # « low » / « medium » / « high » (`ui.reflexion.NIVEAUX_CHATGPT`) ;
        # None : le champ n'est pas envoye.
        self._effort = effort

    # ── Identite / disponibilite ─────────────────────────────
    @property
    def requires_api_key(self) -> bool:
        return False

    def is_available(self) -> bool:
        compte = self._session.compte()
        return bool(compte and compte.get("forfait") and self._model)

    # ── Envoi ────────────────────────────────────────────────
    def _entetes(self, jeton: str) -> dict:
        return {"Authorization": f"Bearer {jeton}",
                "Content-Type": "application/json"}

    def _corps(self, system: str, messages: list[dict]) -> dict:
        corps = {"model": self._model,
                 "input": [{"role": m["role"], "content": m["content"]}
                           for m in messages],
                 "store": False, "stream": True}
        if system:
            corps["instructions"] = system
        effort = self._effort
        if effort is EN_DIRECT:
            from ..ai_config import ai_config   # lazy: evite un cycle
            effort = ai_config.chatgpt_reasoning
        if effort and not reflexion_refusee(self._model):
            corps["reasoning"] = {"effort": effort}
        return corps

    def _flux(self, system: str, messages: list[dict], timeout) -> Iterator[str]:
        url = f"{self._base_url}/responses"
        corps = self._corps(system, messages)
        for essai in (0, 1):
            jeton = self._session.jeton(forcer=essai == 1)
            if not jeton:
                # None ne veut pas toujours dire « deconnecte » : une panne
                # reseau au renouvellement garde les identifiants.
                if getattr(self._session, "panne_reseau", False):
                    raise RuntimeError(_texte("chatgpt_err_network"))
                raise RuntimeError(_texte("chatgpt_err_signed_out"))
            try:
                termine = False
                for ligne in self._transport.iter_sse(url, self._entetes(jeton),
                                                      corps, timeout):
                    ligne = ligne.strip()
                    if not ligne.startswith("data:"):
                        continue                 # « event: … », commentaires
                    donnee = ligne[len("data:"):].strip()
                    if donnee == "[DONE]":
                        break
                    try:
                        ev = json.loads(donnee)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(ev, dict):
                        continue
                    genre = ev.get("type")
                    if genre == "response.output_text.delta":
                        morceau = ev.get("delta")
                        if isinstance(morceau, str) and morceau:
                            yield morceau
                    elif genre == "response.completed":
                        termine = True
                        break
                    elif genre in ("response.failed", "response.incomplete"):
                        reponse = ev.get("response") if isinstance(ev.get("response"), dict) else {}
                        raise RuntimeError(_message_evenement(reponse.get("error"))
                                           if reponse.get("error")
                                           else _texte("chatgpt_err_interrupted"))
                    elif genre == "error":
                        raise RuntimeError(_message_evenement(ev))
                if not termine:
                    raise RuntimeError(_texte("chatgpt_err_interrupted"))
                return
            except HttpError as e:
                # Un 401 arrive AVANT le flux : rien n'a ete rendu, on peut
                # renouveler et recommencer une fois.
                if e.status == 401 and essai == 0:
                    continue
                if "reasoning" in corps and _refus_de_la_reflexion(e):
                    # Retirer le champ refuse, comme la doc le demande, puis
                    # renvoyer : le modele repond a son niveau habituel.
                    _REFLEXION_REFUSEE.add(self._model)
                    yield from self._flux(system, messages, timeout)
                    return
                raise RuntimeError(_message_http(e)) from e
            except ConnectionError as e:
                raise RuntimeError(_error_message("network")) from e

    def _complete(self, system: str, messages: list[dict], *,
                  temperature=None, max_tokens=None,
                  timeout=_DEFAULT_TIMEOUT) -> str:
        """Le flux est obligatoire : on le COLLECTE. `timeout=None` (la
        generation, TODO #24) reste « aucun delai »."""
        delai = _TIMEOUT if timeout is _DEFAULT_TIMEOUT else timeout
        return "".join(self._flux(system, messages, delai))

    def _complete_stream(self, system: str, messages: list[dict], *,
                         temperature=None, max_tokens=None) -> Iterator[str]:
        yield from self._flux(system, messages, _TIMEOUT)

    # ── Modeles et sonde ─────────────────────────────────────
    def list_models_detailed(self) -> "tuple[list[str], str]":
        """Le catalogue DEPEND DU COMPTE : tableau `models`, garder
        `visibility == "list"`, identifiant `slug`. Ordre conserve."""
        jeton = self._session.jeton()
        if not jeton:
            return [], "auth"
        try:
            data = self._transport.get_json(f"{self._base_url}/models",
                                            self._entetes(jeton), _LIST_TIMEOUT)
        except HttpError as e:
            return [], _status_kind(e.status)
        except ConnectionError:
            return [], "network"
        modeles = []
        for m in (data or {}).get("models") or []:
            if isinstance(m, dict) and m.get("visibility") == "list":
                slug = m.get("slug") or m.get("id")
                if slug:
                    modeles.append(str(slug))
        return modeles, ("" if modeles else "empty")

    def probe_model(self) -> "tuple[bool, str]":
        """Un VRAI aller-retour minime, jusqu'a `response.completed`."""
        try:
            for _m in self._flux("", [{"role": "user", "content": "ping"}],
                                 _PROBE_TIMEOUT):
                pass
            return True, ""
        except RuntimeError as e:
            return False, str(e)
        except Exception as e:                    # jamais lever vers l'UI
            return False, f"{type(e).__name__}: {e}"
