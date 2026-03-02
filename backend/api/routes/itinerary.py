"""
api/routes/itinerary.py
------------------------
POST /v1/itinerary/generate

Runs the full 5-stage FTRM+ACO pipeline and returns the itinerary JSON.
A ReOptimizationSession is automatically created and stored in-memory so
the /v1/reoptimize/* endpoints can be used immediately after.

In-memory session store will be replaced by Redis in task 10.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type, time as time_type
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from schemas.constraints import (
    HardConstraints, SoftConstraints, CommonsenseConstraints, ConstraintBundle,
)
from schemas.itinerary import Itinerary
from modules.tool_usage.attraction_tool import AttractionTool, _CITY_CENTERS
from modules.reoptimization.session import ReOptimizationSession
from main import run_pipeline

router = APIRouter()

# ── In-memory session store ────────────────────────────────────────────────────
# key: session_id (str uuid4)
# value: {
#   "itinerary":   Itinerary,
#   "constraints": ConstraintBundle,
#   "attractions": list[AttractionRecord],
#   "session":     ReOptimizationSession,
# }
_store: dict[str, dict] = {}


# ── Request / Response schemas ─────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    user_id: str = Field("user_001", description="Unique user identifier")
    departure_city: str
    destination_city: str
    departure_date: str = Field(..., description="ISO-8601 date YYYY-MM-DD")
    return_date:    str = Field(..., description="ISO-8601 date YYYY-MM-DD")
    num_adults:     int = Field(1, ge=1)
    num_children:   int = Field(0, ge=0)
    restaurant_preference: str = Field("", description="Cuisine string e.g. 'Indian'")
    total_budget:   float = Field(50000.0, gt=0)
    requires_wheelchair: bool = False
    # Soft constraints
    interests:       list[str] = Field(default_factory=list)
    spending_power:  str = Field("medium", description="low | medium | high")
    avoid_crowds:    bool = False
    pace_preference: str = Field("moderate", description="relaxed | moderate | packed")
    heavy_travel_penalty: bool = False


# ── Serialisers ────────────────────────────────────────────────────────────────

def _ser_time(t: Optional[time_type]) -> Optional[str]:
    return t.strftime("%H:%M") if t else None


def _ser_itinerary(it: Itinerary) -> dict:
    return {
        "trip_id": it.trip_id,
        "destination_city": it.destination_city,
        "total_actual_cost": it.total_actual_cost,
        "budget": {
            "Accommodation":  it.budget.Accommodation,
            "Attractions":    it.budget.Attractions,
            "Restaurants":    it.budget.Restaurants,
            "Transportation": it.budget.Transportation,
            "Other_Expenses": it.budget.Other_Expenses,
            "Reserve_Fund":   it.budget.Reserve_Fund,
        },
        "days": [
            {
                "day_number":        d.day_number,
                "date":              str(d.date),
                "daily_budget_used": d.daily_budget_used,
                "route_points": [
                    {
                        "sequence":              rp.sequence,
                        "name":                  rp.name,
                        "location_lat":          rp.location_lat,
                        "location_lon":          rp.location_lon,
                        "arrival_time":          _ser_time(rp.arrival_time),
                        "departure_time":        _ser_time(rp.departure_time),
                        "visit_duration_minutes": rp.visit_duration_minutes,
                        "activity_type":         rp.activity_type,
                        "estimated_cost":        rp.estimated_cost,
                        "notes":                 rp.notes,
                    }
                    for rp in d.route_points
                ],
            }
            for d in it.days
        ],
    }


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("/generate", summary="Generate a full multi-day itinerary")
def generate_itinerary(req: GenerateRequest) -> dict:
    """
    Runs the full FTRM+ACO 5-stage pipeline:
      1. Constraint modelling
      2. Budget planning
      3. Recommendations (attractions / hotels / restaurants / flights)
      4. ACO route optimisation
      5. Memory update

    Returns the itinerary JSON plus a `session_id` for real-time
    re-optimisation via the /v1/reoptimize/* endpoints.
    """
    # ── Validate dates ─────────────────────────────────────────────────────
    try:
        dep_date = date_type.fromisoformat(req.departure_date)
        ret_date = date_type.fromisoformat(req.return_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {exc}") from exc

    if ret_date < dep_date:
        raise HTTPException(
            status_code=422,
            detail=f"return_date ({ret_date}) must be >= departure_date ({dep_date})",
        )

    # ── Build constraint bundle ────────────────────────────────────────────
    hard = HardConstraints(
        departure_city=req.departure_city,
        destination_city=req.destination_city,
        departure_date=dep_date,
        return_date=ret_date,
        num_adults=req.num_adults,
        num_children=req.num_children,
        restaurant_preference=req.restaurant_preference,
        requires_wheelchair=req.requires_wheelchair,
    )
    soft = SoftConstraints(
        interests=req.interests,
        spending_power=req.spending_power,
        avoid_crowds=req.avoid_crowds,
        pace_preference=req.pace_preference,
        heavy_travel_penalty=req.heavy_travel_penalty,
    )
    commonsense = CommonsenseConstraints()
    constraints = ConstraintBundle(hard=hard, soft=soft, commonsense=commonsense)

    # ── Run pipeline ───────────────────────────────────────────────────────
    try:
        itinerary = run_pipeline(
            user_id=req.user_id,
            constraints=constraints,
            total_budget=req.total_budget,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc

    # ── Fetch attraction pool for reoptimise session ───────────────────────
    try:
        attractions = AttractionTool().fetch(req.destination_city)
    except Exception:
        attractions = []

    # ── Determine hotel coordinates (city centre fallback) ─────────────────
    city_key = req.destination_city.strip().lower()
    hotel_lat, hotel_lon = _CITY_CENTERS.get(city_key, (0.0, 0.0))

    # ── Create reoptimise session ──────────────────────────────────────────
    try:
        reopt_session = ReOptimizationSession.from_itinerary(
            itinerary=itinerary,
            constraints=constraints,
            remaining_attractions=attractions,
            hotel_lat=hotel_lat,
            hotel_lon=hotel_lon,
            start_day=1,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"ReOptimizationSession init error: {exc}"
        ) from exc

    # ── Persist in memory ──────────────────────────────────────────────────
    session_id = str(uuid.uuid4())
    _store[session_id] = {
        "itinerary":   itinerary,
        "constraints": constraints,
        "attractions": attractions,
        "session":     reopt_session,
    }

    return {
        "session_id": session_id,
        "itinerary": _ser_itinerary(itinerary),
    }


# ── Utility: expose store to other routes ─────────────────────────────────────

def get_session(session_id: str) -> dict:
    """Retrieve a stored session or raise 404."""
    entry = _store.get(session_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. Call /v1/itinerary/generate first.",
        )
    return entry
