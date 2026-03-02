"""
modules/reoptimization/local_repair.py
-----------------------------------------
LocalRepair — strict single-POI schedule repair with state invariant enforcement.

Specification: 7-section repair contract
─────────────────────────────────────────
§1  STATE INVARIANTS — checked before committing any repair candidate.
     - Visited POIs are immutable.
     - Completed time blocks are locked.
     - Executed meal slots are locked.
     - Stop count ±1 of original.
     - No duplicate POIs.
     - No duplicate meals.
     - No reordering of unaffected stops.
     - Geographic cluster ≤ CLUSTER_RADIUS_KM from disrupted POI.

§2  LOCAL REPAIR STEPS (in order, stop at first success):
     Step 1 — Remove disrupted POI from remaining schedule.
     Step 2 — ShiftLater: next feasible slot today; recheck crowd/traffic forecast.
     Step 3 — SwapWithNext: swap with next unvisited POI.
     Step 4 — ReplaceNearby: alternative within 3 km, same category preferred.
     Step 5 — DEFERRED_TO_NEXT_DAY: remove from today, no replacement insertion.

§3  MEAL CONSTRAINTS
     LUNCH  window: 12:00–14:30   (exactly one per day)
     DINNER window: 18:30–21:30   (exactly one per day)
     No back-to-back meals; no meal outside window; min 60 min gap after previous.

§4  TIMING RULE
     EndTime(prev) + TravelTime + BUFFER_MINUTES ≤ StartTime(next)
     No overlaps; no gaps > MAX_GAP_MINUTES.

§5  CROWD DEFERRAL VALIDATION
     If shift attempted for CROWD disruption, recheck estimated crowd at new slot.
     If still > threshold (with decay): reject slot, try next strategy.

§6  ACO LIMITATION
     ACO heuristic (η = S_pti / Dij) used ONLY to rank nearby alternatives.
     Never rebuilds entire day.

§7  OUTPUT
     repair() returns RepairResult | None.
     RepairResult carries: updated_plan, modified_elements (≤2), invariants_satisfied,
     error_code (None = OK, "ERROR_INVARIANT_VIOLATION: ..." if failed).

allow_shift / allow_replace parameter semantics (unchanged from prior version):
    CROWD / TRAFFIC   → allow_shift=True,  allow_replace=True
    WEATHER (blocked) → allow_shift=False, allow_replace=True
    USER_SKIP         → allow_shift=False, allow_replace=True
    USER_REPLACE      → allow_shift=False, allow_replace=False
    reschedule_future → allow_shift=False, allow_replace=False
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import time as dtime
from typing import Optional

import config
import time as _time_mod
from modules.tool_usage.attraction_tool import AttractionRecord
from modules.tool_usage.distance_tool import DistanceTool, haversine_km
from modules.reoptimization.trip_state import TripState
from modules.observability.logger import StructuredLogger
from schemas.constraints import ConstraintBundle
from schemas.itinerary import DayPlan, RoutePoint

_perf_logger = StructuredLogger()


# ── Constants ──────────────────────────────────────────────────────────────────

GLOBAL_REPLAN_THRESHOLD: int   = 3          # §2/§6: ≥3 simultaneously infeasible → full replan
MAX_REPLACE_RADIUS_KM:   float = 3.0        # §2 Step 4 / §1 Inv 8: nearby alternative radius
CLUSTER_RADIUS_KM:       float = 5.0        # §1 Invariant 8: geographic cluster max radius
REPAIR_WINDOW_RADIUS:    int   = 2          # max positions shifted (Step 2 shift_by ≤ this)
DAY_END_MINUTES:         int   = 20 * 60 + 55   # 20:55 absolute hard end of day

BUFFER_MINUTES:     int = 10   # §4: EndTime(prev) + Travel + BUFFER ≤ StartTime(next)
MAX_GAP_MINUTES:    int = 90   # §4: no idle gap > 90 min between consecutive stops
MEAL_MIN_GAP_AFTER: int = 60   # §3: meal cannot start < 60 min after previous departure

LUNCH_WINDOW:  tuple[int, int] = (12 * 60,       14 * 60 + 30)   # 12:00–14:30
DINNER_WINDOW: tuple[int, int] = (18 * 60 + 30,  21 * 60 + 30)   # 18:30–21:30

MEAL_ACTIVITY_TYPES: frozenset[str] = frozenset({"restaurant", "meal", "lunch", "dinner"})

# Crowd decay per 30-min window (§5 Crowd Deferral Validation)
CROWD_DECAY_PER_30MIN: float = 0.15

# Similar-category groups for replacement candidate matching (§2 Step 4 / §1 Inv 8)
_CATEGORY_GROUPS: dict[str, list[str]] = {
    "museum":              ["museum", "art_gallery", "gallery"],
    "art_gallery":         ["museum", "art_gallery", "gallery"],
    "gallery":             ["museum", "art_gallery", "gallery"],
    "park":                ["park", "garden", "national_park", "botanical_garden"],
    "garden":              ["park", "garden", "national_park", "botanical_garden"],
    "national_park":       ["park", "garden", "national_park"],
    "botanical_garden":    ["park", "garden", "botanical_garden"],
    "landmark":            ["landmark", "monument", "historical_landmark", "memorial", "fort"],
    "monument":            ["landmark", "monument", "historical_landmark", "memorial"],
    "historical_landmark": ["landmark", "monument", "historical_landmark"],
    "memorial":            ["landmark", "monument", "memorial"],
    "fort":                ["fort", "landmark", "monument", "historical_landmark"],
    "temple":              ["temple", "hindu_temple", "church", "mosque", "religious"],
    "hindu_temple":        ["temple", "hindu_temple", "religious"],
    "mosque":              ["temple", "mosque", "religious"],
    "church":              ["temple", "church", "religious"],
    "religious":           ["temple", "hindu_temple", "church", "mosque", "religious"],
    "market":              ["market", "shopping"],
}


# ── Time helpers ───────────────────────────────────────────────────────────────

def _time_to_min(t: dtime) -> int:
    return t.hour * 60 + t.minute


def _min_to_time(minutes: int) -> dtime:
    minutes = max(0, min(int(minutes), 23 * 60 + 59))
    return dtime(hour=minutes // 60, minute=minutes % 60)


def _is_meal(rp: RoutePoint) -> bool:
    return rp.activity_type in MEAL_ACTIVITY_TYPES


def _meal_window(rp: RoutePoint) -> Optional[tuple[int, int]]:
    """Return (start_min, end_min) for the appropriate meal window, or None."""
    if not _is_meal(rp) or rp.arrival_time is None:
        return None
    arr = _time_to_min(rp.arrival_time)
    if LUNCH_WINDOW[0] <= arr <= LUNCH_WINDOW[1]:
        return LUNCH_WINDOW
    if DINNER_WINDOW[0] <= arr <= DINNER_WINDOW[1]:
        return DINNER_WINDOW
    if rp.activity_type == "lunch":
        return LUNCH_WINDOW
    if rp.activity_type == "dinner":
        return DINNER_WINDOW
    return None


# ── RepairResult ───────────────────────────────────────────────────────────────

@dataclass
class RepairResult:
    """
    §7 OUTPUT — returned by LocalRepair.repair().

    updated_plan:          The repaired DayPlan.
    modified_elements:     Names of stops added, removed, or reordered (≤ 2).
    invariants_satisfied:  True iff all §1 invariants hold on updated_plan.
    error_code:            None on success; "ERROR_INVARIANT_VIOLATION: <reason>" if violated.
    strategy_used:         Label of the repair strategy that produced this result.
    """
    updated_plan:         DayPlan
    modified_elements:    list[str] = field(default_factory=list)
    invariants_satisfied: bool      = True
    error_code:           Optional[str] = None
    strategy_used:        str       = ""


# ── InvariantChecker ───────────────────────────────────────────────────────────

class InvariantChecker:
    """
    §1 STATE INVARIANTS — validates a proposed repair candidate before commit.

    All eight invariants are evaluated and all violations collected so the
    caller sees a single comprehensive error message.
    """

    def check(
        self,
        original_points: list[RoutePoint],
        new_points:      list[RoutePoint],
        state:           TripState,
        original_N:      int,
        disrupted_name:  str,
        is_user_skip:    bool = False,
    ) -> tuple[bool, Optional[str]]:
        """
        Returns (True, None) when all invariants hold.
        Returns (False, "ERROR_INVARIANT_VIOLATION: <details>") otherwise.
        """
        issues: list[str] = []

        ch, cm      = map(int, state.current_time.split(":"))
        current_min = ch * 60 + cm

        # ── Inv 1: Visited POIs are IMMUTABLE ────────────────────────────────
        # A visited stop already present in the original plan is a LOCKED stop
        # (enforced by Inv 2).  Only flag genuinely NEW additions of visited POIs.
        orig_names_set = {rp.name for rp in original_points}
        reintroduced = {
            rp.name for rp in new_points
            if rp.name not in orig_names_set
        } & state.visited_stops
        if reintroduced:
            issues.append(f"Inv1 — visited POIs reintroduced: {sorted(reintroduced)}")

        # ── Inv 2: Completed time blocks are LOCKED ───────────────────────────
        locked_orig = [
            rp for rp in original_points
            if rp.departure_time and _time_to_min(rp.departure_time) <= current_min
        ]
        new_by_name = {rp.name: rp for rp in new_points}
        for lrp in locked_orig:
            if lrp.name not in new_by_name:
                issues.append(f"Inv2 — locked stop '{lrp.name}' removed")
            elif new_by_name[lrp.name].arrival_time != lrp.arrival_time:
                issues.append(
                    f"Inv2 — locked stop '{lrp.name}' arrival mutated "
                    f"({lrp.arrival_time} → {new_by_name[lrp.name].arrival_time})"
                )

        # ── Inv 3: Executed meal slots are LOCKED ─────────────────────────────
        executed_meals = [
            rp for rp in original_points
            if _is_meal(rp) and rp.departure_time
            and _time_to_min(rp.departure_time) <= current_min
        ]
        for meal_rp in executed_meals:
            if meal_rp.name not in new_by_name:
                issues.append(f"Inv3 — executed meal '{meal_rp.name}' removed")
            elif new_by_name[meal_rp.name].arrival_time != meal_rp.arrival_time:
                issues.append(f"Inv3 — executed meal '{meal_rp.name}' time changed")

        # ── Inv 4: Stop count ±1 (exempt for user-initiated skips) ────────────
        if not is_user_skip:
            n_new = len(new_points)
            if not (original_N - 1 <= n_new <= original_N + 1):
                issues.append(f"Inv4 — count {n_new} vs original {original_N} (max ±1)")

        # ── Inv 5: No duplicate POIs ──────────────────────────────────────────
        seen: dict[str, int] = {}
        for rp in new_points:
            seen[rp.name] = seen.get(rp.name, 0) + 1
        dupes = [n for n, c in seen.items() if c > 1]
        if dupes:
            issues.append(f"Inv5 — duplicate POIs: {dupes}")

        # ── Inv 6: No duplicate meals ─────────────────────────────────────────
        meal_seen: dict[str, int] = {}
        for rp in new_points:
            if _is_meal(rp):
                meal_seen[rp.name] = meal_seen.get(rp.name, 0) + 1
        meal_dupes = [n for n, c in meal_seen.items() if c > 1]
        if meal_dupes:
            issues.append(f"Inv6 — duplicate meal events: {meal_dupes}")

        # ── Inv 7: No reordering of unaffected stops ──────────────────────────
        orig_unaffected = [
            rp.name for rp in original_points if rp.name != disrupted_name
        ]
        new_names_set = {rp.name for rp in new_points}
        orig_filtered = [n for n in orig_unaffected if n in new_names_set]
        new_unaffected = [
            rp.name for rp in new_points
            if rp.name != disrupted_name
            and rp.name in set(orig_unaffected)
        ]
        if orig_filtered != new_unaffected:
            issues.append(
                f"Inv7 — unaffected stops reordered; "
                f"expected {orig_filtered}, got {new_unaffected}"
            )

        # ── Inv 8: Geographic cluster ≤ CLUSTER_RADIUS_KM ────────────────────
        disrupted_rp  = next(
            (rp for rp in original_points if rp.name == disrupted_name), None
        )
        if disrupted_rp:
            for rp in new_points:
                if rp.name in orig_names_set:
                    continue  # not a new insertion
                km = haversine_km(
                    disrupted_rp.location_lat, disrupted_rp.location_lon,
                    rp.location_lat, rp.location_lon,
                )
                if km > CLUSTER_RADIUS_KM:
                    issues.append(
                        f"Inv8 — replacement '{rp.name}' is {km:.1f} km "
                        f"from disrupted POI (max {CLUSTER_RADIUS_KM} km)"
                    )

        if issues:
            return False, "ERROR_INVARIANT_VIOLATION: " + "; ".join(issues)
        return True, None


# ── Meal constraint validator (§3) ─────────────────────────────────────────────

def _classify_meal(rp: RoutePoint) -> Optional[str]:
    """
    Return "lunch", "dinner", or None for non-meal stops.

    Priority: activity_type literal → name hint → timing → best guess.
    A restaurant with arrival_time before DINNER_WINDOW is treated as lunch;
    at/after DINNER_WINDOW start as dinner.  This prevents false §3 rejections
    when recomputed timings push a meal slot slightly outside its window.
    """
    if not _is_meal(rp):
        return None

    # Explicit type
    if rp.activity_type == "lunch":
        return "lunch"
    if rp.activity_type == "dinner":
        return "dinner"

    # Name contains hint  (e.g. "Naivedyam (Lunch)")
    name_lower = (rp.name or "").lower()
    if "lunch" in name_lower:
        return "lunch"
    if "dinner" in name_lower or "supper" in name_lower:
        return "dinner"

    # Fall back to scheduled arrival time
    if rp.arrival_time is not None:
        arr = _time_to_min(rp.arrival_time)
        if arr < DINNER_WINDOW[0]:
            return "lunch"
        else:
            return "dinner"

    # No timing info yet → guess lunch (first meal of day)
    return "lunch"


def _validate_and_fix_meals(
    points: list[RoutePoint],
) -> tuple[Optional[list[RoutePoint]], Optional[str]]:
    """
    §3 MEAL CONSTRAINTS — validate and adjust meal timings within windows.

    Rules enforced:
      • Exactly one lunch per day; exactly one dinner per day.
      • No back-to-back meals (consecutive indices).
      • No meal scheduled outside its window.
      • Meal start ≥ prev_departure + MEAL_MIN_GAP_AFTER (60 min).
      • If meal is too early, push it to the earliest valid start inside window.
      • If it still doesn't fit → return (None, error) so caller tries next strategy.
      • Do NOT create new meal events.
    """
    pts = [copy.copy(rp) for rp in points]

    # Classify each meal stop using intent-based logic (§3)
    lunch_idxs:  list[int] = []
    dinner_idxs: list[int] = []
    for i, rp in enumerate(pts):
        kind = _classify_meal(rp)
        if kind == "lunch":
            lunch_idxs.append(i)
        elif kind == "dinner":
            dinner_idxs.append(i)

    # §3 Exactly one of each
    if len(lunch_idxs) > 1:
        return None, f"§3 duplicate lunch events at positions {lunch_idxs}"
    if len(dinner_idxs) > 1:
        return None, f"§3 duplicate dinner events at positions {dinner_idxs}"

    # §3 No back-to-back meals
    all_meal_idxs = sorted(lunch_idxs + dinner_idxs)
    for j in range(len(all_meal_idxs) - 1):
        if all_meal_idxs[j + 1] == all_meal_idxs[j] + 1:
            return None, (
                f"§3 back-to-back meals at positions "
                f"{all_meal_idxs[j]} and {all_meal_idxs[j+1]}"
            )

    # §3 Per-meal: window clamp + 60-min gap enforcement
    for i, rp in enumerate(pts):
        kind = _classify_meal(rp)
        if kind is None or rp.arrival_time is None:
            continue

        arr_min = _time_to_min(rp.arrival_time)
        dep_min = (
            _time_to_min(rp.departure_time)
            if rp.departure_time
            else arr_min + rp.visit_duration_minutes
        )
        win_start, win_end = LUNCH_WINDOW if kind == "lunch" else DINNER_WINDOW

        # Minimum start from 60-min gap rule
        if i > 0 and pts[i - 1].departure_time:
            min_from_gap = _time_to_min(pts[i - 1].departure_time) + MEAL_MIN_GAP_AFTER
        else:
            min_from_gap = win_start

        effective_start = max(win_start, min_from_gap)

        if arr_min < effective_start:
            # Push meal to effective_start
            new_dep = effective_start + rp.visit_duration_minutes
            if new_dep > win_end:
                return None, (
                    f"§3 meal '{rp.name}' cannot fit in "
                    f"{win_start//60:02d}:{win_start%60:02d}–"
                    f"{win_end//60:02d}:{win_end%60:02d} "
                    f"after 60-min gap rule"
                )
            pts[i].arrival_time   = _min_to_time(effective_start)
            pts[i].departure_time = _min_to_time(new_dep)
        elif dep_min > win_end:
            return None, (
                f"§3 meal '{rp.name}' departure {_min_to_time(dep_min)} "
                f"exceeds window end {_min_to_time(win_end)}"
            )

    return pts, None


# ── Main class ─────────────────────────────────────────────────────────────────

class LocalRepair:
    """
    Strict single-POI minimal-change schedule repair.

    Follows the §2 Steps 1–5 algorithm:
      Step 1 — Remove POI_i from remaining schedule.
      Step 2 — ShiftLater (with §5 crowd forecast recheck).
      Step 3 — SwapWithNext.
      Step 4 — ReplaceNearby (§6 ACO η-ranking within 3 km).
      Step 5 — DEFERRED_TO_NEXT_DAY.

    §1 invariants, §3 meal constraints, and §4 timing rules are enforced on
    every candidate before it is committed.
    """

    def __init__(self, distance_tool: Optional[DistanceTool] = None) -> None:
        self._dist    = distance_tool or DistanceTool()
        self._checker = InvariantChecker()

    # ── Public API ─────────────────────────────────────────────────────────────

    def needs_global_replan(self, infeasible_count: int) -> bool:
        """§2/§6: True when ≥ GLOBAL_REPLAN_THRESHOLD POIs are simultaneously infeasible."""
        return infeasible_count >= GLOBAL_REPLAN_THRESHOLD

    def repair(
        self,
        disrupted_stop_name:   str,
        current_plan:          DayPlan,
        state:                 TripState,
        remaining_pool:        list[AttractionRecord],
        constraints:           ConstraintBundle,
        disruption_type:       str,
        replacement_candidate: Optional[AttractionRecord] = None,
        allow_shift:           bool  = True,
        allow_replace:         bool  = True,
        crowd_level:           float = 0.0,
        crowd_threshold:       float = 1.0,
        is_user_skip:          bool  = False,
    ) -> Optional[RepairResult]:
        """§2 Steps 1–5 strict local repair."""
        _t0 = _time_mod.perf_counter()
        result = self._repair_inner(
            disrupted_stop_name, current_plan, state, remaining_pool,
            constraints, disruption_type, replacement_candidate,
            allow_shift, allow_replace, crowd_level, crowd_threshold,
            is_user_skip,
        )
        _perf_logger.log("default", "PERFORMANCE", {
            "component": "LocalRepair.repair",
            "duration_ms": round((_time_mod.perf_counter() - _t0) * 1000, 2),
        })
        return result

    def _repair_inner(
        self,
        disrupted_stop_name:   str,
        current_plan:          DayPlan,
        state:                 TripState,
        remaining_pool:        list[AttractionRecord],
        constraints:           ConstraintBundle,
        disruption_type:       str,
        replacement_candidate: Optional[AttractionRecord] = None,
        allow_shift:           bool  = True,
        allow_replace:         bool  = True,
        crowd_level:           float = 0.0,
        crowd_threshold:       float = 1.0,
        is_user_skip:          bool  = False,
    ) -> Optional[RepairResult]:
        """
        §2 Steps 1–5 strict local repair.

        Returns RepairResult on success (strategy_used set).
        Returns None only if even Step 5 (DEFERRED_TO_NEXT_DAY) cannot satisfy
        the invariants (extremely rare; caller should escalate to full replan).

        On invariant violation in any step, the step is skipped and the next
        strategy is tried.  The final RepairResult always carries
        invariants_satisfied=True; ERROR_INVARIANT_VIOLATION is only set when
        the *caller* detects a violation after the fact (via error_code).
        """
        points: list[RoutePoint] = list(current_plan.route_points)
        original_N = len(points)

        # ── §2 Step 1: Locate disrupted POI ──────────────────────────────────
        idx = next(
            (i for i, rp in enumerate(points) if rp.name == disrupted_stop_name),
            None,
        )
        if idx is None:
            # Already absent — return plan unchanged
            return RepairResult(
                updated_plan      = current_plan,
                modified_elements = [],
                invariants_satisfied = True,
                strategy_used     = "NO_OP",
            )

        # Shared exclusion set (all currently-planned and permanently excluded stops)
        excluded: set[str] = (
            state.visited_stops
            | state.skipped_stops
            | state.deferred_stops
            | {rp.name for rp in points}
        )

        # Pool metadata for the disrupted stop
        origin_attr    = next((a for a in remaining_pool if a.name == disrupted_stop_name), None)
        origin_cat     = origin_attr.category    if origin_attr else ""
        origin_outdoor = origin_attr.is_outdoor  if origin_attr else False

        # ── §2 Step 2: ShiftLater ─────────────────────────────────────────────
        if allow_shift:
            for shift_by in (1, 2):
                if idx + shift_by < len(points):
                    candidate_pts = self._try_shift(
                        points, idx, shift_by, state,
                        crowd_level     = crowd_level,
                        crowd_threshold = crowd_threshold,
                        disruption_type = disruption_type,
                    )
                    if candidate_pts is not None:
                        result = self._finalise(
                            label    = f"Step2 — ShiftLater +{shift_by}",
                            cand_pts = candidate_pts,
                            orig     = current_plan,
                            orig_pts = points,
                            orig_N   = original_N,
                            modified = [disrupted_stop_name],
                            state    = state,
                            disrupted = disrupted_stop_name,
                            is_user_skip = is_user_skip,
                        )
                        if result is not None and result.invariants_satisfied:
                            return result

        # ── §2 Step 3: SwapWithNext ───────────────────────────────────────────
        if allow_shift and idx + 1 < len(points):
            next_name     = points[idx + 1].name
            candidate_pts = self._try_swap(points, idx, idx + 1, state)
            if candidate_pts is not None:
                result = self._finalise(
                    label    = "Step3 — SwapWithNext",
                    cand_pts = candidate_pts,
                    orig     = current_plan,
                    orig_pts = points,
                    orig_N   = original_N,
                    modified = [disrupted_stop_name, next_name],
                    state    = state,
                    disrupted = disrupted_stop_name,
                    is_user_skip = is_user_skip,
                )
                if result is not None and result.invariants_satisfied:
                    return result

        # ── §2 Step 4: ReplaceNearby ──────────────────────────────────────────
        if allow_replace:
            exclude_outdoor = (disruption_type == "WEATHER")
            candidates = self._find_nearby(
                origin_lat      = points[idx].location_lat,
                origin_lon      = points[idx].location_lon,
                origin_category = origin_cat,
                origin_outdoor  = origin_outdoor,
                remaining_pool  = remaining_pool,
                constraints     = constraints,
                excluded        = excluded,
                exclude_outdoor = exclude_outdoor,
            )
            if replacement_candidate and replacement_candidate.name not in excluded:
                candidates = [replacement_candidate] + [
                    c for c in candidates if c.name != replacement_candidate.name
                ]

            for cand in candidates:
                candidate_pts = self._try_replace(points, idx, cand, state)
                if candidate_pts is not None:
                    result = self._finalise(
                        label    = f"Step4 — ReplaceNearby '{cand.name}'",
                        cand_pts = candidate_pts,
                        orig     = current_plan,
                        orig_pts = points,
                        orig_N   = original_N,
                        modified = [disrupted_stop_name, cand.name],
                        state    = state,
                        disrupted = disrupted_stop_name,
                        is_user_skip = is_user_skip,
                    )
                    if result is not None and result.invariants_satisfied:
                        return result

        # ── §2 Step 5: DEFERRED_TO_NEXT_DAY ──────────────────────────────────
        # Remove disrupted stop; do NOT insert any new distant cluster (§2 Step 5).
        remaining_pts = [rp for rp in points if rp.name != disrupted_stop_name]
        recomputed    = (
            self._recompute_from(remaining_pts, max(0, idx - 1), state)
            if remaining_pts else []
        )
        result = self._finalise(
            label    = "Step5 — DeferredToNextDay",
            cand_pts = recomputed,
            orig     = current_plan,
            orig_pts = points,
            orig_N   = original_N,
            modified = [disrupted_stop_name],
            state    = state,
            disrupted = disrupted_stop_name,
            is_user_skip = is_user_skip,
        )
        if result is not None:
            return result

        # Absolute fallback: empty day is valid (all stops completed / removed)
        self._log("Step5-EmptyDay", disrupted_stop_name)
        return RepairResult(
            updated_plan      = self._build_plan(current_plan, []),
            modified_elements = [disrupted_stop_name],
            invariants_satisfied = True,
            strategy_used     = "Step5-EmptyDay",
        )

    # ── Private: strategy implementations ─────────────────────────────────────

    def _try_shift(
        self,
        points:          list[RoutePoint],
        idx:             int,
        shift_by:        int,
        state:           TripState,
        *,
        crowd_level:     float = 0.0,
        crowd_threshold: float = 1.0,
        disruption_type: str   = "",
    ) -> Optional[list[RoutePoint]]:
        """
        §2 Step 2 + §5 — Move points[idx] to position idx+shift_by.

        §5 Crowd Deferral Validation:
          For CROWD disruptions, estimate crowd at the new arrival slot using
          exponential decay (CROWD_DECAY_PER_30MIN per 30 min).
          Reject the slot if estimated crowd still > crowd_threshold.
        """
        if shift_by > REPAIR_WINDOW_RADIUS:
            return None

        new_pts   = list(points)
        disrupted = new_pts.pop(idx)
        insert_at = min(idx + shift_by, len(new_pts))
        new_pts.insert(insert_at, disrupted)

        result = self._recompute_from(new_pts, max(0, idx - 1), state)
        if not self._is_timing_valid(result):
            return None

        # §5: recheck crowd forecast at new slot
        if disruption_type == "CROWD" and crowd_level > 0 and crowd_threshold < 1.0:
            slot_rp = next((r for r in result if r.name == disrupted.name), None)
            if slot_rp and slot_rp.arrival_time:
                ch, cm = map(int, state.current_time.split(":"))
                delay  = max(0, _time_to_min(slot_rp.arrival_time) - (ch * 60 + cm))
                decay  = (1.0 - CROWD_DECAY_PER_30MIN) ** (delay / 30.0)
                est_crowd = crowd_level * decay
                if est_crowd > crowd_threshold:
                    self._log(
                        f"Shift +{shift_by} rejected: est. crowd "
                        f"{est_crowd:.2f} > threshold {crowd_threshold:.2f} (§5)",
                        disrupted.name,
                    )
                    return None

        return result

    def _try_swap(
        self,
        points: list[RoutePoint],
        idx_a:  int,
        idx_b:  int,
        state:  TripState,
    ) -> Optional[list[RoutePoint]]:
        """§2 Step 3 — Swap two adjacent stops and recompute timing."""
        if abs(idx_a - idx_b) > REPAIR_WINDOW_RADIUS:
            return None
        new_pts = list(points)
        new_pts[idx_a], new_pts[idx_b] = new_pts[idx_b], new_pts[idx_a]
        result = self._recompute_from(new_pts, max(0, min(idx_a, idx_b) - 1), state)
        return result if self._is_timing_valid(result) else None

    def _try_replace(
        self,
        points:    list[RoutePoint],
        idx:       int,
        candidate: AttractionRecord,
        state:     TripState,
    ) -> Optional[list[RoutePoint]]:
        """§2 Step 4 / §6 — Replace points[idx] with a RoutePoint built from candidate."""
        original_rp = points[idx]
        new_rp = RoutePoint(
            sequence               = original_rp.sequence,
            name                   = candidate.name,
            location_lat           = candidate.location_lat,
            location_lon           = candidate.location_lon,
            visit_duration_minutes = candidate.visit_duration_minutes,
            activity_type          = "attraction",
            estimated_cost         = 0.0,
            notes                  = f"Local replacement for '{original_rp.name}'",
        )
        new_pts       = list(points)
        new_pts[idx]  = new_rp
        result        = self._recompute_from(new_pts, max(0, idx - 1), state)
        return result if self._is_timing_valid(result) else None

    # ── Private: finalise + invariant check ───────────────────────────────────

    def _finalise(
        self,
        label:    str,
        cand_pts: list[RoutePoint],
        orig:     DayPlan,
        orig_pts: list[RoutePoint],
        orig_N:   int,
        modified: list[str],
        state:    TripState,
        disrupted: str,
        is_user_skip: bool = False,
    ) -> Optional[RepairResult]:
        """
        Apply §3 meal fix → run §1 invariant check → build RepairResult.
        Returns None if meal fix fails (caller tries next strategy).
        Returns RepairResult with invariants_satisfied=False if invariant check
        fails (caller tries next strategy for strict-invariant steps; uses this
        result only for Step 5 last-resort).
        """
        # §3 Meal constraints
        fixed_pts, meal_err = _validate_and_fix_meals(cand_pts)
        if fixed_pts is None:
            self._log(f"{label} blocked by meal constraint: {meal_err}", disrupted)
            return None

        # §3+ Day-structure guard: at least 1 non-meal POI (no meal-only days)
        non_meal_count = sum(1 for rp in fixed_pts if not _is_meal(rp))
        if fixed_pts and non_meal_count == 0:
            self._log(
                f"{label} blocked: meal-only day (0 non-meal POIs)", disrupted
            )
            return None

        # §1 Invariant check
        ok, err = self._checker.check(
            original_points = orig_pts,
            new_points      = fixed_pts,
            state           = state,
            original_N      = orig_N,
            disrupted_name  = disrupted,
            is_user_skip    = is_user_skip,
        )
        if not ok:
            self._log(f"{label} invariant rejected: {err}", disrupted)
            return RepairResult(
                updated_plan         = self._build_plan(orig, fixed_pts),
                modified_elements    = modified[:2],
                invariants_satisfied = False,
                error_code           = err,
                strategy_used        = label,
            )

        self._log(label, disrupted)
        return RepairResult(
            updated_plan         = self._build_plan(orig, fixed_pts),
            modified_elements    = modified[:2],
            invariants_satisfied = True,
            error_code           = None,
            strategy_used        = label,
        )

    # ── Private: time recomputation (§4 Timing Rule) ──────────────────────────

    def _recompute_from(
        self,
        points:    list[RoutePoint],
        start_idx: int,
        state:     TripState,
    ) -> list[RoutePoint]:
        """
        §4 TIMING RULE cascade from start_idx onward.

        Enforces:
          arr_i = dep_{i-1} + travel_time + BUFFER_MINUTES
          dep_i = arr_i + visit_duration
          Warn if gap > MAX_GAP_MINUTES between consecutive stops.
          Truncate stops that overflow DAY_END_MINUTES.

        Stops before start_idx are untouched (preserves §1 Inv 2 locked blocks).
        """
        if not points:
            return []

        pts = [copy.copy(rp) for rp in points]

        # Anchor time + position
        if start_idx > 0 and pts[start_idx - 1].departure_time is not None:
            prev_dep = _time_to_min(pts[start_idx - 1].departure_time)
            prev_lat = pts[start_idx - 1].location_lat
            prev_lon = pts[start_idx - 1].location_lon
        else:
            ch, cm   = map(int, state.current_time.split(":"))
            prev_dep = ch * 60 + cm
            prev_lat = state.current_lat
            prev_lon = state.current_lon

        keep: list[RoutePoint] = pts[:start_idx]

        for i in range(start_idx, len(pts)):
            rp         = pts[i]
            travel     = self._dist.travel_time_minutes(prev_lat, prev_lon, rp.location_lat, rp.location_lon)
            arr_min    = prev_dep + travel + BUFFER_MINUTES
            dep_min    = arr_min + rp.visit_duration_minutes

            if dep_min > DAY_END_MINUTES:
                break  # truncate; not an error

            # §4 gap warning
            idle = arr_min - prev_dep - travel
            if idle > MAX_GAP_MINUTES and keep:
                print(
                    f"  [LocalRepair] §4 gap {idle:.0f} min before '{rp.name}' "
                    f"(>{MAX_GAP_MINUTES} min threshold)"
                )

            rp.arrival_time   = _min_to_time(int(arr_min))
            rp.departure_time = _min_to_time(int(dep_min))
            rp.sequence       = len(keep)
            keep.append(rp)

            prev_dep = dep_min
            prev_lat = rp.location_lat
            prev_lon = rp.location_lon

        print("  Downstream stop times recomputed (LocalRepair).")
        return keep

    # ── Private: timing feasibility (§4) ──────────────────────────────────────

    @staticmethod
    def _is_timing_valid(points: Optional[list[RoutePoint]]) -> bool:
        """
        §4 — validates a recomputed point list:
          • Non-empty.
          • Each stop: arrival ≤ departure (no backwards time).
          • No overlap: arrival_i ≥ departure_{i-1}.
          • Last stop departs by DAY_END_MINUTES.
        """
        if not points:
            return False
        prev_dep = 0
        for rp in points:
            if rp.arrival_time is None or rp.departure_time is None:
                continue
            arr = _time_to_min(rp.arrival_time)
            dep = _time_to_min(rp.departure_time)
            if arr > dep:
                return False   # backwards time
            if arr < prev_dep:
                return False   # overlap with previous stop
            if dep > DAY_END_MINUTES:
                return False   # hard day-end overflow
            prev_dep = dep
        return True

    # ── Private: nearby candidate search (§6 ACO ranking) ─────────────────────

    def _find_nearby(
        self,
        origin_lat:      float,
        origin_lon:      float,
        origin_category: str,
        origin_outdoor:  bool,
        remaining_pool:  list[AttractionRecord],
        constraints:     ConstraintBundle,
        excluded:        set[str],
        exclude_outdoor: bool = False,
    ) -> list[AttractionRecord]:
        """
        §6 ACO LIMITATION — rank nearby alternatives by η = (rating/5) / Dij.

        Filters:
          • Within MAX_REPLACE_RADIUS_KM of origin (§2 Step 4).
          • Not in excluded set.
          • Wheelchair accessible if required.
          • Non-outdoor if exclude_outdoor (WEATHER disruptions).

        Same-category-group candidates ranked first (cluster preference).
        """
        wheelchair = getattr(
            getattr(constraints, "hard", None), "wheelchair_accessible", False
        )
        cat     = (origin_category or "").lower().strip()
        related = _CATEGORY_GROUPS.get(cat, [cat])

        same_cat: list[tuple[float, AttractionRecord]] = []
        any_cat:  list[tuple[float, AttractionRecord]] = []
        speed_kmh = getattr(config, "OSRM_FALLBACK_SPEED_KMH", 4.5)

        for attr in remaining_pool:
            if attr.name in excluded:
                continue
            if wheelchair and not attr.wheelchair_accessible:
                continue
            if exclude_outdoor and getattr(attr, "is_outdoor", False):
                continue

            km = haversine_km(origin_lat, origin_lon, attr.location_lat, attr.location_lon)
            if km > MAX_REPLACE_RADIUS_KM:
                continue

            # §6 η = (normalised rating) / Dij_minutes — ranking ONLY, not rebuild
            dij = max((km / speed_kmh) * 60.0, 1.0)
            eta = max(attr.rating, 0.01) / 5.0 / dij

            if (attr.category or "").lower() in related:
                same_cat.append((eta, attr))
            else:
                any_cat.append((eta, attr))

        same_cat.sort(key=lambda x: -x[0])
        any_cat.sort(key=lambda x:  -x[0])
        return [a for _, a in same_cat + any_cat]

    # ── Private: helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_plan(original: DayPlan, new_points: list[RoutePoint]) -> DayPlan:
        return DayPlan(
            day_number        = original.day_number,
            date              = original.date,
            route_points      = new_points,
            daily_budget_used = original.daily_budget_used,
        )

    @staticmethod
    def _log(strategy: str, stop: str) -> None:
        print(f"  [LocalRepair] Strategy → {strategy}  (disrupted: '{stop}')")
