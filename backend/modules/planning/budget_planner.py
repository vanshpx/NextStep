"""
modules/planning/budget_planner.py
------------------------------------
Distributes the preliminary budget estimate (from BudgetRecommender) across
the six budget categories defined in the architecture doc.

Called in Stage 2 after user confirms the preliminary estimate.

Budget categories (from architecture doc):
  - Accommodation
  - Attractions
  - Restaurants
  - Transportation
  - Other_Expenses
  - Reserve_Fund

TODO (MISSING from architecture doc):
  - Distribution algorithm (equal split? percentage-based? LLM-driven?).
  - Min/max and percentage bounds per category.
  - Currency unit.
  - How commonsense constraints constrain the distribution.
"""

from __future__ import annotations
from typing import Any
from schemas.constraints import ConstraintBundle
from schemas.itinerary import BudgetAllocation
import config


class BudgetPlanner:
    """
    Re-evaluates the financial situation and distributes budget across categories.
    Adheres to commonsense knowledge and dynamic adjustments.
    """

    def __init__(self, llm_client: Any = None):
        """
        Args:
            llm_client: LLM client for dynamic adjustment reasoning.
                        TODO: MISSING — LLM provider not specified.
        """
        self.llm_client = llm_client

    def distribute(
        self,
        total_budget: float,
        constraints: ConstraintBundle,
        preliminary_estimate: BudgetAllocation | None = None,
    ) -> BudgetAllocation:
        """
        Distribute total_budget across all budget categories.

        Args:
            total_budget:         User-confirmed total budget amount.
            constraints:          Constraint bundle with hard/soft/commonsense.
            preliminary_estimate: Output from BudgetRecommender (optional refinement input).

        Returns:
            BudgetAllocation with values filled per category.

        TODO: MISSING — replace placeholder percentages with actual algorithm.
        TODO: MISSING — LLM dynamic adjustment call not wired (llm_client stub).
        TODO: MISSING — currency unit validation.
        """
        # ── Placeholder: naive percentage split ──────────────────────────────
        # TODO: MISSING — actual distribution ratios not specified in architecture doc.
        # The values below are assumptions only. Replace when specification is available.
        RATIOS: dict[str, float] = {
            "Accommodation":   0.35,   # TODO: MISSING — replace with actual ratio
            "Attractions":     0.15,   # TODO: MISSING
            "Restaurants":     0.20,   # TODO: MISSING
            "Transportation":  0.15,   # TODO: MISSING
            "Other_Expenses":  0.10,   # TODO: MISSING
            "Reserve_Fund":    0.05,   # TODO: MISSING
        }

        assert abs(sum(RATIOS.values()) - 1.0) < 1e-6, "Ratios must sum to 1.0"

        allocation = BudgetAllocation(
            Accommodation  = round(total_budget * RATIOS["Accommodation"], 2),
            Attractions    = round(total_budget * RATIOS["Attractions"], 2),
            Restaurants    = round(total_budget * RATIOS["Restaurants"], 2),
            Transportation = round(total_budget * RATIOS["Transportation"], 2),
            Other_Expenses = round(total_budget * RATIOS["Other_Expenses"], 2),
            Reserve_Fund   = round(total_budget * RATIOS["Reserve_Fund"], 2),
        )

        # TODO: If llm_client is configured, call LLM here for dynamic adjustment
        # based on constraints.soft.spending_power and commonsense_constraints.

        return allocation

    def validate(self, allocation: BudgetAllocation, total_budget: float) -> bool:
        """
        Check that allocated total does not exceed confirmed budget.

        Args:
            allocation:   The BudgetAllocation to validate.
            total_budget: The user-confirmed total budget.

        Returns:
            True if valid, False otherwise.
        """
        return allocation.total <= total_budget + 1e-2  # 1 cent tolerance for rounding
