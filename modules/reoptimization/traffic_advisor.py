"""
modules/reoptimization/traffic_advisor.py
-------------------------------------------
Deterministic traffic disruption handler for the Travel Itinerary Optimizer.

Core logic
──────────
1. Recompute effective travel time for every remaining POI:
       Dij_new = Dij_base × delay_factor
   where delay_factor = 1 + traffic_level
   and   Dij_base     = haversine(current_pos, stop) / AVG_SPEED_KMH × 60   [minutes]

2. Feasibility check for each stop:
       feasible  IF  Dij_new + stop.visit_duration_minutes ≤ remaining_minutes
       infeasible otherwise

3. For infeasible stops apply Defer vs Replace rule:
       IF  S_pti ≥ HIGH_PRIORITY_THRESHOLD   → DEFER (stop is kept for next slot/day)
       ELSE                                   → REPLACE (drop from today, find nearby alt)

4. Rank alternatives by updated heuristic:
       η_ij_new = S_pti / Dij_new            (ACO heuristic with congested travel time)
   Prefer stops that are:
       • geographically clustered with current position  (Dij_new ≤ CLUSTER_RADIUS_MIN)
       • HC-valid
       • high S_pti

5. Return TrafficAdvisoryResult with feasibility map, defer/replace split,
   ranked alternatives, and new start-time offsets.

Constants (MISSING in spec — defined here with rationale):
    HIGH_PRIORITY_THRESHOLD = 0.65
        S_pti above this → stop is valuable enough to defer rather than replace.
    CLUSTER_RADIUS_MIN      = 30
        Minutes travel in traffic — stops within this window are considered
        "nearby" for geographic clustering.
    AVG_SPEED_CLEAR_KMH     = 20.0
        Assumed road speed under normal conditions (urban).
    AVG_SPEED_WALK_KMH      = 4.0
        Fallback pedestrian speed used when delay_factor > 2.0 (gridlock).
    REPLAN_DELAY_THRESHOLD_MIN = 20
        Minimum accumulated delay (minutes) before a replan is triggered.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from math import radians, sin, cos, sqrt, atan2

from modules.tool_usage.attraction_tool import AttractionRecord
from schemas.constraints import ConstraintBundle


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

HIGH_PRIORITY_THRESHOLD:    float = 0.65   # MISSING in spec
CLUSTER_RADIUS_MIN:         float = 30.0   # MISSING in spec
AVG_SPEED_CLEAR_KMH:        float = 20.0   # MISSING in spec
AVG_SPEED_WALK_KMH:         float = 4.0    # MISSING in spec
REPLAN_DELAY_THRESHOLD_MIN: int   = 20     # MISSING in spec
EARTH_RADIUS_KM:            float = 6371.0


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrafficFeasibility:
    """Feasibility assessment for one POI under current traffic conditions."""
    attraction:   AttractionRecord
    Dij_base:     float   # travel time [min] without traffic
    Dij_new:      float   # travel time [min] with delay applied
    delay_factor: float
    S_pti:        float   # composite FTRM score
    feasible:     bool
    action:       str     # "keep" | "defer" | "replace"
    reason:       str


@dataclass
class TrafficAlternative:
    """One nearby, feasible alternative ranked by η_ij_new."""
    attraction:   AttractionRecord
    eta_ij_new:   float   # S_pti / Dij_new
    S_pti:        float
    Dij_new:      float   # congested travel time [min]
    is_clustered: bool    # within CLUSTER_RADIUS_MIN
    why_suitable: str


@dataclass
class TrafficAdvisoryResult:
    """Full traffic advisory package produced by TrafficAdvisor.assess()."""
    traffic_level:  float
    delay_factor:   float
    threshold:      float
    feasibility:    list[TrafficFeasibility]   = field(default_factory=list)
    deferred_stops: list[TrafficFeasibility]   = field(default_factory=list)
    replaced_stops: list[TrafficFeasibility]   = field(default_factory=list)
    alternatives:   list[TrafficAlternative]   = field(default_factory=list)
    start_time_delay_minutes: int = 0          # recommended start-time push
    strategy_msg:   str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_minutes(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
    speed_kmh: float,
) -> float:
    r   = EARTH_RADIUS_KM
    φ1, φ2 = radians(lat1), radians(lat2)
    dφ  = radians(lat2 - lat1)
    dλ  = radians(lon2 - lon1)
    a   = sin(dφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(dλ / 2) ** 2
    d   = 2 * r * atan2(sqrt(a), sqrt(1 - a))
    return max(1.0, (d / speed_kmh) * 60)


def _effective_speed(delay_factor: float) -> float:
    """At extreme congestion (delay_factor > 2) switch to walking speed."""
    return AVG_SPEED_WALK_KMH if delay_factor > 2.0 else AVG_SPEED_CLEAR_KMH


def _simple_S_pti(a: AttractionRecord, constraints: ConstraintBundle) -> float:
    """Lightweight FTRM score: rating normalised + category + preference bonuses."""
    rating_norm = (getattr(a, "rating", 3.0) - 1.0) / 4.0
    soft = constraints.soft
    interest_bonus = (
        0.15 if soft.interests and
        any(i.lower() == a.category.lower() for i in soft.interests)
        else 0.0
    )
    crowd_bonus = (
        0.10 if soft.avoid_crowds and not getattr(a, "is_outdoor", False)
        else 0.0
    )
    return min(1.0, rating_norm + interest_bonus + crowd_bonus)


def _why_traffic_suitable(
    a: AttractionRecord,
    is_clustered: bool,
    constraints: ConstraintBundle,
) -> str:
    reasons: list[str] = []
    if is_clustered:
        reasons.append(f"nearby ({int(CLUSTER_RADIUS_MIN)} min or less in traffic)")
    soft = constraints.soft
    if soft.interests and a.category.lower() in [i.lower() for i in soft.interests]:
        reasons.append(f"matches interest in '{a.category}'")
    if not getattr(a, "is_outdoor", False):
        reasons.append("indoor — avoids weather+traffic exposure")
    if soft.pace_preference == "relaxed" and a.intensity_level == "low":
        reasons.append("low intensity — suits relaxed pace")
    reasons.append(f"η_ij_new = S/Dij")
    return "; ".join(reasons) if reasons else "ranked by η_ij = S_pti/Dij_new"


# ─────────────────────────────────────────────────────────────────────────────
# TrafficAdvisor
# ─────────────────────────────────────────────────────────────────────────────

class TrafficAdvisor:
    """
    Assesses traffic impact on remaining POIs and ranks alternatives.

    Usage:
        advisor = TrafficAdvisor()
        result  = advisor.assess(
            traffic_level     = 0.65,
            threshold         = 0.44,
            delay_minutes     = 35,
            remaining_pool    = [...],
            constraints       = bundle,
            current_lat       = 28.62,
            current_lon       = 77.21,
            remaining_minutes = 250,
            top_n             = 3,
        )
    """

    def assess(
        self,
        traffic_level:     float,
        threshold:         float,
        delay_minutes:     int,
        remaining_pool:    list[AttractionRecord],
        constraints:       ConstraintBundle,
        current_lat:       float,
        current_lon:       float,
        remaining_minutes: int,
        top_n:             int = 3,
    ) -> TrafficAdvisoryResult:
        """
        Deterministic traffic disruption assessment.

        delay_factor = 1 + traffic_level
        For each stop:
            Dij_base = haversine(current, stop) / speed_clear
            Dij_new  = Dij_base × delay_factor
            feasible = Dij_new + visit_duration ≤ remaining_minutes

        If infeasible:
            S_pti ≥ HIGH_PRIORITY_THRESHOLD → DEFER
            S_pti <  HIGH_PRIORITY_THRESHOLD → REPLACE
        """
        delay_factor = 1.0 + traffic_level
        speed        = _effective_speed(delay_factor)

        feasibility: list[TrafficFeasibility] = []
        deferred:    list[TrafficFeasibility] = []
        replaced:    list[TrafficFeasibility] = []
        keep_pool:   list[TrafficFeasibility] = []

        for a in remaining_pool:
            Dij_base = _haversine_minutes(
                current_lat, current_lon,
                a.location_lat, a.location_lon,
                AVG_SPEED_CLEAR_KMH,
            )
            Dij_new  = Dij_base * delay_factor
            S        = _simple_S_pti(a, constraints)
            trip_ok  = (Dij_new + a.visit_duration_minutes) <= remaining_minutes

            # ── Defer vs Replace ──────────────────────────────────────────────
            if trip_ok:
                action = "keep"
                reason = (
                    f"Dij_new {Dij_new:.1f} min + {a.visit_duration_minutes} min "
                    f"≤ {remaining_minutes} min remaining — feasible."
                )
                fi = TrafficFeasibility(
                    attraction   = a,
                    Dij_base     = Dij_base,
                    Dij_new      = Dij_new,
                    delay_factor = delay_factor,
                    S_pti        = S,
                    feasible     = True,
                    action       = action,
                    reason       = reason,
                )
                keep_pool.append(fi)
            else:
                if S >= HIGH_PRIORITY_THRESHOLD:
                    # Valuable stop — defer, not drop
                    action = "defer"
                    reason = (
                        f"Infeasible: Dij_new {Dij_new:.1f} + {a.visit_duration_minutes} "
                        f"min > {remaining_minutes} min. "
                        f"S_pti={S:.2f} ≥ {HIGH_PRIORITY_THRESHOLD} → deferred."
                    )
                else:
                    # Low-priority — replace with closer alternative
                    action = "replace"
                    reason = (
                        f"Infeasible: Dij_new {Dij_new:.1f} + {a.visit_duration_minutes} "
                        f"min > {remaining_minutes} min. "
                        f"S_pti={S:.2f} < {HIGH_PRIORITY_THRESHOLD} → replace."
                    )
                fi = TrafficFeasibility(
                    attraction   = a,
                    Dij_base     = Dij_base,
                    Dij_new      = Dij_new,
                    delay_factor = delay_factor,
                    S_pti        = S,
                    feasible     = False,
                    action       = action,
                    reason       = reason,
                )
                if action == "defer":
                    deferred.append(fi)
                else:
                    replaced.append(fi)

            feasibility.append(fi)

        # ── Rank alternatives from keep_pool by η_ij_new ─────────────────────
        # Only stops that are feasible AND not already in the deferred list
        alt_candidates: list[TrafficAlternative] = []
        deferred_names = {d.attraction.name for d in deferred}
        replaced_names = {r.attraction.name for r in replaced}

        for fi in keep_pool:
            a = fi.attraction
            clustered = fi.Dij_new <= CLUSTER_RADIUS_MIN
            eta       = fi.S_pti / fi.Dij_new if fi.Dij_new > 0 else 0.0
            alt_candidates.append(TrafficAlternative(
                attraction   = a,
                eta_ij_new   = eta,
                S_pti        = fi.S_pti,
                Dij_new      = fi.Dij_new,
                is_clustered = clustered,
                why_suitable = _why_traffic_suitable(a, clustered, constraints),
            ))

        # Sort: clustered first, then by η_ij_new descending
        alt_candidates.sort(
            key=lambda x: (not x.is_clustered, -x.eta_ij_new)
        )
        alternatives = alt_candidates[:top_n]

        # ── Recommended start-time push ───────────────────────────────────────
        # Push start time by the accumulated delay so downstream time slots are valid
        start_delay = delay_minutes if delay_minutes >= REPLAN_DELAY_THRESHOLD_MIN else 0

        # ── Strategy message ──────────────────────────────────────────────────
        alt_names = " and ".join(f"'{a.attraction.name}'" for a in alternatives[:2])
        def_names = ", ".join(f"'{d.attraction.name}'" for d in deferred[:2])
        rep_names = ", ".join(f"'{r.attraction.name}'" for r in replaced[:2])

        parts: list[str] = [
            f"Traffic at {traffic_level:.0%} (threshold {threshold:.0%}), "
            f"delay factor ×{delay_factor:.1f}."
        ]
        if deferred:
            parts.append(
                f"{len(deferred)} high-priority stop(s) deferred "
                f"(S_pti ≥ {HIGH_PRIORITY_THRESHOLD}): {def_names}."
            )
        if replaced:
            parts.append(
                f"{len(replaced)} low-priority stop(s) replaced: {rep_names}."
            )
        if alternatives:
            parts.append(
                f"Routing to nearby feasible stop(s): {alt_names}."
            )
        if start_delay > 0:
            parts.append(f"Start time pushed by +{start_delay} min.")

        return TrafficAdvisoryResult(
            traffic_level            = traffic_level,
            delay_factor             = delay_factor,
            threshold                = threshold,
            feasibility              = feasibility,
            deferred_stops           = deferred,
            replaced_stops           = replaced,
            alternatives             = alternatives,
            start_time_delay_minutes = start_delay,
            strategy_msg             = " ".join(parts),
        )
