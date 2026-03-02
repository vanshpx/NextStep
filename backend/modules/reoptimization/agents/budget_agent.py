"""
modules/reoptimization/agents/budget_agent.py
-----------------------------------------------
BudgetAgent — evaluates financial state of the trip.

Classifies budget status as OK / OVERRUN / UNDERUTILIZED and
recommends one of three actions: NO_CHANGE, REBALANCE, SUGGEST_CHEAPER.
Never allocates money or changes categories directly.
"""

from __future__ import annotations

from modules.reoptimization.agents.base_agent import BaseAgent, AgentContext
from modules.reoptimization.agent_action import ActionType, AgentAction


# ── Budget‑status → ActionType mapping ────────────────────────────────────────
_STATUS_ACTION_MAP: dict[str, ActionType] = {
    "NO_CHANGE":       ActionType.NO_ACTION,
    "REBALANCE":       ActionType.RELAX_CONSTRAINT,
    "SUGGEST_CHEAPER": ActionType.REPLACE_POI,
}


class BudgetAgent(BaseAgent):
    """Specialist for budget evaluation (read-only — never mutates state)."""

    AGENT_NAME = "BudgetAgent"

    SYSTEM_PROMPT = """\
You are BudgetAgent.

You do NOT allocate money.
You do NOT change categories.
You only evaluate financial state.

Budget status:
- OK
- OVERRUN
- UNDERUTILIZED

Allowed actions:
- NO_CHANGE
- REBALANCE
- SUGGEST_CHEAPER

Return STRICT JSON:

{
  "budget_status": "<OK|OVERRUN|UNDERUTILIZED>",
  "action": "<NO_CHANGE|REBALANCE|SUGGEST_CHEAPER>",
  "variance_percentage": <number>
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

    # ── Thresholds ────────────────────────────────────────────────────────────
    OVERRUN_THRESHOLD:        float = 0.90   # ≥90 % spent → OVERRUN
    UNDERUTILIZED_THRESHOLD:  float = 0.40   # ≤40 % spent with ≥60 % time gone → UNDERUTILIZED
    TIME_PROGRESS_GATE:       float = 0.60   # need ≥60 % day elapsed to flag under-utilisation

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _variance_pct(spent: float, allocated: float) -> float:
        """Return signed variance: +ve = over, −ve = under."""
        if allocated <= 0:
            return 0.0
        return round((spent - allocated) / allocated * 100, 1)

    def _classify(self, spend_ratio: float, time_ratio: float
                  ) -> tuple[str, str]:
        """
        Classify budget state.

        Returns (budget_status, action).
        """
        if spend_ratio >= self.OVERRUN_THRESHOLD:
            return "OVERRUN", "SUGGEST_CHEAPER"

        if (time_ratio >= self.TIME_PROGRESS_GATE
                and spend_ratio <= self.UNDERUTILIZED_THRESHOLD):
            return "UNDERUTILIZED", "REBALANCE"

        return "OK", "NO_CHANGE"

    # ── Core evaluate ─────────────────────────────────────────────────────────

    def evaluate(self, context: AgentContext) -> AgentAction:
        obs = context.observation

        budget = obs.budget
        spent  = obs.budget_spent or {}

        if budget is None:
            return AgentAction(
                action_type=ActionType.NO_ACTION,
                reasoning="BudgetAgent: no budget allocation available",
                parameters={
                    "budget_status":      "OK",
                    "action":             "NO_CHANGE",
                    "variance_percentage": 0.0,
                },
            )

        # ── Compute totals ────────────────────────────────────────────────────
        total_budget = getattr(budget, "total", 0.0) or 0.0
        total_spent  = sum(spent.values())

        # Time progress: what fraction of the day's available minutes are gone
        remaining = getattr(obs, "remaining_minutes", 0) or 0
        total_day = getattr(obs, "total_day_minutes", 0) or 0
        time_ratio = 1.0 - (remaining / total_day) if total_day > 0 else 0.0

        spend_ratio = (total_spent / total_budget) if total_budget > 0 else 0.0

        # ── Classify ──────────────────────────────────────────────────────────
        status, action_label = self._classify(spend_ratio, time_ratio)
        variance = self._variance_pct(total_spent, total_budget)

        action_type = _STATUS_ACTION_MAP[action_label]

        # For SUGGEST_CHEAPER, point at the next stop as replacement target
        target = None
        if action_label == "SUGGEST_CHEAPER" and obs.remaining_stops:
            target = obs.next_stop_name or (
                obs.remaining_stops[0] if obs.remaining_stops else None
            )

        return AgentAction(
            action_type=action_type,
            target_poi=target,
            reasoning=(
                f"BudgetAgent: {status} — "
                f"₹{total_spent:,.0f} of ₹{total_budget:,.0f} used "
                f"({variance:+.1f}%)"
            ),
            parameters={
                "budget_status":      status,
                "action":             action_label,
                "variance_percentage": variance,
            },
        )