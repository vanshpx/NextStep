"""
modules/reoptimization/partial_replanner.py
---------------------------------------------
Re-plans the REMAINDER of the current day starting from the traveller's
current position.

Key differences from RoutePlanner.plan():
  - Start node = current GPS position (not hotel)
  - Tmax       = minutes from current_time to end-of-day (not full 480 min)
  - Pool        = remaining_attractions − visited − skipped
  - Optional:   deprioritize_outdoor flag for weather events

Reuses all existing FTRM + ACO machinery unchanged.
"""

from __future__ import annotations
from datetime import date

from schemas.constraints import ConstraintBundle, SoftConstraints
from schemas.itinerary import BudgetAllocation, DayPlan
from schemas.ftrm import FTRMParameters
from modules.tool_usage.attraction_tool import AttractionRecord
from modules.tool_usage.distance_tool import DistanceTool
from modules.tool_usage.time_tool import TimeTool
from modules.planning.route_planner import RoutePlanner, DEFAULT_DAY_END
from modules.reoptimization.trip_state import TripState
import config


class PartialReplanner:
    """
    Wraps RoutePlanner._plan_single_day() for mid-trip replanning.

    Adjusts three inputs before delegating to the existing planner:
      1. start_lat/lon  ← current GPS position from TripState
      2. Tmax (minutes) ← remaining minutes in today
      3. attraction pool ← filtered to exclude visited + skipped stops

    The caller is responsible for passing an updated ConstraintBundle if
    any SoftConstraints changed (e.g. preference update event).
    """

    def __init__(
        self,
        distance_tool: DistanceTool | None = None,
        time_tool: TimeTool | None = None,
    ) -> None:
        self._distance  = distance_tool or DistanceTool()
        self._time      = time_tool or TimeTool()

    def replan(
        self,
        state: TripState,
        remaining_attractions: list[AttractionRecord],
        constraints: ConstraintBundle,
        day_end_time: str = "20:00",
        deprioritize_outdoor: bool = False,
    ) -> DayPlan:
        """
        Generate a new DayPlan for the rest of today from current position.

        Args:
            state:                  Live TripState (position, time, visited).
            remaining_attractions:  Full remaining pool — visited/skipped
                                    stops are filtered out inside this method.
            constraints:            May have been updated mid-trip (pref change).
            day_end_time:           End-of-day boundary (default "20:00").
            deprioritize_outdoor:   If True (weather event), outdoor attractions
                                    are moved to the end of the scoring pool so
                                    the ACO prefers indoor alternatives.

        Returns:
            New DayPlan covering the remaining stops for today.
        """
        # ── 1. Filter pool ────────────────────────────────────────────────────
        excluded = state.visited_stops | state.skipped_stops | state.deferred_stops
        pool = [a for a in remaining_attractions if a.name not in excluded]

        if deprioritize_outdoor:
            indoor  = [a for a in pool if not getattr(a, "is_outdoor", False)]
            outdoor = [a for a in pool if getattr(a, "is_outdoor", False)]
            pool = indoor + outdoor   # indoor attractions evaluated first by ACO

        if not pool:
            # Nothing left to plan — return empty day
            return DayPlan(day_number=state.current_day, date=state.current_day_date)

        # ── 2. Compute remaining Tmax ─────────────────────────────────────────
        remaining_min = state.remaining_minutes_today(day_end_time)
        if remaining_min <= 0:
            return DayPlan(day_number=state.current_day, date=state.current_day_date)

        # ── 3. Build a RoutePlanner with reduced Tmax ─────────────────────────
        adjusted_params = FTRMParameters(
            Tmax=remaining_min,                      # ← reduced day window
            alpha=config.ACO_ALPHA,
            beta=config.ACO_BETA,
            rho=config.ACO_RHO,
            Q=config.ACO_Q,
            tau_init=config.ACO_TAU_INIT,
            num_ants=config.ACO_NUM_ANTS,
            num_iterations=config.ACO_ITERATIONS,
            sc_aggregation_method=config.SC_AGGREGATION_METHOD,
            pheromone_update_strategy=config.ACO_PHEROMONE_STRATEGY,
        )

        planner = RoutePlanner(
            distance_tool=self._distance,
            time_tool=self._time,
            ftrm_params=adjusted_params,
        )

        # ── 4. Derive context ─────────────────────────────────────────────────
        trip_month   = state.current_day_date.month
        group_size   = (constraints.hard.group_size
                        or constraints.hard.total_travelers or 1)
        traveler_ages = constraints.hard.traveler_ages

        # ── 5. Delegate to _plan_single_day from current position ─────────────
        new_plan = planner._plan_single_day(
            day_number=state.current_day,
            plan_date=state.current_day_date,
            available_attractions=pool,
            start_lat=state.current_lat,         # ← current position, not hotel
            start_lon=state.current_lon,
            constraints=constraints,
            trip_month=trip_month,
            group_size=group_size,
            traveler_ages=traveler_ages,
            is_arrival_or_departure_day=False,   # mid-trip replan: no boundary penalty
        )

        # Shift all route point times forward to start from current_time
        ch, cm = map(int, state.current_time.split(":"))
        current_minutes = ch * 60 + cm
        default_start_h, default_start_m = 9, 0
        default_start_minutes = default_start_h * 60 + default_start_m
        offset = current_minutes - default_start_minutes  # may be 0 if exactly 09:00

        if offset != 0 and new_plan.route_points:
            for rp in new_plan.route_points:
                rp.arrival_time   = self._time.add_minutes(rp.arrival_time,   offset)
                rp.departure_time = self._time.add_minutes(rp.departure_time, offset)

        return new_plan

    def apply_preference_update(
        self,
        constraints: ConstraintBundle,
        field_name: str,
        value,
    ) -> ConstraintBundle:
        """
        Return an updated ConstraintBundle with a single SoftConstraints field changed.
        Used by ReOptimizationSession when a USER_PREFERENCE_CHANGE event fires.
        """
        soft_dict = {
            k: getattr(constraints.soft, k)
            for k in constraints.soft.__dataclass_fields__
        }
        soft_dict[field_name] = value
        new_soft = SoftConstraints(**soft_dict)
        return ConstraintBundle(
            hard=constraints.hard,
            soft=new_soft,
            commonsense=constraints.commonsense,
        )
