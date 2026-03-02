"""
api/routes/reoptimize.py
-------------------------
All real-time re-optimisation endpoints.

Flow:
  1. POST /v1/itinerary/generate  → returns session_id + itinerary
  2. POST /v1/reoptimize/advance  → move to the next stop
  3. POST /v1/reoptimize/check    → feed live crowd/weather/traffic readings
                                    (builds PendingDecision if threshold breached)
  4. POST /v1/reoptimize/resolve  → APPROVE / REJECT / MODIFY the pending decision
  5. POST /v1/reoptimize/event    → fire any EventType directly
  6. GET  /v1/reoptimize/summary/{session_id}  → session summary JSON
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from modules.reoptimization.event_handler import EventType
from api.routes.itinerary import get_session, _ser_itinerary

router = APIRouter()


# ── Request schemas ────────────────────────────────────────────────────────────

class AdvanceRequest(BaseModel):
    session_id: str
    stop_name: str
    arrival_time: Optional[str] = None       # "HH:MM"
    lat: Optional[float] = None
    lon: Optional[float] = None
    cost: float = 0.0
    duration_minutes: int = 60
    intensity_level: str = "medium"          # low | medium | high


class CheckRequest(BaseModel):
    session_id: str
    # Crowd
    crowd_level: Optional[float] = None      # 0.0–1.0
    next_stop_name: Optional[str] = None
    next_stop_is_outdoor: bool = False
    # Weather
    weather_condition: Optional[str] = None  # clear|cloudy|rainy|stormy|snowy|foggy
    weather_severity: Optional[float] = None # 0.0–1.0
    # Traffic
    traffic_level: Optional[float] = None    # 0.0–1.0
    estimated_traffic_delay_minutes: int = 0


class ResolveRequest(BaseModel):
    session_id: str
    decision: str                            # APPROVE | REJECT | MODIFY
    action_index: Optional[int] = None       # required when decision=MODIFY


class EventRequest(BaseModel):
    session_id: str
    event_type: str                          # EventType.value string
    metadata: dict[str, Any] = {}


# ── Helper: serialise a DayPlan (or None) ─────────────────────────────────────

def _ser_dayplan(plan) -> Optional[dict]:
    if plan is None:
        return None
    from datetime import time as time_type
    def _t(t):
        return t.strftime("%H:%M") if isinstance(t, time_type) else None

    return {
        "day_number":        plan.day_number,
        "date":              str(plan.date),
        "daily_budget_used": plan.daily_budget_used,
        "route_points": [
            {
                "sequence":              rp.sequence,
                "name":                  rp.name,
                "location_lat":          rp.location_lat,
                "location_lon":          rp.location_lon,
                "arrival_time":          _t(rp.arrival_time),
                "departure_time":        _t(rp.departure_time),
                "visit_duration_minutes": rp.visit_duration_minutes,
                "activity_type":         rp.activity_type,
                "estimated_cost":        rp.estimated_cost,
                "notes":                 rp.notes,
            }
            for rp in plan.route_points
        ],
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/advance", summary="Mark a stop as visited and advance the session clock")
def advance(req: AdvanceRequest) -> dict:
    """
    Call this when the traveller physically arrives at (or departs from) a stop.
    Updates the session's current position, time, and visited-set.
    """
    entry = get_session(req.session_id)
    session = entry["session"]

    try:
        session.advance_to_stop(
            stop_name=req.stop_name,
            arrival_time=req.arrival_time,
            lat=req.lat,
            lon=req.lon,
            cost=req.cost,
            duration_minutes=req.duration_minutes,
            intensity_level=req.intensity_level,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "session_id": req.session_id,
        "current_time": session.state.current_time,
        "visited": list(session.state.visited_stops),
    }


@router.post("/check", summary="Feed live environmental readings to the session")
def check_conditions(req: CheckRequest) -> dict:
    """
    Feeds real-time crowd / weather / traffic readings.

    If a threshold is breached, the session builds a PendingDecision and
    returns it in `pending_decision`. Call /resolve next.

    If nothing is breached, `pending_decision` is null.
    """
    entry = get_session(req.session_id)
    session = entry["session"]

    kwargs: dict[str, Any] = {}
    if req.crowd_level is not None:
        kwargs["crowd_level"] = req.crowd_level
    if req.next_stop_name:
        kwargs["next_stop_name"] = req.next_stop_name
    kwargs["next_stop_is_outdoor"] = req.next_stop_is_outdoor
    if req.weather_condition:
        kwargs["weather_condition"] = req.weather_condition
    if req.weather_severity is not None:
        kwargs["weather_severity"] = req.weather_severity
    if req.traffic_level is not None:
        kwargs["traffic_level"] = req.traffic_level
    if req.estimated_traffic_delay_minutes:
        kwargs["estimated_traffic_delay_minutes"] = req.estimated_traffic_delay_minutes

    try:
        new_plan = session.check_conditions(**kwargs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    pending = None
    if session.pending_decision is not None:
        pd = session.pending_decision
        pending = {
            "disruption_type": getattr(pd, "disruption_type", None),
            "affected_stop":   getattr(pd, "affected_stop", None),
            "severity":        getattr(pd, "severity", None),
            "actions": [
                {
                    "index":       i,
                    "strategy":    str(getattr(a, "strategy", a)),
                    "description": getattr(a, "description", str(a)),
                }
                for i, a in enumerate(getattr(pd, "actions", []))
            ],
            "advisory_panel": getattr(pd, "advisory_panel", None),
        }

    return {
        "session_id":       req.session_id,
        "new_plan":         _ser_dayplan(new_plan),
        "pending_decision": pending,
        "current_time":     session.state.current_time,
    }


@router.post("/resolve", summary="Approve / Reject / Modify a pending disruption decision")
def resolve(req: ResolveRequest) -> dict:
    """
    APPROVE  — apply the chosen strategy and replan.
    REJECT   — discard the pending decision, keep current plan.
    MODIFY   — apply one specific action by index (action_index required).
    """
    entry = get_session(req.session_id)
    session = entry["session"]

    if session.pending_decision is None:
        raise HTTPException(
            status_code=409,
            detail="No pending decision. Call /check first.",
        )

    decision = req.decision.upper()
    if decision not in ("APPROVE", "REJECT", "MODIFY"):
        raise HTTPException(
            status_code=422,
            detail="decision must be APPROVE | REJECT | MODIFY",
        )

    try:
        if decision == "MODIFY":
            if req.action_index is None:
                raise HTTPException(
                    status_code=422,
                    detail="action_index is required when decision=MODIFY",
                )
            new_plan = session.resolve_pending(decision, action_index=req.action_index)
        else:
            new_plan = session.resolve_pending(decision)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "session_id": req.session_id,
        "new_plan":   _ser_dayplan(new_plan),
    }


@router.post("/event", summary="Fire a named EventType on the session")
def fire_event(req: EventRequest) -> dict:
    """
    Fire any EventType directly.  Supported values:
      user_skip, user_delay, user_pref, user_add, user_report,
      env_crowd, env_traffic, env_weather, venue_closed,
      user_dislike_next, user_replace_poi, user_skip_current,
      user_reorder, user_manual_reopt, user_hunger, user_fatigue
    """
    entry = get_session(req.session_id)
    session = entry["session"]

    try:
        event_type = EventType(req.event_type)
    except ValueError:
        valid = [e.value for e in EventType]
        raise HTTPException(
            status_code=422,
            detail=f"Unknown event_type '{req.event_type}'. Valid: {valid}",
        )

    try:
        new_plan = session.event(event_type, req.metadata)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "session_id": req.session_id,
        "new_plan":   _ser_dayplan(new_plan),
        "current_time": session.state.current_time,
    }


@router.get("/summary/{session_id}", summary="Get the full session diagnostic summary")
def summary(session_id: str) -> dict:
    """
    Returns visited stops, skipped stops, disruption log, threshold values,
    and DisruptionMemory records.
    """
    entry = get_session(session_id)
    session = entry["session"]

    try:
        return session.summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
