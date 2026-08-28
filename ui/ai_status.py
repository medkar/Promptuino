"""Dernier etat CONNU du backend IA — partage sans reseau (TODO #80).

⛔ **Pourquoi ce module existe.** La pastille << Modele IA >> de la barre
d'etat etait VERTE EN DUR : `statusbar._refresh` ne consultait rien du tout.
Elle avait l'air juste tant que tout allait bien — le pire mode d'echec, elle
ne se trompait que quand on avait besoin d'elle.

⛔ **Le correctif naif est INTERDIT, et c'est mesure** : appeler
`is_server_running()` depuis `_refresh()` coute 29 ms serveur allume mais
**2 030 ms serveur ETEINT**, sur le fil graphique et a chaque signal
(`ai_config.changed`, `board_manager`…). Deux secondes de gel precisement
dans le cas ou la pastille devrait enfin dire quelque chose.

Ce module ne fait donc **AUCUN appel reseau** : il memorise ce que l'onglet
Modele IA a deja calcule (a la construction, a chaque affichage de l'onglet,
a chaque changement de backend) et le republie par signal. La pastille lit,
elle ne mesure jamais.

⚠️ **`None` veut dire << on ne sait pas encore >>, et la pastille doit alors
etre GRISE** : une pastille << inconnue >> vaut mieux qu'une verte qui ment —
c'est le defaut d'origine qu'il ne faut pas recreer en croyant le corriger.

⚠️ **L'etat est le DERNIER CONNU, pas un temps reel** : un serveur Ollama qui
tombe pendant que l'utilisateur travaille ailleurs ne sera vu qu'au prochain
recalcul (retour sur l'onglet, changement de backend, generation). C'est le
prix du zero-reseau, assume.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

# Les familles d'etats que la pastille sait colorer. Tout etat inconnu est
# traite comme une erreur : mieux vaut du rouge en trop que du vert menteur.
KINDS_OK = frozenset({"ollama_ok", "cli_ok", "cloud_key_ok"})
KINDS_WARN = frozenset({"ollama_model_missing"})


class _AiStatus(QObject):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._state: "str | None" = None

    @property
    def state(self) -> "str | None":
        return self._state

    def set_state(self, kind: "str | None") -> None:
        if kind != self._state:
            self._state = kind
            self.changed.emit()


ai_status = _AiStatus()
