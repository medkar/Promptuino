"""Y a-t-il une version plus recente ? — logique pure, sans Qt.

TODO #77. Trois decisions prises le 2026-08-28, et le module les applique
litteralement :

1. **On PROPOSE, on n'installe jamais.** Une application scolaire qui se met a
   jour toute seule en pleine seance est une mauvaise surprise. Ce module ne
   telecharge rien : il rend un numero de version, l'appelant decide quoi en
   faire.
2. **Hors ligne = SILENCE.** Pas de message d'erreur, pas d'icone d'alerte.
   Un poste d'etablissement sans reseau ne doit pas etre harcele pour une
   fonctionnalite dont il n'a que faire. Toute panne rend `None`.
3. **Verification au demarrage ET a la demande** (bouton dans << A propos >>).

⚠️ **Un build de developpement ne se compare a rien.** `0.1.0+dev` est EN
AVANCE sur la derniere version publiee, pas en retard ; lui annoncer une mise
a jour serait absurde. `is_release_build()` coupe court.

⚠️ **Les brouillons de Release ne sont PAS vus, et c'est ce qu'on veut** :
l'API `/releases/latest` de GitHub ignore les brouillons et les
pre-publications. Les Releases de test du projet n'ont donc jamais declenche
de proposition, sans qu'il ait fallu les filtrer.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .version import APP_VERSION, is_release_build

DEPOT = "medkar/Promptuino"
_API = f"https://api.github.com/repos/{DEPOT}/releases/latest"
PAGE_RELEASES = f"https://github.com/{DEPOT}/releases/latest"

# Delai court : c'est un confort, pas une fonctionnalite. Mieux vaut ne rien
# dire que retarder le demarrage sur un reseau qui ne repond pas.
_TIMEOUT_S = 6


def parse_version(texte: str) -> tuple:
    """`"v0.1.2"` -> `(0, 1, 2)`. Ignore un suffixe (`-test8`, `+dev`).

    Rend `()` si rien de numerique ne s'en degage -- l'appelant traite ce cas
    comme << on ne sait pas >>, donc comme un silence.
    """
    if not texte:
        return ()
    m = re.match(r"v?(\d+(?:\.\d+)*)", texte.strip())
    if not m:
        return ()
    return tuple(int(x) for x in m.group(1).split("."))


def is_newer(distante: str, locale: str) -> bool:
    """True si `distante` est strictement plus recente que `locale`."""
    a, b = parse_version(distante), parse_version(locale)
    if not a or not b:
        return False
    # Comparaison a longueur egale : 0.2 doit battre 0.1.9.
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def fetch_latest(url: str = _API, timeout: int = _TIMEOUT_S) -> tuple:
    """`(tag, joignable)`.

    ⚠️ **Les deux cas ou il n'y a pas de tag ne sont PAS le meme.** Un serveur
    injoignable et un depot sans aucune Release publiee rendent tous deux
    << rien >>, mais on ne dit pas la meme chose a l'utilisateur : << impossible
    de verifier >> dans un cas, << vous avez la derniere version >> dans
    l'autre. Confondre les deux faisait afficher une erreur reseau alors que
    le reseau repondait parfaitement (constate le 2026-08-28, le depot public
    n'ayant alors que des brouillons).

    Un 404 signifie donc `(None, True)` : l'API a repondu, il n'y a rien.
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": f"Promptuino/{APP_VERSION}",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("tag_name") or None), True
    except urllib.error.HTTPError as e:
        # 404 = aucune Release publiee. Les autres codes (403 quota, 5xx)
        # sont des pannes : on ne peut pas conclure.
        return None, e.code == 404
    except Exception:
        return None, False


def fetch_latest_tag(url: str = _API, timeout: int = _TIMEOUT_S) -> "str | None":
    """Le tag de la derniere Release publiee, ou None (toutes causes)."""
    return fetch_latest(url, timeout)[0]


def check(url: str = _API, timeout: int = _TIMEOUT_S) -> "str | None":
    """Le tag d'une version plus recente, ou None s'il n'y a rien a dire.

    C'est la seule fonction que l'interface appelle. Elle ne leve jamais.
    """
    if not is_release_build():
        return None
    tag = fetch_latest_tag(url, timeout)
    if not tag:
        return None
    return tag if is_newer(tag, APP_VERSION) else None
