"""Ne JAMAIS ouvrir de fenetre de console en lancant un sous-processus.

⛔ **Defaut trouve le 2026-08-31, a la premiere installation du `.exe`** --
et rigoureusement invisible depuis les sources, ce qui explique qu'il ait
survecu si longtemps.

Sur Windows, un processus GRAPHIQUE (une application empaquetee avec
`console=False`) qui lance un programme CONSOLE se voit allouer une console
neuve par le systeme : une fenetre noire apparait le temps de l'appel. Rediriger
`stdout` et `stderr` n'y change RIEN -- l'allocation de la console est decidee
par le sous-systeme de l'executable enfant, pas par les descripteurs. Seul
`CREATE_NO_WINDOW` la supprime.

Depuis les SOURCES, l'application herite de la console du terminal qui l'a
lancee, l'enfant la reutilise, et aucune fenetre n'apparait. Le defaut ne se
manifeste donc que dans le paquet -- il a ete signale par l'utilisateur a la
premiere installation, sur deux symptomes qui n'en faisaient qu'un :

- des fenetres de terminal qui clignotent pendant la generation
  (`arduino_cli._run`, appele a chaque compilation) ;
- **la fenetre de parametres qui se referme toute seule** : elle se ferme des
  qu'elle perd le focus (`SettingsDialog.changeEvent`, « close on outside
  click ») et `LibraryView` lance `arduino-cli lib list` a sa construction. La
  console volait l'activation, les parametres se fermaient. Une console
  invisible ne vole rien.

`CREATE_NO_WINDOW` n'existe que sur Windows ; ailleurs la constante vaut 0,
c'est-a-dire un `creationflags` neutre. La passer INCONDITIONNELLEMENT est donc
sur sur les trois plateformes -- pas de `if sys.platform`, rien a oublier dans
une branche.

⚠️ Toute nouvelle invocation de sous-processus doit la passer.
`scripts/test_no_console_window.py` fait rougir la suite sinon : la regle est
mecanique, elle ne repose pas sur la memoire de la prochaine personne.
"""
from __future__ import annotations

import subprocess

NO_CONSOLE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
