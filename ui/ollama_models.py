"""Telecharger un modele Ollama depuis l'app — logique pure, sans Qt.

⛔ **Pourquoi ce module existe.** Recuperer un modele demandait un TERMINAL
(`ollama pull …`), ce qui exclut le public vise par le projet. Ollama expose
pourtant `POST /api/pull`, qui fait exactement ce que fait la commande : c'est
le meme geste, envoye par un programme au lieu d'un humain.

MESURES DU 2026-08-28, faites avant d'ecrire une ligne d'interface :

- **Annuler = fermer le flux, et ca marche vraiment.** Zero octet
  supplementaire pendant les 10 s qui suivent la fermeture.
- ⛔ **Mais annuler ne LIBERE PAS d'espace.** Ollama PREALLOUE le fichier a sa
  taille finale : apres 36,8 Mo reellement transferes sur 379,4, le disque
  avait deja grossi de 379,4 Mo. Un modele de 20 Go annule a 5 % laisse 20 Go
  reserves. **Ne jamais promettre le contraire a l'utilisateur.**
- ✅ **Un second essai REPREND** ou il s'etait arrete (releve : reparti a
  63,5 Mo au lieu de 0). Les blocs partiels ne sont donc pas perdus.
- `DELETE /api/delete` nettoie tout, a l'octet pres.

⛔ **La taille d'un modele NON telecharge est INCONNUE de l'app.** `/api/show`
repond 404 tant que le modele n'est pas local, et il n'existe aucune API de
catalogue (`/api/search`, `/api/library`… tous 404, verifie). Les tailles de
`SUGGERES` sont donc **recopiees a la main depuis ollama.com/library** : elles
sont INDICATIVES, peuvent deriver, et doivent etre affichees avec un `~`. Des
qu'un modele est local, `/api/tags` donne sa taille EXACTE : c'est elle qui
doit primer.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from .subprocess_flags import NO_CONSOLE

BASE_URL = "http://127.0.0.1:11434"
PAGE_LIBRARY = "https://ollama.com/library"


def dossier_blobs():
    """Ou Ollama range ses fichiers (complets et partiels).

    ⚠️ Respecte `OLLAMA_MODELS` si NOTRE processus le voit ; si seul le
    SERVEUR a cette variable, on regarde au mauvais endroit et on rendra
    honnetement << 0 fichier >> plutot que d'echouer.
    """
    from pathlib import Path
    base = os.environ.get("OLLAMA_MODELS")
    racine = Path(base) if base else Path.home() / ".ollama" / "models"
    return racine / "blobs"


# Marge gardee sous le plafond : un disque SYSTEME rempli a ras bord rend
# Windows instable -- on refuse avant d'en arriver la, pas apres.
MARGE_DISQUE = 2 * 1024**3


def espace_disque_libre() -> "int | None":
    """Octets libres sur le disque qui recoit les modeles, None si inconnu.

    Mesure sur le dossier des blobs (remonte au premier parent existant si
    Ollama n'a encore rien cree). Contrairement a la VRAM, cette mesure est
    fiable partout -- `shutil.disk_usage` ne ment pas au-dela de 4 Go.
    """
    import shutil as _shutil
    d = dossier_blobs()
    while not d.exists():
        if d.parent == d:
            return None
        d = d.parent
    try:
        return _shutil.disk_usage(d).free
    except Exception:
        return None


def espace_suffisant(taille_modele: int) -> "bool | None":
    """False si on SAIT que ca ne tient pas ; None si l'espace est inconnu.

    ⚠️ None n'est pas False (meme regle que `tient_en_vram`) : ne pas savoir
    n'autorise pas a bloquer. Dans ce cas on laisse partir, et l'erreur
    d'Ollama -- si erreur il y a -- remonte par le filet `md_failed`.

    ⚠️ La verification IMPORTE ici plus qu'ailleurs : Ollama PREALLOUE le
    fichier entier des le debut (mesure), donc un modele trop gros ne remplit
    pas le disque progressivement -- il le sature dans les premieres secondes.
    Le comportement d'Ollama disque REELLEMENT plein n'a pas ete mesure (on ne
    va pas saturer un disque pour voir) ; ce garde-fou existe pour ne jamais
    avoir a le decouvrir.
    """
    libre = espace_disque_libre()
    if libre is None:
        return None
    return taille_modele + MARGE_DISQUE <= libre


def espace_partiels() -> int:
    """Octets occupes par les telechargements interrompus (`*-partial*`)."""
    try:
        return sum(p.stat().st_size for p in dossier_blobs().iterdir()
                   if p.is_file() and "-partial" in p.name)
    except Exception:
        return 0


def supprimer_partiels() -> tuple:
    """Supprime les fichiers partiels. Rend `(supprimes, octets, verrouilles)`.

    MESURE 2026-08-28 avant d'oser ecrire ici : 22 fichiers partiels (5 072 Mo,
    dont un llama3.1:8b annule a 10 % qui en reservait ~4 700 a lui seul)
    supprimes 22/22 SERVEUR ALLUME, espace rendu a l'octet pres, et un pull
    ulterieur marche -- il repart simplement de zero, ce qui est le prix.

    ⚠️ Il n'existe AUCUNE API pour ca : `DELETE /api/delete` exige un modele
    complet (il passe par le manifeste). On touche donc au dossier d'Ollama --
    uniquement les fichiers `*-partial*`, jamais un blob acheve.

    ⚠️ `verrouilles` peut etre > 0 : juste apres une annulation, Windows garde
    brievement un verrou sur le fichier en cours (constate en mesurant -- une
    suppression immediate a laisse un fichier derriere elle). L'appelant doit
    le DIRE et laisser reessayer, pas boucler en silence.
    """
    supprimes, octets, verrouilles = 0, 0, 0
    try:
        cibles = [p for p in dossier_blobs().iterdir()
                  if p.is_file() and "-partial" in p.name]
    except Exception:
        return 0, 0, 0
    for p in cibles:
        try:
            n = p.stat().st_size
            p.unlink()
            supprimes += 1
            octets += n
        except Exception:
            verrouilles += 1
    return supprimes, octets, verrouilles

# ─── Modeles suggeres ────────────────────────────────────────────────────
# `gemma4:e2b` EN TETE : c'est le modele par defaut de l'app (celui que le
# message << Modele non telecharge -- ollama pull gemma4:e2b >> reclame, et le
# seul autour duquel les reglages ont ete calibres). Il manquait a sa propre
# liste de suggestions jusqu'au 2026-08-28 -- un debutant se voyait proposer
# quatre modeles SAUF celui que l'app attend.
#
# ⚠️ Les autres sont proposes pour leur TAILLE, et rien d'autre : Promptuino
# n'a PAS evalue ce qu'ils produisent. Ne pas laisser croire a un classement.
#
# ⚠️ Tailles INDICATIVES pour les non-locaux (recopiees d'ollama.com ou
# relevees sur /api/tags) ; des qu'un modele est local, la taille exacte
# prime dans l'affichage.
SUGGERES: tuple = (
    ("gemma4:e2b",          7.2e9, "5,1 Md"),
    ("gemma3:1b",           0.8e9, "1 Md"),
    ("qwen2.5-coder:1.5b",  1.0e9, "1,5 Md"),
    ("gemma3:4b",           3.3e9, "4 Md"),
    ("qwen2.5-coder:7b",    4.7e9, "7 Md"),
    ("gemma4:12b",          7.6e9, "11,9 Md"),
)


def vram_totale() -> "int | None":
    """VRAM de la carte, en octets, ou None si on ne sait pas.

    ⛔ **Ne PAS utiliser `Win32_VideoController.AdapterRAM`** : le champ est un
    entier 32 bits et plafonne a 4 Go. Mesure du 2026-08-28 sur une RTX 5060 Ti
    de 16 Go : Windows annonce **4,00 Go**. Il repond, il a l'air credible, et
    il ferait deconseiller un modele de 6 Go a quelqu'un qui a 16 Go.

    `nvidia-smi` donne la vraie valeur (16 311 Mio sur la meme carte) mais
    n'existe que chez NVIDIA. AMD et Intel n'ont pas d'equivalent ici : on rend
    None, et l'interface doit alors se taire plutot que d'inventer un verdict.
    """
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=8,
            creationflags=NO_CONSOLE
            if sys.platform == "win32" else 0)
        if r.returncode != 0:
            return None
        m = re.search(r"(\d+)\s*MiB", r.stdout)
        return int(m.group(1)) * 1024 * 1024 if m else None
    except Exception:
        return None


def go_carte(vram: int) -> str:
    """La memoire de la carte, comme Windows et le fabricant l'annoncent.

    ⛔ PAS en milliards d'octets : la RTX 5060 Ti « 16 Go » de l'auteur
    (16 311 Mio selon nvidia-smi) s'affichait « 17.1 Go », repete sur chaque
    ligne de la fenetre « Modeles… » -- lu comme la taille des modeles (QA du
    2026-11-06). Le Go d'une carte graphique est un Gio : arrondi a l'entier.
    """
    return f"{round(vram / 2**30)} Go"


def tient_en_vram(taille_modele: int, vram: "int | None") -> "bool | None":
    """True / False / None quand on ne sait pas.

    ⚠️ **None n'est pas False.** Ne pas savoir n'est pas savoir que ca ne passe
    pas : l'interface ne doit afficher aucune croix dans ce cas. Meme regle que
    la modale de choix de bibliotheque, qui ne revendique aucune compatibilite
    quand la carte est inconnue.

    La marge de 15 % couvre le contexte et les tampons, qui s'ajoutent au poids
    des poids.
    """
    if not vram:
        return None
    return taille_modele * 1.15 <= vram


def _params_fr(brut: str) -> str:
    """`"11.9B"` (API Ollama) -> `"11,9 Md"`, le format des suggeres."""
    if not brut or not brut.upper().endswith("B"):
        return ""
    return brut[:-1].replace(".", ",") + " Md"


def modeles_locaux() -> dict:
    """`{nom: (taille_exacte, params)}` — la seule taille dont on soit sur.

    Les parametres viennent de `details.parameter_size` : ils permettent
    d'afficher les modeles locaux au MEME format que les suggeres.
    """
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/tags", timeout=5) as r:
            d = json.load(r)
        return {m["name"]: (m.get("size", 0),
                            _params_fr(m.get("details", {})
                                       .get("parameter_size", "")))
                for m in d.get("models", [])}
    except Exception:
        return {}


def cumuler(avancement: dict, ligne: dict) -> tuple:
    """Additionne la progression PAR BLOB. Rend `(recu, total)` cumules.

    ⛔ **Le flux d'Ollama rapporte chaque COUCHE separement, pas le modele.**
    Constate le 2026-08-28 sur un llama3.1:8b : l'affichage disait
    << 0,1 / 0,6 Go >> pour un modele de 4,9 -- la ligne montrait UN blob, et
    le serveur en telecharge jusqu'a 4 en parallele
    (`OLLAMA_MAX_TRANSFER_STREAMS:4`), leurs lignes s'entremelant. Sur un
    petit modele le defaut etait invisible : un seul blob ≈ le modele entier.

    Le cumul est la seule totalisation possible : il n'existe aucune API qui
    donne la taille du modele AVANT le flux. Le `total` cumule GRANDIT donc a
    mesure que les blobs s'annoncent -- le pourcentage peut reculer quand un
    nouveau blob apparait, c'est le prix de l'honnetete (l'appelant re-verifie
    d'ailleurs l'espace disque a chaque croissance).
    """
    dig = ligne.get("digest")
    if dig and ligne.get("total"):
        avancement[dig] = (ligne.get("completed", 0), ligne["total"])
    recu = sum(c for c, _ in avancement.values())
    total = sum(t for _, t in avancement.values())
    return recu, total


def supprimer_modele(nom: str) -> "str | None":
    """Supprime un modele local. None si ok, un message d'erreur sinon.

    `DELETE /api/delete` passe par le manifeste et rend l'espace a l'octet
    pres (mesure 2026-08-28 : 50 801,1 -> 50 421,7 Mo apres suppression du
    modele de test). Rapide meme sur un gros modele : c'est un unlink cote
    serveur, pas une re-ecriture.
    """
    corps = json.dumps({"model": nom}).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/delete", data=corps,
                                 headers={"Content-Type": "application/json"},
                                 method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=30):
            return None
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode()).get("error") or f"HTTP {e.code}"
        except Exception:
            return f"HTTP {e.code}"
    except Exception as e:
        return type(e).__name__


def telecharger(nom: str, progression, arret) -> "str | None":
    """Telecharge `nom`. Rend None si tout va bien, un message d'erreur sinon.

    `progression(recu, total, etape)` recoit les valeurs CUMULEES sur tous les
    blobs vus (cf. `cumuler`). `arret()` est consultee entre deux lignes : si
    elle rend True, on FERME la connexion — ce qui arrete reellement le
    serveur (mesure).

    ⚠️ A executer dans un THREAD : la fonction bloque tant que le
    telechargement dure, soit plusieurs minutes.
    """
    corps = json.dumps({"model": nom, "stream": True}).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/pull", data=corps,
                                 headers={"Content-Type": "application/json"})
    avancement: dict = {}
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("error", "")
        except Exception:
            msg = ""
        return msg or f"HTTP {e.code}"
    except Exception as e:
        return f"{type(e).__name__}"
    try:
        for ligne in resp:
            if arret():
                return None            # annulation : la fermeture suffit
            if not ligne.strip():
                continue
            try:
                d = json.loads(ligne)
            except Exception:
                continue
            if d.get("error"):
                return d["error"]
            recu, total = cumuler(avancement, d)
            progression(recu, total, d.get("status", ""))
    except Exception as e:
        return f"{type(e).__name__}"
    finally:
        resp.close()
    return None


# ─── Charger / decharger en memoire (2026-11-06) ─────────────────────────
# Voulu par l'auteur : le meme geste que pour LM Studio, sur les deux moteurs.
# MESURES DU 2026-11-06 sur Ollama 0.40.5 (llama3.1:8b), avant d'ecrire une
# ligne d'interface :
# - charger = `POST /api/generate` SANS prompt -> `done_reason: "load"`
#   (~30 s a froid pour 4,9 Go).
# - `keep_alive: -1` -> `expires_at` en 2319 ; une demande ORDINAIRE ensuite
#   (sans keep_alive) ne le raccourcit PAS : le modele reste jusqu'a
#   « Decharger ».
# - ⛔ une demande avec un AUTRE `num_ctx` RECHARGE le modele (7,7 s), qui
#   repart alors sur les 5 min par defaut. L'appelant passe donc le contexte
#   de la GENERATION (`OllamaBackend.generation_context`), source unique.
# - decharger = `keep_alive: 0` -> `done_reason: "unload"`, `/api/ps` vide
#   aussitot.
# - `/api/ps` donne `context_length` ; un vieil Ollama ne le donne pas : on
#   se tait plutot que d'inventer un chiffre.

from .lmstudio_models import _requete    # meme contrat : jamais d'exception

_TIMEOUT_CHARGEMENT = 300     # un gros modele a froid peut prendre longtemps


def _message(rep: dict) -> str:
    err = rep.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or "")
    return str(err) if err else ""


def _avec_etiquette(nom: str) -> str:
    """`mistral` et `mistral:latest` sont le MEME modele ; `/api/ps` rend
    toujours la forme etiquetee."""
    nom = (nom or "").strip()
    return nom if ":" in nom else f"{nom}:latest"


def modeles_charges(*, transport=None) -> dict:
    """`{nom: contexte ou None}` des modeles en memoire ; `{}` si muet."""
    statut, rep = _requete("GET", f"{BASE_URL}/api/ps", None, 5, transport)
    if statut != 200:
        return {}
    charges = {}
    for m in rep.get("models") or []:
        if not isinstance(m, dict) or not (m.get("name") or m.get("model")):
            continue
        ctx = m.get("context_length")
        charges[_avec_etiquette(m.get("name") or m.get("model"))] = (
            ctx if isinstance(ctx, int) and not isinstance(ctx, bool) and ctx > 0
            else None)
    return charges


# Sous cette part en VRAM, le modele a DEBORDE de la carte : il tourne en
# partie sur le processeur, donc lentement. Mesure du 2026-11-06 : 100 % quand
# il tient (llama3.1:8b @16k), 64 % quand il deborde (@128k).
SEUIL_PART_VRAM = 0.95


def en_memoire(nom: str, *, transport=None) -> "dict | None":
    """`{"charge", "ctx", "deborde"}` pour `nom` ; None si Ollama se tait --
    muet n'est PAS « pas charge », l'ecran ne doit rien affirmer.
    `deborde` : la part du modele en VRAM (`size_vram / size`) est sous
    `SEUIL_PART_VRAM` ; None quand Ollama ne donne pas les tailles."""
    statut, rep = _requete("GET", f"{BASE_URL}/api/ps", None, 5, transport)
    if statut != 200:
        return None
    cle = _avec_etiquette(nom)
    for m in rep.get("models") or []:
        if not isinstance(m, dict):
            continue
        if _avec_etiquette(m.get("name") or m.get("model") or "") != cle:
            continue
        ctx = m.get("context_length")
        ctx = ctx if isinstance(ctx, int) and not isinstance(ctx, bool) and ctx > 0 else None
        taille, vram = m.get("size"), m.get("size_vram")
        deborde = None
        if isinstance(taille, int) and isinstance(vram, int) and taille > 0:
            deborde = vram < taille * SEUIL_PART_VRAM
        return {"charge": True, "ctx": ctx, "deborde": deborde}
    return {"charge": False, "ctx": None, "deborde": None}


def contexte_max(nom: str, *, transport=None) -> "int | None":
    """Le contexte maximum du modele (`model_info.<arch>.context_length` de
    `/api/show`), ou None s'il ne le dit pas ou si Ollama se tait. Mesure du
    2026-11-06 : les cinq modeles installes le donnaient (131 072 a 262 144)."""
    statut, rep = _requete("POST", f"{BASE_URL}/api/show", {"model": nom},
                           5, transport)
    if statut != 200:
        return None
    info = rep.get("model_info")
    if not isinstance(info, dict):
        return None
    for cle, valeur in info.items():
        if (str(cle).endswith(".context_length") and isinstance(valeur, int)
                and not isinstance(valeur, bool) and valeur > 0):
            return valeur
    return None


def reflexion_modele(nom: str, *, transport=None):
    """Ce que le modele permet en matiere de reflexion (`ui.reflexion`), lu
    dans `/api/show` ; None si Ollama se tait (TODO #123)."""
    from . import reflexion
    statut, rep = _requete("POST", f"{BASE_URL}/api/show", {"model": nom},
                           5, transport)
    return reflexion.depuis_ollama(rep) if statut == 200 else None


# Ce que PROMPTUINO a charge (« Charger ») pendant la session, pour le
# decharger a la fermeture (decision de l'auteur, 2026-11-07) : `keep_alive:
# -1` epingle sans limite, donc la carte restait occupee apres la sortie. Un
# modele charge par un autre moyen n'y entre jamais.
EPINGLES: set = set()


def charger(nom: str, num_ctx: int, *, transport=None,
            timeout: int = _TIMEOUT_CHARGEMENT,
            coupure=None) -> "tuple[bool, str]":
    """Charge `nom` a `num_ctx` tokens, jusqu'a « Decharger ». `coupure` :
    pour l'annuler en cours (cf. `lmstudio_models._requete`)."""
    statut, rep = _requete(
        "POST", f"{BASE_URL}/api/generate",
        {"model": nom, "keep_alive": -1, "stream": False,
         "options": {"num_ctx": int(num_ctx)}},
        timeout, transport, coupure)
    if statut == 200 and not rep.get("error"):
        EPINGLES.add(_avec_etiquette(nom))
        return True, ""
    return False, _message(rep)


def decharger(nom: str, *, transport=None,
              timeout: int = 30) -> "tuple[bool, str]":
    statut, rep = _requete(
        "POST", f"{BASE_URL}/api/generate",
        {"model": nom, "keep_alive": 0, "stream": False}, timeout, transport)
    if statut == 200 and not rep.get("error"):
        EPINGLES.discard(_avec_etiquette(nom))
        return True, ""
    return False, _message(rep)
