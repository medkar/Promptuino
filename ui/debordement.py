"""Le modele LM Studio a-t-il deborde de la carte graphique ? (2026-11-06)

Demande de l'auteur : une fois le modele charge, LIRE s'il a deborde, et le
dire en orange (« branche mais lent »). Mesures du jour :
docs/superpowers/measures/2026-11-06-contexte-vram.md.

⛔ **Deux debordements differents, deux signaux** -- aucun ne voit les deux :
- le modele DEPASSE la carte : le pilote met le surplus en RAM, ce que
  Windows compte comme memoire graphique PARTAGEE du processus `llama-server`
  (0,13 a 0,17 Gio quand il tient, 6,41 Gio quand il deborde) ;
- LM Studio a mis des COUCHES sur le processeur (gemma-4-26b : 23 sur 30) :
  la memoire partagee reste basse (0,17 Gio). Seul son journal le dit.
⛔ Comparer la VRAM reelle a une prevision ne marche PAS : gemma-4-e4b
(rapide, une partie en RAM par conception) aurait ete signale, gemma-4-26b
(lent) non.

Ollama n'est pas ici : il donne directement la part en VRAM
(`ollama_models.en_memoire`).

Windows seulement (la classe WMI et le chemin du journal) : ailleurs, tout
rend None et l'ecran se tait. Jamais d'exception.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

from .subprocess_flags import NO_CONSOLE

# Entre 0,17 Gio (le plus haut mesure quand ca tient) et 6,41 Gio (deborde).
SEUIL_PARTAGE = int(0.5 * 2 ** 30)

# ⚠️ La CLASSE WMI, pas `Get-Counter` : le nom du compteur est TRADUIT selon la
# langue de Windows (« \Memory\... » echoue en francais -- verifie).
_WMI = ("$ids = (Get-Process llama-server -ErrorAction SilentlyContinue).Id;"
        "if ($ids) { Get-CimInstance "
        "Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory |"
        " Where-Object { $ids -contains [int]($_.Name -replace '^pid_(\\d+)_.*','$1') } |"
        " ForEach-Object { '{0};{1}' -f $_.DedicatedUsage, $_.SharedUsage } }")

_BLOC = re.compile(r"raw num offload layers '([^']+)' and context length '(\d+)'")


def _powershell(commande: str) -> "str | None":
    if sys.platform != "win32":
        return None
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", commande],
                           capture_output=True, text=True, timeout=10,
                           creationflags=NO_CONSOLE)
        return r.stdout
    except Exception:
        return None


def memoire_partagee(*, executer=_powershell) -> "int | None":
    """Octets de memoire graphique PARTAGEE des processus `llama-server`, ou
    None (aucun processus, pas Windows, pas de reponse)."""
    sortie = executer(_WMI)
    if not sortie:
        return None
    total, vu = 0, False
    for ligne in sortie.split():
        if ";" in ligne:
            try:
                total += int(ligne.split(";")[1])
                vu = True
            except ValueError:
                continue
    return total if vu else None


def _journal_lms() -> "str | None":
    """La fin de `main.log` de LM Studio (Windows : %APPDATA%), ou None."""
    base = os.environ.get("APPDATA")
    if not base:
        return None
    chemin = os.path.join(base, "LM Studio", "logs", "main.log")
    try:
        with open(chemin, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 256 * 1024))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def couches_partielles(contexte: int, *, lire=_journal_lms) -> "bool | None":
    """Le DERNIER chargement journalise a-t-il mis des couches sur le
    processeur ? `max` -> non ; un nombre -> oui.

    ⚠️ Le journal ne nomme pas le modele : le dernier bloc n'est le notre que
    si sa taille de contexte CONCORDE (« Charger » decharge les autres
    modeles, donc le dernier chargement est le bon). Sinon : None, on se tait.
    ⚠️ Journal INTERNE : un autre format dans une future version rend None
    (silence), jamais une fausse alerte.
    """
    texte = lire()
    if not texte:
        return None
    blocs = _BLOC.findall(texte)
    if not blocs:
        return None
    couches, ctx = blocs[-1]
    if int(ctx) != int(contexte):
        return None
    return couches.strip().lower() != "max"


def lmstudio_deborde(contexte: int, *, partage=memoire_partagee,
                     couches=couches_partielles) -> "bool | None":
    """True si l'un des deux signaux le dit ; None si aucun n'a pu parler."""
    octets = partage()
    partiel = couches(contexte)
    if (octets is not None and octets > SEUIL_PARTAGE) or partiel is True:
        return True
    if octets is None and partiel is None:
        return None
    return False
