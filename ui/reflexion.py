"""La reflexion (« thinking ») des modeles : ce que le modele permet, ce que
l'interrupteur montre, ce qu'on envoie au moteur (TODO #123).

Module PUR : aucun Qt, aucun reseau. Les pages de l'onglet IA et les moteurs
lui passent ce que le serveur a dit du modele.

Decisions de l'auteur (2026-11-06) : pouvoir activer ou desactiver la
reflexion sur chaque moteur, DESACTIVEE par defaut ; un curseur a trois crans
pour ChatGPT. Mesures du meme jour :

- **Ollama** (`/api/show`) : `thinking: {values, default}` -- `[False, True]`
  pour gemma4, `[False]` pour qwen3-coder, rien pour llama3.1. Un serveur plus
  ancien ne donne que la capacite « thinking ». Une valeur peut aussi etre un
  NIVEAU nomme (`"low"`...) : le modele reflechit alors toujours.
- **LM Studio** (`GET /api/v1/models`) : `capabilities.reasoning.
  allowed_options`. Par son API compatible OpenAI -- celle de l'app --,
  `reasoning_effort: "none"` coupe la reflexion d'un modele qui l'accepte
  (Gemma : `off`/`on`). ⚠️ « low/high ignores », conclu le 2026-11-06, avait
  ete mesure sur Gemma, qui n'a PAS de niveaux : sur gpt-oss (`low`/`medium`/
  `high`), la meme API les RESPECTE -- 67 / 220-268 / 312-552 tokens de
  reflexion, chiffres identiques a l'API native (mesure 2026-11-07,
  TODO #125). gpt-oss ne se coupe pas : `none` y revient a `low`.

⛔ On n'envoie jamais ce qu'on n'a pas mesure : `think: true` a un modele qui
ne sait pas reflechir fait echouer Ollama, et un champ inconnu de LM Studio
n'a ete essaye que sur des modeles qui reflechissent.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capacite:
    peut_reflechir: bool        # le modele sait reflechir
    peut_couper: bool           # ... et on peut l'en empecher
    allumer: object = True      # ce qu'Ollama recoit pour reflechir
    niveaux: tuple = ()         # niveaux NOMMES (« low »...), dans l'ordre


# ── Ce que le modele permet ──────────────────────────────────────────────

def depuis_ollama(show) -> "Capacite | None":
    """D'apres la reponse de `/api/show`. None : Ollama n'a rien dit."""
    if not isinstance(show, dict) or not show:
        return None
    pensee = show.get("thinking")
    if isinstance(pensee, dict) and isinstance(pensee.get("values"), list):
        valeurs = pensee["values"]
        niveaux = [v for v in valeurs if isinstance(v, str)]
        if any(v is True for v in valeurs):
            allumer = True
        elif niveaux:
            defaut = pensee.get("default")
            allumer = defaut if defaut in niveaux else niveaux[0]
        else:
            return Capacite(False, True, None)
        return Capacite(True, any(v is False for v in valeurs), allumer,
                        ordonner_niveaux(niveaux))
    capacites = show.get("capabilities")
    if isinstance(capacites, list):
        return (Capacite(True, True, True) if "thinking" in capacites
                else Capacite(False, True, None))
    return None


def depuis_lmstudio(options) -> "Capacite | None":
    """D'apres `allowed_options` (un tuple, vide si le modele n'a pas de
    reflexion). None : le serveur ne l'a pas dit (LM Studio plus ancien)."""
    if options is None:
        return None
    permis = {str(o).lower() for o in options}
    if not permis - {"off"}:
        return Capacite(False, True, None)
    niveaux = ordonner_niveaux([o for o in permis if o not in ("off", "on")])
    return Capacite(True, "off" in permis, niveaux[0] if niveaux else "on",
                    niveaux)


# ── Ce que l'interrupteur montre ─────────────────────────────────────────

def interrupteur(cap: "Capacite | None", voulu: bool) -> "tuple[bool, bool]":
    """(actif, coche). Grise et decoche si le modele ne sait pas reflechir,
    grise et coche s'il reflechit toujours. Inconnu : on laisse regler."""
    if cap is None:
        return True, bool(voulu)
    if not cap.peut_reflechir:
        return False, False
    if not cap.peut_couper:
        return False, True
    return True, bool(voulu)


# ── Ce qu'on envoie ──────────────────────────────────────────────────────

def ordonner_niveaux(niveaux) -> tuple:
    """Les niveaux dans l'ordre d'effort croissant : les noms connus d'abord
    (low < medium < high), les autres ensuite, dans l'ordre du serveur."""
    connus = [n for n in _ORDRE if n in niveaux]
    return tuple(connus + [n for n in niveaux if n not in _ORDRE])


_ORDRE = ("minimal", "low", "medium", "high")


def ollama_think(cap: "Capacite | None", voulu: bool, niveau: str = ""):
    """La valeur du champ `think`. Inconnu ou incapable : `False`, la valeur
    que l'app envoyait depuis toujours. `niveau` : le niveau choisi (P3/P4,
    2026-11-07), envoye seulement s'il fait partie de ceux du modele."""
    if cap is None or not cap.peut_reflechir:
        return False
    allumer = niveau if niveau and niveau in cap.niveaux else cap.allumer
    if not cap.peut_couper:
        return allumer
    return allumer if voulu else False


def lmstudio_champs(cap: "Capacite | None", voulu: bool,
                    niveau: str = "") -> dict:
    """Les champs a ajouter a la requete compatible OpenAI de LM Studio.
    Un modele a niveaux (gpt-oss) recoit le niveau choisi, ou son defaut ;
    jamais un niveau qu'il n'annonce pas (LM Studio refuserait)."""
    if cap is None or not cap.peut_reflechir:
        return {}
    if cap.peut_couper and not voulu:
        return {"reasoning_effort": "none"}
    if cap.niveaux:
        return {"reasoning_effort": niveau if niveau in cap.niveaux
                else cap.allumer}
    return {}


# ── ChatGPT : trois crans ────────────────────────────────────────────────

# « Instant / Moyen / Eleve », comme la maquette officielle d'OpenAI (« Model
# speed »). `low`/`medium`/`high` : les trois niveaux que tous les modeles a
# raisonnement d'OpenAI acceptent (`minimal` et `none` dependent du modele).
NIVEAUX_CHATGPT = ("low", "medium", "high")
NIVEAU_CHATGPT_DEFAUT = "medium"


def niveau_chatgpt(valeur) -> str:
    return valeur if valeur in NIVEAUX_CHATGPT else NIVEAU_CHATGPT_DEFAUT
