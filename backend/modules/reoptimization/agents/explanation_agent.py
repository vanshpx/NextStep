"""modules/reoptimization/agents/explanation_agent.py
----------------------------------------------------
ExplanationAgent — explains decisions in 2-4 concise sentences.

Does NOT modify the itinerary.  Always returns NO_ACTION with an
``explanation`` string in ``parameters``.
"""

from __future__ import annotations

from modules.reoptimization.agents.base_agent import BaseAgent, AgentContext
from modules.reoptimization.agent_action import ActionType, AgentAction


class ExplanationAgent(BaseAgent):
    """Specialist for generating concise decision explanations."""

    AGENT_NAME = "ExplanationAgent"

    SYSTEM_PROMPT = """\
You are ExplanationAgent.

Explain decision in 2-4 concise sentences.
Do NOT invent facts.
Use only provided state.

Return STRICT JSON:

{
  "explanation": "<text>"
}

You must NOT:
- Generate itinerary content
- Change schedule directly
- Assume city data
- Invent coordinates
- Create new POIs
- Override deterministic constraints

Return JSON only.
If output is not valid JSON, it will be rejected."""

    # ------------------------------------------------------------------
    # evaluate  — build explanation from observation, always NO_ACTION
    # ------------------------------------------------------------------
    def evaluate(self, context: AgentContext) -> AgentAction:
        obs = context.observation
        explanation = _build_explanation(obs)
        return AgentAction(
            action_type=ActionType.NO_ACTION,
            reasoning=f"ExplanationAgent: {explanation}",
            parameters={"explanation": explanation},
        )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _build_explanation(obs) -> str:
    """Compose 2-4 sentences from observation state — no invented facts."""
    sentences: list[str] = []

    # Sentence 1 — time / remaining stops
    stop_count = len(obs.remaining_stops) if obs.remaining_stops else 0
    sentences.append(
        f"At {obs.current_time} with {obs.remaining_minutes} min remaining "
        f"and {stop_count} stop(s) left"
    )

    # Sentence 2 — next stop context (if any)
    if obs.next_stop_name:
        kind = "outdoor" if obs.next_stop_is_outdoor else "indoor"
        sentences.append(
            f"Next stop is '{obs.next_stop_name}' ({kind}, "
            f"S_pti={obs.next_stop_spti_proxy:.2f})"
        )

    # Sentence 3 — disruptions / environment
    env_parts: list[str] = []
    if obs.disruptions_today > 0:
        env_parts.append(f"{obs.disruptions_today} disruption(s) today")
    if obs.crowd_level is not None and obs.crowd_level > 0:
        env_parts.append(f"crowd {obs.crowd_level:.0%}")
    if obs.weather_condition:
        env_parts.append(
            f"{obs.weather_condition} (severity {obs.weather_severity:.0%})"
        )
    if obs.traffic_level is not None and obs.traffic_level > 0:
        env_parts.append(f"traffic {obs.traffic_level:.0%}")
    if env_parts:
        sentences.append("Environment: " + ", ".join(env_parts))

    # Sentence 4 — budget snapshot (only when meaningful)
    total_budget = getattr(obs.budget, "total", 0) if obs.budget else 0
    total_spent = sum(obs.budget_spent.values()) if isinstance(obs.budget_spent, dict) else 0
    if total_budget > 0 and total_spent > 0:
        pct = total_spent / total_budget * 100
        sentences.append(f"Budget: {pct:.0f}% spent")

    return ". ".join(sentences) + "."
