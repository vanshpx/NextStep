"""
modules/recommendation/flight_recommender.py
---------------------------------------------
Resolution 4: Unified SC pipeline applied to flight recommendations.

Previous: cheapest-first sort + LLM stub.
Current:
  1. HC filter via constraint_registry (price, travel mode, departure window)
  2. SC score via satisfaction.py → S_pti per flight
  3. Sort descending by S_pti (replaces raw price sort)
  4. LLM: explanation / preference extraction only
  5. Like/pass rerank
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any
from schemas.constraints import ConstraintBundle
from modules.tool_usage.flight_tool import FlightRecord
from modules.recommendation.base_recommender import BaseRecommender
from modules.optimization.constraint_registry import evaluate_hc
from modules.optimization.satisfaction import evaluate_satisfaction
import config


@dataclass
class ScoredFlight:
    flight: FlightRecord
    S_pti: float
    HC: int
    SC: float


class FlightRecommender(BaseRecommender):

    def recommend(
        self,
        constraints: ConstraintBundle,
        real_time_data: list[FlightRecord],
        history_insights: dict[str, Any],
        context: dict | None = None,
    ) -> list[FlightRecord]:
        """
        Resolution 4: HC filter → SC sort → LLM explanation only.
        """
        if not real_time_data:
            return []

        ctx = self._build_context(constraints, context or {})
        scored = [self._score_flight(f, ctx) for f in real_time_data]
        scored.sort(key=lambda x: x.S_pti, reverse=True)
        ranked = [s.flight for s in scored]

        prompt = self._build_prompt(constraints, ranked, history_insights)
        _ = self._call_llm(prompt)   # TODO: parse preference notes
        return ranked

    def rerank(self, items: list[FlightRecord], feedback: dict[str, str]) -> list[FlightRecord]:
        """Like/pass rerank keyed on flight_number."""
        liked   = [f for f in items if feedback.get(f.flight_number) == "like"]
        neutral = [f for f in items if f.flight_number not in feedback]
        passed  = [f for f in items if feedback.get(f.flight_number) == "pass"]
        return liked + neutral + passed

    # ── Internal ──────────────────────────────────────────────────────────────

    def _score_flight(self, flight: FlightRecord, ctx: dict) -> ScoredFlight:
        poi_data = {
            "price":          flight.price,
            "stops_type":     flight.stops_type if hasattr(flight, "stops_type") else "direct",
            "departure_time": flight.departure_time if hasattr(flight, "departure_time") else "",
        }
        hard_results = evaluate_hc("flight", poi_data, ctx)

        # Soft: value-for-money = budget_ceiling / price (capped at 1.0)
        flight_budget = ctx.get("flight_budget", float("inf"))
        sc_val = min(flight_budget / flight.price, 1.0) if flight.price > 0 else 0.0
        result = evaluate_satisfaction(hard_results, [sc_val], [1.0], method=config.SC_AGGREGATION_METHOD)
        return ScoredFlight(flight=flight, S_pti=result["S"], HC=result["HC"], SC=result["SC"])

    @staticmethod
    def _build_context(constraints: ConstraintBundle, extra: dict) -> dict:
        return {
            "flight_budget":  extra.get("flight_budget", float("inf")),
            "allowed_modes":  extra.get("allowed_modes", set()),
            "earliest_dep":   extra.get("earliest_dep"),
            "latest_dep":     extra.get("latest_dep"),
        }

    @staticmethod
    def _build_prompt(constraints, flights, history):
        options = [(f.airline, f.flight_number, f.price) for f in flights[:5]]
        return (
            f"Flights {constraints.hard.departure_city}→{constraints.hard.destination_city}"
            f" ranked by ICDM Spti: {options}\n"
            f"Prefs: {constraints.soft}\nHistory: {history}\n"
            f"TODO: MISSING — refine prompt and extract preference notes."
        )
