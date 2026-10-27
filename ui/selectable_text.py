"""Rendre le texte INFORMATIF de l'app sélectionnable et copiable (TODO #95).

Né d'un besoin concret pendant la QA du 2026-09-07 : *« je ne peux pas te
copier-coller le texte de la bannière »*. Mesuré alors : **238 `QLabel` dans
`ui/`, dont 4 sélectionnables** (À propos, messages du chat, paramètres,
accueil). Tout le reste — bannières, messages d'erreur, avertissements de
câblage, instructions, contenu des modales — ne pouvait ni être surligné ni
être copié.

⛔ **L'interrupteur global est un piège, et c'est pour ça que ce module
existe.** Donner `TextSelectableByMouse` à tous les `QLabel` tient en une ligne
au démarrage et couvre même le code futur — mais un label sélectionnable
**capte le clic**, qui n'atteint plus le widget parent. Les **cards
cliquables** (onglet Composants, projets, modale d'ambiguïté, choix de
bibliothèque) deviendraient inertes sur toute leur zone de texte.

D'où une application **choisie** : on désigne les conteneurs qui portent de
l'information à lire, jamais ceux qui portent une action à cliquer.

⚠️ `make_selectable` s'applique à un SOUS-ARBRE, pas à un label : la plupart
des textes informatifs vivent dans des modales entières, et les énumérer un à
un dériverait au premier écran ajouté. La règle est donc « ce conteneur
est-il fait pour être LU ? » — si oui, tout ce qu'il contient est copiable.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget

# Ce que reçoit un texte destiné à être lu : sélection à la souris ET au
# clavier (Ctrl+A / Ctrl+C fonctionnent alors), plus les liens cliquables si
# le texte en contient — sans quoi rendre un label sélectionnable casserait
# les `<a href>` déjà présents dans certaines modales pédagogiques.
_FLAGS = (Qt.TextInteractionFlag.TextSelectableByMouse
          | Qt.TextInteractionFlag.TextSelectableByKeyboard
          | Qt.TextInteractionFlag.LinksAccessibleByMouse)


def make_selectable(root: QWidget) -> int:
    """Rend sélectionnable et copiable tout `QLabel` sous `root` (inclus).

    Retourne le nombre de labels traités — utile aux tests, qui vérifient que
    l'appel a bien mordu plutôt que de faire confiance à son existence.

    ⚠️ Ne PAS appeler sur un conteneur dont les enfants sont cliquables : le
    label capterait le clic destiné à la card. `is_selectable` permet de le
    vérifier depuis un test.
    """
    labels = root.findChildren(QLabel)
    if isinstance(root, QLabel):
        labels = [root, *labels]
    for label in labels:
        label.setTextInteractionFlags(_FLAGS)
    return len(labels)


def is_selectable(label: QLabel) -> bool:
    """True si `label` peut être surligné à la souris.

    Lit le drapeau réel du widget plutôt que de supposer qu'un appel a eu
    lieu : c'est ce qui rend la garde de dérive concluante.
    """
    return bool(label.textInteractionFlags()
                & Qt.TextInteractionFlag.TextSelectableByMouse)
