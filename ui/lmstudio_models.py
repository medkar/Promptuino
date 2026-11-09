"""Gerer les modeles LM Studio depuis l'app — logique pure, sans Qt (TODO #121).

Frere de `ui/ollama_models.py`. Parle l'API native **v1** (`/api/v1/*`,
LM Studio >= 0.4.0), qui sait lister, telecharger, charger et decharger.
L'ecran d'etat de la section Local lit encore la **v0**
(`ui/ai_backends/lmstudio_api.py`) ; la migrer n'est pas de ce chantier.

MESURES DU 2026-11-06 sur LM Studio 0.4.27, faites avant d'ecrire une ligne
d'interface (telechargement reel de google/gemma-3-270m, puis supprime) :

- ⛔ **La taille du catalogue est fausse, dans les deux sens.** 270M : 550 Mo
  au catalogue, **241 Mo** telecharges (LM Studio a pris `qat-Q4_0`). Gemma 4
  E4B : 5,90 Go annonces, **6,33 Go** sur disque. Les tailles de `SUGGERES`
  sont donc INDICATIVES (le `~` le dit) ; la vraie arrive avec la premiere
  requete d'etat d'un telechargement.
- ✅ **Relancer la meme demande pendant un telechargement rend le MEME job.**
  C'est le filet apres un redemarrage de Promptuino. ⛔ Ce n'est PAS un
  moyen de retrouver la progression en rouvrant la fenetre : il faut un
  clic que personne ne devine (QA AV2 du 2026-11-06, voir `suivre`).
  ⛔ Mais le `total_size_bytes` de cette relance est FAUX (64 005 octets pour
  241 474 213) : `demarrer` ne rend donc AUCUN total, seul `etat` en donne.
- `estimated_completion` vaut `9999-12-31...` quand LM Studio ne sait pas.
- Charger a 16 384 tokens : 2,6 s pour un 270M, contexte relu identique.
  Charger au-dela des moyens de la machine : 500 `model_load_failed` avec un
  message clair de LM Studio, qu'on affiche tel quel.
- ⛔ **Ni annulation ni suppression** dans l'API (ni dans `lms`, demande
  ouverte lmstudio-ai/lms#579) : l'ecran renvoie vers LM Studio pour
  supprimer, et dit que fermer la fenetre n'arrete pas un telechargement.

Contrat de tout le module : **jamais d'exception vers l'ecran**. Un serveur
injoignable se dit `"muet"`, pas par une trace.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .ai_backends.lmstudio_api import _native_root

# Le plancher vit dans `ui/contexte.py`, commun aux deux moteurs depuis le
# 2026-11-06 ; re-exporte ici pour les appelants existants.
from .contexte import CTX_PROMPTUINO  # noqa: E402,F401

PAGE_CATALOGUE = "https://lmstudio.ai/models"

_TIMEOUT = 10                 # une requete locale
_TIMEOUT_CHARGEMENT = 300     # charger un gros modele peut prendre longtemps

# ─── Modeles suggeres ────────────────────────────────────────────────────
# Identifiants VERIFIES au catalogue le 2026-11-06 (lmstudio.ai/models).
# `google/gemma-4-e2b` EN TETE : c'est l'equivalent du `gemma4:e2b` par defaut
# d'Ollama (5,1 Md de parametres), le seul autour duquel l'app a ete reglee.
# ⚠️ Les autres sont proposes pour leur TAILLE, rien d'autre : pas un
# classement. Qwen 2.5 Coder, suggere chez Ollama, n'existe pas au catalogue.
SUGGERES: tuple = (
    ("google/gemma-4-e2b", 4.20e9, "5,1 Md"),
    ("google/gemma-3-1b",  0.75e9, "1 Md"),
    ("google/gemma-3-4b",  2.40e9, "4 Md"),
    ("google/gemma-4-e4b", 5.90e9, "8 Md"),
    ("google/gemma-4-12b", 7.40e9, "12 Md"),
)

# Exclusion, pas liste blanche — meme raison que `lmstudio_api._NON_CHAT_TYPES` :
# la taxonomie complete est inconnue, et un type conversationnel inconnu doit
# rester visible.
_TYPES_EXCLUS = frozenset({"embedding", "embeddings"})


def _v1(base_url: str) -> str:
    return f"{_native_root(base_url)}/api/v1"


def _json(octets: bytes) -> dict:
    try:
        valeur = json.loads(octets.decode("utf-8", errors="replace") or "{}")
    except Exception:
        return {}
    return valeur if isinstance(valeur, dict) else {}


def _requete(methode: str, url: str, corps, timeout: int,
             transport, coupure=None) -> "tuple[int | None, dict]":
    """(statut HTTP, JSON) ; statut None = serveur injoignable.

    ⚠️ `except Exception` VOULU, meme raison que `lmstudio_api._get_json` : le
    contrat est « jamais d'exception », et une liste de types precis laisse
    toujours passer quelque chose (un transport de test, un proxy).
    """
    try:
        if transport is not None:
            return transport(methode, url, corps, timeout)
        data = json.dumps(corps).encode("utf-8") if corps is not None else None
        req = urllib.request.Request(
            url, data=data, method=methode,
            headers={"Content-Type": "application/json",
                     "Accept": "application/json"})
        # `coupure` (ai_backends.coupure) : un autre fil peut couper la
        # socket AVANT la reponse -- c'est ce qui permet d'annuler un
        # chargement (le serveur l'abandonne quand le client part, mesure le
        # 2026-11-07 sur LM Studio et Ollama).
        ouvrir = coupure.urlopen if coupure is not None else urllib.request.urlopen
        try:
            with ouvrir(req, timeout=timeout) as rep:
                return rep.status, _json(rep.read())
        except urllib.error.HTTPError as e:
            return e.code, _json(e.read())
    except Exception:
        return None, {}


def _message(rep: dict) -> str:
    """Le message de LM Studio, tel quel ; "" s'il n'en a pas donne."""
    err = rep.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or "")
    return str(err) if isinstance(err, str) else ""


def _entier(v) -> "int | None":
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


# ─── Etat de l'API ───────────────────────────────────────────────────────

def etat_api(base_url: str, *, transport=None, timeout: int = _TIMEOUT) -> str:
    """`"ok"`, `"ancien"` (le serveur repond, la v1 n'existe pas : LM Studio
    < 0.4) ou `"muet"` (rien ne repond, ou une reponse illisible)."""
    statut, rep = _requete("GET", f"{_v1(base_url)}/models", None,
                           timeout, transport)
    if statut == 200 and isinstance(rep.get("models"), list):
        return "ok"
    if statut == 404:
        return "ancien"
    return "muet"


# ─── Liste ───────────────────────────────────────────────────────────────

def modeles_installes(base_url: str, *, transport=None,
                      timeout: int = _TIMEOUT) -> list:
    """Les modeles installes, sans les embeddings, tries par cle.

    Chaque fiche : `cle`, `taille` (octets EXACTS), `params`, `quant`,
    `ctx_max`, `instances` (liste de `(id, contexte charge ou None)`),
    `reflexion` (les `allowed_options` du modele, `()` s'il ne reflechit
    pas, None si LM Studio ne le dit pas -- cf. `_reflexion`).
    `[]` si le serveur ne repond pas — l'appelant qui doit distinguer
    « aucun modele » de « serveur muet » utilise `etat_api`.
    """
    statut, rep = _requete("GET", f"{_v1(base_url)}/models", None,
                           timeout, transport)
    if statut != 200 or not isinstance(rep.get("models"), list):
        return []
    fiches = []
    for m in rep["models"]:
        if not isinstance(m, dict) or not m.get("key"):
            continue
        if str(m.get("type") or "").lower() in _TYPES_EXCLUS:
            continue
        instances = []
        for inst in m.get("loaded_instances") or []:
            if isinstance(inst, dict) and inst.get("id"):
                config = inst.get("config")
                ctx = config.get("context_length") if isinstance(config, dict) else None
                instances.append((str(inst["id"]), _entier(ctx) or None))
        quant = m.get("quantization")
        fiches.append({
            "cle": str(m["key"]),
            "taille": _entier(m.get("size_bytes")),
            "params": str(m.get("params_string") or ""),
            "quant": str(quant.get("name") or "") if isinstance(quant, dict) else "",
            "ctx_max": _entier(m.get("max_context_length")) or None,
            "instances": instances,
            "reflexion": _reflexion(m.get("capabilities")),
        })
    return sorted(fiches, key=lambda f: f["cle"])


def _reflexion(capacites) -> "tuple | None":
    """`capabilities.reasoning.allowed_options` (mesure sur 0.4, 2026-11-06 :
    `["off", "on"]` pour gemma-4, `["on"]` pour phi-4-mini-reasoning, pas de
    cle `reasoning` pour qwen3-4b-2507). Sans `capabilities`, on ne sait pas."""
    if not isinstance(capacites, dict):
        return None
    raisonnement = capacites.get("reasoning")
    if not isinstance(raisonnement, dict):
        return ()
    options = raisonnement.get("allowed_options")
    return tuple(str(o) for o in options) if isinstance(options, list) else ()


def fiche(base_url: str, cle: str, *, transport=None) -> "dict | None":
    """La fiche d'un modele installe (son `ctx_max`, ses instances), ou None
    s'il n'est pas dans la liste ou si le serveur se tait."""
    return next((f for f in modeles_installes(base_url, transport=transport)
                 if f["cle"] == cle), None)


# ─── Telechargement ──────────────────────────────────────────────────────

def demarrer(base_url: str, cle: str, *, transport=None,
             timeout: int = _TIMEOUT) -> dict:
    """Lance (ou retrouve) le telechargement de `cle`.

    `{"etat": "en_cours", "job": id}`, `{"etat": "deja_la"}`,
    `{"etat": "muet"}` ou `{"etat": "erreur", "message": ...}`.
    ⛔ Aucun total : celui-ci est faux sur une relance (voir l'en-tete).
    """
    statut, rep = _requete("POST", f"{_v1(base_url)}/models/download",
                           {"model": cle}, timeout, transport)
    if statut is None:
        return {"etat": "muet"}
    if statut == 200:
        if rep.get("status") == "already_downloaded":
            return {"etat": "deja_la"}
        if rep.get("job_id") and rep.get("status") != "failed":
            return {"etat": "en_cours", "job": str(rep["job_id"])}
    return {"etat": "erreur", "message": _message(rep)}


_ETATS_JOB = {"downloading": "en_cours", "paused": "en_pause",
              "completed": "termine", "failed": "echec"}


def etat(base_url: str, job: str, *, transport=None,
         timeout: int = _TIMEOUT) -> dict:
    """Ou en est le telechargement `job`.

    `etat` : `en_cours`, `en_pause`, `termine`, `echec`, `muet`, `perdu` ou
    `inconnu` (statut que LM Studio n'a pas documente : l'appelant continue
    d'attendre).

    ⛔ `perdu` (404) n'est PAS un echec. Mesure du 2026-11-06 : LM Studio
    OUBLIE un job termine — quelques minutes apres la fin d'un
    google/gemma-3-4b reussi, son statut rendait `job_not_found`. Seule la
    liste des installes dit si le modele est arrive, et pas sous le nom
    demande (installe en `gemma-3-4b-it`).
    `recu` / `total` en octets, `debit` en octets/s ou None, `fin` (ISO) ou
    None — jamais la date sentinelle `9999-...`.
    """
    statut, rep = _requete(
        "GET", f"{_v1(base_url)}/models/download/status/{job}", None,
        timeout, transport)
    if statut is None:
        return {"etat": "muet"}
    if statut == 404:
        return {"etat": "perdu", "message": _message(rep)}
    if statut != 200:
        return {"etat": "echec", "message": _message(rep)}
    debit = rep.get("bytes_per_second")
    fin = rep.get("estimated_completion")
    return {
        "etat": _ETATS_JOB.get(rep.get("status"), "inconnu"),
        "recu": _entier(rep.get("downloaded_bytes")) or 0,
        "total": _entier(rep.get("total_size_bytes")),
        "debit": debit if isinstance(debit, (int, float)) and debit > 0 else None,
        "fin": fin if isinstance(fin, str) and fin and not fin.startswith("9999") else None,
        "message": _message(rep),
    }


# ─── Le telechargement suivi pendant la session ──────────────────────────
# QA AV2 du 2026-11-06 : fermer la fenetre pendant un telechargement, la
# rouvrir -> plus rien a l'ecran, alors que LM Studio continuait (fichiers
# `.part` qui grossissaient, job toujours `downloading`). Le numero de suivi
# vivait dans la fenetre, detruite a la fermeture.
# ⛔ L'API n'a AUCUN moyen de lister les telechargements en cours (verifie le
# meme jour : seul `download/status/:job_id` existe, tout autre chemin rend
# 404). Le numero vit donc ICI, pour la duree de la session ; apres un
# redemarrage de Promptuino, relancer le meme modele retrouve le meme job.

_SUIVIS: dict = {}


def suivre(base_url: str, cle: str, job: str, *, avant=()) -> None:
    """`avant` : les cles installees AU DEPART. C'est la seule preuve
    d'arrivee quand LM Studio a oublie le job (voir `etat`, cas `perdu`) —
    le nom demande ne sert a rien, le modele s'installe sous un autre."""
    _SUIVIS[_native_root(base_url)] = {"cle": cle, "job": job,
                                       "avant": frozenset(avant)}


def suivi(base_url: str) -> "dict | None":
    """`{"cle", "job", "avant"}` du telechargement suivi sur ce serveur, ou
    None."""
    return _SUIVIS.get(_native_root(base_url))


def oublier(base_url: str) -> None:
    _SUIVIS.pop(_native_root(base_url), None)


# ─── Charger / decharger ─────────────────────────────────────────────────

# Les instances que PROMPTUINO a chargees pendant la session, (url, id), pour
# les decharger a la fermeture (cf. `ollama_models.EPINGLES`).
EPINGLES: set = set()


def decharger(base_url: str, instance: str, *, transport=None,
              timeout: int = _TIMEOUT) -> "tuple[bool, str]":
    """(reussi, message de LM Studio). Message vide = rien a dire, ou serveur
    muet : l'appelant choisit alors son propre texte."""
    statut, rep = _requete("POST", f"{_v1(base_url)}/models/unload",
                           {"instance_id": instance}, timeout, transport)
    if statut == 200:
        EPINGLES.discard((base_url, instance))
        return True, ""
    return False, _message(rep)


def charger(base_url: str, cle: str, contexte: int = CTX_PROMPTUINO, *,
            transport=None, timeout: int = _TIMEOUT_CHARGEMENT,
            coupure=None) -> "tuple[bool, str]":
    """Charge `cle` avec `contexte` tokens, plafonne au maximum du modele.

    ⚠️ Les instances DEJA chargees de ce modele sont dechargees d'abord : c'est
    le cas « contexte trop petit », et en garder une a 4 096 tokens a cote de
    la nouvelle occuperait la memoire sans qu'on sache laquelle LM Studio
    servirait. Les AUTRES modeles ne sont jamais touches : si la memoire
    manque, LM Studio refuse avec un message, et c'est ce message qu'on rend.
    """
    fiche = next((f for f in modeles_installes(base_url, transport=transport)
                  if f["cle"] == cle), None)
    if fiche is not None:
        if fiche["ctx_max"]:
            contexte = min(contexte, fiche["ctx_max"])
        for instance, _ctx in fiche["instances"]:
            ok, msg = decharger(base_url, instance, transport=transport)
            if not ok:
                return False, msg
    statut, rep = _requete("POST", f"{_v1(base_url)}/models/load",
                           {"model": cle, "context_length": contexte},
                           timeout, transport, coupure)
    if statut == 200 and rep.get("instance_id"):
        EPINGLES.add((base_url, rep["instance_id"]))
        return True, ""
    return False, _message(rep)
