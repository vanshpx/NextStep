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
from schemas.itinerary import BudgetAllocation, Itinerary

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
        constraints = ConstraintBundle(hard=hard, soft=soft, commonsense=commonsense)

    print(f"  Hard  : {departure_city} → {destination_city} | {departure_date} – {return_date}")
    print(f"  Soft  : interests={soft.interests}, spending_power={soft.spending_power}")
    print(f"  Common: {len(commonsense.rules)} rules loaded")

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

    budget_planner = BudgetPlanner(llm_client=llm)
    budget_allocation = budget_planner.distribute(total_budget, constraints, preliminary)
    assert budget_planner.validate(budget_allocation, total_budget), "Budget allocation exceeds total!"
    print(f"  Budget allocated: {budget_allocation}")

    # ══════════════════════════════════════════════════════════════
    # STAGE 3: Recommendation and Information Gathering
    # ══════════════════════════════════════════════════════════════
    print("\n[Stage 3] Recommendations")

    # ── Attractions ───────────────────────────────────────────────────────
    # TODO: Replace dummy data inside AttractionTool.fetch() with real API once
    #       ATTRACTION_API_URL env var is configured.
    real_time_attractions = AttractionTool().fetch(destination_city)
    print(f"  Fetched {len(real_time_attractions)} attractions (stub)")

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

    # ── Hotels ───────────────────────────────────────────────────────────
    # TODO: Replace dummy data inside HotelTool.fetch() with real API once
    #       HOTEL_API_URL env var is configured.
    fetched_hotels = HotelTool().fetch(
        destination_city,
        check_in=str(departure_date),
        check_out=str(return_date),
    )
    num_days = max((return_date - departure_date).days, 1)
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



    # ══════════════════════════════════════════════════════════════
    # STAGE 4: Route Planning
    # ══════════════════════════════════════════════════════════════
    print("\n[Stage 4] Route Planning")

    route_planner = RoutePlanner()
    itinerary = route_planner.plan(
        constraints=constraints,
        attraction_set=ranked_attractions,
        budget=budget_allocation,
        start_date=departure_date,
        end_date=return_date,
        hotel_lat=28.6139,   # TODO: MISSING — should come from Hotel Recommender output
        hotel_lon=77.2090,
    )

    print(f"  Generated {len(itinerary.days)} day(s) for trip {itinerary.trip_id}")
    for day in itinerary.days:
        print(f"  Day {day.day_number} ({day.date}): {len(day.route_points)} stops, "
              f"cost={day.daily_budget_used:.2f}")
        for rp in day.route_points:
            print(f"    [{rp.sequence}] {rp.name} | arr={rp.arrival_time} dep={rp.departure_time}")

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
    Demonstrates the ReOptimizationSession on day 1 of the generated itinerary.

    Shows:
      - Thresholds LEARNED from user's SoftConstraints (crowd / traffic / weather)
      - User-reported disruption (skip stop, preference change)
      - Environmental triggers (crowd too high → auto-replan)
      - Interactive loop: feed custom readings at the prompt

    Run:  python main.py --reoptimize
    """
    from modules.tool_usage.attraction_tool import AttractionTool

    print("\n" + "=" * 60)
    print("  REAL-TIME RE-OPTIMIZER")
    print("=" * 60)

    # ── Rebuild constraints (same as default run_pipeline) ─────────────────
    from modules.memory.long_term_memory import LongTermMemory
    ltm = LongTermMemory()
    history = ltm.get_history_insights("user_001")
    hard = HardConstraints(
        departure_city="Mumbai",
        destination_city="Delhi",
        departure_date=date(2026, 3, 1),
        return_date=date(2026, 3, 5),
        num_adults=2,
        num_children=0,
        traveler_ages=[30, 28],
        restaurant_preference="Indian",
        requires_wheelchair=False,
    )
    soft = SoftConstraints(
        interests=history["user_preferences"].get("interests", ["museum", "history"]),
        spending_power=history["user_preferences"].get("spending_power", "medium"),
        avoid_crowds=True,          # ← will set crowd threshold LOW
        pace_preference="moderate",
        heavy_travel_penalty=True,
    )
    commonsense = CommonsenseConstraints(rules=history["commonsense_rules"])
    constraints = ConstraintBundle(hard=hard, soft=soft, commonsense=commonsense)

    # ── Fetch attraction pool ──────────────────────────────────────────────
    all_attractions = AttractionTool().fetch("Delhi")

    # ── Create session from the pre-built itinerary ────────────────────────
    session = ReOptimizationSession.from_itinerary(
        itinerary=itinerary,
        constraints=constraints,
        remaining_attractions=all_attractions,
        hotel_lat=28.6139,
        hotel_lon=77.2090,
        start_day=1,
    )

    print(f"\n  Thresholds derived from your preferences:")
    print(f"    {session.thresholds.describe()}")
    print(f"    (avoid_crowds={soft.avoid_crowds}, pace={soft.pace_preference}, "
          f"heavy_travel_penalty={soft.heavy_travel_penalty})")

    day1 = itinerary.days[0] if itinerary.days else None
    if day1:
        print(f"\n  Original Day 1 plan: {[rp.name for rp in day1.route_points]}")
    else:
        print("\n  (No stops in Day 1 plan — running with attraction pool)")

    # ── Scripted simulation ────────────────────────────────────────────────
    print("\n" + "-" * 50)
    print("  SIMULATION")
    print("-" * 50)

    # Step 1: Advance to first stop normally
    if day1 and day1.route_points:
        first_stop = day1.route_points[0]
        print(f"\n  Step 1: Arrived at '{first_stop.name}' at 09:30")
        session.advance_to_stop(
            stop_name=first_stop.name,
            arrival_time="10:45",
            lat=28.6560, lon=77.2410,
            cost=first_stop.estimated_cost,
        )

    # Step 2: Check conditions — crowd is high at next stop (will exceed threshold)
    if day1 and len(day1.route_points) > 1:
        next_stop = day1.route_points[1]
        crowd = 0.80   # above the 0.35 threshold for avoid_crowds=True
        traffic = 0.45
        print(f"\n  Step 2: Checking conditions for '{next_stop.name}'")
        print(f"    crowd_level={crowd:.0%}, traffic_level={traffic:.0%}")
        new_plan = session.check_conditions(
            crowd_level=crowd,
            traffic_level=traffic,
            next_stop_name=next_stop.name,
            next_stop_is_outdoor=getattr(
                next(
                    (a for a in all_attractions if a.name == next_stop.name),
                    None
                ), "is_outdoor", False
            ),
        )
        if new_plan:
            print(f"    → New plan: {[rp.name for rp in new_plan.route_points]}")

    # Step 3: User reports bad weather → replan to prefer indoor
    print(f"\n  Step 3: Weather update — 'rainy' reported")
    new_plan = session.check_conditions(
        weather_condition="rainy",
        next_stop_is_outdoor=True,
    )
    if new_plan:
        print(f"    → New plan: {[rp.name for rp in new_plan.route_points]}")
    else:
        print(f"    Severity below weather threshold — no replan.")

    # Step 4: User preference change mid-trip
    print(f"\n  Step 4: User updates pace to 'relaxed'")
    new_plan = session.event(
        EventType.USER_PREFERENCE_CHANGE,
        {"field": "pace_preference", "value": "relaxed"},
    )
    print(f"    New thresholds: {session.thresholds.describe()}")

    # ── Interactive loop ───────────────────────────────────────────────────
    print("\n" + "-" * 50)
    print("  INTERACTIVE MODE  (type 'q' to quit)")
    print("  Commands:")
    print("    skip <stop_name>")
    print("    delay <minutes>")
    print("    crowd <level 0-1> <stop_name>")
    print("    weather <condition>   e.g. rainy / stormy / clear")
    print("    traffic <level 0-1> <stop_name> <delay_minutes>")
    print("    summary")
    print("-" * 50)

    while True:
        try:
            raw = input("  reoptimize> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw or raw.lower() in ("q", "quit", "exit"):
            break

        parts = raw.split()
        cmd = parts[0].lower()

        if cmd == "skip" and len(parts) >= 2:
            stop = " ".join(parts[1:])
            session.event(EventType.USER_SKIP, {"stop_name": stop})

        elif cmd == "delay" and len(parts) >= 2:
            session.event(EventType.USER_DELAY, {"delay_minutes": int(parts[1])})

        elif cmd == "crowd" and len(parts) >= 2:
            level = float(parts[1])
            stop  = " ".join(parts[2:]) if len(parts) > 2 else ""
            session.check_conditions(crowd_level=level, next_stop_name=stop)

        elif cmd == "weather" and len(parts) >= 2:
            condition = parts[1]
            session.check_conditions(
                weather_condition=condition, next_stop_is_outdoor=True
            )

        elif cmd == "traffic" and len(parts) >= 2:
            level = float(parts[1])
            stop  = parts[2] if len(parts) > 2 else ""
            delay = int(parts[3]) if len(parts) > 3 else 0
            session.check_conditions(
                traffic_level=level,
                next_stop_name=stop,
                estimated_traffic_delay_minutes=delay,
            )

        elif cmd == "summary":
            import json
            print(json.dumps(session.summary(), indent=2, default=str))

        else:
            print("  Unknown command. Type 'q' to quit or see commands above.")

    print("\n  Final session summary:")
    import json
    print(json.dumps(session.summary(), indent=2, default=str))


if __name__ == "__main__":
    _chat_mode      = "--chat"       in sys.argv
    _reoptimize     = "--reoptimize" in sys.argv

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

    # Pretty-print day summary
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
                "stops": [rp.name for rp in d.route_points],
            }
            for d in itinerary.days
        ],
    }
    print(json.dumps(summary, indent=2))
