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

    # Check environmental readings → build approval-gate payload; NO auto-replan
    session.check_conditions(crowd_level=0.7, weather_condition="rainy")
    # → displays PendingDecision panel; returns None; sets session.pending_decision

    # User reviews the payload, then resolves:
    new_plan = session.resolve_pending("APPROVE")   # apply + replan
    # session.resolve_pending("REJECT")             # keep unchanged
    # session.resolve_pending("MODIFY", action_index=0)  # apply one action

    # Or fire a user event directly
    new_plan = session.event(EventType.USER_SKIP, {"stop_name": "Heritage Fort"})

    # Inspect live state
    print(session.state.current_time, session.thresholds.describe())
"""

from __future__ import annotations
from dataclasses import dataclass, field as _dc_field
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


@dataclass
class ProposedAction:
    """One candidate action inside a PendingDecision payload."""
    # Environmental gate: "DEFER" | "REPLACE" | "SHIFT_TIME" | "KEEP_AS_IS"
    # User action gate:   "APPLY_CHANGE" | "SUGGEST_ALTERNATIVES" | "DEFER_CHANGE" | "KEEP_AS_IS"
    action_type: str
    target_stop: str
    details: dict = _dc_field(default_factory=dict)


@dataclass
class PendingDecision:
    """
    Frozen snapshot presented to the user before any state mutation.
    Covers both environmental disruptions (CROWD/WEATHER/TRAFFIC) and
    user-triggered actions (SKIP/REPLACE/ADD/REORDER/…).
    Stored in session.pending_decision until the user calls resolve_pending().
    """
    disruption_type: str              # "CROWD"|"WEATHER"|"TRAFFIC"|"USER_ACTION"
    impacted_pois: list               # list[str]
    reason: str
    missed_value: float               # avg S_pti proxy of removed/deferred stops
    proposed_actions: list            # list[ProposedAction]
    suggested_alternatives: list      # top-3 by S_pti from remaining pool
    severity: float                   # 0.0 for user actions; raw reading for env
    _raw_decisions: list = _dc_field(default_factory=list)   # env ReplanDecisions
    # ── User-action gate fields (set only when gate covers a user event) ─────
    _user_event_type: str = ""        # EventType.value of the intercepted event
    _user_event_payload: dict = _dc_field(default_factory=dict)
    impact_summary: dict = _dc_field(default_factory=dict)
    # feasibility_change, satisfaction_change, time_change, cost_change


# Event types that MUST go through the approval gate before any state mutation
_USER_GATE_EVENTS: frozenset = frozenset({
    "user_skip",
    "user_skip_current",
    "user_dislike_next",
    "user_replace_poi",
    "user_add",
    "user_pref",
    "user_reorder",
    "user_manual_reopt",
})


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

        # Pending disruption awaiting user APPROVE / REJECT / MODIFY
        # Set by check_conditions(); cleared by resolve_pending()
        self.pending_decision: Optional[PendingDecision] = None

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

        # Update remaining pool
        self._remaining = [a for a in self._remaining if a.name not in self.state.visited_stops]
        self._condition_monitor.update_remaining(self._remaining)
        print(f"  [Session] Visited '{stop_name}' at {self.state.current_time}. "
              f"Remaining stops: {len(self._remaining)}")

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

        APPROVAL GATE — if a threshold is exceeded the method does NOT
        automatically replan.  Instead it:
          1. Freezes the current itinerary (no state mutation).
          2. Builds a structured PendingDecision payload.
          3. Prints the decision panel for the user.
          4. Stores the decision in self.pending_decision.
          5. Returns None.

        The caller must then call:
            session.resolve_pending("APPROVE")   — apply + replan
            session.resolve_pending("REJECT")    — keep unchanged
            session.resolve_pending("MODIFY", action_index=<int>)
        """
        # Guard: only one pending decision at a time
        if self.pending_decision is not None:
            print("  [Gate] A disruption is already awaiting your decision.")
            print("  [Gate] Call resolve_pending(\"APPROVE\"|\"REJECT\"|"
                  "\"MODIFY\") first.")
            return None

        decisions = self._condition_monitor.check(
            state=self.state,
            crowd_level=crowd_level,
            traffic_level=traffic_level,
            weather_condition=weather_condition,
            next_stop_name=next_stop_name,
            next_stop_is_outdoor=next_stop_is_outdoor,
            estimated_traffic_delay_minutes=estimated_traffic_delay_minutes,
        )

        # Collect candidates: triggered disruptions + crowd inform_user
        candidates: list = [d for d in decisions if d.should_replan]
        if not candidates:
            for d in decisions:
                if d.metadata.get("crowd_action") == "inform_user":
                    candidates.append(d)
        if not candidates:
            return None

        # ── Classify by type ────────────────────────────────────────────────
        crowd_ds   = [d for d in candidates if d.metadata.get("crowd_action")]
        weather_ds = [d for d in candidates if d.metadata.get("weather_action")]
        traffic_ds = [d for d in candidates if d.metadata.get("traffic_action")]

        impacted_pois: list[str]     = []
        proposed_actions: list       = []
        reason_parts: list[str]      = []
        severity: float              = 0.0
        disruption_type: str         = "UNKNOWN"

        if crowd_ds:
            disruption_type = "CROWD"
            for cd in crowd_ds:
                m   = cd.metadata
                stp = m.get("stop_name", next_stop_name or "next stop")
                act = m.get("crowd_action", "inform_user")
                clv = m.get("crowd_level", crowd_level or 0.0)
                thr = m.get("threshold",   self.thresholds.crowd)
                severity = max(severity, clv)
                if stp not in impacted_pois:
                    impacted_pois.append(stp)
                reason_parts.append(
                    f"crowd {clv:.0%} > threshold {thr:.0%} at '{stp}'"
                )
                if act == "reschedule_same_day":
                    proposed_actions.append(
                        ProposedAction("DEFER", stp, {"timing": "later today"})
                    )
                elif act == "reschedule_future_day":
                    proposed_actions.append(
                        ProposedAction("DEFER", stp,
                                       {"target_day": self.state.current_day + 1})
                    )
                else:  # inform_user
                    proposed_actions.append(
                        ProposedAction("KEEP_AS_IS", stp, {})
                    )

        elif weather_ds:
            disruption_type = "WEATHER"
            for wd in weather_ds:
                m         = wd.metadata
                condition = m.get("condition", weather_condition or "bad_weather")
                sev       = m.get("severity",  0.0)
                thr       = m.get("threshold", self.thresholds.weather)
                severity  = max(severity, sev)
                reason_parts.append(
                    f"{condition} (severity {sev:.0%} > threshold {thr:.0%})"
                )
                # Impacted: the next outdoor stop (if known) plus any
                # outdoor stops visible in the remaining pool
                if next_stop_is_outdoor and next_stop_name:
                    if next_stop_name not in impacted_pois:
                        impacted_pois.append(next_stop_name)
                        proposed_actions.append(
                            ProposedAction("DEFER", next_stop_name, {})
                        )
                for rec in self._remaining:
                    if (getattr(rec, "is_outdoor", False)
                            and rec.name not in impacted_pois):
                        impacted_pois.append(rec.name)
                        proposed_actions.append(
                            ProposedAction("DEFER", rec.name, {})
                        )

        elif traffic_ds:
            disruption_type = "TRAFFIC"
            for td in traffic_ds:
                m     = td.metadata
                tlv   = m.get("traffic_level", traffic_level or 0.0)
                thr   = m.get("threshold",     self.thresholds.traffic)
                delay = m.get("delay_minutes",
                               estimated_traffic_delay_minutes)
                severity = max(severity, tlv)
                stp  = next_stop_name or "current stop"
                reason_parts.append(
                    f"traffic {tlv:.0%} > threshold {thr:.0%},"
                    f" delay +{delay} min"
                )
                if stp not in impacted_pois:
                    impacted_pois.append(stp)
                # Heuristic: if stop exists in remaining pool use its
                # category-based score proxy; default to DEFER
                stop_rec = next(
                    (a for a in self._remaining if a.name == stp), None
                )
                if stop_rec is not None:
                    # Use rating as a simple Spti proxy (0-1 normalised)
                    s_proxy = min(1.0, max(0.0, stop_rec.rating / 5.0))
                    if s_proxy >= 0.65:
                        proposed_actions.append(
                            ProposedAction("DEFER", stp,
                                           {"reason": "high value — kept for later"})
                        )
                    else:
                        proposed_actions.append(
                            ProposedAction("REPLACE", stp,
                                           {"reason": "low value — swap for nearby alt"})
                        )
                else:
                    proposed_actions.append(ProposedAction("DEFER", stp, {}))

        # ── Compute missed_value (avg S_pti proxy of impacted stops) ─────────
        scores_for_impacted = []
        for name in impacted_pois:
            rec = next((a for a in self._remaining if a.name == name), None)
            if rec is not None:
                scores_for_impacted.append(min(1.0, max(0.0, rec.rating / 5.0)))
        missed_value = (
            sum(scores_for_impacted) / len(scores_for_impacted)
            if scores_for_impacted else 0.0
        )

        # ── Suggested alternatives (top-3 remaining not already impacted) ────
        alts_pool = [
            a for a in self._remaining
            if a.name not in impacted_pois
            and a.name not in self.state.visited_stops
            and a.name not in self.state.skipped_stops
        ]
        alts_pool.sort(key=lambda a: a.rating, reverse=True)
        suggested_alternatives = [a.name for a in alts_pool[:3]]

        # ── Build and store PendingDecision ──────────────────────────────────
        self.pending_decision = PendingDecision(
            disruption_type     = disruption_type,
            impacted_pois       = impacted_pois,
            reason              = " | ".join(reason_parts),
            missed_value        = missed_value,
            proposed_actions    = proposed_actions,
            suggested_alternatives = suggested_alternatives,
            severity            = severity,
            _raw_decisions      = candidates,
        )

        self._print_pending_decision(self.pending_decision)
        return None   # ← NO automatic replan; user must call resolve_pending()

    # ── Approval gate — user must call this after check_conditions() ─────────

    def resolve_pending(
        self,
        user_decision: str,
        action_index: int | None = None,
    ) -> Optional[DayPlan]:
        """
        Apply user's response to the last detected disruption.

        Args:
            user_decision:  "APPROVE" | "REJECT" | "MODIFY"
            action_index:   (MODIFY only) index into pending_decision.proposed_actions

        Returns:
            New DayPlan if a replan was triggered, else None.
        """
        if self.pending_decision is None:
            print("  [Gate] No pending disruption. Call check_conditions() first.")
            return None

        pd = self.pending_decision
        W  = 64

        # ── REJECT — keep itinerary unchanged ───────────────────────────────
        if user_decision.upper() == "REJECT":
            print(f"\n  [Gate] {'═' * W}")
            print(f"  [Gate] Decision: REJECT — itinerary unchanged.")
            print(f"  [Gate] {'═' * W}\n")
            self._disruption_memory.record_generic(
                disruption_type = pd.disruption_type,
                severity        = pd.severity,
                action_taken    = "REJECT",
                user_response   = "REJECT",
                impacted_stops  = pd.impacted_pois,
            )
            self.pending_decision = None
            return None

        # ── APPROVE — execute the pending action ───────────────────────────────
        if user_decision.upper() == "APPROVE":
            print(f"\n  [Gate] {'═' * W}")
            print(f"  [Gate] Decision: APPROVE — applying change…")
            print(f"  [Gate] {'═' * W}\n")
            result: Optional[DayPlan] = None

            if pd._user_event_type:
                # User-triggered action: reconstruct EventType and execute
                ev_type = next(
                    (e for e in EventType if e.value == pd._user_event_type), None
                )
                if ev_type:
                    result = self._execute_user_event(ev_type, pd._user_event_payload)
            else:
                # Environmental trigger: route through normal handlers
                for d in pd._raw_decisions:
                    if d.metadata.get("crowd_action"):
                        result = self._handle_crowd_action(d)
                    elif d.metadata.get("weather_action"):
                        result = self._handle_weather_action(d)
                    elif d.metadata.get("traffic_action"):
                        result = self._handle_traffic_action(d)
                    else:
                        result = self._do_replan(reasons=[d.reason])

            self._disruption_memory.record_generic(
                disruption_type = pd.disruption_type or pd._user_event_type,
                severity        = pd.severity,
                action_taken    = "APPROVE",
                user_response   = "APPROVE",
                impacted_stops  = pd.impacted_pois,
            )
            self.pending_decision = None
            return result

        # ── MODIFY — apply one specific ProposedAction ───────────────────────
        if user_decision.upper() == "MODIFY":
            if action_index is None:
                print("  [Gate] MODIFY requires action_index=<int>.")
                return None
            if action_index < 0 or action_index >= len(pd.proposed_actions):
                print(f"  [Gate] action_index {action_index} out of range "
                      f"(0–{len(pd.proposed_actions)-1}).")
                return None

            chosen = pd.proposed_actions[action_index]
            print(f"\n  [Gate] {'═' * W}")
            print(f"  [Gate] Decision: MODIFY → "
                  f"{chosen.action_type}  '{chosen.target_stop}'")
            if chosen.details:
                print(f"  [Gate] Details: {chosen.details}")
            print(f"  [Gate] {'═' * W}\n")

            if chosen.action_type in ("APPLY_CHANGE", "SUGGEST_ALTERNATIVES"):
                # For user-triggered events this is equivalent to APPROVE
                if pd._user_event_type:
                    ev_type = next(
                        (e for e in EventType if e.value == pd._user_event_type), None
                    )
                    mod_result: Optional[DayPlan] = (
                        self._execute_user_event(ev_type, pd._user_event_payload)
                        if ev_type else None
                    )
                else:
                    mod_result = self._do_replan(reasons=[f"MODIFY:{chosen.action_type}"])

            elif chosen.action_type == "DEFER_CHANGE":
                if chosen.target_stop:
                    self.state.defer_stop(chosen.target_stop)
                mod_result = self._do_replan(reasons=["MODIFY:DEFER_CHANGE"])

            elif chosen.action_type == "DEFER":
                self.state.defer_stop(chosen.target_stop)
                mod_result = self._do_replan(reasons=["MODIFY:DEFER"])

            elif chosen.action_type == "REPLACE":
                self.state.mark_skipped(chosen.target_stop)
                # Inject first suggested alternative into the pool
                if pd.suggested_alternatives:
                    alt_name = pd.suggested_alternatives[0]
                    alt_rec  = next(
                        (a for a in self._remaining if a.name == alt_name), None
                    )
                    if alt_rec is None:
                        from modules.tool_usage.attraction_tool import AttractionTool
                        all_recs = AttractionTool().fetch(self._city)
                        alt_rec  = next(
                            (a for a in all_recs if a.name == alt_name), None
                        )
                    if alt_rec and alt_rec not in self._remaining:
                        self._remaining.append(alt_rec)
                        self._condition_monitor.update_remaining(self._remaining)
                mod_result = self._do_replan(reasons=["MODIFY:REPLACE"])

            elif chosen.action_type == "SHIFT_TIME":
                delay = chosen.details.get("delay_minutes", 30) if chosen.details else 30
                h, m = map(int, self.state.current_time.split(":"))
                total = h * 60 + m + delay
                self.state.advance_time(f"{total // 60:02d}:{total % 60:02d}")
                mod_result = self._do_replan(reasons=["MODIFY:SHIFT_TIME"])

            elif chosen.action_type == "KEEP_AS_IS":
                mod_result = None

            else:
                mod_result = self._do_replan(reasons=[f"MODIFY:{chosen.action_type}"])

            self._disruption_memory.record_generic(
                disruption_type = pd.disruption_type or pd._user_event_type,
                severity        = pd.severity,
                action_taken    = f"MODIFY:{chosen.action_type}",
                user_response   = f"MODIFY:{chosen.action_type}",
                impacted_stops  = pd.impacted_pois,
            )
            self.pending_decision = None

            if chosen.action_type == "KEEP_AS_IS":
                print(f"  [Gate] Proceeding as-is — no replan.")
                return None

            return mod_result

        print(f"  [Gate] Unknown decision '{user_decision}'. "
              "Use APPROVE | REJECT | MODIFY.")
        return None

    def _print_pending_decision(self, pd: PendingDecision) -> None:
        """Print the structured disruption payload for user review."""
        W   = 54
        sep = "═" * W

        if pd._user_event_type:
            header_line = "✋  USER ACTION — AWAITING YOUR DECISION"
        else:
            header_line = "⚠  DISRUPTION DETECTED — AWAITING YOUR DECISION"

        print(f"\n  {sep}")
        print(f"  {header_line}")
        print(f"  {sep}")
        if pd._user_event_type:
            print(f"  Action    : {pd._user_event_type}")
        print(f"  Type      : {pd.disruption_type}")
        print(f"  Reason    : {pd.reason}")
        print(f"  Impacted  : {pd.impacted_pois}")
        if not pd._user_event_type:
            print(f"  Value at risk (avg S_pti proxy): {pd.missed_value:.2f}")
        print()

        if pd.impact_summary:
            print(f"  IMPACT SUMMARY:")
            for k, v in pd.impact_summary.items():
                print(f"    {k:<26}: {v}")
            print()

        print(f"  PROPOSED ACTIONS:")
        for i, act in enumerate(pd.proposed_actions):
            detail_str = (
                "  →  " + "  ".join(f"{k}: {v}" for k, v in act.details.items())
                if act.details else ""
            )
            print(f"    [{i}] {act.action_type:<20}  {act.target_stop}{detail_str}")

        if pd.suggested_alternatives:
            print()
            print(f"  BEST ALTERNATIVES: {pd.suggested_alternatives}")

        print()
        print(f"  → session.resolve_pending(\"APPROVE\")")
        print(f"     session.resolve_pending(\"REJECT\")")
        if pd.proposed_actions:
            print(f"     session.resolve_pending(\"MODIFY\", action_index=0..{len(pd.proposed_actions)-1})")
        print(f"  {sep}\n")


    # ── User-action approval gate helpers ─────────────────────────────────────

    def _next_unvisited_stop_name(self) -> str:
        """Return name of the first non-visited/skipped/deferred stop in current plan."""
        if not self.state.current_day_plan:
            return ""
        excluded = (self.state.visited_stops
                    | self.state.skipped_stops
                    | self.state.deferred_stops)
        for rp in self.state.current_day_plan.route_points:
            if rp.name not in excluded:
                return rp.name
        return ""

    def _spti_proxy(self, name: str) -> float:
        """Quick S_pti proxy = attraction.rating / 5.0, capped [0, 1]."""
        rec = next((a for a in self._remaining if a.name == name), None)
        if rec is None:
            return 0.0
        return min(1.0, max(0.0, rec.rating / 5.0))

    def _top_alternatives(self, exclude: list[str], n: int = 3) -> list[str]:
        """Top-n remaining stops by rating, excluding listed names."""
        excluded_set = (set(exclude)
                        | self.state.visited_stops
                        | self.state.skipped_stops)
        pool = [a for a in self._remaining if a.name not in excluded_set]
        pool.sort(key=lambda a: a.rating, reverse=True)
        return [a.name for a in pool[:n]]

    def _build_user_action_pending(
        self,
        event_type: "EventType",
        payload: dict,
    ) -> "PendingDecision":
        """
        Freeze itinerary state and compute impact analysis for a user-triggered
        change request.  Returns a PendingDecision — no state is mutated.

        Impact fields per event type:
          USER_SKIP / USER_SKIP_CURRENT:
            HC_pti proxy = 1 (skip is feasible)
            ΔSpti        = −S_pti(target)
            missed_value = S_pti(target)
            proposed     = [APPLY_CHANGE(skip), DEFER_CHANGE, KEEP_AS_IS]

          USER_DISLIKE_NEXT:
            impacted     = next unvisited stop
            proposed     = [APPLY_CHANGE(show_alts), KEEP_AS_IS]

          USER_REPLACE_POI:
            impacted     = [original, replacement]
            ΔSpti        = S_pti(replacement) − S_pti(original)
            proposed     = [APPLY_CHANGE(replace), KEEP_AS_IS]

          USER_ADD_STOP:
            impacted     = [new_stop]
            ΔSpti        = +S_pti(new_stop)
            proposed     = [APPLY_CHANGE(add), KEEP_AS_IS]

          USER_PREFERENCE_CHANGE / USER_REORDER / USER_MANUAL_REOPT:
            impacted     = all remaining stops (labels only)
            proposed     = [APPLY_CHANGE, KEEP_AS_IS]
        """
        et = event_type.value

        # ── USER_SKIP / USER_SKIP_CURRENT ────────────────────────────────────
        if et in ("user_skip", "user_skip_current"):
            stop = payload.get("stop_name", "") or self._next_unvisited_stop_name()
            rec  = next((a for a in self._remaining if a.name == stop), None)
            s    = self._spti_proxy(stop)
            alts = self._top_alternatives([stop])
            dur  = getattr(rec, "estimated_duration_minutes", 60) if rec else 60
            cost = getattr(rec, "estimated_cost", 0.0) if rec else 0.0
            return PendingDecision(
                disruption_type    = "USER_ACTION",
                impacted_pois      = [stop] if stop else [],
                reason             = (f"User requested skip of '{stop}' "
                                      f"(S_pti proxy={s:.2f})"),
                missed_value       = s,
                proposed_actions   = [
                    ProposedAction("APPLY_CHANGE",  stop,
                                   {"op": "skip", "HC_pti": 1,
                                    "delta_Spti": round(-s, 3)}),
                    ProposedAction("DEFER_CHANGE",  stop,
                                   {"timing": "later today"}),
                    ProposedAction("KEEP_AS_IS",    stop, {}),
                ],
                suggested_alternatives = alts,
                severity           = 0.0,
                _user_event_type   = et,
                _user_event_payload = payload,
                impact_summary     = {
                    "feasibility_change":  1,
                    "satisfaction_change": round(-s, 3),
                    "time_change":         f"-{dur} min (freed)",
                    "cost_change":         f"-{cost:.0f}",
                },
            )

        # ── USER_DISLIKE_NEXT ─────────────────────────────────────────────────
        if et == "user_dislike_next":
            stop = self._next_unvisited_stop_name()
            s    = self._spti_proxy(stop)
            alts = self._top_alternatives([stop])
            return PendingDecision(
                disruption_type    = "USER_ACTION",
                impacted_pois      = [stop] if stop else [],
                reason             = (f"User dislikes next stop '{stop}' "
                                      f"(S_pti proxy={s:.2f}) — show alternatives"),
                missed_value       = s,
                proposed_actions   = [
                    ProposedAction("SUGGEST_ALTERNATIVES", stop,
                                   {"op": "dislike_show_alts",
                                    "delta_Spti": round(-s, 3)}),
                    ProposedAction("KEEP_AS_IS", stop, {}),
                ],
                suggested_alternatives = alts,
                severity           = 0.0,
                _user_event_type   = et,
                _user_event_payload = payload,
                impact_summary     = {
                    "feasibility_change":  1,
                    "satisfaction_change": round(-s, 3),
                    "time_change":         "0 min (no skip yet)",
                    "cost_change":         "0",
                },
            )

        # ── USER_REPLACE_POI ─────────────────────────────────────────────────
        if et == "user_replace_poi":
            replacement = payload.get("replacement_record")
            orig_name   = self._next_unvisited_stop_name()
            s_orig      = self._spti_proxy(orig_name)
            s_rep       = min(1.0, max(0.0,
                              getattr(replacement, "rating", 0.0) / 5.0)
                          ) if replacement else 0.0
            delta_s     = round(s_rep - s_orig, 3)
            rep_name    = getattr(replacement, "name", "?") if replacement else "?"
            orig_cost   = getattr(
                next((a for a in self._remaining if a.name == orig_name), None),
                "estimated_cost", 0.0)
            rep_cost    = getattr(replacement, "estimated_cost", 0.0) if replacement else 0.0
            orig_dur    = getattr(
                next((a for a in self._remaining if a.name == orig_name), None),
                "estimated_duration_minutes", 60)
            rep_dur     = getattr(replacement, "estimated_duration_minutes", 60) if replacement else 60
            # HC_pti proxy: replacement passes if HC_pti > 0 (rating > 0 heuristic)
            hc_proxy    = 1 if s_rep > 0 else 0
            return PendingDecision(
                disruption_type    = "USER_ACTION",
                impacted_pois      = [orig_name, rep_name],
                reason             = (f"Replace '{orig_name}' → '{rep_name}' "
                                      f"ΔSpti={delta_s:+.2f}  HC_pti={hc_proxy}"),
                missed_value       = s_orig,
                proposed_actions   = [
                    ProposedAction("APPLY_CHANGE", orig_name,
                                   {"replacement": rep_name,
                                    "HC_pti": hc_proxy,
                                    "delta_Spti": delta_s}),
                    ProposedAction("KEEP_AS_IS",   orig_name, {}),
                ],
                suggested_alternatives = self._top_alternatives([orig_name, rep_name]),
                severity           = 0.0,
                _user_event_type   = et,
                _user_event_payload = payload,
                impact_summary     = {
                    "feasibility_change":  hc_proxy,
                    "satisfaction_change": delta_s,
                    "time_change":    f"{rep_dur - orig_dur:+d} min",
                    "cost_change":    f"{rep_cost - orig_cost:+.0f}",
                },
            )

        # ── USER_ADD_STOP ─────────────────────────────────────────────────────
        if et == "user_add":
            new_attr = payload.get("attraction") or payload.get("new_attraction")
            if new_attr is None:
                return PendingDecision(
                    disruption_type="USER_ACTION", impacted_pois=[],
                    reason="Add-stop request with no attraction record.",
                    missed_value=0.0, proposed_actions=[], suggested_alternatives=[],
                    severity=0.0, _user_event_type=et, _user_event_payload=payload,
                )
            name  = getattr(new_attr, "name", "?")
            s_new = min(1.0, max(0.0, getattr(new_attr, "rating", 0.0) / 5.0))
            dur   = getattr(new_attr, "estimated_duration_minutes", 60)
            cost  = getattr(new_attr, "estimated_cost", 0.0)
            return PendingDecision(
                disruption_type    = "USER_ACTION",
                impacted_pois      = [name],
                reason             = (f"Add '{name}' to pool "
                                      f"(S_pti proxy={s_new:.2f})"
                                      f"  STi≈{dur} min  cost≈{cost:.0f}"),
                missed_value       = 0.0,
                proposed_actions   = [
                    ProposedAction("APPLY_CHANGE", name,
                                   {"op": "add_to_pool",
                                    "delta_Spti": round(s_new, 3),
                                    "STi": dur, "cost": cost}),
                    ProposedAction("KEEP_AS_IS", name, {}),
                ],
                suggested_alternatives = [],
                severity           = 0.0,
                _user_event_type   = et,
                _user_event_payload = payload,
                impact_summary     = {
                    "feasibility_change":  1,
                    "satisfaction_change": round(s_new, 3),
                    "time_change":         f"+{dur} min",
                    "cost_change":         f"+{cost:.0f}",
                },
            )

        # ── USER_PREFERENCE_CHANGE / USER_REORDER / USER_MANUAL_REOPT ─────────
        field = payload.get("field", "")
        value = payload.get("value", "")
        reason_text = {
            "user_pref":          (f"Preference change: {field} → {value}"),
            "user_reorder":       (f"Reorder request: {payload.get('preferred_order', [])}"),
            "user_manual_reopt":  (payload.get("reason", "Manual re-optimization requested")),
        }.get(et, f"User action: {et}")
        remaining_labels = [
            a.name for a in self._remaining
            if a.name not in self.state.visited_stops
            and a.name not in self.state.skipped_stops
        ][:5]
        return PendingDecision(
            disruption_type    = "USER_ACTION",
            impacted_pois      = remaining_labels,
            reason             = reason_text,
            missed_value       = 0.0,
            proposed_actions   = [
                ProposedAction("APPLY_CHANGE", "all_remaining",
                               {"field": field, "value": str(value)}),
                ProposedAction("KEEP_AS_IS",   "all_remaining", {}),
            ],
            suggested_alternatives = [],
            severity           = 0.0,
            _user_event_type   = et,
            _user_event_payload = payload,
            impact_summary     = {
                "feasibility_change":  1,
                "satisfaction_change": "recomputed after change",
                "time_change":         "recomputed",
                "cost_change":         "unchanged",
            },
        )

    def _execute_user_event(
        self,
        event_type: "EventType",
        payload: dict,
    ) -> "Optional[DayPlan]":
        """
        Execute a user event directly, bypassing the approval gate.
        Called by resolve_pending() after the user approves.
        Contains the original dispatch logic from event() minus the gate check.
        """
        decision = self._event_handler.handle(event_type, payload, self.state)

        # Apply preference change to constraints before replanning
        if (event_type == EventType.USER_PREFERENCE_CHANGE
                and decision.metadata.get("sc_update")):
            for f_name, f_val in decision.metadata["sc_update"].items():
                self.constraints = self._partial_replanner.apply_preference_update(
                    self.constraints, f_name, f_val
                )
            self._condition_monitor = ConditionMonitor(
                self.constraints.soft, self._remaining, total_days=self.total_days
            )
            self.thresholds = self._condition_monitor.thresholds

        # Handle add-stop: inject AttractionRecord into pool
        if (event_type == EventType.USER_ADD_STOP
                and decision.metadata.get("new_attraction")):
            new_attr = decision.metadata["new_attraction"]
            if new_attr not in self._remaining:
                self._remaining.append(new_attr)
            self._condition_monitor.update_remaining(self._remaining)

        if not decision.should_replan:
            if decision.metadata.get("crowd_action") == "inform_user":
                return self._handle_crowd_action(decision)
            if decision.metadata.get("user_edit_action"):
                return self._handle_user_edit_action(decision)
            print(f"  [Session] Event '{event_type.value}': no replan needed. "
                  f"({decision.reason})")
            return None

        if decision.metadata.get("crowd_action"):
            return self._handle_crowd_action(decision)
        if decision.metadata.get("user_edit_action"):
            return self._handle_user_edit_action(decision)

        return self._do_replan(reasons=[decision.reason])

    # ── Direct event API ─────────────────────────────────────────────────────

    def event(
        self,
        event_type: EventType,
        payload: dict,
    ) -> Optional[DayPlan]:
        """
        Fire a single disruption event (user-reported or external).

        User-triggered changes that modify the itinerary REQUIRE approval:
            event() → builds PendingDecision → returns None
            resolve_pending("APPROVE"|"REJECT"|"MODIFY") → applies change

        Non-gated events (VENUE_CLOSED, USER_DELAY, USER_REPORT_DISRUPTION)
        are executed immediately.

        Returns:
            New DayPlan if a non-gated event triggered a replan; else None.
        """
        # ── APPROVAL GATE: user-triggered itinerary modifications ─────────────
        if event_type.value in _USER_GATE_EVENTS:
            if self.pending_decision is not None:
                print("  [Gate] A decision is already pending — call "
                      "resolve_pending() first.")
                return None
            pd = self._build_user_action_pending(event_type, payload)
            self.pending_decision = pd
            self._print_pending_decision(pd)
            return None

        # ── NLP hook: detect hunger/fatigue signals in free-text reports ──────
        if event_type == EventType.USER_REPORT_DISRUPTION:
            self._hf_advisor.check_nlp_trigger(
                payload.get("message", ""), self.state
            )
            hf_triggers = self._hf_advisor.check_triggers(self.state)
            hf_result = None
            for trigger_type in hf_triggers:
                if trigger_type == "hunger_disruption":
                    hf_result = self._handle_hunger_disruption()
                elif trigger_type == "fatigue_disruption":
                    hf_result = self._handle_fatigue_disruption()
            if hf_triggers:
                return hf_result

        # ── Non-gated events: route directly ─────────────────────────────────
        decision = self._event_handler.handle(event_type, payload, self.state)

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
        pd = self.pending_decision
        pending_info = None
        if pd is not None:
            pending_info = {
                "disruption_type":      pd.disruption_type,
                "reason":               pd.reason,
                "impacted_pois":        pd.impacted_pois,
                "missed_value":         round(pd.missed_value, 3),
                "severity":             round(pd.severity, 3),
                "proposed_actions": [
                    {"action": a.action_type, "stop": a.target_stop,
                     "details": a.details}
                    for a in pd.proposed_actions
                ],
                "suggested_alternatives": pd.suggested_alternatives,
                "status": "AWAITING_DECISION",
            }
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
            "pending_decision":     pending_info,
            "disruption_memory":    self._disruption_memory.summarize(),
        }
