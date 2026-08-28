"""Quelles puces le projet utilise DEJA, d'apres ses `#include`.

POURQUOI (TODO #64). Sur un prompt de SUITE — « arrondis la temperature a un
chiffre apres la virgule » — le retrieval ne voit que le prompt NU : ni le
code, ni la puce qui y est declaree. Mesure du 2026-08-26 sur les 40 cas de la
batterie C (`scripts/bench_rag_followup.py`) : SEPT prompts de ce genre
injectaient la bibliotheque d'une AUTRE puce de la meme famille — `adt7410`,
`mcp9808`, `max6675` sur un projet DS18B20 — et le modele suit docilement.

CE QUE CE MODULE REND, ET SURTOUT CE QU'IL NE REND PAS. Quatre formes ont ete
mesurees sur la meme batterie, et trois sont des pieges :

    forme jointe au signal de recherche              fautes (sur 40)
    -------------------------------------------      ----------------
    rien (l'existant)                                        7
    les `#include` BRUTS  (la forme du ticket)               9  ⛔
    le NOM de la bibliotheque (« Adafruit BME280 Library »)  9  ⛔
    l'ID du corpus        (« dallas-temperature »)           3
    le seul NUMERO DE PIECE (« ds18b20 »)                    0  ✅

⚠️ La lecon est ETROITE, ne pas l'elargir : ce qui aide est le jeton que le
corpus reconnait, seul. Chaque mot de prose ajoute au signal deplace la moyenne
de l'embedding (meme mecanique qu'au TODO #65) et rapproche les voisins — c'est
litteralement pourquoi l'id du corpus fait moins bien que le numero de piece :
« dallas-temperature » traine le mot « temperature », qui ravive exactement la
confusion qu'on cherche a eteindre.

⚠️ Et l'indice ne pese que sur le CLASSEMENT : voir `rag._build_lib_context`,
parametre `ranking_hint`. Le coller au prompt basculerait 21 des 40 cas d'un
en-tete hedge a un en-tete imperatif, ce que personne n'a demande.

Module PUR : aucun Qt, aucune lecture disque directe. Ses imports sont locaux
aux fonctions, comme dans `lib_by_header` et pour la meme raison — `markers`
importe `rag`, qui n'a pas a dependre d'eux au chargement.
"""
from __future__ import annotations

import re
from typing import Iterable

# Meme motif que `arduino_cli._INCLUDE_RE`, recopie plutot qu'importe : ce
# module doit rester pur et `arduino_cli` importe PyQt6 au niveau module.
_INCLUDE_RE = re.compile(r'^\s*#include\s*<([^>]+)>', re.MULTILINE)


def headers_in_code(code: str) -> list[str]:
    """Les `#include <...>` du sketch, dans l'ordre, sans doublon.

    Les includes ENTRE GUILLEMETS sont ignores volontairement : `#include
    "pitches.h"` designe un fichier du projet, pas une bibliotheque.
    """
    out: list[str] = []
    for header in _INCLUDE_RE.findall(code or ""):
        header = header.strip()
        if header and header not in out:
            out.append(header)
    return out


def _own_headers() -> set[str]:
    """Les en-tetes dont une entree corpus est PROPRIETAIRE (son 1er en-tete).

    Meme regle, et pour la meme raison, que `lib_by_header._from_corpus` : une
    entree liste son en-tete d'abord, puis ses COMPAGNONS, qui appartiennent a
    une autre bibliotheque. Verifie sur le corpus courant, 4 en-tetes sont
    listes par plusieurs entrees, et deux ne sont proprietaires de RIEN :
    `Adafruit_Sensor.h` (base commune a toutes les libs Adafruit) et
    `Adafruit_GFX.h` (base commune a tous les ecrans).

    ⛔ SANS CE FILTRE, la table d'alias sur-affirme. Mesure du 2026-08-26 :
    `Adafruit_Sensor.h` sortait en `bme280` et `SPI.h` en `microsd_card_module`
    -- un projet TSL2561 aurait recu l'indice << bme280 >>, soit exactement la
    fausse puce que #64 existe pour supprimer. La table d'alias n'est pas en
    cause : elle repond << quel composant ce fichier evoque-t-il >>, ce qui est
    la bonne question pour dessiner une boite de cablage et la mauvaise pour
    affirmer ce que le projet contient.

    ⚠️ Ce defaut n'a PAS ete trouve par la batterie C -- ses trois projets s'en
    sortaient par hasard, le compagnon aliasant vers la meme puce que
    l'en-tete proprietaire. Il a ete trouve par un test unitaire.
    """
    from .lib_by_header import _norm      # LA normalisation d'en-tete du depot ;
    from .rag import all_corpus_entries   # la recopier, c'est la faire deriver
    out: set[str] = set()
    for entry in all_corpus_entries():
        headers = entry.get("headers") or []
        if headers:
            out.add(_norm(headers[0]))
    return out


def chip_tokens_for_headers(headers: Iterable[str]) -> list[str]:
    """Les numeros de piece que le corpus reconnait, dans l'ordre des en-tetes.

    Trois etapes, et chacune reutilise une regle qui existe deja :

      1. on ne retient que les en-tetes dont une entree corpus est
         PROPRIETAIRE (`_own_headers`) — un compagnon ne prouve rien.
      2. en-tete -> composant, par `markers._clean_lib_name`. C'est la table
         d'alias DERIVEE du registre (TODO #60) : elle sait que `OneWire.h` et
         `DallasTemperature.h` designent tous deux le `ds18b20`, ce qu'aucune
         heuristique sur le nom de fichier ne donne. En ecrire une seconde ici
         serait recreer a la main ce que #60 a supprime.
      3. on ne GARDE que les slugs qui sont un jeton de signature du corpus
         (`rag.corpus_signature_tokens`). C'est le critere exact du boost
         lexical : un jeton qui n'y est pas ne peut RIEN classer, il ne ferait
         que deplacer la moyenne de l'embedding. C'est ce filtre qui separe la
         forme a zero faute de la forme a quatre — sans lui, `Wire.h` entre
         dans le signal et traine du bruit.

    Jamais d'exception : un magasin casse ne doit pas empecher une generation,
    il doit rendre le comportement d'avant (aucun indice).
    """
    try:
        from .lib_by_header import _norm
        from .rag import corpus_signature_tokens
        from .wiring.markers import _clean_lib_name
        known = corpus_signature_tokens()
        own = _own_headers()
    except Exception:
        return []
    if not known or not own:
        return []
    out: list[str] = []
    for header in headers or ():
        try:
            if _norm(header) not in own:
                continue
            slug = _clean_lib_name(header, default="")
        except Exception:
            continue
        if slug and slug in known and slug not in out:
            out.append(slug)
    return out


def chip_hint(code: str) -> str:
    """L'indice de classement pour le code d'un projet : « bme280 ds18b20 ».

    Chaine VIDE quand le projet n'a pas de code, n'inclut aucune bibliotheque,
    ou n'en inclut aucune que le corpus reconnaisse — et une chaine vide veut
    dire « ne change rien », cf. `rag.build_lib_context`.
    """
    return " ".join(chip_tokens_for_headers(headers_in_code(code)))
