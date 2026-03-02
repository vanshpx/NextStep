"""
modules/reoptimization/agents/preference_agent.py
----------------------------------------------------
PreferenceAgent — extracts structured preference constraints.

Does NOT infer missing attributes.  Does NOT assume preferences.
Returns {interests, pace_preference, environment_tolerance} extracted
from the event + observation context.
"""

from __future__ import annotations
from typing import Optional

from modules.reoptimization.agents.base_agent import BaseAgent, AgentContext
from modules.reoptimization.agent_action import ActionType, AgentAction


# ── Event→pace mapping ───────────────────────────────────────────────────────
_PACE_MAP: dict[str, str] = {
    "slower":   "relaxed",
    "faster":   "fast",
    "relaxed":  "relaxed",
    "fast":     "fast",
    "balanced": "balanced",
}

# ── Tolerance keyword helpers ─────────────────────────────────────────────────
_VALID_TOLERANCE_LEVELS = frozenset({"low", "medium", "high"})


def _crowd_from_observation(obs) -> Optional[int]:
    """Extract crowd preference as 0–100 from observation, or None."""
    if obs.avoid_crowds:
        return 30          # low-crowd tolerance when user asked to avoid
    return None


def _weather_from_observation(obs) -> Optional[str]:
    """Map weather severity to tolerance label, or None."""
    if obs.weather_severity >= 0.75:
        return "low"       # unsafe weather → low tolerance
    if obs.weather_severity >= 0.4:
        return "medium"
    return None


def _traffic_from_observation(obs) -> Optional[str]:
    """Map traffic level to tolerance label, or None."""
    tl = obs.traffic_level
    if tl is not None and tl >= 0.70:
        return "low"
    if tl is not None and tl >= 0.40:
        return "medium"
    return None


class PreferenceAgent(BaseAgent):
    """Specialist for extracting structured preference constraints."""

    AGENT_NAME = "PreferenceAgent"

    SYSTEM_PROMPT = """\
You are PreferenceAgent.

Extract structured constraints from user message.

You do NOT infer missing attributes.
You do NOT assume preferences.

Return STRICT JSON:

{
  "interests": [<list>],
  "pace_preference": "<fast|balanced|relaxed|null>",
  "environment_tolerance": {
      "crowd": <0-100|null>,
      "weather": "<low|medium|high|null>",
      "traffic": "<low|medium|high|null>"
  }
}

If none detected:
{
  "interests": [],
  "pace_preference": null,
  "environment_tolerance": {}
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

    def evaluate(self, context: AgentContext) -> AgentAction:
        obs    = context.observation
        event  = context.event_type.lower().strip()
        params = context.parameters

        # ── Extract interests ─────────────────────────────────────────────────
        interests: list[str] = list(params.get("interests", []))

        # ── Extract pace_preference ───────────────────────────────────────────
        pace: Optional[str] = _PACE_MAP.get(event)
        if pace is None:
            pace = _PACE_MAP.get(
                str(params.get("pace", "")).lower().strip()
            )

        # ── Extract environment_tolerance ─────────────────────────────────────
        env_tol: dict = {}
        crowd_val = _crowd_from_observation(obs)
        if crowd_val is not None:
            env_tol["crowd"] = crowd_val
        weather_val = _weather_from_observation(obs)
        if weather_val is not None:
            env_tol["weather"] = weather_val
        traffic_val = _traffic_from_observation(obs)
        if traffic_val is not None:
            env_tol["traffic"] = traffic_val

        # ── Build extracted JSON payload ──────────────────────────────────────
        extracted = {
            "interests":             interests,
            "pace_preference":       pace,
            "environment_tolerance": env_tol if env_tol else {},
        }

        # ── Decide action type ────────────────────────────────────────────────
        has_change = bool(interests or pace or env_tol)

        if has_change:
            # Pace changed from current? → reoptimize
            old_pace = obs.pace_preference or "moderate"
            pace_actually_changed = pace is not None and pace != old_pace

            action = (
                ActionType.REOPTIMIZE_DAY
                if (pace_actually_changed or interests)
                else ActionType.NO_ACTION
            )
            reasoning_parts = []
            if pace is not None:
                reasoning_parts.append(
                    f"pace '{old_pace}' → '{pace}'" if pace_actually_changed
                    else f"pace already '{old_pace}'"
                )
            if interests:
                reasoning_parts.append(f"interests {interests}")
            if env_tol:
                reasoning_parts.append(f"env_tolerance {env_tol}")

            return AgentAction(
                action_type=action,
                reasoning=(
                    f"PreferenceAgent: {' | '.join(reasoning_parts)}"
                    + (" — no change" if action == ActionType.NO_ACTION else "")
                ),
                parameters=extracted,
            )

        # ── Nothing detected ──────────────────────────────────────────────────
        return AgentAction(
            action_type=ActionType.NO_ACTION,
            reasoning="PreferenceAgent: no preference change detected",
            parameters=extracted,
        )
