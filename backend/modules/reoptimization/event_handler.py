"""
modules/reoptimization/event_handler.py
-----------------------------------------
Event types and the EventHandler that validates incoming events,
updates TripState, and decides whether a full replan is needed.

Disruption sources:
  1. User-reported: skip stop, delay, preference change, add stop, generic report
  2. Environmental (fired by ConditionMonitor): crowd / traffic / weather threshold exceeded
  3. Venue-level: unexpected closure detected

The handler returns a ReplanDecision — a lightweight struct telling the
ReOptimizationSession whether and how urgently to invoke PartialReplanner.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from modules.reoptimization.trip_state import TripState


# ─────────────────────────────────────────────────────────────────────────────
# Event taxonomy
# ─────────────────────────────────────────────────────────────────────────────

class EventType(Enum):
    # ── User-reported ─────────────────────────────────────────────────────────
    USER_SKIP           = "user_skip"      # skip the next planned stop
    USER_DELAY          = "user_delay"     # running behind schedule (minutes)
    USER_PREFERENCE_CHANGE = "user_pref"  # update soft constraints mid-trip
    USER_ADD_STOP       = "user_add"       # insert a new stop into remaining pool
    USER_REPORT_DISRUPTION = "user_report" # generic free-text disruption report

    # ── Environmental (auto from ConditionMonitor) ────────────────────────────
    ENV_CROWD_HIGH      = "env_crowd"      # crowd level > tolerance threshold
    ENV_TRAFFIC_HIGH    = "env_traffic"    # traffic level > tolerance threshold
    ENV_WEATHER_BAD     = "env_weather"    # weather severity > tolerance threshold

    # ── Venue-level ───────────────────────────────────────────────────────────
    VENUE_CLOSED        = "venue_closed"   # a planned stop is unexpectedly closed

    # ── User-edit actions ────────────────────────────────────────────────────
    USER_DISLIKE_NEXT   = "user_dislike_next"  # dislike next stop → request alternatives
    USER_REPLACE_POI    = "user_replace_poi"   # replace a specific stop with chosen alt
    USER_SKIP_CURRENT   = "user_skip_current"  # skip the currently active stop mid-visit
    USER_REORDER         = "user_reorder"       # request a specific stop order
    USER_MANUAL_REOPT    = "user_manual_reopt"  # explicit user request to re-optimize
    # ── User-state disruptions (hunger / fatigue) ─────────────────────────
    HUNGER_DISRUPTION   = "hunger_disruption"  # hunger_level ≥ HUNGER_TRIGGER_THRESHOLD
    FATIGUE_DISRUPTION  = "fatigue_disruption" # fatigue_level ≥ FATIGUE_TRIGGER_THRESHOLD

# ─────────────────────────────────────────────────────────────────────────────
# Replan decision
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReplanDecision:
    """
    Output of EventHandler.handle().
    Tells ReOptimizationSession whether / how urgently to replan.
    """
    should_replan: bool = False
    urgency: str = "normal"          # "low" | "normal" | "high"
    reason: str = ""                 # human-readable trigger description
    updated_state: TripState | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Event handler
# ─────────────────────────────────────────────────────────────────────────────

class EventHandler:
    """
    Processes a single DisruptionEvent, mutates TripState, and returns
    a ReplanDecision indicating whether the PartialReplanner should run.

    All handler methods follow the convention:
        _handle_<event_type>(state, payload) -> ReplanDecision
    """

    def handle(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        state: TripState,
    ) -> ReplanDecision:
        """
        Dispatch to the correct sub-handler.

        Args:
            event_type: The type of disruption event.
            payload:    Event-specific data (see each handler for keys).
            state:      Live TripState — MUTATED in place.

        Returns:
            ReplanDecision with should_replan flag and reason.
        """
        # Log to state regardless of event type
        state.log_disruption(event_type.value, payload)

        dispatch = {
            EventType.USER_SKIP:              self._handle_skip,
            EventType.USER_DELAY:             self._handle_delay,
            EventType.USER_PREFERENCE_CHANGE: self._handle_preference_change,
            EventType.USER_ADD_STOP:          self._handle_add_stop,
            EventType.USER_REPORT_DISRUPTION: self._handle_user_report,
            EventType.ENV_CROWD_HIGH:         self._handle_env_crowd,
            EventType.ENV_TRAFFIC_HIGH:       self._handle_env_traffic,
            EventType.ENV_WEATHER_BAD:        self._handle_env_weather,
            EventType.VENUE_CLOSED:           self._handle_venue_closed,
            EventType.USER_DISLIKE_NEXT:      self._handle_dislike_next,
            EventType.USER_REPLACE_POI:       self._handle_replace_poi,
            EventType.USER_SKIP_CURRENT:      self._handle_skip_current,
            EventType.USER_REORDER:           self._handle_reorder,
            EventType.USER_MANUAL_REOPT:      self._handle_manual_reopt,
            EventType.HUNGER_DISRUPTION:      self._handle_hunger,
            EventType.FATIGUE_DISRUPTION:     self._handle_fatigue,
        }
        handler_fn = dispatch.get(event_type)
        if handler_fn is None:
            return ReplanDecision(should_replan=False, reason=f"Unknown event: {event_type}")
        return handler_fn(state, payload)

    # ── User-reported handlers ─────────────────────────────────────────────

    def _handle_skip(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: { "stop_name": str }
        User wants to skip the next planned stop. Mark it skipped and replan
        the remaining day without it.
        """
        stop = payload.get("stop_name", "")
        if stop:
            state.mark_skipped(stop)
        return ReplanDecision(
            should_replan=True,
            urgency="normal",
            reason=f"User skipped '{stop}' — replanning remaining stops.",
            updated_state=state,
        )

    def _handle_delay(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: { "delay_minutes": int, "current_time": str (optional) }
        User is running behind. Advance the clock; if remaining time drops
        below a threshold (config.REPLAN_DELAY_THRESHOLD_MINUTES), replan.
        """
        delay = int(payload.get("delay_minutes", 0))
        new_time = payload.get("current_time")
        if new_time:
            state.advance_time(new_time)
        elif delay > 0:
            # Advance current_time by delay_minutes
            h, m = map(int, state.current_time.split(":"))
            total = h * 60 + m + delay
            state.advance_time(f"{total // 60:02d}:{total % 60:02d}")

        remaining = state.remaining_minutes_today()
        urgency = "high" if remaining < 90 else "normal"
        should_replan = delay >= 20 or remaining < 120
        return ReplanDecision(
            should_replan=should_replan,
            urgency=urgency,
            reason=f"User delayed {delay} min. Remaining day: {remaining} min.",
            updated_state=state,
        )

    def _handle_preference_change(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: { "field": str, "value": Any }
        User changes a soft preference mid-trip (e.g. switches pace to "relaxed").
        The updated SoftConstraints are applied outside in the session before calling replan.
        Always triggers a replan since scores change globally.
        """
        field_name = payload.get("field", "unknown")
        value = payload.get("value")
        return ReplanDecision(
            should_replan=True,
            urgency="normal",
            reason=f"Preference '{field_name}' changed to '{value}' — rescoring needed.",
            updated_state=state,
            metadata={"sc_update": {field_name: value}},
        )

    def _handle_add_stop(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: { "attraction": AttractionRecord }
        User wants to add a new stop to the remaining day pool.
        The caller adds it to remaining_attractions before calling replan.
        """
        name = payload.get("attraction", {})
        name_str = getattr(name, "name", str(name))
        return ReplanDecision(
            should_replan=True,
            urgency="low",
            reason=f"User added '{name_str}' to remaining stops.",
            updated_state=state,
            metadata={"new_attraction": payload.get("attraction")},
        )

    def _handle_user_report(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: { "message": str }
        Free-text disruption report from user. Always triggers a replan
        since we cannot infer the exact stop to skip programmatically.
        (In production: pipe message through LLM to extract structured event.)
        """
        msg = payload.get("message", "")
        # Heuristic: if the message mentions crowded / closed / full / bad weather
        urgency = "high" if any(w in msg.lower() for w in
                                ("closed", "full", "crowded", "storm", "flood")) else "normal"
        return ReplanDecision(
            should_replan=True,
            urgency=urgency,
            reason=f"User reported disruption: '{msg}'",
            updated_state=state,
        )

    # ── Environmental handlers ─────────────────────────────────────────────

    def _handle_env_crowd(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: {
            "stop_name"          : str,
            "crowd_level"        : float [0-1],
            "threshold"          : float,
            "total_days"         : int   (total trip days — injected by session/monitor),
            "remaining_minutes"  : int   (minutes left today — injected by session/monitor),
            "min_visit_duration" : int   (min minutes needed for this stop),
            "place_importance"   : str   (shown to user if no rescheduling possible),
        }

        Crowd level at the next planned stop exceeded user tolerance.
        Instead of immediately skipping, the system tries three strategies in order:

        Strategy 1 — Reschedule later TODAY
            If enough day remains (remaining > min_duration + 60-min buffer),
            defer the stop: exclude it from this replan, keep it available for
            the next planning cycle when the crowd may have thinned.

        Strategy 2 — Move to a FUTURE DAY
            If today is too short but trip days remain, shift the stop to the
            next day so the traveller still gets to visit.

        Strategy 3 — Inform user (no rescheduling possible)
            On the last day (or when no capacity exists), present the stop's
            historical/cultural significance and let the user decide whether to
            visit despite the crowds or skip permanently.
        """
        stop            = payload.get("stop_name", "")
        level           = payload.get("crowd_level", 0.0)
        threshold       = payload.get("threshold", 0.5)
        total_days      = payload.get("total_days", state.current_day)
        remaining_min   = payload.get("remaining_minutes", state.remaining_minutes_today())
        min_duration    = payload.get("min_visit_duration", 60)
        place_importance = payload.get("place_importance", "")

        # Buffer: need at least min_duration more after completing current obligations
        time_for_later = remaining_min - min_duration - 60  # 60-min breathing room

        # ── Strategy 1: Reschedule to a quieter time later today ─────────────
        if stop and time_for_later >= min_duration:
            state.defer_stop(stop)   # temporarily exclude from this replan
            return ReplanDecision(
                should_replan=True,
                urgency="low",
                reason=(
                    f"'{stop}' is very crowded right now ({level:.0%} > {threshold:.0%}). "
                    f"Rescheduling to a quieter time later today \u2014 "
                    f"moving on to the next stop first."
                ),
                updated_state=state,
                metadata={
                    "crowd_action":  "reschedule_same_day",
                    "deferred_stop": stop,
                },
            )

        # ── Strategy 2: Move to a future day ─────────────────────────────────
        if stop and state.current_day < total_days:
            target_day = state.current_day + 1
            state.defer_stop(stop)   # excluded from today's plan
            return ReplanDecision(
                should_replan=True,
                urgency="normal",
                reason=(
                    f"'{stop}' is very crowded ({level:.0%}) and today's schedule "
                    f"is too full to visit later. Rescheduled to Day {target_day} "
                    f"for a better experience."
                ),
                updated_state=state,
                metadata={
                    "crowd_action":  "reschedule_future_day",
                    "deferred_stop": stop,
                    "target_day":    target_day,
                },
            )

        # ── Strategy 3: No rescheduling possible — inform user ────────────────
        # Don't auto-skip; present importance and let the traveller decide.
        importance_text = (
            place_importance
            or f"'{stop}' is a notable attraction on your itinerary."
        )
        return ReplanDecision(
            should_replan=False,   # session will prompt user; no auto-replan
            urgency="high",
            reason=(
                f"'{stop}' is very crowded ({level:.0%}) and cannot be "
                f"rescheduled (last day or no capacity)."
            ),
            updated_state=state,
            metadata={
                "crowd_action":    "inform_user",
                "deferred_stop":   stop,
                "place_importance": importance_text,
                "crowd_level":      level,
                "threshold":        threshold,
            },
        )

    def _handle_env_traffic(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: { "stop_name": str, "traffic_level": float [0-1],
                   "threshold": float, "delay_minutes": int,
                   "current_lat": float, "current_lon": float,
                   "remaining_minutes": int }
        Traffic to the next stop is too heavy.
          - Apply delay to clock immediately.
          - Fire TrafficAdvisor (via session._handle_traffic_action) on replan.
          - Deferred/replaced stop decisions are made by the advisor.
        """
        stop          = payload.get("stop_name", "")
        traffic       = payload.get("traffic_level", 0.0)
        threshold     = payload.get("threshold", 0.5)
        delay         = int(payload.get("delay_minutes", 0))
        delay_factor  = 1.0 + traffic

        if delay >= 20:
            h, m = map(int, state.current_time.split(":"))
            total = h * 60 + m + delay
            state.advance_time(f"{total // 60:02d}:{total % 60:02d}")

        should_replan = delay >= 20
        return ReplanDecision(
            should_replan = should_replan,
            urgency       = "normal" if delay < 40 else "high",
            reason        = (
                f"Traffic to '{stop}' at {traffic:.0%} "
                f"(threshold {threshold:.0%}), +{delay} min delay. "
                f"Delay factor ×{delay_factor:.1f} — rereplanning with "
                f"updated Dij_new."
            ),
            updated_state = state,
            metadata = {
                "traffic_action":   "assess_and_replan",
                "stop_name":        stop,
                "traffic_level":    traffic,
                "threshold":        threshold,
                "delay_minutes":    delay,
                "delay_factor":     delay_factor,
                "current_lat":      payload.get("current_lat",  state.current_lat),
                "current_lon":      payload.get("current_lon",  state.current_lon),
                "remaining_minutes": payload.get(
                    "remaining_minutes", state.remaining_minutes_today()
                ),
            },
        )

    def _handle_env_weather(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: { "severity": float [0-1], "threshold": float,
                   "condition": str, "affects_outdoor": bool,
                   "current_lat": float, "current_lon": float,
                   "remaining_minutes": int }
        Bad weather exceeded threshold.
          - WeatherAdvisor classifies blocked/deferred/safe stops.
          - Blocked stops (HC override = 0) are deferred in TripState.
          - Indoor alternatives are ranked by η_ij = S_pti / Dij.
          - PartialReplanner runs with deprioritize_outdoor=True.
        """
        severity        = payload.get("severity", 0.0)
        threshold       = payload.get("threshold", 0.5)
        condition       = payload.get("condition", "bad weather")
        affects_outdoor = payload.get("affects_outdoor", True)
        urgency         = "high" if severity > 0.80 else "normal"

        return ReplanDecision(
            should_replan = affects_outdoor,
            urgency       = urgency,
            reason        = (
                f"Weather: '{condition}' (severity {severity:.0%} > "
                f"{threshold:.0%}). "
                + ("Classifying outdoor stops; rerouting to indoor alternatives."
                   if affects_outdoor
                   else "No outdoor stops affected — no replan needed.")
            ),
            updated_state = state,
            metadata = {
                "weather_action":    "classify_and_replan",
                "condition":         condition,
                "severity":          severity,
                "threshold":         threshold,
                "affects_outdoor":   affects_outdoor,
                "deprioritize_outdoor": affects_outdoor,
                "current_lat":       payload.get("current_lat",  state.current_lat),
                "current_lon":       payload.get("current_lon",  state.current_lon),
                "remaining_minutes": payload.get(
                    "remaining_minutes", state.remaining_minutes_today()
                ),
            },
        )

    def _handle_venue_closed(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: { "stop_name": str }
        A planned stop is unexpectedly closed. Skip and replan immediately.
        """
        stop = payload.get("stop_name", "")
        if stop:
            state.mark_skipped(stop)
        return ReplanDecision(
            should_replan=True,
            urgency="high",
            reason=f"'{stop}' is unexpectedly closed — rerouting immediately.",
            updated_state=state,
        )

    # ── User-edit handlers ────────────────────────────────────────────────────

    def _handle_dislike_next(
        self, state: TripState, payload: dict
    ) -> ReplanDecision:
        """
        payload: {
            "current_stop": str  (optional — informational only),
            "current_lat":  float,
            "current_lon":  float,
            "current_time": str,
            "remaining_minutes": int,
        }
        User dislikes the next planned stop and requests alternatives.
        Does NOT mutate state — the advisory is printed by the session;
        the user then follows up with USER_REPLACE_POI or does nothing.
        Returns should_replan=False so no immediate replan is triggered.
        """
        return ReplanDecision(
            should_replan=False,
            urgency="low",
            reason="User dislikes next stop — computing alternatives.",
            updated_state=state,
            metadata={
                "user_edit_action":  "dislike_next",
                "current_lat":       payload.get("current_lat",  state.current_lat),
                "current_lon":       payload.get("current_lon",  state.current_lon),
                "current_time":      payload.get("current_time", state.current_time),
                "remaining_minutes": payload.get(
                    "remaining_minutes", state.remaining_minutes_today()
                ),
            },
        )

    def _handle_replace_poi(
        self, state: TripState, payload: dict
    ) -> ReplanDecision:
        """
        payload: {
            "replacement_record": AttractionRecord,  # chosen alternative
            "current_lat":        float,
            "current_lon":        float,
            "current_time":       str,
            "remaining_minutes":  int,
            "budget_remaining":   float,
        }
        User has chosen a specific alternative to substitute for the next stop.
        Validation + time recomputation are handled by the session via
        UserEditHandler.replace_stop().  If accepted, a replan is triggered
        FROM the new stop position; if rejected, no replan occurs.
        Returns should_replan=True so the session runs the replacement pipeline.
        """
        record = payload.get("replacement_record")
        record_name = getattr(record, "name", str(record)) if record else "<unknown>"
        return ReplanDecision(
            should_replan=True,
            urgency="normal",
            reason=f"User replacing next stop with '{record_name}'.",
            updated_state=state,
            metadata={
                "user_edit_action":   "replace_poi",
                "replacement_record": record,
                "current_lat":        payload.get("current_lat",  state.current_lat),
                "current_lon":        payload.get("current_lon",  state.current_lon),
                "current_time":       payload.get("current_time", state.current_time),
                "remaining_minutes":  payload.get(
                    "remaining_minutes", state.remaining_minutes_today()
                ),
                "budget_remaining":   payload.get("budget_remaining", 0.0),
            },
        )

    def _handle_skip_current(
        self, state: TripState, payload: dict
    ) -> ReplanDecision:
        """
        payload: {
            "stop_name": str  (currently active stop to abort mid-visit)
        }
        User aborts the current stop mid-visit. Differs from USER_SKIP:
            - USER_SKIP      marks the *next* stop skipped (before arrival)
            - USER_SKIP_CURRENT marks the *current ongoing* stop skipped
              and replans from the same lat/lon (no travel time consumed).
        The session calls state.mark_skipped() + triggers replan.
        """
        stop = payload.get("stop_name", "")
        if stop:
            state.mark_skipped(stop)
        return ReplanDecision(
            should_replan=True,
            urgency="normal",
            reason=(
                f"User aborted '{stop}' mid-visit — replanning remaining stops "
                f"from current position."
            ),
            updated_state=state,
            metadata={
                "user_edit_action":  "skip_current",
                "stop_name":         stop,
                "current_lat":       payload.get("current_lat",  state.current_lat),
                "current_lon":       payload.get("current_lon",  state.current_lon),
                "remaining_minutes": payload.get(
                    "remaining_minutes", state.remaining_minutes_today()
                ),
            },
        )

    # ── Hunger / Fatigue handlers ──────────────────────────────────────────

    def _handle_hunger(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        Fired when hunger_level ≥ HUNGER_TRIGGER_THRESHOLD.
        Signals session to insert a meal stop + run LocalRepair.
        """
        return ReplanDecision(
            should_replan=True,
            urgency="normal",
            reason=(
                f"Hunger level {state.hunger_level:.0%} exceeded threshold — "
                f"inserting meal stop and replanning downstream."
            ),
            updated_state=state,
            metadata={
                "hf_action":    "hunger",
                "hunger_level": state.hunger_level,
            },
        )

    def _handle_fatigue(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        Fired when fatigue_level ≥ FATIGUE_TRIGGER_THRESHOLD.
        Signals session to insert a rest break + run LocalRepair.
        """
        return ReplanDecision(
            should_replan=True,
            urgency="normal",
            reason=(
                f"Fatigue level {state.fatigue_level:.0%} exceeded threshold — "
                f"inserting rest break and replanning downstream."
            ),
            updated_state=state,
            metadata={
                "hf_action":     "fatigue",
                "fatigue_level": state.fatigue_level,
            },
        )

    def _handle_reorder(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: { "preferred_order": list[str]  (optional) }
        User requests a specific stop ordering.  The PartialReplanner ACO
        will re-sequence remaining stops; preferred_order is advisory only.
        """
        preferred = payload.get("preferred_order", [])
        state.replan_pending = True
        return ReplanDecision(
            should_replan=True,
            urgency="normal",
            reason=f"User requested reorder of remaining stops: {preferred}",
            updated_state=state,
            metadata={"reorder_preferred": preferred},
        )

    def _handle_manual_reopt(self, state: TripState, payload: dict) -> ReplanDecision:
        """
        payload: { "reason": str  (optional) }
        Explicit user-initiated full re-optimization of the rest of the day.
        """
        reason_text = payload.get("reason", "Manual re-optimization requested by user")
        state.replan_pending = True
        return ReplanDecision(
            should_replan=True,
            urgency="normal",
            reason=reason_text,
            updated_state=state,
        )
