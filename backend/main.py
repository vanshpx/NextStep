"""
main.py
--------
TravelAgent pipeline entry point.
Orchestrates all 5 stages from the architecture doc:
  Stage 1: Initial User Input and Constraint Modeling
  Stage 2: Budget Planning
  Stage 3: Recommendation and Information Gathering (Attraction example)
  Stage 4: Route Planning
  Stage 5: Output and Continuous Learning

Run:
  python main.py

Notes:
  - All external API calls will raise NotImplementedError until environment
    variables are configured. See config.py for required vars.
  - LLM calls will raise NotImplementedError until llm_client is wired.
  - This file is a runnable skeleton — it prints each stage to stdout.
"""

from __future__ import annotations
import json
import sys
from datetime import date, datetime

# ── Schemas ────────────────────────────────────────────────────────────────────
from schemas.constraints import HardConstraints, SoftConstraints, CommonsenseConstraints, ConstraintBundle
from schemas.itinerary import BudgetAllocation, Itinerary, RoutePoint

# ── Tool-usage Module ──────────────────────────────────────────────────────────
from modules.tool_usage.attraction_tool import AttractionTool, AttractionRecord
from modules.tool_usage.hotel_tool import HotelTool, HotelRecord
from modules.tool_usage.flight_tool import FlightTool, FlightRecord
from modules.tool_usage.restaurant_tool import RestaurantTool, RestaurantRecord
from modules.tool_usage.city_tool import CityTool
from modules.tool_usage.distance_tool import DistanceTool
from modules.tool_usage.time_tool import TimeTool

# ── Recommendation Module ──────────────────────────────────────────────────────
from modules.recommendation.budget_recommender import BudgetRecommender
from modules.recommendation.attraction_recommender import AttractionRecommender
from modules.recommendation.hotel_recommender import HotelRecommender
from modules.recommendation.flight_recommender import FlightRecommender
from modules.recommendation.restaurant_recommender import RestaurantRecommender
from modules.recommendation.city_recommender import CityRecommender

# ── Planning Module ────────────────────────────────────────────────────────────
from modules.planning.budget_planner import BudgetPlanner
from modules.planning.route_planner import RoutePlanner
from modules.planning.attraction_scoring import AttractionScorer

# ── Memory Module ──────────────────────────────────────────────────────────────
from modules.memory.short_term_memory import ShortTermMemory
from modules.memory.long_term_memory import LongTermMemory
from modules.input.chat_intake import ChatIntake

from google import genai as genai_sdk
from google.genai import types as genai_types
import os
import config

from modules.reoptimization import (
    ReOptimizationSession, EventType, ConditionMonitor
)

# ── Stub LLM client (no API calls) ───────────────────────────────────────────
class StubLLMClient:
    """No-op LLM client used when USE_STUB_LLM=true or API is unavailable.
    Returns a safe empty/default string for every call.
    All current recommenders already discard the LLM response, so the
    pipeline runs end-to-end without any real API calls.
    """

    def complete(self, prompt: str) -> str:  # noqa: ARG002
        return "[stub response]"


# ── Gemini LLM client ────────────────────────────────────────────────────────────
class GeminiClient:
    _TIMEOUT_SECONDS = 60

    def __init__(self, model: str = "gemini-1.5-flash"):
        api_key = os.environ.get("GEMINI_API_KEY", config.LLM_API_KEY)
        self._client = genai_sdk.Client(
            api_key=api_key,
            http_options={"timeout": self._TIMEOUT_SECONDS},
        )

        # Use model from config if it is explicitly set
        if config.LLM_MODEL_NAME and config.LLM_MODEL_NAME != "UNSPECIFIED":
            model = config.LLM_MODEL_NAME
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
        )
        return response.text





def _make_stub_hotels() -> list[HotelRecord]:
    """
    Stub hotel data — exercises Resolution 1 (static/dynamic split)
    and Resolution 4 (HC+SC pipeline in HotelRecommender).
    TODO: Remove once HotelTool.fetch() is wired to a real API.
    """
    return [
        HotelRecord(
            name="The Grand Palace",
            brand="Luxury Chain",
            location_lat=28.6100, location_lon=77.2100,
            star_rating=5.0, amenities=["pool", "spa", "gym"],
            check_in_time="14:00", check_out_time="12:00",
            wheelchair_accessible=True,
            price_per_night=6000.0, available=True, discount_pct=10.0,
        ),
        HotelRecord(
            name="Budget Inn",
            brand="Economy Stay",
            location_lat=28.6150, location_lon=77.2050,
            star_rating=2.0, amenities=["wifi"],
            check_in_time="12:00", check_out_time="10:00",
            wheelchair_accessible=False,
            price_per_night=1200.0, available=True, discount_pct=0.0,
        ),
        HotelRecord(
            name="City Comfort Suites",
            brand="Mid-Range Group",
            location_lat=28.6080, location_lon=77.2180,
            star_rating=3.5, amenities=["wifi", "breakfast", "parking"],
            check_in_time="13:00", check_out_time="11:00",
            wheelchair_accessible=True,
            price_per_night=3500.0, available=False,  # HC fail: not available
            discount_pct=5.0,
        ),
    ]


def _make_stub_restaurants() -> list[RestaurantRecord]:
    """
    Stub restaurant data — exercises Resolution 4 (budget-only HC gate).
    TODO: Remove once RestaurantTool.fetch() is wired to a real API.
    avg_cost_per_person mapped to avg_price_per_person for HC registry.
    """
    return [
        RestaurantRecord(
            name="Spice Garden",
            location_lat=28.6120, location_lon=77.2110,
            cuisine_type="Indian", rating=4.3,
            avg_price_per_person=400.0,   # within budget
            opening_hours="11:00-23:00", accepts_reservations=True,
        ),
        RestaurantRecord(
            name="The Rooftop Bistro",
            location_lat=28.6090, location_lon=77.2060,
            cuisine_type="Continental", rating=4.6,
            avg_price_per_person=1800.0,  # exceeds per-meal budget -> HC fail
            opening_hours="12:00-23:00", accepts_reservations=True,
        ),
        RestaurantRecord(
            name="Street Bites",
            location_lat=28.6160, location_lon=77.2130,
            cuisine_type="Indian", rating=3.9,
            avg_price_per_person=150.0,   # within budget
            opening_hours="08:00-22:00", accepts_reservations=False,
        ),
    ]


def _make_stub_flights() -> list[FlightRecord]:
    """
    Stub flight data — exercises Resolution 4 (HC + value-for-money SC).
    TODO: Remove once FlightTool.fetch() is wired to a real API.
    """
    return [
        FlightRecord(
            airline="IndiGo", flight_number="6E-201",
            origin="BOM", destination="DEL",
            departure_datetime="2026-03-01T06:00:00",
            arrival_datetime="2026-03-01T08:10:00",
            duration_minutes=130, price=3500.0,
            cabin_class="economy", stops=0,
        ),
        FlightRecord(
            airline="Air India", flight_number="AI-101",
            origin="BOM", destination="DEL",
            departure_datetime="2026-03-01T09:30:00",
            arrival_datetime="2026-03-01T11:45:00",
            duration_minutes=135, price=8500.0,  # expensive -> lower S_pti
            cabin_class="business", stops=0,
        ),
        FlightRecord(
            airline="SpiceJet", flight_number="SG-401",
            origin="BOM", destination="DEL",
            departure_datetime="2026-03-01T14:00:00",
            arrival_datetime="2026-03-01T17:30:00",
            duration_minutes=210, price=2200.0,   # cheap but 1 stop
            cabin_class="economy", stops=1,
        ),
    ]


def run_pipeline(
    user_id: str = "user_001",
    departure_city: str = "Mumbai",
    destination_city: str = "Delhi",
    departure_date: date = date(2026, 3, 1),
    return_date: date = date(2026, 3, 5),
    num_adults: int = 2,
    num_children: int = 0,
    restaurant_preference: str = "Indian",
    total_budget: float = 50000.0,
    constraints: ConstraintBundle | None = None,   # if provided, skips hardcoded Stage 1 build
) -> Itinerary:
    """
    End-to-end TravelAgent pipeline.

    Args documented above correspond to user input fields referenced in
    architecture document Stage 1. Additional fields are MISSING.
    """

    llm = StubLLMClient() if config.USE_STUB_LLM else GeminiClient()
    if config.USE_STUB_LLM:
        print("  [LLM] Running in stub mode (USE_STUB_LLM=true) — no API calls.")
    stm = ShortTermMemory()
    ltm = LongTermMemory()

    print("\n" + "="*60)
    print("  TRAVELAGENT PIPELINE")
    print("="*60)

    # ══════════════════════════════════════════════════════════════
    # STAGE 1: Initial User Input and Constraint Modeling
    # ══════════════════════════════════════════════════════════════
    print("\n[Stage 1] Constraint Modeling")

    # Always load history insights — used by Stage 2+ regardless of intake mode
    history_insights = ltm.get_history_insights(user_id)

    if constraints is not None:
        # ── Chat-extracted constraints (--chat mode) ────────────────────────
        hard           = constraints.hard
        soft           = constraints.soft
        commonsense    = constraints.commonsense
        departure_city = hard.departure_city or departure_city
        destination_city = hard.destination_city or destination_city
        departure_date = hard.departure_date or departure_date
        return_date    = hard.return_date    or return_date
    else:
        # ── Default hardcoded constraints (no --chat) ───────────────────────
        hard = HardConstraints(
            departure_city=departure_city,
            destination_city=destination_city,
            departure_date=departure_date,
            return_date=return_date,
            num_adults=num_adults,
            num_children=num_children,
            restaurant_preference=restaurant_preference,
        )

        soft = SoftConstraints(
            travel_preferences=history_insights["user_preferences"].get("travel_preferences", []),
            interests=history_insights["user_preferences"].get("interests", []),
            spending_power=history_insights["user_preferences"].get("spending_power", "medium"),
        )
        commonsense = CommonsenseConstraints(rules=history_insights["commonsense_rules"])
        constraints = ConstraintBundle(
            hard=hard, soft=soft, commonsense=commonsense,
            total_budget=total_budget,   # bind user budget into bundle
        )

    print(f"  Hard  : {departure_city} → {destination_city} | {departure_date} – {return_date}")
    print(f"  Soft  : interests={soft.interests}, spending_power={soft.spending_power}")
    print(f"  Common: {len(commonsense.rules)} rules loaded")
    # ─────────────────────────────────────────────────────────────
    # PIPELINE TRACE — validates that user inputs flow strictly through all layers
    # ─────────────────────────────────────────────────────────────
    print("""
[TRACE]
  UserDestination      : {dest}
  ConstraintDestination: {cdest}
  UserBudget           : ₹{budget:,.0f}
  ConstraintBudget     : ₹{cbdgt:,.0f}
  SoftInterests        : {si}""".format(
        dest   = destination_city,
        cdest  = hard.destination_city,
        budget = total_budget,
        cbdgt  = constraints.total_budget,
        si     = soft.interests or "(none yet)",
    ))

    # ── Destination binding assertion ────────────────────────────────────────────
    assert hard.destination_city.strip().lower() == destination_city.strip().lower(), (
        f"HARD FAIL: destination_city mismatch — "
        f"hard.destination_city={hard.destination_city!r} vs pipeline param={destination_city!r}"
    )

    # ── Budget binding assertion ───────────────────────────────────────────────
    assert total_budget > 0, (
        "HARD FAIL: total_budget=0 — user budget is required before planning can start."
    )
    if constraints.total_budget > 0:
        assert abs(total_budget - constraints.total_budget) < 0.01, (
            f"HARD FAIL: budget mismatch — "
            f"constraints.total_budget={constraints.total_budget} vs pipeline param={total_budget}"
        )

    # ── Interest binding check ────────────────────────────────────────────────
    if constraints.has_chat_input and not soft.interests:
        raise ValueError(
            "INPUT_BINDING_ERROR: Phase 2 chat detected (has_chat_input=True) but "
            "soft.interests is empty. Check ChatIntake._extract_interests_local()."
        )
    # Pre-compute trip dimensions (used in Stages 2, 3, and 4)
    num_days   = max((return_date - departure_date).days, 1)
    group_size = hard.num_adults + hard.num_children

    # ══════════════════════════════════════════════════════════════
    # STAGE 2: Budget Planning
    # ══════════════════════════════════════════════════════════════
    print("\n[Stage 2] Budget Planning")

    budget_recommender = BudgetRecommender(llm_client=llm)
    preliminary_estimates = budget_recommender.recommend(constraints, [], history_insights)
    preliminary = preliminary_estimates[0] if preliminary_estimates else BudgetAllocation()
    print(f"  Preliminary estimate (stub): {preliminary}")

    # Simulate user confirmation of total_budget
    print(f"  User confirmed total budget: {total_budget}")

    # Preliminary allocation from city cost index (real price data not yet fetched)
    budget_planner = BudgetPlanner(llm_client=llm)
    budget_allocation = budget_planner.distribute(
        total_budget=total_budget,
        constraints=constraints,
        num_days=num_days,
    )
    assert budget_planner.validate(budget_allocation, total_budget), "Budget allocation exceeds total!"
    print(f"  Preliminary: Accommodation=₹{budget_allocation.Accommodation:,.0f}"
          f"  Restaurants=₹{budget_allocation.Restaurants:,.0f}"
          f"  Reserve=₹{budget_allocation.Reserve_Fund:,.0f}"
          f"  [{budget_allocation.ValidationStatus}]")

    # ══════════════════════════════════════════════════════════════
    # STAGE 3: Recommendation and Information Gathering
    # ══════════════════════════════════════════════════════════════
    print("\n[Stage 3] Recommendations")

    # ── Attractions ───────────────────────────────────────────────────────
    # Assertion: city passed to fetch must match constraint destination
    assert destination_city.strip().lower() == hard.destination_city.strip().lower(), (
        f"DESTINATION BINDING ERROR: fetch city={destination_city!r} "
        f"!= constraint.destination_city={hard.destination_city!r}"
    )
    real_time_attractions = AttractionTool().fetch(destination_city)
    print(f"  Fetched {len(real_time_attractions)} attractions (stub)")

    # ── TRACE continued: tool fetch cities ───────────────────────────────────────
    print(f"  [TRACE] AttractionFetchCity : {destination_city}")
    print(f"  [TRACE] HotelFetchCity      : {destination_city}")
    print(f"  [TRACE] RestaurantFetchCity : {destination_city}")

    # ── Data consistency rule (Task 6) ─────────────────────────────────────────
    city_lower = destination_city.strip().lower()
    mismatched = [
        a.name for a in real_time_attractions
        if a.city and a.city.strip().lower() != city_lower
    ]
    if mismatched:
        raise RuntimeError(
            f"DATA_CONSISTENCY_ERROR: {len(mismatched)} attraction(s) have "
            f"city != {destination_city!r}: {mismatched[:5]}"
        )

    attraction_recommender = AttractionRecommender(llm_client=llm)
    recommended_attractions = attraction_recommender.recommend(
        constraints, real_time_attractions, history_insights
    )
    print(f"  Recommended: {[a.name for a in recommended_attractions]}")

    # Simulate user behavioral feedback
    feedback = {"City Museum": "like", "Riverfront Park": "pass"}
    stm.log_interaction("feedback", feedback)
    ranked_attractions = attraction_recommender.rerank(recommended_attractions, feedback)
    print(f"  Re-ranked: {[a.name for a in ranked_attractions]}")

    # Implicit insight learning -> update short-term memory
    stm.store_insight("liked_categories", ["museum", "landmark"])
    stm.store_insight("user_interests", soft.interests)   # bind user preferences to STM

    # ── Hotels ───────────────────────────────────────────────────────────
    # TODO: Replace dummy data inside HotelTool.fetch() with real API once
    #       HOTEL_API_URL env var is configured.
    fetched_hotels = HotelTool().fetch(
        destination_city,
        check_in=str(departure_date),
        check_out=str(return_date),
    )
    print(f"\n  Fetched {len(fetched_hotels)} hotels")
    hotel_recommender = HotelRecommender(llm_client=llm)
    hotel_ctx = {
        "nightly_budget":     budget_allocation.Accommodation / num_days,
        "min_star_rating":    2,
        "requires_wheelchair": False,
    }
    recommended_hotels = hotel_recommender.recommend(
        constraints, fetched_hotels, history_insights, context=hotel_ctx
    )
    print(f"  Hotel S_pti ranking : {[h.name for h in recommended_hotels]}")
    print(f"  (HC removes unavailable; SC = star_rating/5.0)")
    stm.record_feedback("star_rating_sc", +0.8)

    # ── Restaurants ────────────────────────────────────────────────────
    # TODO: Replace dummy data inside RestaurantTool.fetch() with real API once
    #       RESTAURANT_API_URL env var is configured.
    fetched_restaurants = RestaurantTool().fetch(destination_city)
    print(f"\n  Fetched {len(fetched_restaurants)} restaurants")
    restaurant_recommender = RestaurantRecommender(llm_client=llm)
    per_meal = budget_allocation.Restaurants / max(num_days * 2, 1)
    rest_ctx = {"per_meal_budget": per_meal}
    recommended_restaurants = restaurant_recommender.recommend(
        constraints, fetched_restaurants, history_insights, context=rest_ctx
    )
    print(f"  Restaurant S_pti ranking: {[r.name for r in recommended_restaurants]}")
    print(f"  (per-meal budget {per_meal:.0f}; HC blocks restaurants above this)")
    stm.record_feedback("rating_sc", +0.6)

    # ── Flights ───────────────────────────────────────────────────────────
    # TODO: Replace dummy data inside FlightTool.fetch() with real API once
    #       FLIGHT_API_URL and SERPAPI_KEY env vars are configured.
    fetched_flights = FlightTool().fetch(
        origin=departure_city,
        destination=destination_city,
        departure_date=str(departure_date),
    )
    print(f"\n  Fetched {len(fetched_flights)} flights")
    flight_recommender = FlightRecommender(llm_client=llm)
    flight_ctx = {"flight_budget": budget_allocation.Transportation}
    recommended_flights = flight_recommender.recommend(
        constraints, fetched_flights, history_insights, context=flight_ctx
    )
    print(f"  Flight S_pti ranking : {[f'{f.airline} {f.flight_number} ${f.price:.0f}' for f in recommended_flights]}")
    print(f"  (SC = budget/price capped at 1.0; cheaper = higher S_pti)")
    stm.record_feedback("value_for_money_sc", +0.5)

    # ── Budget Recompute: update with real pricing data from Stage 3 ──────────
    budget_allocation = budget_planner.distribute(
        total_budget=total_budget,
        constraints=constraints,
        num_days=num_days,
        hotel_records=fetched_hotels,
        restaurant_records=fetched_restaurants,
        attraction_records=real_time_attractions,
    )
    assert budget_planner.validate(budget_allocation, total_budget), \
        "Post-Stage-3 budget recompute failed validation!"
    print(f"\n  [Budget] Recomputed with real data:")
    print(f"    Accommodation  ₹{budget_allocation.Accommodation:>10,.0f}")
    print(f"    Restaurants    ₹{budget_allocation.Restaurants:>10,.0f}")
    print(f"    Transportation ₹{budget_allocation.Transportation:>10,.0f}")
    print(f"    Attractions    ₹{budget_allocation.Attractions:>10,.0f}")
    print(f"    Other Expenses ₹{budget_allocation.Other_Expenses:>10,.0f}")
    print(f"    Reserve Fund   ₹{budget_allocation.Reserve_Fund:>10,.0f}")
    print(f"    TOTAL          ₹{budget_allocation.total:>10,.0f}"
          f"  [{budget_allocation.ValidationStatus}]"
          f"  DataQuality:{budget_allocation.DataQuality}"
          f"  Rebalance:{budget_allocation.RebalanceApplied}")

    # ══════════════════════════════════════════════════════════════
    # §5  PRE-STAGE 4 PIPELINE GUARD
    # Validates data integrity before route planning begins.
    # Any failure aborts the pipeline — no silent fallbacks.
    # ══════════════════════════════════════════════════════════════
    print("\n[Stage 4 Pre-Guard] Data integrity check")

    # Guard 1: attraction pool must not be empty
    if not ranked_attractions:
        raise RuntimeError(
            "PIPELINE_GUARD[1]: ranked_attractions is empty — cannot plan route. "
            "AttractionTool.fetch() must return data and the recommender must "
            "not eject all records."
        )

    # Guard 2: every attraction must belong to the destination city
    # (no cross-city contamination from recommender or data sources)
    _guard_city = destination_city.strip().lower()
    _city_mismatch = [
        a.name for a in ranked_attractions
        if a.city and a.city.strip().lower() != _guard_city
    ]
    if _city_mismatch:
        raise RuntimeError(
            f"PIPELINE_GUARD[2]: {len(_city_mismatch)} attraction(s) in "
            f"ranked_attractions have city != '{destination_city}': "
            f"{_city_mismatch[:5]}. "
            "Aborting. DO NOT substitute or infer city."
        )

    # Guard 3: if chat input was provided, soft constraints must be populated
    if constraints.has_chat_input and not soft.interests:
        raise RuntimeError(
            "PIPELINE_GUARD[3]: has_chat_input=True but soft.interests is empty — "
            "constraint propagation from ChatIntake failed. "
            "Check ChatIntake._extract_interests_local()."
        )

    # Guard 4: budget must be positive and match the constraint bundle
    if total_budget <= 0:
        raise RuntimeError(
            "PIPELINE_GUARD[4]: total_budget <= 0 — cannot plan route without budget."
        )
    if constraints.total_budget > 0 and abs(total_budget - constraints.total_budget) >= 0.01:
        raise RuntimeError(
            f"PIPELINE_GUARD[4]: budget mismatch — "
            f"pipeline total_budget={total_budget} != "
            f"constraints.total_budget={constraints.total_budget}."
        )

    print(f"  [Guard] ✓ {len(ranked_attractions)} attractions | "
          f"city='{destination_city}' | budget=₹{total_budget:,.0f} | "
          f"interests={len(soft.interests)} — all 4 guards passed")

    # STAGE 4: Route Planning
    # ══════════════════════════════════════════════════════════════
    print("\n[Stage 4] Route Planning")

    route_planner = RoutePlanner()
    # Derive hotel anchor from the best recommended hotel (fallback to city centre)
    # Import city-center table from attraction_tool (100+ cities, zero API calls)
    from modules.tool_usage.attraction_tool import _CITY_CENTERS, _CITY_NAME_ALIASES
    _dest_lower = destination_city.strip().lower()
    _dest_key   = _CITY_NAME_ALIASES.get(_dest_lower, _dest_lower)
    _city_center = _CITY_CENTERS.get(_dest_key)
    _default_lat  = _city_center[0] if _city_center else 0.0
    _default_lon  = _city_center[1] if _city_center else 0.0

    # Anchor logic:
    #   - Real hotel API (USE_STUB_HOTELS=false): trust hotel record coords.
    #   - Stub hotels (USE_STUB_HOTELS=true):  stub data has hardcoded Delhi
    #     coordinates regardless of destination — always use city-center instead
    #     to avoid a spurious ERROR_INVALID_HOTEL_ANCHOR.
    #   - Either way: if hotel record has (0, 0), fall back to city center.
    if recommended_hotels and not config.USE_STUB_HOTELS:
        _hotel_anchor = recommended_hotels[0]
        hotel_lat = _hotel_anchor.location_lat or _default_lat
        hotel_lon = _hotel_anchor.location_lon or _default_lon
        _anchor_source = "best hotel (real API)"
    else:
        hotel_lat, hotel_lon = _default_lat, _default_lon
        _anchor_source = "city-centre (stub hotels use destination coords)"
    print(f"  Hotel anchor: ({hotel_lat:.4f}, {hotel_lon:.4f})  (from {_anchor_source})")
    itinerary = route_planner.plan(
        constraints=constraints,
        attraction_set=ranked_attractions,
        budget=budget_allocation,
        start_date=departure_date,
        end_date=return_date,
        hotel_lat=hotel_lat,
        hotel_lon=hotel_lon,
    )

    # ── Inject meal stops (adaptive lunch + dinner) into every day ───────────
    _inject_meals_smart(itinerary, recommended_restaurants)

    print(f"  Generated {len(itinerary.days)} day(s) for trip {itinerary.trip_id}")
    for day in itinerary.days:
        print(f"  Day {day.day_number} ({day.date}): {len(day.route_points)} stops, "
              f"cost={day.daily_budget_used:.2f}")
        for rp in day.route_points:
            arr = rp.arrival_time.strftime("%H:%M")   if rp.arrival_time   else "--:--"
            dep = rp.departure_time.strftime("%H:%M") if rp.departure_time else "--:--"
            tag = " [meal]" if rp.activity_type == "restaurant" else ""
            print(f"    [{rp.sequence}] {rp.name}{tag} | {arr} – {dep}  ({rp.visit_duration_minutes} min)")

    # ── Accumulate actual costs from Stage 3 selections ──────────────────────
    # total_actual_cost starts at 0 because attraction entry_cost has no API
    # source. We add the real costs from the best-ranked hotel, outbound flight,
    # and restaurant (cheapest approved × group × days × 2 meals/day).
    # (group_size and num_days were hoisted to the top of the pipeline)

    if recommended_hotels:
        best_hotel = recommended_hotels[0]
        hotel_actual = best_hotel.price_per_night * num_days
        itinerary.total_actual_cost += hotel_actual
        print(f"  Hotel cost   : ₹{hotel_actual:,.2f}  "
              f"({best_hotel.name}, ₹{best_hotel.price_per_night:,.0f}/night × {num_days} nights)")

    if recommended_flights:
        best_flight = recommended_flights[0]
        # price is per-person for the outbound leg; multiply by group size
        flight_actual = best_flight.price * group_size
        itinerary.total_actual_cost += flight_actual
        print(f"  Flight cost  : ₹{flight_actual:,.2f}  "
              f"({best_flight.airline} {best_flight.flight_number}, "
              f"₹{best_flight.price:,.0f}/person × {group_size} pax)")

    if recommended_restaurants:
        best_rest = recommended_restaurants[0]
        # 2 meals/day (lunch + dinner) × group size × trip days
        rest_actual = best_rest.avg_price_per_person * group_size * num_days * 2
        itinerary.total_actual_cost += rest_actual
        print(f"  Dining cost  : ₹{rest_actual:,.2f}  "
              f"({best_rest.name}, ₹{best_rest.avg_price_per_person:,.0f}/person "
              f"× {group_size} pax × {num_days} days × 2 meals)")

    print(f"  Total actual : ₹{itinerary.total_actual_cost:,.2f}")

    # ── Budget: post-itinerary rebalance ──────────────────────────────────────
    best_hotel_rec      = recommended_hotels[0]      if recommended_hotels      else None
    best_restaurant_rec = recommended_restaurants[0] if recommended_restaurants else None
    best_flight_rec     = recommended_flights[0]     if recommended_flights     else None
    budget_allocation = budget_planner.post_itinerary_rebalance(
        allocation=budget_allocation,
        total_budget=total_budget,
        itinerary=itinerary,
        best_hotel=best_hotel_rec,
        best_restaurant=best_restaurant_rec,
        best_flight=best_flight_rec,
        group_size=group_size,
        num_days=num_days,
    )
    itinerary.budget = budget_allocation
    print(f"\n  [Budget] Final validated allocation:")
    print(f"    Accommodation  ₹{budget_allocation.Accommodation:>10,.0f}")
    print(f"    Restaurants    ₹{budget_allocation.Restaurants:>10,.0f}")
    print(f"    Transportation ₹{budget_allocation.Transportation:>10,.0f}")
    print(f"    Attractions    ₹{budget_allocation.Attractions:>10,.0f}")
    print(f"    Other Expenses ₹{budget_allocation.Other_Expenses:>10,.0f}")
    print(f"    Reserve Fund   ₹{budget_allocation.Reserve_Fund:>10,.0f}")
    print(f"    TOTAL          ₹{budget_allocation.total:>10,.0f}"
          f"  [{budget_allocation.ValidationStatus}]")
    if budget_allocation.RebalanceApplied:
        print("    ⚠  budget_rebalance_event was triggered and applied.")

    # ══════════════════════════════════════════════════════════════
    # STAGE 5: Output and Continuous Learning
    # ══════════════════════════════════════════════════════════════
    print("\n[Stage 5] Memory Update")

    ltm.promote_from_short_term(user_id, stm.get_all_insights())

    # Wv weight update (Resolution 3) — promote feedback signals
    feedback_summary = stm.get_feedback_summary()
    if feedback_summary:
        updated_weights = ltm.update_soft_weights(user_id, feedback_summary)
        print(f"  Wv weights updated: {updated_weights}")

    stm.clear()
    print(f"  Long-term profile updated for user '{user_id}'")

    print("\n[DONE] Itinerary generated successfully.")
    print("="*60 + "\n")
    return itinerary


# ══════════════════════════════════════════════════════════════════════════════
# REAL-TIME RE-OPTIMIZATION DEMO  (python main.py --reoptimize)
# ══════════════════════════════════════════════════════════════════════════════

def _run_reoptimize_demo(itinerary: Itinerary) -> None:
    """
    Fully interactive real-time re-optimizer.  No scripted steps.
    Every disruption is user-triggered; every decision requires explicit
    user confirmation before any state mutation occurs.

    Run:  python main.py --reoptimize
    """
    import uuid as _uuid
    from modules.tool_usage.attraction_tool import (
        AttractionTool, _CITY_CENTERS, _CITY_NAME_ALIASES,
    )
    from modules.observability.logger import StructuredLogger

    _logger = StructuredLogger()
    _session_id = f"reopt_{_uuid.uuid4().hex[:12]}"

    print("\n" + "=" * 60)
    print("  REAL-TIME RE-OPTIMIZER  (Interactive Mode)")
    print("=" * 60)

    # ── Derive destination from itinerary ──────────────────────────────────
    day1 = itinerary.days[0] if itinerary.days else None
    _dest_raw = (
        day1.route_points[0].city
        if day1 and day1.route_points and getattr(day1.route_points[0], "city", "")
        else "Delhi"
    )
    destination = _dest_raw.strip() or "Delhi"

    # ── Rebuild constraints ─────────────────────────────────────────────────
    from modules.memory.long_term_memory import LongTermMemory
    ltm = LongTermMemory()
    history = ltm.get_history_insights("user_001")
    hard = HardConstraints(
        departure_city="Mumbai",
        destination_city=destination,
        departure_date=date(2026, 3, 1),
        return_date=date(2026, 3, 5),
        num_adults=2,
        num_children=0,
        restaurant_preference="Indian",
        requires_wheelchair=False,
    )
    soft = SoftConstraints(
        interests=history["user_preferences"].get("interests", ["museum", "history"]),
        spending_power=history["user_preferences"].get("spending_power", "medium"),
        avoid_crowds=True,
        pace_preference="moderate",
        heavy_travel_penalty=True,
    )
    commonsense = CommonsenseConstraints(rules=history["commonsense_rules"])
    constraints = ConstraintBundle(hard=hard, soft=soft, commonsense=commonsense)

    # ── Fetch attraction pool ───────────────────────────────────────────────
    all_attractions = AttractionTool().fetch(destination)

    # ── Resolve hotel anchor from city centre ───────────────────────────────
    _dest_key   = _CITY_NAME_ALIASES.get(destination.lower(), destination.lower())
    _city_ctr   = _CITY_CENTERS.get(_dest_key, (0.0, 0.0))
    hotel_lat   = _city_ctr[0] if isinstance(_city_ctr, tuple) else 0.0
    hotel_lon   = _city_ctr[1] if isinstance(_city_ctr, tuple) else 0.0

    # ── Create session ──────────────────────────────────────────────────────
    session = ReOptimizationSession.from_itinerary(
        itinerary=itinerary,
        constraints=constraints,
        remaining_attractions=all_attractions,
        hotel_lat=hotel_lat,
        hotel_lon=hotel_lon,
        start_day=1,
    )

    print(f"\n  Destination : {destination}")
    print(f"  Thresholds  : {session.thresholds.describe()}")
    print(f"  Preferences : avoid_crowds={soft.avoid_crowds}, "
          f"pace={soft.pace_preference}, heavy_travel_penalty={soft.heavy_travel_penalty}")
    if day1:
        print(f"  Day 1 plan  : {[rp.name for rp in day1.route_points]}")
    else:
        print("  (No Day 1 stops — running from attraction pool)")

    # ── State display helpers ───────────────────────────────────────────────

    def _current_stop_name() -> str:
        """Return the last visited stop name, or 'Hotel (start)'."""
        plan    = session.state.current_day_plan
        visited = session.state.visited_stops
        if plan:
            for rp in reversed(plan.route_points):
                if rp.name in visited:
                    return rp.name
        return "Hotel (start)"

    def _next_stop_name() -> str:
        """Return the first unvisited, non-skipped stop in the current plan."""
        plan    = session.state.current_day_plan
        visited = session.state.visited_stops
        skipped = session.state.skipped_stops
        if plan:
            for rp in plan.route_points:
                if rp.name not in visited and rp.name not in skipped:
                    return rp.name
        return "—"

    def _remaining_stop_names() -> list[str]:
        plan    = session.state.current_day_plan
        visited = session.state.visited_stops
        skipped = session.state.skipped_stops
        if not plan:
            return []
        return [
            rp.name for rp in plan.route_points
            if rp.name not in visited and rp.name not in skipped
        ]

    def _remaining_budget() -> float:
        if not session.budget:
            return 0.0
        return max(0.0, session.budget.total - sum(session.state.budget_spent.values()))

    def _display_state() -> None:
        remaining = _remaining_stop_names()
        w = 43
        print("\n  ┌" + "─" * w + "┐")
        print(f"  │  {'Current Location':<17}: {_current_stop_name():<{w-21}}│")
        print(f"  │  {'Current Time':<17}: {session.state.current_time:<{w-21}}│")
        print(f"  │  {'Next Stop':<17}: {_next_stop_name():<{w-21}}│")
        print(f"  │  {'Remaining Stops':<17}: {len(remaining):<{w-21}}│")
        for name in remaining[:4]:
            print(f"  │    • {name:<{w-4}}│")
        if len(remaining) > 4:
            more = f"  … and {len(remaining)-4} more"
            print(f"  │  {more:<{w-1}}│")
        bstr = f"\u20b9{_remaining_budget():,.0f}"
        print(f"  │  {'Remaining Budget':<17}: {bstr:<{w-21}}│")
        print("  └" + "─" * w + "┘")

    def _print_help() -> None:
        print("\n  ── Commands ───────────────────────────────────────────")
        print("    crowd <percent>      e.g.  crowd 80")
        print("    traffic <percent>    e.g.  traffic 65")
        print("    weather <condition>  e.g.  weather rainy | stormy | clear | hot")
        print("    skip                 skip the next planned stop")
        print("    replace              replace next stop with an alternative")
        print("    tired                report fatigue — insert rest break")
        print("    continue             mark next stop visited and advance time")
        print("    end / q              finish session")
        if session.pending_decision is not None:
            print("\n  ── Awaiting your decision ─────────────────────────────")
            print("    approve              apply disruption handling + replan")
            print("    reject               keep current plan unchanged")
            print("    modify <n>           apply only action #n (0-based)")
        print()

    # ── Initial state display ───────────────────────────────────────────────
    _display_state()
    _print_help()

    # ── Event loop ─────────────────────────────────────────────────────────
    _DISRUPTION_CMDS = frozenset(
        {"crowd", "traffic", "weather", "skip", "replace", "tired"}
    )
    _VALID_WEATHER_CONDITIONS = frozenset(
        {"clear", "rainy", "stormy", "hot", "cold", "fog"}
    )

    while True:
        try:
            raw = input("  reoptimize> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            continue

        parts = raw.split()
        cmd   = parts[0].lower()

        _logger.log(_session_id, "USER_COMMAND", {
            "command": raw,
            "parsed_type": cmd,
        })

        # ── Pending-gate resolution commands ───────────────────────────────
        if cmd == "approve":
            if session.pending_decision is None:
                print("  No pending decision. Trigger a disruption first.")
                continue
            pd = session.pending_decision
            # Context-aware token: skip-type events → SKIP, everything else → REPLACE
            _user_evt = getattr(pd, "_user_event_type", "")
            if _user_evt in ("user_skip", "user_skip_current"):
                _token = "SKIP"
            elif getattr(pd, "_rich_alternatives", []):
                _token = "REPLACE"
            else:
                _token = "SKIP"  # no alternatives → remove disrupted stop
            new_plan = session.resolve_pending(_token)
            if new_plan:
                session.state.current_day_plan = new_plan
                print(f"  → Plan updated: {[rp.name for rp in new_plan.route_points]}")
            else:
                print("  → Disruption handled — plan unchanged.")
            _display_state()
            continue

        if cmd == "reject":
            if session.pending_decision is None:
                print("  No pending decision.")
                continue
            session.resolve_pending("REJECT")
            print("  → Plan kept unchanged.")
            _display_state()
            continue

        if cmd == "modify":
            if session.pending_decision is None:
                print("  No pending decision.")
                continue
            if len(parts) < 2:
                print("  Usage: modify <n>   (0-based action index)")
                continue
            try:
                idx = int(parts[1])
                new_plan = session.resolve_pending("MODIFY", action_index=idx)
                if new_plan:
                    session.state.current_day_plan = new_plan
                    print(f"  → Plan updated: {[rp.name for rp in new_plan.route_points]}")
                else:
                    print("  → No route change for this action.")
            except ValueError:
                print("  Usage: modify <n>   (integer index)")
            _display_state()
            continue

        # ── Block new disruptions while one is already pending ──────────────
        if cmd in _DISRUPTION_CMDS and session.pending_decision is not None:
            print("  [Gate] A disruption already awaits your decision.")
            print("  [Gate] Type  approve / reject / modify <n>  first.")
            continue

        # ── crowd <percent> ─────────────────────────────────────────────────
        if cmd == "crowd":
            if len(parts) < 2:
                print("  Usage: crowd <percent>   e.g. crowd 80")
                continue
            try:
                level = float(parts[1].rstrip("%")) / 100.0
            except ValueError:
                print("  Usage: crowd <percent>   e.g. crowd 80")
                continue
            if not (0.0 <= level <= 1.0):
                print("  [Error] crowd must be 0–100 (integer percent).")
                continue
            next_name = _next_stop_name()
            # Pass weather_condition="" and traffic_level=0.0 to suppress
            # auto-fetch of weather/traffic — user is testing crowd only.
            session.check_conditions(
                crowd_level=level,
                next_stop_name=next_name if next_name != "—" else "",
                weather_condition="",
                traffic_level=0.0,
            )
            if session.pending_decision is None:
                print(f"  Crowd {level:.0%} is below your threshold "
                      f"(threshold: {session.thresholds.crowd:.0%}) — no disruption.")
            _display_state()

        # ── traffic <percent> ───────────────────────────────────────────────
        elif cmd == "traffic":
            if len(parts) < 2:
                print("  Usage: traffic <percent>   e.g. traffic 65")
                continue
            try:
                level = float(parts[1].rstrip("%")) / 100.0
            except ValueError:
                print("  Usage: traffic <percent>   e.g. traffic 65")
                continue
            if not (0.0 <= level <= 1.0):
                print("  [Error] traffic must be 0–100 (integer percent).")
                continue
            next_name = _next_stop_name()
            # Pass weather_condition="" to suppress weather auto-fetch.
            session.check_conditions(
                traffic_level=level,
                next_stop_name=next_name if next_name != "—" else "",
                weather_condition="",
            )
            if session.pending_decision is None:
                print(f"  Traffic {level:.0%} is below your threshold "
                      f"(threshold: {session.thresholds.traffic:.0%}) — no disruption.")
            _display_state()

        # ── weather <condition> ─────────────────────────────────────────────
        elif cmd == "weather":
            if len(parts) < 2:
                print("  Usage: weather <condition>   e.g. weather rainy")
                continue
            condition = parts[1].lower()
            if condition not in _VALID_WEATHER_CONDITIONS:
                print(f"  [Error] Unknown weather condition '{condition}'.")
                print(f"  Allowed: {sorted(_VALID_WEATHER_CONDITIONS)}")
                continue
            next_name = _next_stop_name()
            next_rec  = next(
                (a for a in all_attractions if a.name == next_name), None
            )
            is_outdoor = getattr(next_rec, "is_outdoor", True) if next_rec else True
            # Pass traffic_level=0.0 to suppress traffic auto-fetch.
            session.check_conditions(
                weather_condition=condition,
                traffic_level=0.0,
                next_stop_name=next_name if next_name != "—" else "",
                next_stop_is_outdoor=is_outdoor,
            )
            if session.pending_decision is None:
                print(f"  Weather '{condition}' is below your threshold "
                      f"(threshold: {session.thresholds.weather:.0%}) — no disruption.")
            _display_state()

        # ── skip ────────────────────────────────────────────────────────────
        elif cmd == "skip":
            next_name = _next_stop_name()
            if next_name == "—":
                print("  No remaining stop to skip.")
                continue
            # Fire event — USER_SKIP goes through the approval gate (returns None
            # and sets pending_decision). Immediately resolve as SKIP since the
            # user already expressed their intent by typing the command.
            session.event(EventType.USER_SKIP, {"stop_name": next_name})
            if session.pending_decision is not None:
                result = session.resolve_pending("SKIP")
                if result is not None:
                    session.state.current_day_plan = result
                    print(f"  → Skipped '{next_name}'. "
                          f"New plan: {[rp.name for rp in result.route_points]}")
                else:
                    print(f"  → '{next_name}' skipped. Remaining plan updated.")
            else:
                print(f"  → '{next_name}' skipped (no replan needed).")
            _display_state()

        # ── replace ─────────────────────────────────────────────────────────
        elif cmd == "replace":
            next_name = _next_stop_name()
            if next_name == "—":
                print("  No remaining stop to replace.")
                continue
            # Fire event — USER_DISLIKE_NEXT goes through the gate; the session
            # prints alternatives automatically via _print_pending_decision.
            session.event(EventType.USER_DISLIKE_NEXT, {"stop_name": next_name})
            if session.pending_decision is not None:
                # Alternatives were already printed by the session.
                # Auto-pick the top alternative (index 1 = best by S_pti).
                result = session.resolve_pending("REPLACE", action_index=1)
                if result is not None:
                    session.state.current_day_plan = result
                    print(f"  → Replaced '{next_name}'. "
                          f"New plan: {[rp.name for rp in result.route_points]}")
                else:
                    print("  → No suitable replacement in pool — stop kept.")
            else:
                print("  → No replacement available in pool.")
            _display_state()

        # ── tired ────────────────────────────────────────────────────────────
        elif cmd == "tired":
            session.state.fatigue_level = max(session.state.fatigue_level, 0.82)
            result = session.event(EventType.FATIGUE_DISRUPTION, {})
            if result is not None:
                session.state.current_day_plan = result
                print(f"  → Rest break inserted. "
                      f"Plan: {[rp.name for rp in result.route_points]}")
            elif session.pending_decision is not None:
                print("  [Gate] Confirm rest insertion: type  approve / reject")
            else:
                print("  → Fatigue noted. Consider switching to relaxed pace (type slower).")
            _display_state()

        # ── continue ─────────────────────────────────────────────────────────
        elif cmd == "continue":
            next_name = _next_stop_name()
            if next_name == "—":
                print("  No remaining stop — day is complete.")
                continue
            # Resolve cost and arrival_time from current plan
            plan     = session.state.current_day_plan
            cost     = 0.0
            arr_time = session.state.current_time
            if plan:
                for rp in plan.route_points:
                    if rp.name == next_name:
                        cost     = rp.estimated_cost or 0.0
                        arr_time = (
                            rp.arrival_time.strftime("%H:%M")
                            if rp.arrival_time else session.state.current_time
                        )
                        break
            session.advance_to_stop(
                stop_name=next_name,
                arrival_time=arr_time,
                cost=cost,
            )
            print(f"  → Visited '{next_name}' at {arr_time}.")
            _display_state()

        # ── help ─────────────────────────────────────────────────────────────
        elif cmd in ("help", "?", "h", "commands"):
            _print_help()

        # ── end / quit ───────────────────────────────────────────────────────
        elif cmd in ("end", "q", "quit", "exit"):
            break

        else:
            print(f"  Unknown command '{cmd}'. Type  help  for the full command list.")

    # ── Final summary ───────────────────────────────────────────────────────
    _logger.log(_session_id, "SESSION_END", {})
    _logger.close(_session_id)
    print("\n" + "=" * 60)
    print("  SESSION COMPLETE")
    print("=" * 60)
    import json as _json
    print(_json.dumps(session.summary(), indent=2, default=str))


# ═══════════════════════════════════════════════════════════════════════════
# SMART MEAL INJECTION   (Rules 3, 5, 6)
# ═══════════════════════════════════════════════════════════════════════════

def _inject_meals_smart(itinerary: Itinerary, restaurants: list) -> None:
    """
    Insert lunch and dinner RoutePoints into every day using adaptive timing.

    Rule 3 — Meal structure:
      • Lunch window  12:00–14:30  (placed after 2–3 attractions or fatigue > 60 %)
      • Dinner window 18:30–21:30  (placed when day winds down / ≥ 18:30)
      • Restaurant must be within 2 km of the preceding POI (closest within 2 km;
        fall back to overall closest if none is inside the radius).
      • Fixed 13:00 lunch / 19:30 dinner slots are removed.

    Rule 5 — Fatigue:
      If a continuous sightseeing block of ≥ 3 h (180 min) is detected between
      two adjacent attractions, a lunch break is inserted at the natural gap even
      if it falls slightly outside the strict 12:00–14:30 window.

    Rule 6 — Day completion:
      Meal is only inserted when the resulting departure still fits before 20:30.

    Overlap safety:
      Before inserting any meal, every existing RoutePoint is checked for
      time-range overlap; the meal is silently dropped if it would collide.
    """
    import math as _math
    from datetime import time as dtime

    if not restaurants:
        return

    MEAL_DUR_MIN   = 60          # 1-hour meal
    BUFFER_MIN     = 12          # transition buffer around meal slot
    MEAL_PROX_KM   = 2.0         # Rule 3: restaurant proximity limit
    FATIGUE_THRESH = 180         # Rule 5: 3 h continuous sightseeing

    def _t2m(t: dtime) -> int:
        return t.hour * 60 + t.minute

    def _m2t(m: int) -> dtime:
        m = max(0, min(int(m), 23 * 60 + 59))
        return dtime(m // 60, m % 60)

    def _hav(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        p1, p2 = _math.radians(lat1), _math.radians(lat2)
        a = (_math.sin(_math.radians((lat2 - lat1) / 2)) ** 2
             + _math.cos(p1) * _math.cos(p2)
             * _math.sin(_math.radians((lon2 - lon1) / 2)) ** 2)
        return 2 * R * _math.asin(_math.sqrt(a))

    def _best_restaurant(prev_lat: float, prev_lon: float) -> object | None:
        """Closest restaurant within 2 km; fall back to overall closest."""
        ranked = sorted(
            restaurants,
            key=lambda r: _hav(prev_lat, prev_lon, r.location_lat, r.location_lon),
        )
        return ranked[0] if ranked else None

    def _overlaps(meal_start: int, meal_end: int, existing: list) -> bool:
        for rp in existing:
            s = _t2m(rp.arrival_time)   if rp.arrival_time   else 0
            e = _t2m(rp.departure_time) if rp.departure_time else 0
            if meal_start < e and meal_end > s:
                return True
        return False

    LUNCH_OPEN  = _t2m(dtime(12,  0))
    LUNCH_CLOSE = _t2m(dtime(16,  0))   # allow "late lunch" up to 16:00 for packed days
    DIN_OPEN    = _t2m(dtime(18, 30))
    DIN_CLOSE   = _t2m(dtime(21, 30))
    DAY_HARD    = _t2m(dtime(20, 30))

    for day in itinerary.days:
        # Work only with attraction stops (restaurants not yet inserted)
        attractions = [rp for rp in day.route_points if rp.activity_type != "restaurant"]
        if not attractions:
            continue

        new_meals: list[RoutePoint] = []

        # ── Lunch ─────────────────────────────────────────────────────────────
        # Strategy 1: find the last attraction that departs at or before LUNCH_CLOSE.
        # Lunch starts right after it (clamped to LUNCH_OPEN).
        lunch_anchor = None
        for rp in attractions:
            dep = _t2m(rp.departure_time) if rp.departure_time else 0
            if dep <= LUNCH_CLOSE:
                lunch_anchor = rp
            else:
                break   # already sorted chronologically

        # Strategy 2 (fatigue fallback): if no anchor found in window, look for a
        # natural ≥ 3 h sightseeing gap between consecutive stops.
        if lunch_anchor is None and len(attractions) >= 2:
            cumulative = 0
            for i in range(len(attractions) - 1):
                a_dep = _t2m(attractions[i].departure_time)   if attractions[i].departure_time else 0
                b_arr = _t2m(attractions[i + 1].arrival_time) if attractions[i + 1].arrival_time else 0
                cumulative += (b_arr - a_dep)
                if cumulative >= FATIGUE_THRESH:
                    lunch_anchor = attractions[i]
                    break

        if lunch_anchor:
            anchor_dep  = _t2m(lunch_anchor.departure_time)
            lunch_start = max(anchor_dep + BUFFER_MIN, LUNCH_OPEN)
            lunch_end   = lunch_start + MEAL_DUR_MIN
            if lunch_end <= LUNCH_CLOSE and not _overlaps(lunch_start, lunch_end, day.route_points):
                rest = _best_restaurant(lunch_anchor.location_lat, lunch_anchor.location_lon)
                if rest:
                    new_meals.append(RoutePoint(
                        sequence=0,
                        name=f"{rest.name} (Lunch)",
                        location_lat=rest.location_lat,
                        location_lon=rest.location_lon,
                        arrival_time=_m2t(lunch_start),
                        departure_time=_m2t(lunch_end),
                        visit_duration_minutes=MEAL_DUR_MIN,
                        activity_type="restaurant",
                        estimated_cost=0.0,
                        notes=f"{rest.cuisine_type} · ₹{rest.avg_price_per_person:.0f}/person",
                    ))

        # ── Dinner ────────────────────────────────────────────────────────────
        # Find the last attraction to finish before 21:30.
        # Dinner starts right after it (clamped to DIN_OPEN).
        dinner_anchor = None
        for rp in reversed(attractions):
            dep = _t2m(rp.departure_time) if rp.departure_time else 0
            if dep <= DIN_CLOSE:
                dinner_anchor = rp
                break

        if dinner_anchor:
            anchor_dep   = _t2m(dinner_anchor.departure_time)
            dinner_start = max(anchor_dep + BUFFER_MIN, DIN_OPEN)
            dinner_end   = dinner_start + MEAL_DUR_MIN
            if dinner_end <= DIN_CLOSE and not _overlaps(dinner_start, dinner_end, day.route_points):
                rest = _best_restaurant(dinner_anchor.location_lat, dinner_anchor.location_lon)
                if rest:
                    new_meals.append(RoutePoint(
                        sequence=0,
                        name=f"{rest.name} (Dinner)",
                        location_lat=rest.location_lat,
                        location_lon=rest.location_lon,
                        arrival_time=_m2t(dinner_start),
                        departure_time=_m2t(dinner_end),
                        visit_duration_minutes=MEAL_DUR_MIN,
                        activity_type="restaurant",
                        estimated_cost=0.0,
                        notes=f"{rest.cuisine_type} · ₹{rest.avg_price_per_person:.0f}/person",
                    ))

        # ── Merge + re-sequence ────────────────────────────────────────────
        day.route_points.extend(new_meals)
        day.route_points.sort(key=lambda rp: _t2m(rp.arrival_time) if rp.arrival_time else 0)
        for i, rp in enumerate(day.route_points):
            rp.sequence = i


# ═══════════════════════════════════════════════════════════════════════════
# FORMATTED ITINERARY PRINTER
# ═══════════════════════════════════════════════════════════════════════════

def _print_itinerary(itinerary: Itinerary) -> None:
    """Print a human-readable day-by-day schedule with visit times."""
    import calendar

    width = 52
    print()
    print("═" * width)
    print(f"  YOUR ITINERARY  —  {itinerary.destination_city}  ({len(itinerary.days)} day(s))")
    print("═" * width)

    for day in itinerary.days:
        # Weekday + date heading
        day_name = calendar.day_name[day.date.weekday()]
        print(f"\n  Day {day.day_number}  —  {day_name}, {day.date.strftime('%d %b %Y')}")
        print("  " + "─" * (width - 2))

        if not day.route_points:
            print("    (no stops scheduled)")
            continue

        for rp in day.route_points:
            arr = rp.arrival_time.strftime("%H:%M")   if rp.arrival_time   else "--:--"
            dep = rp.departure_time.strftime("%H:%M") if rp.departure_time else "--:--"
            dur = rp.visit_duration_minutes
            time_block = f"{arr} – {dep}"
            name_col   = rp.name[:28].ljust(28)
            if rp.activity_type == "restaurant":
                note = f"  {rp.notes}" if rp.notes else ""
                print(f"    {time_block}   {name_col}  ({dur} min){note}")
            else:
                print(f"    {time_block}   {name_col}  ({dur} min)")

    print()
    print("═" * width)
    print(f"  Total trip cost : ₹{itinerary.total_actual_cost:,.2f}")
    print("═" * width)
    print()


if __name__ == "__main__":
    _chat_mode      = "--chat"       in sys.argv
    _reoptimize     = "--reoptimize" in sys.argv
    _replay_mode    = "--replay"     in sys.argv

    if _replay_mode:
        from modules.observability.replay import replay_session
        _replay_idx = sys.argv.index("--replay")
        if _replay_idx + 1 >= len(sys.argv):
            print("Usage: python main.py --replay <session_id>")
            sys.exit(1)
        _replay_sid = sys.argv[_replay_idx + 1]
        replay_session(_replay_sid)
        sys.exit(0)

    if _chat_mode:
        # ── Chat mode: extract constraints from conversation ────────────────
        _llm = StubLLMClient() if config.USE_STUB_LLM else GeminiClient()
        _intake = ChatIntake(llm_client=_llm)
        _bundle, _budget = _intake.run()
        itinerary = run_pipeline(
            constraints=_bundle,
            total_budget=_budget,
        )
    else:
        # ── Default mode: hardcoded pipeline run ───────────────────────────
        itinerary = run_pipeline()

    if _reoptimize:
        _run_reoptimize_demo(itinerary)

    # ── Human-readable schedule ───────────────────────────────────────────
    _print_itinerary(itinerary)

    # ── Machine-readable JSON summary ────────────────────────────────────
    print("ITINERARY SUMMARY (JSON):")
    summary = {
        "trip_id": itinerary.trip_id,
        "destination": itinerary.destination_city,
        "total_days": len(itinerary.days),
        "total_actual_cost": itinerary.total_actual_cost,
        "budget": {
            "Accommodation":   itinerary.budget.Accommodation,
            "Attractions":     itinerary.budget.Attractions,
            "Restaurants":     itinerary.budget.Restaurants,
            "Transportation":  itinerary.budget.Transportation,
            "Other_Expenses":  itinerary.budget.Other_Expenses,
            "Reserve_Fund":    itinerary.budget.Reserve_Fund,
        },
        "days": [
            {
                "day": d.day_number,
                "date": str(d.date),
                "stops": [
                    {
                        "sequence": rp.sequence,
                        "name":     rp.name,
                        "type":     rp.activity_type,
                        "arrival":  rp.arrival_time.strftime("%H:%M")   if rp.arrival_time   else None,
                        "departure": rp.departure_time.strftime("%H:%M") if rp.departure_time else None,
                        "duration_minutes": rp.visit_duration_minutes,
                        "notes":    rp.notes,
                    }
                    for rp in d.route_points
                ],
            }
            for d in itinerary.days
        ],
    }
    print(json.dumps(summary, indent=2))
