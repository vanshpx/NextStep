"""
modules/reoptimization/trip_state.py
--------------------------------------
Live state of an in-progress trip.
Updated as the traveler moves through stops and events occur.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from schemas.itinerary import DayPlan


@dataclass
class TripState:
    """
    Tracks the real-time state of an active trip day.

    This is the single source of truth for the PartialReplanner:
      - current position (lat/lon)  → start node for the new plan
      - current_time                → remaining Tmax derived from this
      - visited_stops               → filter pool before re-scoring
      - budget_spent                → passed to next plan for cost awareness
    """

    # ── Position & Time ────────────────────────────────────────────────
    current_lat: float = 0.0
    current_lon: float = 0.0
    current_time: str = "09:00"           # "HH:MM" 24-hour

    # ── Day context ────────────────────────────────────────────────────
    current_day: int = 1                  # 1-indexed day number
    current_day_date: date = field(default_factory=date.today)

    # ── Stop tracking ─────────────────────────────────────────────────
    visited_stops: set[str] = field(default_factory=set)
    skipped_stops: set[str] = field(default_factory=set)
    deferred_stops: set[str] = field(default_factory=set)
    # ^ Stops temporarily excluded from the CURRENT replan due to high crowd levels.
    # Unlike skipped_stops, deferred stops are re-admitted to the planning pool
    # by the session once the deferral window passes.

    # ── Budget ────────────────────────────────────────────────────────
    budget_spent: dict[str, float] = field(default_factory=lambda: {
        "Accommodation": 0.0,
        "Attractions":   0.0,
        "Restaurants":   0.0,
        "Transportation": 0.0,
        "Other_Expenses": 0.0,
        "Reserve_Fund":  0.0,
    })

    # ── Current plan (may be replaced after replan) ───────────────────
    current_day_plan: DayPlan | None = None

    # ── Disruption log ────────────────────────────────────────────────
    disruption_log: list[dict] = field(default_factory=list)

    # ── Hunger / Fatigue state ────────────────────────────────────────
    hunger_level:    float = 0.0    # 0 = satiated, 1 = urgent need to eat
    fatigue_level:   float = 0.0    # 0 = fresh,    1 = exhausted
    last_meal_time:  str   = "09:00"  # reset on meal completion
    last_rest_time:  str   = "09:00"  # reset on rest insertion
    minutes_on_feet: int   = 0        # cumulative active minutes since last rest

    # ── Replan flag ───────────────────────────────────────────────────
    replan_pending: bool = False

    # ── Helpers ───────────────────────────────────────────────────────

    def mark_visited(self, stop_name: str, cost: float = 0.0) -> None:
        """Mark a stop as completed and update position + budget."""
        self.visited_stops.add(stop_name)
        self.budget_spent["Attractions"] += cost

    def mark_skipped(self, stop_name: str) -> None:
        """Mark a stop as user-skipped (excluded from future plans too)."""
        self.skipped_stops.add(stop_name)
        # If it was deferred, promote to permanently skipped
        self.deferred_stops.discard(stop_name)

    def defer_stop(self, stop_name: str) -> None:
        """Temporarily exclude a stop from the current replan (crowd deferral)."""
        self.deferred_stops.add(stop_name)

    def undefer_stop(self, stop_name: str) -> None:
        """Re-admit a stop to the planning pool (crowd may have cleared)."""
        self.deferred_stops.discard(stop_name)

    def advance_time(self, new_time: str) -> None:
        """Update current clock time, e.g. after arriving at a new stop."""
        self.current_time = new_time

    def move_to(self, lat: float, lon: float) -> None:
        """Update current GPS position."""
        self.current_lat = lat
        self.current_lon = lon

    def log_disruption(self, event_type: str, detail: dict) -> None:
        """Append a disruption event to the session log."""
        self.disruption_log.append({"type": event_type, **detail})

    def remaining_budget(self, budget_allocation) -> float:
        """Return remaining Attractions budget for today."""
        return budget_allocation.Attractions - self.budget_spent["Attractions"]

    def remaining_minutes_today(self, day_end_time: str = "20:00") -> int:
        """Minutes left from current_time until day_end_time."""
        ch, cm = map(int, self.current_time.split(":"))
        eh, em = map(int, day_end_time.split(":"))
        return max((eh * 60 + em) - (ch * 60 + cm), 0)
