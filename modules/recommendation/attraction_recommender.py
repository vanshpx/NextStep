"""
modules/recommendation/attraction_recommender.py
-------------------------------------------------
Personalized attraction recommendations.
Implements the full Stage 3 workflow from the architecture doc (Figure 3 flow):
  1. Use hard constraints to filter real-time data.
  2. Retrieve history insights from Memory Module (passed in).
  3. Call LLM to synthesize and rank attractions.
  4. Accept user feedback → rerank.
  5. Return finalized attraction set for Route Planner.

TODO (MISSING from architecture doc):
  - LLM prompt template for attraction recommendation
  - Feedback schema (like/pass → numeric signal mapping)
  - Output schema passed to Route Planner
"""

from __future__ import annotations
from typing import Any
from schemas.constraints import ConstraintBundle
from modules.tool_usage.attraction_tool import AttractionRecord
from modules.recommendation.base_recommender import BaseRecommender


class AttractionRecommender(BaseRecommender):
    """Recommends and re-ranks attractions using LLM + real-time data + memory."""

    def recommend(
        self,
        constraints: ConstraintBundle,
        real_time_data: list[AttractionRecord],
        history_insights: dict[str, Any],
    ) -> list[AttractionRecord]:
        """
        Generate personalized attraction list.

        Args:
            constraints:      Bundled constraint types.
            real_time_data:   Attractions from AttractionTool.fetch().
            history_insights: Soft/commonsense context from Memory Module.

        Returns:
            Ordered list of AttractionRecord (most to least recommended).

        TODO: MISSING — LLM prompt template.
        TODO: MISSING — scoring/ranking logic beyond LLM output.
        """
        if not real_time_data:
            return []

        # Build LLM prompt
        # TODO: MISSING — exact prompt structure not defined in architecture doc.
        prompt = self._build_prompt(constraints, real_time_data, history_insights)
        llm_response = self._call_llm(prompt)

        # TODO: MISSING — parse LLM response into ordered AttractionRecord list.
        # Placeholder: return real_time_data in original order until LLM parsing is implemented.
        _ = llm_response  # suppress unused warning until implemented
        return real_time_data

    def rerank(
        self,
        items: list[AttractionRecord],
        feedback: dict[str, str],
    ) -> list[AttractionRecord]:
        """
        Re-rank based on user like/pass feedback.

        Args:
            items:    Current recommendation list.
            feedback: {attraction_name: "like" | "pass"}.
                      TODO: MISSING — feedback schema (name vs id, signal values).

        Returns:
            Re-ranked list: liked items first, passed items last.
        """
        liked = [a for a in items if feedback.get(a.name) == "like"]
        passed = [a for a in items if feedback.get(a.name) == "pass"]
        neutral = [a for a in items if a.name not in feedback]
        return liked + neutral + passed

    @staticmethod
    def _build_prompt(
        constraints: ConstraintBundle,
        attractions: list[AttractionRecord],
        history: dict[str, Any],
    ) -> str:
        """
        Construct LLM prompt for attraction recommendation.

        TODO: MISSING — actual prompt template from architecture doc.
              The template below is a structural placeholder.
        """
        names = [a.name for a in attractions]
        return (
            f"You are a travel expert. Recommend and rank the following attractions "
            f"for a trip to {constraints.hard.destination_city}.\n"
            f"Attractions available: {names}\n"
            f"User preferences: {constraints.soft.interests}\n"
            f"Historical insights: {history}\n"
            f"Return a ranked list, most recommended first.\n"
            f"TODO: MISSING — refine this prompt with the actual template."
        )
