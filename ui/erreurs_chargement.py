"""Un refus de chargement se dit SIMPLEMENT, dans la langue de l'app.

Demande de l'auteur du 2026-11-06 : le texte brut de LM Studio (« Failed to
load LLM '…': Error: Model loading was stopped due to insufficient system
resources. Under the current settings, this model requires approximately
29.11 GB of memory, and continuing… ») etait affiche tel quel -- trop long,
trop complexe, en anglais. Plus aucun texte brut :
- le manque de memoire a SON message, avec le chiffre (il dit de combien on
  est loin) ;
- tout autre echec, une phrase simple.

Module pur : ni Qt, ni reseau.
"""
from __future__ import annotations

import re

# LM Studio : « insufficient system resources … requires approximately 29.11 GB » ;
# Ollama : « model requires more system memory (9.1 GiB) than is available ».
_MEMOIRE = re.compile(r"insufficient system resources|requires more system memory"
                      r"|out of memory|not enough memory", re.IGNORECASE)
_CHIFFRE = re.compile(r"requires (?:approximately |more system memory \()"
                      r"([\d.]+)\s*Gi?B", re.IGNORECASE)


_INTROUVABLE = re.compile(r"not found|does not exist|unknown model|no such model",
                          re.IGNORECASE)
_RESEAU = re.compile(r"urlerror|timed? ?out|connection|network|getaddrinfo|"
                     r"name or service|ssl|tls|unreachable", re.IGNORECASE)


def telechargement(brut: str, s) -> str:
    """La phrase a montrer pour un telechargement echoue : deux cas qui disent
    QUOI FAIRE (nom introuvable -- souvent une faute de frappe dans « Un autre
    modele » ; reseau), une phrase simple pour le reste. Jamais le texte brut."""
    brut = brut or ""
    if _INTROUVABLE.search(brut):
        return s.dl_not_found
    if _RESEAU.search(brut):
        return s.dl_network
    return s.md_failed


def message(moteur: str, brut: str, s, *, decharge: bool = False) -> str:
    """La phrase a montrer pour un echec de chargement (ou de dechargement)."""
    brut = brut or ""
    if not decharge and _MEMOIRE.search(brut):
        m = _CHIFFRE.search(brut)
        if m:
            try:
                return s.load_no_memory.format(go=round(float(m.group(1))))
            except ValueError:
                pass
        return s.load_no_memory_short
    if moteur == "ollama":
        return s.om_unload_failed if decharge else s.om_load_failed
    return s.lms_unload_failed if decharge else s.lms_load_failed
