"""
modules/reoptimization/session.py
-----------------------------------
ReOptimizationSession — top-level orchestrator for mid-trip re-planning.

Wraps TripState, EventHandler, ConditionMonitor, and PartialReplanner
into a single interface the rest of the system (main.py --reoptimize,
an API endpoint, or a UI) can drive.

Lifecycle:
    session = ReOptimizationSession.from_itinerary(itinerary, constraints)

    # Advance through stops normally
    session.advance_to_stop("City Museum")

    # Check environmental readings → auto-replan if thresholds exceeded
    new_plan = session.check_conditions(crowd_level=0.7, weather="rainy")

    # Or fire a user event directly
    new_plan = session.event(EventType.USER_SKIP, {"stop_name": "Heritage Fort"})

    # Inspect live state
    print(session.state.current_time, session.thresholds.describe())
"""

from __future__ import annotations
from datetime import date
from typing import Optional

from schemas.constraints import ConstraintBundle
from schemas.itinerary import BudgetAllocation, DayPlan, Itinerary
from modules.tool_usage.attraction_tool import AttractionRecord
from modules.tool_usage.historical_tool import HistoricalInsightTool
from modules.reoptimization.trip_state import TripState
from modules.reoptimization.event_handler import EventHandler, EventType, ReplanDecision
from modules.reoptimization.condition_monitor import ConditionMonitor
from modules.reoptimization.partial_replanner import PartialReplanner
from modules.reoptimization.crowd_advisory import CrowdAdvisory, CrowdAdvisoryResult
from modules.reoptimization.weather_advisor import WeatherAdvisor, WeatherAdvisoryResult
from modules.reoptimization.traffic_advisor import TrafficAdvisor, TrafficAdvisoryResult
from modules.memory.disruption_memory import DisruptionMemory
from modules.reoptimization.user_edit_handler import (
    UserEditHandler, DislikeResult, ReplaceResult, SkipResult,
)
from modules.reoptimization.hunger_fatigue_advisor import (
    HungerFatigueAdvisor, HungerAdvisoryResult, FatigueAdvisoryResult,
)


class ReOptimizationSession:
    """
    Manages the re-optimization lifecycle for one active trip day.

    Single source of truth for:
      - Live TripState (position, time, visited stops)
      - User-personalized thresholds (from ConditionMonitor)
      - Accumulated disruption log
      - Latest DayPlan (may be a replanned version)
    """

    def __init__(
        self,
        state: TripState,
        constraints: ConstraintBundle,
        remaining_attractions: list[AttractionRecord],
        budget: BudgetAllocation,
        total_days: int = 1,
    ) -> None:
        self.state                 = state
        self.constraints           = constraints
        self._remaining            = list(remaining_attractions)
        self.budget                = budget
        self.total_days            = total_days

        self._event_handler        = EventHandler()
        self._condition_monitor    = ConditionMonitor(
            constraints.soft, self._remaining, total_days=total_days
        )
        self._partial_replanner    = PartialReplanner()
        self._crowd_advisory       = CrowdAdvisory(HistoricalInsightTool())
        self._weather_advisor      = WeatherAdvisor()
        self._traffic_advisor      = TrafficAdvisor()
        self._disruption_memory    = DisruptionMemory()
        self._user_edit            = UserEditHandler()
        self._hf_advisor           = HungerFatigueAdvisor()

        # Destination city for historical insight lookup
        self._city = constraints.hard.destination_city if constraints.hard else ""

        # Thresholds exposed for display / debugging
        self.thresholds            = self._condition_monitor.thresholds

        # Log of all replan decisions this session
        self.replan_history: list[dict] = []

        # Stops deferred to future days due to crowds: {stop_name: target_day}
        self.future_deferred: dict[str, int] = {}

        # Pending user decision when stop is crowded on last day
        # Set to a dict with keys: stop_name, place_importance, crowd_level
        self.crowd_pending_decision: dict | None = None

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_itinerary(
        cls,
        itinerary: Itinerary,
        constraints: ConstraintBundle,
        remaining_attractions: list[AttractionRecord],
        hotel_lat: float = 0.0,
        hotel_lon: float = 0.0,
        start_day: int = 1,
    ) -> "ReOptimizationSession":
        """
        Construct a session from a freshly generated Itinerary.
        Starts at the hotel position at 09:00 on the first trip day.
        """
        first_day = itinerary.days[start_day - 1] if itinerary.days else None
        total_days = len(itinerary.days)
        state = TripState(
            current_lat=hotel_lat,
            current_lon=hotel_lon,
            current_time="09:00",
            current_day=start_day,
            current_day_date=(
                first_day.date if first_day else constraints.hard.departure_date
            ),
            current_day_plan=first_day,
        )
        return cls(
            state=state,
            constraints=constraints,
            remaining_attractions=remaining_attractions,
            budget=itinerary.budget,
            total_days=total_days,
        )

    # ── Advance through the plan normally ────────────────────────────────────

    def advance_to_stop(
        self,
        stop_name: str,
        arrival_time: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        cost: float = 0.0,
        duration_minutes: int = 60,
        intensity_level: str = "medium",
    ) -> None:
        """
        Record that the traveller has arrived at (and departed from) a stop.
        Updates clock, position, visited set, budget, and hunger/fatigue state.
        """
        if arrival_time:
            self.state.advance_time(arrival_time)
        if lat is not None and lon is not None:
            self.state.move_to(lat, lon)
        self.state.mark_visited(stop_name, cost)

        # Accumulate hunger and fatigue from this stop
        self._hf_advisor.accumulate(self.state, intensity_level, duration_minutes)

        # Update remaining pool
        self._remaining = [a for a in self._remaining if a.name not in self.state.visited_stops]
        self._condition_monitor.update_remaining(self._remaining)
        print(f"  [Session] Visited '{stop_name}' at {self.state.current_time}. "
              f"Remaining stops: {len(self._remaining)}  "
              f"| Hunger: {self.state.hunger_level:.0%}  "
              f"| Fatigue: {self.state.fatigue_level:.0%}")

    # ── Environmental condition check ────────────────────────────────────────

    def check_conditions(
        self,
        crowd_level: float | None = None,
        traffic_level: float | None = None,
        weather_condition: str | None = None,
        next_stop_name: str = "",
        next_stop_is_outdoor: bool = False,
        estimated_traffic_delay_minutes: int = 0,
    ) -> Optional[DayPlan]:
        """
        Feed real-time environmental data into ConditionMonitor.
        If any threshold is exceeded, triggers a PartialReplanner run.

        Returns:
            New DayPlan if a replan was triggered, else None.
        """
        decisions = self._condition_monitor.check(
            state=self.state,
            crowd_level=crowd_level,
            traffic_level=traffic_level,
            weather_condition=weather_condition,
            next_stop_name=next_stop_name,
            next_stop_is_outdoor=next_stop_is_outdoor,
            estimated_traffic_delay_minutes=estimated_traffic_delay_minutes,
        )

        triggered = [d for d in decisions if d.should_replan]

        result: Optional[DayPlan] = None

        if not triggered:
            # Check for crowd decisions that need user input (inform_user strategy)
            for d in decisions:
                if d.metadata.get("crowd_action") == "inform_user":
                    result = self._handle_crowd_action(d)
            # Do NOT return here — fall through to HF trigger check below

        else:
            # Separate crowd decisions that need special handling
            crowd_decisions = [
                d for d in triggered if d.metadata.get("crowd_action")
            ]
            weather_decisions = [
                d for d in triggered if d.metadata.get("weather_action")
            ]
            traffic_decisions = [
                d for d in triggered if d.metadata.get("traffic_action")
            ]
            other_decisions = [
                d for d in triggered
                if not d.metadata.get("crowd_action")
                and not d.metadata.get("weather_action")
                and not d.metadata.get("traffic_action")
            ]

            # Handle crowd rescheduling first
            for cd in crowd_decisions:
                result = self._handle_crowd_action(cd)

            # Handle weather disruptions
            for wd in weather_decisions:
                result = self._handle_weather_action(wd)

            # Handle traffic disruptions
            for td in traffic_decisions:
                result = self._handle_traffic_action(td)

            # Then handle other triggers (generic) if any
            if other_decisions:
                reasons = [d.reason for d in other_decisions]
                deprioritize_outdoor = any(
                    d.metadata.get("deprioritize_outdoor", False) for d in other_decisions
                )
                result = self._do_replan(
                    reasons=reasons,
                    deprioritize_outdoor=deprioritize_outdoor,
                )

        # ── Hunger / Fatigue trigger check ──────────────────────────────────
        hf_triggers = self._hf_advisor.check_triggers(self.state)
        for trigger_type in hf_triggers:
            if trigger_type == "hunger_disruption":
                result = self._handle_hunger_disruption()
            elif trigger_type == "fatigue_disruption":
                result = self._handle_fatigue_disruption()

        return result

    # ── Direct event API ─────────────────────────────────────────────────────

    def event(
        self,
        event_type: EventType,
        payload: dict,
    ) -> Optional[DayPlan]:
        """
        Fire a single disruption event (user-reported or external).

        Returns:
            New DayPlan if the event required a replan, else None.
        """
        # ── USER_SKIP: show advisory (WHAT YOU WILL MISS + alternatives) first ─
        if event_type == EventType.USER_SKIP:
            stop_name = payload.get("stop_name", "")
            if stop_name:
                advisory = self._crowd_advisory.build(
                    crowded_stop      = stop_name,
                    crowd_level       = 1.0,
                    threshold         = self.thresholds.crowd,
                    strategy          = "inform_user",
                    remaining_pool    = self._remaining,
                    constraints       = self.constraints,
                    current_lat       = self.state.current_lat,
                    current_lon       = self.state.current_lon,
                    current_time_str  = self.state.current_time,
                    remaining_minutes = self.state.remaining_minutes_today(),
                    city              = self._city,
                    target_day        = None,
                    top_n             = 3,
                )
                self._print_crowd_advisory(advisory, header="SKIP ADVISORY")

        # ── NLP hook: detect hunger/fatigue signals in free-text reports ──────
        if event_type == EventType.USER_REPORT_DISRUPTION:
            self._hf_advisor.check_nlp_trigger(
                payload.get("message", ""), self.state
            )

        decision = self._event_handler.handle(event_type, payload, self.state)

        # Apply preference change to constraints before replanning
        if event_type == EventType.USER_PREFERENCE_CHANGE and decision.metadata.get("sc_update"):
            for field, value in decision.metadata["sc_update"].items():
                self.constraints = self._partial_replanner.apply_preference_update(
                    self.constraints, field, value
                )
            # Rebuild monitor with new soft constraints
            self._condition_monitor = ConditionMonitor(
                self.constraints.soft, self._remaining, total_days=self.total_days
            )
            self.thresholds = self._condition_monitor.thresholds

        # Handle add-stop: insert the new AttractionRecord into the pool
        if event_type == EventType.USER_ADD_STOP and decision.metadata.get("new_attraction"):
            new_attr = decision.metadata["new_attraction"]
            if new_attr not in self._remaining:
                self._remaining.append(new_attr)
            self._condition_monitor.update_remaining(self._remaining)

        if not decision.should_replan:
            # Check for crowd inform_user
            if decision.metadata.get("crowd_action") == "inform_user":
                return self._handle_crowd_action(decision)
            # Check for user_edit advisory (dislike_next — no replan, just print)
            if decision.metadata.get("user_edit_action"):
                return self._handle_user_edit_action(decision)
            print(f"  [Session] Event '{event_type.value}': no replan needed. "
                  f"({decision.reason})")
            return None

        # Route crowd events through the 3-strategy handler
        if decision.metadata.get("crowd_action"):
            return self._handle_crowd_action(decision)

        # Route user-edit events through the edit handler
        if decision.metadata.get("user_edit_action"):
            return self._handle_user_edit_action(decision)

        return self._do_replan(reasons=[decision.reason])
    # ── Crowd rescheduling dispatcher ──────────────────────────────────────────

    def _handle_crowd_action(self, decision: "ReplanDecision") -> Optional[DayPlan]:
        """
        Execute the appropriate crowd strategy.

        ALWAYS builds a CrowdAdvisoryResult first so the traveller sees:
          - Ranked alternatives filtered by soft + commonsense constraints.
          - What the system will do and why.
          - WHAT YOU WILL MISS only when permanent loss is possible (inform_user).
          - Final-veto option (inform_user / Strategy 3 only).
        """
        crowd_action = decision.metadata.get("crowd_action", "")
        stop         = decision.metadata.get("deferred_stop", "")
        crowd_level  = decision.metadata.get("crowd_level",  0.0)
        threshold    = decision.metadata.get("threshold",    0.5)
        target_day   = decision.metadata.get("target_day",   None)

        # ── Build advisory (historical importance + ranked alternatives) ─────
        advisory = self._crowd_advisory.build(
            crowded_stop      = stop,
            crowd_level       = crowd_level,
            threshold         = threshold,
            strategy          = crowd_action,
            remaining_pool    = self._remaining,
            constraints       = self.constraints,
            current_lat       = self.state.current_lat,
            current_lon       = self.state.current_lon,
            current_time_str  = self.state.current_time,
            remaining_minutes = self.state.remaining_minutes_today(),
            city              = self._city,
            target_day        = target_day,
            top_n             = 3,
        )

        # ── Print advisory panel ─────────────────────────────────────────────
        self._print_crowd_advisory(advisory)

        # ── Execute strategy ─────────────────────────────────────────────────
        if crowd_action == "reschedule_same_day":
            result = self._do_replan(reasons=[decision.reason])
            self.state.undefer_stop(stop)
            return result

        if crowd_action == "reschedule_future_day":
            self.future_deferred[stop] = target_day
            return self._do_replan(reasons=[decision.reason])

        if crowd_action == "inform_user":
            self.crowd_pending_decision = {
                "stop_name":        stop,
                "crowd_level":      crowd_level,
                "threshold":        threshold,
                "place_importance": advisory.insight.importance,
            }
            return None

        return self._do_replan(reasons=[decision.reason])

    def _print_crowd_advisory(
        self,
        advisory: "CrowdAdvisoryResult",
        header: str = "CROWD ALERT",
    ) -> None:
        """Print the formatted crowd advisory panel to the terminal."""
        W   = 64
        sep = "-" * W

        print(f"\n  [Crowd] {sep}")
        print(f"  {header}: '{advisory.crowded_stop}'")
        print(f"  Live crowd: {advisory.crowd_level:.0%}  |  "
              f"Your tolerance: {advisory.threshold:.0%}")
        print(f"  {sep}")

        # WHAT YOU WILL MISS — only when permanent loss is possible
        if advisory.strategy == "inform_user":
            print(f"  WHAT YOU WILL MISS IF YOU SKIP:")
            for ln in advisory.insight.format_for_display(W - 4):
                print(f"    {ln.strip()}")
            print()

        # BEST ALTERNATIVES — always shown
        if advisory.alternatives:
            print(f"  BEST ALTERNATIVES RIGHT NOW (ranked by FTRM score):")
            for i, alt in enumerate(advisory.alternatives, 1):
                a = alt.attraction
                print(f"    {i}. {a.name}")
                print(f"       Category : {a.category}  |  Rating: {a.rating:.1f}"
                      f"  |  Intensity: {a.intensity_level}")
                print(f"       Why good : {alt.why_suitable}")
                if a.historical_importance:
                    teaser = a.historical_importance.split(".")[0] + "."
                    words: list[str] = teaser.split()
                    cur: list[str] = []
                    tlines: list[str] = []
                    for word in words:
                        if sum(len(w) + 1 for w in cur) + len(word) > W - 16:
                            tlines.append(" ".join(cur))
                            cur = [word]
                        else:
                            cur.append(word)
                    if cur:
                        tlines.append(" ".join(cur))
                    print(f"       Context  : {tlines[0]}")
                    for tl in tlines[1:]:
                        print(f"                  {tl}")
                print()
        else:
            print(f"  (No alternatives available under your constraints.)")
            print()

        # SYSTEM DECISION
        print(f"  SYSTEM DECISION:")
        words2 = advisory.strategy_msg.split()
        cur2: list[str] = []
        for word in words2:
            if sum(len(w) + 1 for w in cur2) + len(word) > W - 4:
                print(f"    " + " ".join(cur2))
                cur2 = [word]
            else:
                cur2.append(word)
        if cur2:
            print(f"    " + " ".join(cur2))
        print()

        # YOUR CHOICE — only for inform_user / Strategy 3
        if advisory.pending_decision:
            print(f"  YOUR CHOICE:")
            print(f"    a) Visit '{advisory.crowded_stop}' despite the crowds")
            print(f"       (continue as planned — no action needed)")
            print(f"    b) Skip permanently:")
            print(f"       session.event(EventType.USER_SKIP,")
            print(f"                     {{\"stop_name\": \"{advisory.crowded_stop}\"}})")
            print()

        print(f"  {sep}\n")

    # ── User-edit dispatcher ──────────────────────────────────────────────────

    def _handle_user_edit_action(
        self, decision: "ReplanDecision"
    ) -> Optional[DayPlan]:
        """
        Route the three user-edit events to the correct UserEditHandler method.

        DISLIKE_NEXT  → compute + print alternatives; no replan; no state change.
        REPLACE_POI   → validate + swap stop; recompute times; replan on accept.
        SKIP_CURRENT  → already marked skipped by EventHandler; replan from here.
        """
        meta   = decision.metadata
        action = meta.get("user_edit_action", "")

        rem    = meta.get("remaining_minutes", self.state.remaining_minutes_today())
        cur_lat  = meta.get("current_lat",  self.state.current_lat)
        cur_lon  = meta.get("current_lon",  self.state.current_lon)
        cur_time = meta.get("current_time", self.state.current_time)

        if not self.state.current_day_plan:
            print("  [UserEdit] No active day plan — nothing to edit.")
            return None

        # ── A: DISLIKE_NEXT ────────────────────────────────────────────────
        if action == "dislike_next":
            result = self._user_edit.dislike_next_poi(
                current_plan      = self.state.current_day_plan,
                remaining_pool    = self._remaining,
                visited           = self.state.visited_stops,
                skipped           = self.state.skipped_stops,
                deferred          = self.state.deferred_stops,
                constraints       = self.constraints,
                current_lat       = cur_lat,
                current_lon       = cur_lon,
                current_time_str  = cur_time,
                remaining_minutes = rem,
            )
            self._print_dislike_advisory(result)
            return None   # no replan; waits for USER_REPLACE_POI or user ignores

        # ── B: REPLACE_POI ─────────────────────────────────────────────────
        if action == "replace_poi":
            record = meta.get("replacement_record")
            if record is None:
                print("  [UserEdit] REPLACE_POI: no replacement_record in payload.")
                return None

            budget_rem = meta.get(
                "budget_remaining",
                self.state.remaining_budget(self.budget),
            )
            result = self._user_edit.replace_poi(
                current_plan        = self.state.current_day_plan,
                replacement_record  = record,
                visited             = self.state.visited_stops,
                skipped             = self.state.skipped_stops,
                constraints         = self.constraints,
                current_lat         = cur_lat,
                current_lon         = cur_lon,
                current_time_str    = cur_time,
                remaining_minutes   = rem,
                budget_remaining    = budget_rem,
            )
            self._print_replace_result(result)

            if result.accepted and result.updated_plan:
                # Commit the updated plan to state
                self.state.current_day_plan = result.updated_plan
                # Deduct cost delta from budget
                if result.budget_delta != 0:
                    self.state.budget_spent["Attractions"] = max(
                        0.0,
                        self.state.budget_spent["Attractions"] + result.budget_delta,
                    )
                # Record replacement to memory
                self._disruption_memory.record_replacement(
                    original    = result.original_stop,
                    replacement = result.replacement_stop,
                    reason      = "user_replace",
                    S_orig      = 0.0,   # N/A — user-choice override
                    S_rep       = 0.0,
                )
                # Replan from the replacement stop's position
                return self._do_replan(reasons=[decision.reason])
            return None

        # ── C: SKIP_CURRENT ────────────────────────────────────────────────
        if action == "skip_current":
            stop_name = meta.get("stop_name", "")
            # Provide skip analysis for memory signal
            result = self._user_edit.skip_current_poi(
                current_plan      = self.state.current_day_plan,
                remaining_pool    = self._remaining,
                visited           = self.state.visited_stops,
                skipped           = self.state.skipped_stops,
                constraints       = self.constraints,
                current_lat       = cur_lat,
                current_lon       = cur_lon,
                current_time_str  = cur_time,
                remaining_minutes = rem,
            )
            print(f"  [UserEdit] {result.reason}")
            if result.memory_signal:
                # Write preference signal: traveller skipped a high-value stop
                self._disruption_memory.record_replacement(
                    original    = result.skipped_stop,
                    replacement = "",
                    reason      = "user_skip_current_high_spti",
                    S_orig      = result.S_pti_lost,
                    S_rep       = 0.0,
                )
                print(f"  [UserEdit] Preference signal recorded"
                      f" (S_pti={result.S_pti_lost:.2f} ≥"
                      f" {result.S_pti_lost:.2f} threshold).")
            # stop already marked_skipped by EventHandler._handle_skip_current;
            # trigger replan from same position (no travel cost)
            return self._do_replan(reasons=[decision.reason])

        print(f"  [UserEdit] Unknown user_edit_action: '{action}'")
        return None

    def _print_dislike_advisory(
        self,
        result: "DislikeResult",
        header: str = "DISLIKE ADVISORY",
    ) -> None:
        """Print the dislike-next-stop advisory panel."""
        W   = 64
        sep = "-" * W
        print(f"\n  [Edit] {sep}")
        print(f"  {header}")
        print(f"  You disliked: '{result.disliked_stop}'  "
              f"(S_pti={result.current_S_pti:.2f})")
        print(f"  {sep}")

        if result.no_alternatives:
            print("  No alternatives available under your constraints.")
            print(f"  {sep}\n")
            return

        print(f"  BEST ALTERNATIVES (ranked by FTRM score):")
        for opt in result.alternatives:
            a = opt.attraction
            print(f"    {opt.rank}. {a.name}")
            print(f"       Category  : {a.category}  |  Rating: {a.rating:.1f}")
            print(f"       S_pti={opt.S_pti:.2f}  Dij={opt.Dij_from_current:.1f} min"
                  f"  η={opt.eta_ij:.3f}")
            print(f"       Suitability: {opt.why_suitable}")
            print()

        print(f"  TO REPLACE, fire:")
        if result.alternatives:
            print(f"    session.event(EventType.USER_REPLACE_POI, {{")
            print(f"        \"replacement_record\": <chosen AttractionRecord>,")
            print(f"    }})")
        print(f"\n  {sep}\n")

    def _print_replace_result(
        self,
        result: "ReplaceResult",
        header: str = "POI REPLACEMENT",
    ) -> None:
        """Print the replace-POI result panel."""
        W   = 64
        sep = "-" * W
        print(f"\n  [Edit] {sep}")
        print(f"  {header}: '{result.original_stop}' → '{result.replacement_stop}'")
        print(f"  {sep}")

        if result.accepted:
            print(f"  ✓  ACCEPTED")
            delta_sign = "+" if result.budget_delta >= 0 else ""
            print(f"     Budget delta  : {delta_sign}{result.budget_delta:.2f}")
            if result.updated_plan:
                stops = [rp.name for rp in result.updated_plan.route_points]
                print(f"     Updated plan  : {stops}")
        else:
            print(f"  ✗  REJECTED")
            print(f"     Reason: {result.rejection_reason}")

        print(f"\n  {sep}\n")

    # ── Weather disruption dispatcher ─────────────────────────────────────────

    def _handle_weather_action(self, decision: "ReplanDecision") -> Optional[DayPlan]:
        """
        Execute weather disruption response.

        1. Classify POIs: BLOCKED (HC=0), DEFERRED (risky), SAFE (indoor).
        2. Defer all blocked stops in TripState.
        3. Print advisory panel.
        4. Record to DisruptionMemory.
        5. Trigger replan with deprioritize_outdoor=True.
        """
        meta      = decision.metadata
        condition = meta.get("condition", "bad_weather")
        severity  = meta.get("severity", 0.0)
        threshold = meta.get("threshold", 0.5)
        cur_lat   = meta.get("current_lat",       self.state.current_lat)
        cur_lon   = meta.get("current_lon",       self.state.current_lon)
        rem_min   = meta.get("remaining_minutes", self.state.remaining_minutes_today())

        advisory = self._weather_advisor.classify(
            condition         = condition,
            threshold         = threshold,
            remaining_pool    = self._remaining,
            constraints       = self.constraints,
            current_lat       = cur_lat,
            current_lon       = cur_lon,
            remaining_minutes = rem_min,
            top_n             = 3,
        )

        # Defer all blocked stops so PartialReplanner excludes them
        for imp in advisory.blocked_stops:
            self.state.defer_stop(imp.attraction.name)

        self._print_weather_advisory(advisory)

        # Record to memory
        self._disruption_memory.record_weather(
            condition  = condition,
            severity   = severity,
            threshold  = threshold,
            blocked    = len(advisory.blocked_stops),
            deferred   = len(advisory.deferred_stops),
            accepted   = True,
            alternatives = [a.attraction.name for a in advisory.alternatives],
        )
        for imp in advisory.blocked_stops:
            if advisory.alternatives:
                self._disruption_memory.record_replacement(
                    original    = imp.attraction.name,
                    replacement = advisory.alternatives[0].attraction.name,
                    reason      = "weather",
                    S_orig      = advisory.alternatives[0].S_pti * 0.0,
                    S_rep       = advisory.alternatives[0].S_pti,
                )

        return self._do_replan(
            reasons=[decision.reason],
            deprioritize_outdoor=meta.get("deprioritize_outdoor", True),
        )

    def _print_weather_advisory(
        self,
        advisory: "WeatherAdvisoryResult",
        header: str = "WEATHER DISRUPTION",
    ) -> None:
        """Print the weather advisory panel."""
        W   = 64
        sep = "-" * W
        print(f"\n  [Weather] {sep}")
        print(f"  {header}: '{advisory.condition}'")
        print(f"  Severity: {advisory.severity:.0%}  |  "
              f"Threshold: {advisory.threshold:.0%}")
        print(f"  {sep}")

        if advisory.blocked_stops:
            print(f"  BLOCKED OUTDOOR STOPS (HC_pti = 0 — unsafe to visit):")
            for imp in advisory.blocked_stops:
                print(f"    \u2713 {imp.attraction.name}  [{imp.attraction.category}]")
                print(f"      {imp.reason}")
            print()

        if advisory.deferred_stops:
            print(f"  DEFERRED RISKY STOPS (duration reduced ×0.75):")
            for imp in advisory.deferred_stops:
                adj = advisory.duration_adjustments.get(imp.attraction.name, "?")
                print(f"    ~ {imp.attraction.name}  [{imp.attraction.category}]"
                      f"  → {adj} min")
            print()

        if advisory.alternatives:
            print(f"  INDOOR ALTERNATIVES (ranked by \u03b7_ij = S_pti / Dij):")
            for i, alt in enumerate(advisory.alternatives, 1):
                a = alt.attraction
                print(f"    {i}. {a.name}")
                print(f"       S_pti={alt.S_pti:.2f}  Dij={alt.Dij_new:.1f} min"
                      f"  \u03b7={alt.eta_ij:.3f}")
                print(f"       {alt.why_suitable}")
            print()

        print(f"  SYSTEM DECISION:")
        words = advisory.strategy_msg.split()
        cur: list[str] = []
        for word in words:
            if sum(len(w) + 1 for w in cur) + len(word) > W - 4:
                print(f"    " + " ".join(cur))
                cur = [word]
            else:
                cur.append(word)
        if cur:
            print(f"    " + " ".join(cur))
        print(f"\n  {sep}\n")

    # ── Traffic disruption dispatcher ─────────────────────────────────────────

    def _handle_traffic_action(self, decision: "ReplanDecision") -> Optional[DayPlan]:
        """
        Execute traffic disruption response.

        1. Run TrafficAdvisor.assess() to classify feasible/infeasible stops.
        2. Defer high-priority infeasible stops (S_pti ≥ HIGH_PRIORITY_THRESHOLD).
        3. Print advisory panel.
        4. Record to DisruptionMemory.
        5. Trigger replan with current position.
        """
        meta          = decision.metadata
        traffic_level = meta.get("traffic_level",    0.0)
        threshold     = meta.get("threshold",         0.5)
        delay_minutes = meta.get("delay_minutes",       0)
        cur_lat       = meta.get("current_lat",  self.state.current_lat)
        cur_lon       = meta.get("current_lon",  self.state.current_lon)
        rem_min       = meta.get("remaining_minutes", self.state.remaining_minutes_today())

        advisory = self._traffic_advisor.assess(
            traffic_level     = traffic_level,
            threshold         = threshold,
            delay_minutes     = delay_minutes,
            remaining_pool    = self._remaining,
            constraints       = self.constraints,
            current_lat       = cur_lat,
            current_lon       = cur_lon,
            remaining_minutes = rem_min,
            top_n             = 3,
        )

        # Defer high-priority infeasible stops
        for fi in advisory.deferred_stops:
            self.state.defer_stop(fi.attraction.name)

        self._print_traffic_advisory(advisory)

        # Record to memory
        self._disruption_memory.record_traffic(
            traffic_level = traffic_level,
            threshold     = threshold,
            delay_minutes = delay_minutes,
            delay_factor  = advisory.delay_factor,
            deferred      = [f.attraction.name for f in advisory.deferred_stops],
            replaced      = [f.attraction.name for f in advisory.replaced_stops],
            accepted      = True,
        )
        for fi in advisory.replaced_stops:
            if advisory.alternatives:
                self._disruption_memory.record_replacement(
                    original    = fi.attraction.name,
                    replacement = advisory.alternatives[0].attraction.name,
                    reason      = "traffic",
                    S_orig      = fi.S_pti,
                    S_rep       = advisory.alternatives[0].S_pti,
                )

        return self._do_replan(reasons=[decision.reason])

    def _print_traffic_advisory(
        self,
        advisory: "TrafficAdvisoryResult",
        header: str = "TRAFFIC DISRUPTION",
    ) -> None:
        """Print the traffic advisory panel."""
        W   = 64
        sep = "-" * W
        print(f"\n  [Traffic] {sep}")
        print(f"  {header}")
        print(f"  Traffic: {advisory.traffic_level:.0%}  |  "
              f"Threshold: {advisory.threshold:.0%}  |  "
              f"Delay factor: \u00d7{advisory.delay_factor:.1f}")
        print(f"  {sep}")

        if advisory.deferred_stops:
            print(f"  DEFERRED (high-priority, S_pti \u2265 threshold — kept for later):")
            for fi in advisory.deferred_stops:
                print(f"    ~ {fi.attraction.name}  "
                      f"Dij_new={fi.Dij_new:.1f} min  S={fi.S_pti:.2f}")
            print()

        if advisory.replaced_stops:
            print(f"  REPLACED (low-priority, S_pti < threshold):")
            for fi in advisory.replaced_stops:
                print(f"    \u2715 {fi.attraction.name}  "
                      f"Dij_new={fi.Dij_new:.1f} min  S={fi.S_pti:.2f}")
            print()

        if advisory.alternatives:
            print(f"  NEARBY ALTERNATIVES (ranked by \u03b7_ij = S_pti / Dij_new):")
            for i, alt in enumerate(advisory.alternatives, 1):
                a = alt.attraction
                clustered = "\u2022 CLUSTERED" if alt.is_clustered else ""
                print(f"    {i}. {a.name}  {clustered}")
                print(f"       S_pti={alt.S_pti:.2f}  Dij_new={alt.Dij_new:.1f} min"
                      f"  \u03b7={alt.eta_ij_new:.3f}")
                print(f"       {alt.why_suitable}")
            print()

        if advisory.start_time_delay_minutes > 0:
            print(f"  START-TIME ADJUSTMENT: +{advisory.start_time_delay_minutes} min")
            print()

        print(f"  SYSTEM DECISION:")
        words = advisory.strategy_msg.split()
        cur: list[str] = []
        for word in words:
            if sum(len(w) + 1 for w in cur) + len(word) > W - 4:
                print(f"    " + " ".join(cur))
                cur = [word]
            else:
                cur.append(word)
        if cur:
            print(f"    " + " ".join(cur))
        print(f"\n  {sep}\n")

    # ── Hunger / Fatigue disruption handlers ─────────────────────────────────

    def _handle_hunger_disruption(self) -> DayPlan:
        """
        Triggered when hunger_level ≥ HUNGER_TRIGGER_THRESHOLD.

        Action: advance clock by MEAL_DURATION_MIN, reset hunger to 0,
        build advisory panel, record to DisruptionMemory, run LocalRepair
        (= _do_replan) to shift remaining stop times.
        """
        # Compute advisory (best restaurant options)
        advisory = self._hf_advisor.build_hunger_advisory(
            state             = self.state,
            remaining         = self._remaining,
            constraints       = self.constraints,
            cur_lat           = self.state.current_lat,
            cur_lon           = self.state.current_lon,
            remaining_minutes = self.state.remaining_minutes_today(),
            budget_per_meal   = self.budget.Restaurants / max(self.total_days, 1),
        )
        # Print advisory panel
        self._hf_advisor.print_hunger_advisory(advisory)

        # Advance clock + reset hunger
        minutes_consumed = self._hf_advisor.advance_clock_for_meal(self.state)

        # Record in DisruptionMemory
        best = advisory.meal_options[0] if advisory.meal_options else None
        self._disruption_memory.record_hunger(
            trigger_time    = self.state.current_time,
            hunger_level    = self.state.hunger_level,     # already reset to 0
            action_taken    = "meal_inserted",
            restaurant_name = best.name if best else None,
            S_pti_inserted  = best.S_pti if best else None,
            user_response   = "accepted",
        )

        # LocalRepair: replan downstream stops with new clock start
        return self._do_replan(
            reasons=[f"Hunger disruption: {minutes_consumed}-min meal break inserted."]
        )

    def _handle_fatigue_disruption(self) -> DayPlan:
        """
        Triggered when fatigue_level ≥ FATIGUE_TRIGGER_THRESHOLD.

        Action: advance clock by REST_DURATION_MIN, reduce fatigue,
        build advisory panel, record to DisruptionMemory, run LocalRepair.
        """
        # Determine next planned stop name for the advisory
        next_stop = ""
        if self.state.current_day_plan and self.state.current_day_plan.route_points:
            remaining_rp = [
                rp for rp in self.state.current_day_plan.route_points
                if rp.name not in self.state.visited_stops
                and rp.name not in self.state.skipped_stops
            ]
            if remaining_rp:
                next_stop = remaining_rp[0].name

        advisory = self._hf_advisor.build_fatigue_advisory(
            state     = self.state,
            next_stop = next_stop,
            remaining = self._remaining,
        )
        self._hf_advisor.print_fatigue_advisory(advisory)

        # Advance clock + reduce fatigue
        minutes_consumed = self._hf_advisor.advance_clock_for_rest(self.state)

        # Record in DisruptionMemory
        self._disruption_memory.record_fatigue(
            trigger_time   = self.state.current_time,
            fatigue_level  = self.state.fatigue_level,    # already reduced
            action_taken   = "rest_inserted",
            rest_duration  = minutes_consumed,
            stops_deferred = advisory.deferred_stops,
            user_response  = "accepted",
        )

        # LocalRepair
        return self._do_replan(
            reasons=[f"Fatigue disruption: {minutes_consumed}-min rest break inserted."]
        )

    # ── Internal replan dispatcher ────────────────────────────────────────────

    def _do_replan(
        self,
        reasons: list[str],
        deprioritize_outdoor: bool = False,
    ) -> DayPlan:
        """
        Invoke PartialReplanner and update session state with new plan.
        """
        display_reason = " | ".join(reasons)
        print(f"\n  [Replan] Triggered: {display_reason}")
        print(f"  [Replan] Position {self.state.current_lat:.4f},{self.state.current_lon:.4f}"
              f" | Time {self.state.current_time} "
              f"| Remaining {self.state.remaining_minutes_today()} min")

        new_plan = self._partial_replanner.replan(
            state=self.state,
            remaining_attractions=self._remaining,
            constraints=self.constraints,
            deprioritize_outdoor=deprioritize_outdoor,
        )

        # Update remaining pool (remove newly planned stops so they aren't double-counted)
        self.state.current_day_plan = new_plan
        self.state.replan_pending = False

        planned_names = {rp.name for rp in new_plan.route_points}
        self.replan_history.append({
            "time": self.state.current_time,
            "reasons": reasons,
            "new_stops": list(planned_names),
        })

        stop_names = [rp.name for rp in new_plan.route_points]
        print(f"  [Replan] New plan ({len(stop_names)} stops): {stop_names}\n")
        return new_plan

    # ── Helpers ───────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return a concise session summary for display or logging."""
        return {
            "current_time":         self.state.current_time,
            "current_day":          self.state.current_day,
            "visited":              sorted(self.state.visited_stops),
            "skipped":              sorted(self.state.skipped_stops),
            "deferred_same_day":    sorted(self.state.deferred_stops),
            "deferred_future_days": dict(self.future_deferred),
            "remaining_stops":      [a.name for a in self._remaining
                                     if a.name not in self.state.visited_stops
                                     and a.name not in self.state.skipped_stops],
            "remaining_minutes":    self.state.remaining_minutes_today(),
            "thresholds":           self.thresholds.describe(),
            "replans_triggered":    len(self.replan_history),
            "disruption_log":       self.state.disruption_log,
            "crowd_pending":        self.crowd_pending_decision,
            "disruption_memory":    self._disruption_memory.summarize(),
        }
