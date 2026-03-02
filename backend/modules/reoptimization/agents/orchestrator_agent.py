"""
modules/reoptimization/agents/orchestrator_agent.py
------------------------------------------------------
OrchestratorAgent — routes incoming events to the correct specialist.

This agent does NOT plan trips, modify itineraries, or infer missing data.
It only decides which specialist agent should handle the current event.

Deterministic routing logic (no LLM required in stub mode):
  weather / crowd / traffic readings  →  DisruptionAgent
  budget keyword                      →  BudgetAgent
  preference change (slower/faster)   →  PreferenceAgent
  explain keyword                     →  ExplanationAgent
  memory keyword                      →  MemoryAgent
  multi-disruption / time pressure    →  PlanningAgent
  no actionable signal                →  NONE
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.reoptimization.agents.base_agent import AgentContext


# ── Routing result ────────────────────────────────────────────────────────────

@dataclass
class OrchestratorResult:
    """Strict JSON-shaped output of the OrchestratorAgent."""
    invoke_agent: str   # e.g. "DisruptionAgent" | "PlanningAgent" | "NONE"
    reason:       str   # short one-line reason

    def to_dict(self) -> dict:
        return {"invoke_agent": self.invoke_agent, "reason": self.reason}


# ── Orchestrator ──────────────────────────────────────────────────────────────

class OrchestratorAgent:
    """
    Pure router.  Given context, returns which specialist should act.

    Allowed agents:
      PlanningAgent, DisruptionAgent, BudgetAgent,
      PreferenceAgent, MemoryAgent, ExplanationAgent.
    """

    AGENT_NAME = "OrchestratorAgent"

    SYSTEM_PROMPT = """\
You are OrchestratorAgent.

You DO NOT plan trips.
You DO NOT modify itinerary.
You DO NOT infer missing data.

You only decide which specialist agent should handle the current event.

Allowed agents:
- PlanningAgent
- DisruptionAgent
- BudgetAgent
- PreferenceAgent
- MemoryAgent
- ExplanationAgent

Return STRICT JSON:

{
  "invoke_agent": "<agent_name>",
  "reason": "<short_reason>"
}

If unclear:
{
  "invoke_agent": "NONE",
  "reason": "insufficient_information"
}

No text outside JSON.

You must NOT:
- Generate itinerary content
- Change schedule directly
- Assume city data
- Invent coordinates
- Create new POIs
- Override deterministic constraints

Return JSON only.
If output is not valid JSON, it will be rejected."""

    # ── Allowed specialist names ──────────────────────────────────────────────
    ALLOWED_AGENTS = frozenset({
        "PlanningAgent", "DisruptionAgent", "BudgetAgent",
        "PreferenceAgent", "MemoryAgent", "ExplanationAgent",
    })

    # ── Explicit event → agent mapping ────────────────────────────────────────
    _EVENT_ROUTING: dict[str, str] = {
        "crowd":      "DisruptionAgent",
        "weather":    "DisruptionAgent",
        "traffic":    "DisruptionAgent",
        "budget":     "BudgetAgent",
        "slower":     "PreferenceAgent",
        "faster":     "PreferenceAgent",
        "preference": "PreferenceAgent",
        "explain":    "ExplanationAgent",
        "memory":     "MemoryAgent",
        "plan":       "PlanningAgent",
        "reoptimize": "PlanningAgent",
    }

    # ── Public API ────────────────────────────────────────────────────────────

    def route(self, context: AgentContext) -> OrchestratorResult:
        """
        Determine which specialist agent should handle the current context.
        Deterministic: same context → same routing.
        """
        # ── 1. Explicit event type match ──────────────────────────────────────
        event = context.event_type.lower().strip()
        if event in self._EVENT_ROUTING:
            agent = self._EVENT_ROUTING[event]
            return OrchestratorResult(agent, f"{event}_event_detected")

        # ── 2. Auto-detect from observation ───────────────────────────────────
        obs = context.observation

        # Weather threshold exceeded
        if (obs.weather_severity > 0
                and obs.thresholds is not None
                and obs.weather_severity > obs.thresholds.weather):
            return OrchestratorResult(
                "DisruptionAgent", "weather_threshold_exceeded"
            )

        # Crowd threshold exceeded
        if (obs.crowd_level is not None
                and obs.thresholds is not None
                and obs.crowd_level > obs.thresholds.crowd):
            return OrchestratorResult(
                "DisruptionAgent", "crowd_threshold_exceeded"
            )

        # Traffic threshold exceeded
        if (obs.traffic_level is not None
                and obs.thresholds is not None
                and obs.traffic_level > obs.thresholds.traffic):
            return OrchestratorResult(
                "DisruptionAgent", "traffic_threshold_exceeded"
            )

        # Multiple disruptions today → replanning needed
        if obs.disruptions_today >= 3:
            return OrchestratorResult(
                "PlanningAgent", "multiple_disruptions_require_reoptimization"
            )

        # Time pressure
        if obs.remaining_minutes <= 60 and len(obs.remaining_stops) > 1:
            return OrchestratorResult(
                "PlanningAgent", "time_pressure_detected"
            )

        # ── 3. Nothing actionable ─────────────────────────────────────────────
        return OrchestratorResult("NONE", "no_actionable_event")

    def __repr__(self) -> str:
        return "OrchestratorAgent"
