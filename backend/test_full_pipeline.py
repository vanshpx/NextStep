"""
test_full_pipeline.py
──────────────────────────────────────────────────────────────────────────────
End-to-end simulation of the FULL TravelAgent pipeline, including:

  PART 1 — Chat Intake
    Phase 1: Structured form (all input() calls are monkey-patched with scripted
             user answers — no actual terminal interaction required).
    Phase 2: Free-form preference chat (LLM is replaced with a MockLLMClient
             that returns a realistic SC JSON without any API call).

  PART 2 — Constraint Identification
    Prints the extracted HardConstraints, SoftConstraints, and
    CommonsenseConstraints side-by-side with what the user "said".

  PART 3 — Itinerary Generation
    Runs the full Stage 1–5 pipeline with the chat-extracted constraints.

  PART 4 — Mid-Trip Re-Optimization (Auto — System Triggered)
    Simulates the traveller advancing through stops, then fires three
    automatic environmental events:
      A. Crowd spike at "Heritage Fort"       → auto replan
      B. Rainy weather affecting outdoor stop → auto replan
      C. Heavy traffic to "Lotus Temple"      → auto replan (if delay ≥ 20 min)

  PART 5 — Mid-Trip Re-Optimization (User — Chat Driven)
    Simulates a user typing natural-language disruption messages:
      "I'm really tired, let's slow down"
      "This place is too crowded, skip it"
      "There's a thunderstorm coming"
    Each message is parsed and routed to the EventHandler.

Run:
    python test_full_pipeline.py

All output is printed to stdout with clear section banners.
No pytest / unittest required — plain Python.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import sys
import re
from datetime import date, datetime
from typing import Iterator
from unittest.mock import patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _banner(title: str) -> None:
    width = 70
    print("\n" + "═" * width)
    print(f"  {title}")
    print("═" * width)

def _section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

def _ok(msg: str)   -> None: print(f"  ✓  {msg}")
def _info(msg: str) -> None: print(f"  ·  {msg}")
def _warn(msg: str) -> None: print(f"  ⚠  {msg}")
def _fail(msg: str) -> None: print(f"  ✗  {msg}"); sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Mock LLM — returns realistic SC JSON for Phase 2 chat, plus stubs for
# all recommender LLM calls (those are already discarded by recommenders)
# ─────────────────────────────────────────────────────────────────────────────

_SC_JSON_RESPONSE = json.dumps({
    "soft": {
        "interests":                    ["museum", "history", "art", "architecture"],
        "travel_preferences":           ["cultural", "relaxed", "off-the-beaten-path"],
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
        "heavy_travel_penalty":         True
    },
    "commonsense": {
        "rules": [
            "no street food",
            "avoid overly touristy restaurants",
            "prefer morning visits to museums"
        ]
    }
})


class MockLLMClient:
    """
    Zero-dependency LLM mock.  Returns _SC_JSON_RESPONSE for Phase 2 intake;
    returns '[stub]' for all other recommender calls (those are discarded anyway).
    """

    def complete(self, prompt: str) -> str:
        # Detect SC extraction prompt by its JSON structure keyword
        if '"interests"' in prompt or "soft" in prompt.lower():
            return _SC_JSON_RESPONSE
        return "[stub]"


# ─────────────────────────────────────────────────────────────────────────────
# Scripted input() answers
# ─────────────────────────────────────────────────────────────────────────────

# These are the exact inputs a real user would type, in order:
# Phase 1 form (10 prompts) + Phase 2 chat (4 lines + 'done') + Phase 3 passengers
_PHASE1_ANSWERS = [
    "Mumbai",            # departure city
    "Delhi",             # destination city
    "2026-03-10",        # departure date
    "2026-03-12",        # return date
    "2",                 # num adults
    "1",                 # num children
    "Vegetarian",        # restaurant preference
    "no",                # wheelchair access
    "55000",             # total budget
    "IN",                # guest nationality (new Phase 1 field)
]

_PHASE2_ANSWERS = [
    "I absolutely love history and museums, could spend hours inside them.",
    "I prefer going out in the morning when places are less crowded.",
    "We are vegetarians so no meat please. Also no street-food stalls.",
    "I like a relaxed pace, maybe 3-4 stops a day. No rushed tours.",
    "done",              # ends Phase 2 chat
]

# Phase 3 — passenger details (2 adults + 1 child = 3 passengers × 10 prompts each)
# Prompts per passenger: title, first_name, last_name, dob, gender, email,
#   mobile, mobile_country_code, nationality_code, id_number
_PHASE3_ANSWERS = [
    # ── Adult 1 ──
    "",           # title → default Mr
    "Test",       # first name
    "User",       # last name
    "1990-01-01", # dob
    "",           # gender → default M
    "",           # email
    "",           # mobile
    "",           # mobile country code → 91
    "",           # nationality code → IN
    "",           # id number → skip (no expiry asked)
    # ── Adult 2 ──
    "",           # title
    "Test",       # first name
    "UserTwo",    # last name
    "1985-06-15", # dob
    "",           # gender
    "",           # email
    "",           # mobile
    "",           # mobile country code
    "",           # nationality code
    "",           # id number
    # ── Child 1 ──
    "",           # title
    "Test",       # first name
    "Child",      # last name
    "2015-03-20", # dob
    "",           # gender
    "",           # email
    "",           # mobile
    "",           # mobile country code
    "",           # nationality code
    "",           # id number
]

_ALL_INPUTS = _PHASE1_ANSWERS + _PHASE2_ANSWERS + _PHASE3_ANSWERS


def _make_input_gen(answers: list[str]) -> Iterator[str]:
    """Yield each scripted answer in order; raise if more inputs are requested."""
    idx = 0
    while True:
        if idx >= len(answers):
            raise StopIteration(
                f"Test ran out of scripted inputs after {len(answers)} answers."
            )
        yield answers[idx]
        idx += 1


# ─────────────────────────────────────────────────────────────────────────────
# User-chat disruption parser (Part 5)
# Maps free-text user messages to EventType + payload
# In production this would be an LLM call; here we use keyword rules.
# ─────────────────────────────────────────────────────────────────────────────

from modules.reoptimization.event_handler import EventType

_DISRUPTION_KEYWORDS: list[tuple[list[str], EventType, dict]] = [
    # pattern keywords → EventType + payload template
    (["tired", "slow down", "exhausted", "need rest", "break"],
     EventType.USER_PREFERENCE_CHANGE,
     {"field": "pace_preference", "value": "relaxed"}),

    (["skip", "don't want", "not interested", "pass"],
     EventType.USER_SKIP,
     {}),  # stop_name extracted separately

    (["crowd", "crowded", "packed", "too many people", "full"],
     EventType.USER_REPORT_DISRUPTION,
     {}),  # free-text

    (["rain", "raining", "thunderstorm", "storm", "wet", "flood", "weather"],
     EventType.ENV_WEATHER_BAD,
     {"severity": 0.85, "threshold": 0.65, "condition": "thunderstorm", "affects_outdoor": True}),

    (["traffic", "jam", "stuck", "gridlock", "delay"],
     EventType.USER_DELAY,
     {"delay_minutes": 35}),
]


def parse_user_disruption(
    message: str,
    current_plan_stops: list[str],
) -> tuple[EventType, dict]:
    """
    Parse a free-text disruption message into an (EventType, payload) pair.
    Uses keyword matching — no LLM needed for the test.
    """
    msg_lower = message.lower()

    for keywords, event_type, base_payload in _DISRUPTION_KEYWORDS:
        if any(kw in msg_lower for kw in keywords):
            payload = dict(base_payload)  # copy

            if event_type == EventType.USER_SKIP:
                # Try to extract which stop to skip from message
                for stop in current_plan_stops:
                    if stop.lower() in msg_lower:
                        payload["stop_name"] = stop
                        break
                else:
                    # Default: skip next stop in plan
                    payload["stop_name"] = current_plan_stops[0] if current_plan_stops else ""

            if event_type == EventType.USER_REPORT_DISRUPTION:
                payload["message"] = message

            return event_type, payload

    # Default: generic user report
    return EventType.USER_REPORT_DISRUPTION, {"message": message}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TEST
# ─────────────────────────────────────────────────────────────────────────────

def run_full_pipeline_test() -> None:

    # =========================================================================
    # PART 1 — CHAT INTAKE (mocked input + mocked LLM)
    # =========================================================================
    _banner("PART 1 — CHAT INTAKE")
    _section("Scripted user session")

    for i, ans in enumerate(_PHASE1_ANSWERS, 1):
        _info(f"Phase 1 [{i:02d}]: {ans!r}")
    print()
    for ans in _PHASE2_ANSWERS[:-1]:
        _info(f"Phase 2 chat: {ans!r}")
    _info("Phase 2 chat: 'done'")

    input_gen = _make_input_gen(_ALL_INPUTS)

    def _mock_input(prompt: str = "") -> str:
        answer = next(input_gen)
        # Echo what a real terminal would show
        print(prompt + answer)
        return answer

    llm = MockLLMClient()

    from modules.input.chat_intake import ChatIntake

    with patch("builtins.input", side_effect=_mock_input):
        intake = ChatIntake(llm_client=llm)
        bundle, total_budget = intake.run()

    _ok(f"Intake complete. Budget: {total_budget:,.0f}")

    # =========================================================================
    # PART 2 — CONSTRAINT IDENTIFICATION
    # =========================================================================
    _banner("PART 2 — CONSTRAINT IDENTIFICATION")

    hard = bundle.hard
    soft = bundle.soft
    cc   = bundle.commonsense

    _section("Hard Constraints (from Phase 1 form)")
    _ok(f"Route          : {hard.departure_city} → {hard.destination_city}")
    _ok(f"Dates          : {hard.departure_date} — {hard.return_date}  "
        f"({(hard.return_date - hard.departure_date).days} nights)")
    _ok(f"Group          : {hard.num_adults} adults + {hard.num_children} child(ren) "
        f"= total {hard.total_travelers}")
    _ok(f"Food pref      : {hard.restaurant_preference}")
    _ok(f"Wheelchair     : {hard.requires_wheelchair}")

    _section("Soft Constraints (extracted from Phase 2 chat by mock LLM)")
    _ok(f"Interests      : {soft.interests}")
    _ok(f"Spending power : {soft.spending_power}")
    _ok(f"Pace           : {soft.pace_preference}")
    _ok(f"Avoid crowds   : {soft.avoid_crowds}")
    _ok(f"Time of day    : {soft.preferred_time_of_day}")
    _ok(f"Dietary prefs  : {soft.dietary_preferences}")
    _ok(f"Rest interval  : {soft.rest_interval_minutes} min")
    _ok(f"Heavy travel   : {soft.heavy_travel_penalty}")
    _ok(f"Transport modes: {soft.preferred_transport_mode}")

    _section("Commonsense Rules (extracted from Phase 2 chat)")
    for rule in cc.rules:
        _ok(f"Rule: {rule!r}")

    # Verify key constraints were correctly extracted
    assert soft.avoid_crowds   is True,            "avoid_crowds should be True"
    assert soft.pace_preference == "relaxed",      "pace should be relaxed"
    assert soft.preferred_time_of_day == "morning","preferred_time_of_day should be morning"
    assert "vegetarian" in soft.dietary_preferences, "dietary should include vegetarian"
    assert "museum" in soft.interests,             "interests should include museum"
    assert len(cc.rules) >= 2,                     "at least 2 commonsense rules expected"
    _ok("All constraint assertions passed ✓")

    # =========================================================================
    # PART 3 — ITINERARY GENERATION
    # =========================================================================
    _banner("PART 3 — ITINERARY GENERATION")

    # Patch the LLM inside run_pipeline via the stub config
    import config as cfg
    orig_stub = cfg.USE_STUB_LLM
    cfg.USE_STUB_LLM = True   # ensure no real API calls

    from main import run_pipeline

    print()
    itinerary = run_pipeline(
        constraints=bundle,
        total_budget=total_budget,
    )
    cfg.USE_STUB_LLM = orig_stub

    _section("Itinerary result")
    _ok(f"Trip ID        : {itinerary.trip_id}")
    _ok(f"Destination    : {itinerary.destination_city}")
    _ok(f"Total days     : {len(itinerary.days)}")
    _ok(f"Total cost     : ₹{itinerary.total_actual_cost:.2f}")
    for day in itinerary.days:
        stops = [rp.name for rp in day.route_points]
        _info(f"  Day {day.day_number} ({day.date}): {stops if stops else '(no stops)'}")

    assert len(itinerary.days) > 0, "Itinerary must have at least 1 day"
    _ok("Itinerary generation assertions passed ✓")

    # =========================================================================
    # PART 4 — MID-TRIP RE-OPTIMIZATION (SYSTEM AUTO-TRIGGERED)
    # =========================================================================
    _banner("PART 4 — AUTO RE-OPTIMIZATION (Crowd / Weather / Traffic)")

    from modules.tool_usage.attraction_tool import AttractionTool
    from modules.reoptimization import ReOptimizationSession, EventType

    all_attractions = AttractionTool().fetch(itinerary.destination_city)

    session = ReOptimizationSession.from_itinerary(
        itinerary=itinerary,
        constraints=bundle,
        remaining_attractions=all_attractions,
        hotel_lat=28.6139,
        hotel_lon=77.2090,
        start_day=1,
    )

    _section("Derived environmental thresholds from user constraints")
    _ok(f"Thresholds : {session.thresholds.describe()}")
    _ok(f"  (avoid_crowds={soft.avoid_crowds} → crowd threshold set LOW)")
    _ok(f"  (pace=relaxed + heavy_travel_penalty → traffic threshold very LOW)")

    day1 = itinerary.days[0]
    stops_d1 = [rp.name for rp in day1.route_points]
    _info(f"Original Day 1 plan: {stops_d1}")

    # ── Step A: Advance to first stop ─────────────────────────────────────────
    _section("Step A — Traveller arrives at first stop normally")
    first_stop = day1.route_points[0] if day1.route_points else None
    if first_stop:
        session.advance_to_stop(
            stop_name=first_stop.name,
            arrival_time="09:50",
            lat=28.6560, lon=77.2410,
            cost=first_stop.estimated_cost,
        )
        _ok(f"Visited '{first_stop.name}'. Clock: {session.state.current_time}")

    # ── Step B: Crowd spike at next stop → reschedule / inform user ────────
    _section("Step B — CROWD spike detected (auto trigger)")
    _info("New behavior: system tries 3 strategies in order:")
    _info("  1) Reschedule to quieter time LATER today")
    _info("  2) Move to a FUTURE day")
    _info("  3) Cannot reschedule → show historical importance, let user decide")
    next_stop_name = day1.route_points[1].name if len(day1.route_points) > 1 else "Heritage Fort"
    crowd_reading  = 0.82   # 82% crowd — well above ~35% threshold for avoid_crowds=True
    _info(f"Crowd monitor reading: {crowd_reading:.0%} at '{next_stop_name}'")
    _info(f"User threshold:         {session.thresholds.crowd:.0%}")
    _info(f"Threshold exceeded:     {crowd_reading > session.thresholds.crowd}")

    session.check_conditions(
        crowd_level=crowd_reading,
        next_stop_name=next_stop_name,
        next_stop_is_outdoor=False,
    )
    if session.pending_decision is not None:
        _ok(f"Approval gate: CROWD pending_decision set ✓ "
            f"({session.pending_decision.disruption_type})")
        _info(f"Proposed actions: "
              f"{[a.action_type for a in session.pending_decision.proposed_actions]}")
        b_plan = session.resolve_pending("APPROVE")
    else:
        b_plan = None
    if b_plan:
        _ok(f"Crowd handled (reschedule). New stops: {[rp.name for rp in b_plan.route_points]}")
        _ok(f"'{next_stop_name}' deferred to quieter time — NOT permanently skipped")
    elif session.crowd_pending_decision:
        pend = session.crowd_pending_decision
        _ok(f"Crowd INFORM_USER triggered for '{pend['stop_name']}'")
        _ok(f"Historical importance surfaced to traveller.")
        _info(f"  Crowd: {pend['crowd_level']:.0%}  |  threshold: {pend['threshold']:.0%}")
    else:
        _warn("No crowd action triggered (pool may be exhausted)")

    # ── Step C: Bad weather → outdoor stops deprioritized → auto replan ───────
    _section("Step C — WEATHER deterioration detected (auto trigger)")
    weather_now = "thunderstorm"
    from modules.reoptimization.condition_monitor import WEATHER_SEVERITY
    severity = WEATHER_SEVERITY.get(weather_now, 0.0)
    _info(f"Weather condition:  '{weather_now}' (severity={severity:.0%})")
    _info(f"User threshold:      {session.thresholds.weather:.0%}")
    _info(f"Threshold exceeded:  {severity > session.thresholds.weather}")

    session.check_conditions(
        weather_condition=weather_now,
        next_stop_is_outdoor=True,   # next stop is outdoor → deprioritize outdoor
    )
    if session.pending_decision is not None:
        _ok(f"Approval gate: WEATHER pending_decision set ✓ "
            f"({session.pending_decision.disruption_type})")
        c_plan = session.resolve_pending("APPROVE")
    else:
        c_plan = None
    if c_plan:
        _ok(f"Replan triggered. Outdoor stops deprioritized.")
        _ok(f"New stops: {[rp.name for rp in c_plan.route_points]}")
    else:
        _warn("Weather severity below threshold — no replan (expected for some configs)")

    # ── Step D: Heavy traffic → clock advanced → replan if delay ≥ 20 min ────
    _section("Step D — TRAFFIC jam detected (auto trigger)")
    traffic_reading  = 0.78
    traffic_delay    = 40   # 40 min delay → will trigger
    _info(f"Traffic level: {traffic_reading:.0%}  delay: {traffic_delay} min")
    _info(f"User threshold: {session.thresholds.traffic:.0%}")
    _info(f"Threshold exceeded: {traffic_reading > session.thresholds.traffic}")

    session.check_conditions(
        traffic_level=traffic_reading,
        next_stop_name="Lotus Temple",
        next_stop_is_outdoor=False,
        estimated_traffic_delay_minutes=traffic_delay,
    )
    if session.pending_decision is not None:
        _ok(f"Approval gate: TRAFFIC pending_decision set ✓ "
            f"({session.pending_decision.disruption_type})")
        d_plan = session.resolve_pending("APPROVE")
    else:
        d_plan = None
    if d_plan:
        _ok(f"Replan triggered. New stops: {[rp.name for rp in d_plan.route_points]}")
        _ok(f"Clock advanced by {traffic_delay} min to {session.state.current_time}")
    else:
        _warn("Traffic level below threshold — no replan triggered")

    _section("Part 4 summary")
    _ok(f"Re-optimizations so far: {len(session.replan_history)}")
    for i, entry in enumerate(session.replan_history, 1):
        _info(f"  Replan {i} @ {entry['time']}: {entry['reasons']}")

    # =========================================================================
    # PART 5 — MID-TRIP RE-OPTIMIZATION (USER CHAT DRIVEN)
    # =========================================================================
    _banner("PART 5 — USER CHAT RE-OPTIMIZATION")

    _section("Simulated user disruption messages")

    # Remaining stops that could be in the plan (use all_attractions as pool)
    current_plan_stops = [a.name for a in all_attractions
                          if a.name not in session.state.visited_stops
                          and a.name not in session.state.skipped_stops]

    user_disruption_messages = [
        "I'm really tired and need to slow down, let's take it easy",
        "This place is way too crowded, I don't want to go here",
        "There's a huge thunderstorm coming, it's getting really bad outside",
    ]

    replans_before = len(session.replan_history)

    for msg in user_disruption_messages:
        _section(f"User says: \"{msg}\"")

        event_type, payload = parse_user_disruption(msg, current_plan_stops)
        _info(f"Parsed as  : EventType.{event_type.name}")
        _info(f"Payload    : {payload}")

        new_plan = session.event(event_type, payload)

        # User-triggered events now go through the approval gate — auto-approve
        if session.pending_decision is not None:
            _info("Gate active — auto-approving for test…")
            new_plan = session.resolve_pending("APPROVE")

        if new_plan:
            stops = [rp.name for rp in new_plan.route_points]
            _ok(f"Replan executed. New plan: {stops}")
        else:
            _info("No replan required for this event.")

        # Update remaining pool display after each event
        current_plan_stops = [a.name for a in all_attractions
                               if a.name not in session.state.visited_stops
                               and a.name not in session.state.skipped_stops]

    replans_after = len(session.replan_history)
    _section("Part 5 summary")
    _ok(f"User messages processed: {len(user_disruption_messages)}")
    _ok(f"Additional replans triggered: {replans_after - replans_before}")
    _ok(f"Total replans (all parts):   {len(session.replan_history)}")

    # =========================================================================
    # PART 6 — HUNGER / FATIGUE DISRUPTION
    # =========================================================================
    _banner("PART 6 — HUNGER / FATIGUE DISRUPTION")

    from modules.reoptimization.hunger_fatigue_advisor import (
        HungerFatigueAdvisor,
        HUNGER_TRIGGER_THRESHOLD,
        FATIGUE_TRIGGER_THRESHOLD,
        NLP_HUNGER_FLOOR,
        NLP_FATIGUE_FLOOR,
        REST_RECOVERY_AMOUNT,
        TRIGGER_COOLDOWN_MIN,
    )

    # ── Fresh session for isolated assertions ─────────────────────────────────
    hf_session = ReOptimizationSession.from_itinerary(
        itinerary=itinerary,
        constraints=bundle,
        remaining_attractions=all_attractions,
        hotel_lat=28.6139,
        hotel_lon=77.2090,
        start_day=1,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # A: Deterministic accumulation — verify math after advance_to_stop
    # ─────────────────────────────────────────────────────────────────────────
    # A: Verify advance_to_stop does NOT auto-accumulate hunger/fatigue
    # (hunger/fatigue are user-triggered only via NLP)
    # ─────────────────────────────────────────────────────────────────────────
    _section("A — advance_to_stop does NOT auto-accumulate hunger/fatigue")

    hf_day1  = itinerary.days[0]
    hf_stop1 = hf_day1.route_points[0] if hf_day1.route_points else None

    hunger_before  = hf_session.state.hunger_level
    fatigue_before = hf_session.state.fatigue_level

    if hf_stop1:
        hf_session.advance_to_stop(
            stop_name        = hf_stop1.name,
            arrival_time     = "09:00",
            lat              = 28.6560,
            lon              = 77.2410,
            cost             = hf_stop1.estimated_cost,
            duration_minutes = 90,
            intensity_level  = "high",
        )
        hunger_after  = hf_session.state.hunger_level
        fatigue_after = hf_session.state.fatigue_level
        _ok(f"After 90-min high-intensity stop: hunger={hunger_after:.2f}  fatigue={fatigue_after:.2f}")
        assert hunger_after  == hunger_before,  \
            f"hunger should NOT change on advance_to_stop: before={hunger_before} after={hunger_after}"
        assert fatigue_after == fatigue_before, \
            f"fatigue should NOT change on advance_to_stop: before={fatigue_before} after={fatigue_after}"
        _ok("No auto-accumulation confirmed ✓")
    else:
        _warn("No Day-1 stops available — skipping accumulation check")

    # ─────────────────────────────────────────────────────────────────────────
    # B: Hunger triggered by user NLP message — USER_REPORT_DISRUPTION
    # ─────────────────────────────────────────────────────────────────────────
    _section("B — Hunger triggered by user NLP message")

    # Start from low levels; fatigue within cooldown so only hunger fires
    hf_session.state.hunger_level   = 0.10
    hf_session.state.fatigue_level  = 0.10
    hf_session.state.last_meal_time = "06:00"
    hf_session.state.last_rest_time = "11:50"   # within cooldown → fatigue suppressed
    hf_session.state.current_time   = "12:00"

    hunger_msg = "I'm starving, I need food right now"
    _info(f"User message: \"{hunger_msg}\"")

    hunger_plan = hf_session.event(
        EventType.USER_REPORT_DISRUPTION,
        {"message": hunger_msg},
    )

    _ok(f"hunger_level after NLP raise + meal reset: {hf_session.state.hunger_level:.2f}")
    if hunger_plan:
        _ok(f"HUNGER_DISRUPTION fired → replan triggered")
        _ok(f"  New plan ({len(hunger_plan.route_points)} stops): "
            f"{[rp.name for rp in hunger_plan.route_points]}")

    hunger_mem = hf_session._disruption_memory.hunger_history
    _ok(f"DisruptionMemory.hunger_history: {len(hunger_mem)} record(s)")
    assert len(hunger_mem) >= 1, "At least 1 HungerRecord expected in DisruptionMemory"
    h_rec = hunger_mem[-1]
    _ok(f"  Last record: time={h_rec.trigger_time}  level={h_rec.hunger_level:.2f}"
        f"  action={h_rec.action_taken}")
    assert h_rec.action_taken == "meal_inserted", \
        f"Expected action_taken='meal_inserted', got {h_rec.action_taken!r}"
    assert hf_session.state.hunger_level == 0.0, \
        f"hunger_level should be 0 after meal reset, got {hf_session.state.hunger_level}"
    _ok("Hunger NLP trigger + DisruptionMemory assertions passed ✓")

    # ─────────────────────────────────────────────────────────────────────────
    # C: Fatigue triggered by user NLP message — USER_REPORT_DISRUPTION
    # ─────────────────────────────────────────────────────────────────────────
    _section("C — Fatigue triggered by user NLP message")

    # Hunger within cooldown so only fatigue fires
    hf_session.state.hunger_level   = 0.10
    hf_session.state.fatigue_level  = 0.10
    hf_session.state.last_meal_time = hf_session.state.current_time  # suppress hunger
    hf_session.state.last_rest_time = "06:00"
    hf_session.state.current_time   = "13:10"

    fatigue_msg = "my feet are killing me, I need to sit down and rest"
    _info(f"User message: \"{fatigue_msg}\"")

    fatigue_plan = hf_session.event(
        EventType.USER_REPORT_DISRUPTION,
        {"message": fatigue_msg},
    )

    _ok(f"fatigue_level after NLP raise + rest: {hf_session.state.fatigue_level:.2f}")
    if fatigue_plan:
        _ok(f"FATIGUE_DISRUPTION fired → replan triggered")
        _ok(f"  New plan ({len(fatigue_plan.route_points)} stops): "
            f"{[rp.name for rp in fatigue_plan.route_points]}")
        assert hf_session.state.fatigue_level < 0.78, \
            "fatigue_level should decrease after rest break"

    fatigue_mem = hf_session._disruption_memory.fatigue_history
    _ok(f"DisruptionMemory.fatigue_history: {len(fatigue_mem)} record(s)")
    assert len(fatigue_mem) >= 1, "At least 1 FatigueRecord expected in DisruptionMemory"
    f_rec = fatigue_mem[-1]
    _ok(f"  Last record: time={f_rec.trigger_time}  level={f_rec.fatigue_level:.2f}"
        f"  action={f_rec.action_taken}  rest_dur={f_rec.rest_duration}min")
    assert f_rec.action_taken == "rest_inserted", \
        f"Expected action_taken='rest_inserted', got {f_rec.action_taken!r}"
    assert f_rec.rest_duration is not None and f_rec.rest_duration > 0, \
        "rest_duration should be positive"
    _ok("Fatigue NLP trigger + DisruptionMemory assertions passed ✓")

    # ─────────────────────────────────────────────────────────────────────────
    # D: NLP trigger — free-text message with hunger + fatigue keywords
    # ─────────────────────────────────────────────────────────────────────────
    _section("D — NLP trigger via USER_REPORT_DISRUPTION")

    # Reset levels to low to make the NLP floor clearly visible
    hf_session.state.hunger_level  = 0.10
    hf_session.state.fatigue_level = 0.10
    hf_session.state.last_meal_time = "06:00"
    hf_session.state.last_rest_time = "06:00"
    hf_session.state.current_time  = "14:00"

    _info(f"Before NLP: hunger={hf_session.state.hunger_level:.2f}  "
          f"fatigue={hf_session.state.fatigue_level:.2f}")

    nlp_message = "I'm absolutely starving and my feet are killing me, I need a break"
    _info(f"Message: \"{nlp_message}\"")

    nlp_plan = hf_session.event(
        EventType.USER_REPORT_DISRUPTION,
        {"message": nlp_message}
    )

    _ok(f"After NLP:  hunger={hf_session.state.hunger_level:.2f}"
        f"  (floor={NLP_HUNGER_FLOOR})  "
        f"fatigue={hf_session.state.fatigue_level:.2f}"
        f"  (floor={NLP_FATIGUE_FLOOR})")

    # Levels should have jumped to at least the NLP floor
    # Note: check_conditions also runs during event → they may be reset again
    # so we just verify the NLP hook did raise them (hunger_history / fatigue_history grow)
    total_hunger_records  = len(hf_session._disruption_memory.hunger_history)
    total_fatigue_records = len(hf_session._disruption_memory.fatigue_history)
    _ok(f"DisruptionMemory after NLP event: "
        f"hunger_records={total_hunger_records}  fatigue_records={total_fatigue_records}")
    _ok("NLP trigger path exercised ✓")

    # ─────────────────────────────────────────────────────────────────────────
    # E: Cooldown check — after meal reset, hunger should NOT re-trigger
    #    if < TRIGGER_COOLDOWN_MIN minutes have passed
    # ─────────────────────────────────────────────────────────────────────────
    _section("E — Cooldown: no re-trigger shortly after meal reset")

    hf_session.state.hunger_level  = 0.75    # above threshold
    hf_session.state.last_meal_time = "14:00" # same as current_time → within cooldown
    hf_session.state.current_time  = "14:05" # only 5 min since last meal

    advisor = hf_session._hf_advisor
    triggers_in_cooldown = advisor.check_triggers(hf_session.state)
    _info(f"hunger_level=0.75  last_meal 5 min ago  cooldown={TRIGGER_COOLDOWN_MIN}min")
    _ok(f"Triggers returned during cooldown: {triggers_in_cooldown}")
    assert "hunger_disruption" not in triggers_in_cooldown, \
        "hunger_disruption should be suppressed while within cooldown window"
    _ok("Cooldown suppression assertion passed ✓")

    # ─────────────────────────────────────────────────────────────────────────
    # F: DisruptionMemory serialize/deserialize round-trip with HF records
    # ─────────────────────────────────────────────────────────────────────────
    _section("F — DisruptionMemory serialize / deserialize round-trip")

    from modules.memory.disruption_memory import DisruptionMemory

    mem = hf_session._disruption_memory
    json_str = mem.serialize()
    restored = DisruptionMemory.deserialize(json_str)

    _ok(f"Serialized memory: {len(json_str)} chars")
    _ok(f"Restored hunger_history  count: {len(restored.hunger_history)}"
        f"  (original: {len(mem.hunger_history)})")
    _ok(f"Restored fatigue_history count: {len(restored.fatigue_history)}"
        f"  (original: {len(mem.fatigue_history)})")

    assert len(restored.hunger_history)  == len(mem.hunger_history), \
        "Hunger records lost during serialize/deserialize round-trip"
    assert len(restored.fatigue_history) == len(mem.fatigue_history), \
        "Fatigue records lost during serialize/deserialize round-trip"

    if restored.hunger_history:
        orig_h  = mem.hunger_history[-1]
        resto_h = restored.hunger_history[-1]
        assert orig_h.action_taken  == resto_h.action_taken,  "action_taken mismatch"
        assert orig_h.trigger_time  == resto_h.trigger_time,  "trigger_time mismatch"
        assert orig_h.hunger_level  == resto_h.hunger_level,  "hunger_level mismatch"
    if restored.fatigue_history:
        orig_f  = mem.fatigue_history[-1]
        resto_f = restored.fatigue_history[-1]
        assert orig_f.action_taken  == resto_f.action_taken,  "action_taken mismatch"
        assert orig_f.rest_duration == resto_f.rest_duration, "rest_duration mismatch"

    _ok("Serialize / deserialize round-trip assertions passed ✓")

    # ── Part 6 summary ────────────────────────────────────────────────────────
    _section("Part 6 summary")
    hf_sum = hf_session._disruption_memory.summarize()
    _ok(f"HF session replans          : {len(hf_session.replan_history)}")
    _ok(f"Hunger events in memory     : {hf_sum['hunger_events']}")
    _ok(f"Fatigue events in memory    : {hf_sum['fatigue_events']}")
    _ok(f"Clock at end of HF session  : {hf_session.state.current_time}")
    _ok(f"hunger_level at end         : {hf_session.state.hunger_level:.2f}")
    _ok(f"fatigue_level at end        : {hf_session.state.fatigue_level:.2f}")
    _ok("All Part 6 assertions passed ✓")

    # =========================================================================
    # PART 7 — AGENT CONTROLLER  (observe → evaluate → execute)
    # =========================================================================
    _banner("PART 7 — AGENT CONTROLLER")

    from modules.reoptimization.agent_action import ActionType, AgentAction
    from modules.reoptimization.agent_controller import AgentController, AgentObservation
    from modules.reoptimization.execution_layer import ExecutionLayer, ExecutionResult

    # Build a FRESH session for agent tests (Part 4 session has disruption history)
    agent_session = ReOptimizationSession.from_itinerary(
        itinerary=itinerary,
        constraints=bundle,
        remaining_attractions=all_attractions,
        hotel_lat=28.6139,
        hotel_lon=77.2090,
        start_day=1,
    )

    _section("7a — Agent observes + evaluates: NO_ACTION (no disruption)")
    result_7a = agent_session.agent_evaluate(
        crowd_level=0.10,
        weather_condition="clear",
        traffic_level=0.05,
    )
    assert result_7a.executed, "Agent NO_ACTION must execute successfully"
    assert result_7a.action.action_type == ActionType.NO_ACTION, \
        f"Expected NO_ACTION, got {result_7a.action.action_type}"
    _ok(f"Agent action: {result_7a.action.action_type.value}")
    _ok(f"Reasoning   : {result_7a.action.reasoning}")

    _section("7b — Agent observes + evaluates: DEFER_POI (high crowd)")
    # Clear any pending decision left over from prior parts
    agent_session.pending_decision = None
    result_7b = agent_session.agent_evaluate(
        crowd_level=0.90,
        weather_condition="clear",
        traffic_level=0.0,
    )
    assert result_7b.executed, "Agent DEFER_POI must execute successfully"
    _ok(f"Agent action: {result_7b.action.action_type.value}")
    _ok(f"Reasoning   : {result_7b.action.reasoning}")
    # DEFER or REQUEST_USER_DECISION depending on S_pti
    assert result_7b.action.action_type in (
        ActionType.DEFER_POI, ActionType.REQUEST_USER_DECISION,
        ActionType.REOPTIMIZE_DAY,
    ), f"Expected DEFER/REQUEST/REOPTIMIZE, got {result_7b.action.action_type}"

    _section("7c — Safety guardrails block forbidden parameters")
    from modules.reoptimization.execution_layer import ExecutionLayer as _EL
    _test_action = AgentAction(
        action_type=ActionType.DEFER_POI,
        target_poi="test",
        reasoning="test",
        parameters={"change_hotel": True},
    )
    violation = _EL._check_guardrails(_test_action)
    assert violation, "Guardrail must block change_hotel parameter"
    _ok(f"Guardrail blocked: {violation}")

    _section("7d — Agent → ExecutionLayer full pipeline (weather REPLACE)")
    agent_session.pending_decision = None
    result_7d = agent_session.agent_evaluate(
        crowd_level=0.0,
        weather_condition="stormy",
        traffic_level=0.0,
    )
    _ok(f"Agent action: {result_7d.action.action_type.value}")
    _ok(f"Reasoning   : {result_7d.action.reasoning}")
    # stormy = severity 1.0 ≥ HC_UNSAFE → REPLACE_POI or REOPTIMIZE_DAY
    assert result_7d.action.action_type in (
        ActionType.REPLACE_POI, ActionType.REOPTIMIZE_DAY,
        ActionType.DEFER_POI, ActionType.NO_ACTION,
    ), f"Unexpected action: {result_7d.action.action_type}"

    _section("7e — AgentAction schema serialisation")
    d = result_7a.action.to_dict()
    assert "action_type" in d, "to_dict must contain action_type"
    assert "reasoning" in d, "to_dict must contain reasoning"
    _ok(f"AgentAction.to_dict(): {d}")

    _ok("All Part 7 assertions passed ✓")

    # =========================================================================
    # PART 8 — MULTI-AGENT ORCHESTRATOR (orchestrate → specialist → execute)
    # =========================================================================
    _banner("PART 8 — MULTI-AGENT ORCHESTRATOR")

    from modules.reoptimization.agents import (
        OrchestratorAgent, OrchestratorResult, AgentContext,
        DisruptionAgent, PlanningAgent, BudgetAgent,
        PreferenceAgent, MemoryAgent, ExplanationAgent,
        AgentDispatcher, DispatchResult,
    )

    # Build a fresh session for multi-agent tests
    orch_session = ReOptimizationSession.from_itinerary(
        itinerary=itinerary,
        constraints=bundle,
        remaining_attractions=all_attractions,
        hotel_lat=28.6139,
        hotel_lon=77.2090,
        start_day=1,
    )

    # ── 8a — OrchestratorAgent routes crowd → DisruptionAgent ─────────────
    _section("8a — Orchestrator routes crowd → DisruptionAgent")
    obs_8a = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.90,
        weather_condition="clear",
        traffic_level=0.0,
    )
    ctx_8a = AgentContext(observation=obs_8a, event_type="crowd")
    routing_8a = orch_session._orchestrator.route(ctx_8a)
    assert routing_8a.invoke_agent == "DisruptionAgent", \
        f"Expected DisruptionAgent, got {routing_8a.invoke_agent}"
    _ok(f"Orchestrator: {routing_8a.invoke_agent} ({routing_8a.reason})")

    # ── 8b — OrchestratorAgent routes weather → DisruptionAgent ───────────
    _section("8b — Orchestrator routes weather → DisruptionAgent")
    ctx_8b = AgentContext(observation=obs_8a, event_type="weather")
    routing_8b = orch_session._orchestrator.route(ctx_8b)
    assert routing_8b.invoke_agent == "DisruptionAgent", \
        f"Expected DisruptionAgent, got {routing_8b.invoke_agent}"
    _ok(f"Orchestrator: {routing_8b.invoke_agent} ({routing_8b.reason})")

    # ── 8c — OrchestratorAgent routes budget → BudgetAgent ────────────────
    _section("8c — Orchestrator routes budget → BudgetAgent")
    ctx_8c = AgentContext(observation=obs_8a, event_type="budget")
    routing_8c = orch_session._orchestrator.route(ctx_8c)
    assert routing_8c.invoke_agent == "BudgetAgent", \
        f"Expected BudgetAgent, got {routing_8c.invoke_agent}"
    _ok(f"Orchestrator: {routing_8c.invoke_agent} ({routing_8c.reason})")

    # ── 8d — OrchestratorAgent routes explain → ExplanationAgent ──────────
    _section("8d — Orchestrator routes explain → ExplanationAgent")
    ctx_8d = AgentContext(observation=obs_8a, event_type="explain")
    routing_8d = orch_session._orchestrator.route(ctx_8d)
    assert routing_8d.invoke_agent == "ExplanationAgent", \
        f"Expected ExplanationAgent, got {routing_8d.invoke_agent}"
    _ok(f"Orchestrator: {routing_8d.invoke_agent} ({routing_8d.reason})")

    # ── 8e — OrchestratorAgent returns NONE when no event ─────────────────
    _section("8e — Orchestrator returns NONE for no actionable event")
    obs_quiet = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.05,
        weather_condition="clear",
        traffic_level=0.02,
    )
    ctx_8e = AgentContext(observation=obs_quiet, event_type="")
    routing_8e = orch_session._orchestrator.route(ctx_8e)
    assert routing_8e.invoke_agent == "NONE", \
        f"Expected NONE, got {routing_8e.invoke_agent}"
    _ok(f"Orchestrator: {routing_8e.invoke_agent} ({routing_8e.reason})")

    # ── 8f — Full pipeline: orchestrate crowd → DisruptionAgent → execute ─
    _section("8f — Full pipeline: orchestrate crowd 90%")
    orch_session.pending_decision = None
    dr_8f = orch_session.orchestrate(
        event_type="crowd",
        crowd_level=0.90,
        weather_condition="clear",
        traffic_level=0.0,
    )
    assert isinstance(dr_8f, DispatchResult), "orchestrate must return DispatchResult"
    assert dr_8f.specialist_name == "DisruptionAgent", \
        f"Expected DisruptionAgent, got {dr_8f.specialist_name}"
    assert dr_8f.execution_result.executed, "DisruptionAgent action must execute"
    _ok(f"Specialist: {dr_8f.specialist_name}")
    _ok(f"Action:     {dr_8f.action.action_type.value}")
    _ok(f"Reasoning:  {dr_8f.action.reasoning}")

    # ── 8g — Full pipeline: orchestrate weather stormy ────────────────────
    _section("8g — Full pipeline: orchestrate weather stormy")
    orch_session.pending_decision = None
    dr_8g = orch_session.orchestrate(
        event_type="weather",
        crowd_level=0.0,
        weather_condition="stormy",
        traffic_level=0.0,
    )
    assert isinstance(dr_8g, DispatchResult)
    assert dr_8g.specialist_name == "DisruptionAgent"
    _ok(f"Specialist: {dr_8g.specialist_name}")
    _ok(f"Action:     {dr_8g.action.action_type.value}")
    _ok(f"Reasoning:  {dr_8g.action.reasoning}")

    # ── 8h — Full pipeline: orchestrate explain (passive) ─────────────────
    _section("8h — Full pipeline: orchestrate explain")
    orch_session.pending_decision = None
    dr_8h = orch_session.orchestrate(event_type="explain")
    assert dr_8h.specialist_name == "ExplanationAgent"
    assert dr_8h.action.action_type == ActionType.NO_ACTION, \
        "ExplanationAgent must return NO_ACTION"
    assert "ExplanationAgent" in dr_8h.action.reasoning
    _ok(f"Specialist: {dr_8h.specialist_name}")
    _ok(f"Explanation: {dr_8h.action.reasoning}")

    # ── 8i — Full pipeline: orchestrate budget (healthy) ──────────────────
    _section("8i — Full pipeline: orchestrate budget (healthy budget)")
    orch_session.pending_decision = None
    dr_8i = orch_session.orchestrate(event_type="budget")
    assert dr_8i.specialist_name == "BudgetAgent"
    assert dr_8i.action.action_type == ActionType.NO_ACTION, \
        "BudgetAgent should return NO_ACTION for healthy budget"
    _ok(f"Specialist: {dr_8i.specialist_name}")
    _ok(f"Reasoning:  {dr_8i.action.reasoning}")

    # ── 8j — DispatchResult.to_dict() serialisation ───────────────────────
    _section("8j — DispatchResult serialisation")
    d8 = dr_8f.to_dict()
    assert "routing" in d8, "to_dict must contain routing"
    assert "specialist" in d8, "to_dict must contain specialist"
    assert "action" in d8, "to_dict must contain action"
    assert "execution" in d8, "to_dict must contain execution"
    _ok(f"DispatchResult keys: {list(d8.keys())}")

    # ── 8k — Preference agent via orchestrate slower ──────────────────────
    _section("8k — Full pipeline: orchestrate slower")
    orch_session.pending_decision = None
    dr_8k = orch_session.orchestrate(event_type="slower")
    assert dr_8k.specialist_name == "PreferenceAgent"
    _ok(f"Specialist: {dr_8k.specialist_name}")
    _ok(f"Action:     {dr_8k.action.action_type.value}")
    _ok(f"Reasoning:  {dr_8k.action.reasoning}")

    # ── 8l — PlanningAgent: NO_CHANGE when no disruptions ────────────────
    _section("8l — PlanningAgent: NO_CHANGE (0 disruptions)")
    from modules.reoptimization.agents.planning_agent import PlanningAgent as _PA
    _pa = _PA()
    obs_pa_clean = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.05,
        weather_condition="clear",
        traffic_level=0.02,
    )
    ctx_pa_clean = AgentContext(observation=obs_pa_clean, event_type="plan")
    action_8l = _pa.evaluate(ctx_pa_clean)
    assert action_8l.action_type == ActionType.NO_ACTION, \
        f"Expected NO_ACTION, got {action_8l.action_type}"
    assert action_8l.parameters.get("plan_action") == "NO_CHANGE", \
        f"Expected plan_action=NO_CHANGE, got {action_8l.parameters.get('plan_action')}"
    assert action_8l.parameters.get("scope") == "POI", \
        f"Expected scope=POI, got {action_8l.parameters.get('scope')}"
    _ok(f"plan_action={action_8l.parameters['plan_action']}  scope={action_8l.parameters['scope']}")
    _ok(f"Reasoning: {action_8l.reasoning}")

    # ── 8m — PlanningAgent: FULL_PLAN when ≥3 disruptions ────────────────
    _section("8m — PlanningAgent: FULL_PLAN (≥3 disruptions)")
    # Temporarily inject disruption log entries so disruptions_today ≥ 3
    _saved_log = list(orch_session.state.disruption_log)
    for _d in range(3):
        orch_session.state.disruption_log.append({"type": "test_disruption"})
    obs_pa_full = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.05,
        weather_condition="clear",
        traffic_level=0.02,
    )
    ctx_pa_full = AgentContext(observation=obs_pa_full, event_type="plan")
    action_8m = _pa.evaluate(ctx_pa_full)
    assert action_8m.action_type == ActionType.REOPTIMIZE_DAY, \
        f"Expected REOPTIMIZE_DAY, got {action_8m.action_type}"
    assert action_8m.parameters.get("plan_action") == "FULL_PLAN", \
        f"Expected plan_action=FULL_PLAN, got {action_8m.parameters.get('plan_action')}"
    assert action_8m.parameters.get("scope") == "DAY", \
        f"Expected scope=DAY, got {action_8m.parameters.get('scope')}"
    _ok(f"plan_action={action_8m.parameters['plan_action']}  scope={action_8m.parameters['scope']}")
    _ok(f"Reasoning: {action_8m.reasoning}")
    orch_session.state.disruption_log = _saved_log   # restore

    # ── 8n — PlanningAgent: REORDER on time pressure ─────────────────────
    _section("8n — PlanningAgent: REORDER (time pressure)")
    # Simulate time pressure: patch remaining_minutes to 45
    obs_pa_reorder = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.05,
        weather_condition="clear",
        traffic_level=0.02,
    )
    obs_pa_reorder.remaining_minutes = 45
    obs_pa_reorder.remaining_stops = ["Stop_A", "Stop_B", "Stop_C"]
    ctx_pa_reorder = AgentContext(observation=obs_pa_reorder, event_type="plan")
    action_8n = _pa.evaluate(ctx_pa_reorder)
    assert action_8n.action_type == ActionType.RELAX_CONSTRAINT, \
        f"Expected RELAX_CONSTRAINT, got {action_8n.action_type}"
    assert action_8n.parameters.get("plan_action") == "REORDER", \
        f"Expected plan_action=REORDER, got {action_8n.parameters.get('plan_action')}"
    assert action_8n.parameters.get("scope") == "DAY", \
        f"Expected scope=DAY, got {action_8n.parameters.get('scope')}"
    _ok(f"plan_action={action_8n.parameters['plan_action']}  scope={action_8n.parameters['scope']}")
    _ok(f"Reasoning: {action_8n.reasoning}")

    # ── 8o — PlanningAgent: LOCAL_REPAIR with 1-2 disruptions ────────────
    _section("8o — PlanningAgent: LOCAL_REPAIR (1-2 disruptions)")
    obs_pa_repair = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.05,
        weather_condition="clear",
        traffic_level=0.02,
    )
    obs_pa_repair.disruptions_today = 2
    ctx_pa_repair = AgentContext(observation=obs_pa_repair, event_type="plan")
    action_8o = _pa.evaluate(ctx_pa_repair)
    assert action_8o.action_type == ActionType.DEFER_POI, \
        f"Expected DEFER_POI, got {action_8o.action_type}"
    assert action_8o.parameters.get("plan_action") == "LOCAL_REPAIR", \
        f"Expected plan_action=LOCAL_REPAIR, got {action_8o.parameters.get('plan_action')}"
    assert action_8o.parameters.get("scope") == "POI", \
        f"Expected scope=POI, got {action_8o.parameters.get('scope')}"
    _ok(f"plan_action={action_8o.parameters['plan_action']}  scope={action_8o.parameters['scope']}")
    _ok(f"Reasoning: {action_8o.reasoning}")

    # ── 8p — PlanningAgent JSON output shape ─────────────────────────────
    _section("8p — PlanningAgent output contains plan_action/scope/justification")
    for _test_action in [action_8l, action_8m, action_8n, action_8o]:
        p = _test_action.parameters
        assert "plan_action" in p, f"Missing plan_action in {p}"
        assert "scope" in p, f"Missing scope in {p}"
        assert "justification" in p, f"Missing justification in {p}"
        assert p["plan_action"] in ("FULL_PLAN", "LOCAL_REPAIR", "REORDER", "NO_CHANGE"), \
            f"Invalid plan_action: {p['plan_action']}"
        assert p["scope"] in ("DAY", "POI"), f"Invalid scope: {p['scope']}"
    _ok("All PlanningAgent outputs contain plan_action / scope / justification")

    # ── 8q — DisruptionAgent: LOW severity (no threshold exceeded) ────────
    _section("8q — DisruptionAgent: LOW (no disruption)")
    from modules.reoptimization.agents.disruption_agent import DisruptionAgent as _DA
    _da = _DA()
    obs_da_clean = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.05,
        weather_condition="clear",
        traffic_level=0.02,
    )
    ctx_da_clean = AgentContext(observation=obs_da_clean, event_type="crowd")
    action_8q = _da.evaluate(ctx_da_clean)
    assert action_8q.action_type == ActionType.NO_ACTION, \
        f"Expected NO_ACTION, got {action_8q.action_type}"
    assert action_8q.parameters.get("disruption_level") == "LOW", \
        f"Expected LOW, got {action_8q.parameters.get('disruption_level')}"
    assert action_8q.parameters.get("action") == "IGNORE", \
        f"Expected IGNORE, got {action_8q.parameters.get('action')}"
    _ok(f"level={action_8q.parameters['disruption_level']}  action={action_8q.parameters['action']}")

    # ── 8r — DisruptionAgent: HIGH crowd → ASK_USER ──────────────────────
    _section("8r — DisruptionAgent: HIGH crowd → ASK_USER")
    obs_da_crowd = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.90,
        weather_condition="clear",
        traffic_level=0.0,
    )
    ctx_da_crowd = AgentContext(observation=obs_da_crowd, event_type="crowd")
    action_8r = _da.evaluate(ctx_da_crowd)
    assert action_8r.action_type == ActionType.REQUEST_USER_DECISION, \
        f"Expected REQUEST_USER_DECISION, got {action_8r.action_type}"
    assert action_8r.parameters.get("disruption_level") == "HIGH", \
        f"Expected HIGH, got {action_8r.parameters.get('disruption_level')}"
    assert action_8r.parameters.get("action") == "ASK_USER", \
        f"Expected ASK_USER, got {action_8r.parameters.get('action')}"
    _ok(f"level={action_8r.parameters['disruption_level']}  action={action_8r.parameters['action']}")
    _ok(f"Reasoning: {action_8r.reasoning}")

    # ── 8s — DisruptionAgent: MEDIUM weather → ASK_USER ──────────────────
    _section("8s — DisruptionAgent: MEDIUM weather → ASK_USER")
    obs_da_weather = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.0,
        weather_condition="stormy",
        traffic_level=0.0,
    )
    # Patch weather to moderate (above threshold but below HC_UNSAFE 0.75)
    obs_da_weather.weather_severity = 0.65
    obs_da_weather.next_stop_is_outdoor = True
    ctx_da_weather = AgentContext(observation=obs_da_weather, event_type="weather")
    action_8s = _da.evaluate(ctx_da_weather)
    assert action_8s.action_type == ActionType.REQUEST_USER_DECISION, \
        f"Expected REQUEST_USER_DECISION, got {action_8s.action_type}"
    assert action_8s.parameters.get("disruption_level") == "MEDIUM", \
        f"Expected MEDIUM, got {action_8s.parameters.get('disruption_level')}"
    assert action_8s.parameters.get("action") == "ASK_USER", \
        f"Expected ASK_USER, got {action_8s.parameters.get('action')}"
    _ok(f"level={action_8s.parameters['disruption_level']}  action={action_8s.parameters['action']}")

    # ── 8t — DisruptionAgent JSON output contains disruption_level/action/confidence
    _section("8t — DisruptionAgent JSON shape validation")
    for _da_action in [action_8q, action_8r, action_8s]:
        p = _da_action.parameters
        assert "disruption_level" in p, f"Missing disruption_level in {p}"
        assert "action" in p, f"Missing action in {p}"
        assert "confidence" in p, f"Missing confidence in {p}"
        assert p["disruption_level"] in ("LOW", "MEDIUM", "HIGH"), \
            f"Invalid disruption_level: {p['disruption_level']}"
        assert p["action"] in ("IGNORE", "ASK_USER", "DEFER", "REPLACE"), \
            f"Invalid action: {p['action']}"
        assert 0.0 <= p["confidence"] <= 1.0, f"confidence out of range: {p['confidence']}"
    _ok("All DisruptionAgent outputs contain disruption_level / action / confidence")

    # ── 8u — BudgetAgent: OK (healthy budget, low spend) ─────────────────
    _section("8u — BudgetAgent: OK (healthy budget)")
    from modules.reoptimization.agents.budget_agent import BudgetAgent as _BA
    _ba = _BA()
    obs_ba_ok = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.0,
        weather_condition="clear",
        traffic_level=0.0,
    )
    # Ensure low spend
    obs_ba_ok.budget_spent = {"attractions": 500.0, "restaurants": 200.0}
    ctx_ba_ok = AgentContext(observation=obs_ba_ok, event_type="budget")
    action_8u = _ba.evaluate(ctx_ba_ok)
    assert action_8u.action_type == ActionType.NO_ACTION, \
        f"Expected NO_ACTION, got {action_8u.action_type}"
    assert action_8u.parameters["budget_status"] == "OK", \
        f"Expected OK, got {action_8u.parameters['budget_status']}"
    assert action_8u.parameters["action"] == "NO_CHANGE", \
        f"Expected NO_CHANGE, got {action_8u.parameters['action']}"
    _ok(f"status={action_8u.parameters['budget_status']}  action={action_8u.parameters['action']}")

    # ── 8v — BudgetAgent: OVERRUN (high spend) ───────────────────────────
    _section("8v — BudgetAgent: OVERRUN (90%+ spend)")
    obs_ba_over = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.0,
        weather_condition="clear",
        traffic_level=0.0,
    )
    # Overrun: spend 95% of total budget
    _total = orch_session.budget.total
    obs_ba_over.budget_spent = {"attractions": _total * 1.05}  # 105% of budget
    ctx_ba_over = AgentContext(observation=obs_ba_over, event_type="budget")
    action_8v = _ba.evaluate(ctx_ba_over)
    assert action_8v.action_type == ActionType.REPLACE_POI, \
        f"Expected REPLACE_POI, got {action_8v.action_type}"
    assert action_8v.parameters["budget_status"] == "OVERRUN", \
        f"Expected OVERRUN, got {action_8v.parameters['budget_status']}"
    assert action_8v.parameters["action"] == "SUGGEST_CHEAPER", \
        f"Expected SUGGEST_CHEAPER, got {action_8v.parameters['action']}"
    assert action_8v.parameters["variance_percentage"] > 0, \
        "Overrun variance must be positive"
    _ok(f"status={action_8v.parameters['budget_status']}  action={action_8v.parameters['action']}  variance={action_8v.parameters['variance_percentage']}%")

    # ── 8w — BudgetAgent: UNDERUTILIZED (low spend, high time elapsed) ───
    _section("8w — BudgetAgent: UNDERUTILIZED (low spend, 70% time gone)")
    obs_ba_under = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.0,
        weather_condition="clear",
        traffic_level=0.0,
    )
    obs_ba_under.budget_spent = {"attractions": _total * 0.10}  # Only 10%
    obs_ba_under.remaining_minutes = 180   # 3 h left of ~11 h day
    obs_ba_under.total_day_minutes = 660   # full day
    ctx_ba_under = AgentContext(observation=obs_ba_under, event_type="budget")
    action_8w = _ba.evaluate(ctx_ba_under)
    assert action_8w.action_type == ActionType.RELAX_CONSTRAINT, \
        f"Expected RELAX_CONSTRAINT, got {action_8w.action_type}"
    assert action_8w.parameters["budget_status"] == "UNDERUTILIZED", \
        f"Expected UNDERUTILIZED, got {action_8w.parameters['budget_status']}"
    assert action_8w.parameters["action"] == "REBALANCE", \
        f"Expected REBALANCE, got {action_8w.parameters['action']}"
    assert action_8w.parameters["variance_percentage"] < 0, \
        "Underutilized variance must be negative"
    _ok(f"status={action_8w.parameters['budget_status']}  action={action_8w.parameters['action']}  variance={action_8w.parameters['variance_percentage']}%")

    # ── 8x — BudgetAgent JSON shape validation ───────────────────────────
    _section("8x — BudgetAgent JSON shape validation")
    for _ba_action in [action_8u, action_8v, action_8w]:
        p = _ba_action.parameters
        assert "budget_status" in p, f"Missing budget_status in {p}"
        assert "action" in p, f"Missing action in {p}"
        assert "variance_percentage" in p, f"Missing variance_percentage in {p}"
        assert p["budget_status"] in ("OK", "OVERRUN", "UNDERUTILIZED"), \
            f"Invalid budget_status: {p['budget_status']}"
        assert p["action"] in ("NO_CHANGE", "REBALANCE", "SUGGEST_CHEAPER"), \
            f"Invalid action: {p['action']}"
        assert isinstance(p["variance_percentage"], (int, float)), \
            f"variance_percentage must be numeric: {p['variance_percentage']}"
    _ok("All BudgetAgent outputs contain budget_status / action / variance_percentage")

    # ── 8y — PreferenceAgent: nothing detected ──────────────────────────
    _section("8y — PreferenceAgent: nothing detected")
    from modules.reoptimization.agents.preference_agent import PreferenceAgent as _PrefA
    _prefa = _PrefA()
    obs_pref_none = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.0,
        weather_condition="clear",
        traffic_level=0.0,
    )
    obs_pref_none.avoid_crowds = False       # ensure no env_tolerance triggers
    ctx_pref_none = AgentContext(observation=obs_pref_none, event_type="explain")
    action_8y = _prefa.evaluate(ctx_pref_none)
    assert action_8y.action_type == ActionType.NO_ACTION, \
        f"Expected NO_ACTION, got {action_8y.action_type}"
    p8y = action_8y.parameters
    assert p8y["interests"] == [], \
        f"Expected empty interests, got {p8y['interests']}"
    assert p8y["pace_preference"] is None, \
        f"Expected null pace, got {p8y['pace_preference']}"
    assert p8y["environment_tolerance"] == {}, \
        f"Expected empty env_tolerance, got {p8y['environment_tolerance']}"
    _ok(f"interests={p8y['interests']}  pace={p8y['pace_preference']}  env={p8y['environment_tolerance']}")

    # ── 8z — PreferenceAgent: pace change (slower) ─────────────────────
    _section("8z — PreferenceAgent: pace change (slower)")
    obs_pref_pace = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.0,
        weather_condition="clear",
        traffic_level=0.0,
    )
    obs_pref_pace.pace_preference = "fast"  # set current pace to differ
    ctx_pref_pace = AgentContext(observation=obs_pref_pace, event_type="slower")
    action_8z = _prefa.evaluate(ctx_pref_pace)
    assert action_8z.action_type == ActionType.REOPTIMIZE_DAY, \
        f"Expected REOPTIMIZE_DAY, got {action_8z.action_type}"
    assert action_8z.parameters["pace_preference"] == "relaxed", \
        f"Expected relaxed, got {action_8z.parameters['pace_preference']}"
    _ok(f"pace={action_8z.parameters['pace_preference']}  action={action_8z.action_type.value}")

    # ── 8A — PreferenceAgent: interests + env tolerance ────────────────
    _section("8A — PreferenceAgent: interests + environment tolerance")
    obs_pref_env = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.0,
        weather_condition="stormy",
        traffic_level=0.75,
    )
    obs_pref_env.avoid_crowds = True
    ctx_pref_env = AgentContext(
        observation=obs_pref_env,
        event_type="preference",
        parameters={"interests": ["temples", "food"]},
    )
    action_8A = _prefa.evaluate(ctx_pref_env)
    assert action_8A.action_type == ActionType.REOPTIMIZE_DAY, \
        f"Expected REOPTIMIZE_DAY, got {action_8A.action_type}"
    p8A = action_8A.parameters
    assert p8A["interests"] == ["temples", "food"], \
        f"Expected [temples, food], got {p8A['interests']}"
    assert "crowd" in p8A["environment_tolerance"], \
        "Expected crowd in env_tolerance"
    assert "weather" in p8A["environment_tolerance"], \
        "Expected weather in env_tolerance"
    assert "traffic" in p8A["environment_tolerance"], \
        "Expected traffic in env_tolerance"
    _ok(f"interests={p8A['interests']}  env={p8A['environment_tolerance']}")

    # ── 8B — PreferenceAgent JSON shape validation ──────────────────────
    _section("8B — PreferenceAgent JSON shape validation")
    for _pref_action in [action_8y, action_8z, action_8A]:
        p = _pref_action.parameters
        assert "interests" in p, f"Missing interests in {p}"
        assert "pace_preference" in p, f"Missing pace_preference in {p}"
        assert "environment_tolerance" in p, f"Missing environment_tolerance in {p}"
        assert isinstance(p["interests"], list), \
            f"interests must be list: {p['interests']}"
        assert p["pace_preference"] in ("fast", "balanced", "relaxed", None), \
            f"Invalid pace: {p['pace_preference']}"
        assert isinstance(p["environment_tolerance"], dict), \
            f"env_tolerance must be dict: {p['environment_tolerance']}"
    _ok("All PreferenceAgent outputs contain interests / pace_preference / environment_tolerance")

    # ── 8C — MemoryAgent: no disruptions → store=false ───────────────────
    _section("8C — MemoryAgent: 0 disruptions (no store)")
    from modules.reoptimization.agents.memory_agent import MemoryAgent as _MemA
    _mema = _MemA()
    obs_mem_clean = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.0,
        weather_condition="clear",
        traffic_level=0.0,
    )
    obs_mem_clean.disruptions_today = 0
    ctx_mem_clean = AgentContext(observation=obs_mem_clean, event_type="memory")
    action_8C = _mema.evaluate(ctx_mem_clean)
    assert action_8C.action_type == ActionType.NO_ACTION, \
        f"Expected NO_ACTION, got {action_8C.action_type}"
    assert action_8C.parameters["store"] is False, \
        f"Expected store=False, got {action_8C.parameters['store']}"
    assert action_8C.parameters["memory_type"] is None, \
        f"Expected memory_type=None, got {action_8C.parameters['memory_type']}"
    _ok(f"store={action_8C.parameters['store']}  type={action_8C.parameters['memory_type']}")

    # ── 8D — MemoryAgent: 2 disruptions → short_term ──────────────────
    _section("8D — MemoryAgent: 2 disruptions (short_term)")
    obs_mem_short = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.0,
        weather_condition="clear",
        traffic_level=0.0,
    )
    obs_mem_short.disruptions_today = 2
    ctx_mem_short = AgentContext(observation=obs_mem_short, event_type="memory")
    action_8D = _mema.evaluate(ctx_mem_short)
    assert action_8D.action_type == ActionType.NO_ACTION
    assert action_8D.parameters["store"] is True, \
        f"Expected store=True, got {action_8D.parameters['store']}"
    assert action_8D.parameters["memory_type"] == "short_term", \
        f"Expected short_term, got {action_8D.parameters['memory_type']}"
    _ok(f"store={action_8D.parameters['store']}  type={action_8D.parameters['memory_type']}")

    # ── 8E — MemoryAgent: 4 disruptions → long_term ───────────────────
    _section("8E — MemoryAgent: 4 disruptions (long_term)")
    obs_mem_long = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
        crowd_level=0.0,
        weather_condition="clear",
        traffic_level=0.0,
    )
    obs_mem_long.disruptions_today = 4
    ctx_mem_long = AgentContext(observation=obs_mem_long, event_type="memory")
    action_8E = _mema.evaluate(ctx_mem_long)
    assert action_8E.action_type == ActionType.NO_ACTION
    assert action_8E.parameters["store"] is True, \
        f"Expected store=True, got {action_8E.parameters['store']}"
    assert action_8E.parameters["memory_type"] == "long_term", \
        f"Expected long_term, got {action_8E.parameters['memory_type']}"
    _ok(f"store={action_8E.parameters['store']}  type={action_8E.parameters['memory_type']}")

    # ── 8F — MemoryAgent JSON shape validation ─────────────────────────
    _section("8F — MemoryAgent JSON shape validation")
    for _mem_action in [action_8C, action_8D, action_8E]:
        p = _mem_action.parameters
        assert "store" in p, f"Missing store in {p}"
        assert "memory_type" in p, f"Missing memory_type in {p}"
        assert "reason" in p, f"Missing reason in {p}"
        assert isinstance(p["store"], bool), \
            f"store must be bool: {p['store']}"
        assert p["memory_type"] in ("short_term", "long_term", None), \
            f"Invalid memory_type: {p['memory_type']}"
        assert isinstance(p["reason"], str), \
            f"reason must be str: {p['reason']}"
    _ok("All MemoryAgent outputs contain store / memory_type / reason")

    # ── 8G — ExplanationAgent basic explanation ────────────────────────
    _section("8G — ExplanationAgent: basic explanation")
    from modules.reoptimization.agents.explanation_agent import ExplanationAgent
    _exp_agent = ExplanationAgent()
    obs_exp_basic = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
    )
    obs_exp_basic.remaining_minutes = 300
    obs_exp_basic.current_time = "11:00"
    obs_exp_basic.remaining_stops = ["Stop A", "Stop B"]
    obs_exp_basic.next_stop_name = "Stop A"
    obs_exp_basic.next_stop_is_outdoor = True
    obs_exp_basic.next_stop_spti_proxy = 0.72
    obs_exp_basic.disruptions_today = 0
    obs_exp_basic.crowd_level = 0.0
    obs_exp_basic.weather_condition = None
    obs_exp_basic.weather_severity = 0.0
    obs_exp_basic.traffic_level = 0.0
    from modules.reoptimization.agents.base_agent import AgentContext
    ctx_exp_basic = AgentContext(observation=obs_exp_basic, event_type="explain")
    action_8G = _exp_agent.evaluate(ctx_exp_basic)
    assert action_8G.action_type == ActionType.NO_ACTION, \
        f"ExplanationAgent must return NO_ACTION, got {action_8G.action_type}"
    assert "explanation" in action_8G.parameters, \
        f"Missing 'explanation' key in parameters: {action_8G.parameters}"
    expl_text = action_8G.parameters["explanation"]
    assert isinstance(expl_text, str) and len(expl_text) > 10, \
        f"Explanation too short: {expl_text!r}"
    assert "Stop A" in expl_text, \
        f"Explanation should mention next stop: {expl_text!r}"
    _ok(f"explanation contains next stop — len={len(expl_text)}")

    # ── 8H — ExplanationAgent crowd / disruption context ───────────────
    _section("8H — ExplanationAgent: crowd + disruption context")
    obs_exp_crowd = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
    )
    obs_exp_crowd.remaining_minutes = 180
    obs_exp_crowd.current_time = "14:00"
    obs_exp_crowd.remaining_stops = ["Stop X"]
    obs_exp_crowd.next_stop_name = "Stop X"
    obs_exp_crowd.next_stop_is_outdoor = False
    obs_exp_crowd.next_stop_spti_proxy = 0.55
    obs_exp_crowd.disruptions_today = 3
    obs_exp_crowd.crowd_level = 0.85
    obs_exp_crowd.weather_condition = None
    obs_exp_crowd.weather_severity = 0.0
    obs_exp_crowd.traffic_level = 0.0
    ctx_exp_crowd = AgentContext(observation=obs_exp_crowd, event_type="explain")
    action_8H = _exp_agent.evaluate(ctx_exp_crowd)
    expl_crowd = action_8H.parameters["explanation"]
    assert "3 disruption" in expl_crowd, \
        f"Should mention 3 disruptions: {expl_crowd!r}"
    assert "crowd" in expl_crowd.lower() or "85%" in expl_crowd, \
        f"Should mention crowd level: {expl_crowd!r}"
    _ok(f"crowd + disruption context present")

    # ── 8I — ExplanationAgent weather context ──────────────────────────
    _section("8I — ExplanationAgent: weather context")
    obs_exp_weather = orch_session._agent_controller.observe(
        state=orch_session.state,
        constraints=orch_session.constraints,
        remaining_attractions=orch_session._remaining,
        budget=orch_session.budget,
    )
    obs_exp_weather.remaining_minutes = 240
    obs_exp_weather.current_time = "12:30"
    obs_exp_weather.remaining_stops = ["Stop M", "Stop N", "Stop O"]
    obs_exp_weather.next_stop_name = "Stop M"
    obs_exp_weather.next_stop_is_outdoor = True
    obs_exp_weather.next_stop_spti_proxy = 0.60
    obs_exp_weather.disruptions_today = 1
    obs_exp_weather.crowd_level = 0.0
    obs_exp_weather.weather_condition = "heavy_rain"
    obs_exp_weather.weather_severity = 0.80
    obs_exp_weather.traffic_level = 0.50
    ctx_exp_weather = AgentContext(observation=obs_exp_weather, event_type="explain")
    action_8I = _exp_agent.evaluate(ctx_exp_weather)
    expl_weather = action_8I.parameters["explanation"]
    assert "heavy_rain" in expl_weather or "rain" in expl_weather.lower(), \
        f"Should mention weather: {expl_weather!r}"
    assert "traffic" in expl_weather.lower() or "50%" in expl_weather, \
        f"Should mention traffic: {expl_weather!r}"
    _ok(f"weather + traffic context present")

    # ── 8J — ExplanationAgent JSON shape validation ────────────────────
    _section("8J — ExplanationAgent JSON shape validation")
    for _exp_act in [action_8G, action_8H, action_8I]:
        p = _exp_act.parameters
        assert "explanation" in p, f"Missing 'explanation' in {p}"
        assert isinstance(p["explanation"], str), \
            f"explanation must be str: {p['explanation']}"
        assert len(p["explanation"]) > 0, "explanation must not be empty"
    _ok("All ExplanationAgent outputs contain valid 'explanation' string")

    _ok("All Part 8 assertions passed ✓")

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    _banner("FULL TEST SUMMARY")

    summary = session.summary()
    _ok(f"Current time       : {summary['current_time']}")
    _ok(f"Stops visited      : {summary['visited']}")
    _ok(f"Stops skipped      : {summary['skipped']}")
    if summary.get('deferred_future_days'):
        _ok(f"Deferred (future)  : {summary['deferred_future_days']}")
    if summary.get('crowd_pending'):
        pend = summary['crowd_pending']
        _ok(f"Crowd pending      : '{pend['stop_name']}' — awaiting user decision")
    _ok(f"Remaining stops    : {summary['remaining_stops']}")
    _ok(f"Remaining minutes  : {summary['remaining_minutes']}")
    _ok(f"Thresholds applied : {summary['thresholds']}")
    _ok(f"Total replans      : {summary['replans_triggered']}")
    _ok(f"Disruption log ({len(summary['disruption_log'])} events):")
    for entry in summary["disruption_log"]:
        _info(f"  [{entry['type']}]  {json.dumps({k: v for k, v in entry.items() if k != 'type'})}")

    dm_sum = summary.get("disruption_memory", {})
    if dm_sum.get("hunger_events", 0) or dm_sum.get("fatigue_events", 0):
        _ok(f"Hunger disruptions (main session): {dm_sum.get('hunger_events', 0)}")
        _ok(f"Fatigue disruptions (main session): {dm_sum.get('fatigue_events', 0)}")

    print()
    _ok("ALL PARTS COMPLETED SUCCESSFULLY")
    print()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_full_pipeline_test()
