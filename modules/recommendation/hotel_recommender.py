"""
modules/recommendation/hotel_recommender.py
---------------------------------------------
Resolution 4: Unified SC pipeline applied to hotel recommendations.

Previous behaviour: LLM-only ranking.
Current behaviour:
  1. HC filter via constraint_registry (budget, availability, accessibility, star rating)
  2. SC scoring via satisfaction.py (Eq 1 → 2 → 4) → S_pti per hotel
  3. Sort descending by S_pti
  4. LLM: explanation / preference extraction ONLY (not primary ranking)
  5. Like/pass rerank on final list

LLM no longer drives ordering — ICDM Spti is the primary sort key.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from schemas.constraints import ConstraintBundle
from modules.tool_usage.hotel_tool import HotelRecord
from modules.recommendation.base_recommender import BaseRecommender
from modules.optimization.constraint_registry import evaluate_hc
from modules.optimization.satisfaction import evaluate_satisfaction
import config


@dataclass
class ScoredHotel:
    hotel: HotelRecord
    S_pti: float
    HC: int
    SC: float


class HotelRecommender(BaseRecommender):

    def recommend(
        self,
        constraints: ConstraintBundle,
        real_time_data: list[HotelRecord],
        history_insights: dict[str, Any],
        context: dict | None = None,
    ) -> list[HotelRecord]:
        """
        Resolution 4: HC filter → SC sort → LLM explanation only.

        Args:
            context: Runtime context for HC evaluation. Expected keys:
                     nightly_budget, requires_wheelchair, min_star_rating.
                     Defaults to constraint values if not supplied.
        """
        if not real_time_data:
            return []

        ctx = self._build_context(constraints, context or {})
        scored = [self._score_hotel(h, ctx) for h in real_time_data]

        # Sort by S_pti descending (ICDM primary ranking — Resolution 4)
        scored.sort(key=lambda x: x.S_pti, reverse=True)
        ranked = [s.hotel for s in scored]

        # LLM: explanation / preference note only (not reordering)
        prompt = self._build_prompt(constraints, ranked, history_insights)
        _ = self._call_llm(prompt)   # TODO: parse LLM output for preference extraction

        return ranked

    def rerank(self, items: list[HotelRecord], feedback: dict[str, str]) -> list[HotelRecord]:
        """Like/pass rerank applied AFTER S_pti ordering."""
        liked   = [h for h in items if feedback.get(h.name) == "like"]
        neutral = [h for h in items if h.name not in feedback]
        passed  = [h for h in items if feedback.get(h.name) == "pass"]
        return liked + neutral + passed

    # ── Internal ──────────────────────────────────────────────────────────────

    def _score_hotel(self, hotel: HotelRecord, ctx: dict) -> ScoredHotel:
        """Compute S_pti for a hotel via HC registry + satisfaction chain."""
        poi_data = {
            "price_per_night":       hotel.price_per_night,
            "available":             hotel.available,
            "wheelchair_accessible": hotel.wheelchair_accessible,
            "star_rating":           hotel.star_rating,
        }
        hard_results = evaluate_hc("hotel", poi_data, ctx)

        # SC 1: normalized star rating ∈ [0,1]
        sc1 = min(hotel.star_rating / 5.0, 1.0)

        # SC 2: amenity match ∈ [0,1]
        # Score = fraction of requested amenities available at this hotel.
        # If no amenity preferences are specified, defaults to neutral 0.5.
        requested: list[str] = ctx.get("preferred_amenities", [])
        if requested:
            hotel_amenities = {a.lower() for a in hotel.amenities}
            matched = sum(
                1 for req in requested
                if any(req.lower() in a or a in req.lower() for a in hotel_amenities)
            )
            sc2 = matched / len(requested)
        else:
            sc2 = 0.5  # no preference → neutral

        # SC 3: value-for-money — how much of the nightly budget is saved ∈ [0,1]
        nightly_bgt = ctx.get("nightly_budget", 0.0)
        if nightly_bgt and nightly_bgt > 0:
            effective_price = hotel.price_per_night * (1 - hotel.discount_pct / 100.0)
            sc3 = max(0.0, min(1.0, 1.0 - effective_price / nightly_bgt))
        else:
            sc3 = 0.5  # no budget context → neutral

        # Weights: star rating (0.50), amenity match (0.30), value-for-money (0.20)
        sc_vals = [sc1, sc2, sc3]
        sc_wts  = [0.50, 0.30, 0.20]
        result  = evaluate_satisfaction(hard_results, sc_vals, sc_wts,
                                        method=config.SC_AGGREGATION_METHOD)
        return ScoredHotel(hotel=hotel, S_pti=result["S"], HC=result["HC"], SC=result["SC"])

    @staticmethod
    def _build_context(constraints: ConstraintBundle, extra: dict) -> dict:
        return {
            "nightly_budget":      extra.get("nightly_budget", float("inf")),
            "requires_wheelchair": extra.get(
                "requires_wheelchair", constraints.hard.requires_wheelchair
            ),
            "min_star_rating":     extra.get("min_star_rating", 0),
            "preferred_amenities": extra.get("preferred_amenities", []),
        }

    @staticmethod
    def _build_prompt(constraints, hotels, history):
        names = [h.name for h in hotels[:5]]
        return (
            f"Hotels in {constraints.hard.destination_city} ranked by ICDM Spti: {names}\n"
            f"User preferences: {constraints.soft}\nHistory: {history}\n"
            f"TODO: MISSING — extract preference notes from LLM response."
        )
