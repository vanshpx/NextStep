"""
modules/reoptimization/agents/disruption_agent.py
----------------------------------------------------
DisruptionAgent — classifies disruption severity and decides interaction
strategy.  It does NOT change the itinerary, defer automatically, or
reorder the schedule.

Severity levels returned:
  LOW    → IGNORE      (below threshold, no user-facing impact)
  MEDIUM → ASK_USER    (ambiguous, let user choose)
  HIGH   → ASK_USER    (significant, always surface to user)

The severity-to-ActionType mapping consumed by ExecutionLayer:
  IGNORE   → NO_ACTION
  ASK_USER → REQUEST_USER_DECISION
  DEFER    → DEFER_POI
  REPLACE  → REPLACE_POI
"""

from __future__ import annotations

from modules.reoptimization.agents.base_agent import BaseAgent, AgentContext
from modules.reoptimization.agent_action import ActionType, AgentAction


class DisruptionAgent(BaseAgent):
    """Specialist for crowd / weather / traffic disruptions."""

    AGENT_NAME = "DisruptionAgent"

    SYSTEM_PROMPT = """\
You are DisruptionAgent.

You do NOT change itinerary.
You do NOT defer automatically.
You do NOT reorder schedule.

You classify disruption severity and decide interaction strategy.

Disruption levels:
- LOW
- MEDIUM
- HIGH

Allowed actions:
- IGNORE
- ASK_USER
- DEFER
- REPLACE

Rules:
- If severity HIGH → ASK_USER
- If MEDIUM → ASK_USER
- If LOW → IGNORE

Return STRICT JSON:

{
  "disruption_level": "<LOW|MEDIUM|HIGH>",
  "action": "<IGNORE|ASK_USER|DEFER|REPLACE>",
  "confidence": <0-1>
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
    HC_UNSAFE_WEATHER: float = 0.75
    HIGH_VALUE_CUTOFF: float = 0.65

    # Severity boundaries
    # LOW  = reading is within threshold or barely above
    # MEDIUM = clearly above threshold but not HC-unsafe
    # HIGH = HC-unsafe territory or extreme readings
    _HIGH_CROWD:   float = 0.85   # crowd ≥ 85 % → HIGH
    _HIGH_TRAFFIC:  float = 0.80   # traffic ≥ 80 % → HIGH

    # ── ActionType map from strategy labels ───────────────────────────────────
    _ACTION_MAP: dict[str, ActionType] = {
        "IGNORE":   ActionType.NO_ACTION,
        "ASK_USER": ActionType.REQUEST_USER_DECISION,
        "DEFER":    ActionType.DEFER_POI,
        "REPLACE":  ActionType.REPLACE_POI,
    }

    def evaluate(self, context: AgentContext) -> AgentAction:
        obs = context.observation

        # ── Weather ───────────────────────────────────────────────────────────
        action = self._check_weather(obs)
        if action:
            return action

        # ── Crowd ─────────────────────────────────────────────────────────────
        action = self._check_crowd(obs)
        if action:
            return action

        # ── Traffic ───────────────────────────────────────────────────────────
        action = self._check_traffic(obs)
        if action:
            return action

        # ── No disruption ─────────────────────────────────────────────────────
        return AgentAction(
            action_type=ActionType.NO_ACTION,
            reasoning="DisruptionAgent: no threshold exceeded",
            parameters={
                "disruption_level": "LOW",
                "action":           "IGNORE",
                "confidence":       1.0,
            },
        )

    # ── Private evaluators ────────────────────────────────────────────────────

    def _classify_weather(self, obs) -> str:
        """Return LOW / MEDIUM / HIGH for weather."""
        if obs.weather_severity >= self.HC_UNSAFE_WEATHER:
            return "HIGH"
        if (obs.thresholds is not None
                and obs.weather_severity > obs.thresholds.weather):
            return "MEDIUM"
        return "LOW"

    def _classify_crowd(self, obs) -> str:
        """Return LOW / MEDIUM / HIGH for crowd."""
        if obs.crowd_level is None:
            return "LOW"
        if obs.crowd_level >= self._HIGH_CROWD:
            return "HIGH"
        if (obs.thresholds is not None
                and obs.crowd_level > obs.thresholds.crowd):
            return "MEDIUM"
        return "LOW"

    def _classify_traffic(self, obs) -> str:
        """Return LOW / MEDIUM / HIGH for traffic."""
        if obs.traffic_level is None:
            return "LOW"
        if obs.traffic_level >= self._HIGH_TRAFFIC:
            return "HIGH"
        if (obs.thresholds is not None
                and obs.traffic_level > obs.thresholds.traffic):
            return "MEDIUM"
        return "LOW"

    def _check_weather(self, obs) -> AgentAction | None:
        if obs.weather_severity <= 0 or obs.thresholds is None:
            return None
        if obs.weather_severity <= obs.thresholds.weather:
            return None

        stop = obs.next_stop_name
        if not stop:
            return None

        level = self._classify_weather(obs)

        # HIGH → ASK_USER  (weather is HC-unsafe; outdoor stops need REPLACE
        # but we surface to user first)
        if level == "HIGH":
            # For outdoor stops the downstream action would be REPLACE;
            # for indoor stops it's safe — but still surface to user.
            action_label = "ASK_USER"
            confidence   = 0.95
            if obs.next_stop_is_outdoor:
                action_label = "ASK_USER"
                confidence   = 0.98
            return AgentAction(
                action_type=ActionType.REQUEST_USER_DECISION,
                target_poi=stop,
                reasoning=(
                    f"Weather severity {obs.weather_severity:.0%} >= HC unsafe "
                    f"threshold — outdoor stop '{stop}' at risk"
                ),
                parameters={
                    "disruption_level": level,
                    "action":           action_label,
                    "confidence":       confidence,
                    "cause":            "weather_unsafe",
                    "severity":         obs.weather_severity,
                    "category_hint":    "indoor" if obs.next_stop_is_outdoor else "",
                },
            )

        # MEDIUM → ASK_USER
        if obs.next_stop_is_outdoor:
            return AgentAction(
                action_type=ActionType.REQUEST_USER_DECISION,
                target_poi=stop,
                reasoning=(
                    f"Weather {obs.weather_condition} (severity "
                    f"{obs.weather_severity:.0%}) > threshold "
                    f"{obs.thresholds.weather:.0%} — outdoor '{stop}' affected"
                ),
                parameters={
                    "disruption_level": level,
                    "action":           "ASK_USER",
                    "confidence":       0.80,
                    "cause":            "weather",
                    "severity":         obs.weather_severity,
                    "condition":        obs.weather_condition or "",
                },
            )
        return None

    def _check_crowd(self, obs) -> AgentAction | None:
        if obs.crowd_level is None or obs.thresholds is None:
            return None
        if obs.crowd_level <= obs.thresholds.crowd:
            return None

        stop = obs.next_stop_name
        if not stop:
            return None

        level = self._classify_crowd(obs)

        # HIGH or MEDIUM → ASK_USER
        return AgentAction(
            action_type=ActionType.REQUEST_USER_DECISION,
            target_poi=stop,
            reasoning=(
                f"Crowd {obs.crowd_level:.0%} > threshold "
                f"{obs.thresholds.crowd:.0%} at '{stop}' "
                f"(S_pti={obs.next_stop_spti_proxy:.2f} — "
                f"{'HIGH' if level == 'HIGH' else 'MEDIUM'} severity)"
            ),
            parameters={
                "disruption_level": level,
                "action":           "ASK_USER",
                "confidence":       0.90 if level == "HIGH" else 0.75,
                "cause":            "crowd",
                "crowd_level":      obs.crowd_level,
                "spti_proxy":       obs.next_stop_spti_proxy,
            },
        )

    def _check_traffic(self, obs) -> AgentAction | None:
        if obs.traffic_level is None or obs.thresholds is None:
            return None
        if obs.traffic_level <= obs.thresholds.traffic:
            return None

        stop = obs.next_stop_name
        if not stop:
            return None

        level = self._classify_traffic(obs)

        # HIGH or MEDIUM → ASK_USER
        return AgentAction(
            action_type=ActionType.REQUEST_USER_DECISION,
            target_poi=stop,
            reasoning=(
                f"Traffic {obs.traffic_level:.0%} > threshold "
                f"{obs.thresholds.traffic:.0%} — "
                f"{'HIGH' if level == 'HIGH' else 'MEDIUM'} severity at '{stop}'"
            ),
            parameters={
                "disruption_level": level,
                "action":           "ASK_USER",
                "confidence":       0.90 if level == "HIGH" else 0.70,
                "cause":            "traffic",
                "traffic_level":    obs.traffic_level,
                "delay_minutes":    obs.traffic_delay_minutes,
            },
        )
