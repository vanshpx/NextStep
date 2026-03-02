"""
modules/reoptimization/agents/agent_dispatcher.py
----------------------------------------------------
AgentDispatcher — end-to-end pipeline:

    OrchestratorAgent.route(context)
      → specialist.evaluate(context)
        → ExecutionLayer.execute(action, …)
          → ExecutionResult

The dispatcher owns no state.  It wires the observation, routing,
decision, and execution steps together in a single ``dispatch()`` call.
"""

from __future__ import annotations

from typing import Optional

from modules.reoptimization.agents.base_agent import BaseAgent, AgentContext
from modules.reoptimization.agents.orchestrator_agent import (
    OrchestratorAgent, OrchestratorResult,
)
from modules.reoptimization.agent_action import ActionType, AgentAction
from modules.reoptimization.agent_controller import AgentObservation
from modules.reoptimization.execution_layer import ExecutionLayer, ExecutionResult
from modules.reoptimization.trip_state import TripState
from modules.memory.short_term_memory import ShortTermMemory
from schemas.constraints import ConstraintBundle
from schemas.itinerary import BudgetAllocation
from modules.tool_usage.attraction_tool import AttractionRecord


# ── Dispatch result (wraps orchestrator routing + execution result) ───────────

class DispatchResult:
    """Full trace of an orchestrated multi-agent invocation."""

    __slots__ = (
        "routing", "specialist_name", "action", "execution_result",
    )

    def __init__(
        self,
        routing: OrchestratorResult,
        specialist_name: str,
        action: AgentAction,
        execution_result: ExecutionResult,
    ) -> None:
        self.routing          = routing
        self.specialist_name  = specialist_name
        self.action           = action
        self.execution_result = execution_result

    def to_dict(self) -> dict:
        return {
            "routing":       self.routing.to_dict(),
            "specialist":    self.specialist_name,
            "action":        self.action.to_dict(),
            "execution":     self.execution_result.to_dict(),
        }


# ── AgentDispatcher ──────────────────────────────────────────────────────────

class AgentDispatcher:
    """
    Orchestrator → Specialist → ExecutionLayer pipeline.

    Usage::

        dispatcher = AgentDispatcher(
            orchestrator=OrchestratorAgent(),
            specialists={
                "DisruptionAgent": disruption_agent,
                "PlanningAgent":   planning_agent,
                ...
            },
            execution_layer=execution_layer,
            stm=stm,
        )
        result = dispatcher.dispatch(context, state, remaining, constraints, budget)
    """

    def __init__(
        self,
        orchestrator:    OrchestratorAgent,
        specialists:     dict[str, BaseAgent],
        execution_layer: ExecutionLayer,
        stm:             ShortTermMemory,
    ) -> None:
        self._orchestrator    = orchestrator
        self._specialists     = specialists
        self._execution_layer = execution_layer
        self._stm             = stm

    @property
    def orchestrator(self) -> OrchestratorAgent:
        return self._orchestrator

    @property
    def specialists(self) -> dict[str, BaseAgent]:
        return dict(self._specialists)

    # ── Core pipeline ─────────────────────────────────────────────────────────

    def dispatch(
        self,
        context: AgentContext,
        state: TripState,
        remaining_attractions: list[AttractionRecord],
        constraints: ConstraintBundle,
        budget: BudgetAllocation,
        *,
        restaurant_pool: list | None = None,
    ) -> DispatchResult:
        """
        Full pipeline: orchestrate → specialist decide → execute.

        1. OrchestratorAgent routes the context to a specialist.
        2. The specialist evaluates the context → AgentAction.
        3. ExecutionLayer validates guardrails and applies the action.
        4. Result logged to ShortTermMemory.

        Returns a DispatchResult containing the full trace.
        """
        # ── Step 1: Route ─────────────────────────────────────────────────────
        routing = self._orchestrator.route(context)

        print(f"  [Orchestrator] → {routing.invoke_agent} ({routing.reason})")

        # ── Step 2: Look up specialist ────────────────────────────────────────
        specialist = self._specialists.get(routing.invoke_agent)

        if specialist is None:
            # No matching specialist — return NO_ACTION
            no_action = AgentAction(
                action_type=ActionType.NO_ACTION,
                reasoning=(
                    f"Orchestrator routed to '{routing.invoke_agent}' "
                    f"— no specialist available; no action"
                ),
            )
            noop_result = ExecutionResult(no_action, executed=True)
            self._stm.log_interaction("orchestrator_dispatch", {
                "routing": routing.to_dict(),
                "specialist": "NONE",
                "action": no_action.to_dict(),
            })
            return DispatchResult(routing, "NONE", no_action, noop_result)

        # ── Step 3: Specialist decides ────────────────────────────────────────
        action = specialist.evaluate(context)

        print(f"  [{specialist.AGENT_NAME}] {action}")

        # ── Step 4: Execute via ExecutionLayer ────────────────────────────────
        exec_result = self._execution_layer.execute(
            action=action,
            state=state,
            remaining_attractions=remaining_attractions,
            constraints=constraints,
            budget=budget,
            restaurant_pool=restaurant_pool or [],
        )

        # ── Step 5: Log full trace to STM ─────────────────────────────────────
        self._stm.log_interaction("orchestrator_dispatch", {
            "routing":    routing.to_dict(),
            "specialist": specialist.AGENT_NAME,
            "action":     action.to_dict(),
            "executed":   exec_result.executed,
            "error":      exec_result.error,
        })

        return DispatchResult(routing, specialist.AGENT_NAME, action, exec_result)
