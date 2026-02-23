"""
modules/recommendation/budget_recommender.py
---------------------------------------------
Generates a preliminary budget estimate using LLMs.
Called in Stage 2 before the Budget Planner distributes funds.

TODO (MISSING from architecture doc):
  - LLM prompt template
  - Output format (structured dict vs. free text)
  - Currency unit
"""

from __future__ import annotations
from typing import Any
from schemas.constraints import ConstraintBundle
from schemas.itinerary import BudgetAllocation
from modules.recommendation.base_recommender import BaseRecommender
import config


class BudgetRecommender(BaseRecommender):
    """Generates a preliminary budget estimate via LLM."""

    def recommend(
        self,
        constraints: ConstraintBundle,
        real_time_data: list[Any],   # typically empty or price data for budget stage
        history_insights: dict[str, Any],
    ) -> list[BudgetAllocation]:
        """
        Generate a preliminary budget estimate.

        Returns:
            List with a single BudgetAllocation (preliminary estimate).
            TODO: MISSING — output format may differ from BudgetAllocation.
        """
        prompt = self._build_prompt(constraints, history_insights)
        llm_response = self._call_llm(prompt)

        # TODO: MISSING — parse LLM response into BudgetAllocation values.
        # Placeholder: return a zero-valued allocation until parsing is implemented.
        _ = llm_response
        preliminary = BudgetAllocation()  # all zeros until LLM parsing is wired
        return [preliminary]

    def rerank(self, items: list[Any], feedback: dict[str, str]) -> list[Any]:
        """Not applicable for budget recommendation. Returns items unchanged."""
        return items

    @staticmethod
    def _build_prompt(constraints: ConstraintBundle, history: dict[str, Any]) -> str:
        """
        TODO: MISSING — actual prompt template.
        Placeholder for LLM budget estimation prompt.
        """
        return (
            f"Estimate a travel budget for a trip from {constraints.hard.departure_city} "
            f"to {constraints.hard.destination_city}.\n"
            f"Dates: {constraints.hard.departure_date} to {constraints.hard.return_date}\n"
            f"Group: {constraints.hard.num_adults} adults, {constraints.hard.num_children} children.\n"
            f"Currency: {config.CURRENCY_UNIT}\n"
            f"Historical spending power: {constraints.soft.spending_power}\n"
            f"Distribute across: Accommodation, Attractions, Restaurants, Transportation, "
            f"Other_Expenses, Reserve_Fund.\n"
            f"TODO: MISSING — refine prompt with actual template."
        )
