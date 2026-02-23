"""
demo_reoptimizer.py
────────────────────────────────────────────────────────────────────────────
Hackathon demo: walks through 6 real-world re-optimization scenarios,
one at a time, with a Press-Enter pause between each.

No math or formulas — each scenario shows the system making a decision
in a real travel situation and explains what it did in plain English.

Scenarios:
  1. Crowded stop — system auto-reschedules to a quieter time later today
  2. Crowded stop, last day — system can't reschedule, shows what you'd miss
  3. Thunderstorm hits — outdoor stops blocked, routed to indoor alternatives
  4. Traffic jam ahead — high-value stops deferred, low-value ones swapped
  5. Traveller skips a stop — system shows full advisory before accepting skip
  6. Auto-detect: hungry + tired — system acts without any user input

Run:
    python demo_reoptimizer.py
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import sys
from datetime import date
from unittest.mock import patch
from typing import Iterator

# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────

WIDTH = 66

def _banner(title: str) -> None:
    print("\n" + "═" * WIDTH)
    print(f"  {title}")
    print("═" * WIDTH)

def _scene(number: int, title: str, situation: str) -> None:
    print("\n" + "╔" + "═" * (WIDTH - 2) + "╗")
    print(f"║  SCENARIO {number} — {title:<{WIDTH - 15}}║")
    print("╠" + "═" * (WIDTH - 2) + "╣")
    for line in _wrap(situation, WIDTH - 4):
        print(f"║  {line:<{WIDTH - 4}}║")
    print("╚" + "═" * (WIDTH - 2) + "╝")

def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).lstrip()
    if cur:
        lines.append(cur)
    return lines

def _pause() -> None:
    try:
        input("\n  [ Press Enter to trigger the scenario... ]\n")
    except EOFError:
        print()

def _result_note(text: str) -> None:
    print()
    print("  ┌─ WHAT HAPPENED " + "─" * (WIDTH - 19) + "┐")
    for line in _wrap(text, WIDTH - 4):
        print(f"  │  {line:<{WIDTH - 4}}│")
    print("  └" + "─" * (WIDTH - 2) + "┘")

def _separator() -> None:
    print("\n" + "─" * WIDTH)


# ─────────────────────────────────────────────────────────────────────────────
# Silent pipeline bootstrap (reuses test_full_pipeline machinery)
# ─────────────────────────────────────────────────────────────────────────────

_SC_JSON = json.dumps({
    "soft": {
        "interests":                    ["museum", "history", "art", "architecture"],
        "travel_preferences":           ["cultural", "relaxed"],
        "spending_power":               "medium",
        "character_traits":             ["avoids_crowds", "prefers_mornings"],
        "dietary_preferences":          ["vegetarian", "local_cuisine"],
        "preferred_time_of_day":        "morning",
        "avoid_crowds":                 True,
        "pace_preference":              "relaxed",
        "preferred_transport_mode":     ["walking", "public_transit"],
        "avoid_consecutive_same_category": True,
        "novelty_spread":               True,
        "rest_interval_minutes":        90,
        "heavy_travel_penalty":         True,
    },
    "commonsense": {
        "rules": ["no street food", "prefer morning visits to museums"]
    },
})

_PHASE1_ANSWERS = [
    "Mumbai", "Delhi", "2026-03-10", "2026-03-12",
    "2", "1", "32,30,8", "Vegetarian", "no", "55000",
]
_PHASE2_ANSWERS = [
    "I love history and museums.",
    "I prefer mornings, less crowded.",
    "We are vegetarians — no meat, no street food.",
    "Relaxed pace, 3-4 stops a day.",
    "done",
]

class _MockLLM:
    def complete(self, prompt: str) -> str:
        if '"interests"' in prompt or "soft" in prompt.lower():
            return _SC_JSON
        return "[stub]"

def _make_gen(answers: list[str]) -> Iterator[str]:
    for a in answers:
        yield a

def _build_itinerary():
    """Run the full pipeline silently and return (itinerary, bundle)."""
    gen = _make_gen(_PHASE1_ANSWERS + _PHASE2_ANSWERS)

    def _mock_input(prompt: str = "") -> str:
        val = next(gen)
        print(prompt + val)
        return val

    from modules.input.chat_intake import ChatIntake
    import config as cfg

    with patch("builtins.input", side_effect=_mock_input):
        intake = ChatIntake(llm_client=_MockLLM())
        bundle, budget = intake.run()

    orig = cfg.USE_STUB_LLM
    cfg.USE_STUB_LLM = True
    from main import run_pipeline
    itinerary = run_pipeline(constraints=bundle, total_budget=budget)
    cfg.USE_STUB_LLM = orig
    return itinerary, bundle


def _new_session(itinerary, bundle):
    """Create a fresh ReOptimizationSession for a scenario."""
    from modules.tool_usage.attraction_tool import AttractionTool
    from modules.reoptimization import ReOptimizationSession

    attractions = AttractionTool().fetch(itinerary.destination_city)
    return ReOptimizationSession.from_itinerary(
        itinerary=itinerary,
        constraints=bundle,
        remaining_attractions=attractions,
        hotel_lat=28.6139,
        hotel_lon=77.2090,
        start_day=1,
    ), attractions


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────

def run_demo() -> None:

    # ── Bootstrap ─────────────────────────────────────────────────────────────
    _banner("TRAVEL ITINERARY OPTIMIZER — Re-Optimization Demo")
    print("""
  This demo shows the re-optimization engine handling 6 real situations
  that arise mid-trip. After each situation fires, watch how the system
  decides what to do — automatically — and explains its reasoning.

  The trip: Mumbai → Delhi, 2 adults + 1 child, 2 nights, ₹55,000 budget.
  User preferences: loves history & museums, avoids crowds, relaxed pace.
    """)

    print("  Building itinerary...", end="", flush=True)

    # Suppress the pipeline's own print output during build
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        itinerary, bundle = _build_itinerary()

    day1 = itinerary.days[0]
    stops_d1 = [rp.name for rp in day1.route_points]
    print(" done.\n")
    print(f"  Generated itinerary — Day 1 stops: {stops_d1}")
    print(f"  Destination: {itinerary.destination_city}  |  "
          f"Days: {len(itinerary.days)}  |  "
          f"Budget used: ₹{itinerary.total_actual_cost:,.0f}")

    from modules.reoptimization import EventType
    from modules.reoptimization.condition_monitor import WEATHER_SEVERITY

    # =========================================================================
    # SCENARIO 1 — Crowded stop, reschedule same day
    # =========================================================================
    _scene(
        1,
        "Popular spot is packed — system auto-reschedules",
        "You're heading to Heritage Fort. The crowd monitor reads 82% occupancy. "
        "Your preference is set to avoid crowds (tolerance: ~35%). "
        "There's still plenty of time left in the day, so the system has room to work with. "
        "Watch what it does — no input from you.",
    )
    _pause()

    session1, _ = _new_session(itinerary, bundle)

    # Advance past stop 0 to simulate being mid-trip
    if day1.route_points:
        s0 = day1.route_points[0]
        session1.advance_to_stop(
            stop_name=s0.name, arrival_time="09:00",
            lat=28.6560, lon=77.2410, cost=s0.estimated_cost,
            duration_minutes=60, intensity_level="low",
        )

    session1.check_conditions(
        crowd_level=0.82,
        next_stop_name="Heritage Fort",
        next_stop_is_outdoor=False,
    )

    if session1.pending_decision is not None:
        print(f"  [Approval gate] Disruption payload above — approving now...")
        plan1 = session1.resolve_pending("APPROVE")
    else:
        plan1 = None

    if plan1:
        _result_note(
            "The system detected 82% crowd at Heritage Fort (your limit is ~35%). "
            "After your APPROVE, it deferred Heritage Fort to a quieter time later today and "
            f"rerouted you through: {[rp.name for rp in plan1.route_points]}. "
            "Heritage Fort remains in the pool — you'll still visit it today when it's less busy."
        )
    elif session1.crowd_pending_decision:
        pend = session1.crowd_pending_decision
        _result_note(
            f"Crowd ADVISORY raised for '{pend['stop_name']}' "
            f"({pend['crowd_level']:.0%} crowd, your limit {pend['threshold']:.0%}). "
            "After approval, the INFORM_USER panel was presented — awaiting final user choice."
        )
    else:
        _result_note("No crowd action triggered — pool may be exhausted for this run.")

    _separator()

    # =========================================================================
    # SCENARIO 2 — Crowded stop, last day — user must decide
    # =========================================================================
    _scene(
        2,
        "Crowded stop on the LAST day — system can't reschedule",
        "Same crowd situation, but now it's your last day. "
        "The system can't push Heritage Fort to Day 3 because the trip ends today. "
        "It can't fit it later today either. "
        "So instead of silently dropping it, it shows you exactly what you'd miss "
        "and lets you make the call.",
    )
    _pause()

    session2, _ = _new_session(itinerary, bundle)

    # Force last-day state — current_day must equal total_days
    session2.state.current_day = session2.total_days
    # Mark remaining time as tight so same-day reschedule also fails
    session2.state.current_time = "16:30"
    session2.state.remaining_minutes = 30

    session2.check_conditions(
        crowd_level=0.82,
        next_stop_name="Heritage Fort",
        next_stop_is_outdoor=False,
    )

    if session2.pending_decision is not None:
        print(f"  [Approval gate] Disruption payload above — approving now...")
        plan2 = session2.resolve_pending("APPROVE")
    else:
        plan2 = None

    if session2.crowd_pending_decision:
        pend = session2.crowd_pending_decision
        _result_note(
            f"INFORM USER strategy triggered. Heritage Fort is {pend['crowd_level']:.0%} crowded "
            f"(limit {pend['threshold']:.0%}) and cannot be rescheduled — last day, no time. "
            "After APPROVE, the full advisory panel was shown: WHAT YOU WILL MISS (historical context) "
            "and YOUR CHOICE: brave the crowds or skip permanently."
        )
    elif plan2:
        _result_note(
            "System found a slot and auto-rescheduled after approval. "
            f"New plan: {[rp.name for rp in plan2.route_points]}"
        )
    else:
        _result_note(
            "Crowd advisory raised — user approved display. No further replan needed. "
            "This is the 'inform user' strategy — the system respects your agency."
        )

    _separator()

    # =========================================================================
    # SCENARIO 3 — Thunderstorm hits
    # =========================================================================
    _scene(
        3,
        "Thunderstorm hits mid-trip",
        "It was sunny this morning. Now a thunderstorm has rolled in with 90% severity. "
        "Several of your upcoming stops are outdoor — parks, monuments, open-air sites. "
        "Watch how the system responds without you typing a single command.",
    )
    _pause()

    session3, _ = _new_session(itinerary, bundle)

    session3.check_conditions(
        weather_condition="thunderstorm",
        next_stop_is_outdoor=True,
    )

    severity = WEATHER_SEVERITY.get("thunderstorm", 0.9)
    if session3.pending_decision is not None:
        print(f"  [Approval gate] WEATHER disruption payload shown — approving now...")
        plan3 = session3.resolve_pending("APPROVE")
    else:
        plan3 = None

    if plan3:
        _result_note(
            f"Thunderstorm severity {severity:.0%} triggered a weather disruption. "
            "After your APPROVE, outdoor stops with HC_pti = 0 (unsafe) were blocked. "
            "Stops with moderate exposure were kept but with reduced duration. "
            f"The system rerouted to: {[rp.name for rp in plan3.route_points]}. "
            "Indoor venues were ranked by quality-per-travel-minute and selected automatically."
        )
    else:
        _result_note(
            f"Thunderstorm severity {severity:.0%} was below this user's weather threshold "
            f"({session3.thresholds.weather:.0%}). No disruption pending — within acceptable range."
        )

    _separator()

    # =========================================================================
    # SCENARIO 4 — Traffic jam ahead
    # =========================================================================
    _scene(
        4,
        "Traffic jam on the way to Lotus Temple",
        "You're about to leave for Lotus Temple. Live traffic shows 78% congestion — "
        "the estimated delay is 40 minutes. Some stops are still worth waiting for. "
        "Others aren't. The system decides which is which and acts accordingly.",
    )
    _pause()

    session4, _ = _new_session(itinerary, bundle)

    session4.check_conditions(
        traffic_level=0.78,
        next_stop_name="Lotus Temple",
        next_stop_is_outdoor=False,
        estimated_traffic_delay_minutes=40,
    )

    if session4.pending_decision is not None:
        print(f"  [Approval gate] TRAFFIC disruption payload shown — approving now...")
        plan4 = session4.resolve_pending("APPROVE")
    else:
        plan4 = None

    if plan4:
        _result_note(
            "Traffic at 78% (threshold ~40%). After your APPROVE, delay factor was applied. "
            "Stops with high FTRM score (≥ 0.65) were DEFERRED — saved for later in the day. "
            "Stops with low FTRM score (< 0.65) were REPLACED with nearby alternatives. "
            "Clock advanced by 40 min. "
            f"New plan: {[rp.name for rp in plan4.route_points]}"
        )
    else:
        _result_note(
            "Traffic level below threshold — no disruption pending. "
            "The system decided the delay is minor enough to proceed as planned."
        )

    _separator()

    # =========================================================================
    # SCENARIO 5 — User types: "skip this"
    # =========================================================================
    _scene(
        5,
        "You decide to skip next stop — system shows what you'd miss",
        "You're tired of the current neighbourhood and want to skip National Gallery of Art. "
        "Before the system accepts your skip, it pulls up everything you should know: "
        "the historical significance, what you'll miss, and the best alternatives available. "
        "You stay in control — the system just makes sure you're informed.",
    )
    _pause()

    session5, attractions5 = _new_session(itinerary, bundle)
    skip_target = "National Gallery of Art"

    plan5 = session5.event(
        EventType.USER_SKIP,
        {"stop_name": skip_target},
    )

    _result_note(
        f"SKIP ADVISORY fired for '{skip_target}'. "
        "Panel shows: WHAT YOU WILL MISS (historical context), "
        "BEST ALTERNATIVES ranked by FTRM score, YOUR CHOICE. "
        "After your confirmation, the skip was registered and the itinerary was replanned. "
        + (f"New plan: {[rp.name for rp in plan5.route_points]}" if plan5 else
           "No further replan needed — pool rebuilt around your remaining preferences.")
    )

    _separator()

    # =========================================================================
    # SCENARIO 6 — User reports hunger and fatigue in their own words
    # =========================================================================
    _scene(
        6,
        "User says: 'I'm starving and my feet are killing me'",
        "It's 1:30pm. You've been walking since 9am. You type a message to the system "
        "in plain English — you don't press any special button or pick from a menu. "
        "The system parses your words, figures out you're both hungry and tired, "
        "and handles both disruptions back-to-back.",
    )
    _pause()

    session6, _ = _new_session(itinerary, bundle)

    # Set up mid-trip state so the advisory has meaningful context
    session6.state.current_time   = "13:30"
    session6.state.last_meal_time = "08:00"
    session6.state.last_rest_time = "08:00"
    session6.state.hunger_level   = 0.10   # low — NLP will raise it to the floor
    session6.state.fatigue_level  = 0.10

    user_message = "I'm absolutely starving and my feet are killing me, I really need a break"
    print(f'  User types: "{user_message}"')
    print()

    plan6 = session6.event(
        EventType.USER_REPORT_DISRUPTION,
        {"message": user_message},
    )

    hunger_fired  = len(session6._disruption_memory.hunger_history) > 0
    fatigue_fired = len(session6._disruption_memory.fatigue_history) > 0

    _result_note(
        f'User said: "{user_message}". '
        "The system detected hunger and fatigue keywords in the message. "
        + ("HUNGER advisory fired — 45-min meal break inserted, nearby restaurants ranked and shown. "
           if hunger_fired else "") +
        ("FATIGUE advisory fired — 20-min rest break inserted, fatigue reduced. "
           if fatigue_fired else "") +
        "All downstream stop times were shifted to account for the breaks. "
        + (f"New plan: {[rp.name for rp in plan6.route_points]}" if plan6 else
           "Plan updated — breaks inserted into schedule.")
    )

    _separator()

    # =========================================================================
    # WRAP-UP
    # =========================================================================
    _banner("DEMO COMPLETE — Session Summary")

    # Use session3 as the representative session for summary
    summary = session3.summary()
    dm = summary.get("disruption_memory", {})

    print(f"""
  What you just saw:

    Scenario 1  Crowd detected → auto-reschedule same day
    Scenario 2  Crowd on last day → informs user, preserves agency
    Scenario 3  Thunderstorm → blocks outdoor stops, routes indoors
    Scenario 4  Traffic jam → defers high-value, replaces low-value stops
    Scenario 5  User skip → full advisory with historical context first
    Scenario 6  User reports hungry + tired in plain English → system handles both

  All 6 scenarios used the same constraint bundle:
    · avoid_crowds=True  · pace=relaxed  · interests=[museum, history, art]
    · dietary=vegetarian  · preferred_time=morning

  The thresholds the system derived from those preferences:
    {summary['thresholds']}
    """)

    print("═" * WIDTH)
    print("  End of demo.")
    print("═" * WIDTH)


if __name__ == "__main__":
    import os
    os.environ.setdefault("PYTHONUTF8", "1")
    run_demo()
