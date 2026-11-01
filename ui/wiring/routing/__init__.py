"""Wiring.routing — routeur de fils sur grille (style autorouteur PCB).

Architecture (cf .planning/wiring_routing_design.md) :
  - grid.OccupancyGrid : 4 numpy arrays 2D modelisant l'espace canvas
  - astar.astar       : recherche A* Manhattan avec cout de virage
  - router.route_wires : pipeline complet scene + netlist -> wires
"""
from __future__ import annotations

from .grid import OccupancyGrid
from .astar import astar
from .router import route_wires

# Variable d'env historique. Conservee en re-export comme constante string
# -- les scripts smoke qui la settent ne provoquent plus aucun comportement,
# mais ne plantent pas non plus.
FEATURE_FLAG_ENV = "PROMPTUINO_ROUTER"


__all__ = [
    "OccupancyGrid",
    "astar",
    "route_wires",
    "FEATURE_FLAG_ENV",
]
