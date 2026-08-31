"""Une fonctionnalité qui bloque la boucle dégrade toutes les autres
(TODO #89, 2026-08-31).

Les contributions de toutes les fonctionnalités atterrissent dans LE MÊME
`loop()`. Un `delay(1000)` n'y met donc pas « sa » fonctionnalité en pause :
il met **tout le sketch** en pause. Un bouton lu une fois par tour ne répond
plus qu'une fois toutes les N millisecondes — un appui bref ne fait plus
rien du tout.

**Mesuré** (2026-08-31, `gemma4:e2b`, 8 demandes typiques de débutant) :
**6 fonctionnalités sur 8 bloquent**, médiane **2 000 ms**, et **3 sur 8**
dépassent 200 ms. Ce n'est pas un cas limite — et les trois plus lourdes
(clignotement, affichage d'un capteur, affichage LCD) sont précisément les
compagnons les plus naturels d'un bouton.

⚠️ **Ni un défaut du modèle, ni un défaut d'assemblage** : chaque bloc pris
isolément est du code Arduino idiomatique, et l'assemblage est exact. C'est
la COMPOSITION qui casse, en silence — ça compile, le schéma est juste.

Module PUR — aucun Qt, aucune lecture disque.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .feature_model import Feature

# Au-delà de ce blocage, un appui de bouton se perd. Ce n'est PAS un seuil
# calibré sur un échantillon (le projet a déjà payé cette erreur avec le
# filet auto d'ambiguïté) : c'est un fait PHYSIQUE — un appui volontaire
# dure de 100 à 300 ms, donc une boucle plus lente que ~200 ms en rate.
# La mesure du 2026-08-31 le conforte sans le fabriquer : les blocages
# observés se répartissent en 30 / 50 / 100 ms d'un côté et 2 000 ms de
# l'autre — le seuil tombe dans un vrai trou, il n'en découpe pas un.
BLOCKING_THRESHOLD_MS = 200

_DELAY_RE = re.compile(r"\bdelay\s*\(\s*(\d+)\s*\)")
_DELAY_US_RE = re.compile(r"\bdelayMicroseconds\s*\(\s*(\d+)\s*\)")
# Lire une entrée = être DÉGRADÉ par le blocage d'un voisin. Volontairement
# limité aux deux primitives : elles sont sans ambiguïté. Une bibliothèque
# de bouton (`bouton.tick()`) souffre autant, mais la reconnaître demanderait
# de deviner — et un avertissement manqué vaut mieux qu'un faux.
_INPUT_RE = re.compile(r"\b(?:digitalRead|analogRead)\s*\(")


def blocking_ms(feature: Feature) -> int:
    """Millisecondes pendant lesquelles cette fonctionnalité fige le `loop()`.

    ⚠️ **Sous-estime volontairement** : un `delay()` dans une boucle `for`
    s'exécute N fois et n'est compté qu'une. Sous-estimer, c'est avertir
    MOINS souvent — la direction sûre : une alerte manquée est un statu quo,
    une fausse alerte est une friction à chaque génération.
    """
    corps = "\n".join(feature.loop_lines)
    ms = sum(int(m.group(1)) for m in _DELAY_RE.finditer(corps))
    ms += sum(int(m.group(1)) // 1000 for m in _DELAY_US_RE.finditer(corps))
    return ms


def reads_an_input(feature: Feature) -> bool:
    """La fonctionnalité lit-elle une entrée à chaque tour ? (= victime)"""
    return bool(_INPUT_RE.search("\n".join(feature.loop_lines)))


@dataclass(frozen=True)
class BlockingConflict:
    """La fonctionnalité `blocker_id` fige la boucle `blocker_ms` ms, et
    `victim_ids` lisent une entrée — elles ne répondront plus qu'une fois
    par tour."""
    blocker_id: str
    blocker_ms: int
    victim_ids: tuple[str, ...]


def find_conflict(features: list[Feature]) -> BlockingConflict | None:
    """Le conflit le plus lourd, ou None.

    Trois conditions, toutes nécessaires et toutes déterministes : au moins
    deux fonctionnalités, l'une bloque au-delà du seuil, une AUTRE lit une
    entrée. Une fonctionnalité qui se bloque elle-même sans voisin réactif
    n'a rien de fautif — c'est un clignotement, et il marche.
    """
    if len(features) < 2:
        return None
    victimes = [f.id for f in features if reads_an_input(f)]
    if not victimes:
        return None
    pire = None
    for f in features:
        ms = blocking_ms(f)
        if ms < BLOCKING_THRESHOLD_MS:
            continue
        autres = tuple(v for v in victimes if v != f.id)
        if not autres:
            continue      # elle est sa propre victime : rien à dénoncer
        if pire is None or ms > pire.blocker_ms:
            pire = BlockingConflict(f.id, ms, autres)
    return pire


def non_blocking_directive(lang: str = "fr") -> str:
    """Le delta de prompt envoyé au modèle quand l'utilisateur accepte la
    conversion. En ANGLAIS comme toutes les consignes machine du projet
    (`lang` n'est là que pour la symétrie d'API avec les autres builders).

    Dit le POURQUOI — les autres fonctionnalités partagent la boucle — parce
    que sans lui le modèle remplace `delay` par une attente active, ce qui
    bloque tout autant."""
    del lang
    return (
        "Rewrite this feature so it NEVER blocks the loop: replace every "
        "delay() with a non-blocking millis() timer (store the last event "
        "time in a global unsigned long and compare it to millis() on each "
        "loop pass). Keep the exact same behavior and timings. Do NOT use "
        "busy-wait loops (while (millis() - t < N) {}) — they block just as "
        "much. Other features share the same loop() and must keep running."
    )
