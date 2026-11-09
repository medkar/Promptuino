"""Charger un modele libere d'abord les AUTRES, sur les deux moteurs locaux.

Decision de l'auteur du 2026-11-06. Constat du jour : deux modeles etaient
charges dans LM Studio en meme temps (l'un par `lms` le matin, l'autre par
« Charger pour Promptuino »), et occupaient la memoire ensemble. Au
chargement d'un modele depuis Promptuino, tous les AUTRES sont donc
decharges -- y compris ceux de l'AUTRE moteur : passer de LM Studio a Ollama
libere le modele de LM Studio, et inversement. « Decharger » reste
disponible a la main.

⚠️ C'est l'inverse de la regle posee le matin meme (« les autres modeles ne
sont jamais touches »), qui protegeait quelqu'un qui se servirait de
LM Studio pour autre chose en meme temps. L'auteur a tranche pour le public
de Promptuino, qui n'utilise que lui.

⚠️ Ne vaut que pour un chargement DEMANDE (les boutons). Ollama charge aussi
un modele seul a la premiere generation ; il libere alors lui-meme les moins
recents quand la memoire manque.

Module pur : ni Qt. Jamais d'exception : un serveur muet ne libere rien.
"""
from __future__ import annotations

from . import lmstudio_models as lm
from . import ollama_models as om


def _ollama_libere(garder: "str | None") -> list:
    liberes = []
    try:
        charges = om.modeles_charges()
    except Exception:
        return liberes
    garder = om._avec_etiquette(garder) if garder else None
    for nom in charges:
        if nom == garder:
            continue
        try:
            ok, _msg = om.decharger(nom)
        except Exception:
            ok = False
        if ok:
            liberes.append((nom, "Ollama"))
    return liberes


def _lmstudio_libere(base_url: str, garder: "str | None") -> list:
    liberes = []
    try:
        fiches = lm.modeles_installes(base_url)
    except Exception:
        return liberes
    for f in fiches:
        if f["cle"] == garder:
            continue        # ses instances, `lm.charger` les gere lui-meme
        for instance, _ctx in f["instances"]:
            try:
                ok, _msg = lm.decharger(base_url, instance)
            except Exception:
                ok = False
            if ok:
                liberes.append((instance, "LM Studio"))
    return liberes


def liberer_autres(moteur: str, modele: str, lmstudio_url: str) -> list:
    """Decharge tout modele charge SAUF `modele` sur `moteur`.

    Rend `[(modele, "Ollama" | "LM Studio"), ...]` : ce qui a VRAIMENT ete
    libere -- un refus n'est pas annonce comme une liberation.
    """
    return (_ollama_libere(modele if moteur == "ollama" else None)
            + _lmstudio_libere(lmstudio_url, modele if moteur == "lmstudio" else None))


def decharger_les_notres(*, timeout: int = 5) -> list:
    """A la FERMETURE : decharge ce que Promptuino a lui-meme charge pendant
    la session (« Charger »), sur les deux moteurs, et rien d'autre (decision
    de l'auteur, 2026-11-07). Rend ce qui a ete libere. Delai court : on est
    en train de quitter, un serveur muet ne doit pas retenir la fenetre."""
    liberes = []
    for nom in sorted(om.EPINGLES):
        try:
            ok, _ = om.decharger(nom, timeout=timeout)
        except Exception:
            ok = False
        if ok:
            liberes.append((nom, "Ollama"))
    for url, instance in sorted(lm.EPINGLES):
        try:
            ok, _ = lm.decharger(url, instance, timeout=timeout)
        except Exception:
            ok = False
        if ok:
            liberes.append((instance, "LM Studio"))
    return liberes


def phrase(liberes: list, gabarit: str) -> str:
    """« gemma-4-e4b (LM Studio), llama3.1:8b (Ollama) » dans `gabarit`, ou
    "" s'il n'y a rien a dire."""
    if not liberes:
        return ""
    return gabarit.format(liste=", ".join(f"{m} ({moteur})" for m, moteur in liberes))
