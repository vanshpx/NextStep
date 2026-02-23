"""
modules/recommendation/city_recommender.py
-------------------------------------------
Recommends the best destination city when the user has not specified one,
or ranks multiple candidate cities.

TODO (MISSING from architecture doc):
  - Whether this recommender is invoked pre-trip or is destination always given.
  - LLM prompt template.
"""

from __future__ import annotations
from typing import Any
from schemas.constraints import ConstraintBundle
from modules.recommendation.base_recommender import BaseRecommender


class CityRecommender(BaseRecommender):

    def recommend(
        self,
        constraints: ConstraintBundle,
        real_time_data: list[Any],   # list of city name strings or CityRecord objects
        history_insights: dict[str, Any],
    ) -> list[Any]:
        """
        Rank candidate cities based on user preferences and history.

        TODO: MISSING — input schema (city strings vs CityRecord objects).
        TODO: MISSING — LLM prompt template.
        Placeholder: returns real_time_data unchanged.
        """
        if not real_time_data:
            return []
        prompt = self._build_prompt(constraints, real_time_data, history_insights)
        llm_response = self._call_llm(prompt)
        _ = llm_response  # TODO: parse LLM ranking
        return real_time_data

    def rerank(self, items: list[Any], feedback: dict[str, str]) -> list[Any]:
        """TODO: MISSING — feedback schema for city recommendation."""
        return items

    @staticmethod
    def _build_prompt(constraints, cities, history):
        return (
            f"Recommend destination cities given:\n"
            f"User interests: {constraints.soft.interests}\n"
            f"Departure: {constraints.hard.departure_city}\n"
            f"Candidates: {cities}\nHistory: {history}\n"
            f"TODO: MISSING — refine prompt."
        )
