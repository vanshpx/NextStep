"""
modules/reoptimization/agents/memory_agent.py
-----------------------------------------------
MemoryAgent — determines whether the current interaction should
update long-term memory.

Returns {store, memory_type, reason} — never modifies state directly.
"""

from __future__ import annotations

from modules.reoptimization.agents.base_agent import BaseAgent, AgentContext
from modules.reoptimization.agent_action import ActionType, AgentAction


# ── Constants ─────────────────────────────────────────────────────────────
_LONG_TERM_DISRUPTION_THRESHOLD: int = 3  # ≥3 disruptions → store long-term
_SHORT_TERM_DISRUPTION_THRESHOLD: int = 1  # 1–2 disruptions → short-term only


class MemoryAgent(BaseAgent):
    """Specialist for memory-update decisions (read-only — never mutates state)."""

    AGENT_NAME = "MemoryAgent"

    SYSTEM_PROMPT = """\
You are MemoryAgent.

Determine whether current interaction
should update long-term memory.

Return STRICT JSON:

{
  "store": true|false,
  "memory_type": "short_term|long_term|null",
  "reason": "<short_reason>"
}

No narrative text.

You must NOT:
- Generate itinerary content
- Change schedule directly
- Assume city data
- Invent coordinates
- Create new POIs
- Override deterministic constraints

Return JSON only.
If output is not valid JSON, it will be rejected."""

    def evaluate(self, context: AgentContext) -> AgentAction:
        obs = context.observation
        disruptions = obs.disruptions_today

        # ── ≥3 disruptions → long-term store (recurring pattern) ─────────────
        if disruptions >= _LONG_TERM_DISRUPTION_THRESHOLD:
            return AgentAction(
                action_type=ActionType.NO_ACTION,
                reasoning=(
                    f"MemoryAgent: {disruptions} disruptions — "
                    f"storing long-term pattern"
                ),
                parameters={
                    "store":       True,
                    "memory_type": "long_term",
                    "reason":      (
                        f"{disruptions} disruptions today; "
                        f"recurring pattern warrants long-term storage"
                    ),
                },
            )

        # ── 1–2 disruptions → short-term only ─────────────────────────────
        if disruptions >= _SHORT_TERM_DISRUPTION_THRESHOLD:
            return AgentAction(
                action_type=ActionType.NO_ACTION,
                reasoning=(
                    f"MemoryAgent: {disruptions} disruption(s) — "
                    f"short-term note"
                ),
                parameters={
                    "store":       True,
                    "memory_type": "short_term",
                    "reason":      (
                        f"{disruptions} disruption(s); "
                        f"noted in short-term memory"
                    ),
                },
            )

        # ── 0 disruptions → no store needed ────────────────────────────────
        return AgentAction(
            action_type=ActionType.NO_ACTION,
            reasoning="MemoryAgent: session clean — no memory update needed",
            parameters={
                "store":       False,
                "memory_type": None,
                "reason":      "no disruptions; nothing to store",
            },
        )
