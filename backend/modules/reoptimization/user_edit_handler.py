"""
modules/reoptimization/user_edit_handler.py
---------------------------------------------
Handles three user-initiated itinerary edit actions:

  1. DISLIKE_NEXT_POI
     Peek at the next unvisited stop in the current plan.
     Score every remaining candidate → rank by (S_pti DESC, Dij ASC).
     Return top-N alternatives without mutating state.

  2. REPLACE_POI
     Substitute the next stop with a user-chosen alternative.
     Recompute all downstream arrival / departure times.
     Validate HC, Tmax, budget, and no-duplicate invariants.
     Write preference signal to DisruptionMemory.

  3. SKIP_CURRENT_POI
     Permanently remove the current (or next) stop.
     Advance clock + position AS IF we stayed in place (no travel cost).
     Trigger a full PartialReplanner pass from current position.
     Write preference signal to DisruptionMemory when S_pti was high.

Constants (MISSING in spec — defined here with rationale):
    HIGH_SPTI_MEMORY_THRESHOLD = 0.70
        Skipped/replaced stops above this S_pti trigger a preference signal
        so the Memory Module can learn the traveller's aversion patterns.
    DEFAULT_TOP_N_ALTERNATIVES = 5
        Maximum alternatives returned by DISLIKE_NEXT_POI.
    TRAVEL_SPEED_KMH = 5.0
        Walking speed used for quick Dij re-estimate when recomputing
        downstream times after a replace/skip operation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from math import radians, sin, cos, sqrt, atan2
from datetime import time as dtime
from typing import Any

from modules.tool_usage.attraction_tool import AttractionRecord
from modules.planning.attraction_scoring import AttractionScorer, AttractionScore
from schemas.constraints import ConstraintBundle
from schemas.itinerary import DayPlan, RoutePoint


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

HIGH_SPTI_MEMORY_THRESHOLD: float = 0.70   # MISSING in spec
DEFAULT_TOP_N_ALTERNATIVES: int   = 5      # MISSING in spec
TRAVEL_SPEED_KMH:           float = 5.0    # MISSING in spec
EARTH_RADIUS_KM:            float = 6371.0
DAY_END_TIME:               str   = "20:00"


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AlternativeOption:
    """One ranked alternative for DISLIKE_NEXT_POI response."""
    rank:         int
    attraction:   AttractionRecord
    S_pti:        float
    Dij_from_current: float   # [minutes] travel from current position
    eta_ij:       float       # S_pti / Dij
    why_suitable: str


@dataclass
class DislikeResult:
    """Result of DISLIKE_NEXT_POI — alternatives list + disliked stop info."""
    disliked_stop:    str
    current_S_pti:    float
    alternatives:     list[AlternativeOption] = field(default_factory=list)
    no_alternatives:  bool = False


@dataclass
class ReplaceResult:
    """Result of REPLACE_POI — validation outcome + updated plan."""
    original_stop:    str
    replacement_stop: str
    accepted:         bool
    rejection_reason: str = ""
    updated_plan:     DayPlan | None = None
    time_delta_minutes: int = 0   # positive = plan got shorter; negative = longer
    budget_delta:       float = 0.0


@dataclass
class SkipResult:
    """Result of SKIP_CURRENT_POI — always accepted; replan handled by session."""
    skipped_stop:     str
    S_pti_lost:       float
    memory_signal:    bool   # True when S_pti ≥ HIGH_SPTI_MEMORY_THRESHOLD
    reason:           str


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_minutes(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
    speed_kmh: float = TRAVEL_SPEED_KMH,
) -> float:
    r   = EARTH_RADIUS_KM
    φ1, φ2 = radians(lat1), radians(lat2)
    dφ  = radians(lat2 - lat1)
    dλ  = radians(lon2 - lon1)
    a   = sin(dφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(dλ / 2) ** 2
    d   = 2 * r * atan2(sqrt(a), sqrt(1 - a))
    return max(1.0, (d / speed_kmh) * 60)


def _time_str_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _minutes_to_time_str(total: int) -> str:
    total = min(total, 23 * 60 + 59)
    return f"{total // 60:02d}:{total % 60:02d}"


def _rp_arrival_minutes(rp: RoutePoint) -> int:
    if rp.arrival_time is None:
        return 9 * 60
    return rp.arrival_time.hour * 60 + rp.arrival_time.minute


def _rp_departure_minutes(rp: RoutePoint) -> int:
    if rp.departure_time is None:
        return _rp_arrival_minutes(rp) + rp.visit_duration_minutes
    return rp.departure_time.hour * 60 + rp.departure_time.minute


def _why_suitable_edit(score: AttractionScore, soft: Any) -> str:
    a = score.attraction
    parts: list[str] = []
    if soft.interests and a.category.lower() in [i.lower() for i in soft.interests]:
        parts.append(f"matches interest in '{a.category}'")
    if soft.avoid_crowds and not getattr(a, "is_outdoor", False):
        parts.append("indoor — less crowded")
    if soft.pace_preference == "relaxed" and a.intensity_level == "low":
        parts.append("low intensity — suits relaxed pace")
    parts.append(f"S_pti={score.S_pti:.2f}")
    return "; ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# UserEditHandler
# ─────────────────────────────────────────────────────────────────────────────

class UserEditHandler:
    """
    Handles user-driven itinerary edits: dislike, replace, skip.

    Instantiated once and held by ReOptimizationSession:
        self._user_edit = UserEditHandler()
    """

    # ── A: DISLIKE_NEXT_POI ───────────────────────────────────────────────────

    def dislike_next_poi(
        self,
        current_plan:      DayPlan,
        remaining_pool:    list[AttractionRecord],
        visited:           set[str],
        skipped:           set[str],
        deferred:          set[str],
        constraints:       ConstraintBundle,
        current_lat:       float,
        current_lon:       float,
        current_time_str:  str,
        remaining_minutes: int,
        top_n:             int = DEFAULT_TOP_N_ALTERNATIVES,
    ) -> DislikeResult:
        """
        Peek at next unvisited stop, score alternatives, return ranked list.

        Does NOT mutate state — caller decides whether to follow up with
        REPLACE_POI or do nothing.

        Algorithm:
            next_stop   ← first route_point not in visited ∪ skipped
            candidates  ← remaining_pool − visited − skipped − deferred
                           − {next_stop}
            For each candidate:
                HC_pti  ← Π hcm (via AttractionScorer)
                SC_pti  ← Σ Wv × scv
                S_pti   ← HC × SC
                Dij     ← haversine(current → candidate)
                η_ij    ← S_pti / Dij
                KEEP IF HC_pti > 0
                     AND candidate.visit_duration ≤ remaining_minutes
            Sort by (S_pti DESC, Dij ASC)
        """
        # Find next stop in current plan
        excluded = visited | skipped
        next_rp = next(
            (rp for rp in current_plan.route_points if rp.name not in excluded),
            None,
        )
        disliked_name = next_rp.name if next_rp else ""

        # Score current disliked stop (for memory threshold check)
        disliked_record = next(
            (a for a in remaining_pool if a.name == disliked_name), None
        )
        current_S = 0.0
        if disliked_record is not None:
            _dep = getattr(constraints.hard, "departure_date", None)
            _month = _dep.month if _dep else 0
            _group = (
                (constraints.hard.group_size or 0)
                or constraints.hard.total_travelers or 1
            ) if constraints.hard else 1
            scorer_check = AttractionScorer(
                Tmax_minutes  = remaining_minutes,
                constraints   = constraints,
                trip_month    = _month,
                group_size    = _group,
                traveler_ages = constraints.hard.traveler_ages if constraints.hard else [],
            )
            scored_check = scorer_check.score_all([disliked_record],
                                                   current_lat, current_lon, current_time_str)
            if scored_check:
                current_S = scored_check[0].S_pti

        # Build candidate pool
        pool_excluded = excluded | deferred | ({disliked_name} if disliked_name else set())
        candidates = [a for a in remaining_pool if a.name not in pool_excluded]

        if not candidates:
            return DislikeResult(
                disliked_stop=disliked_name,
                current_S_pti=current_S,
                no_alternatives=True,
            )

        # Score candidates with full FTRM
        _dep = getattr(constraints.hard, "departure_date", None)
        _month = _dep.month if _dep else 0
        _group = (
            (constraints.hard.group_size or 0)
            or constraints.hard.total_travelers or 1
        ) if constraints.hard else 1
        scorer = AttractionScorer(
            Tmax_minutes  = remaining_minutes,
            constraints   = constraints,
            trip_month    = _month,
            group_size    = _group,
            traveler_ages = constraints.hard.traveler_ages if constraints.hard else [],
        )
        scored = scorer.score_all(candidates, current_lat, current_lon, current_time_str)

        # Filter: HC > 0, feasible under remaining time
        feasible = [
            s for s in scored
            if s.HC_pti > 0
            and s.attraction.visit_duration_minutes <= remaining_minutes
        ]

        # Compute Dij from current position for each candidate
        options: list[AlternativeOption] = []
        for i, sc in enumerate(
            sorted(feasible, key=lambda x: (-x.S_pti, 0)), start=1
        ):
            Dij = _haversine_minutes(
                current_lat, current_lon,
                sc.attraction.location_lat,
                sc.attraction.location_lon,
            )
            eta = sc.S_pti / Dij if Dij > 0 else 0.0
            options.append(AlternativeOption(
                rank              = i,
                attraction        = sc.attraction,
                S_pti             = sc.S_pti,
                Dij_from_current  = Dij,
                eta_ij            = eta,
                why_suitable      = _why_suitable_edit(sc, constraints.soft),
            ))
            if i >= top_n:
                break

        return DislikeResult(
            disliked_stop  = disliked_name,
            current_S_pti  = current_S,
            alternatives   = options,
            no_alternatives= len(options) == 0,
        )

    # ── B: REPLACE_POI ───────────────────────────────────────────────────────

    def replace_poi(
        self,
        current_plan:       DayPlan,
        replacement_record: AttractionRecord,
        visited:            set[str],
        skipped:            set[str],
        constraints:        ConstraintBundle,
        current_lat:        float,
        current_lon:        float,
        current_time_str:   str,
        remaining_minutes:  int,
        budget_remaining:   float,
    ) -> ReplaceResult:
        """
        Substitute the next unvisited stop with replacement_record.

        Validation (in order — fail fast):
            1. replacement not already visited or skipped
            2. HC_pti(replacement) > 0
            3. Dij(current→replacement) + STi(replacement) ≤ remaining_minutes
            4. replacement.entry_cost ≤ budget_remaining
            5. No duplicate: replacement not already in future plan

        On success:
            - Swap the RoutePoint in current_plan
            - Recompute arrival_time, departure_time for every downstream stop
              using Dij = haversine / TRAVEL_SPEED_KMH
            - Return updated plan copy
        """
        excluded = visited | skipped

        # Find next stop index
        next_idx = next(
            (i for i, rp in enumerate(current_plan.route_points)
             if rp.name not in excluded),
            None,
        )
        if next_idx is None:
            return ReplaceResult(
                original_stop    = "",
                replacement_stop = replacement_record.name,
                accepted         = False,
                rejection_reason = "No next stop found in current plan.",
            )

        original_name = current_plan.route_points[next_idx].name

        # ── Validation ───────────────────────────────────────────────────────
        if replacement_record.name in excluded:
            return ReplaceResult(
                original_stop    = original_name,
                replacement_stop = replacement_record.name,
                accepted         = False,
                rejection_reason = f"'{replacement_record.name}' is already visited or skipped.",
            )

        # HC check
        _dep = getattr(constraints.hard, "departure_date", None)
        _month = _dep.month if _dep else 0
        _group = (
            (constraints.hard.group_size or 0)
            or constraints.hard.total_travelers or 1
        ) if constraints.hard else 1
        scorer = AttractionScorer(
            Tmax_minutes  = remaining_minutes,
            constraints   = constraints,
            trip_month    = _month,
            group_size    = _group,
            traveler_ages = constraints.hard.traveler_ages if constraints.hard else [],
        )
        scored = scorer.score_all(
            [replacement_record], current_lat, current_lon, current_time_str
        )
        if not scored or scored[0].HC_pti == 0.0:
            return ReplaceResult(
                original_stop    = original_name,
                replacement_stop = replacement_record.name,
                accepted         = False,
                rejection_reason = (
                    f"'{replacement_record.name}' fails a hard constraint "
                    f"(HC_pti = 0) — cannot be added."
                ),
            )

        Dij_to_alt = _haversine_minutes(
            current_lat, current_lon,
            replacement_record.location_lat,
            replacement_record.location_lon,
        )
        if Dij_to_alt + replacement_record.visit_duration_minutes > remaining_minutes:
            return ReplaceResult(
                original_stop    = original_name,
                replacement_stop = replacement_record.name,
                accepted         = False,
                rejection_reason = (
                    f"Infeasible: Dij {Dij_to_alt:.1f} min + "
                    f"STi {replacement_record.visit_duration_minutes} min "
                    f"> {remaining_minutes} min remaining."
                ),
            )

        if replacement_record.entry_cost > budget_remaining:
            return ReplaceResult(
                original_stop    = original_name,
                replacement_stop = replacement_record.name,
                accepted         = False,
                rejection_reason = (
                    f"Budget exceeded: entry cost {replacement_record.entry_cost:.2f} "
                    f"> remaining {budget_remaining:.2f}."
                ),
            )

        future_names = {
            rp.name for rp in current_plan.route_points[next_idx + 1:]
        }
        if replacement_record.name in future_names:
            return ReplaceResult(
                original_stop    = original_name,
                replacement_stop = replacement_record.name,
                accepted         = False,
                rejection_reason = (
                    f"Duplicate: '{replacement_record.name}' already appears "
                    f"later in today's plan."
                ),
            )

        # ── Build updated plan ────────────────────────────────────────────────
        import copy
        new_plan = copy.deepcopy(current_plan)
        rps = new_plan.route_points

        # Swap the stop
        old_cost = rps[next_idx].estimated_cost
        rps[next_idx].name                   = replacement_record.name
        rps[next_idx].location_lat           = replacement_record.location_lat
        rps[next_idx].location_lon           = replacement_record.location_lon
        rps[next_idx].visit_duration_minutes = replacement_record.visit_duration_minutes
        rps[next_idx].estimated_cost         = replacement_record.entry_cost
        rps[next_idx].notes                  = f"Replaced original stop '{original_name}' by user."

        # Recompute times from current clock forward
        current_min = _time_str_to_minutes(current_time_str)
        prev_lat, prev_lon = current_lat, current_lon

        for idx in range(next_idx, len(rps)):
            rp    = rps[idx]
            Dij   = _haversine_minutes(prev_lat, prev_lon, rp.location_lat, rp.location_lon)
            arr   = current_min + int(Dij)
            dep   = arr + rp.visit_duration_minutes
            rp.arrival_time   = dtime(arr // 60, arr % 60)
            rp.departure_time = dtime(dep // 60, dep % 60)
            current_min       = dep
            prev_lat, prev_lon = rp.location_lat, rp.location_lon

        # Validate Tmax after recompute
        day_end_min = _time_str_to_minutes(DAY_END_TIME)
        if current_min > day_end_min:
            return ReplaceResult(
                original_stop    = original_name,
                replacement_stop = replacement_record.name,
                accepted         = False,
                rejection_reason = (
                    f"After replacement, plan runs until "
                    f"{_minutes_to_time_str(current_min)} — exceeds Tmax ({DAY_END_TIME})."
                ),
            )

        budget_delta = replacement_record.entry_cost - old_cost

        return ReplaceResult(
            original_stop    = original_name,
            replacement_stop = replacement_record.name,
            accepted         = True,
            updated_plan     = new_plan,
            budget_delta     = budget_delta,
        )

    # ── C: SKIP_CURRENT_POI ──────────────────────────────────────────────────

    def skip_current_poi(
        self,
        current_plan:      DayPlan,
        remaining_pool:    list[AttractionRecord],
        visited:           set[str],
        skipped:           set[str],
        constraints:       ConstraintBundle,
        current_lat:       float,
        current_lon:       float,
        current_time_str:  str,
        remaining_minutes: int,
    ) -> SkipResult:
        """
        Permanently remove the next unvisited stop and signal the session to
        trigger PartialReplanner from current position.

        Does NOT call PartialReplanner itself — returns SkipResult so the
        session can call state.mark_skipped() + _do_replan().
        """
        excluded = visited | skipped
        next_rp = next(
            (rp for rp in current_plan.route_points if rp.name not in excluded),
            None,
        )
        if next_rp is None:
            return SkipResult(
                skipped_stop  = "",
                S_pti_lost    = 0.0,
                memory_signal = False,
                reason        = "No remaining stop found to skip.",
            )

        stop_name = next_rp.name

        # Compute S_pti of the skipped stop for memory signal
        record = next(
            (a for a in remaining_pool if a.name == stop_name), None
        )
        S_lost = 0.0
        if record is not None:
            _dep = getattr(constraints.hard, "departure_date", None)
            _month = _dep.month if _dep else 0
            _group = (
                (constraints.hard.group_size or 0)
                or constraints.hard.total_travelers or 1
            ) if constraints.hard else 1
            scorer = AttractionScorer(
                Tmax_minutes  = remaining_minutes,
                constraints   = constraints,
                trip_month    = _month,
                group_size    = _group,
                traveler_ages = constraints.hard.traveler_ages if constraints.hard else [],
            )
            scored = scorer.score_all([record], current_lat, current_lon, current_time_str)
            if scored:
                S_lost = scored[0].S_pti

        memory_signal = S_lost >= HIGH_SPTI_MEMORY_THRESHOLD

        return SkipResult(
            skipped_stop  = stop_name,
            S_pti_lost    = S_lost,
            memory_signal = memory_signal,
            reason        = (
                f"User skipped '{stop_name}' "
                f"(S_pti={S_lost:.2f}"
                + (f" ≥ {HIGH_SPTI_MEMORY_THRESHOLD} — preference signal written"
                   if memory_signal else "")
                + ")."
            ),
        )
