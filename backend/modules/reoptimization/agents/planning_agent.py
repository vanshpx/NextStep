"""
modules/reoptimization/agents/planning_agent.py
-------------------------------------------------
PlanningAgent — decides planning STRATEGY only.

It does NOT generate itineraries, compute timings, or access coordinates.
It inspects the observation snapshot and returns one of four strategy decisions
that the ExecutionLayer maps to a concrete module call.

Strategy → ActionType mapping (consumed by ExecutionLayer):
  FULL_PLAN    → REOPTIMIZE_DAY  (bounded ACO re-run, scope DAY)
  LOCAL_REPAIR → DEFER_POI       (local swap/insert, scope POI)
  REORDER      → RELAX_CONSTRAINT (resequence remaining, scope DAY)
  NO_CHANGE    → NO_ACTION       (continue as-is, scope POI)
"""

from __future__ import annotations

from modules.reoptimization.agents.base_agent import BaseAgent, AgentContext
from modules.reoptimization.agent_action import ActionType, AgentAction


class PlanningAgent(BaseAgent):
    """Specialist for schedule-level planning strategy decisions."""

    AGENT_NAME = "PlanningAgent"

    SYSTEM_PROMPT = """\
You are PlanningAgent.

You do NOT generate itineraries.
You do NOT compute timings.
You do NOT access coordinates.

You decide planning STRATEGY only.

Available plan actions:
- FULL_PLAN
- LOCAL_REPAIR
- REORDER
- NO_CHANGE

Scope:
- DAY
- POI

Return STRICT JSON:

{
  "plan_action": "<action>",
  "scope": "<DAY|POI>",
  "justification": "<short_reason>"
}

If no action required:
{
  "plan_action": "NO_CHANGE",
  "scope": "POI",
  "justification": "no_violation_detected"
}

No prose.

You must NOT:
- Generate itinerary content
- Change schedule directly
- Assume city data
- Invent coordinates
- Create new POIs
- Override deterministic constraints

Return JSON only.
If output is not valid JSON, it will be rejected."""

    # ── Constants ─────────────────────────────────────────────────────────────
    MULTI_DISRUPTION_TRIGGER: int = 3    # ≥3 disruptions → day is compromised
    TIME_PRESSURE_MINUTES:    int = 60   # <60 min left with >1 stop → reorder
    SINGLE_DISRUPTION_REPAIR: int = 1    # 1-2 disruptions → local repair viable

    def evaluate(self, context: AgentContext) -> AgentAction:
        obs = context.observation

        # ── Rule 1: ≥3 disruptions today → FULL_PLAN (scope DAY) ─────────────
        #   Schedule integrity compromised; bounded ACO re-run needed.
        if obs.disruptions_today >= self.MULTI_DISRUPTION_TRIGGER:
            return AgentAction(
                action_type=ActionType.REOPTIMIZE_DAY,
                target_poi=None,
                reasoning=(
                    f"PlanningAgent: {obs.disruptions_today} disruptions — "
                    f"FULL_PLAN at DAY scope"
                ),
                parameters={
                    "plan_action":   "FULL_PLAN",
                    "scope":         "DAY",
                    "justification": (
                        f"{obs.disruptions_today}_disruptions_compromise_schedule"
                    ),
                    "deprioritize_outdoor": obs.weather_severity > 0.4,
                },
            )

        # ── Rule 2: Time pressure → REORDER (scope DAY) ──────────────────────
        #   Not enough time to visit all remaining stops in current sequence;
        #   reorder / relax travel constraint to fit what we can.
        if (obs.remaining_minutes <= self.TIME_PRESSURE_MINUTES
                and len(obs.remaining_stops) > 1):
            return AgentAction(
                action_type=ActionType.RELAX_CONSTRAINT,
                target_poi=None,
                reasoning=(
                    f"PlanningAgent: {obs.remaining_minutes} min left, "
                    f"{len(obs.remaining_stops)} stops — REORDER at DAY scope"
                ),
                parameters={
                    "plan_action":   "REORDER",
                    "scope":         "DAY",
                    "justification": "time_pressure_requires_resequencing",
                    "constraint":    "max_travel_min",
                    "old":           60,
                    "new":           120,
                },
            )

        # ── Rule 3: 1-2 disruptions → LOCAL_REPAIR (scope POI) ───────────────
        #   Only a few disruptions; local repair (swap / insert nearest) is
        #   sufficient — no need for a full ACO rerun.
        if (self.SINGLE_DISRUPTION_REPAIR
                <= obs.disruptions_today
                < self.MULTI_DISRUPTION_TRIGGER
                and obs.next_stop_name):
            return AgentAction(
                action_type=ActionType.DEFER_POI,
                target_poi=obs.next_stop_name,
                reasoning=(
                    f"PlanningAgent: {obs.disruptions_today} disruption(s) — "
                    f"LOCAL_REPAIR at POI scope for '{obs.next_stop_name}'"
                ),
                parameters={
                    "plan_action":   "LOCAL_REPAIR",
                    "scope":         "POI",
                    "justification": "minor_disruption_local_repair_sufficient",
                    "cause":         "planning_repair",
                },
            )

        # ── Rule 4: NO_CHANGE (scope POI) ────────────────────────────────────
        return AgentAction(
            action_type=ActionType.NO_ACTION,
            reasoning="PlanningAgent: NO_CHANGE at POI scope — no_violation_detected",
            parameters={
                "plan_action":   "NO_CHANGE",
                "scope":         "POI",
                "justification": "no_violation_detected",
            },
        )
