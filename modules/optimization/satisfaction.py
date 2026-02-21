"""
modules/optimization/satisfaction.py
--------------------------------------
Implements the full satisfaction chain from the FTRM model.

Equations implemented:
  Eq (1) : HC_pti = Π_m hcm_pti           — hard constraint conjunction
  Eq (2) : SC_pti = aggregation(Wv, scv)   — soft constraint aggregation (4 methods)
  Eq (3) : Σ Wv = 1                        — weight normalization (validated here)
  Eq (4) : S_pti  = HC_pti × SC_pti        — unified satisfaction metric

Confirmed defaults (2026-02-20 completions):
  - hcm_pti ∈ {0,1}  (binary — any violation gates entire POI to 0)
  - SC aggregation method: "sum" (recommended for itinerary optimizer)
  - scv_pti ∈ [0,1]
  - S_pti ∈ [0,1]
"""

from __future__ import annotations
import math
from typing import Literal

SCMethod = Literal["sum", "least_misery", "most_pleasure", "multiplicative"]


# ─────────────────────────────────────────────────────────────────────────────
# Equation (1): Hard Constraint Satisfaction
# ─────────────────────────────────────────────────────────────────────────────

def compute_HC(hard_results: list[int]) -> int:
    """
    HC_pti = Π_m hcm_pti

    Args:
        hard_results: List of binary hard constraint results hcm_pti ∈ {0,1}.
                      One entry per hard constraint m.

    Returns:
        1 if ALL hard constraints satisfied, 0 if ANY violated.

    Complexity: O(n) — short-circuits on first 0.
    """
    for hcm in hard_results:
        if hcm == 0:
            return 0
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# Equation (2): Soft Constraint Aggregation
# ─────────────────────────────────────────────────────────────────────────────

def compute_SC(
    sc_values: list[float],
    weights: list[float],
    method: SCMethod = "sum",
) -> float:
    """
    SC_pti using selectable aggregation method (Eq 2).

    Args:
        sc_values: Individual soft constraint scores scv_pti ∈ [0,1].
        weights:   Corresponding weights Wv ∈ [0,1]; must sum to 1 (Eq 3).
        method:    Aggregation method (see options below).

    Returns:
        Aggregated SC_pti ∈ [0,1].

    Methods:
        "sum"           : SC = Σ_v Wv × scv_pti
                          Smooth blending. RECOMMENDED for itinerary optimizer.
        "least_misery"  : SC = min_v(scv_pti)
                          Pessimistic — bottlenecked by worst constraint.
        "most_pleasure" : SC = max_v(scv_pti)
                          Optimistic — driven by best constraint.
        "multiplicative": SC = Π_v (scv_pti)^Wv
                          Strong penalty for any low-scoring constraint.
                          Avoid early in training — numerically unstable with many constraints.

    Raises:
        ValueError: If weights do not sum to ~1.0 (Eq 3 violated).
        ValueError: If sc_values and weights lengths do not match.
    """
    if not sc_values:
        return 0.0

    if len(sc_values) != len(weights):
        raise ValueError(
            f"sc_values length ({len(sc_values)}) must equal weights length ({len(weights)})"
        )

    # Eq (3): validate Σ Wv = 1
    weight_sum = sum(weights)
    if abs(weight_sum - 1.0) > 1e-4:
        raise ValueError(
            f"Eq (3) violated: Σ Wv = {weight_sum:.6f} ≠ 1.0. "
            f"Weights: {weights}"
        )

    if method == "sum":
        return sum(w * s for w, s in zip(weights, sc_values))

    elif method == "least_misery":
        return min(sc_values)

    elif method == "most_pleasure":
        return max(sc_values)

    elif method == "multiplicative":
        result = 1.0
        for w, s in zip(weights, sc_values):
            if s <= 0.0:
                return 0.0  # any zero collapses product
            result *= s ** w
        return result

    else:
        raise ValueError(
            f"Unknown SC aggregation method: '{method}'. "
            f"Valid options: 'sum', 'least_misery', 'most_pleasure', 'multiplicative'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Equation (4): Unified Satisfaction Metric
# ─────────────────────────────────────────────────────────────────────────────

def compute_S(HC_pti: int, SC_pti: float) -> float:
    """
    S_pti = HC_pti × SC_pti   (Eq 4)

    Args:
        HC_pti: Binary hard constraint gate ∈ {0,1}.
        SC_pti: Soft constraint score ∈ [0,1].

    Returns:
        Unified satisfaction ∈ [0,1].
        Returns 0.0 immediately if HC_pti == 0 (hard gate).
    """
    if HC_pti == 0:
        return 0.0
    return SC_pti


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: evaluate full chain for one POI
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_satisfaction(
    hard_results: list[int],
    sc_values: list[float],
    weights: list[float],
    method: SCMethod = "sum",
) -> dict:
    """
    Evaluate the full Eq 1 → 2 → 4 chain for one POI visit.

    Returns:
        {
            "HC":  int,   # Eq 1
            "SC":  float, # Eq 2
            "S":   float, # Eq 4
            "feasible": bool
        }
    """
    HC = compute_HC(hard_results)
    SC = compute_SC(sc_values, weights, method) if HC == 1 else 0.0
    S  = compute_S(HC, SC)
    return {"HC": HC, "SC": SC, "S": S, "feasible": HC == 1}
