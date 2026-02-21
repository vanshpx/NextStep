"""
modules/recommendation/restaurant_recommender.py
-------------------------------------------------
Resolution 4: Unified SC pipeline applied to restaurant recommendations.

Previous: dietary filter → LLM ranking.
Current:
  1. HC filter via constraint_registry (dietary, opening hours, price, accessibility)
  2. SC score via satisfaction.py → S_pti per restaurant
  3. Sort descending by S_pti
  4. LLM: explanation / preference extraction only
  5. Like/pass rerank
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any
from schemas.constraints import ConstraintBundle
from modules.tool_usage.restaurant_tool import RestaurantRecord
from modules.recommendation.base_recommender import BaseRecommender
from modules.optimization.constraint_registry import evaluate_hc
from modules.optimization.satisfaction import evaluate_satisfaction
import config


@dataclass
class ScoredRestaurant:
    restaurant: RestaurantRecord
    S_pti: float
    HC: int
    SC: float


class RestaurantRecommender(BaseRecommender):

    def recommend(
        self,
        constraints: ConstraintBundle,
        real_time_data: list[RestaurantRecord],
        history_insights: dict[str, Any],
        context: dict | None = None,
    ) -> list[RestaurantRecord]:
        """
        Resolution 4: HC filter → SC sort → LLM explanation only.
        """
        if not real_time_data:
            return []

        ctx = self._build_context(constraints, context or {})
        scored = [self._score_restaurant(r, ctx) for r in real_time_data]
        scored.sort(key=lambda x: x.S_pti, reverse=True)
        ranked = [s.restaurant for s in scored]

        prompt = self._build_prompt(constraints, ranked, history_insights)
        _ = self._call_llm(prompt)   # TODO: parse preference notes from LLM
        return ranked

    def rerank(self, items: list[RestaurantRecord], feedback: dict[str, str]) -> list[RestaurantRecord]:
        liked   = [r for r in items if feedback.get(r.name) == "like"]
        neutral = [r for r in items if r.name not in feedback]
        passed  = [r for r in items if feedback.get(r.name) == "pass"]
        return liked + neutral + passed

    # ── Internal ──────────────────────────────────────────────────────────────

    def _score_restaurant(self, restaurant: RestaurantRecord, ctx: dict) -> ScoredRestaurant:
        poi_data = {
            "cuisine_type":          restaurant.cuisine_type,
            "cuisine_tags":          restaurant.cuisine_tags,
            "opening_hours":         restaurant.opening_hours,
            "avg_price_per_person":  restaurant.avg_price_per_person,
            "wheelchair_accessible": restaurant.wheelchair_accessible,
        }
        hard_results = evaluate_hc("restaurant", poi_data, ctx)

        # SC 1: normalized rating ∈ [0,1]
        sc1 = min(restaurant.rating / 5.0, 1.0) if restaurant.rating else 0.5

        # SC 2: cuisine / dietary preference match ∈ {0.2, 0.5, 1.0}
        user_prefs: set[str] = ctx.get("dietary_preferences", set())
        if user_prefs:
            all_tags = {t.lower() for t in restaurant.cuisine_tags} | {restaurant.cuisine_type.lower()}
            matched = any(
                any(p.lower() in tag or tag in p.lower() for tag in all_tags)
                for p in user_prefs
            )
            sc2 = 1.0 if matched else 0.2
        else:
            sc2 = 0.5  # no preference → neutral

        # SC 3: reservation availability bonus ∈ {0.5, 1.0}
        # Prefers restaurants where reservations can be made (more reliable)
        sc3 = 1.0 if restaurant.accepts_reservations else 0.5

        # Weights: rating (0.50), cuisine match (0.35), reservation (0.15)
        sc_vals = [sc1, sc2, sc3]
        sc_wts  = [0.50, 0.35, 0.15]
        result  = evaluate_satisfaction(hard_results, sc_vals, sc_wts,
                                        method=config.SC_AGGREGATION_METHOD)
        return ScoredRestaurant(
            restaurant=restaurant, S_pti=result["S"],
            HC=result["HC"], SC=result["SC"]
        )

    @staticmethod
    def _build_context(constraints: ConstraintBundle, extra: dict) -> dict:
        hard = constraints.hard
        soft = constraints.soft
        # Combine restaurant_preference (hard form field) + dietary_preferences (soft)
        prefs: set[str] = set()
        if hard.restaurant_preference:
            prefs.add(hard.restaurant_preference)
        prefs.update(soft.dietary_preferences)
        return {
            "dietary_preferences": extra.get("dietary_preferences", prefs),
            "t_cur":               extra.get("t_cur", dtime(12, 0)),
            "per_meal_budget":     extra.get("per_meal_budget", float("inf")),
            "requires_wheelchair": extra.get(
                "requires_wheelchair", hard.requires_wheelchair
            ),
        }

    @staticmethod
    def _build_prompt(constraints, restaurants, history):
        names = [r.name for r in restaurants[:5]]
        return (
            f"Restaurants in {constraints.hard.destination_city} ranked by ICDM Spti: {names}\n"
            f"Preference: {constraints.hard.restaurant_preference}\nHistory: {history}\n"
            f"TODO: MISSING — refine prompt and parse LLM preference notes."
        )
