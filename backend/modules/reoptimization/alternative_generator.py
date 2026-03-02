"""
modules/reoptimization/alternative_generator.py
------------------------------------------------
Context-aware alternative generator for disrupted POI handling.

Given a disrupted POI, generates 3–5 ranked replacement candidates from
the remaining attraction (and optional restaurant) pool using 7 weighted
criteria.  ACO η_ij = Spti / Dij is used for the FTRM ranking criterion;
no full ACO tour-construction run is performed.

Design principles:
  - NO schedule mutation.  This module is read-only and produces a list.
  - Called by ReOptimizationSession.check_conditions() before presenting
    the user-decision gate.
  - Restaurants are automatically included as top candidates when
    current_time falls within the soft meal windows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import time as dtime
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Output dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AlternativeOption:
    """
    A single ranked alternative presented to the user during a disruption gate.
    All fields are populated before display — no lazy evaluation.
    """
    rank: int                          # 1-based display rank
    name: str
    category: str                      # e.g. "Historical", "Park", "Restaurant"
    distance_km: float                 # from current traveller position
    travel_time_min: int               # estimated transit minutes
    expected_duration_min: int         # recommended visit / meal duration
    why_suitable: str                  # one-line human reason (context-aware)
    historical_summary: str            # cultural/historical brief (from HistoricalInsightTool)
    predicted_crowd: float             # 0.0–1.0 (0 = empty, 1 = jam-packed)
    ftrm_score: float                  # η_ij = Spti / Dij composite score [0-1]
    composite_score: float             # final weighted ranking score [0-1]
    is_meal_option: bool = False       # True if this is a restaurant alternative

    def describe(self, index: int) -> str:
        """Formatted one-block description for terminal display."""
        crowd_pct = f"{self.predicted_crowd:.0%}"
        meal_tag  = "  🍽  MEAL OPTION" if self.is_meal_option else ""
        lines = [
            f"  [{index}] {self.name}{meal_tag}",
            f"      Category : {self.category}  |  Distance: {self.distance_km:.1f} km"
            f"  |  Travel: {self.travel_time_min} min",
            f"      Duration : {self.expected_duration_min} min  "
            f"|  Crowd: {crowd_pct}  |  FTRM: {self.ftrm_score:.2f}",
            f"      Why now  : {self.why_suitable}",
        ]
        if self.historical_summary:
            lines.append(f"      History  : {self.historical_summary}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Scoring weights  (must sum to 1.0)
# ─────────────────────────────────────────────────────────────────────────────

_W_DISTANCE    = 0.25
_W_CATEGORY    = 0.15
_W_CROWD       = 0.20
_W_WEATHER     = 0.15
_W_TIMING      = 0.10
_W_FTRM        = 0.10
_W_MEAL        = 0.05

_MAX_DISTANCE_KM    = 5.0     # hard filter; beyond this → excluded
_AVG_SPEED_KMPH     = 25.0    # city travel speed for time estimate
_DEFAULT_DURATION   = 60      # minutes — fallback if not on record


# ─────────────────────────────────────────────────────────────────────────────
# Generator
# ─────────────────────────────────────────────────────────────────────────────

class AlternativeGenerator:
    """
    Generates context-aware, ranked alternatives for a disrupted POI.

    Usage:
        gen = AlternativeGenerator(historical_tool=HistoricalInsightTool())
        options = gen.generate(
            disrupted_poi_name = "Qutub Minar",
            disrupted_category = "Historical",
            candidates         = remaining_attractions,
            restaurant_pool    = recommended_restaurants,
            context            = {
                "current_lat":       28.524,
                "current_lon":       77.185,
                "current_time":      time(11, 30),
                "weather_condition": "clear",
                "crowd_forecast":    {},       # {name: float} if available
                "meal_lunch_window": ("12:00","14:00"),
                "meal_dinner_window":("19:00","21:00"),
                "n_alternatives":    5,
            }
        )
    """

    def __init__(self, historical_tool: Any = None) -> None:
        self._historical = historical_tool

    # ── Public ────────────────────────────────────────────────────────────────

    def generate(
        self,
        disrupted_poi_name: str,
        disrupted_category: str,
        candidates: list,                    # list[AttractionRecord]
        restaurant_pool: list | None = None, # list[RestaurantRecord]
        context: dict | None = None,
    ) -> list[AlternativeOption]:
        """
        Return up to `n_alternatives` ranked AlternativeOption objects.
        Schedule is NOT mutated.
        """
        ctx = context or {}
        n   = int(ctx.get("n_alternatives", 5))

        cur_lat  = float(ctx.get("current_lat",  0.0))
        cur_lon  = float(ctx.get("current_lon",  0.0))
        t_cur    = ctx.get("current_time", dtime(9, 0))
        weather  = str(ctx.get("weather_condition", "clear")).lower()
        crowd_fc = dict(ctx.get("crowd_forecast", {}))

        lunch_w  = ctx.get("meal_lunch_window",  ("12:00", "14:00"))
        dinner_w = ctx.get("meal_dinner_window", ("19:00", "21:00"))
        in_meal  = self._in_meal_window(t_cur, lunch_w, dinner_w)

        scored: list[tuple[float, AlternativeOption]] = []

        # ── Score attraction candidates ───────────────────────────────────────
        for rec in candidates:
            name = getattr(rec, "name", "")
            if name == disrupted_poi_name:
                continue

            dist_km = self._haversine(
                cur_lat, cur_lon,
                getattr(rec, "location_lat", 0.0),
                getattr(rec, "location_lon", 0.0),
            )
            if dist_km > _MAX_DISTANCE_KM:
                continue   # hard distance filter

            travel_min = self._travel_time(dist_km)
            category   = getattr(rec, "category", "Attraction")
            oh         = getattr(rec, "opening_hours", "")
            duration   = int(getattr(rec, "visit_duration_minutes",
                                     getattr(rec, "estimated_duration_minutes",
                                             _DEFAULT_DURATION)))
            rating     = float(getattr(rec, "rating", 3.0))
            is_outdoor = bool(getattr(rec, "is_outdoor", False))

            # 7-criteria composite ────────────────────────────────────────────
            s_dist    = self._score_distance(dist_km)
            s_cat     = self._score_category(category, disrupted_category)
            s_crowd   = self._score_crowd(name, crowd_fc)
            s_weather = self._score_weather(is_outdoor, weather)
            s_timing  = self._score_timing(t_cur, oh)
            s_ftrm    = self._score_ftrm(rating, dist_km)
            s_meal    = 0.0   # attractions don't get meal-window bonus

            composite = (
                _W_DISTANCE * s_dist  +
                _W_CATEGORY * s_cat   +
                _W_CROWD    * s_crowd +
                _W_WEATHER  * s_weather +
                _W_TIMING   * s_timing +
                _W_FTRM     * s_ftrm  +
                _W_MEAL     * s_meal
            )

            hist = self._get_historical_summary(name)
            why  = self._why_suitable(
                name, category, dist_km, s_crowd,
                weather, is_outdoor, in_meal, False,
            )

            opt = AlternativeOption(
                rank=0,
                name=name,
                category=category,
                distance_km=round(dist_km, 2),
                travel_time_min=travel_min,
                expected_duration_min=duration,
                why_suitable=why,
                historical_summary=hist,
                predicted_crowd=round(crowd_fc.get(name, max(0.0, s_crowd * 0.5)), 2),
                ftrm_score=round(s_ftrm, 3),
                composite_score=round(composite, 4),
                is_meal_option=False,
            )
            scored.append((composite, opt))

        # ── Add restaurant candidates during meal windows ─────────────────────
        if in_meal and restaurant_pool:
            for rec in restaurant_pool:
                name = getattr(rec, "name", "")
                dist_km = self._haversine(
                    cur_lat, cur_lon,
                    getattr(rec, "location_lat", 0.0),
                    getattr(rec, "location_lon", 0.0),
                )
                if dist_km > _MAX_DISTANCE_KM:
                    continue

                travel_min = self._travel_time(dist_km)
                rating     = float(getattr(rec, "rating", 3.0))
                oh         = getattr(rec, "opening_hours", "")

                s_dist    = self._score_distance(dist_km)
                s_cat     = 0.5   # different category from disrupted attraction
                s_crowd   = self._score_crowd(name, crowd_fc)
                s_weather = 1.0   # restaurants are indoor
                s_timing  = self._score_timing(t_cur, oh)
                s_ftrm    = self._score_ftrm(rating, dist_km)
                s_meal    = 1.0   # meal window bonus

                composite = (
                    _W_DISTANCE * s_dist  +
                    _W_CATEGORY * s_cat   +
                    _W_CROWD    * s_crowd +
                    _W_WEATHER  * s_weather +
                    _W_TIMING   * s_timing +
                    _W_FTRM     * s_ftrm  +
                    _W_MEAL     * s_meal
                )

                cuisine = getattr(rec, "cuisine_type", "")
                why = (
                    f"Near meal window ({t_cur.strftime('%H:%M')})"
                    + (f", serves {cuisine}" if cuisine else "")
                    + f", {dist_km:.1f} km away"
                )
                opt = AlternativeOption(
                    rank=0,
                    name=name,
                    category=f"Restaurant ({cuisine})" if cuisine else "Restaurant",
                    distance_km=round(dist_km, 2),
                    travel_time_min=travel_min,
                    expected_duration_min=60,
                    why_suitable=why,
                    historical_summary="",
                    predicted_crowd=round(crowd_fc.get(name, 0.3), 2),
                    ftrm_score=round(s_ftrm, 3),
                    composite_score=round(composite, 4),
                    is_meal_option=True,
                )
                scored.append((composite, opt))

        # ── Sort + assign ranks ───────────────────────────────────────────────
        scored.sort(key=lambda x: x[0], reverse=True)
        result: list[AlternativeOption] = []
        for rank, (_, opt) in enumerate(scored[:n], start=1):
            opt.rank = rank
            result.append(opt)

        return result

    # ── Criterion scorers (all return float ∈ [0, 1]) ────────────────────────

    @staticmethod
    def _score_distance(dist_km: float) -> float:
        """Closer = higher score. Linear decay to 0 at MAX_DISTANCE_KM."""
        if dist_km <= 0:
            return 1.0
        return max(0.0, 1.0 - dist_km / _MAX_DISTANCE_KM)

    @staticmethod
    def _score_category(candidate_cat: str, disrupted_cat: str) -> float:
        """Exact match = 1.0; partial substring match = 0.5; unrelated = 0.2."""
        c1 = candidate_cat.lower()
        c2 = disrupted_cat.lower()
        if c1 == c2:
            return 1.0
        if c1 in c2 or c2 in c1:
            return 0.5
        return 0.2

    @staticmethod
    def _score_crowd(name: str, crowd_forecast: dict) -> float:
        """Lower crowd = higher score. 1 - crowd_level."""
        level = float(crowd_forecast.get(name, 0.4))   # default: moderate
        return max(0.0, 1.0 - level)

    @staticmethod
    def _score_weather(is_outdoor: bool, weather: str) -> float:
        """Outdoor venues penalised on rainy/stormy weather."""
        bad_weather = weather in ("rain", "rainy", "storm", "stormy", "thunderstorm")
        if is_outdoor and bad_weather:
            return 0.1
        if not is_outdoor and bad_weather:
            return 1.0   # indoor preferred in bad weather
        return 0.8       # neutral (clear weather / indoor)

    @staticmethod
    def _score_timing(t_cur: dtime, opening_hours: str) -> float:
        """
        1.0 if within opening hours (or no data).
        0.0 if closed right now.
        """
        if not opening_hours or "-" not in opening_hours:
            return 0.8   # unknown → mildly positive
        parts = opening_hours.split("-")
        if len(parts) != 2:
            return 0.8
        try:
            open_h, open_m  = map(int, parts[0].strip().split(":"))
            close_h, close_m = map(int, parts[1].strip().split(":"))
            t_open  = dtime(open_h,  open_m)
            t_close = dtime(close_h, close_m)
            return 1.0 if t_open <= t_cur <= t_close else 0.0
        except (ValueError, AttributeError):
            return 0.8

    @staticmethod
    def _score_ftrm(rating: float, dist_km: float) -> float:
        """
        η_ij proxy = Spti / Dij  (both normalised).
        Spti proxy = rating / 5.0; Dij proxy = dist_km / MAX_DISTANCE_KM.
        """
        spti = min(1.0, max(0.0, rating / 5.0))
        dij  = max(0.01, dist_km / _MAX_DISTANCE_KM)
        return min(1.0, spti / dij)

    # ── Meal window check ─────────────────────────────────────────────────────

    @staticmethod
    def _in_meal_window(
        t_cur: dtime,
        lunch_window: tuple,
        dinner_window: tuple,
    ) -> bool:
        """Return True if current_time is inside lunch OR dinner window."""
        def _parse(w: tuple) -> tuple[dtime, dtime]:
            def _t(s: str) -> dtime:
                h, m = map(int, s.split(":"))
                return dtime(h, m)
            return _t(w[0]), _t(w[1])

        try:
            ls, le = _parse(lunch_window)
            ds, de = _parse(dinner_window)
            return (ls <= t_cur <= le) or (ds <= t_cur <= de)
        except (ValueError, TypeError):
            return False

    # ── Historical summary ────────────────────────────────────────────────────

    def _get_historical_summary(self, name: str) -> str:
        """Fetch short cultural/historical text. Returns '' on any failure."""
        if self._historical is None:
            return ""
        try:
            result = self._historical.get_insight(name)
            return getattr(result, "summary", "") or ""
        except Exception:
            return ""

    # ── Why-suitable text ─────────────────────────────────────────────────────

    @staticmethod
    def _why_suitable(
        name: str,
        category: str,
        dist_km: float,
        crowd_score: float,
        weather: str,
        is_outdoor: bool,
        in_meal: bool,
        is_restaurant: bool,
    ) -> str:
        """Build a short one-line human-readable reason."""
        parts: list[str] = []
        if dist_km < 1.0:
            parts.append("very close by")
        elif dist_km < 3.0:
            parts.append(f"{dist_km:.1f} km away")
        if crowd_score > 0.7:
            parts.append("low crowd expected")
        bad_weather = weather in ("rain", "rainy", "storm", "stormy")
        if bad_weather and not is_outdoor:
            parts.append("indoor venue — weather safe")
        if in_meal and is_restaurant:
            parts.append("within meal window")
        if not parts:
            parts.append(f"similar {category.lower()} experience")
        return ", ".join(parts).capitalize()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance in km."""
        R = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        a = (math.sin(math.radians((lat2 - lat1) / 2)) ** 2
             + math.cos(p1) * math.cos(p2)
             * math.sin(math.radians((lon2 - lon1) / 2)) ** 2)
        return 2 * R * math.asin(math.sqrt(max(0.0, a)))

    @staticmethod
    def _travel_time(dist_km: float) -> int:
        """Estimated city travel time in minutes at AVG_SPEED_KMPH."""
        return max(5, int((dist_km / _AVG_SPEED_KMPH) * 60))
