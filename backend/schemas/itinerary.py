"""
schemas/itinerary.py
--------------------
Dataclass definitions for the output itinerary structures in TravelAgent.

TODO (MISSING from architecture doc):
  - Exact fields for RoutePoint (activity type enum, cost breakdown, etc.)
  - Currency and time units
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, time
from typing import Optional


@dataclass
class BudgetAllocation:
    """
    Budget distributed by the deterministic BudgetPlanner engine.

    Six financial categories (all amounts in INR):
      Accommodation  — hotel / lodging spend
      Attractions    — combined entry fees for scheduled POIs
      Restaurants    — food & beverage across the trip
      Transportation — ground transport (metro / auto / cab / ride-share)
      Other_Expenses — incidentals, shopping, tips (5–10% of total)
      Reserve_Fund   — buffer for overruns (≥ 5% of total)

    Validation metadata (set by BudgetPlanner._apply_constraints_and_balance):
      ValidationStatus  — "PASS" | "FAIL" | "PENDING"
      RebalanceApplied  — True if any cap or floor triggered redistribution
      DataQuality       — "REAL"            (hotel + restaurant prices from API)
                          "CITY_INDEX"      (city-level cost index used as fallback)
                          "MISSING_COST_DATA" (no pricing source found)
                          "PENDING"         (not yet computed)
    """
    # ── Financial categories ──────────────────────────────────────────────────
    Accommodation:  float = 0.0
    Attractions:    float = 0.0
    Restaurants:    float = 0.0
    Transportation: float = 0.0
    Other_Expenses: float = 0.0
    Reserve_Fund:   float = 0.0

    # ── Validation metadata ───────────────────────────────────────────────────
    ValidationStatus: str  = "PENDING"
    RebalanceApplied: bool = False
    DataQuality:      str  = "PENDING"

    @property
    def total(self) -> float:
        """Sum of the six financial categories only (excludes metadata fields)."""
        return (
            self.Accommodation + self.Attractions + self.Restaurants
            + self.Transportation + self.Other_Expenses + self.Reserve_Fund
        )


@dataclass
class RoutePoint:
    """
    A single stop in a day's itinerary.

    TODO: MISSING — activity_type enum values not specified in architecture doc.
    TODO: MISSING — cost field currency unit.
    """
    sequence: int = 0
    name: str = ""
    location_lat: float = 0.0
    location_lon: float = 0.0
    arrival_time: Optional[time] = None        # t_cur at this point
    departure_time: Optional[time] = None
    visit_duration_minutes: int = 0            # TODO: MISSING — time unit (assumed minutes)
    activity_type: str = ""                    # e.g. "attraction" | "restaurant" | "hotel" | "flight"
    estimated_cost: float = 0.0               # TODO: MISSING — currency unit
    notes: str = ""


@dataclass
class DayPlan:
    """One day's scheduled activities."""
    day_number: int = 0
    date: Optional[date] = None
    route_points: list[RoutePoint] = field(default_factory=list)
    daily_budget_used: float = 0.0


@dataclass
class Itinerary:
    """
    Top-level output of the Planning Module.
    Final artefact returned to the user in Stage 5.
    """
    trip_id: str = ""
    destination_city: str = ""
    days: list[DayPlan] = field(default_factory=list)
    budget: BudgetAllocation = field(default_factory=BudgetAllocation)
    total_actual_cost: float = 0.0
    generated_at: str = ""  # ISO-8601 timestamp
