"""
modules/reoptimization/execution_layer.py
-------------------------------------------
ExecutionLayer — the ONLY component that may mutate itinerary state.

Receives a validated AgentAction from AgentController and dispatches it
to the appropriate deterministic module:

  NO_ACTION           → noop
  REQUEST_USER_DECISION → build PendingDecision, present alternatives
  DEFER_POI           → LocalRepair.repair() (shift / remove single stop)
  REPLACE_POI         → AlternativeGenerator.generate() + present choices
  RELAX_CONSTRAINT    → mutate ConditionMonitor thresholds / planner params
  REOPTIMIZE_DAY      → PartialReplanner.replan() (bounded ACO re-run)

Safety guardrails (enforced before every execution):
  1. Cannot delete more than 1 stop per action.
  2. Cannot change hotel anchor.
  3. Cannot change destination city.
  4. Cannot modify budget directly.
  5. Every mutation is logged to ShortTermMemory.
"""

from __future__ import annotations

from typing import Optional

from modules.reoptimization.agent_action import ActionType, AgentAction
from modules.reoptimization.trip_state import TripState
from modules.reoptimization.local_repair import LocalRepair
from modules.reoptimization.partial_replanner import PartialReplanner
from modules.reoptimization.alternative_generator import (
    AlternativeGenerator, AlternativeOption,
)
from modules.memory.short_term_memory import ShortTermMemory
from schemas.constraints import ConstraintBundle
from schemas.itinerary import BudgetAllocation, DayPlan
from modules.tool_usage.attraction_tool import AttractionRecord
from modules.observability.logger import StructuredLogger

import hashlib
import json as _json

_logger = StructuredLogger()


# ── State hashing ─────────────────────────────────────────────────────────────

_TRANSIENT_FIELDS = frozenset({"current_day_plan", "replan_pending"})


def compute_state_hash(state: TripState) -> str:
    """Deterministic SHA-256 of the mutable parts of TripState.

    Ignores transient fields (current_day_plan, replan_pending) that change
    as a side-effect of replanning rather than as a true state mutation.
    """
    snapshot: dict = {}
    for k, v in sorted(vars(state).items()):
        if k in _TRANSIENT_FIELDS:
            continue
        if isinstance(v, set):
            v = sorted(v)
        snapshot[k] = v
    raw = _json.dumps(snapshot, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Safety violation sentinel ─────────────────────────────────────────────────

class SafetyViolation(RuntimeError):
    """Raised when an AgentAction violates a guardrail."""


# ── Execution result ──────────────────────────────────────────────────────────

class ExecutionResult:
    """Outcome of executing one AgentAction."""

    __slots__ = (
        "action", "executed", "new_plan", "alternatives",
        "relaxed_constraint", "error",
    )

    def __init__(
        self,
        action: AgentAction,
        *,
        executed: bool = True,
        new_plan: Optional[DayPlan] = None,
        alternatives: list[AlternativeOption] | None = None,
        relaxed_constraint: dict | None = None,
        error: str = "",
    ) -> None:
        self.action = action
        self.executed = executed
        self.new_plan = new_plan
        self.alternatives = alternatives or []
        self.relaxed_constraint = relaxed_constraint
        self.error = error

    def to_dict(self) -> dict:
        return {
            "action":             self.action.to_dict(),
            "executed":           self.executed,
            "new_plan_stops":     (
                [rp.name for rp in self.new_plan.route_points]
                if self.new_plan else []
            ),
            "alternatives":       [a.name for a in self.alternatives],
            "relaxed_constraint": self.relaxed_constraint,
            "error":              self.error,
        }


# ── Guardrail keywords ───────────────────────────────────────────────────────

_FORBIDDEN_PARAM_KEYS = frozenset({
    "change_hotel", "change_city", "modify_budget",
    "delete_multiple", "override_hc",
})


# ── ExecutionLayer ────────────────────────────────────────────────────────────

class ExecutionLayer:
    """
    Stateless executor.  Takes an AgentAction + live context ⇒ applies mutation.

    The agent (AgentController) has zero write access to TripState, DayPlan,
    or BudgetAllocation.  Only this class does.
    """

    def __init__(
        self,
        local_repair: LocalRepair,
        partial_replanner: PartialReplanner,
        alt_generator: AlternativeGenerator,
        stm: ShortTermMemory,
    ) -> None:
        self._repair = local_repair
        self._replanner = partial_replanner
        self._alt_gen = alt_generator
        self._stm = stm

    # ── Public API ────────────────────────────────────────────────────────────

    def execute(
        self,
        action: AgentAction,
        state: TripState,
        remaining_attractions: list[AttractionRecord],
        constraints: ConstraintBundle,
        budget: BudgetAllocation,
        *,
        restaurant_pool: list | None = None,
    ) -> ExecutionResult:
        """
        Validate guardrails, dispatch to the correct module, log to STM.

        Returns an ExecutionResult regardless of outcome.
        """
        # ── Step 1: Guardrails ────────────────────────────────────────────────
        violation = self._check_guardrails(action)
        if violation:
            self._stm.log_interaction("agent_action_blocked", {
                "action": action.to_dict(),
                "violation": violation,
            })
            return ExecutionResult(action, executed=False, error=violation)

        # ── Step 2: Dispatch ──────────────────────────────────────────────────
        dispatch = {
            ActionType.NO_ACTION:            self._exec_no_action,
            ActionType.REQUEST_USER_DECISION: self._exec_request_user,
            ActionType.DEFER_POI:            self._exec_defer,
            ActionType.REPLACE_POI:          self._exec_replace,
            ActionType.RELAX_CONSTRAINT:     self._exec_relax,
            ActionType.REOPTIMIZE_DAY:       self._exec_reoptimize,
        }
        handler = dispatch.get(action.action_type, self._exec_no_action)

        before_hash = compute_state_hash(state)
        result = handler(
            action, state, remaining_attractions, constraints, budget,
            restaurant_pool=restaurant_pool or [],
        )
        after_hash = compute_state_hash(state)

        _logger.log("default", "STATE_MUTATION", {
            "before_hash": before_hash,
            "after_hash": after_hash,
            "action": action.action_type.value,
        })

        # ── Step 3: Log to ShortTermMemory ────────────────────────────────────
        self._stm.log_interaction("agent_action_executed", {
            "action": action.to_dict(),
            "executed": result.executed,
            "error": result.error,
        })

        return result

    # ── Guardrail check ───────────────────────────────────────────────────────

    @staticmethod
    def _check_guardrails(action: AgentAction, *, session_id: str = "default") -> str:
        """Return a non-empty error string if the action is unsafe; else ''."""
        violations: list[str] = []

        # Rule 4: forbidden parameter keys
        for key in _FORBIDDEN_PARAM_KEYS:
            if key in action.parameters:
                violations.append(f"SAFETY_VIOLATION: forbidden parameter '{key}'")

        # Rule 1: cannot delete multiple stops
        targets = action.parameters.get("targets", [])
        if isinstance(targets, list) and len(targets) > 1:
            violations.append("SAFETY_VIOLATION: cannot delete >1 stop in one action")

        if violations:
            _logger.log(session_id, "GUARDRAIL_CHECK", {
                "status": "BLOCKED",
                "violations": violations,
            })
            for v in violations:
                _logger.log(session_id, "GUARDRAIL_BLOCK", {"reason": v})
            return violations[0]

        _logger.log(session_id, "GUARDRAIL_CHECK", {
            "status": "PASS",
            "violations": [],
        })
        return ""

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _exec_no_action(
        self, action, state, remaining, constraints, budget, **kw
    ) -> ExecutionResult:
        return ExecutionResult(action, executed=True)

    def _exec_request_user(
        self, action, state, remaining, constraints, budget, **kw
    ) -> ExecutionResult:
        """
        Build a list of alternatives and return them — the caller
        (session) is responsible for presenting the PendingDecision panel.
        """
        poi = action.target_poi or ""
        category_hint = action.parameters.get("category_hint", "")
        candidates = [
            a for a in remaining
            if a.name != poi
            and a.name not in state.visited_stops
            and a.name not in state.skipped_stops
        ]
        from datetime import time as _dtime
        try:
            _h, _m = map(int, state.current_time.split(":"))
            _t_cur = _dtime(_h, _m)
        except (ValueError, AttributeError):
            _t_cur = _dtime(9, 0)

        alts = self._alt_gen.generate(
            disrupted_poi_name=poi,
            disrupted_category=category_hint or "Attraction",
            candidates=candidates,
            restaurant_pool=kw.get("restaurant_pool", []),
            context={
                "current_lat": state.current_lat,
                "current_lon": state.current_lon,
                "current_time": _t_cur,
                "weather_condition": action.parameters.get("condition", "clear"),
                "crowd_forecast": {},
                "n_alternatives": 5,
            },
        )

        return ExecutionResult(
            action, executed=True, alternatives=alts,
        )

    def _exec_defer(
        self, action, state, remaining, constraints, budget, **kw
    ) -> ExecutionResult:
        """Defer a single POI via LocalRepair (shift / remove today)."""
        poi = action.target_poi
        if not poi:
            return ExecutionResult(action, executed=False, error="No target_poi")

        state.defer_stop(poi)
        filtered = [
            a for a in remaining
            if a.name not in (state.visited_stops | state.skipped_stops
                              | state.deferred_stops)
        ]
        day_plan = state.current_day_plan
        if day_plan is None:
            return ExecutionResult(action, executed=True, new_plan=None)

        cause = action.parameters.get("cause", "agent_defer")
        result = self._repair.repair(
            disrupted_stop_name=poi,
            current_plan=day_plan,
            state=state,
            remaining_pool=filtered,
            constraints=constraints,
            disruption_type=cause.upper(),
            allow_shift=True,
            allow_replace=True,
            crowd_level=action.parameters.get("crowd_level", 0.0),
            crowd_threshold=action.parameters.get("crowd_threshold", 1.0),
        )

        new_plan = result.updated_plan if result else None
        if new_plan is not None:
            state.current_day_plan = new_plan
        return ExecutionResult(action, executed=True, new_plan=new_plan)

    def _exec_replace(
        self, action, state, remaining, constraints, budget, **kw
    ) -> ExecutionResult:
        """
        Generate alternatives for a POI and return them.
        The session will present choices; actual swap happens on user confirm.
        """
        poi = action.target_poi or ""
        category_hint = action.parameters.get("category_hint", "Attraction")
        candidates = [
            a for a in remaining
            if a.name != poi
            and a.name not in state.visited_stops
            and a.name not in state.skipped_stops
        ]
        from datetime import time as _dtime
        try:
            _h, _m = map(int, state.current_time.split(":"))
            _t_cur = _dtime(_h, _m)
        except (ValueError, AttributeError):
            _t_cur = _dtime(9, 0)

        alts = self._alt_gen.generate(
            disrupted_poi_name=poi,
            disrupted_category=category_hint,
            candidates=candidates,
            restaurant_pool=kw.get("restaurant_pool", []),
            context={
                "current_lat": state.current_lat,
                "current_lon": state.current_lon,
                "current_time": _t_cur,
                "weather_condition": action.parameters.get("condition", "clear"),
                "crowd_forecast": {},
                "n_alternatives": 5,
            },
        )
        return ExecutionResult(action, executed=True, alternatives=alts)

    def _exec_relax(
        self, action, state, remaining, constraints, budget, **kw
    ) -> ExecutionResult:
        """
        Relax a soft constraint parameter (e.g. max_travel_min 60 → 120).
        Does NOT touch budget or hard constraints.
        """
        constraint_name = action.parameters.get("constraint", "")
        new_value = action.parameters.get("new")
        old_value = action.parameters.get("old")
        if not constraint_name or new_value is None:
            return ExecutionResult(action, executed=False, error="Missing constraint/new")

        return ExecutionResult(
            action, executed=True,
            relaxed_constraint={
                "constraint": constraint_name,
                "old": old_value,
                "new": new_value,
            },
        )

    def _exec_reoptimize(
        self, action, state, remaining, constraints, budget, **kw
    ) -> ExecutionResult:
        """Bounded ACO re-run for the remainder of the day."""
        deprioritize = action.parameters.get("deprioritize_outdoor", False)
        new_plan = self._replanner.replan(
            state=state,
            remaining_attractions=remaining,
            constraints=constraints,
            deprioritize_outdoor=deprioritize,
        )
        state.current_day_plan = new_plan
        state.replan_pending = False
        return ExecutionResult(action, executed=True, new_plan=new_plan)
