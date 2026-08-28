"""La version de Promptuino — une seule source, et elle suit le BUILD.

⛔ **Avant le 2026-08-28, il y en avait deux et elles divergeaient deja** :
`ui/sidebar.py` portait `APP_VERSION = "v0.1.0"` en dur, tandis que
`build/installer.iss` recevait la sienne du tag git. L'installeur s'annoncait
donc `0.1.1` pendant que l'application affichait `v0.1.0`.

C'est sans gravite tant que personne ne s'en sert -- mais un verificateur de
mise a jour (TODO #77) compare << ma version >> a << la derniere publiee >>.
Avec une chaine que personne ne remonte, il est faux par construction : il
dirait toujours << a jour >>, ou toujours << perimee >>.

**Comment la valeur arrive ici** : la CI REECRIT la ligne `APP_VERSION`
ci-dessous avec le tag, juste avant PyInstaller. En developpement, c'est la
valeur du depot qui sert -- d'ou le suffixe `+dev`, qui dit franchement que ce
n'est pas un build publie plutot que de se faire passer pour un.
"""
from __future__ import annotations

# ⚠️ Ligne reecrite par la CI (`.github/workflows/release.yml`). Garder la
# forme exacte `APP_VERSION = "..."` : le remplacement s'appuie dessus.
APP_VERSION = "0.1.0+dev"


def display_version() -> str:
    """Ce qu'on montre a l'utilisateur : `v` + la version."""
    return f"v{APP_VERSION}"


def is_release_build() -> bool:
    """False pour une execution depuis les sources ou un build non tague.

    Le verificateur de mise a jour s'en sert pour ne PAS annoncer qu'une
    version de developpement est perimee : elle est en avance, pas en retard.
    """
    return "+dev" not in APP_VERSION
