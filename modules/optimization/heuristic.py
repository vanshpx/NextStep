"""
modules/optimization/heuristic.py
-----------------------------------
Implements the FTRM heuristic desirability function.

Equation (12):
    η_ij = Score(j) / Distance(i,j)

Where (confirmed 2026-02-20):
    Score(j)       = S_pti  (unified satisfaction metric from satisfaction.py)
    Distance(i,j)  = Dij    (travel time in minutes)

Interpretation:
    Higher satisfaction + shorter travel time → higher heuristic value.
    Used by ACO transition probability (Eq 13).

Edge cases handled:
    - Dij = 0 → return inf (same location; set to large cap to avoid div-by-zero)
    - S_pti = 0 (HC gate closed) → return 0.0 (infeasible POI)
"""

from __future__ import annotations


# Cap for same-location heuristic (prevents inf in probability normalization)
_ETA_MAX: float = 1e6


def compute_eta(S_pti: float, Dij: float) -> float:
    """
    η_ij = S_pti / Dij   (Eq 12)

    Args:
        S_pti : Unified satisfaction score for target node j ∈ [0,1].
        Dij   : Travel time from node i to node j [minutes].

    Returns:
        η_ij ≥ 0.
        Returns 0.0 if S_pti == 0 (HC blocked).
        Returns _ETA_MAX if Dij ≈ 0 (same location — cap applied).
    """
    if S_pti <= 0.0:
        return 0.0
    if Dij <= 0.0:
        return _ETA_MAX
    return S_pti / Dij


def compute_eta_matrix(
    S_matrix: dict[int, float],
    D_matrix: dict[tuple[int, int], float],
    node_ids: list[int],
) -> dict[tuple[int, int], float]:
    """
    Compute full η matrix for all pairs (i,j) in node_ids.

    Args:
        S_matrix : {node_id: S_pti} — satisfaction per node.
        D_matrix : {(i,j): Dij}     — travel time matrix [minutes].
        node_ids : List of all node IDs to include.

    Returns:
        {(i,j): η_ij} for all i ≠ j pairs.
    """
    eta: dict[tuple[int, int], float] = {}
    for i in node_ids:
        for j in node_ids:
            if i == j:
                continue
            Dij = D_matrix.get((i, j), float("inf"))
            S_j = S_matrix.get(j, 0.0)
            eta[(i, j)] = compute_eta(S_j, Dij)
    return eta
