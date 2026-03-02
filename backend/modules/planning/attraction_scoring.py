"""
modules/planning/attraction_scoring.py
----------------------------------------
FTRM-based attraction scoring for the Route Planner's daily planning loop.

Simplified to API-Verified model (07-simplified-model.md).

  Eq (1)  : HC_pti = Π_m hcm_pti
  Eq (2)  : SC_pti = Wr·SC_r + Wp·SC_p + Wo·SC_o   (3 dimensions only)
  Eq (4)  : S_pti  = HC_pti × SC_pti
  Eq (12) : η_ij   = S_pti / Dij

Hard constraints (via constraint_registry — simplified):
  hc1: opening_hours gate           (Google Places)
  hc2: time-budget feasibility      (elapsed + Dij + STi ≤ Tmax)
  hc3: wheelchair accessibility     (Google Places)
  hc4: minimum visit duration       (remaining ≥ Dij + min_visit_duration_minutes)

Soft constraints (scored here — 3 dimensions):
  SC_r (w=0.40): rating quality         — normalised poi.rating [0,1]
  SC_p (w=0.35): interest / category match — poi.category ∈ user.interests
  SC_o (w=0.25): outdoor preference     — is_outdoor vs pace_preference + avoid_crowds

Removed SC dimensions (no API source):
  BREAKING_CHANGE: sc1 (optimal_visit_time), sc4 (preferred_time_of_day),
  sc5 (intensity_level / crowd energy)

Weights default: [Wr=0.40, Wp=0.35, Wo=0.25]. Override via sc_weights parameter.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import time

from schemas.constraints import ConstraintBundle, SoftConstraints
from modules.tool_usage.attraction_tool import AttractionRecord
from modules.tool_usage.distance_tool import DistanceTool
from modules.tool_usage.time_tool import TimeTool
from modules.optimization.satisfaction import compute_HC, compute_SC, compute_S
from modules.optimization.heuristic import compute_eta
import config


# SC weights for 3 API-verified soft dimensions [Wr, Wp, Wo] (must sum to 1.0)
# Source: 07-simplified-model.md § Surviving SC dimensions
_DEFAULT_SC_WEIGHTS = [0.40, 0.35, 0.25]


@dataclass
class AttractionScore:
    """Computed FTRM score breakdown for a single attraction candidate."""
    attraction: AttractionRecord
    # FTRM satisfaction chain
    HC_pti: int           # Eq 1: binary hard gate
    SC_pti: float         # Eq 2: soft constraint aggregation
    S_pti: float          # Eq 4: unified satisfaction = HC × SC
    # Heuristic and feasibility
    eta_ij: float         # Eq 12: η = S_pti / Dij (selection metric)
    Dij_minutes: float    # travel time to this attraction [minutes]
    feasible: bool        # True if S_ret (time gate) is satisfied


class AttractionScorer:
    """
    FTRM-based scorer implementing Algorithm 1.
    Computes the full Eq 1→2→4→12 chain per attraction candidate.

    Hard constraints are evaluated via constraint_registry (hc1–hc8).
    Soft constraints sc1–sc5 are computed here using user profile from
    SoftConstraints (passed in via ConstraintBundle).
    """

    def __init__(
        self,
        distance_tool: DistanceTool | None = None,
        time_tool: TimeTool | None = None,
        sc_method: str = config.SC_AGGREGATION_METHOD,
        sc_weights: list[float] | None = None,
        Tmax_minutes: float = config.ACO_TMAX_MINUTES,
        constraints: ConstraintBundle | None = None,
    ):
        self.distance_tool  = distance_tool or DistanceTool()
        self.time_tool      = time_tool     or TimeTool()
        self.sc_method      = sc_method
        self.sc_weights     = sc_weights or _DEFAULT_SC_WEIGHTS
        self.Tmax_minutes   = Tmax_minutes
        self.soft           = constraints.soft if constraints else SoftConstraints()
        self.hard           = constraints.hard if constraints else None
        # Removed: trip_month, group_size, traveler_ages (no API source for
        # min_age, group-size bounds, seasonal_open_months) — BREAKING_CHANGE

    # ── Public ────────────────────────────────────────────────────────────────

    def score_all(
        self,
        candidates: list[AttractionRecord],
        p_cur_lat: float,
        p_cur_lon: float,
        t_cur: time,
        end_time: time,
        is_arrival_or_departure_day: bool = False,  # retained for call-site compatibility; unused
    ) -> list[AttractionScore]:
        """
        Score all candidate attractions; return sorted descending by η_ij (Eq 12).
        Infeasible attractions (feasible=False) are placed at end.
        """
        elapsed_minutes = self.time_tool.minutes_until(t_cur, end_time)
        # elapsed = how much day has been used = Tmax - remaining
        used_minutes = max(0.0, self.Tmax_minutes - elapsed_minutes)

        scores = [
            self._score_one(
                a, p_cur_lat, p_cur_lon, t_cur,
                used_minutes, elapsed_minutes,
            )
            for a in candidates
        ]
        # Sort: feasible first (by η desc), then infeasible at end
        feasible   = sorted([s for s in scores if s.feasible],     key=lambda x: x.eta_ij, reverse=True)
        infeasible = [s for s in scores if not s.feasible]
        return feasible + infeasible

    # ── Internal ──────────────────────────────────────────────────────────────

    def _score_one(
        self,
        attraction: AttractionRecord,
        p_cur_lat: float,
        p_cur_lon: float,
        t_cur: time,
        used_minutes: float,
        remaining_minutes: float,
    ) -> AttractionScore:
        """Full FTRM scoring pipeline for one attraction (simplified 3-SC model)."""

        # Travel time Dij [minutes] — OSRM Route API; haversine fallback on error
        Dij = self.distance_tool.travel_time_minutes(
            p_cur_lat, p_cur_lon,
            attraction.location_lat, attraction.location_lon,
        )

        total_needed = Dij + attraction.visit_duration_minutes

        # ── Hard Constraints (Eq 1) via constraint_registry ───────────────────
        from modules.optimization.constraint_registry import evaluate_hc
        hc_requires_wheelchair = (self.hard.requires_wheelchair if self.hard else False)
        ctx = {
            "t_cur":               t_cur,
            "elapsed_min":         used_minutes,
            "Tmax_min":            self.Tmax_minutes,
            "Dij_minutes":         Dij,
            "requires_wheelchair": hc_requires_wheelchair,
        }
        poi_data = {
            "opening_hours":              attraction.opening_hours,
            "visit_duration_minutes":     attraction.visit_duration_minutes,
            "min_visit_duration_minutes": attraction.min_visit_duration_minutes,
            "wheelchair_accessible":      attraction.wheelchair_accessible,
            "Dij_minutes":                Dij,
        }
        hard_results = evaluate_hc("attraction", poi_data, ctx)
        HC = compute_HC(hard_results)    # Eq 1

        # ── Soft Constraints (Eq 2) — 3 API-verified dimensions ──────────────
        # SC_r (w=0.40): rating quality
        sc_r = self._score_rating(attraction)
        # SC_p (w=0.35): interest / category alignment
        sc_p = self._score_interest_match(attraction, self.soft)
        # SC_o (w=0.25): outdoor preference + crowd avoidance
        sc_o = self._score_outdoor_preference(attraction, t_cur, self.soft)

        SC = compute_SC([sc_r, sc_p, sc_o], self.sc_weights, self.sc_method)  # Eq 2

        # ── Unified Satisfaction (Eq 4) ───────────────────────────────────────
        S = compute_S(HC, SC)          # Eq 4

        # ── Heuristic (Eq 12) ─────────────────────────────────────────────────
        eta = compute_eta(S, Dij)      # Eq 12

        return AttractionScore(
            attraction   = attraction,
            HC_pti       = HC,
            SC_pti       = SC,
            S_pti        = S,
            eta_ij       = eta,
            Dij_minutes  = Dij,
            feasible     = (HC == 1),
        )

    # ── Soft constraint scorers ───────────────────────────────────────────────

    @staticmethod
    def _check_opening_hours(attraction: AttractionRecord, t_cur: time) -> int:
        """hc1 fallback: Is current time within attraction opening hours?"""
        oh = attraction.opening_hours
        if not oh or "-" not in oh:
            return 1
        parts = oh.split("-")
        if len(parts) != 2:
            return 1
        return 1 if TimeTool.is_within_window(t_cur, parts[0].strip(), parts[1].strip()) else 0

    @staticmethod
    def _score_interest_match(
        attraction: AttractionRecord,
        soft: SoftConstraints,
    ) -> float:
        """
        SC_p: Interest / category alignment.
        1.0 — attraction.category is in user interests list
        0.5 — no interests defined (neutral)
        0.0 — category not in interests (excluded per simplified model)
        """
        if not soft.interests:
            return 0.5  # no preference data → neutral
        cat = attraction.category.lower()
        if any(cat in interest.lower() or interest.lower() in cat
               for interest in soft.interests):
            return 1.0
        return 0.0   # category not in interests

    @staticmethod
    def _score_rating(attraction: AttractionRecord) -> float:
        """
        SC_r: Normalised Google Places rating quality score.
        Google Places ratings are in [1.0, 5.0].
        Maps to [0.0, 1.0] via (rating - 1) / 4.
        Returns 0.5 (neutral) when rating is missing or zero.
        """
        r = attraction.rating
        if not r or r <= 0.0:
            return 0.5
        return max(0.0, min(1.0, (r - 1.0) / 4.0))

    @staticmethod
    def _score_outdoor_preference(
        attraction: AttractionRecord,
        t_cur: time,
        soft: SoftConstraints,
    ) -> float:
        """
        SC_o: Outdoor preference match.
        Implements the exact lookup table from 07-simplified-model.md § SC_o.

        is_outdoor=TRUE,  pace relaxed/moderate → 0.8
        is_outdoor=TRUE,  pace packed           → 0.5
        is_outdoor=FALSE, pace relaxed + avoid_crowds=TRUE  → 0.6
        is_outdoor=FALSE, pace relaxed + avoid_crowds=FALSE → 0.7
        is_outdoor=FALSE, pace moderate/packed              → 0.9
        """
        pace = (soft.pace_preference or "moderate").lower()
        if attraction.is_outdoor:
            return 0.5 if pace == "packed" else 0.8
        # Indoor
        if pace == "relaxed":
            return 0.6 if soft.avoid_crowds else 0.7
        return 0.9  # moderate or packed + indoor