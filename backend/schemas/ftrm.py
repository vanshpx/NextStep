"""
schemas/ftrm.py
----------------
Dataclass definitions for all FTRM (Flexible Travel Route Model) mathematical entities.

Sources:
  - Architecture doc (FTRM section)
  - User completions (2026-02-20): Eq 2, 9, 14, HCpti domain, P_ij normalization,
    δ_ij definition, unit assignments.

Units (CONFIRMED via user completions):
  - Dij  : minutes (travel time)
  - STi  : minutes (visit duration)
  - Tmax : minutes per day
  - Si   : normalized utility [0, 1]
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Graph entities  G = (V, E)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FTRMNode:
    """
    A vertex v ∈ V in the POI graph.

    Attributes:
        node_id   : Unique identifier (integer index in adjacency matrix).
        name      : Human-readable POI name.
        Si        : Utility score ∈ [0,1]  (base; Spti computed at runtime).
        STi       : Visit duration [minutes].
        lat, lon  : Geographic coordinates (used to compute Dij via DistanceTool).
        is_start  : True if this is the fixed start node s.
        is_end    : True if this is the fixed end node e.
    """
    node_id: int = 0
    name: str = ""
    Si: float = 0.0           # normalized utility [0, 1]
    STi: float = 0.0          # minutes
    lat: float = 0.0
    lon: float = 0.0
    is_start: bool = False
    is_end: bool = False


@dataclass
class FTRMEdge:
    """
    An edge (i,j) ∈ E in the POI graph.

    Attributes:
        i   : Source node_id.
        j   : Destination node_id.
        Dij : Travel time [minutes].
    """
    i: int = 0
    j: int = 0
    Dij: float = 0.0          # minutes


@dataclass
class FTRMGraph:
    """
    G = (V, E) — complete weighted graph of POIs.

    adjacency[i][j] = Dij (minutes). -1 means no direct edge.
    """
    nodes: list[FTRMNode] = field(default_factory=list)
    edges: list[FTRMEdge] = field(default_factory=list)

    # Derived at build time
    adjacency: dict[tuple[int, int], float] = field(default_factory=dict)

    def build_adjacency(self) -> None:
        """Populate adjacency dict from edges list."""
        self.adjacency = {(e.i, e.j): e.Dij for e in self.edges}

    def get_Dij(self, i: int, j: int) -> float:
        """
        Return travel time [minutes] from node i to node j.
        Returns float('inf') if edge not found.
        """
        return self.adjacency.get((i, j), float("inf"))

    def get_node(self, node_id: int) -> Optional[FTRMNode]:
        """Return node by node_id."""
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ACO & optimization parameters
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FTRMParameters:
    """
    All tunable parameters for the FTRM optimization model.

    Defaults from user completions (SUGGESTED DEFAULT — tune empirically).
    """
    # ── Temporal ──────────────────────────────────────────────────────────────
    Tmax: float = 480.0                  # minutes per day (default 8 hours)
    trip_days: list[int] = field(default_factory=lambda: [1])  # d ∈ M

    # ── ACO hyperparameters ────────────────────────────────────────────────────
    alpha: float = 2.0                   # pheromone exponent (SUGGESTED DEFAULT)
    beta: float = 3.0                    # heuristic exponent (SUGGESTED DEFAULT)
    rho: float = 0.1                     # evaporation rate   (SUGGESTED DEFAULT)
    Q: float = 1.0                       # pheromone constant (SUGGESTED DEFAULT)
    tau_init: float = 1.0                # initial pheromone on all edges
    num_ants: int = 20                   # ants per iteration
    num_iterations: int = 100            # ACO iterations

    # ── Satisfaction weights ──────────────────────────────────────────────────
    # Wv weights for soft constraints (Eq 3: Σ Wv = 1)
    # Key = soft constraint name, Value = weight
    soft_constraint_weights: dict[str, float] = field(default_factory=dict)

    # SC aggregation method (Eq 2)
    # Options: "sum" | "least_misery" | "most_pleasure" | "multiplicative"
    sc_aggregation_method: str = "sum"   # RECOMMENDED for itinerary optimizer

    # ── Pheromone update strategy ─────────────────────────────────────────────
    # "best_ant" = deposit only on best tour (RECOMMENDED — lower noise)
    # "all_ants" = deposit from all ants
    pheromone_update_strategy: str = "best_ant"
