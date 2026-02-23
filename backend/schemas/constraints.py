"""
schemas/constraints.py
-----------------------
Dataclass definitions for the three constraint types in TravelAgent.

Hard Constraints (HC) — non-negotiable; violating any makes the itinerary invalid:
  Time & Scheduling:
    operating_hours        — place must be open when visited
    no_time_overlap        — enforced by ACO sequential tour construction
    transit_time           — Dij accounted in Tmax budget (hc2 in registry)
    activity_duration      — min_visit_duration_minutes per venue
    fixed_appointments     — pre-booked flights/check-ins with locked times
  Geography & Logistics:
    requires_wheelchair    — venue must be wheelchair accessible if needed
    visa_restricted_countries — destination must not be in restricted list
    traveler_ages          — age restrictions per venue
  Budget:
    total cost cap         — enforced by BudgetPlanner.validate()
    mandatory_spend        — fixed_appointments sunk costs honored
  Group & Personal:
    group_size             — checked against venue min/max capacity
  Date Boundaries:
    departure_date/return_date — no activity outside trip window
    seasonal_open_months   — venue must be open in the trip month

Soft Constraints (SC) — preferences; violating degrades, not invalidates:
  Experience & Comfort:
    preferred_time_of_day  — "morning" | "afternoon" | "evening" | ""
    avoid_crowds           — prefer off-peak times (morning/weekday)
    pace_preference        — "relaxed" | "moderate" | "packed"
  Routing & Efficiency:
    preferred_transport_mode — ["walking", "public_transit", "taxi", "car"]
  Meals & Breaks:
    dietary_preferences    — ["vegan", "vegetarian", "halal", "local", ...]
    meal_lunch_window      — preferred lunch slot e.g. ("12:00","14:00")
    meal_dinner_window     — preferred dinner slot e.g. ("19:00","21:00")
    rest_interval_minutes  — max consecutive activity minutes before a break
  Interest Alignment:
    interests              — activity categories user enjoys
    avoid_consecutive_same_category — no 3 art museums back-to-back
    novelty_spread         — mix culture/nature/food across the day
  Energy Management:
    heavy_travel_penalty   — reduce score for strenuous activities on
                             arrival/departure days or day after long flight
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class HardConstraints:
    """
    Non-negotiable trip requirements.  Any violation gates S_pti to 0.
    Populated in Stage 1 (chat intake Phase 1 or hardcoded pipeline).
    """
    # ── Core trip parameters ──────────────────────────────────────────────────
    departure_city: str = ""
    destination_city: str = ""
    departure_date: Optional[date] = None
    return_date: Optional[date] = None
    num_adults: int = 1
    num_children: int = 0
    restaurant_preference: str = ""          # cuisine / dietary string from Phase 1 form

    # ── Accessibility & group ─────────────────────────────────────────────────
    requires_wheelchair: bool = False         # venues must be wheelchair accessible
    group_size: int = 1                       # total travellers; checked vs venue min/max
    traveler_ages: list[int] = field(default_factory=list)
    # ^ actual ages of travellers; used for age-restriction HC (hc4 in registry)
    # Leave empty to disable age-restriction checks.

    # ── Fixed / pre-booked slots ──────────────────────────────────────────────
    fixed_appointments: list[dict] = field(default_factory=list)
    # ^ Each entry: {"name": str, "date": "YYYY-MM-DD", "time": "HH:MM",
    #                "duration_minutes": int, "type": "flight|hotel|tour"}
    # These are sunk-cost commitments and must be honored.

    # ── Geography / legal ─────────────────────────────────────────────────────
    visa_restricted_countries: list[str] = field(default_factory=list)
    # ^ ISO country codes (e.g. ["KP", "IR"]) that are inaccessible to
    # the traveller; used to gate destinations (handled upstream, not in FTRM).

    @property
    def total_travelers(self) -> int:
        """Convenience alias: num_adults + num_children."""
        return self.num_adults + self.num_children


@dataclass
class SoftConstraints:
    """
    User preferences that influence scoring (SCpti) but do not hard-gate items.
    Retrieved from Memory Module; evolve via iterative feedback (Wv learning).
    """
    # ── Existing fields ───────────────────────────────────────────────────────
    travel_preferences: list[str] = field(default_factory=list)
    # ^ travel style: ["adventure", "relaxed", "cultural", "luxury", ...]
    character_traits: list[str] = field(default_factory=list)
    # ^ personality: ["avoids_crowds", "budget_conscious", "spontaneous"]
    interests: list[str] = field(default_factory=list)
    # ^ activity categories: ["museum", "park", "landmark", "food", "nightlife"]
    spending_power: str = ""                 # "low" | "medium" | "high"

    # ── Dietary / food ────────────────────────────────────────────────────────
    dietary_preferences: list[str] = field(default_factory=list)
    # ^ ["vegan", "vegetarian", "halal", "kosher", "gluten_free", "local_cuisine"]
    # Used as SOFT signal in RestaurantRecommender SC scoring (on top of HC cuisine gate).

    # ── Experience & comfort ──────────────────────────────────────────────────
    preferred_time_of_day: str = ""
    # ^ "" | "morning" | "afternoon" | "evening"
    # Attractions whose optimal_visit_time aligns score higher.
    avoid_crowds: bool = False
    # ^ True → prefer morning/off-peak slots; is_outdoor venues penalized mid-day.
    pace_preference: str = "moderate"
    # ^ "relaxed" | "moderate" | "packed"
    # relaxed  → fewer stops, longer visits; packed → maximize stops per day.

    # ── Routing preferences ───────────────────────────────────────────────────
    preferred_transport_mode: list[str] = field(default_factory=list)
    # ^ ["walking", "public_transit", "taxi", "car", "bike"]
    # Used as SC preference signal in FlightRecommender / general routing.

    # ── Meal timing ───────────────────────────────────────────────────────────
    meal_lunch_window: tuple = ("12:00", "14:00")
    # ^ (start_HH:MM, end_HH:MM) — preferred lunch slot; route planner avoids
    # scheduling attractions during this window on days with restaurants.
    meal_dinner_window: tuple = ("19:00", "21:00")
    # ^ (start_HH:MM, end_HH:MM) — preferred dinner slot.

    # ── Break / energy ────────────────────────────────────────────────────────
    rest_interval_minutes: int = 120
    # ^ max consecutive activity minutes before inserting a rest/meal break.
    # Used in route planner to inject break slots.
    heavy_travel_penalty: bool = True
    # ^ True → strenuous (intensity_level="high") attractions score lower on
    # arrival/departure days and the day immediately after a long flight.

    # ── Interest alignment ────────────────────────────────────────────────────
    avoid_consecutive_same_category: bool = True
    # ^ True → penalise scheduling the same attraction category back-to-back
    # (e.g. 3 museums in a row); promotes variety within a day.
    novelty_spread: bool = True
    # ^ True → reward mixing culture / nature / food across the day's route.


@dataclass
class CommonsenseConstraints:
    """
    General travel rules applied across POI types.
    Examples: a sight can't be visited twice; hotels near city centre.
    Populated by LLM extraction in Phase 2 (chat_intake) and Memory Module.
    """
    rules: list[str] = field(default_factory=list)
    # ^ Free-text rules, e.g.:
    #   "no street food", "avoid tourist traps", "visit famous landmarks first"
    # TODO: Migrate to structured rule objects when format is stabilised.


@dataclass
class ConstraintBundle:
    """Aggregated view of all three constraint types, passed between modules."""
    hard: HardConstraints = field(default_factory=HardConstraints)
    soft: SoftConstraints = field(default_factory=SoftConstraints)
    commonsense: CommonsenseConstraints = field(default_factory=CommonsenseConstraints)
