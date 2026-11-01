"""Genere `assets/logo/promptuino.ico` depuis `assets/logo/icon-dark.svg`.

    python scripts/gen_app_icon.py

Pourquoi un script et pas un binaire depose a la main : un `.ico` committe
sans provenance ne se regenere pas quand le logo change, et personne ne sait
plus de quoi il sort. Ici, la source est le SVG du depot.

⚠️ Deux details qui changent le RESULTAT et pas seulement la forme :

1. **Les polices du depot sont chargees avant le rendu.** Le SVG demande
   `Geist` ; sans elle, Qt tombe sur une police systeme et l'icone ne
   ressemble plus a la marque.
2. **`icon-dark.svg` et pas `icon-transparent-dark.svg`** : une icone
   d'application a besoin de son fond. La variante transparente donnerait un
   texte clair flottant, illisible sur un theme clair.

⚠️ **Limite assumee** : ce logo est un mot (<< Prompt>uino >>). A 16 px --
la taille qu'utilise la liste << Applications installees >> de Windows -- il
devient une tache. Une icone lisible en petit demanderait un GLYPHE, pas un
mot ; c'est une decision de design, pas un reglage de ce script.
"""
from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "assets" / "logo" / "icon-dark.svg"
CIBLE = RACINE / "assets" / "logo" / "promptuino.ico"

# Tailles que Windows pioche selon le contexte : 16 = liste de
# desinstallation, 32 = barre des taches, 48 = Explorateur, 256 = grandes
# vignettes. Fournir les intermediaires evite un reechantillonnage laid.
TAILLES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    from PyQt6.QtGui import QFontDatabase, QGuiApplication, QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer

    app = QGuiApplication(sys.argv)          # requis pour rendre du texte

    polices = RACINE / "assets" / "fonts"
    for ttf in sorted(polices.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(ttf))

    rendu = QSvgRenderer(str(SOURCE))
    if not rendu.isValid():
        print(f"SVG illisible : {SOURCE}")
        return 2

    from PIL import Image

    images = []
    for n in TAILLES:
        img = QImage(n, n, QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        rendu.render(p)
        p.end()
        buf = img.constBits().asstring(n * n * 4)
        # Qt rend en ARGB32 little-endian = BGRA en memoire.
        images.append(Image.frombytes("RGBA", (n, n), buf, "raw", "BGRA"))

    images[-1].save(CIBLE, format="ICO",
                    sizes=[(n, n) for n in TAILLES])
    print(f"{CIBLE.relative_to(RACINE)} : {CIBLE.stat().st_size} octets, "
          f"{len(TAILLES)} tailles {TAILLES}")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
