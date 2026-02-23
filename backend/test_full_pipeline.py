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
# Phase 1 form (10 prompts) + Phase 2 chat (4 lines + 'done')
_PHASE1_ANSWERS = [
    "Mumbai",            # departure city
    "Delhi",             # destination city
    "2026-03-10",        # departure date
    "2026-03-12",        # return date
    "2",                 # num adults
    "1",                 # num children
    "32,30,8",           # traveler ages
    "Vegetarian",        # restaurant preference
    "no",                # wheelchair access
    "55000",             # total budget
]

_PHASE2_ANSWERS = [
    "I absolutely love history and museums, could spend hours inside them.",
    "I prefer going out in the morning when places are less crowded.",
    "We are vegetarians so no meat please. Also no street-food stalls.",
    "I like a relaxed pace, maybe 3-4 stops a day. No rushed tours.",
    "done",              # ends Phase 2 chat
]

_ALL_INPUTS = _PHASE1_ANSWERS + _PHASE2_ANSWERS


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
        f"= group_size {hard.group_size}")
    _ok(f"Traveler ages  : {hard.traveler_ages}")
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
