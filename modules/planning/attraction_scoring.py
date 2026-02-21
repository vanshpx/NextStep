"""
modules/planning/attraction_scoring.py
----------------------------------------
FTRM-based attraction scoring for the Route Planner's daily planning loop.

Replaces previous placeholder scoring with the full FTRM satisfaction chain:
  Eq (1)  : HC_pti = Π_m hcm_pti
  Eq (2)  : SC_pti = Σ_v Wv × scv_pti   (sum aggregation, recommended)
  Eq (4)  : S_pti  = HC_pti × SC_pti
  Eq (12) : η_ij   = S_pti / Dij         (used as the selection score)

Hard constraints encoded per attraction (via constraint_registry):
  hc1: opening hours gate
  hc2: time-budget feasibility     (elapsed + Dij + STi ≤ Tmax)
  hc3: wheelchair accessibility    (if traveler requires it)
  hc4: age restriction             (youngest traveler ≥ min_age)
  hc5: permit/ticket availability
  hc6: group size                  (min_group_size ≤ group_size ≤ max_group_size)
  hc7: seasonal closure            (trip month ∈ seasonal_open_months)
  hc8: minimum visit duration      (remaining ≥ Dij + min_visit_duration_minutes)

Soft constraints encoded per attraction (scored here):
  sc1 (w=0.25): optimal visit window   — is t_cur within optimal_visit_time? (S_opt,i)
  sc2 (w=0.20): remaining-time eff.    — (Tmax - elapsed - Dij - STi) / Tmax  (S_left,i)
  sc3 (w=0.30): category interest match — attraction.category ∈ user.interests
  sc4 (w=0.15): time-of-day preference — preferred_time_of_day aligns with visit window
  sc5 (w=0.10): crowd + energy score   — avoid_crowds, intensity_level, pace_preference

Weights sum to 1.0. Override via sc_weights parameter.
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


# Default SC weights for 5 soft dimensions (must sum to 1.0)
_DEFAULT_SC_WEIGHTS = [0.25, 0.20, 0.30, 0.15, 0.10]


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
        trip_month: int = 0,
        group_size: int = 1,
        traveler_ages: list[int] | None = None,
    ):
        self.distance_tool  = distance_tool or DistanceTool()
        self.time_tool      = time_tool     or TimeTool()
        self.sc_method      = sc_method
        self.sc_weights     = sc_weights or _DEFAULT_SC_WEIGHTS
        self.Tmax_minutes   = Tmax_minutes
        self.soft           = constraints.soft if constraints else SoftConstraints()
        self.hard           = constraints.hard if constraints else None
        self.trip_month     = trip_month
        self.group_size     = group_size
        self.traveler_ages  = traveler_ages or []

    # ── Public ────────────────────────────────────────────────────────────────

    def score_all(
        self,
        candidates: list[AttractionRecord],
        p_cur_lat: float,
        p_cur_lon: float,
        t_cur: time,
        end_time: time,
        is_arrival_or_departure_day: bool = False,
    ) -> list[AttractionScore]:
        """
        Score all candidate attractions; return sorted descending by η_ij (Eq 12).
        Infeasible attractions (feasible=False) are placed at end.

        Args:
            is_arrival_or_departure_day: True → apply heavy_travel_penalty to
                high-intensity attractions (SC energy management).
        """
        elapsed_minutes = self.time_tool.minutes_until(t_cur, end_time)
        # elapsed = how much day has been used = Tmax - remaining
        used_minutes = max(0.0, self.Tmax_minutes - elapsed_minutes)

        scores = [
            self._score_one(
                a, p_cur_lat, p_cur_lon, t_cur,
                used_minutes, elapsed_minutes,
                is_arrival_or_departure_day,
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
        is_arrival_or_departure_day: bool = False,
    ) -> AttractionScore:
        """Full FTRM scoring pipeline for one attraction."""

        # Travel time Dij [minutes]
        dist_raw = self.distance_tool.calculate(
            p_cur_lat, p_cur_lon,
            attraction.location_lat, attraction.location_lon,
        )
        Dij = self.time_tool.estimate_travel_time(dist_raw)

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
            "traveler_ages":       self.traveler_ages,
            "permit_available":    True,
            "group_size":          self.group_size,
            "trip_month":          self.trip_month,
        }
        poi_data = {
            "opening_hours":             attraction.opening_hours,
            "visit_duration_minutes":    attraction.visit_duration_minutes,
            "min_visit_duration_minutes": attraction.min_visit_duration_minutes,
            "wheelchair_accessible":     attraction.wheelchair_accessible,
            "min_age":                   attraction.min_age,
            "ticket_required":           attraction.ticket_required,
            "min_group_size":            attraction.min_group_size,
            "max_group_size":            attraction.max_group_size,
            "seasonal_open_months":      attraction.seasonal_open_months,
            "Dij_minutes":               Dij,
        }
        hard_results = evaluate_hc("attraction", poi_data, ctx)
        HC = compute_HC(hard_results)    # Eq 1

        # ── Soft Constraints (Eq 2) ───────────────────────────────────────────
        sc1 = self._score_optimal_window(attraction, t_cur)
        # sc2: remaining-time efficiency (S_left,i equivalent) ∈ [0,1]
        remaining_after = remaining_minutes - total_needed
        sc2 = max(0.0, remaining_after / self.Tmax_minutes) if self.Tmax_minutes > 0 else 0.0
        # sc3: category / interest alignment ∈ {0.0, 0.5, 1.0}
        sc3 = self._score_interest_match(attraction, self.soft)
        # sc4: time-of-day preference alignment ∈ {0.0, 0.5, 1.0}
        sc4 = self._score_time_of_day_preference(attraction, t_cur, self.soft)
        # sc5: crowd avoidance + energy management ∈ [0.0, 1.0]
        sc5 = self._score_crowd_energy(
            attraction, t_cur, self.soft, is_arrival_or_departure_day
        )

        SC = compute_SC([sc1, sc2, sc3, sc4, sc5], self.sc_weights, self.sc_method)  # Eq 2

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
    def _score_optimal_window(attraction: AttractionRecord, t_cur: time) -> float:
        """
        sc1: Soft score for optimal visit time (S_opt,i equivalent).
        Returns 1.0 if in optimal window, 0.5 if no window info, 0.0 if outside.
        """
        window = attraction.optimal_visit_time
        if not window or "-" not in window:
            return 0.5   # no data → neutral
        parts = window.split("-")
        if len(parts) != 2:
            return 0.5
        in_window = TimeTool.is_within_window(t_cur, parts[0].strip(), parts[1].strip())
        return 1.0 if in_window else 0.0

    @staticmethod
    def _score_interest_match(
        attraction: AttractionRecord,
        soft: SoftConstraints,
    ) -> float:
        """
        sc3: Interest / category alignment.
        1.0 — attraction.category is in user interests list
        0.5 — no interests defined (neutral)
        0.2 — category not in interests (de-prioritized but not gated)
        """
        if not soft.interests:
            return 0.5  # no preference data → neutral
        cat = attraction.category.lower()
        if any(cat in interest.lower() or interest.lower() in cat
               for interest in soft.interests):
            return 1.0
        return 0.2   # category not in interests → de-prioritize

    @staticmethod
    def _score_time_of_day_preference(
        attraction: AttractionRecord,
        t_cur: time,
        soft: SoftConstraints,
    ) -> float:
        """
        sc4: User preferred_time_of_day alignment.

        Mapping:
          "morning"   → bonus if t_cur 06:00–12:00
          "afternoon" → bonus if t_cur 12:00–17:00
          "evening"   → bonus if t_cur 17:00–21:00
          ""          → neutral 0.5

        outdoor attractions get a time-of-day bonus regardless of preference:
          morning light → full bonus; afternoon → slight penalty (heat/crowds).
        """
        pref = soft.preferred_time_of_day.lower() if soft.preferred_time_of_day else ""
        hour = t_cur.hour

        if not pref:
            # No explicit preference: reward outdoor visits in morning
            if attraction.is_outdoor and hour < 11:
                return 0.8
            return 0.5

        if pref == "morning" and 6 <= hour < 12:
            return 1.0
        if pref == "afternoon" and 12 <= hour < 17:
            return 1.0
        if pref == "evening" and 17 <= hour < 21:
            return 1.0

        # Opposite time-of-day → lower score but not zero
        return 0.2

    @staticmethod
    def _score_crowd_energy(
        attraction: AttractionRecord,
        t_cur: time,
        soft: SoftConstraints,
        is_arrival_or_departure_day: bool,
    ) -> float:
        """
        sc5: Crowd avoidance + energy management composite score.

        Crowd avoidance (avoid_crowds=True):
          outdoor attractions mid-day (10:00–15:00) → penalised (0.3)
          outdoor attractions early morning or late afternoon → rewarded (1.0)
          indoor attractions → not crowd-sensitive (0.7)

        Energy management (heavy_travel_penalty=True):
          high-intensity attractions on arrival/departure days → penalised (0.1)
          low/medium intensity always → no penalty (1.0)

        Pace preference:
          "relaxed"  → prefer low intensity (high → penalised)
          "packed"   → all intensities ok
          "moderate" → neutral
        """
        score = 1.0

        # Crowd avoidance
        if soft.avoid_crowds:
            hour = t_cur.hour
            if attraction.is_outdoor and 10 <= hour < 15:
                score = min(score, 0.3)   # peak crowd time outdoors
            elif attraction.is_outdoor:
                score = min(score, 1.0)   # rewarded — off-peak outdoor
            else:
                score = min(score, 0.7)   # indoor: mild crowd penalty

        # Energy / intensity management
        intensity = attraction.intensity_level.lower()
        if soft.heavy_travel_penalty and is_arrival_or_departure_day:
            if intensity == "high":
                score = min(score, 0.1)   # strenuous + travel day = bad
            elif intensity == "medium":
                score = min(score, 0.5)

        # Pace preference
        if soft.pace_preference == "relaxed" and intensity == "high":
            score = min(score, 0.4)
        elif soft.pace_preference == "packed":
            pass   # no penalty for any intensity in packed mode

        return max(score, 0.0)
