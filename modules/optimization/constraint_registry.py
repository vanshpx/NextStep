"""
modules/optimization/constraint_registry.py
---------------------------------------------
Central HC Registry: evaluates all hard constraints per POI type.

Resolution 2: Extended HC coverage across all POI categories.

For each POI type, returns a list of hcm_pti ∈ {0,1}.
HC_pti = Π hcm_pti  (Eq 1) — computed by caller via compute_HC().

Registered HC checks per category:

  ATTRACTION:
    hc1 — opening_hours gate
    hc2 — time-budget feasibility (elapsed + Dij + STi ≤ Tmax)
    hc3 — accessibility (wheelchair if required)
    hc4 — age restriction (min_age ≤ youngest traveller age)
    hc5 — permit required (ticket_required & permit_available)
    hc6 — group size (min_group_size ≤ group_size ≤ max_group_size)
    hc7 — seasonal closure (trip month must be in seasonal_open_months)
    hc8 — minimum visit duration feasible (remaining ≥ Dij + min_visit_duration)

  HOTEL:
    hc1 — price_per_night ≤ nightly_budget
    hc2 — availability on check_in date
    hc3 — accessibility (if required)
    hc4 — min_star_rating ≤ star_rating

  RESTAURANT:
    hc1 — dietary / cuisine match (cuisine_tags ∩ user_prefs ≠ ∅, or no prefs)
    hc2 — opening hours gate (must be open at planned meal time)
    hc3 — price_per_person ≤ per_meal_budget
    hc4 — accessibility (wheelchair if required)

  FLIGHT:
    hc1 — price ≤ flight_budget
    hc2 — travel_mode compatibility (direct vs connected)
    hc3 — departure within allowed time window
"""

from __future__ import annotations
from datetime import time as dtime
from modules.tool_usage.time_tool import TimeTool


# ─────────────────────────────────────────────────────────────────────────────
# Registry dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_hc(poi_type: str, poi_data: dict, context: dict) -> list[int]:
    """
    Evaluate all hard constraints for a given POI and return
    a list of hcm_pti ∈ {0,1} for use in compute_HC().

    Args:
        poi_type : "attraction" | "hotel" | "restaurant" | "flight"
        poi_data : Dict of POI fields (from *Record dataclass via __dict__ or manual).
        context  : Runtime context — traveller profile + scheduling state.

                   Required keys by type:
                     attraction: elapsed_min, Tmax_min, t_cur (time), traveller_ages (list[int]),
                                 requires_wheelchair, permit_available,
                                 group_size (int), trip_month (int 1-12)
                     hotel:      nightly_budget, check_in_date, requires_wheelchair,
                                 min_star_rating
                     restaurant: dietary_preferences (set[str]), t_cur (time),
                                 per_meal_budget, requires_wheelchair
                     flight:     flight_budget, allowed_modes (set[str]),
                                 earliest_dep (time), latest_dep (time)

    Returns:
        list[int] — one entry per constraint; 1=satisfied, 0=violated.
    """
    dispatch = {
        "attraction": _hc_attraction,
        "hotel":      _hc_hotel,
        "restaurant": _hc_restaurant,
        "flight":     _hc_flight,
    }
    fn = dispatch.get(poi_type)
    if fn is None:
        # Unknown type — pass-through (no HC applied)
        return [1]
    return fn(poi_data, context)


# ─────────────────────────────────────────────────────────────────────────────
# ATTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def _hc_attraction(poi: dict, ctx: dict) -> list[int]:
    results: list[int] = []

    # hc1 — opening hours
    oh = poi.get("opening_hours", "")
    t_cur: dtime = ctx.get("t_cur", dtime(9, 0))
    if oh and "-" in oh:
        parts = oh.split("-")
        within = TimeTool.is_within_window(t_cur, parts[0].strip(), parts[1].strip())
        results.append(1 if within else 0)
    else:
        results.append(1)  # unknown → allow

    # hc2 — time-budget feasibility (Tmax)
    elapsed   = ctx.get("elapsed_min", 0.0)
    Tmax      = ctx.get("Tmax_min", 480.0)
    Dij       = poi.get("Dij_minutes", 0.0)
    visit_dur = poi.get("visit_duration_minutes", 60.0)
    results.append(1 if elapsed + Dij + visit_dur <= Tmax else 0)

    # hc3 — accessibility
    if ctx.get("requires_wheelchair", False):
        results.append(1 if poi.get("wheelchair_accessible", True) else 0)
    else:
        results.append(1)  # not required → satisfied

    # hc4 — age restriction
    # Use the YOUNGEST traveller age; if traveler_ages is empty, skip check.
    traveler_ages: list[int] = ctx.get("traveler_ages", [])
    min_age: int = poi.get("min_age", 0)
    if traveler_ages and min_age > 0:
        youngest = min(traveler_ages)
        results.append(1 if youngest >= min_age else 0)
    else:
        results.append(1)  # no age data or no restriction → satisfied

    # hc5 — permit/ticket availability
    if poi.get("ticket_required", False):
        results.append(1 if ctx.get("permit_available", True) else 0)
    else:
        results.append(1)

    # hc6 — group size (venue capacity)
    group_size: int = ctx.get("group_size", 1)
    min_grp: int = poi.get("min_group_size", 1)
    max_grp: int = poi.get("max_group_size", 999)
    results.append(1 if min_grp <= group_size <= max_grp else 0)

    # hc7 — seasonal closure
    # If seasonal_open_months is non-empty, the trip month must be in the list.
    seasonal: list[int] = poi.get("seasonal_open_months", [])
    trip_month: int = ctx.get("trip_month", 0)  # 0 = unknown → allow
    if seasonal and trip_month:
        results.append(1 if trip_month in seasonal else 0)
    else:
        results.append(1)  # open all year or month unknown → allow

    # hc8 — minimum visit duration feasible
    # Remaining time after travel must accommodate at least the minimum visit length.
    min_visit: int = poi.get("min_visit_duration_minutes", 0)
    remaining_after_travel = Tmax - elapsed - Dij
    if min_visit > 0:
        results.append(1 if remaining_after_travel >= min_visit else 0)
    else:
        results.append(1)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# HOTEL
# ─────────────────────────────────────────────────────────────────────────────

def _hc_hotel(poi: dict, ctx: dict) -> list[int]:
    results: list[int] = []

    # hc1 — price_per_night ≤ nightly_budget
    price         = poi.get("price_per_night", 0.0)
    nightly_bgt   = ctx.get("nightly_budget", float("inf"))
    results.append(1 if price <= nightly_bgt else 0)

    # hc2 — availability on check_in date
    results.append(1 if poi.get("available", True) else 0)

    # hc3 — accessibility
    if ctx.get("requires_wheelchair", False):
        results.append(1 if poi.get("wheelchair_accessible", False) else 0)
    else:
        results.append(1)

    # hc4 — minimum star rating
    min_stars  = ctx.get("min_star_rating", 0)
    star_rating = poi.get("star_rating", 0)
    results.append(1 if star_rating >= min_stars else 0)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# RESTAURANT
# ─────────────────────────────────────────────────────────────────────────────

def _hc_restaurant(poi: dict, ctx: dict) -> list[int]:
    results: list[int] = []

    # hc1 — dietary / cuisine match
    # Pass if: user has no dietary preferences, OR cuisine tags overlap with preferences.
    user_prefs: set[str] = ctx.get("dietary_preferences", set())
    if user_prefs:
        poi_tags: list[str] = poi.get("cuisine_tags", [])
        cuisine_type: str   = poi.get("cuisine_type", "").lower()
        # Normalise: include cuisine_type as a tag for matching
        all_tags = {t.lower() for t in poi_tags} | {cuisine_type}
        # Match if ANY user preference appears in any tag (partial match OK)
        matched = any(
            any(pref.lower() in tag or tag in pref.lower() for tag in all_tags)
            for pref in user_prefs
        )
        results.append(1 if matched else 0)
    else:
        results.append(1)  # no preference → satisfied

    # hc2 — opening hours gate
    oh: str     = poi.get("opening_hours", "")
    t_cur: dtime = ctx.get("t_cur", dtime(12, 0))
    if oh and "-" in oh:
        parts = oh.split("-")
        within = TimeTool.is_within_window(t_cur, parts[0].strip(), parts[1].strip())
        results.append(1 if within else 0)
    else:
        results.append(1)  # unknown → allow

    # hc3 — price per person ≤ per-meal budget
    price    = poi.get("avg_price_per_person", 0.0)
    meal_bgt = ctx.get("per_meal_budget", float("inf"))
    results.append(1 if price <= meal_bgt else 0)

    # hc4 — accessibility
    if ctx.get("requires_wheelchair", False):
        results.append(1 if poi.get("wheelchair_accessible", True) else 0)
    else:
        results.append(1)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# FLIGHT
# ─────────────────────────────────────────────────────────────────────────────

def _hc_flight(poi: dict, ctx: dict) -> list[int]:
    results: list[int] = []

    # hc1 — total price ≤ flight budget
    price      = poi.get("price", 0.0)
    flight_bgt = ctx.get("flight_budget", float("inf"))
    results.append(1 if price <= flight_bgt else 0)

    # hc2 — travel mode compatibility (e.g. "direct" / "one_stop")
    allowed_modes: set[str] = ctx.get("allowed_modes", set())
    flight_mode:   str      = poi.get("stops_type", "direct")
    if allowed_modes:
        results.append(1 if flight_mode in allowed_modes else 0)
    else:
        results.append(1)

    # hc3 — departure within allowed time window
    early: dtime | None = ctx.get("earliest_dep")
    late:  dtime | None = ctx.get("latest_dep")
    dep_str: str        = poi.get("departure_time", "")
    if early and late and dep_str:
        results.append(
            1 if TimeTool.is_within_window(early, dep_str, late.strftime("%H:%M")) else 0
        )
    else:
        results.append(1)

    return results
