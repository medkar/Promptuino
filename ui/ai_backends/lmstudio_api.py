"""API NATIVE de LM Studio (`/api/v0/...`), que l'API compatible OpenAI ne
remplace pas.

Deux informations ne vivent QUE la : le contexte reellement charge, et le TYPE
du modele. Module **pur** -- aucun Qt, aucun acces disque, transport injectable
pour que les tests ne touchent jamais le reseau (meme discipline que
`ui/library_index.py`).

Tout est mesure sur **LM Studio 0.4.27+2** le 2026-11-04 ; les payloads des
tests sont copies de ces reponses reelles.
"""
from __future__ import annotations

import json
import urllib.request

_TIMEOUT = 10          # une requete locale ; au-dela, le serveur ne repond pas

# ⛔ EXCLUSION, et non liste blanche -- la decision tient a une mesure qui a
# failli coûter un defaut silencieux. Le plan prevoyait de garder
# `type == "llm"`. Or le Gemma 4 E4B de l'utilisateur sort en **`vlm`** (il
# embarque un projecteur d'image), et un filtre sur « llm » l'aurait fait
# DISPARAITRE de la liste : l'utilisateur telecharge un modele, Promptuino ne
# le propose pas, et rien ne dit pourquoi.
#
# ⚠️ Trois valeurs seulement ont ete OBSERVEES (`llm`, `vlm`, `embeddings`) :
# on ne connait donc pas la taxonomie entiere. Exclure ce qu'on sait
# inutilisable fait donc moins de degats que n'admettre que ce qu'on connait --
# un type conversationnel inconnu reste propose, au prix d'un type non
# conversationnel inconnu qui passerait. Le filtre par sous-chaine de
# `openai_compat` (« embed », « whisper »...) reste en second rideau.
_NON_CHAT_TYPES = frozenset({
    "embeddings", "embedding",
    "reranker", "rerank",
    "tts", "stt", "whisper",
})


def _native_root(base_url: str) -> str:
    """De l'URL configuree vers la racine de l'API native.

    ⚠️ L'utilisateur configure l'endpoint compatible OpenAI
    (`http://127.0.0.1:1234/v1`), mais l'API native vit a la RACINE
    (`http://127.0.0.1:1234/api/v0/...`). Oublier de retirer le suffixe donne
    un 404 que rien ne signale : la liste se vide, et on croit le serveur
    eteint.
    """
    root = (base_url or "").rstrip("/")
    # ⚠️ Du PLUS LONG au plus court, et ce n'est pas cosmetique : teste dans
    # l'autre sens, « /api/v0 » matchait « /v0 » d'abord et laissait « /api »
    # tronque. Trouve en mesurant, pas en relisant.
    for suffixe in ("/api/v1", "/api/v0", "/v1", "/v0"):
        if root.endswith(suffixe):
            return root[: -len(suffixe)]
    return root


def _get_json(url: str, timeout: int, transport) -> dict | None:
    """Rend le JSON, ou None sur TOUTE erreur -- jamais d'exception.

    Cette fonction sert a renseigner un ecran : une panne doit s'y traduire par
    « je ne sais pas », pas par une trace.
    """
    # ⚠️ `except Exception` est VOULU, et le contrat de la fonction le
    # justifie : « rend le JSON ou None, jamais d'exception ». Une liste de
    # types precis a deja laisse passer deux choses -- un transport de test qui
    # leve, et tout ce qu'`urllib` peut inventer sous un proxy mal configure.
    # Une trace qui traverse l'interface pour un serveur local injoignable
    # serait un defaut, pas une information.
    try:
        if transport is not None:
            return transport(url, timeout)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as rep:
            return json.loads(rep.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def models(base_url: str, *, transport=None,
           timeout: int = _TIMEOUT) -> list[dict]:
    """Les fiches de l'API native, ou [] si le serveur ne repond pas.

    ⚠️ Une liste vide ne veut PAS dire « aucun modele » : elle veut dire
    « aucun modele OU serveur muet ». L'appelant qui a besoin de distinguer
    les deux utilise `server_responds`.
    """
    data = _get_json(f"{_native_root(base_url)}/api/v0/models", timeout, transport)
    if not isinstance(data, dict):
        return []
    fiches = data.get("data")
    return [f for f in fiches if isinstance(f, dict)] if isinstance(fiches, list) else []


def server_responds(base_url: str, *, transport=None,
                    timeout: int = _TIMEOUT) -> bool:
    """Le serveur repond-il ? Distinct de « a-t-il des modeles »."""
    return isinstance(
        _get_json(f"{_native_root(base_url)}/api/v0/models", timeout, transport),
        dict,
    )


def chat_models(base_url: str, *, transport=None,
                timeout: int = _TIMEOUT) -> list[str]:
    """Les identifiants des modeles avec lesquels on peut CONVERSER.

    Le type vient du SERVEUR, pas d'une devinette sur le nom -- c'est ce que
    l'API compatible OpenAI ne sait pas dire (`/v1/models` ne rend que
    `id` / `object` / `owned_by`).
    """
    out: list[str] = []
    for f in models(base_url, transport=transport, timeout=timeout):
        mid = f.get("id")
        if not mid:
            continue
        if str(f.get("type") or "").lower() in _NON_CHAT_TYPES:
            continue
        out.append(mid)
    return out


def loaded_context(base_url: str, model_id: str, *, transport=None,
                   timeout: int = _TIMEOUT) -> int | None:
    """Le contexte REELLEMENT charge pour ce modele, ou None si on l'ignore.

    ⛔ NE REPLIE JAMAIS SUR `max_context_length`, et c'est la regle la plus
    importante de ce module. Mesure du 2026-11-04 : le Gemma 4 E2B annonce
    `max_context_length: 131072` alors que le serveur, une fois le modele
    charge, peut n'en servir que 4096. Prendre le plafond du fichier GGUF pour
    le reglage actif ferait emballer 128k de prompt par
    `generation/context_budget.py` -- une panne, et SILENCIEUSE, parce que le
    chiffre a l'air mesure.

    `None` veut dire « inconnu », ce que l'ecran doit DIRE : le champ
    `loaded_context_length` n'existe que si `state == "loaded"`, et LM Studio
    ne charge pas forcement a la premiere requete (mesure : une requete sur un
    modele non charge ECHOUE).
    """
    if not model_id:
        return None
    for f in models(base_url, transport=transport, timeout=timeout):
        if f.get("id") != model_id:
            continue
        if str(f.get("state") or "").lower() != "loaded":
            return None
        valeur = f.get("loaded_context_length")
        return valeur if isinstance(valeur, int) and valeur > 0 else None
    return None


def is_loaded(base_url: str, model_id: str, *, transport=None,
              timeout: int = _TIMEOUT) -> bool:
    """Ce modele est-il charge ? Un modele non charge fait ECHOUER la
    generation : le serveur repond « No models loaded. Please load a model in
    the developer page or use the 'lms load' command » (mesure du
    2026-11-04). C'est donc un ETAT ROUGE de l'ecran, pas un detail."""
    if not model_id:
        return False
    for f in models(base_url, transport=transport, timeout=timeout):
        if f.get("id") == model_id:
            return str(f.get("state") or "").lower() == "loaded"
    return False
