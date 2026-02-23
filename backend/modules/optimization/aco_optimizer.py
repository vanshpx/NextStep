"""
modules/optimization/aco_optimizer.py
---------------------------------------
Ant Colony Optimization (ACO) engine for FTRM itinerary planning.

JSON-defined ACO entities (2026-02-20 spec):

  ant_state:
    current_node        : i ∈ V — position of ant at current step
    visited             : set[node_id] — enforces Eq 8 (visit-once)
    path                : ordered list[node_id] traversed so far
    elapsed             : Σ (D_ij + ST_i) [minutes] — Tmax guard (Eq 10)
    total_satisfaction  : Σ S_pti × ST_i — Eq 5 objective numerator

  heuristic_function   : η_ij = S_pti / D_ij  (Eq 12 → heuristic.py)

  transition_probability:
    P_ij = (τ_ij^α × η_ij^β) / Σ_{k ∈ feasible(i)} (τ_ik^α × η_ik^β)  (Eq 13)
    feasible(i) = { k ∈ V | k ∉ visited ∧ S_ptk > 0 ∧ elapsed+D_ik+ST_k ≤ T_max }

  local_update_rule    : τ_ij ← (1−ρ)τ_ij + δ_ij        (Eq 15)
    deposit            : δ_ij = Q/L_k  if edge (i,j) ∈ ant_k path, else 0

  global_update_rule   : τ_ij ← ρτ_ij + (1−ρ)δ_ij       (Eq 16)
    deposit            : δ_ij = Q/L_best  if edge (i,j) ∈ best_tour path, else 0
    strategy           : best-ant only (reduces noise for itinerary planning)

Equation references:
  Eq (8)  visit-once   : enforced via AntState.visited
  Eq (9)  continuity   : implicit — ant always extends from AntState.current_node
  Eq (10) Tmax         : AntState.elapsed + D_ij + ST_j ≤ T_max
  Eq (12) heuristic    : η_ij = S_pti / D_ij  (heuristic.py)
  Eq (13) probability  : _select_next()
  Eq (14) deposit      : _compute_delta()
  Eq (15) local update : _local_pheromone_update()
  Eq (16) global update: _global_pheromone_update()

Confirmed defaults (2026-02-20):
  α=2.0, β=3.0, ρ=0.1, Q=1.0, τ_init=1.0, strategy="best_ant"
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import Optional
from schemas.ftrm import FTRMGraph, FTRMNode, FTRMParameters
from modules.optimization.heuristic import compute_eta


# ─────────────────────────────────────────────────────────────────────────────
# Tour representation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Tour:
    """A complete single-day route produced by one ant."""
    path: list[int] = field(default_factory=list)   # ordered node_ids
    total_cost: float = 0.0                          # Σ (Dij + STi) [minutes]
    total_satisfaction: float = 0.0                  # Σ S_pti × STi (objective numerator)


@dataclass
class AntState:
    """
    Complete state of one ant at any point during tour construction.

    Maps to JSON spec 'ant_state' (2026-02-20):
      current_node       : i ∈ V
      visited            : set enforcing Eq 8 (visit-once)
      path               : ordered trajectory
      elapsed            : Σ (D_ij + ST_i) [minutes] for Eq 10 (Tmax gate)
      total_satisfaction : Σ S_pti × ST_i — partial Eq 5 objective
    """
    current_node: int = 0
    visited: set = field(default_factory=set)
    path: list = field(default_factory=list)
    elapsed: float = 0.0
    total_satisfaction: float = 0.0

    def to_tour(self) -> Tour:
        """Finalise ant state into a completed Tour."""
        return Tour(
            path=list(self.path),
            total_cost=self.elapsed,
            total_satisfaction=self.total_satisfaction,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ACO Optimizer
# ─────────────────────────────────────────────────────────────────────────────

class ACOOptimizer:
    """
    ACO solver for a single-day FTRM route optimization problem.

    Usage:
        aco = ACOOptimizer(graph, S_pti, params)
        best_tour = aco.run()
    """

    def __init__(
        self,
        graph: FTRMGraph,
        S_pti: dict[int, float],        # {node_id: S_pti} — pre-computed satisfaction per node
        params: FTRMParameters,
        start_node: int = 0,
        end_node: Optional[int] = None,
        seed: Optional[int] = None,
    ):
        """
        Args:
            graph      : FTRMGraph with nodes and adjacency (Dij in minutes).
            S_pti      : Pre-computed satisfaction scores per node (HC × SC).
            params     : FTRMParameters with ACO hyperparameters.
            start_node : node_id of s (start node).
            end_node   : node_id of e (end node). None = open route.
            seed       : Random seed for reproducibility.
        """
        self.graph = graph
        self.S_pti = S_pti
        self.params = params
        self.start_node = start_node
        self.end_node = end_node
        if seed is not None:
            random.seed(seed)

        # Initialise pheromone matrix τ_ij = τ_init for all edges
        self.tau: dict[tuple[int, int], float] = {
            (e.i, e.j): params.tau_init
            for e in graph.edges
        }

        # Precompute η_ij matrix (Eq 12) — static for all iterations
        node_ids = [n.node_id for n in graph.nodes]
        D_matrix = {(e.i, e.j): e.Dij for e in graph.edges}
        self.eta: dict[tuple[int, int], float] = {
            (i, j): compute_eta(S_pti.get(j, 0.0), D_matrix.get((i, j), float("inf")))
            for i in node_ids for j in node_ids if i != j
        }

    # ── Public interface ───────────────────────────────────────────────────────

    def run(self) -> Tour:
        """
        Execute ACO for params.num_iterations iterations.

        Returns:
            Best Tour found across all iterations and ants.
        """
        best_tour = Tour()
        best_tour.total_satisfaction = -1.0

        for iteration in range(self.params.num_iterations):
            iteration_tours: list[Tour] = []

            for _ in range(self.params.num_ants):
                tour = self._construct_tour()
                iteration_tours.append(tour)

                # Track global best
                if tour.total_satisfaction > best_tour.total_satisfaction:
                    best_tour = tour

            # Pheromone update
            if self.params.pheromone_update_strategy == "best_ant":
                self._global_pheromone_update(best_tour)  # Eq 16
            else:
                for t in iteration_tours:
                    self._local_pheromone_update(t)       # Eq 15

        return best_tour

    # ── Tour construction ─────────────────────────────────────────────────────

    def _construct_tour(self) -> Tour:
        """
        Construct one ant's route using AntState.
        Starts at start_node, selects next node via Eq 13 at each step.
        Stops when Tmax is reached or no feasible node remains.

        AntState fields map directly to JSON spec 'ant_state':
          current_node      → i ∈ V (current position)
          visited           → Eq 8 gate
          path              → ordered trajectory
          elapsed           → Eq 10 Tmax check
          total_satisfaction→ partial Eq 5 objective
        """
        state = AntState(
            current_node=self.start_node,
            visited={self.start_node},
            path=[self.start_node],
            elapsed=0.0,
            total_satisfaction=0.0,
        )

        while True:
            feasible = self._get_feasible_nodes(
                state.current_node, state.visited, state.elapsed
            )
            if not feasible:
                break

            next_node = self._select_next(state.current_node, feasible)   # Eq 13
            n_obj = self.graph.get_node(next_node)
            if n_obj is None:
                break

            Dij = self.graph.get_Dij(state.current_node, next_node)

            # Update AntState
            state.elapsed           += Dij + n_obj.STi
            state.total_satisfaction += self.S_pti.get(next_node, 0.0) * n_obj.STi
            state.path.append(next_node)
            state.visited.add(next_node)
            state.current_node = next_node

        # Close tour at end node if specified
        if self.end_node is not None and self.end_node not in state.visited:
            state.path.append(self.end_node)

        return state.to_tour()

    # ── Equation (13): Transition probability ────────────────────────────────

    def _select_next(self, current: int, feasible: list[int]) -> int:
        """
        Roulette-wheel selection using normalized transition probabilities.

        P_ij = (τ_ij^α × η_ij^β) / Σ_k∈feasible (τ_ik^α × η_ik^β)   [Eq 13]
        """
        alpha = self.params.alpha
        beta = self.params.beta

        weights: list[float] = []
        for j in feasible:
            tau_val = self.tau.get((current, j), 1e-6)   # floor prevents zero
            eta_val = self.eta.get((current, j), 0.0)

            score = (tau_val ** alpha) * (eta_val ** beta)
            weights.append(score)

        total = sum(weights)
        if total == 0.0:
            return random.choice(feasible)

        # Normalise and roulette-wheel select
        norm = [w / total for w in weights]
        r = random.random()
        cumulative = 0.0
        for j, p in zip(feasible, norm):
            cumulative += p
            if r <= cumulative:
                return j
        return feasible[-1]  # fallback

    # ── Equation (10) feasibility check ──────────────────────────────────────

    def _get_feasible_nodes(
        self,
        current: int,
        visited: set[int],
        elapsed: float,
    ) -> list[int]:
        """
        Return nodes satisfying:
          - Not visited (Eq 8)
          - Not start/end node (unless it IS the end node and we want to close)
          - HC gate: S_pti > 0
          - Time: elapsed + Dij + STj ≤ Tmax (Eq 10)
        """
        feasible = []
        Tmax = self.params.Tmax

        for node in self.graph.nodes:
            j = node.node_id
            if j in visited:
                continue
            if j == self.end_node:
                continue   # end node handled separately at tour close

            # HC gate
            if self.S_pti.get(j, 0.0) <= 0.0:
                continue

            # Tmax check (Eq 10)
            Dij = self.graph.get_Dij(current, j)
            if Dij == float("inf"):
                continue
            if elapsed + Dij + node.STi > Tmax:
                continue

            feasible.append(j)
        return feasible

    # ── Equation (14): Pheromone deposit ─────────────────────────────────────

    def _compute_delta(self, tour: Tour) -> dict[tuple[int, int], float]:
        """
        δ_ij (best-ant variant, Eq 14):
            δ_ij = Q / L_best   if edge (i,j) in tour
            δ_ij = 0            otherwise

        Where L_best = tour.total_cost  (total minutes; lower is better route cost).
        Falls back to all-ones deposit if cost is zero (degenerate tour).
        """
        if tour.total_cost <= 0.0:
            deposit = self.params.Q
        else:
            deposit = self.params.Q / tour.total_cost

        delta: dict[tuple[int, int], float] = {}
        for k in range(len(tour.path) - 1):
            i, j = tour.path[k], tour.path[k + 1]
            delta[(i, j)] = deposit

        return delta

    # ── Equation (15): Local pheromone update ────────────────────────────────

    def _local_pheromone_update(self, tour: Tour) -> None:
        """
        τ_ij ← (1 − ρ) × τ_ij + δ_ij   [Eq 15]
        Applied per-ant after each tour construction.
        """
        rho = self.params.rho
        delta = self._compute_delta(tour)

        for (i, j) in list(self.tau.keys()):
            evaporated = (1.0 - rho) * self.tau[(i, j)]
            deposited  = delta.get((i, j), 0.0)
            self.tau[(i, j)] = evaporated + deposited

    # ── Equation (16): Global pheromone update ────────────────────────────────

    def _global_pheromone_update(self, best_tour: Tour) -> None:
        """
        τ_ij ← ρ × τ_ij + (1 − ρ) × δ_ij   [Eq 16]
        Applied once per iteration using only the best tour found so far.
        This is the "best-ant" strategy — reduces noise vs all-ants update.
        """
        rho = self.params.rho
        delta = self._compute_delta(best_tour)

        for (i, j) in list(self.tau.keys()):
            evaporated = rho * self.tau[(i, j)]
            deposited  = (1.0 - rho) * delta.get((i, j), 0.0)
            self.tau[(i, j)] = evaporated + deposited
