"""
modules/recommendation/base_recommender.py
-------------------------------------------
Abstract base class for all recommenders in the Recommendation Module.
Each specific recommender (Budget, City, Flight, etc.) inherits from this.

Design note: The interface is intentionally minimal — exact input/output schemas
are MISSING from the architecture document and must be filled in per recommender.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from schemas.constraints import ConstraintBundle


class BaseRecommender(ABC):
    """
    Abstract recommender.
    All concrete recommenders must implement `recommend()` and `rerank()`.
    """

    def __init__(self, llm_client: Any = None):
        """
        Args:
            llm_client: An initialized LLM client instance.
                        TODO: MISSING — LLM provider/model not specified in architecture doc.
                        Pass an object with a `.complete(prompt: str) -> str` interface.
        """
        self.llm_client = llm_client

    @abstractmethod
    def recommend(
        self,
        constraints: ConstraintBundle,
        real_time_data: list[Any],
        history_insights: dict[str, Any],
    ) -> list[Any]:
        """
        Generate personalized recommendations.

        Args:
            constraints:     Bundled hard + soft + commonsense constraints.
            real_time_data:  Data from Tool-usage Module (e.g., AttractionRecord list).
            history_insights: Memory Module output for this user.

        Returns:
            Ordered list of recommendation records.

        TODO: MISSING — exact input/output schemas per recommender type.
        """
        ...

    @abstractmethod
    def rerank(self, items: list[Any], feedback: dict[str, str]) -> list[Any]:
        """
        Re-rank recommendations based on user behavioral feedback.

        Args:
            items:    Current ordered recommendation list.
            feedback: Map of item_id → "like" | "pass".
                      TODO: MISSING — feedback schema not specified in architecture doc.

        Returns:
            Re-ranked list of recommendation records.
        """
        ...

    def _call_llm(self, prompt: str) -> str:
        """
        Wrapper around the LLM client call.
        Raises NotImplementedError if llm_client is not configured.
        """
        if self.llm_client is None:
            raise NotImplementedError(
                "MISSING: llm_client is not configured. "
                "Pass an LLM client to the recommender constructor."
            )
        return self.llm_client.complete(prompt)
