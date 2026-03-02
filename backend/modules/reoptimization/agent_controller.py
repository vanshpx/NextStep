"""
modules/reoptimization/agent_controller.py
---------------------------------------------
AgentController — deterministic decision engine for mid-trip re-optimization.

Architecture contract
─────────────────────
  • The agent OBSERVES the world (itinerary, time, location, budget,
    disruptions, preferences, environment).
  • The agent EMITS a single AgentAction.
  • The agent NEVER mutates itinerary state directly.
  • Only the ExecutionLayer (execution_layer.py) may apply state changes.

Tool access (read-only probes):
  • CrowdTool      — current / forecast crowd level at a POI
  • WeatherTool    — current weather at a lat/lon
  • TrafficTool    — current traffic between two points
  • MemoryModule   — disruption history, user preference drift
  • BudgetModule   — remaining category budgets

Forbidden calls:
  • RoutePlanner   — only the execution layer may trigger replans.

Safety rules (hard-coded, not overridable):
  1. Cannot delete >1 stop per action.
  2. Cannot change hotel.
  3. Cannot change city.
  4. Cannot modify budget directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from modules.reoptimization.agent_action import ActionType, AgentAction
from modules.reoptimization.trip_state import TripState
from modules.reoptimization.condition_monitor import (
    ConditionMonitor, ConditionThresholds, WEATHER_SEVERITY,
)
from modules.memory.disruption_memory import DisruptionMemory
from modules.memory.short_term_memory import ShortTermMemory
from schemas.constraints import ConstraintBundle
from schemas.itinerary import BudgetAllocation, DayPlan
from modules.tool_usage.attraction_tool import AttractionRecord
from modules.tool_usage.weather_tool import WeatherTool
from modules.tool_usage.traffic_tool import TrafficTool
from modules.observability.logger import StructuredLogger

_logger = StructuredLogger()


# ── Internal observation snapshot ─────────────────────────────────────────────

@dataclass
class AgentObservation:
    """
    Read-only snapshot of everything the agent sees before deciding.
    Built once per evaluate() call — the agent cannot request more data.
    """

    # Itinerary
    current_day_plan: Optional[DayPlan] = None
    remaining_stops: list[str] = field(default_factory=list)

    # Position & time
    current_time: str = "09:00"
    current_lat: float = 0.0
    current_lon: float = 0.0
    remaining_minutes: int = 660
    total_day_minutes: int = 660

    # Budget
    budget: Optional[BudgetAllocation] = None
    budget_spent: dict[str, float] = field(default_factory=dict)

    # Disruptions (active readings)
    crowd_level: Optional[float] = None
    weather_condition: Optional[str] = None
    weather_severity: float = 0.0
    traffic_level: Optional[float] = None
    traffic_delay_minutes: int = 0

    # Thresholds (derived from preferences)
    thresholds: Optional[ConditionThresholds] = None

    # Next stop context
    next_stop_name: str = ""
    next_stop_is_outdoor: bool = False
    next_stop_spti_proxy: float = 0.0

    # User preferences (snapshot)
    avoid_crowds: bool = False
    pace_preference: str = "moderate"

    # Disruption history count
    disruptions_today: int = 0

    def to_dict(self) -> dict:
        return {
            "current_time":           self.current_time,
            "remaining_minutes":      self.remaining_minutes,
            "next_stop":              self.next_stop_name,
            "next_stop_outdoor":      self.next_stop_is_outdoor,
            "next_stop_spti":         round(self.next_stop_spti_proxy, 3),
            "crowd_level":            self.crowd_level,
            "weather_condition":      self.weather_condition,
            "weather_severity":       round(self.weather_severity, 3),
            "traffic_level":          self.traffic_level,
            "traffic_delay_min":      self.traffic_delay_minutes,
            "disruptions_today":      self.disruptions_today,
            "remaining_stops":        len(self.remaining_stops),
        }


# ── AgentController ──────────────────────────────────────────────────────────

class AgentController:
    """
    Pure decision engine.  Given an observation, returns one AgentAction.

    Evaluation order (first matching rule wins):
      1. Weather unsafe  → DEFER or REPLACE outdoor POI
      2. Crowd exceeded  → DEFER or REQUEST_USER_DECISION
      3. Traffic exceeded → DEFER (high-value) or REPLACE (low-value)
      4. Multiple disruptions today → REOPTIMIZE_DAY
      5. Constraint tension detected → RELAX_CONSTRAINT
      6. Otherwise → NO_ACTION

    The agent never calls RoutePlanner.  It never edits the itinerary.
    """

    # ── Safety constants ──────────────────────────────────────────────────────
    HC_UNSAFE_WEATHER_THRESHOLD: float = 0.75     # severity ≥ this → HC_pti = 0
    HIGH_VALUE_SPTI_CUTOFF:     float = 0.65      # S_pti proxy above → DEFER; below → REPLACE
    MULTI_DISRUPTION_TRIGGER:   int   = 3         # ≥3 disruptions today → REOPTIMIZE_DAY
    TIME_PRESSURE_MINUTES:      int   = 60        # <60 min left → relax travel constraint

    def __init__(
        self,
        condition_monitor: ConditionMonitor,
        disruption_memory: DisruptionMemory,
        short_term_memory: ShortTermMemory,
        weather_tool: WeatherTool | None = None,
        traffic_tool: TrafficTool | None = None,
    ) -> None:
        self._monitor = condition_monitor
        self._disruption_memory = disruption_memory
        self._stm = short_term_memory
        self._weather_tool = weather_tool or WeatherTool()
        self._traffic_tool = traffic_tool or TrafficTool()

    # ── Public API ────────────────────────────────────────────────────────────

    def observe(
        self,
        state: TripState,
        constraints: ConstraintBundle,
        remaining_attractions: list[AttractionRecord],
        budget: BudgetAllocation,
        *,
        crowd_level: float | None = None,
        weather_condition: str | None = None,
        traffic_level: float | None = None,
        traffic_delay_minutes: int = 0,
    ) -> AgentObservation:
        """
        Build a read-only observation snapshot from live state.
        The agent uses ONLY this snapshot to decide — no further data access.
        """
        # Resolve next stop
        next_stop = ""
        next_outdoor = False
        next_spti = 0.0
        excluded = (state.visited_stops | state.skipped_stops | state.deferred_stops)
        if state.current_day_plan:
            for rp in state.current_day_plan.route_points:
                if rp.name not in excluded:
                    next_stop = rp.name
                    break
        if next_stop:
            rec = next((a for a in remaining_attractions if a.name == next_stop), None)
            if rec:
                next_outdoor = getattr(rec, "is_outdoor", False)
                next_spti = min(1.0, max(0.0, rec.rating / 5.0))

        # Weather severity
        w_sev = 0.0
        if weather_condition:
            w_sev = WEATHER_SEVERITY.get(weather_condition.lower(), 0.0)

        remaining_names = [
            a.name for a in remaining_attractions
            if a.name not in excluded
        ]

        return AgentObservation(
            current_day_plan=state.current_day_plan,
            remaining_stops=remaining_names,
            current_time=state.current_time,
            current_lat=state.current_lat,
            current_lon=state.current_lon,
            remaining_minutes=state.remaining_minutes_today(),
            total_day_minutes=660,   # 09:00–20:00 = 11 h
            budget=budget,
            budget_spent=dict(state.budget_spent),
            crowd_level=crowd_level,
            weather_condition=weather_condition,
            weather_severity=w_sev,
            traffic_level=traffic_level,
            traffic_delay_minutes=traffic_delay_minutes,
            thresholds=self._monitor.thresholds,
            next_stop_name=next_stop,
            next_stop_is_outdoor=next_outdoor,
            next_stop_spti_proxy=next_spti,
            avoid_crowds=(
                constraints.soft.avoid_crowds
                if constraints and constraints.soft else False
            ),
            pace_preference=(
                constraints.soft.pace_preference
                if constraints and constraints.soft else "moderate"
            ),
            disruptions_today=len(state.disruption_log),
        )

    def evaluate(self, obs: AgentObservation, *, session_id: str = "default") -> AgentAction:
        """
        Pure decision function.  Deterministic — same observation ⇒ same action.

        Returns exactly one AgentAction.  No free-text.
        """
        # ── Rule 1: Weather unsafe → DEFER outdoor / REPLACE ─────────────────
        action = self._check_weather(obs)
        if action:
            return self._log_decision(action, session_id)

        # ── Rule 2: Crowd exceeded → DEFER / REQUEST_USER_DECISION ───────────
        action = self._check_crowd(obs)
        if action:
            return self._log_decision(action, session_id)

        # ── Rule 3: Traffic exceeded → DEFER / REPLACE ───────────────────────
        action = self._check_traffic(obs)
        if action:
            return self._log_decision(action, session_id)

        # ── Rule 4: Multiple disruptions → REOPTIMIZE_DAY ───────────────────
        if obs.disruptions_today >= self.MULTI_DISRUPTION_TRIGGER:
            return self._log_decision(AgentAction(
                action_type=ActionType.REOPTIMIZE_DAY,
                target_poi=None,
                reasoning=(
                    f"{obs.disruptions_today} disruptions today — "
                    f"schedule integrity compromised; bounded reoptimization"
                ),
                parameters={"deprioritize_outdoor": obs.weather_severity > 0.4},
            ), session_id)

        # ── Rule 5: Time pressure → RELAX_CONSTRAINT ────────────────────────
        action = self._check_time_pressure(obs)
        if action:
            return self._log_decision(action, session_id)

        # ── Rule 6: NO_ACTION ────────────────────────────────────────────────
        return self._log_decision(AgentAction(
            action_type=ActionType.NO_ACTION,
            reasoning="No disruption detected — continue itinerary",
        ), session_id)

    @staticmethod
    def _log_decision(action: AgentAction, session_id: str) -> AgentAction:
        """Log the agent decision and return the action unchanged."""
        _logger.log(session_id, "AGENT_DECISION", {
            "agent": "AgentController",
            "decision": action.to_dict(),
        })
        return action

    # ── Private rule evaluators ───────────────────────────────────────────────

    def _check_weather(self, obs: AgentObservation) -> AgentAction | None:
        if obs.weather_severity <= 0 or obs.thresholds is None:
            return None
        if obs.weather_severity <= obs.thresholds.weather:
            return None

        # Weather exceeds threshold — decide based on next stop outdoor + severity
        if obs.weather_severity >= self.HC_UNSAFE_WEATHER_THRESHOLD:
            # HC-blocked: outdoor stops are infeasible
            if obs.next_stop_is_outdoor and obs.next_stop_name:
                return AgentAction(
                    action_type=ActionType.REPLACE_POI,
                    target_poi=obs.next_stop_name,
                    reasoning=(
                        f"Weather severity {obs.weather_severity:.0%} ≥ HC unsafe "
                        f"threshold — outdoor stop '{obs.next_stop_name}' blocked"
                    ),
                    parameters={
                        "cause": "weather_unsafe",
                        "severity": obs.weather_severity,
                        "category_hint": "indoor",
                    },
                )
            # All indoor remaining — no POI-level action needed
            return None

        # Moderate weather — defer outdoor next stop if applicable
        if obs.next_stop_is_outdoor and obs.next_stop_name:
            return AgentAction(
                action_type=ActionType.DEFER_POI,
                target_poi=obs.next_stop_name,
                reasoning=(
                    f"Weather {obs.weather_condition} (severity {obs.weather_severity:.0%}) "
                    f"> threshold {obs.thresholds.weather:.0%} — "
                    f"deferring outdoor stop '{obs.next_stop_name}'"
                ),
                parameters={
                    "cause": "weather",
                    "severity": obs.weather_severity,
                    "condition": obs.weather_condition or "",
                },
            )
        return None

    def _check_crowd(self, obs: AgentObservation) -> AgentAction | None:
        if obs.crowd_level is None or obs.thresholds is None:
            return None
        if obs.crowd_level <= obs.thresholds.crowd:
            return None

        stop = obs.next_stop_name
        if not stop:
            return None

        # High-value stop → DEFER; low-value → ask user
        if obs.next_stop_spti_proxy >= self.HIGH_VALUE_SPTI_CUTOFF:
            return AgentAction(
                action_type=ActionType.DEFER_POI,
                target_poi=stop,
                reasoning=(
                    f"Crowd {obs.crowd_level:.0%} > threshold "
                    f"{obs.thresholds.crowd:.0%} at '{stop}' "
                    f"(high value S_pti={obs.next_stop_spti_proxy:.2f} — deferring)"
                ),
                parameters={
                    "cause": "crowd",
                    "crowd_level": obs.crowd_level,
                },
            )
        else:
            return AgentAction(
                action_type=ActionType.REQUEST_USER_DECISION,
                target_poi=stop,
                reasoning=(
                    f"Crowd {obs.crowd_level:.0%} > threshold "
                    f"{obs.thresholds.crowd:.0%} at '{stop}' "
                    f"(low value S_pti={obs.next_stop_spti_proxy:.2f} "
                    f"— user should decide)"
                ),
                parameters={
                    "cause": "crowd",
                    "crowd_level": obs.crowd_level,
                    "spti_proxy": obs.next_stop_spti_proxy,
                },
            )

    def _check_traffic(self, obs: AgentObservation) -> AgentAction | None:
        if obs.traffic_level is None or obs.thresholds is None:
            return None
        if obs.traffic_level <= obs.thresholds.traffic:
            return None

        stop = obs.next_stop_name
        if not stop:
            return None

        if obs.next_stop_spti_proxy >= self.HIGH_VALUE_SPTI_CUTOFF:
            return AgentAction(
                action_type=ActionType.DEFER_POI,
                target_poi=stop,
                reasoning=(
                    f"Traffic {obs.traffic_level:.0%} > threshold "
                    f"{obs.thresholds.traffic:.0%} — "
                    f"high value '{stop}' deferred"
                ),
                parameters={
                    "cause": "traffic",
                    "traffic_level": obs.traffic_level,
                    "delay_minutes": obs.traffic_delay_minutes,
                },
            )
        else:
            return AgentAction(
                action_type=ActionType.REPLACE_POI,
                target_poi=stop,
                reasoning=(
                    f"Traffic {obs.traffic_level:.0%} > threshold "
                    f"{obs.thresholds.traffic:.0%} — "
                    f"low value '{stop}' should be replaced"
                ),
                parameters={
                    "cause": "traffic",
                    "traffic_level": obs.traffic_level,
                    "delay_minutes": obs.traffic_delay_minutes,
                },
            )

    def _check_time_pressure(self, obs: AgentObservation) -> AgentAction | None:
        """If remaining time is tight and there are many stops, relax travel constraint."""
        if obs.remaining_minutes > self.TIME_PRESSURE_MINUTES:
            return None
        if len(obs.remaining_stops) <= 1:
            return None  # only one stop left — no tension
        return AgentAction(
            action_type=ActionType.RELAX_CONSTRAINT,
            target_poi=None,
            reasoning=(
                f"Only {obs.remaining_minutes} min left with "
                f"{len(obs.remaining_stops)} stops — relaxing travel constraint"
            ),
            parameters={
                "constraint": "max_travel_min",
                "old": 60,
                "new": 120,
            },
        )
